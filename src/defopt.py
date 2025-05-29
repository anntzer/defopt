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
import os
import re
import sys
import types
import typing
from argparse import (
    REMAINDER, SUPPRESS,
    Action, ArgumentParser, RawTextHelpFormatter,
    ArgumentError, ArgumentTypeError)
from collections import defaultdict, namedtuple, Counter
from enum import Enum
from pathlib import PurePath
from types import MethodType
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    import importlib.metadata as _im
except ImportError:
    import importlib_metadata as _im
try:
    from pkgutil import resolve_name as _pkgutil_resolve_name
except ImportError:
    from pkgutil_resolve_name import resolve_name as _pkgutil_resolve_name
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal
try:
    from typing import get_args as _ti_get_args, get_origin as _ti_get_origin
except ImportError:
    import typing_inspect as _ti
    _ti_get_args = _ti.get_args
    _ti_get_origin = _ti.get_origin

import docutils.core
from docutils.nodes import NodeVisitor, SkipNode, TextElement
from docutils.parsers.rst.states import Body

try:
    collections.Callable = collections.abc.Callable
    from sphinxcontrib.napoleon import Config, GoogleDocstring, NumpyDocstring
finally:
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

__all__ = ['run', 'signature', 'bind', 'bind_known']

_PARAM_TYPES = ['param', 'parameter', 'arg', 'argument', 'key', 'keyword']
_TYPE_NAMES = ['type', 'kwtype']
_LIST_TYPES = [
    list,
    collections.abc.Iterable,
    collections.abc.Collection,
    collections.abc.Sequence,
]


