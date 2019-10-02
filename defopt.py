"""
Effortless argument parser.

Run Python functions from the command line with ``run(func)``.
"""

import ast
import collections.abc
import contextlib
import functools
import inspect
import re
import sys
import typing
from argparse import (
    SUPPRESS, ArgumentError, ArgumentTypeError, ArgumentParser,
    RawTextHelpFormatter, _AppendAction, _StoreAction)
from collections import defaultdict, namedtuple, Counter
from enum import Enum
from pathlib import PurePath
from typing import Any, Callable, Dict, List, Optional, Union

from docutils.core import publish_doctree
from docutils.nodes import NodeVisitor, SkipNode
from docutils.parsers.rst.states import Body
from docutils.utils import roman
from sphinxcontrib.napoleon.docstring import GoogleDocstring, NumpyDocstring
import typing_inspect as ti

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

try:
    from colorama import colorama_text as _colorama_text
except ImportError:
    @contextlib.contextmanager
    def _colorama_text(*args):
        yield

__all__ = ['run']
__version__ = '5.1.0'

_PARAM_TYPES = ['param', 'parameter', 'arg', 'argument', 'key', 'keyword']
_TYPE_NAMES = ['type', 'kwtype']

_Doc = namedtuple('_Doc', ('first_line', 'text', 'params', 'raises'))
_Param = namedtuple('_Param', ('text', 'type'))
_Type = namedtuple('_Type', ('type', 'container'))

_SUPPRESS_BOOL_DEFAULT = object()


def _ti_get_args(tp):  # Make Py<3.7 behave consistently with Py>=3.7.
    if type(tp) is type(Literal):  # Py <= 3.6.
        return tp.__values__
    return ti.get_args(tp, evaluate=True)  # evaluate = True default on Py >= 3.7.


def run(funcs: Union[Callable, List[Callable]], *,
        parsers: Optional[Dict[type, Callable[[str], Any]]] = None,
        short: Optional[Dict[str, str]] = None,
        strict_kwonly: bool = True,
        show_types: bool = False,
        argparse_kwargs: dict = {},
        argv: Optional[List[str]] = None):
    """
    Process command line arguments and run the given functions.

    ``funcs`` can be a single callable, which is parsed and run; or it can be
    a list of callables, in which case each one is given a subparser with its
    name, and only the chosen callable is run.

    :param funcs:
        Function or functions to process and run.
    :param parsers:
        Dictionary mapping types to parsers to use for parsing function
        arguments.
    :param short:
        Dictionary mapping parameter names (after conversion of underscores to
        dashes) to letters, to use as alternative short flags.  Defaults to
        ``None``, which means to generate short flags for any non-ambiguous
        option.  Set to ``{}`` to completely disable short flags.
    :param strict_kwonly:
        If `False`, all parameters with a default are converted into
        command-line flags.  The default behavior (`True`) is to convert
        keyword-only parameters to command line flags, and non-keyword-only
        parameters with a default to optional positional command line
        parameters.
    :param show_types:
        If `True`, display type names after parameter descriptions in the help
        text.
    :param argparse_kwargs:
        A mapping of keyword arguments that will be passed to the
        ArgumentParser constructor.  (If the ``formatter_class`` key is set, it
        will override the formatter implied by ``show_types``.)
    :param argv:
        Command line arguments to parse (default: ``sys.argv[1:]``).
    :return:
        The value returned by the function that was run.
    """
    parser = _create_parser(
        funcs, parsers=parsers, short=short, strict_kwonly=strict_kwonly,
        show_types=show_types, argparse_kwargs=argparse_kwargs)
    with _colorama_text():
        args = parser.parse_args(argv)
    # Workaround for http://bugs.python.org/issue9253#msg186387
    if not hasattr(args, '_func'):
        parser.error('too few arguments')
    try:
        return _call_function(parser, args._func, args)
    except args._exc_types as e:
        sys.exit(e)


