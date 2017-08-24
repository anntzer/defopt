"""Effortless argument parser.

Run Python functions from the command line with ``run(func)``.
"""
from __future__ import (
    absolute_import, division, unicode_literals, print_function)

import contextlib
import inspect
import logging
import re
import sys
import warnings
from argparse import (
    SUPPRESS, ArgumentParser, RawTextHelpFormatter, _AppendAction,
    _StoreAction)
from collections import defaultdict, namedtuple, Counter, OrderedDict
from enum import Enum
from typing import Callable, Dict, Iterable, List, Sequence, Tuple, Union
from typing import get_type_hints as _get_type_hints
from xml.etree import ElementTree

from docutils.core import publish_doctree
from sphinxcontrib.napoleon.docstring import GoogleDocstring, NumpyDocstring

try:
    from inspect import signature as _inspect_signature
except ImportError:  # pragma: no cover
    from funcsigs import signature as _inspect_signature

try:
    from pathlib import Path
except ImportError:
    class Path(object):
        """Dummy type, such that no user input is ever of that type.
        """

try:
    from colorama import colorama_text as _colorama_text
except ImportError:
    @contextlib.contextmanager
    def _colorama_text(*args):
        yield

if sys.version_info.major == 2:  # pragma: no cover
    def _get_type_hints(obj, globalns=None, localns=None):
        return getattr(obj, '__annotations__', {})
    _basestring = basestring
else:
    _basestring = str

__all__ = ['run']
__version__ = '3.2.0'

_LIST_TYPES = [List, Iterable, Sequence]
_PARAM_TYPES = ['param', 'parameter', 'arg', 'argument', 'key', 'keyword']
_TYPE_NAMES = ['type', 'kwtype']

log = logging.getLogger(__name__)

class _Doc(namedtuple('_Doc', ('paragraphs', 'params'))):
    @property
    def text(self):
        return '\n\n'.join(self.paragraphs)

_Param = namedtuple('_Param', ('text', 'type'))
_Type = namedtuple('_Type', ('type', 'container'))


def run(funcs, *args, **kwargs):
    """run(funcs, *, parsers=None, short=None, strict_kwonly=True, show_types=False, argv=None)

    Process command line arguments and run the given functions.

    ``funcs`` can be a single callable, which is parsed and run; or it can be
    a list of callables, in which case each one is given a subparser with its
    name, and only the chosen callable is run.

    :param Callable funcs: Function or functions to process and run
    :param parsers: Dictionary mapping types to parsers to use for parsing
        function arguments.
    :type parsers: Dict[type, Callable[[str], type]]
    :param short: Dictionary mapping parameter names (after conversion of
        underscores to dashes) to letters, to use as alternative short flags.
        Defaults to ``None``, which means to generate short flags for any
        non-ambiguous option.  Set to ``{}`` to completely disable short flags.
    :type short: Dict[str, str]
    :param bool strict_kwonly: If `True` (the default), only keyword-only
        arguments are converted into command line flags; non-keyword-only
        arguments become optional positional command line parameters.  Note
        that on Python 2, setting this to False is the only way to obtain
        command line flags.
    :param bool show_types: If `True`, display type names after parameter
        descriptions in the the help text.
    :param List[str] argv: Command line arguments to parse (default:
        sys.argv[1:])
    :return: The value returned by the function that was run
    """
    argv = kwargs.pop('argv', None)
    if argv is None:
        argv = sys.argv[1:]
    parser = _create_parser(funcs, *args, **kwargs)
    with _colorama_text():
        args = parser.parse_args(argv)
    # Workaround for http://bugs.python.org/issue9253#msg186387
    if not hasattr(args, '_func'):
        parser.error('too few arguments')
    return _call_function(args._func, args)


def _create_parser(funcs, *args, **kwargs):
    parsers = kwargs.pop('parsers', None)
    short = kwargs.pop('short', None)
    strict_kwonly = kwargs.pop('strict_kwonly', True)
    show_types = kwargs.pop('show_types', False)
    if kwargs:
        raise TypeError(
            'unexpected keyword argument: {}'.format(list(kwargs)[0]))
    if args:
        warnings.warn(
            'Passing multiple functions as separate arguments is deprecated; '
            'pass a list of functions instead', DeprecationWarning)
        funcs = [funcs] + list(args)
    formatter_class = _NoTypeFormatter
    if show_types:
        formatter_class = _Formatter
    parser = ArgumentParser(formatter_class=formatter_class)
    if callable(funcs):
        _populate_parser(funcs, parser, parsers, short, strict_kwonly)
        parser.set_defaults(_func=funcs)
    else:
        subparsers = parser.add_subparsers()
        for func in funcs:
            subparser = subparsers.add_parser(
                func.__name__.replace("_", "-"),
                formatter_class=formatter_class,
                help=_parse_function_docstring(func).paragraphs[0])
            _populate_parser(func, subparser, parsers, short, strict_kwonly)
            subparser.set_defaults(_func=func)
    return parser


