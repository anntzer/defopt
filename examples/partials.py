"""
Example showing using partial functions in defopt.

A partial function (using `functools.partial`) may be used to
wrap a function specifying a default for a requirement argument,
or to change the default for an argument.

Code usage::

    >>> partial(foo, bar=5)()
    5
    5
    >>> foo2()
    1
    1
    >>> partial(foo2, bar=6)()
    6
    6

Command line usage::

    $ python partials.py foo
      5
    $ python partials.py sub foo2
      6
"""
import defopt
from functools import partial

def foo(*, bar: int) -> None:
    print(bar)
    return bar

def foo2(*, bar: int = 1) -> None:
    print(bar)
    return bar

if __name__ == '__main__':
    defopt.run({"foo": partial(foo, bar=5), "sub": [partial(foo2, bar=6)]})
