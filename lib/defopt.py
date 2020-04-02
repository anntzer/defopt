"""
Effortless argument parser.

Run Python functions from the command line with ``run(func)``.
"""

import ast
import collections.abc
import contextlib
import functools
import importlib
import inspect
import re
import pydoc
import sys
import typing
from argparse import (
    REMAINDER, SUPPRESS,
    Action, ArgumentParser, RawTextHelpFormatter,
    ArgumentError, ArgumentTypeError)
from collections import defaultdict, namedtuple, Counter
from enum import Enum
from pathlib import PurePath
from typing import Any, Callable, Dict, List, Optional, Union

import docutils.core
from docutils.nodes import NodeVisitor, SkipNode, TextElement
from docutils.parsers.rst.states import Body

try:
    collections.Callable = collections.abc.Callable
    from sphinxcontrib.napoleon.docstring import (
        GoogleDocstring, NumpyDocstring)
finally:
    if sys.version_info >= (3, 7):
        del collections.Callable

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

try:
    from _defopt_version import version as __version__
except ImportError:
    pass

__all__ = ['run', 'signature']

_PARAM_TYPES = ['param', 'parameter', 'arg', 'argument', 'key', 'keyword']
_TYPE_NAMES = ['type', 'kwtype']

_Doc = namedtuple('_Doc', ('first_line', 'text', 'params', 'raises'))
_Param = namedtuple('_Param', ('text', 'type'))

_SUPPRESS_BOOL_DEFAULT = object()


if hasattr(typing, 'get_args'):
    _ti_get_args = typing.get_args
else:
    def _ti_get_args(tp):
        import typing_inspect as ti
        if type(tp) is type(Literal):  # Py<=3.6.
            return tp.__values__
        return ti.get_args(tp, evaluate=True)  # evaluate=True default on Py>=3.7.


if hasattr(typing, 'get_origin'):
    _ti_get_origin = typing.get_origin
else:
    def _ti_get_origin(tp):
        import typing_inspect as ti
        if type(tp) is type(Literal):  # Py<=3.6.
            return Literal
        origin = ti.get_origin(tp)
        return {  # Py<=3.6.
            typing.List: list,
            typing.Iterable: collections.abc.Iterable,
            typing.Sequence: collections.abc.Sequence,
            typing.Tuple: tuple,
        }.get(origin, origin)


class _DefaultList(list):
    """
    Marker type used to determine that a parameter corresponds to a varargs,
    and thus should have its default value hidden.  Varargs are unpacked during
    function call, so the caller won't see this type.
    """


def run(funcs: Union[Callable, List[Callable], Dict[str, Callable]], *,
        parsers: Dict[type, Callable[[str], Any]] = {},
        short: Optional[Dict[str, str]] = None,
        strict_kwonly: bool = True,
        show_defaults: bool = True,
        show_types: bool = False,
        version: Union[str, None, bool] = None,
        argparse_kwargs: dict = {},
        argv: Optional[List[str]] = None):
    """
    Process command line arguments and run the given functions.

    ``funcs`` can be a single callable, which is parsed and run; or it can
    be a list of callables or mappable of strs to callables, in which case
    each one is given a subparser with its name (if ``funcs`` is a list) or
    the corresponding key (if ``funcs`` is a mappable), and only the chosen
    callable is run.

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
    :param show_defaults:
        Whether parameter defaults are appneded to parameter descriptions.
    :param show_types:
        Whether parameter types are appended to parameter descriptions.
    :param version:
        If a string, add a ``--version`` flag which prints the given version
        string and exits.
        If ``True``, the version string is auto-detected by searching for a
        ``__version__`` attribute on the module where the function is defined,
        and its parent packages, if any.  Error out if such a version cannot be
        found, or if multiple callables with different version strings are
        passed.
        If ``None`` (the default), behave as for ``True``, but don't add a
        ``--version`` flag if no version string can be autodetected.
        If ``False``, do not add a ``--version`` flag.
    :param argparse_kwargs:
        A mapping of keyword arguments that will be passed to the
        ArgumentParser constructor.
    :param argv:
        Command line arguments to parse (default: ``sys.argv[1:]``).
    :return:
        The value returned by the function that was run.
    """
    parser = _create_parser(
        funcs, parsers=parsers, short=short, strict_kwonly=strict_kwonly,
        show_defaults=show_defaults, show_types=show_types, version=version,
        argparse_kwargs=argparse_kwargs)
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
        parsers={},
        short=None,
        strict_kwonly=True,
        show_defaults=True,
        show_types=False,
        version=None,
        argparse_kwargs={}):
    parser = ArgumentParser(
        **{**{'formatter_class': RawTextHelpFormatter}, **argparse_kwargs})
    version_sources = []
    if callable(funcs):
        _populate_parser(funcs, parser, parsers, short,
                         strict_kwonly, show_defaults, show_types)
        version_sources.append(funcs)
    else:
        subparsers = parser.add_subparsers()
        for func in funcs:
            if isinstance(funcs, collections.abc.MutableMapping):
                name, func = func, funcs[func]
            else:
                name = func.__name__.replace('_', '-')
            subparser = subparsers.add_parser(
                name,
                formatter_class=RawTextHelpFormatter,
                help=_parse_docstring(inspect.getdoc(func)).first_line)
            _populate_parser(func, subparser, parsers, short,
                             strict_kwonly, show_defaults, show_types)
            version_sources.append(func)
    if isinstance(version, str):
        version_string = version
    elif version is None or version:
        version_string = _get_version(version_sources)
        if version and version_string is None:
            raise ValueError('Failed to autodetect version string')
    else:
        version_string = None
    if version_string is not None:
        parser.add_argument(
            '{0}{0}version'.format(parser.prefix_chars[0]),
            action='version', version=version_string)
    return parser