class _Formatter(RawTextHelpFormatter):
    show_types = True

    # Modified from ArgumentDefaultsHelpFormatter to add type information,
    # and remove defaults for varargs (which use _AppendAction instead of
    # _StoreAction).
    def _get_help_string(self, action):
        info = []
        if self.show_types:
            if action.type is not None and '%(type)' not in action.help:
                info.append('type: %(type)s')
        if (not isinstance(action, _AppendAction)
                and '%(default)' not in action.help
                and action.default is not SUPPRESS
                and action.option_strings):
            info.append('default: %(default)s')
        if info:
            return action.help + '\n({})'.format(', '.join(info))
        else:
            return action.help


class _NoTypeFormatter(_Formatter):
    show_types = False


def _populate_parser(func, parser, parsers, short, strict_kwonly):
    full_sig = _inspect_signature(func)
    sig = full_sig.replace(
        parameters=list(param for param in full_sig.parameters.values()
                        if not param.name.startswith('_')))
    doc = _parse_function_docstring(func)
    hints = _get_type_hints(func)
    parser.description = doc.text

    types = dict((name, _get_type(func, name, doc, hints))
                 for name, param in sig.parameters.items())
    positionals = set(name for name, param in sig.parameters.items()
                      if ((param.default is param.empty or strict_kwonly)
                          and not types[name].container
                          and param.kind != param.KEYWORD_ONLY))
    if short is None:
        count_initials = Counter(name[0] for name in sig.parameters
                                 if name not in positionals)
        short = dict(
            (name.replace('_', '-'), name[0]) for name in sig.parameters
            if name not in positionals and count_initials[name[0]] == 1)

    for name, param in sig.parameters.items():
        kwargs = {}
        if name in doc.params:
            help_ = doc.params[name].text
            if help_ is not None:
                kwargs['help'] = help_.replace('%', '%%')
        type_ = types[name]
        if param.kind == param.VAR_KEYWORD:
            raise ValueError('**kwargs not supported')
        hasdefault = param.default is not param.empty
        default = param.default if hasdefault else SUPPRESS
        required = not hasdefault and param.kind != param.VAR_POSITIONAL
        positional = name in positionals
        if type_.type == bool and not positional and not type_.container:
            # Special case: just add parameterless --name and --no-name flags.
            group = parser.add_mutually_exclusive_group(required=required)
            _add_argument(group, name, short,
                          action='store_true',
                          default=default,
                          # Add help if available.
                          **kwargs)
            _add_argument(group, 'no-' + name, short,
                          action='store_false',
                          default=default,
                          dest=name)
            continue
        if positional:
            kwargs['_positional'] = True
            if param.default is not param.empty:
                kwargs['nargs'] = '?'
                kwargs['default'] = default
            if param.kind == param.VAR_POSITIONAL:
                kwargs['nargs'] = '*'
                # This is purely to override the displayed default of None.
                # Ideally we wouldn't want to show a default at all.
                kwargs['default'] = []
        else:
            kwargs['required'] = required
            kwargs['default'] = default
        if type_.container:
            assert type_.container == list
            kwargs['nargs'] = '*'
            if param.kind == param.VAR_POSITIONAL:
                kwargs['action'] = 'append'
                kwargs['default'] = []
        make_tuple = member_types = None
        if _is_generic_type(type_.type, Tuple):
            make_tuple = tuple
            member_types = type_.type.__args__
            kwargs['nargs'] = len(member_types)
            kwargs['action'] = _make_store_tuple_action_class(
                tuple, member_types, parsers)
        elif (inspect.isclass(type_.type) and issubclass(type_.type, tuple)
              and hasattr(type_.type, '_fields')
              and hasattr(type_.type, '_field_types')):
            # Before Py3.6, `_field_types` does not preserve order, so retrieve
            # the order from `_fields`.
            member_types = tuple(type_.type._field_types[field]
                                 for field in type_.type._fields)
            kwargs['nargs'] = len(member_types)
            kwargs['action'] = _make_store_tuple_action_class(
                lambda args: type_.type(*args), member_types, parsers)
            if not positional:  # http://bugs.python.org/issue14074
                kwargs['metavar'] = type_.type._fields
        elif inspect.isclass(type_.type) and issubclass(type_.type, Enum):
            # Want these to behave like argparse choices.
            kwargs['choices'] = _ValueOrderedDict(
                (x.name, x) for x in type_.type)
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
            raise ValueError(
                'unsupported container type: {}'.format(container))
        return _Type(eval(type_, globalns), list)
    return _get_type_from_hint(eval(name, globalns))


