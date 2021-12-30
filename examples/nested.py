"""
Example showing nested parsers in defopt.

Code usage::

    >>> main(1.5)
    >>> sub1(2.0)
    >>> sub2(2.5)

Command line usage::

    $ python nested.py main 1.5
    $ python nested.py sub sub1 2.0
    $ python nested.py sub sub2 2.5
"""

import defopt


def main(number):
    """
    Example main function.

    :param float number: Number to print
    """
    print(number)


def sub1(number):
    """
    Example sub command.

    :param float number: Number to print
    """
    print(number)


def sub2(number):
    """
    Example sub command.

    :param float number: Number to print
    """
    print(number)


if __name__ == '__main__':
    defopt.run({'main': main, 'sub': [sub1, sub2]})
