"""Example showing choices in defopt.

If a parameter's type is a subclass of `enum.Enum` or a `typing.Literal` (or
its backport ``typing_extensions.Literal``), defopt automatically turns this
into a set of string choices on the command line.

Code usage::

    >>> choose_enum(Choice.one, opt=Choice.two)

Command line usage::

    $ python choices.py one --opt two
"""

from enum import Enum
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

import defopt


class Choice(Enum):
    one = 1
    two = 2.0
    three = '03'


def choose_enum(arg, *, opt=None):
    """Example function with `enum.Enum` arguments.

    :param Choice arg: Choice to display
    :param Choice opt: Optional choice to display
    """
    print('{} ({})'.format(arg, arg.value))
    if opt:
        print('{} ({})'.format(opt, opt.value))


def choose_literal(arg, *, opt=None):
    """Example function with `enum.Enum` arguments.

    :param Literal["foo","bar"] arg: Choice to display
    :param Literal["baz","quu"] opt: Optional choice to display
    """
    print(arg)
    if opt:
        print(opt)


if __name__ == '__main__':
    defopt.run([choose_enum, choose_literal])
