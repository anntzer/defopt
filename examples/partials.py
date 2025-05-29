"""
Example showing using partial function applications in defopt.

`functools.partial` objects may be used to wrap a function specifying a default
for a required parameter, or to change the default for a parameter.

Code usage::

    >>> partial(foo, arg=5)()
    5
    >>> bar()
    1
    >>> partial(bar, arg=6)()
    6

Command line usage::

    $ python partials.py foo
      5
    $ python partials.py sub bar
      6
"""

import defopt
from functools import partial


def foo(*, arg: int) -> None:
    print(arg)


def bar(*, arg: int = 1) -> None:
    print(arg)


if __name__ == '__main__':
    defopt.run({"foo": partial(foo, arg=5), "sub": [partial(bar, arg=6)]})
