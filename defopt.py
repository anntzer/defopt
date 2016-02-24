"""Effortless argument parser.

Run Python functions from the command line with ``run(func)``.

Specify type parsers with ``@parser(type)``.
"""
from __future__ import absolute_import, division, unicode_literals, print_function

import argparse
from collections import defaultdict, namedtuple, OrderedDict
from enum import Enum
import inspect
import logging
import re
import sys
import typing
from xml.etree import ElementTree

from docutils.core import publish_doctree
from sphinxcontrib.napoleon.docstring import GoogleDocstring, NumpyDocstring

# The 2.x builtin goes first so we don't get future's builtins if installed
try:
    import __builtin__ as builtins
except ImportError:  # pragma: no cover
    import builtins

if not hasattr(inspect, 'signature'):  # pragma: no cover
    import funcsigs
    inspect.signature = funcsigs.signature

if sys.version_info.major == 2:  # pragma: no cover
    typing.get_type_hints = lambda *args, **kwargs: {}

_LIST_TYPES = [typing.List, typing.Iterable, typing.Sequence]

log = logging.getLogger(__name__)

_Doc = namedtuple('_Doc', ('text', 'params'))
_Param = namedtuple('_Param', ('text', 'type'))
_Type = namedtuple('_Type', ('type', 'container'))

_parsers = {}


# This signature is overridden in docs/api.rst with the Python 3 version.
def run(*funcs, **kwargs):
    """run(*funcs, argv=None)

    Process command line arguments and run the given functions.

    If ``funcs`` is a single function, it is parsed and run.
    If ``funcs`` is multiple functions, each one is given a subparser with its
    name, and only the chosen function is run.

    :param function funcs: Function or functions to process and run
    :param list[str] argv: Command line arguments to parse (default: sys.argv[1:])
    :return: The value returned by the function that was run.
        (This is experimental behavior and will be confirmed or removed in a
        future version.)
    """
    argv = kwargs.pop('argv', None)
    if kwargs:
        raise TypeError('unexpected keyword argument: {}'.format(list(kwargs)[0]))
    if not funcs:
        raise ValueError('need at least one function to run')
    if argv is None:
        argv = sys.argv[1:]
    main = None
    if len(funcs) == 1:
        [main] = funcs
    parser = argparse.ArgumentParser()
    parser.set_defaults()
    if main:
        _populate_parser(main, parser)
    else:
        subparsers = parser.add_subparsers()
        for func in funcs:
            subparser = subparsers.add_parser(func.__name__)
            _populate_parser(func, subparser)
            subparser.set_defaults(_func=func)
    args = parser.parse_args(argv)
    # Workaround for http://bugs.python.org/issue9253#msg186387
    if not main and not hasattr(args, '_func'):
        parser.error('too few arguments')
    if main:
        return _call_function(main, args)
    else:
        return _call_function(args._func, args)


def parser(type_):
    """Return a function that registers a parser for ``type_``.

    The parser must take a single string argument and is returned unmodified.

    Use as a decorator.

    >>> @parser(type)
    ... def func(string): pass

    :param type type_: Type to register parser for
    """
    def decorator(func):
        if type_ in _parsers:
            raise Exception('multiple parsers found for {}'.format(type_.__name__))
        _parsers[type_] = func
        return func
    return decorator


def _populate_parser(func, parser):
    sig = inspect.signature(func)
    doc = _parse_doc(func)
    hints = typing.get_type_hints(func)
    parser.description = doc.text
    for name, param in sig.parameters.items():
        kwargs = {}
        if name in doc.params:
            kwargs['help'] = doc.params[name].text
        type_ = _get_type(func, name, doc, hints)
        if param.kind == param.VAR_KEYWORD:
            raise ValueError('**kwargs not supported')
        if type_.container:
            assert type_.container == list
            name_or_flag = '--' + name
            kwargs['nargs'] = '*'
            if param.default == param.empty:
                kwargs['required'] = True
            else:
                kwargs['default'] = param.default
        elif param.default == param.empty:
            name_or_flag = name
            if param.kind == param.VAR_POSITIONAL:
                kwargs['nargs'] = '*'
        else:
            name_or_flag = '--' + name
            kwargs['default'] = param.default
        if inspect.isclass(type_.type) and issubclass(type_.type, Enum):
            # Want these to behave like argparse choices.
            kwargs['choices'] = _ValueOrderedDict((x.name, x) for x in type_.type)
            kwargs['type'] = _enum_getter(type_.type)
        else:
            kwargs['type'] = _get_parser(type_.type)
        parser.add_argument(name_or_flag, **kwargs)


def _get_type(func, name, doc, hints):
    """Retrieve a type from either documentation or annotations.

    If both are specified, they must agree exactly.
    """
    doc_type = doc.params.get(name, _Param(None, None)).type
    if doc_type is not None:
        doc_type = _get_type_from_doc(doc_type, func.__globals__)

    try:
        hint = hints[name]
    except KeyError:
        hint_type = None
    else:
        hint_type = _get_type_from_hint(hint)

    chosen = [x is not None for x in [doc_type, hint_type]]
    if not any(chosen):
        raise ValueError('no type found for parameter {}'.format(name))
    if all(chosen) and doc_type != hint_type:
        raise ValueError('conflicting types found for parameter {}: {}, {}'
                         .format(name, doc.params[name].type, hint.__name__))
    return doc_type or hint_type


