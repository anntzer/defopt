import ast
import collections.abc
import contextlib
import functools
import pydoc
import sys
from argparse import REMAINDER, ArgumentParser

from . import run


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


if __package__ is not None:
    sys.argv[0] = __package__
main()
