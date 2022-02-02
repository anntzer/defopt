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
import itertools
import re
import pydoc
import sys
import types
import typing
import warnings
from argparse import (
    REMAINDER, SUPPRESS,
    Action, ArgumentParser, RawTextHelpFormatter,
    ArgumentError, ArgumentTypeError)
from collections import defaultdict, namedtuple, Counter
from enum import Enum
from pathlib import PurePath
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import importlib.metadata as _im
except ImportError:
    import importlib_metadata as _im
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

import docutils.core
from docutils.nodes import NodeVisitor, SkipNode, TextElement
from docutils.parsers.rst.states import Body

try:
    collections.Callable = collections.abc.Callable
    from sphinxcontrib.napoleon import Config, GoogleDocstring, NumpyDocstring
finally:
    if sys.version_info >= (3, 7):
        del collections.Callable

try:
    # colorama is a dependency on Windows to support ANSI escapes (from rst
    # markup).  It is optional on Unices, but can still be useful there as it
    # strips out ANSI escapes when the output is piped.
    from colorama import colorama_text as _colorama_text
except ImportError:
    _colorama_text = getattr(contextlib, 'nullcontext', contextlib.ExitStack)

try:
    __version__ = _im.version('defopt')
except ImportError:
    __version__ = '0+unknown'

__all__ = ['run', 'signature', 'bind']

_PARAM_TYPES = ['param', 'parameter', 'arg', 'argument', 'key', 'keyword']
_TYPE_NAMES = ['type', 'kwtype']

_Doc = namedtuple('_Doc', ('first_line', 'text', 'params', 'raises'))
_Param = namedtuple('_Param', ('text', 'type'))
class _Raises(tuple): pass


if hasattr(typing, 'get_args'):
    _ti_get_args = typing.get_args
else:
    import typing_inspect as _ti
    # evaluate=True is default on Py>=3.7.
    _ti_get_args = functools.partial(_ti.get_args, evaluate=True)


if hasattr(typing, 'get_origin'):
    _ti_get_origin = typing.get_origin
else:
    def _ti_get_origin(tp):
        import typing_inspect as ti
        if ti.is_literal_type(tp):  # ti.get_origin returns None for Literals.
            return Literal
        origin = ti.get_origin(tp)
        return {  # Py<3.7.
            typing.List: list,
            typing.Iterable: collections.abc.Iterable,
            getattr(typing, 'Collection', object()):
                getattr(collections.abc, 'Collection', object()),
            typing.Sequence: collections.abc.Sequence,
            typing.Tuple: tuple,
        }.get(origin, origin)


# Modified from Py3.9's version, plus:
# - a fix to bpo#38956 (by omitting the extraneous help string),
# - support for short aliases for --no-foo, by moving negative flag generation
#   to _add_argument (where the negative aliases are available),
# - a hack (_CustomString) to simulate format_usage on Py<3.9 (_CustomString
#   relies on an Py<3.9 implementation detail: the usage string is built using
#   '%s' % option_strings[0] (so there is an additional call to str()) whereas
#   the option invocation help directly joins the strings).


class _CustomString(str):
    def __str__(self):
        return self.action.format_usage()


