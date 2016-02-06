import argparse
import inspect
import sys

_main = None
_subcommands = []


def main(func):
    global _main
    if _main is not None:
        raise Exception('multiple definitions found for main')
    _main = func
    return func


def subcommand(func):
    _subcommands.append(func)
    return func


def run(argv=None):
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
    # Workaround for http://bugs.python.org/issue9253#msg186387
    if _subcommands and args._func is None:
        parser.error('too few arguments')
    if _main:
        _call_function(_main, args)
    if _subcommands:
        _call_function(args._func, args)


def _populate_parser(func, parser):
    sig = inspect.signature(func)
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
        # TODO: determine and fill in type
        parser.add_argument(flag, default=default, nargs=nargs)
    return parser


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