def _get_type_from_hint(hint):
    if any(_is_generic_type(hint, x) for x in _LIST_TYPES):
        # In Python 3.5.2, typing.GenericMeta distinguishes between
        # parameters (which are unfilled) and args (which are filled).
        [type_] = getattr(hint, '__args__', hint.__parameters__)
        return _Type(type_, list)
    elif _is_generic_type(hint, Union):
        # For Union[type, NoneType], just use type.
        args = _get_union_args(hint)
        if len(args) == 2:
            type_, none = args
            if none == type(None):
                return _Type(type_, None)
    return _Type(hint, None)


def _is_generic_type(thing, generic_type):
    if hasattr(thing, '__origin__'):
        return thing.__origin__ is generic_type
    # Unions from older versions of typing don't have a __origin__,
    # so we have to find some other way to identify them.
    # (see https://github.com/python/typing/pull/283).
    if generic_type is Union:
        return getattr(thing, '__union_params__', [])
    return False


def _get_union_args(union):
    try:
        return union.__args__
    except AttributeError:
        return union.__union_params__


def _call_function(func, args):
    positionals = []
    keywords = {}
    sig = _inspect_signature(func)
    for name, param in sig.parameters.items():
        arg = getattr(args, name)
        if param.kind in [param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD]:
            positionals.append(arg)
        elif param.kind == param.VAR_POSITIONAL:
            positionals.extend(arg)
        else:
            keywords[name] = arg
    return func(*positionals, **keywords)


def _parse_function_docstring(func):
    return _parse_docstring(inspect.getdoc(func))


_parse_docstring_cache = {}
def _parse_docstring(doc):
    """Extract documentation from a function's docstring."""
    _cache_key = doc
    try:
        return _parse_docstring_cache[_cache_key]
    except KeyError:
        pass

    if doc is None:
        return _Doc([''], {})

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
            if doctype not in _PARAM_TYPES:
                log.debug('ignoring field %s', field_name.text)
                continue
            log.debug('inline param type %s', type_)
            if 'type' in params[name]:
                raise ValueError('type defined twice for {}'.format(name))
            params[name]['type'] = type_
        else:
            log.debug('ignoring field %s', field_name.text)
            continue
        if doctype in _PARAM_TYPES:
            doctype = 'param'
        if doctype in _TYPE_NAMES:
            doctype = 'type'
        text = _get_text(field_body)
        log.debug('%s %s: %s', doctype, name, text)
        if doctype in params[name]:
            raise ValueError('{} defined twice for {}'.format(doctype, name))
        params[name][doctype] = text

    tuples = {}
    for name, values in params.items():
        tuples[name] = _Param(values.get('param'), values.get('type'))

    parsed = _parse_docstring_cache[_cache_key] = _Doc(doctext or [''], tuples)
    return parsed


def _itertext_ansi(node):
    # Implementation modified from `ElementTree.Element.itertext`.
    tag = node.tag
    if not isinstance(tag, _basestring) and tag is not None:
        return
    ansi_code = {"emphasis": "\033[3m",  # *foo*: italic.
                 "strong": "\033[1m",  # **foo**: bold.
                 "title_reference": "\033[4m",  # `foo`: underlined.
                 }.get(tag, "")
    t = node.text
    if t:
        yield ansi_code
        yield t
        if ansi_code:
            yield "\033[0m"  # Reset.
    for e in node:
        for t in _itertext_ansi(e):
            yield t
        t = e.tail
        if t:
            yield t


def _get_text(node):
    return ''.join(_itertext_ansi(node))


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
    if type_ in [int, str, float, Path]:
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
    getter.__name__ = enum.__name__
    return getter


def _make_store_tuple_action_class(make_tuple, member_types, parsers):
    class _StoreTupleAction(_StoreAction):
        def __call__(self, parser, namespace, values, option_string=None):
            value = make_tuple(_get_parser(arg, parsers)(value)
                               for arg, value in zip(member_types, values))
            return super(_StoreTupleAction, self).__call__(
                parser, namespace, value, option_string)
    return _StoreTupleAction