class _BooleanOptionalAction(Action):
    def __init__(self, option_strings, **kwargs):
        self.negative_option_strings = []  # set by _add_argument
        if option_strings:
            cs = option_strings[0] = _CustomString(option_strings[0])
            cs.action = self
        super().__init__(option_strings, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if option_string in self.option_strings:
            setattr(namespace, self.dest,
                    option_string not in self.negative_option_strings)

    def format_usage(self):
        return ' | '.join(self.option_strings)


class _DefaultList(list):
    """
    Marker type used to determine that a parameter corresponds to a varargs,
    and thus should have its default value hidden.  Varargs are unpacked during
    function call, so the caller won't see this type.
    """


_unset = 'UNSET'


def bind(funcs: Union[Callable, List[Callable], Dict[str, Callable]], *,
         parsers: Dict[type, Callable[[str], Any]] = {},
         short: Optional[Dict[str, str]] = None,
         cli_options: Literal['kwonly', 'all', 'has_default'] = _unset,
         strict_kwonly=_unset,
         show_defaults: bool = True,
         show_types: bool = False,
         no_negated_flags: bool = False,
         version: Union[str, None, bool] = None,
         argparse_kwargs: dict = {},
         argv: Optional[List[str]] = None):
    """
    Process command-line arguments and bind arguments.

    This function takes the same parameters as `defopt.run`, but returns a
    pair, which consists of a `~typing.Callable` *func* and a
    `~inspect.BoundArguments` *ba*, such that `defopt.run` would call
    ``func(*ba.args, **ba.kwargs)`` (modulo exception handling).
    """
    if strict_kwonly == _unset:
        if cli_options == _unset:
            cli_options = 'kwonly'
    else:
        if cli_options != _unset:
            raise ValueError(
                "Cannot pass both 'cli_options' and 'strict_kwonly'")
        warnings.warn(
            'strict_kwonly is deprecated and will be removed in an upcoming '
            'release', DeprecationWarning)
        cli_options = 'kwonly' if strict_kwonly else 'has_default'
    parser = _create_parser(
        funcs, parsers=parsers, short=short, cli_options=cli_options,
        show_defaults=show_defaults, show_types=show_types,
        no_negated_flags=no_negated_flags, version=version,
        argparse_kwargs=argparse_kwargs)
    with _colorama_text():
        parsed_argv = vars(parser.parse_args(argv))
    try:
        func = parsed_argv.pop('_func')
    except KeyError:
        # Workaround for http://bugs.python.org/issue9253#msg186387 (and
        # https://bugs.python.org/issue29298 which blocks using required=True).
        parser.error('too few arguments')
    sig = signature(func)
    ba = sig.bind_partial()
    ba.arguments.update(parsed_argv)
    return func, ba


def run(funcs: Union[Callable, List[Callable], Dict[str, Callable]], *,
        parsers: Dict[type, Callable[[str], Any]] = {},
        short: Optional[Dict[str, str]] = None,
        cli_options: Literal['kwonly', 'all', 'has_default'] = _unset,
        strict_kwonly=_unset,
        show_defaults: bool = True,
        show_types: bool = False,
        no_negated_flags: bool = False,
        version: Union[str, None, bool] = None,
        argparse_kwargs: dict = {},
        argv: Optional[List[str]] = None):
    """
    Process command-line arguments and run the given functions.

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
        `None`, which means to generate short flags for any non-ambiguous
        option.  Set to ``{}`` to completely disable short flags.
    :param cli_options:
        The default behavior ('kwonly') is to convert keyword-only parameters
        to command line flags, and non-keyword-only parameters with a default
        to optional positional command line parameters. 'all' turns all
        parameters into command-line flags. 'has_default' turns a parameter
        into a command-line flag if and only if it has a default value.
    :param strict_kwonly:
        Deprecated.  If `False`, all parameters with a default are converted
        into command-line flags. The default behavior (`True`) is to convert
        keyword-only parameters to command line flags, and non-keyword-only
        parameters with a default to optional positional command line
        parameters.
    :param show_defaults:
        Whether parameter defaults are appended to parameter descriptions.
    :param show_types:
        Whether parameter types are appended to parameter descriptions.
    :param no_negated_flags:
        If `False` (default), for any non-positional bool options, two flags
        are created: ``--foo`` and ``--no-foo``. If `True`, the ``--no-foo``
        is not created for every such option that has a default value `False`.
    :param version:
        If a string, add a ``--version`` flag which prints the given version
        string and exits.
        If `True`, the version string is auto-detected by searching for a
        ``__version__`` attribute on the module where the function is defined,
        and its parent packages, if any.  Error out if such a version cannot be
        found, or if multiple callables with different version strings are
        passed.
        If `None` (the default), behave as for `True`, but don't add a
        ``--version`` flag if no version string can be autodetected.
        If `False`, do not add a ``--version`` flag.
    :param argparse_kwargs:
        A mapping of keyword arguments that will be passed to the
        `~argparse.ArgumentParser` constructor.
    :param argv:
        Command line arguments to parse (default: ``sys.argv[1:]``).
    :return:
        The value returned by the function that was run.
    """
    func, ba = bind(
        funcs, parsers=parsers, short=short, cli_options=cli_options,
        strict_kwonly=strict_kwonly, show_defaults=show_defaults,
        show_types=show_types, no_negated_flags=no_negated_flags,
        version=version, argparse_kwargs=argparse_kwargs, argv=argv)
    sig = signature(func)
    raises, = [
        # typing_inspect does not allow fetching metadata; see e.g. ti#82.
        arg for arg in getattr(sig.return_annotation, '__metadata__', [])
        if isinstance(arg, _Raises)]
    # The function call should occur here to minimize effects on the traceback.
    try:
        return func(*ba.args, **ba.kwargs)
    except raises as e:
        sys.exit(e)


def _recurse_functions(funcs, subparsers):
    if not isinstance(funcs, collections.abc.Mapping):
        # If this iterable is not a maping, then convert it to one using the
        # function name itself as the key, but replacing _ with -.
        try:
            funcs = {func.__name__.replace('_', '-'): func for func in funcs}
        except AttributeError as exc:
            # Do not allow a mapping inside of a list
            raise ValueError(
                'Use dictionaries (mappings) for nesting; other iterables may '
                'only contain functions (callables).'
            ) from exc

    for name, func in funcs.items():
        if callable(func):
            # If this item is callable, then add it to the current
            # subparser using this name.
            subparser = subparsers.add_parser(
                name,
                formatter_class=RawTextHelpFormatter,
                help=_parse_docstring(inspect.getdoc(func)).first_line)
            yield func, subparser
        else:
            # If this item is not callable, then add this name as a new
            # subparser and recurse the the items.
            nestedsubparser = subparsers.add_parser(name)
            nestedsubparsers = nestedsubparser.add_subparsers()
            yield from _recurse_functions(func, nestedsubparsers)


def _create_parser(
        funcs, *,
        parsers={},
        short=None,
        cli_options='kwonly',
        show_defaults=True,
        show_types=False,
        no_negated_flags=False,
        version=None,
        argparse_kwargs={}):
    parser = ArgumentParser(
        **{**{'formatter_class': RawTextHelpFormatter}, **argparse_kwargs})
    version_sources = []
    if callable(funcs):
        _populate_parser(funcs, parser, parsers, short, cli_options,
                         show_defaults, show_types, no_negated_flags)
        version_sources.append(funcs)
    else:
        subparsers = parser.add_subparsers()
        for func, subparser in _recurse_functions(funcs, subparsers):
            _populate_parser(func, subparser, parsers, short, cli_options,
                             show_defaults, show_types, no_negated_flags)
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
    module_name = getattr(func, '__module__', None)
    if not module_name:
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
    - Parameter types are also read from ``func``'s docstring (if a parameter's
      type is specified both in the signature and the docstring, both types
      must match).
    - The docstring for each parameter is available as the
      `~inspect.Parameter`'s ``.doc`` attribute (in fact, a subclass of
      `~inspect.Parameter` is used).
    - The return type is `~typing.Annotated` with the documented raisable
      exception types, in wrapped in a private tuple subclass.
    """
    return _signature(func)


def _signature(func, *, skip_first_arg=False):
    # See _is_constructible_from_str for skip_first_arg.  We can't just drop
    # the first arg later because it may be unannotated.
    orig_sig = inspect.signature(func)
    orig_params = orig_sig.parameters.values()
    if skip_first_arg:
        _, *orig_params = orig_params
    doc = _parse_docstring(inspect.getdoc(func))
    parameters = []
    for param in orig_params:
        if param.name.startswith('_'):
            if param.default is param.empty:
                raise ValueError(
                    'Parameter {} of {}{} is private but has no default'
                    .format(param.name, func.__name__, orig_sig))
        else:
            parameters.append(Parameter(
                name=param.name, kind=param.kind, default=param.default,
                annotation=_get_type(func, param.name),
                doc=doc.params.get(param.name, _Param(None, None)).text))
    exc_types = _Raises(_get_type_from_doc(name, func.__globals__)
                        for name in doc.raises)
    return_annotation = Annotated[orig_sig.return_annotation, exc_types]
    return orig_sig.replace(
        parameters=parameters, return_annotation=return_annotation)


def _populate_parser(func, parser, parsers, short, cli_options,
                     show_defaults, show_types, no_negated_flags):
    sig = signature(func)
    doc = _parse_docstring(inspect.getdoc(func))
    parser.description = doc.text

    positionals = {
        name for name, param in sig.parameters.items()
        if ((cli_options == 'kwonly' or
             (param.default is param.empty and cli_options == 'has_default'))
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
        if type_ in [bool, typing.Optional[bool]] and not positional:
            action = ('store_true' if no_negated_flags and
                      default in [False, None]
                      else _BooleanOptionalAction)  # --name/--no-name
            actions.append(_add_argument(
                parser, name, short, action=action, default=default,
                required=required,  # Always False if `default is False`.
                **kwargs))  # Add help if available.
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
            # Variable-length tuples of homogenous type are specified like
            # Tuple[int, ...]
            if len(member_types) == 2 and member_types[1] is Ellipsis:
                kwargs['nargs'] = "*"
                kwargs['action'] = _make_store_tuple_action_class(
                    tuple, member_types, parsers, is_variable_length=True)
            else:
                kwargs['nargs'] = len(member_types)
                kwargs['action'] = _make_store_tuple_action_class(
                    tuple, member_types, parsers)
        elif (isinstance(type_, type) and issubclass(type_, tuple)
              and hasattr(type_, '_fields')):
            # Before Py3.6, `_field_types` does not preserve order, so retrieve
            # the order from `_fields`.
            hints = typing.get_type_hints(type_)
            member_types = tuple(hints[field] for field in type_._fields)
            kwargs['nargs'] = len(member_types)
            kwargs['action'] = _make_store_tuple_action_class(
                type_, member_types, parsers)
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

    parser.set_defaults(_func=func)


def _add_argument(parser, name, short, _positional=False, **kwargs):
    negative_option_strings = []
    if _positional:
        args = [name]
    else:
        prefix_char = parser.prefix_chars[0]
        name = name.replace('_', '-')
        args = [prefix_char * 2 + name]
        if name in short:
            args.insert(0, prefix_char + short[name])
        if kwargs.get('action') == _BooleanOptionalAction:
            no_name = 'no-' + name
            if no_name in short:
                args.append(prefix_char + short[no_name])
                negative_option_strings.append(args[-1])
            args.append(prefix_char * 2 + no_name)
            negative_option_strings.append(args[-1])
    action = parser.add_argument(*args, **kwargs)
    if negative_option_strings:
        action.negative_option_strings = negative_option_strings
    return action


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
            and action.default is not SUPPRESS):
        info.append(
            'default: {}'.format(action.default.name.replace('%', '%%'))
            if action.type is not None
               and action.type.func is _make_enum_parser
               and isinstance(action.default, action.type.args)
            else 'default: %(default)s')
    parts = [action.help, '({})'.format(', '.join(info)) if info else '']
    action.help = '\n'.join(filter(None, parts)) or ''


def _is_list_like(type_):
    return _ti_get_origin(type_) in [
        list,
        collections.abc.Iterable,
        getattr(collections.abc, 'Collection', object()),
        collections.abc.Sequence,
    ]

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
        param = inspect.signature(func).parameters[name]
        if (param.default is None
                and param.annotation != hint
                and Optional[param.annotation] == hint):
            # `f(x: tuple[int, int] = None)` means we support a tuple, but not
            # None (to constrain the number of arguments).
            hint = param.annotation
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
    # Support for sphinx-specific "list[type]", "tuple[type]" syntax; only
    # needed for Py<3.9.
    # (This intentionally won't catch `List` or `typing.List`.)
    match = re.match(r'(list|tuple)\[([\w\.]+)\]', name)
    if match:
        container, type_ = match.groups()
        container = {'list': List, 'tuple': Tuple}[container]
        return container[eval(type_, globalns)]
    return _get_type_from_hint(eval(name, globalns))


def _get_type_from_hint(hint):
    if _is_list_like(hint):
        [type_] = _ti_get_args(hint)
        return List[type_]
    elif _ti_get_origin(hint) is Union:
        args = _ti_get_args(hint)
        if any(_is_list_like(subtype) for subtype in args):
            non_none = [arg for arg in args if arg is not type(None)]
            if len(non_none) != 1:
                raise ValueError(
                    'unsupported union including container type: {}'
                    .format(hint))
            return non_none[0]
    return hint


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
    # use_ivar avoids generating an unhandled .. attribute:: directive for
    # Attribute blocks, preferring a benign :ivar: field.
    cfg = Config(napoleon_use_ivar=True)
    doc = str(GoogleDocstring(doc, cfg))
    doc = str(NumpyDocstring(doc, cfg))

    with _sphinx_common_roles():
        tree = docutils.core.publish_doctree(
            # Disable syntax highlighting, as 1) pygments is not a dependency
            # 2) we don't render with colors and 3) SH breaks the assumption
            # that literal blocks contain a single text element.
            doc, settings_overrides={'syntax_highlight': 'none'})

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
            super().__init__(document)
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
                (t.lower() if t == t.title() else t) + ':'
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
            # Insert two newlines to separate paragraphs by a blank line.
            # Actually, paragraphs may or may not already have a trailing
            # newline (e.g. text paragraphs do but literal blocks don't) but
            # argparse will strip extra newlines anyways.  This means that
            # extra blank lines in the original docstring will be stripped, but
            # this is less ugly than having a large number of extra blank lines
            # arising e.g. from skipped info fields (which are not rendered).
            # This means that list items are always separated by blank lines,
            # which is an acceptable tradeoff for now.
            text.append('\n\n')
        parsed = _Doc(text[0], ''.join(text), tuples, visitor.raises)
    else:
        parsed = _Doc('', '', tuples, visitor.raises)
    return parsed


def _get_parser(type_, parsers):
    if type_ in parsers:  # Not catching KeyError, to avoid exception chaining.
        parser = functools.partial(parsers[type_])
    elif (type_ in [str, int, float]
          or isinstance(type_, type) and issubclass(type_, PurePath)):
        parser = functools.partial(type_)
    elif type_ == bool:
        parser = functools.partial(_parse_bool)
    elif type_ == slice:
        parser = functools.partial(_parse_slice)
    elif type_ == type(None):
        parser = functools.partial(_parse_none)
    elif type_ == list:
        raise ValueError('unable to parse list (try list[type])')
    elif isinstance(type_, type) and issubclass(type_, Enum):
        parser = _make_enum_parser(type_)
    elif _is_constructible_from_str(type_):
        parser = functools.partial(type_)
    elif _ti_get_origin(type_) in [Union, getattr(types, "UnionType", "")]:
        args = _ti_get_args(type_)
        if type(None) in args:
            # If None is in the Union, parse it first.  This only matters if
            # there's a custom parser for None, in which case the user should
            # normally have picked values that they *want* to be parsed as
            # None as opposed to anything else, e.g. strs, even if that was
            # possible.
            args = (type(None),
                    *[arg for arg in args if arg is not type(None)])
        parser = _make_union_parser(
            type_, [_get_parser(arg, parsers) for arg in args])
    elif _ti_get_origin(type_) is Literal:
        args = _ti_get_args(type_)
        parser = _make_literal_parser(
            type_, [_get_parser(type(arg), parsers) for arg in args])
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


def _parse_none(string):
    raise ValueError('No string can be converted to None')


def _make_enum_parser(enum, value=None):
    if value is None:
        return functools.partial(_make_enum_parser, enum)
    try:
        return enum[value]
    except KeyError:
        raise ArgumentTypeError(
            'invalid choice: {!r} (choose from {})'.format(
                value, ', '.join(map(repr, enum.__members__))))


def _is_constructible_from_str(type_, *, skip_first_arg=False):
    try:
        sig = _signature(type_, skip_first_arg=skip_first_arg)
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
        # skip_first_arg behaves as if the first parameter was bound, i.e.
        # __init__.__get__(object(), type_) but the latter can fail for types
        # implemented in C (which don't support binding arbitrary objects).
        return _is_constructible_from_str(
            type_.__init__, skip_first_arg=True)
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


def _make_store_tuple_action_class(
    tuple_type, member_types, parsers, *, is_variable_length=False):
    if is_variable_length:
        parsers = itertools.repeat(_get_parser(member_types[0], parsers))
    else:
        parsers = [_get_parser(arg, parsers) for arg in member_types]

    class _StoreTupleAction(Action):
        def __call__(self, parser, namespace, values, option_string=None):
            try:
                value = tuple(p(value) for p, value in zip(parsers, values))
            except ArgumentTypeError as exc:
                raise ArgumentError(self, str(exc))
            if tuple_type is not tuple:
                value = tuple_type(*value)
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
