from __future__ import absolute_import, division, unicode_literals, print_function

import argparse
from collections import defaultdict, namedtuple
from enum import Enum
import inspect
import logging
import re
import sys
from xml.etree import ElementTree

from docutils.core import publish_doctree

# The 2.x builtin goes first so we don't get future's builtins if installed
try:
    import __builtin__ as builtins
except ImportError:  # pragma: no cover
    import builtins

if not hasattr(inspect, 'signature'):  # pragma: no cover
    import funcsigs
    inspect.signature = funcsigs.signature

log = logging.getLogger(__name__)

_Doc = namedtuple('_Doc', ('text', 'params'))
_Param = namedtuple('_Param', ('text', 'type'))
_Type = namedtuple('_Type', ('type', 'container'))

_parsers = {}


def parser(type_):
    """Return a function that registers a parser for ``type_``.

    The function must take a single string argument and is returned unmodified.

    Use as a decorator.

    >>> @parser(type)
    ... def func(string): pass

    :param type type_: Type to register parser for
    """
    def decorator(func):
        if type_ in _parsers:
            raise Exception('multiple parsers found for {}'.format(type_.__name__))
        _parsers[type_] = func
    return decorator


# This signature is overridden in docs/api.rst with the Python 3 version.
def run(*funcs, **kwargs):
    """Process command line arguments and run the given functions.

    If ``funcs`` is a single function, it is parsed and run.
    If ``funcs`` is multiple functions, each one is given a subparser with its
    name, and only the chosen function is run.

    :param function funcs: Function or functions to process and run
    :param list[str] argv: Command line arguments to parse (default: sys.argv[1:])
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
        _call_function(main, args)
    else:
        _call_function(args._func, args)


def _populate_parser(func, parser):
    sig = inspect.signature(func)
    doc = _parse_doc(func)
    parser.description = doc.text
    for name, param in sig.parameters.items():
        if name not in doc.params:
            raise ValueError('no documentation found for parameter {}'.format(name))
        kwargs = {'help': doc.params[name].text}
        type_ = _get_type(doc.params[name].type)
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
            kwargs['choices'] = _ValueDict({x.name: x for x in type_.type})
            kwargs['type'] = _enum_getter(type_.type)
        else:
            kwargs['type'] = _get_parser(type_.type)
        parser.add_argument(name_or_flag, **kwargs)


def _get_type(name):
    match = re.match(r'(\w+)\[(\w+)\]', name)
    container = None
    if match:
        container, name = match.groups()
        if container == 'list':
            container = list
        else:
            raise ValueError('container types other than list not supported')
    try:
        type_ = _evaluate(name, stack_depth=3)
    except AttributeError:
        raise ValueError('could not find definition for type {}'.format(name))
    return _Type(type_, container)


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
    func(*positionals, **keywords)


def _parse_doc(func):
    """Extract documentation from a function's docstring.

    All documented parameters are guaranteed to have type information.
    """
    doc = inspect.getdoc(func)
    if doc is None:
        return _Doc('', {})
    dom = publish_doctree(doc).asdom()
    etree = ElementTree.fromstring(dom.toxml())
    doctext = '\n\n'.join(x.text for x in etree.findall('paragraph'))
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
        text = ''.join(field_body.itertext())
        log.debug('%s %s: %s', doctype, name, text)
        if doctype in params[name]:
            raise ValueError('{} defined twice for {}'.format(doctype, name))
        params[name][doctype] = text

    tuples = {}
    for name, values in params.items():
        if 'type' not in values:
            raise ValueError('no type found for parameter {}'.format(name))
        tuples[name] = _Param(values.get('param'), values.get('type'))
    return _Doc(doctext, tuples)


def _evaluate(name, stack_depth=None):
    """Find an object by name.

    :param name: Name of the object to evaluate. May contain dotted lookups,
        e.g. 'a.b' finds 'a' in the target frame, then looks inside 'a'
        to find 'b'.
    :type name: str
    :param stack_depth: How far up the stack to evaluate locals and globals.
        Specify 0 for your frame, 1 for your caller's frame, etc.
        If unspecified, `name` is assumed to refer to a builtin.
    :type stack_depth: int
    """
    log.debug('evaluating %s', name)
    things = dict(vars(builtins))
    if stack_depth is not None:
        things.update(inspect.stack()[stack_depth + 1][0].f_locals)
        things.update(inspect.stack()[stack_depth + 1][0].f_globals)
    parts = name.split('.')
    part = parts[0]
    if part not in things:
        raise AttributeError("'{}' is not a builtin or module attribute".format(part))
    thing = things[part]
    for part in parts[1:]:
        thing = getattr(thing, part)
    log.debug('evaluated to %r', thing)
    return thing


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
    if string.lower() in ['t', 'true']:
        return True
    elif string.lower() in ['f', 'false']:
        return False
    else:
        raise ValueError('{} is not a valid boolean string'.format(string))


class _ValueDict(dict):
    """Dictionary that tests membership based on values instead of keys."""
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
