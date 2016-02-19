"""Example showing supported docstring styles in defopt.

You need to enable the `sphinx.ext.napoleon` extension
to generate documentation for this module.

Code usage::

    >>> sphinx(2, farewell='goodbye!')

Command line usage::

    $ styles.py sphinx 2 --farewell goodbye!
"""
import defopt


def sphinx(integer, farewell=None):
    """Example function with a Sphinx-style docstring.

    Squares a given integer.

    :param int integer: Number to square
    :param str farewell: Parting message
    """
    print(integer ** 2)
    if farewell is not None:
        print(farewell)


def google(integer, farewell=None):
    """Example function with a Google-style docstring.

    Squares a given integer.

    Args:
      integer(int): Number to square
      farewell(str): Parting message
    """
    print(integer ** 2)
    if farewell is not None:
        print(farewell)


def numpy(integer, farewell=None):
    """Example function with a Numpy-style docstring.

    Squares a given integer.

    Parameters
    ----------
    integer : int
        Number to square
    farewell : str
        Parting message
    """
    print(integer ** 2)
    if farewell is not None:
        print(farewell)


if __name__ == '__main__':
    defopt.run(sphinx, google, numpy)
