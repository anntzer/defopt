"""
Example showing supported docstring styles in defopt.

You need to enable the `sphinx.ext.napoleon` extension
to generate documentation for this module.

Code usage::

    >>> sphinx(2, farewell='goodbye!')

Command line usage::

    $ python styles.py sphinx 2 --farewell goodbye!
"""
import defopt


def sphinx(integer, *, farewell=None):
    """
    Example function with a Sphinx-style docstring.

    Squares a given integer.

    .. This is a comment; it won't show up anywhere but here.
       Below is a literal block which will be displayed with a
       4-space indent in the help string and as a code block
       in the documentation.

    ::

        $ python styles.py sphinx 2 --farewell goodbye!
        4
        goodbye!


    :param int integer: Number to square
    :keyword str farewell: Parting message
    """
    print(integer ** 2)
    if farewell is not None:
        print(farewell)


def google(integer, *, farewell=None):
    """
    Example function with a Google-style docstring.

    Squares a given integer.

    .. This is a comment; it won't show up anywhere but here.
       Below is a literal block which will be displayed with a
       4-space indent in the help string and as a code block
       in the documentation.

    ::

        $ python styles.py google 2 --farewell goodbye!
        4
        goodbye!

    Args:
      integer(int): Number to square

    Keyword Arguments:
      farewell(str): Parting message
    """
    print(integer ** 2)
    if farewell is not None:
        print(farewell)


def numpy(integer, *, farewell=None):
    """
    Example function with a Numpy-style docstring.

    Squares a given integer.

    .. This is a comment; it won't show up anywhere but here.
       Below is a literal block which will be displayed with a
       4-space indent in the help string and as a code block
       in the documentation.

    ::

        $ python styles.py numpy 2 --farewell goodbye!
        4
        goodbye!

    Parameters
    ----------
    integer : int
        Number to square

    Keyword Arguments
    -----------------
    farewell : str
        Parting message
    """
    print(integer ** 2)
    if farewell is not None:
        print(farewell)


if __name__ == '__main__':
    defopt.run([sphinx, google, numpy])
