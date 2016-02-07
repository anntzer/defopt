import argparse
import builtins
from collections import defaultdict, namedtuple
from enum import Enum
import inspect
import logging
import sys
from xml.etree import ElementTree

from docutils.core import publish_doctree

logging.basicConfig()

Doc = namedtuple('Doc', ('text', 'params'))
Param = namedtuple('Param', ('text', 'type'))

_main = None
_subcommands = []
_parsers = {}


def main(func):
    """Register the given function as the main function.

    The function is returned unmodified.

    >>> @main
    ... def func():
    ...     pass
    """
    global _main
    if _main is not None:
        raise Exception('multiple definitions found for main')
    _main = func
    return func


def subcommand(func):
    """Register the given function as a subcommand.

    The function is returned unmodified.

    >>> @subcommand
    ... def func():
    ...    pass
    """
    _subcommands.append(func)
    return func


def parser(type_):
    """Register the given function as a parser for the given type.

    The function must take a single string argument.

    The function is returned unmodified.

    >>> @parser(bool)
    ... def func(string):
    ...     return string.lower() in ['y', 'yes']
    """
    def decorator(func):
        if type_ in _parsers:
            raise Exception('multiple parsers found for {}'.format(type_.__name__))
        _parsers[type_] = func
    return decorator


def run(argv=None):
    """Process command line arguments and run the registered functions.

    >>> if __name__ == '__main__':
    ...     run()
    """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser()
    parser.set_defaults(_func=None)
    if _main:
        _populate_parser(_main, parser)
    if _subcommands:
        subparsers = parser.add_subparsers()
        for func in _subcommands:
            subparser = subparsers.add_parser(func.__name__)
            _populate_parser(func, subparser)
            subparser.set_defaults(_func=func)
    args = parser.parse_args(argv)
    _substitute_enums(parser, args)
    # Workaround for http://bugs.python.org/issue9253#msg186387
    if _subcommands and args._func is None:
        parser.error('too few arguments')
    if _main:
        _call_function(_main, args)
    if _subcommands:
        _call_function(args._func, args)


def _populate_parser(func, parser):
    sig = inspect.signature(func)
    doc = _parse_doc(func)
    parser.description = doc.text
    parser._enums = {}
    for name, param in sig.parameters.items():
        default = None
        nargs = None
        if param.kind == param.VAR_KEYWORD:
            raise ValueError('**kwargs not supported')
        if param.default is param.empty:
            flag = name
            if param.kind == param.VAR_POSITIONAL:
                nargs = '*'
        else:
            flag = '--' + name
            default = param.default
        help_ = doc.params[name].text
        type_ = _evaluate(doc.params[name].type, stack_depth=2)
        if inspect.isclass(type_) and issubclass(type_, Enum):
            # argparse won't handle the enum well so we'll have to post-process
            choices = [x.name for x in type_]
            parser._enums[name] = type_
            type_ = None
        else:
            type_ = _get_parser(type_)
            choices = None
        parser.add_argument(flag,
                            nargs=nargs,
                            default=default,
                            type=type_,
                            choices=choices,
                            help=help_)
    return parser


def _substitute_enums(parser, args):
    """Swap out any enum strings for their members."""
    if not hasattr(parser, '_enums'):
        return
    for name, value in vars(args).items():
        try:
            enum = parser._enums[name]
        except KeyError:
            continue
        setattr(args, name, enum[value])


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
    doc = inspect.getdoc(func)
    dom = publish_doctree(doc).asdom()
    etree = ElementTree.fromstring(dom.toxml())
    doctext = '\n\n'.join(x.text for x in etree.findall('paragraph'))
    fields = etree.findall('field_list/field')

    params = defaultdict(dict)
    for field in fields:
        field_name = field.find('field_name')
        field_body = field.find('field_body')
        parts = field_name.text.split()
        if len(parts) < 2:
            logging.debug('ignoring field %s', field_name.text)
            continue
        doctype, name = parts
        text = ''.join(field_body.itertext())
        logging.debug('%s %s: %s', doctype, name, text)
        params[name][doctype] = text

    tuples = {}
    for name, values in params.items():
        tuples[name] = Param(values.get('param'), values.get('type'))
    return Doc(doctext, tuples)


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
    logging.debug('evaluating %s', name)
    things = dict(vars(builtins))
    if stack_depth is not None:
        things.update(inspect.stack()[stack_depth + 1].frame.f_locals)
        things.update(inspect.stack()[stack_depth + 1].frame.f_globals)
    parts = name.split('.')
    thing = things[parts[0]]
    for part in parts[1:]:
        things = vars(thing)
        thing = things[part]
    logging.debug('evaluated to %r', thing)
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
    else:
        raise Exception('no parser found for type {}'.format(type_.__name__))


def _parse_bool(string):
    if string.lower() in ['t', 'true']:
        return True
    elif string.lower() in ['f', 'false']:
        return False
    else:
        raise ValueError('{} is not a valid boolean string'.format(string))
