"""Example showing boolean flags in defopt.

Optional boolean parameters are automatically converted to
``--name`` and ``--no-name`` flags which take no arguments
and store `True` and `False` respectively.

Code usage::

    >>> main('hello!', upper=False, repeat=True)

Command line usage::

    $ python booleans.py 'hello!' --no-upper --repeat
"""
import defopt


def main(message, upper=True, repeat=False):
    """Example function with boolean flags.

    :param str message: Message to display
    :param bool upper: Display the message in upper case
    :param bool repeat: Display the message twice
    """
    if upper:
        message = message.upper()
    for _ in range(1 + repeat):
        print(message)


if __name__ == '__main__':
    defopt.run(main, strict_kwonly=False)
