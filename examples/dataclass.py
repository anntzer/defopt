"""
Example showing dataclass as parameters.

Dataclasses are always considered keyword-only, and are not supported in
containers or unions.
"""

from dataclasses import dataclass
from typing import Optional

import defopt


@dataclass
class Sub:
    c: int
    d: Optional[float] = None


@dataclass
class Data:
    a: str
    b: Sub


def main(arg):
    """
    :param Data arg: The arg.
    """
    print(arg)


if __name__ == "__main__":
    defopt.run(main)
