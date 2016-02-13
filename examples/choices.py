"""Example showing choices in defopt.

If a parameter's type is an Enum subclass, defopt automatically
turns this into a set of string choices on the command line.

Code usage::

    >>> main(Choice.one, opt=Choice.two)

Command line usage::

    $ choices.py one --opt two
"""
from enum import Enum

import defopt


def main(arg, opt=None):
    """Example function with :py:class:`enum.Enum` arguments.

    :param Choice arg: Choice to display
    :param Choice opt: Optional choice to display
    """
    print('{} ({})'.format(arg, arg.value))
    if opt:
        print('{} ({})'.format(opt, opt.value))


class Choice(Enum):
    one = 1
    two = 2.0
    three = '03'


if __name__ == '__main__':
    defopt.run(main)
