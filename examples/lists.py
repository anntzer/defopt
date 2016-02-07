"""Example showing lists in defopt.

Lists are automatically converted to required flags
which accept zero or more arguments.

Code usage:
    main([1.2, 3.4], 2)

Command line usage:
    lists.py 2 --numbers 1.2 3.4
    lists.py --numbers 1.2 3.4 -- 2
"""
import defopt


@defopt.main
def main(numbers, multiplier):
    """Example function with a list argument.

    :param numbers: List of numbers to multiply
    :type numbers: list[float]
    :param multiplier: Amount to multiply by
    :type multiplier: float
    """
    print([x * multiplier for x in numbers])


if __name__ == '__main__':
    defopt.run()