def _create_parser(
        funcs, *,
        parsers=None,
        short=None,
        strict_kwonly=True,
        show_types=False,
        argparse_kwargs={}):
    formatter_class = _Formatter if show_types else _NoTypeFormatter
    parser = ArgumentParser(
        **{"formatter_class": formatter_class, **argparse_kwargs})
    if callable(funcs):
        _populate_parser(funcs, parser, parsers, short, strict_kwonly)
    else:
        subparsers = parser.add_subparsers()
        for func in funcs:
            if isinstance(funcs, dict):
                name, func = func, funcs[func]
            else:
                name = func.__name__.replace('_', '-')
            subparser = subparsers.add_parser(
                name,
                formatter_class=formatter_class,
                help=_parse_function_docstring(func).first_line)
            _populate_parser(func, subparser, parsers, short, strict_kwonly)
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
                and action.default is not _SUPPRESS_BOOL_DEFAULT
                and action.option_strings):
            info.append('default: %(default)s')
        if info:
            return action.help + '\n({})'.format(', '.join(info))
        else:
            return action.help


class _NoTypeFormatter(_Formatter):
    show_types = False


def _public_signature(func):
    full_sig = inspect.signature(func)
    return full_sig.replace(
        parameters=list(param for param in full_sig.parameters.values()
                        if not param.name.startswith('_')))


