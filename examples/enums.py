"""Example showing choices in defopt.

If a parameter's type is an Enum subclass, defopt automatically
turns this into a set of string choices on the command line.

Code usage:
    main(Choice.one, opt=Choice.two)

Command line usage:
    choices.py one --opt two
"""
from enum import Enum

import defopt


class Choice(Enum):
    one = 1
    two = 2.0
    three = '03'


@defopt.main
def main(arg, opt=None):
    """Test function with Enum arguments.

    :param arg: Enum member to display
    :type arg: Choice
    :param opt: Enum member to display
    :type opt: Choice
    """
    print('{} ({})'.format(arg, arg.value))
    if opt:
        print('{} ({})'.format(opt, opt.value))


if __name__ == '__main__':
    defopt.run()
