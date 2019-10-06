"""
Example showing annotations in defopt.

Type hints specified in function annotations may be used
instead of writing types in docstrings.

``Iterable[x]``, ``Sequence[x]`` and ``List[x]`` are all treated
in the same way as ``list[x]`` in the docstring itself.
(See the lists example for more information.)

Code usage::

    >>> documented([1.2, 3.4], 2)

Command line usage::

    $ python annotations.py documented 2 --numbers 1.2 3.4
    $ python annotations.py documented --numbers 1.2 3.4 -- 2
"""
from typing import Iterable

import defopt


def documented(numbers: Iterable[float], exponent: int) -> None:
    """Example function using annotations.

    The types are inserted into the generated documentation
    by ``sphinx-autodoc-typehints``.

    :param numbers: Numbers to multiply
    :param exponent: Power to raise each element to
    """
    print([x ** exponent for x in numbers])


def undocumented(numbers: Iterable[float], exponent: int) -> None:
    print([x ** exponent for x in numbers])


if __name__ == '__main__':
    defopt.run([documented, undocumented])