def _populate_parser(func, parser, parsers, short, strict_kwonly):
    sig = _public_signature(func)
    doc = _parse_function_docstring(func)
    parser.description = doc.text

    types = {name: _get_type(func, name)
             for name, param in sig.parameters.items()}
    exc_types = tuple(_get_type_from_doc(name, func.__globals__).type
                      for name in doc.raises)
    positionals = set(name for name, param in sig.parameters.items()
                      if ((param.default is param.empty or strict_kwonly)
                          and not types[name].container
                          and param.kind != param.KEYWORD_ONLY))
    if short is None:
        count_initials = Counter(name[0] for name in sig.parameters
                                 if name not in positionals)
        if parser.add_help:
            count_initials['h'] += 1
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
            if default == SUPPRESS:
                # Work around lack of "required non-exclusive group" in
                # argparse by checking for that case ourselves.
                default = _SUPPRESS_BOOL_DEFAULT
            _add_argument(parser, name, short,
                          action='store_true',
                          default=default,
                          # Add help if available.
                          **kwargs)
            _add_argument(parser, 'no-' + name, short,
                          action='store_false',
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
        member_types = None
        if ti.is_tuple_type(type_.type):
            member_types = _ti_get_args(type_.type)
            kwargs['nargs'] = len(member_types)
            kwargs['action'] = _make_store_tuple_action_class(
                tuple, member_types, parsers)
        elif (isinstance(type_.type, type) and issubclass(type_.type, tuple)
              and hasattr(type_.type, '_fields')
              and hasattr(type_.type, '_field_types')):
            # Before Py3.6, `_field_types` does not preserve order, so retrieve
            # the order from `_fields`.
            member_types = tuple(type_.type._field_types[field]
                                 for field in type_.type._fields)
            kwargs['nargs'] = len(member_types)
            kwargs['action'] = _make_store_tuple_action_class(
                lambda args, type_=type_: type_.type(*args),
                member_types, parsers)
            if not positional:  # http://bugs.python.org/issue14074
                kwargs['metavar'] = type_.type._fields
        else:
            kwargs['type'] = _get_parser(type_.type, parsers)
            if isinstance(type_.type, type) and issubclass(type_.type, Enum):
                kwargs['metavar'] = (
                    '{' + ','.join(type_.type.__members__) + '}')
            elif ti.get_origin(type_.type) is Literal:  # Py >= 3.7.
                kwargs['metavar'] = (
                    '{' + ','.join(map(str, _ti_get_args(type_.type))) + '}')
            elif type(type_.type) is type(Literal):  # Py <= 3.6.
                kwargs['metavar'] = (
                    '{' + ','.join(map(str, type_.type.__values__)) + '}')
        _add_argument(parser, name, short, **kwargs)

    parser.set_defaults(_func=func, _exc_types=exc_types)


def _add_argument(parser, name, short, _positional=False, **kwargs):
    if _positional:
        args = [name]
    else:
        prefix_char = parser.prefix_chars[0]
        name = name.replace('_', '-')
        args = [prefix_char * 2 + name]
        if name in short:
            args.insert(0, prefix_char + short[name])
    return parser.add_argument(*args, **kwargs)


def _get_type(func, name):
    """Retrieve a type from either documentation or annotations.

    If both are specified, they must agree exactly.
    """
    doc = _parse_function_docstring(func)
    doc_type = doc.params.get(name, _Param(None, None)).type
    if doc_type is not None:
        doc_type = _get_type_from_doc(doc_type, func.__globals__)

    hints = typing.get_type_hints(func)
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
    if ' or ' in name:
        subtypes = [_get_type_from_doc(part, globalns)
                    for part in name.split(' or ')]
        if any(subtype.container is not None for subtype in subtypes):
            raise ValueError(
                'unsupported union including container type: {}'.format(name))
        return _Type(Union[tuple(subtype.type for subtype in subtypes)], None)
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
    container_types = [
        typing.List, typing.Iterable, typing.Sequence,  # Py<3.7.
        list, collections.abc.Iterable, collections.abc.Sequence,  # Py>=3.7
    ]
    if ti.get_origin(hint) in container_types:
        [type_] = _ti_get_args(hint)
        return _Type(type_, list)
    elif ti.is_union_type(hint):
        # For Union[type, NoneType], just use type.
        args = _ti_get_args(hint)
        if len(args) == 2:
            type_, none = args
            if none == type(None):
                return _Type(type_, None)
        if any(ti.get_origin(subtype) in container_types for subtype in args):
            raise ValueError(
                'unsupported union including container type: {}'.format(hint))
    return _Type(hint, None)


def _call_function(parser, func, args):
    positionals = []
    keywords = {}
    sig = _public_signature(func)
    for name, param in sig.parameters.items():
        arg = getattr(args, name)
        if arg is _SUPPRESS_BOOL_DEFAULT:
            parser.error('one of the arguments --{0} --no-{0} is required'
                         .format(name))
        if param.kind in [param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD]:
            positionals.append(arg)
        elif param.kind == param.VAR_POSITIONAL:
            positionals.extend(arg)
        else:
            keywords[name] = arg
    return func(*positionals, **keywords)


def _parse_function_docstring(func):
    return _parse_docstring(inspect.getdoc(func))


@functools.lru_cache()
def _parse_docstring(doc):
    """Extract documentation from a function's docstring."""
    if doc is None:
        return _Doc('', '', {}, [])

    # Convert Google- or Numpy-style docstrings to RST.
    # (Should do nothing if not in either style.)
    doc = str(GoogleDocstring(doc))
    doc = str(NumpyDocstring(doc))

    tree = publish_doctree(doc)

    class Visitor(NodeVisitor):
        optional = [
            'document', 'docinfo',
            'field_list', 'field_body',
            'literal', 'problematic']

        def __init__(self, document):
            NodeVisitor.__init__(self, document)
            self.paragraphs = []
            self.start_lines = []
            self.params = defaultdict(dict)
            self.raises = []
            self._current_paragraph = None
            self._indent_iterator_stack = []
            self._indent_stack = []

        def _do_nothing(self, node):
            pass

        def visit_paragraph(self, node):
            self.start_lines.append(node.line)
            self._current_paragraph = []

        def depart_paragraph(self, node):
            text = ''.join(self._current_paragraph)
            text = ''.join(self._indent_stack) + text
            self._indent_stack = [
                ' ' * len(item) for item in self._indent_stack]
            text = text.replace('\n', '\n' + ''.join(self._indent_stack))
            self.paragraphs.append(text)
            self._current_paragraph = None

        visit_block_quote = visit_paragraph
        depart_block_quote = depart_paragraph

        def visit_Text(self, node):
            self._current_paragraph.append(node)

        depart_Text = _do_nothing

        def visit_emphasis(self, node):
            self._current_paragraph.append('\033[3m')  # *foo*: italic

        def visit_strong(self, node):
            self._current_paragraph.append('\033[1m')  # **foo**: bold

        def visit_title_reference(self, node):
            self._current_paragraph.append('\033[4m')  # `foo`: underlined

        def _depart_markup(self, node):
            self._current_paragraph.append('\033[0m')

        depart_emphasis = depart_strong = depart_title_reference = \
            _depart_markup

        def visit_literal_block(self, node):
            text, = node
            self.start_lines.append(node.line)
            self.paragraphs.append(re.sub('^|\n', r'\g<0>    ', text))  # indent
            raise SkipNode

        def visit_bullet_list(self, node):
            self._indent_iterator_stack.append(
                (node['bullet'] + ' ' for _ in range(len(node))))

        def depart_bullet_list(self, node):
            self._indent_iterator_stack.pop()

        def visit_enumerated_list(self, node):
            enumtype = node['enumtype']
            fmt = {('(', ')'): 'parens',
                   ('', ')'): 'rparen',
                   ('', '.'): 'period'}[node['prefix'], node['suffix']]
            try:
                start = node['start']
            except KeyError:
                start = 1
            else:
                start = {
                    'arabic': int,
                    'loweralpha': lambda s: ord(s) - ord('a') + 1,
                    'upperalpha': lambda s: ord(s) - ord('A') + 1,
                    'lowerroman': lambda s: roman.fromRoman(s.upper()),
                    'upperroman': lambda s: roman.fromRoman(s),
                }[enumtype](start)
            enumerators = [Body(None).make_enumerator(i, enumtype, fmt)[0]
                           for i in range(start, start + len(node))]
            width = max(map(len, enumerators))
            enumerators = [enum.ljust(width) for enum in enumerators]
            self._indent_iterator_stack.append(iter(enumerators))

        def depart_enumerated_list(self, node):
            self._indent_iterator_stack.pop()

        def visit_list_item(self, node):
            self._indent_stack.append(next(self._indent_iterator_stack[-1]))

        def depart_list_item(self, node):
            self._indent_stack.pop()

        def visit_field(self, node):
            field_name_node, field_body_node = node
            field_name, = field_name_node
            parts = field_name.split()
            if len(parts) == 2:
                doctype, name = parts
            elif len(parts) == 3:
                doctype, type_, name = parts
                if doctype not in _PARAM_TYPES:
                    raise SkipNode
                if 'type' in self.params[name]:
                    raise ValueError('type defined twice for {}'.format(name))
                self.params[name]['type'] = type_
            else:
                raise SkipNode
            if doctype in _PARAM_TYPES:
                doctype = 'param'
            if doctype in _TYPE_NAMES:
                doctype = 'type'
            if doctype in ['param', 'type'] and doctype in self.params[name]:
                raise ValueError(
                    '{} defined twice for {}'.format(doctype, name))
            visitor = Visitor(self.document)
            field_body_node.walkabout(visitor)
            if doctype in ['param', 'type']:
                self.params[name][doctype] = ''.join(visitor.paragraphs)
            elif doctype in ['raises']:
                self.raises.append(name)
            raise SkipNode

        def visit_comment(self, node):
            raise SkipNode

        def visit_system_message(self, node):
            raise SkipNode

    visitor = Visitor(tree)
    tree.walkabout(visitor)

    tuples = {name: _Param(values.get('param'), values.get('type'))
              for name, values in visitor.params.items()}
    if visitor.paragraphs:
        text = []
        for start, paragraph, next_start in zip(
                visitor.start_lines,
                visitor.paragraphs,
                visitor.start_lines[1:] + [0]):
            text.append(paragraph)
            # We insert a space before each newline to prevent argparse
            # from stripping consecutive newlines down to just two
            # (http://bugs.python.org/issue31330).
            text.append(' \n' * (next_start - start - paragraph.count('\n')))
        parsed = _Doc(text[0], ''.join(text), tuples, visitor.raises)
    else:
        parsed = _Doc('', '', tuples, visitor.raises)
    return parsed


def _get_parser(type_, parsers=None):
    parser = _find_parser(type_, parsers or {})

    # Make a parser with the name the user expects to see in error messages.
    def named_parser(string):
        return parser(string)

    # Union types don't have a __name__, but their str is fine.
    named_parser.__name__ = getattr(type_, '__name__', str(type_))
    return named_parser


def _find_parser(type_, parsers):
    try:
        return parsers[type_]
    except KeyError:
        pass
    if (type_ in [str, int, float]
            or isinstance(type_, type) and issubclass(type_, PurePath)):
        return type_
    elif type_ == bool:
        return _parse_bool
    elif type_ == slice:
        return _parse_slice
    elif type_ == list:
        raise ValueError('unable to parse list (try list[type])')
    elif isinstance(type_, type) and issubclass(type_, Enum):
        return _make_enum_parser(type_)
    elif _is_constructible_from_str(type_):
        return type_
    elif ti.is_union_type(type_):
        return _make_union_parser(
            type_,
            [_find_parser(subtype, parsers)
             for subtype in _ti_get_args(type_)])
    elif (ti.get_origin(type_) is Literal  # Py >= 3.7.
          or type(type_) is type(Literal)):  # Py <= 3.6.
        return _make_literal_parser(
            type_,
            [_find_parser(type(arg), parsers)
             for arg in _ti_get_args(type_)])
    else:
        raise Exception('no parser found for type {}'.format(
            # typing types have no __name__.
            getattr(type_, '__name__', repr(type_))))


def _parse_bool(string):
    if string.lower() in ['t', 'true', '1']:
        return True
    elif string.lower() in ['f', 'false', '0']:
        return False
    else:
        raise ValueError('{} is not a valid boolean string'.format(string))


def _parse_slice(string):
    exc = ValueError('{} is not a valid slice string'.format(string))
    try:
        mod = ast.parse("_[{}]".format(string))
    except SyntaxError:
        raise exc
    if not len(mod.body) == 1:
        raise exc
    sl = mod.body[0].value.slice
    if not isinstance(sl, ast.Slice):
        raise exc
    start = ast.literal_eval(sl.lower) if sl.lower else None
    stop = ast.literal_eval(sl.upper) if sl.upper else None
    step = ast.literal_eval(sl.step) if sl.step else None
    return slice(start, stop, step)


def _make_enum_parser(enum):
    def parser(value):
        try:
            return enum[value]
        except KeyError:
            raise ArgumentTypeError(
                'invalid choice: {!r} (choose from {})'.format(
                    value, ', '.join(map(repr, enum.__members__))))
    return parser


def _is_constructible_from_str(type_):
    try:
        signature = inspect.signature(type_)
        (argname, _), = signature.bind(object()).arguments.items()
    except TypeError:
        # Can be raised by inspect.signature, Signature.bind, or _get_type.
        return False
    try:
        argtype = _get_type(type_, argname)
    except (TypeError, ValueError):
        pass
    else:
        if argtype and argtype.type is str:
            return True
    if isinstance(type_, type):
        try:
            argtype = _get_type(type_.__init__, argname)
        except (TypeError, ValueError):
            pass
        else:
            if argtype and argtype.type is str:
                return True
    return False


def _make_union_parser(union, parsers):
    def parser(value):
        for p in parsers:
            try:
                return p(value)
            except (ValueError, ArgumentTypeError):
                pass
        raise ValueError(
            '{} could not be parsed as any of {}'.format(value, union))
    return parser


def _make_literal_parser(literal, parsers):
    def parser(value):
        for arg, p in zip(_ti_get_args(literal), parsers):
            try:
                parsed = p(value)
            except ValueError:
                pass
            if parsed == arg:
                return arg
        raise ArgumentTypeError(
            'invalid choice: {!r} (choose from {})'.format(
                value, ', '.join(map(repr, map(str, _ti_get_args(literal))))))
    return parser


def _make_store_tuple_action_class(make_tuple, member_types, parsers):
    class _StoreTupleAction(_StoreAction):
        def __call__(self, parser, namespace, values, option_string=None):
            try:
                value = make_tuple(_get_parser(arg, parsers)(value)
                                   for arg, value in zip(member_types, values))
            except ArgumentTypeError as exc:
                raise ArgumentError(self, str(exc))
            return super(_StoreTupleAction, self).__call__(
                parser, namespace, value, option_string)
    return _StoreTupleAction
