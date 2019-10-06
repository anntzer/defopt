"""
Example showing lists in defopt.

Lists are automatically converted to required flags
which accept zero or more arguments.

Code usage::

    >>> main([1.2, 3.4], 2)

Command line usage::

    $ python lists.py 2 --numbers 1.2 3.4
    $ python lists.py --numbers 1.2 3.4 -- 2
"""
import defopt


def main(numbers, multiplier):
    """
    Example function with a list argument.

    :param list[float] numbers: Numbers to multiply
    :param float multiplier: Amount to multiply by
    """
    print([x * multiplier for x in numbers])


if __name__ == '__main__':
    defopt.run(main)