def _get_version(funcs):
    versions = {v for v in map(_get_version1, funcs) if v is not None}
    return versions.pop() if len(versions) == 1 else None


def _get_version1(func):
    try:
        module_name = func.__module__
    except AttributeError:
        return
    if module_name == '__main__':
        f_globals = getattr(func, '__globals__', {})
        if f_globals.get('__spec__'):
            module_name = f_globals['__spec__'].name
        else:
            return f_globals.get('__version__')
    while True:
        try:
            return importlib.import_module(module_name).__version__
        except AttributeError:
            if '.' not in module_name:
                return
            module_name, _ = module_name.rsplit('.', 1)


class Parameter(inspect.Parameter):
    __slots__ = (*inspect.Parameter.__slots__, '_doc')
    doc = property(lambda self: self._doc)

    def __init__(self, *args, doc=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._doc = doc

    def replace(self, *, doc=inspect._void, **kwargs):
        copy = super().replace(**kwargs)
        copy._doc = self._doc if doc is inspect._void else doc
        return copy


def signature(func: Callable):
    """
    Return an enhanced signature for ``func``.

    This function behaves similarly to `inspect.signature`, with the following
    differences:

    - Private parameters (starting with an underscore) are not listed.
    - Parameter annotations are also read from ``func``'s docstring (if a
      parameter's type is specified both in the signature and the docstring,
      both types must match).
    - The docstring for each parameter is available as the
      `~inspect.Parameter`'s ``.doc`` attribute (in fact, a subclass of
      `~inspect.Parameter` is used).
    """
    full_sig = inspect.signature(func)
    doc = _parse_docstring(inspect.getdoc(func))
    parameters = []
    for param in full_sig.parameters.values():
        if param.name.startswith('_'):
            if param.default is param.empty:
                raise ValueError(
                    'Parameter {} of {}{} is private but has no default'
                    .format(param.name, func.__name__, full_sig))
        else:
            parameters.append(Parameter(
                name=param.name, kind=param.kind, default=param.default,
                annotation=_get_type(func, param.name),
                doc=doc.params.get(param.name, _Param(None, None)).text))
    return full_sig.replace(parameters=parameters)


def _populate_parser(func, parser, parsers, short,
                     strict_kwonly, show_defaults, show_types):
    sig = signature(func)
    doc = _parse_docstring(inspect.getdoc(func))
    parser.description = doc.text

    exc_types = tuple(_get_type_from_doc(name, func.__globals__)
                      for name in doc.raises)
    positionals = {name for name, param in sig.parameters.items()
                   if ((param.default is param.empty or strict_kwonly)
                       and not _is_list_like(param.annotation)
                       and param.kind != param.KEYWORD_ONLY)}
    if short is None:
        count_initials = Counter(name[0] for name in sig.parameters
                                 if name not in positionals)
        if parser.add_help:
            count_initials['h'] += 1
        short = {name.replace('_', '-'): name[0] for name in sig.parameters
                 if name not in positionals and count_initials[name[0]] == 1}

    actions = []
    for name, param in sig.parameters.items():
        kwargs = {}
        if param.doc is not None:
            kwargs['help'] = param.doc.replace('%', '%%')
        type_ = param.annotation
        if param.kind == param.VAR_KEYWORD:
            raise ValueError('**kwargs not supported')
        hasdefault = param.default is not param.empty
        default = param.default if hasdefault else SUPPRESS
        required = not hasdefault and param.kind != param.VAR_POSITIONAL
        positional = name in positionals
        if type_ == bool and not positional:
            # Special case: just add parameterless --name and --no-name flags.
            if default == SUPPRESS:
                # Work around lack of "required non-exclusive group" in
                # argparse by checking for that case ourselves.
                default = _SUPPRESS_BOOL_DEFAULT
            actions.extend([
                _add_argument(parser, name, short,
                              action='store_true',
                              default=default,
                              # Add help if available.
                              **kwargs),
                _add_argument(parser, 'no-' + name, short,
                              action='store_false',
                              default=default,
                              dest=name)])
            continue
        # Always set a default, even for required parameters, so that we can
        # later (ab)use default == SUPPRESS (!= None) to detect required
        # parameters.
        kwargs['default'] = default
        if positional:
            kwargs['_positional'] = True
            if param.default is not param.empty:
                kwargs['nargs'] = '?'
            if param.kind == param.VAR_POSITIONAL:
                kwargs['nargs'] = '*'
                kwargs['default'] = _DefaultList()
        else:
            kwargs['required'] = required
        if _is_list_like(type_):
            type_, = _ti_get_args(type_)
            kwargs['nargs'] = '*'
            if param.kind == param.VAR_POSITIONAL:
                kwargs['action'] = 'append'
                kwargs['default'] = _DefaultList()
        member_types = None
        if _ti_get_origin(type_) is tuple:
            member_types = _ti_get_args(type_)
            kwargs['nargs'] = len(member_types)
            kwargs['action'] = _make_store_tuple_action_class(
                tuple, member_types, parsers)
        elif (isinstance(type_, type) and issubclass(type_, tuple)
              and hasattr(type_, '_fields')
              and hasattr(type_, '_field_types')):
            # Before Py3.6, `_field_types` does not preserve order, so retrieve
            # the order from `_fields`.
            member_types = tuple(type_._field_types[field]
                                 for field in type_._fields)
            kwargs['nargs'] = len(member_types)
            kwargs['action'] = _make_store_tuple_action_class(
                lambda args, type_=type_: type_(*args),
                member_types, parsers)
            if not positional:  # http://bugs.python.org/issue14074
                kwargs['metavar'] = type_._fields
        else:
            kwargs['type'] = _get_parser(type_, parsers)
            if isinstance(type_, type) and issubclass(type_, Enum):
                kwargs['metavar'] = '{' + ','.join(type_.__members__) + '}'
            elif _ti_get_origin(type_) is Literal:
                kwargs['metavar'] = (
                    '{' + ','.join(map(str, _ti_get_args(type_))) + '}')
        actions.append(_add_argument(parser, name, short, **kwargs))
    for action in actions:
        _update_help_string(
            action, show_defaults=show_defaults, show_types=show_types)

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


def _update_help_string(action, *, show_defaults, show_types):
    action_help = action.help or ''
    info = []
    if (show_types
            and action.type is not None
            and action.type.func not in [_make_enum_parser,
                                         _make_literal_parser]
            and '%(type)' not in action_help):
        info.append('type: %(type)s')
    if (show_defaults
            and action.const is not False  # i.e. action='store_false'.
            and not isinstance(action.default, _DefaultList)
            and '%(default)' not in action_help
            and action.default is not SUPPRESS
            and action.default is not _SUPPRESS_BOOL_DEFAULT):
        info.append(
            'default: {}'.format(action.default.name.replace('%', '%%'))
            if action.type is not None
               and action.type.func is _make_enum_parser
               and isinstance(action.default, action.type.args)
            else 'default: %(default)s')
    parts = [action.help, '({})'.format(', '.join(info)) if info else '']
    action.help = '\n'.join(filter(None, parts)) or ''


def _is_list_like(type_):
    return (_ti_get_origin(type_)
            in [list, collections.abc.Iterable, collections.abc.Sequence])


def _get_type(func, name):
    """
    Retrieve a type from either documentation or annotations.

    If both are specified, they must agree exactly.
    """
    doc = _parse_docstring(inspect.getdoc(func))
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
        if any(map(_is_list_like, subtypes)):
            raise ValueError(
                'unsupported union including container type: {}'.format(name))
        return Union[tuple(subtype for subtype in subtypes)]
    # Support for legacy list syntax "list[type]".
    # (This intentionally won't catch `List` or `typing.List`)
    match = re.match(r'([a-z]\w+)\[([\w\.]+)\]', name)
    if match:
        container, type_ = match.groups()
        if container != 'list':
            raise ValueError(
                'unsupported container type: {}'.format(container))
        return List[eval(type_, globalns)]
    return _get_type_from_hint(eval(name, globalns))


def _get_type_from_hint(hint):
    if _is_list_like(hint):
        [type_] = _ti_get_args(hint)
        return List[type_]
    elif _ti_get_origin(hint) is Union:
        # Flatten Union[type, NoneType] (== Optional[type]) to type.
        # get_type_hints also appends NoneType to unions for parameters
        # defaulting to None.
        args = [arg for arg in _ti_get_args(hint) if arg is not type(None)]
        if any(_is_list_like(subtype) for subtype in args):
            raise ValueError(
                'unsupported union including container type: {}'.format(hint))
        return args[0] if len(args) == 1 else Union[tuple(args)]
    return hint


def _call_function(parser, func, args):
    positionals = []
    keywords = {}
    sig = signature(func)
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


def _passthrough_role(
        name, rawtext, text, lineno, inliner, options={}, content=[]):
    return [TextElement(rawtext, text)], []


@contextlib.contextmanager
def _sphinx_common_roles():
    # See "Cross-referencing Python objects" section of
    # http://www.sphinx-doc.org/en/master/usage/restructuredtext/domains.html
    roles = [
        'mod', 'func', 'data', 'const', 'class', 'meth', 'attr', 'exc', 'obj']
    # No public unregistration API :(  Also done by sphinx.
    role_map = docutils.parsers.rst.roles._roles
    for role in roles:
        role_map[role] = role_map['py:' + role] = _passthrough_role
    try:
        yield
    finally:
        for role in roles:
            role_map.pop(role)
            role_map.pop('py:' + role)


@functools.lru_cache()
def _parse_docstring(doc):
    """Extract documentation from a function's docstring."""
    if doc is None:
        return _Doc('', '', {}, [])

    # Convert Google- or Numpy-style docstrings to RST.
    # (Should do nothing if not in either style.)
    doc = str(GoogleDocstring(doc))
    doc = str(NumpyDocstring(doc))

    with _sphinx_common_roles():
        tree = docutils.core.publish_doctree(doc)

    class Visitor(NodeVisitor):
        optional = [
            'document', 'docinfo',
            'field_list', 'field_body',
            'literal', 'problematic',
            # Introduced by our custom passthrough handlers, but the Visitor
            # will recurse into the inner text node by itself.
            'TextElement',
        ]

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

        visit_block_quote = visit_doctest_block = visit_paragraph
        depart_block_quote = depart_doctest_block = depart_paragraph

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

        def visit_rubric(self, node):
            self.visit_paragraph(node)

        def depart_rubric(self, node):
            # Style consistent with "usage:", "positional arguments:", etc.
            self._current_paragraph[:] = [
                (t.lower() if t == t.title() else t) + ":"
                for t in self._current_paragraph]
            self.depart_paragraph(node)

        def visit_literal_block(self, node):
            text, = node
            self.start_lines.append(node.line)
            self.paragraphs.append(
                re.sub('^|\n', r'\g<0>    ', text))  # indent
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
            start = node.get('start', 1)
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
                # docutils>=0.16 represents \* as \0* in the doctree.
                name = name.lstrip('*\0')
            elif len(parts) == 3:
                doctype, type_, name = parts
                name = name.lstrip('*\0')
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
            self.paragraphs.append(comment_token)
            # Comments report their line as the *end* line of the comment.
            self.start_lines.append(
                node.line - node.children[0].count('\n') - 1)
            raise SkipNode

        def visit_system_message(self, node):
            raise SkipNode

    comment_token = object()
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
            if paragraph is comment_token:
                continue
            text.append(paragraph)
            # We insert a space before each newline to prevent argparse
            # from stripping consecutive newlines down to just two
            # (http://bugs.python.org/issue31330).
            # FIXME: but napoleon inserts far too many newlines :/
            text.append(' \n' * (next_start - start - paragraph.count('\n')))
        parsed = _Doc(text[0], ''.join(text), tuples, visitor.raises)
    else:
        parsed = _Doc('', '', tuples, visitor.raises)
    return parsed


def _get_parser(type_, parsers):
    try:
        parser = functools.partial(parsers[type_])
    except KeyError:
        if (type_ in [str, int, float]
                or isinstance(type_, type) and issubclass(type_, PurePath)):
            parser = functools.partial(type_)
        elif type_ == bool:
            parser = functools.partial(_parse_bool)
        elif type_ == slice:
            parser = functools.partial(_parse_slice)
        elif type_ == list:
            raise ValueError('unable to parse list (try list[type])')
        elif isinstance(type_, type) and issubclass(type_, Enum):
            parser = _make_enum_parser(type_)
        elif _is_constructible_from_str(type_):
            parser = functools.partial(type_)
        elif _ti_get_origin(type_) is Union:
            parser = _make_union_parser(
                type_,
                [_get_parser(arg, parsers) for arg in _ti_get_args(type_)])
        elif _ti_get_origin(type_) is Literal:  # Py>=3.7.
            parser = _make_literal_parser(
                type_,
                [_get_parser(type(arg), parsers)
                 for arg in _ti_get_args(type_)])
        else:
            raise Exception('no parser found for type {}'.format(
                # typing types have no __name__.
                getattr(type_, '__name__', repr(type_))))
    # Set the name that the user expects to see in error messages (we always
    # return a temporary partial object so it's safe to set its __name__).
    # Unions and Literals don't have a __name__, but their str is fine.
    parser.__name__ = getattr(type_, '__name__', str(type_))
    return parser


def _parse_bool(string):
    if string.lower() in ['t', 'true', '1']:
        return True
    elif string.lower() in ['f', 'false', '0']:
        return False
    else:
        raise ValueError('{} is not a valid boolean string'.format(string))


def _parse_slice(string):
    slices = []

    class SliceVisitor(ast.NodeVisitor):
        def visit_Slice(self, node):
            start = ast.literal_eval(node.lower) if node.lower else None
            stop = ast.literal_eval(node.upper) if node.upper else None
            step = ast.literal_eval(node.step) if node.step else None
            slices.append(slice(start, stop, step))

    try:
        SliceVisitor().visit(ast.parse('_[{}]'.format(string)))
        sl, = slices
    except (SyntaxError, ValueError):
        raise ValueError('{} is not a valid slice string'.format(string))
    return sl


def _make_enum_parser(enum, value=None):
    if value is None:
        return functools.partial(_make_enum_parser, enum)
    try:
        return enum[value]
    except KeyError:
        raise ArgumentTypeError(
            'invalid choice: {!r} (choose from {})'.format(
                value, ', '.join(map(repr, enum.__members__))))


def _is_constructible_from_str(type_):
    try:
        sig = signature(type_)
        (argname, _), = sig.bind(object()).arguments.items()
    except TypeError:  # Can be raised by signature() or Signature.bind().
        return False
    except ValueError:
        # Can be raised for classes, if the relevant info is in `__init__`.
        if not isinstance(type_, type):
            raise
    else:
        if sig.parameters[argname].annotation is str:
            return True
    if isinstance(type_, type):
        # signature() first checks __new__, if it is present.
        return _is_constructible_from_str(
            type_.__init__.__get__(object(), type_))
    return False


def _make_union_parser(union, parsers, value=None):
    if value is None:
        return functools.partial(_make_union_parser, union, parsers)
    for p in parsers:
        try:
            return p(value)
        except (ValueError, ArgumentTypeError):
            pass
    raise ValueError(
        '{} could not be parsed as any of {}'.format(value, union))


def _make_literal_parser(literal, parsers, value=None):
    if value is None:
        return functools.partial(_make_literal_parser, literal, parsers)
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


def _make_store_tuple_action_class(make_tuple, member_types, parsers):
    class _StoreTupleAction(Action):
        def __call__(self, parser, namespace, values, option_string=None):
            try:
                value = make_tuple(_get_parser(arg, parsers)(value)
                                   for arg, value in zip(member_types, values))
            except ArgumentTypeError as exc:
                raise ArgumentError(self, str(exc))
            setattr(namespace, self.dest, value)
    return _StoreTupleAction


if __name__ == '__main__':
    def main(argv=None):
        parser = ArgumentParser()
        parser.add_argument('function')
        parser.add_argument('args', nargs=REMAINDER)
        args = parser.parse_args(argv)
        try:
            func = pydoc.locate(args.function)
        except pydoc.ErrorDuringImport as exc:
            raise exc.value from None
        if func is None:
            raise ImportError('Failed to locate {!r}'.format(args.function))
        argparse_kwargs = (
            {'prog': ' '.join(sys.argv[:2])} if argv is None else {})
        retval = run(func, argv=args.args, argparse_kwargs=argparse_kwargs)
        sys.displayhook(retval)

    main()
