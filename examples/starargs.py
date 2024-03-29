"""
Example showing ``*args`` handling in defopt.

Variable positional arguments can be specified any number of times
and are received as a tuple.

Flags generated by list types (or equivalents) create a new list
each time they are used.

Code usage::

    >>> plain(1, 2, 3)
    >>> iterable([1, 2], [3, 4, 5])

Command line usage::

    $ python starargs.py plain 1 2 3
    $ python starargs.py iterable --groups 1 2 --groups 3 4 5
"""

import defopt


def plain(*numbers):
    """
    Example function which accepts multiple positional arguments.

    The arguments are plain integers.

    :param int numbers: Numbers to display
    """
    for number in numbers:
        print(number)


def iterable(*groups):
    """
    Example function which accepts multiple positional arguments.

    The arguments are lists of integers.

    :param list[int] groups: Lists of numbers to display
    """
    for group in groups:
        print(group)


if __name__ == '__main__':
    defopt.run([plain, iterable])
