"""Example showing parsers in defopt.

If a type is not simple enough for defopt to parse on its own,
you can explicitly specify parsers for types using decorators.

Code usage::

    >>> main(datetime(2015, 9, 13))

Command line usage::

    $ parsers.py 2015-09-13
"""
from datetime import datetime

import defopt


def main(date):
    """Example function with a `datetime.datetime` argument.

    :param datetime date: Date to display
    """
    print(date)


@defopt.parser(datetime)
def parse_date(string):
    """Parse a `datetime.datetime` using a simple string format.

    :param str string: String to parse
    :rtype: datetime
    """
    return datetime.strptime(string, '%Y-%m-%d')


if __name__ == '__main__':
    defopt.run(main)
