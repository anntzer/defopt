"""
Example showing short flags in defopt.

You can add alternative short flags to arguments by passing a
dictionary to `defopt.run` which maps flag names to single letters.

Code usage::

    >>> main(count=2)

Command line usage::

    $ python short.py -C 2
    $ python short.py --count 2
"""
import defopt


def main(*, count: int = 1):
    """
    Example function which prints a message.

    :param count: Number of times to print the message
    """
    for _ in range(count):
        print('hello!')


if __name__ == '__main__':
    defopt.run(main, short={'count': 'C'})