def _get_type_from_doc(name, globalns):
    match = re.match(r'([\w\.]+)\[([\w\.]+)\]', name)
    container = None
    if match:
        container, name = match.groups()
        container = _evaluate_type(container, globalns)
        if container in [list] + _LIST_TYPES:
            container = list
        else:
            raise ValueError('unsupported container type: {}'.format(container.__name__))
    type_ = _evaluate_type(name, globalns)
    return _Type(type_, container)


def _get_type_from_hint(hint):
    if any(_is_generic_type(hint, x) for x in _LIST_TYPES):
        [type_] = hint.__parameters__
        return _Type(type_, list)
    elif issubclass(hint, typing.Union):
        # For Union[type, NoneType], just use type.
        if len(hint.__union_params__) == 2:
            type_, none = hint.__union_params__
            if none == type(None):
                return _Type(type_, None)
    return _Type(hint, None)


def _is_generic_type(thing, generic_type):
    if not hasattr(thing, '__origin__'):
        return False
    return thing.__origin__ == generic_type


def _call_function(func, args):
    positionals = []
    keywords = {}
    sig = inspect.signature(func)
    for name, param in sig.parameters.items():
        arg = getattr(args, name)
        if param.kind in [param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD]:
            positionals.append(arg)
        elif param.kind == param.VAR_POSITIONAL:
            positionals.extend(arg)
        else:
            keywords[name] = arg
    return func(*positionals, **keywords)


def _parse_doc(func):
    """Extract documentation from a function's docstring."""
    doc = inspect.getdoc(func)
    if doc is None:
        return _Doc('', {})

    # Convert Google- or Numpy-style docstrings to RST.
    # (Should do nothing if not in either style.)
    doc = str(GoogleDocstring(doc))
    doc = str(NumpyDocstring(doc))

    dom = publish_doctree(doc).asdom()
    etree = ElementTree.fromstring(dom.toxml())
    doctext = '\n\n'.join(_get_text(x) for x in etree.findall('paragraph'))
    fields = etree.findall('.//field')

    params = defaultdict(dict)
    for field in fields:
        field_name = field.find('field_name')
        field_body = field.find('field_body')
        parts = field_name.text.split()
        if len(parts) == 2:
            doctype, name = parts
        elif len(parts) == 3:
            doctype, type_, name = parts
            if doctype != 'param':
                log.debug('ignoring field %s', field_name.text)
                continue
            log.debug('inline param type %s', type_)
            if 'type' in params[name]:
                raise ValueError('type defined twice for {}'.format(name))
            params[name]['type'] = type_
        else:
            log.debug('ignoring field %s', field_name.text)
            continue
        text = _get_text(field_body)
        log.debug('%s %s: %s', doctype, name, text)
        if doctype in params[name]:
            raise ValueError('{} defined twice for {}'.format(doctype, name))
        params[name][doctype] = text

    tuples = {}
    for name, values in params.items():
        tuples[name] = _Param(values.get('param'), values.get('type'))
    return _Doc(doctext, tuples)


def _get_text(node):
    return ''.join(node.itertext())


def _evaluate_type(name, globals_=None):
    """Find an object by name.

    :param str name: Name of the object to evaluate. May contain dotted
        lookups, e.g. 'a.b' finds 'a' in the target namespace, then looks
        inside 'a' to find 'b'.
    :param dict[str, object] globals_: Globals to inspect for name. If not
        supplied, ``name`` is assumed to refer to a built-in.
    """
    try:
        log.debug('evaluating %s', name)
        namespace = dict(vars(builtins))
        if globals_:
            namespace.update(globals_)
        parts = name.split('.')
        part = parts[0]
        if part not in namespace:
            raise AttributeError("'{}' is not a builtin or module attribute".format(part))
        member = namespace[part]
        for part in parts[1:]:
            member = getattr(member, part)
        log.debug('evaluated to %r', member)
        return member
    except AttributeError:
        raise ValueError('could not find definition for type {}'.format(name))


def _get_parser(type_):
    parser = _find_parser(type_)

    # Make a parser with the name the user expects to see in error messages.
    def named_parser(string):
        return parser(string)

    named_parser.__name__ = type_.__name__
    return named_parser


def _find_parser(type_):
    try:
        return _parsers[type_]
    except KeyError:
        pass
    if type_ in [int, str, float]:
        return type_
    elif type_ == bool:
        return _parse_bool
    elif type_ == list:
        raise ValueError('unable to parse list (try list[type])')
    else:
        raise Exception('no parser found for type {}'.format(type_.__name__))


def _parse_bool(string):
    if string.lower() in ['t', 'true', '1']:
        return True
    elif string.lower() in ['f', 'false', '0']:
        return False
    else:
        raise ValueError('{} is not a valid boolean string'.format(string))


class _ValueOrderedDict(OrderedDict):
    """OrderedDict that tests membership based on values instead of keys."""
    def __contains__(self, item):
        return item in self.values()


def _enum_getter(enum):
    """Return a function that converts a string to an enum member.

    If ``name`` does not correspond to a member of the enum, it is returned
    unmodified so that argparse can properly report the invalid value.
    """
    def getter(name):
        try:
            return enum[name]
        except KeyError:
            return name
    return getter