class _BooleanOptionalAction(Action):
    # Modified from Py3.9's version, plus:
    # - a fix to bpo#38956 (by omitting the extraneous help string),
    # - support for short aliases for --no-foo, by moving negative flag
    #   generation to _add_argument (where the negative aliases are available),
    # - a hack (_CustomString) to simulate format_usage on Py<3.9
    #   (_CustomString relies on an Py<3.9 implementation detail: the usage
    #   string is built using '%s' % option_strings[0] (so there is an
    #   additional call to str()) whereas the option invocation help directly
    #   joins the strings).

    class _CustomString(str):
        def __str__(self):
            return self.action.format_usage()

    def __init__(self, option_strings, **kwargs):
        self.negative_option_strings = []  # set by _add_argument
        if option_strings:
            cs = option_strings[0] = self._CustomString(option_strings[0])
            cs.action = self
        super().__init__(option_strings, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if option_string in self.option_strings:
            setattr(namespace, self.dest,
                    option_string not in self.negative_option_strings)

    def format_usage(self):
        return ' | '.join(self.option_strings)


class _PseudoChoices(list):
    """
    Pseudo-type used for ``add_argument(..., choices=...)`` so that usage
    strings correctly print choices (as their corresponding str values) for
    enums and literals, but without actually checking for containment (as
    argparse does that on the type-converted values, which are different).

    Note that abusing metavar to generate the usage string does not work as
    well, as that also affects the argument name in generated error messages
    (see `argparse._get_action_name`).
    """

    def __init__(self, items):
        super().__init__(str(item.name if isinstance(item, Enum) else item)
                         for item in items)

    def __contains__(self, obj):
        return True


class _DefaultList(list):
    """
    Marker type used to determine that a parameter corresponds to a varargs,
    and thus should have its default value hidden.  Varargs are unpacked during
    function call, so the caller won't see this type.
    """


def _check_in_list(_values, **kwargs):
    for k, v in kwargs.items():
        if v not in _values:
            raise ValueError(f'{k!r} must be one of {_values!r}, not {v!r}')


def _bind_or_bind_known(funcs, *, opts, _known: bool = False):
    _check_in_list(['kwonly', 'all', 'has_default'],
                   cli_options=opts.cli_options)
    parser = _create_parser(funcs, opts)
    with _colorama_text():
        if not opts.intermixed:
            if not _known:
                args, rest = parser.parse_args(opts.argv), []
            else:
                args, rest = parser.parse_known_args(opts.argv)
        else:
            if not _known:
                args, rest = parser.parse_intermixed_args(opts.argv), []
            else:
                args, rest = parser.parse_known_intermixed_args(opts.argv)
    parsed_args = vars(args)
    try:
        func = parsed_args.pop('_func')
    except KeyError:
        # Workaround for http://bugs.python.org/issue9253#msg186387 (and
        # https://bugs.python.org/issue29298 which blocks using required=True).
        parser.error('too few arguments')
    sig = signature(func)
    ba = sig.bind_partial()
    ba.arguments.update(parsed_args)
    call = functools.partial(func, *ba.args, **ba.kwargs)

    if sig.raises:
        @functools.wraps(call)
        def wrapper():
            try:
                return call()
            except sig.raises as e:
                sys.exit(e)

        return wrapper, rest

    else:
        return call, rest


def bind(*args, **kwargs):
    """
    Process command-line arguments and bind arguments.

    This function takes the same parameters as `defopt.run`, but returns a
    wrapper callable ``call`` such that ``call()`` represents the call that
    ``defopt.run`` would execute.  Note that ``call`` takes no arguments; they
    are bound internally.

    If there are no documented exceptions that ``defopt.run`` needs to
    suppress, then ``call`` is a `functools.partial` object, ``call.func`` is
    one of the functions passed to ``bind``, and ``call.args`` and
    ``call.keywords`` are set according to the command-line arguments.

    If there are documented exceptions that ``defopt.run`` needs to suppress,
    then ``call`` is a wrapper around that partial object.

    A generic expression to retrieve the underlying selected function is thus
    ``getattr(call, "__wrapped__", call).func``.

    This API is provisional and may be adjusted depending on feedback.
    """
    call, rest = _bind_or_bind_known(
        *args, opts=_options(**kwargs), _known=False)
    assert not rest
    return call


def bind_known(*args, **kwargs):
    """
    Process command-line arguments and bind known arguments.

    This function behaves as `bind`, but returns a pair of 1) the
    `~functools.partial` callable, and 2) a list of unknown command-line
    arguments, as returned by `~argparse.ArgumentParser.parse_known_args`.

    This API is provisional and may be adjusted depending on feedback.
    """
    return _bind_or_bind_known(
        *args, opts=_options(**kwargs), _known=True)


Funcs = Union[Callable, List[Callable], Dict[str, 'Funcs']]


def run(
    funcs: Funcs, *,
    parsers: Dict[type, Callable[[str], Any]] = {},
    short: Optional[Dict[str, str]] = None,
    cli_options: Literal['kwonly', 'all', 'has_default'] = 'kwonly',
    show_defaults: bool = True,
    show_types: bool = False,
    no_negated_flags: bool = False,
    version: Union[str, None, bool] = None,
    argparse_kwargs: dict = {},
    intermixed: bool = False,
    argv: Optional[List[str]] = None,
):
    """
    Process command-line arguments and run the given functions.

    *funcs* can be a single callable, which is parsed and run; or it can
    be a list of callables or mappable of strs to callables, in which case
    each one is given a subparser with its name (if *funcs* is a list) or
    the corresponding key (if *funcs* is a mappable), and only the chosen
    callable is run.  Nested mappables are also supported; they define nested
    subcommands.

    See :doc:`/features` for the detailed mapping from function signature to
    command-line parsing.  Note that all docstrings must be valid RST
    conforming to Sphinx-, Google-, or Numpy-style.

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
        to optional positional command line parameters.  'all' turns all
        parameters into command-line flags.  'has_default' turns a parameter
        into a command-line flag if and only if it has a default value.
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
    :param intermixed:
        Whether to use `~argparse.ArgumentParser.parse_intermixed_args` to
        parse the command line.  Intermixed parsing imposes many restrictions,
        listed in the `argparse` documentation.
    :param argv:
        Command line arguments to parse (default: ``sys.argv[1:]``).
    :return:
        The value returned by the function that was run.
    """
    return bind(
        funcs, parsers=parsers, short=short, cli_options=cli_options,
        show_defaults=show_defaults, show_types=show_types,
        no_negated_flags=no_negated_flags, version=version,
        argparse_kwargs=argparse_kwargs, intermixed=intermixed, argv=argv)()


_DefoptOptions = namedtuple(
    '_DefoptOptions',
    ['parsers', 'short', 'cli_options', 'show_defaults', 'show_types',
     'no_negated_flags', 'version', 'argparse_kwargs', 'intermixed', 'argv'])


def _options(**kwargs):
    params = inspect.signature(run).parameters
    return (
        _DefoptOptions(*[params[k].default for k in _DefoptOptions._fields])
        ._replace(**kwargs))


def _recurse_functions(funcs, subparsers):
    if not isinstance(funcs, collections.abc.Mapping):
        # If this iterable is not a mapping, then convert it to one using the
        # function name itself as the key, but replacing _ with -.
        try:
            funcs = {_unwrap_partial(func).__name__.replace('_', '-'): func
                     for func in funcs}
        except AttributeError as exc:
            # Do not allow a mapping inside of a list
            raise ValueError(
                'use dictionaries (mappings) for nesting; other iterables may '
                'only contain functions (callables)'
            ) from exc

    for name, func in funcs.items():
        if callable(func):
            # If this item is callable, then add it to the current
            # subparser using this name.
            doc = inspect.getdoc(_unwrap_partial(func))
            sp_help = signature(doc).doc.split('\n\n', 1)[0]
            subparser = subparsers.add_parser(
                name, formatter_class=RawTextHelpFormatter, help=sp_help)
            yield func, subparser
        else:
            # If this item is not callable, then add this name as a new
            # subparser and recurse the the items.
            nestedsubparser = subparsers.add_parser(name)
            nestedsubparsers = nestedsubparser.add_subparsers()
            yield from _recurse_functions(func, nestedsubparsers)


def _create_parser(funcs, opts):
    parser = ArgumentParser(**{**{'formatter_class': RawTextHelpFormatter},
                               **opts.argparse_kwargs})
    version_sources = []
    if callable(funcs):
        _populate_parser(funcs, parser, opts)
        version_sources.append(_unwrap_partial(funcs))
    else:
        subparsers = parser.add_subparsers()
        for func, subparser in _recurse_functions(funcs, subparsers):
            _populate_parser(func, subparser, opts)
            version_sources.append(_unwrap_partial(func))
    if isinstance(opts.version, str):
        version_string = opts.version
    elif opts.version is None or opts.version:
        version_string = _get_version(version_sources)
        if opts.version and version_string is None:
            raise ValueError('failed to autodetect version string')
    else:
        version_string = None
    if version_string is not None:
        parser.add_argument(
            2 * parser.prefix_chars[0] + 'version',
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


class Signature(inspect.Signature):
    __slots__ = (*inspect.Signature.__slots__, '_doc', '_raises')
    doc = property(lambda self: self._doc)
    raises = property(lambda self: self._raises)

    def __init__(self, *args, doc=None, raises=(), **kwargs):
        super().__init__(*args, **kwargs)
        self._doc = doc
        self._raises = tuple(raises)

    def replace(self, *, doc=inspect._void, raises=inspect._void, **kwargs):
        copy = super().replace(**kwargs)
        copy._doc = self._doc if doc is inspect._void else doc
        copy._raises = tuple(
            self._raises if raises is inspect._void else raises)
        return copy


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


@functools.lru_cache()
def signature(func: Union[Callable, str]):
    """
    Return an enhanced signature for ``func``.

    This function behaves similarly to `inspect.signature`, with the following
    differences:

    - The parsed function docstring (which will be used as the parser
      description) is available as ``signature.doc``; likewise, parameter
      docstrings are available as ``parameter.doc``.  The tuple of raisable
      exception types is available is available as ``signature.raises``.  (This
      is done by using subclasses of `inspect.Signature` and
      `inspect.Parameter`.)
    - Private parameters (starting with an underscore) are not listed.
    - Parameter types are also read from ``func``'s docstring (if a parameter's
      type is specified both in the signature and the docstring, both types
      must match).
    - It is also possible to pass a docstring instead of a callable as *func*;
      in that case, a Signature is still returned, but all parameters are
      considered positional-or-keyword, with no default, and the annotations
      are returned as strs.

    This API is provisional and may be adjusted depending on feedback.
    """
    if isinstance(func, str) or func is None:
        return _parse_docstring(func)
    else:
        inspect_sig = _preprocess_inspect_signature(
            func, inspect.signature(func))
        doc_sig = _preprocess_doc_signature(
            func, signature(inspect.getdoc(_unwrap_partial(func))))
        return _merge_signatures(inspect_sig, doc_sig)


def _unwrap_partial(func):
    return func.func if isinstance(func, functools.partial) else func


def _preprocess_inspect_signature(func, sig):
    hints = typing.get_type_hints(_unwrap_partial(func))
    parameters = []
    for name, param in sig.parameters.items():
        if param.name.startswith('_'):
            if param.default is param.empty:
                raise ValueError(
                    f'parameter {name} of {func.__name__}{sig} is private but '
                    f'has no default')
            continue
        try:
            hint = hints[name]
        except KeyError:
            hint_type = param.empty
        else:
            if (param.default is None
                    and param.annotation != hint
                    and Optional[param.annotation] == hint):
                # `f(x: tuple[int, int] = None)` means we support a tuple, but
                # not None (to constrain the number of arguments).
                hint = param.annotation
            hint_type = _get_type_from_hint(hint)
        parameters.append(Parameter(
            name=name, kind=param.kind, default=param.default,
            annotation=hint_type))
    return sig.replace(parameters=parameters)


def _preprocess_doc_signature(func, sig):
    parameters = []
    for name, param in sig.parameters.items():
        if param.name.startswith('_'):
            continue
        doc_type = (sig.parameters[name].annotation
                    if name in sig.parameters else param.empty)
        doc_type = (
            _get_type_from_doc(doc_type, _unwrap_partial(func).__globals__)
            if doc_type is not param.empty else param.empty)
        parameters.append(Parameter(
            name=name, kind=param.kind, annotation=doc_type,
            doc=(sig.parameters[name].doc
                 if name in sig.parameters else None)))
    return Signature(
        parameters,
        doc=sig.doc,
        raises=[_get_type_from_doc(name, func.__globals__)
                for name in sig.raises])


def _merge_signatures(inspect_sig, doc_sig):
    parameters = []
    for name, param in inspect_sig.parameters.items():
        doc_param = doc_sig.parameters.get(name)
        if doc_param:
            anns = set()
            if param.annotation is not param.empty:
                anns.add(param.annotation)
            if doc_param.annotation is not param.empty:
                anns.add(doc_param.annotation)
            if len(anns) > 1:
                raise ValueError(
                    f'conflicting types found for parameter {name}: '
                    f'{param.annotation.__name__}, '
                    f'{doc_param.annotation.__name__}')
            ann = anns.pop() if anns else param.empty
            param = param.replace(annotation=ann, doc=doc_param.doc)
        parameters.append(param)
    return Signature(
        parameters, return_annotation=inspect_sig.return_annotation,
        doc=doc_sig.doc, raises=doc_sig.raises)


def _get_type_from_doc(name, globalns):
    if ' or ' in name:
        subtypes = [_get_type_from_doc(part, globalns)
                    for part in name.split(' or ')]
        if any(map(_is_list_like, subtypes)) and None not in subtypes:
            raise ValueError(
                f'unsupported union including container type: {name}')
        return Union[tuple(subtype for subtype in subtypes)]
    if sys.version_info < (3, 9):  # Support "list[type]", "tuple[type]".
        globalns = {**globalns, 'tuple': Tuple, 'list': List}
    return _get_type_from_hint(eval(name, globalns))


def _get_type_from_hint(hint):
    if _is_list_like(hint):
        [type_] = _ti_get_args(hint)
        return List[type_]
    return hint


def _populate_parser(func, parser, opts):
    sig = signature(func)
    parser.description = sig.doc

    positionals = {
        name for name, param in sig.parameters.items()
        if ((opts.cli_options == 'kwonly' or
             (param.default is param.empty
              and opts.cli_options == 'has_default'))
            and not any(
                _is_list_like(t) or _is_optional_list_like(t) for t in [
                    param.annotation.__value__
                    if hasattr(typing, 'TypeAliasType')
                    and isinstance(param.annotation, typing.TypeAliasType)
                    else param.annotation
                ]
            )
            and param.kind != param.KEYWORD_ONLY)}
    if opts.short is None:
        count_initials = Counter(name[0] for name in sig.parameters
                                 if name not in positionals)
        if parser.add_help:
            count_initials['h'] += 1
        opts = opts._replace(short={
            name.replace('_', '-'): name[0] for name in sig.parameters
            if name not in positionals and count_initials[name[0]] == 1})

    actions = []
    for name, param in sig.parameters.items():
        kwargs = {}
        if param.doc is not None:
            kwargs['help'] = param.doc.replace('%', '%%')
        type_ = param.annotation
        if (hasattr(typing, 'TypeAliasType')
                and isinstance(type_, typing.TypeAliasType)):
            type_ = type_.__value__
        if param.kind == param.VAR_KEYWORD:
            raise ValueError('**kwargs not supported')
        if type_ is param.empty:
            raise ValueError(f'no type found for parameter {name}')
        hasdefault = param.default is not param.empty
        default = param.default if hasdefault else SUPPRESS
        required = not hasdefault and param.kind != param.VAR_POSITIONAL
        positional = name in positionals

        # Special-case boolean flags.
        if type_ in [bool, typing.Optional[bool]] and not positional:
            action = ('store_true'
                      if opts.no_negated_flags and default in [False, None]
                      else _BooleanOptionalAction)  # --name/--no-name
            actions.append(_add_argument(
                parser, name, opts.short, action=action, default=default,
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

        # If the type is an Optional container, extract only the container.
        union_args = _ti_get_args(type_) if _is_union_type(type_) else []
        if any(_is_container(subtype) for subtype in union_args):
            non_none = [arg for arg in union_args if arg is not type(None)]
            if len(non_none) != 1:
                raise ValueError(
                    f'unsupported union including container type: {type_}')
            type_, = non_none

        if _is_list_like(type_):
            type_, = _ti_get_args(type_)
            kwargs['nargs'] = '*'
            if param.kind == param.VAR_POSITIONAL:
                kwargs['action'] = 'append'
                kwargs['default'] = _DefaultList()

        if isinstance(type_, type) and issubclass(type_, Enum):
            # Enums must be checked first to handle enums-of-namedtuples.
            kwargs['type'] = _get_parser(type_, opts.parsers)
            kwargs['choices'] = _PseudoChoices(type_.__members__.values())

        elif _ti_get_origin(type_) is tuple:
            member_types = _ti_get_args(type_)
            num_members = len(member_types)
            if num_members == 2 and member_types[1] is Ellipsis:
                # Variable-length tuples of homogenous type are specified like
                # tuple[int, ...]
                kwargs['nargs'] = '*'
                kwargs['action'] = _make_store_tuple_action_class(
                    tuple, member_types, opts.parsers, is_variable_length=True)
            elif type(None) in union_args and opts.parsers.get(type(None)):
                if num_members == 1:
                    kwargs['nargs'] = 1
                    kwargs['action'] = _make_store_tuple_action_class(
                        tuple, member_types, opts.parsers,
                        with_none_parser=opts.parsers[type(None)])
                else:
                    raise ValueError(
                        'Optional tuples of length > 1 and NoneType parsers '
                        'cannot be used together due to ambiguity')
            else:
                kwargs['nargs'] = num_members
                kwargs['action'] = _make_store_tuple_action_class(
                    tuple, member_types, opts.parsers)

        elif (isinstance(type_, type) and issubclass(type_, tuple)
              and hasattr(type_, '_fields')):
            # Before Py3.6, `_field_types` does not preserve order, so retrieve
            # the order from `_fields`.
            hints = typing.get_type_hints(type_)
            member_types = tuple(hints[field] for field in type_._fields)
            kwargs['nargs'] = len(member_types)
            kwargs['action'] = _make_store_tuple_action_class(
                type_, member_types, opts.parsers)
            if not positional:  # http://bugs.python.org/issue14074
                kwargs['metavar'] = type_._fields

        else:
            kwargs['type'] = _get_parser(type_, opts.parsers)
            if _ti_get_origin(type_) is Literal:
                kwargs['choices'] = _PseudoChoices(_ti_get_args(type_))

        actions.append(_add_argument(parser, name, opts.short, **kwargs))

    for action in actions:
        _update_help_string(action, opts)

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


def _update_help_string(action, opts):
    action_help = action.help or ''
    info = []
    if (opts.show_types
            and action.type is not None
            and action.type.func not in [_make_enum_parser,
                                         _make_literal_parser]
            and '%(type)' not in action_help):
        info.append('type: %(type)s')
    if (opts.show_defaults
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
    return _ti_get_origin(type_) in _LIST_TYPES


def _is_container(type_):
    return _ti_get_origin(type_) in {*_LIST_TYPES, tuple}


def _is_union_type(type_):
    return _ti_get_origin(type_) in {Union, getattr(types, 'UnionType', '')}


def _is_optional_list_like(type_):
    # Assume a union with a list subtype is actually Optional[list[...]]
    # because this condition is enforced in other places
    return (_is_union_type(type_)
            and any(_is_list_like(subtype) for subtype in _ti_get_args(type_)))


def _passthrough_role(
    name, rawtext, text, lineno, inliner, options={}, content=[],
):
    return [TextElement(rawtext, text)], []


@contextlib.contextmanager
def _sphinx_common_roles():
    # Standard roles:
    # https://www.sphinx-doc.org/en/master/usage/restructuredtext/roles.html
    # Python-domain roles:
    # https://www.sphinx-doc.org/en/master/usage/restructuredtext/domains.html
    roles = [
        'abbr',
        'command',
        'dfn',
        'file',
        'guilabel',
        'kbd',
        'mailheader',
        'makevar',
        'manpage',
        'menuselection',
        'mimetype',
        'newsgroup',
        'program',
        'regexp',
        'samp',
        'pep',
        'rfc',
        'py:mod',
        'py:func',
        'py:data',
        'py:const',
        'py:class',
        'py:meth',
        'py:attr',
        'py:exc',
        'py:obj'
    ]
    # No public unregistration API :(  Also done by sphinx.
    role_map = docutils.parsers.rst.roles._roles
    for role in roles:
        for i in range(role.count(':') + 1):
            role_map[role.split(':', i)[-1]] = _passthrough_role
    try:
        yield
    finally:
        for role in roles:
            for i in range(role.count(':') + 1):
                role_map.pop(role.split(':', i)[-1])


def _parse_docstring(doc):
    """
    Extract documentation from a function's docstring into a `.Signature`
    object *with unevaluated annotations*.
    """

    if doc is None:
        return Signature(doc='')

    # Convert Google- or Numpy-style docstrings to RST.
    # (Should do nothing if not in either style.)
    # use_ivar avoids generating an unhandled .. attribute:: directive for
    # Attribute blocks, preferring a benign :ivar: field.
    doc = inspect.cleandoc(doc)
    cfg = Config(napoleon_use_ivar=True)
    doc = str(GoogleDocstring(doc, cfg))
    doc = str(NumpyDocstring(doc, cfg))

    with _sphinx_common_roles():
        tree = docutils.core.publish_doctree(
            # - Propagate errors out.
            # - Disable syntax highlighting, as 1) pygments is not a dependency
            #   2) we don't render with colors and 3) SH breaks the assumption
            #   that literal blocks contain a single text element.
            doc, settings_overrides={
                'halt_level': 3, 'syntax_highlight': 'none'})

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

        visit_reference = depart_reference = _do_nothing

        def visit_target(self, node):
            if self._current_paragraph is None:
                raise SkipNode

            if node.get('refuri'):
                self._current_paragraph.append(f' ({node["refuri"]})')
            else:
                self._current_paragraph.append(node.astext())
            raise SkipNode

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
                    raise ValueError(f'type defined twice for {name}')
                self.params[name]['type'] = type_
            else:
                raise SkipNode
            if doctype in _PARAM_TYPES:
                doctype = 'param'
            if doctype in _TYPE_NAMES:
                doctype = 'type'
            if doctype in ['param', 'type'] and doctype in self.params[name]:
                raise ValueError(f'{doctype} defined twice for {name}')
            visitor = Visitor(self.document)
            field_body_node.walkabout(visitor)
            if doctype in ['param', 'type']:
                self.params[name][doctype] = '\n\n'.join(visitor.paragraphs)
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

    params = [Parameter(name, kind=Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=values.get('type', Parameter.empty),
                        doc=values.get('param'))
              for name, values in visitor.params.items()]
    text = []
    if visitor.paragraphs:
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
    return Signature(params, doc=''.join(text), raises=visitor.raises)


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
    elif _is_union_type(type_):
        args = _ti_get_args(type_)
        if type(None) in args:
            # If None is in the Union, parse it first.  This only matters if
            # there's a custom parser for None, in which case the user should
            # normally have picked values that they *want* to be parsed as
            # None as opposed to anything else, e.g. strs, even if that was
            # possible.
            args = (type(None),
                    *[arg for arg in args if arg is not type(None)])
        elem_parsers = []
        for arg in args:
            elem_parser = _get_parser(arg, parsers)
            elem_parsers.append(elem_parser)
            if (isinstance(elem_parser, functools.partial)
                    and (elem_parser.func is str
                         or isinstance(elem_parser.func, type)
                         and issubclass(elem_parser.func, PurePath))
                    and not (elem_parser.args or elem_parser.keywords)):
                # Infaillible parser; skip all following types (which may not
                # even have a parser defined).
                break
        parser = _make_union_parser(type_, elem_parsers)
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
        raise ValueError(f'{string!r} is not a valid boolean string')


def _parse_slice(string):
    slices = []

    class SliceVisitor(ast.NodeVisitor):
        def visit_Slice(self, node):
            start = ast.literal_eval(node.lower) if node.lower else None
            stop = ast.literal_eval(node.upper) if node.upper else None
            step = ast.literal_eval(node.step) if node.step else None
            slices.append(slice(start, stop, step))

    try:
        SliceVisitor().visit(ast.parse(f'_[{string}]'))
        sl, = slices
    except (SyntaxError, ValueError):
        raise ValueError(f'{string!r} is not a valid slice string')
    return sl


def _parse_none(string):
    raise ValueError('no string can be converted to None')


def _is_constructible_from_str(type_):
    try:
        sig = signature(type_)
        (argname, _), = sig.bind(object()).arguments.items()
    except TypeError:  # Can be raised by signature() or Signature.bind().
        return False
    except ValueError:
        # No relevant info in signature; continue below to also look in
        # `type_.__init__`, in the case where type_ is indeed a type.
        pass
    else:
        if sig.parameters[argname].annotation is str:
            return True
    if isinstance(type_, type):
        # signature() first checks __new__, if it is present.
        # `MethodType(type_.__init__, object())` binds the first parameter of
        # `__init__` -- similarly to `__init__.__get__(object(), type_)`, but
        # the latter can fail for types implemented in C (which may not support
        # binding arbitrary objects).
        return _is_constructible_from_str(MethodType(type_.__init__, object()))
    return False


# _make_{enum,literal}_parser raise ArgumentTypeError so that the error message
# generated for invalid inputs is fully customized to match standard argparse
# 'choices': "argument x: invalid choice: '{value}' (choose from ...)".
# The other parsers raise ValueError, which leads to
# "argument x: invalid {type} value: '{value}'".


def _make_enum_parser(enum, value=None):
    if value is None:
        return functools.partial(_make_enum_parser, enum)
    try:
        return enum[value]
    except KeyError:
        raise ArgumentTypeError(
            'invalid choice: {!r} (choose from {})'.format(
                value, ', '.join(map(repr, enum.__members__))))


def _make_literal_parser(literal, parsers, value=None):
    if value is None:
        return functools.partial(_make_literal_parser, literal, parsers)
    for arg, parser in zip(_ti_get_args(literal), parsers):
        try:
            if parser(value) == arg:
                return arg
        except (ValueError, ArgumentTypeError):
            pass
    raise ArgumentTypeError(
        'invalid choice: {!r} (choose from {})'.format(
            value, ', '.join(
                map(repr, _PseudoChoices(_ti_get_args(literal))))))


def _make_union_parser(union, parsers, value=None):
    if value is None:
        return functools.partial(_make_union_parser, union, parsers)
    suppressed = []
    for parser in parsers:
        try:
            return parser(value)
        # See ArgumentParser._get_value.
        except (TypeError, ValueError, ArgumentTypeError) as exc:
            suppressed.append((parser, exc))
    _report_suppressed_exceptions(suppressed)
    raise ValueError(f'{value} could not be parsed as any of {union}')


def _make_store_tuple_action_class(
    tuple_type, member_types, parsers, *,
    is_variable_length=False, with_none_parser=None,
):
    if is_variable_length:
        parsers = itertools.repeat(_get_parser(member_types[0], parsers))
    else:
        parsers = [_get_parser(arg, parsers) for arg in member_types]

    def parse(action, values):
        if with_none_parser is not None:
            try:
                return with_none_parser(*values)
            except ValueError:
                pass
        try:
            value = tuple(
                parser(value) for parser, value in zip(parsers, values))
        except (ValueError, ArgumentTypeError) as exc:
            # Custom actions need to raise ArgumentError, not ValueError or
            # ArgumentTypeError.
            raise ArgumentError(action, str(exc))
        if tuple_type is not tuple:
            value = tuple_type(*value)
        return value

    class _StoreTupleAction(Action):
        def __call__(self, parser, namespace, values, option_string=None):
            setattr(namespace, self.dest, parse(self, values))

    return _StoreTupleAction


def _report_suppressed_exceptions(suppressed):
    if not os.environ.get("DEFOPT_DEBUG"):
        return
    print("The following parsing failures were suppressed:\n", file=sys.stderr)
    for parser, exc in suppressed:
        print(parser, file=sys.stderr)
        print(exc, file=sys.stderr)
        print(file=sys.stderr)


if __name__ == '__main__':
    def main(argv=None):
        parser = ArgumentParser()
        parser.add_argument(
            'function',
            help='package.name.function_name or package.name:function_name')
        parser.add_argument('args', nargs=REMAINDER)
        args = parser.parse_args(argv)
        func = _pkgutil_resolve_name(args.function)
        argparse_kwargs = (
            {'prog': ' '.join(sys.argv[:2])} if argv is None else {})
        retval = run(func, argv=args.args, argparse_kwargs=argparse_kwargs)
        sys.displayhook(retval)

    main()
