"""Effortless argument parser.

Run Python functions from the command line with ``run(func)``.
"""
from __future__ import absolute_import, division, unicode_literals, print_function

import inspect
import logging
import re
import sys
from argparse import ArgumentParser, RawTextHelpFormatter, ArgumentDefaultsHelpFormatter
from collections import defaultdict, namedtuple, OrderedDict
from enum import Enum
from typing import List, Iterable, Sequence, Union, Callable, Dict
from typing import get_type_hints as _get_type_hints
from xml.etree import ElementTree

from docutils.core import publish_doctree
try:
    from sphinx.ext.napoleon.docstring import GoogleDocstring, NumpyDocstring
except ImportError:  # pragma: no cover
    from sphinxcontrib.napoleon.docstring import GoogleDocstring
    from sphinxcontrib.napoleon.docstring import NumpyDocstring

# The 2.x builtin goes first so we don't get future's builtins if installed
try:
    import __builtin__ as builtins
except ImportError:  # pragma: no cover
    import builtins

if not hasattr(inspect, 'signature'):  # pragma: no cover
    import funcsigs
    inspect.signature = funcsigs.signature

if sys.version_info.major == 2:  # pragma: no cover
    def _get_type_hints(*args, **kwargs):
        return {}

_LIST_TYPES = [List, Iterable, Sequence]

log = logging.getLogger(__name__)

_Doc = namedtuple('_Doc', ('text', 'params'))
_Param = namedtuple('_Param', ('text', 'type'))
_Type = namedtuple('_Type', ('type', 'container'))

_parsers = {}


def run(*funcs, **kwargs):
    """run(*funcs, parsers=None, short=None, argv=None)

    Process command line arguments and run the given functions.

    If ``funcs`` is a single function, it is parsed and run.
    If ``funcs`` is multiple functions, each one is given a subparser with its
    name, and only the chosen function is run.

    :param Callable funcs: Function or functions to process and run
    :param parsers: Dictionary mapping types to parsers to use for parsing
        function arguments.
    :type parsers: Dict[type, Callable[[str], type]]
    :param short: Dictionary mapping parameter names to letters to use as
        alternative short flags.
    :type short: Dict[str, str]
    :param List[str] argv: Command line arguments to parse (default: sys.argv[1:])
    :return: The value returned by the function that was run
    """
    parsers = kwargs.pop('parsers', None)
    short = kwargs.pop('short', {})
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
    parser = ArgumentParser(formatter_class=_Formatter)
    parser.set_defaults()
    if main:
        _populate_parser(main, parser, parsers, short)
    else:
        subparsers = parser.add_subparsers()
        for func in funcs:
            subparser = subparsers.add_parser(func.__name__, formatter_class=_Formatter)
            _populate_parser(func, subparser, parsers, short)
            subparser.set_defaults(_func=func)
    args = parser.parse_args(argv)
    # Workaround for http://bugs.python.org/issue9253#msg186387
    if not main and not hasattr(args, '_func'):
        parser.error('too few arguments')
    if main:
        return _call_function(main, args)
    else:
        return _call_function(args._func, args)


class _Formatter(RawTextHelpFormatter, ArgumentDefaultsHelpFormatter):
    pass


def parser(type_):
    raise DeprecationWarning(
        'this function was deprecated in defopt 1.3 and removed in defopt 2.0 '
        '(specify mapping from type to parser in call to defopt.run)')


def _populate_parser(func, parser, parsers, short):
    sig = inspect.signature(func)
    doc = _parse_doc(func)
    hints = _get_type_hints(func)
    parser.description = doc.text
    for name, param in sig.parameters.items():
        kwargs = {}
        if name in doc.params:
            kwargs['help'] = doc.params[name].text
        type_ = _get_type(func, name, doc, hints)
        if param.kind == param.VAR_KEYWORD:
            raise ValueError('**kwargs not supported')
        if type_.type == bool and param.default != param.empty:
            # Special case: just add parameterless --name and --no-name flags.
            _add_argument(parser, name, short,
                          action='store_true',
                          default=param.default,
                          # Add help if available.
                          **kwargs)
            _add_argument(parser, 'no-' + name, short,
                          action='store_false',
                          default=param.default,
                          dest=name)
            continue
        if type_.container:
            assert type_.container == list
            kwargs['nargs'] = '*'
            if param.default == param.empty:
                kwargs['required'] = True
            else:
                kwargs['default'] = param.default
        elif param.default == param.empty:
            kwargs['_positional'] = True
            if param.kind == param.VAR_POSITIONAL:
                kwargs['nargs'] = '*'
        else:
            kwargs['default'] = param.default
        if inspect.isclass(type_.type) and issubclass(type_.type, Enum):
            # Want these to behave like argparse choices.
            kwargs['choices'] = _ValueOrderedDict((x.name, x) for x in type_.type)
            kwargs['type'] = _enum_getter(type_.type)
        else:
            kwargs['type'] = _get_parser(type_.type, parsers)
        _add_argument(parser, name, short, **kwargs)


def _add_argument(parser, name, short, _positional=False, **kwargs):
    if _positional:
        args = [name]
    else:
        name = name.replace('_', '-')
        args = ['--' + name]
        if name in short:
            args.insert(0, '-' + short[name])
    return parser.add_argument(*args, **kwargs)


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
    # Support for legacy list syntax "list[type]".
    # (This intentionally won't catch `List` or `typing.List`)
    match = re.match(r'([a-z]\w+)\[([\w\.]+)\]', name)
    if match:
        container, type_ = match.groups()
        if container != 'list':
            raise ValueError('unsupported container type: {}'.format(container))
        return _Type(eval(type_, globalns), list)
    return _get_type_from_hint(eval(name, globalns))


def _get_type_from_hint(hint):
    if any(_is_generic_type(hint, x) for x in _LIST_TYPES):
        # In Python 3.5.2, typing.GenericMeta distinguishes between
        # parameters (which are unfilled) and args (which are filled).
        [type_] = getattr(hint, '__args__', hint.__parameters__)
        return _Type(type_, list)
    elif issubclass(hint, Union):
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
    doctext = []
    for element in etree:
        if element.tag == 'paragraph':
            doctext.append(_get_text(element))
        elif element.tag == 'literal_block':
            doctext.append(_indent(_get_text(element)))
    doctext = '\n\n'.join(doctext)
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


def _indent(text):
    tab = '    '
    return tab + text.replace('\n', '\n' + tab)


def _get_parser(type_, parsers=None):
    parser = _find_parser(type_, parsers or {})

    # Make a parser with the name the user expects to see in error messages.
    def named_parser(string):
        return parser(string)

    named_parser.__name__ = type_.__name__
    return named_parser


def _find_parser(type_, parsers):
    try:
        return parsers[type_]
    except KeyError:
        pass
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
