"""Example showing parsers in defopt.

If a type is not simple enough for defopt to parse on its own,
you can explicitly specify parsers for types using decorators.

Code usage:
    main(datetime(2015, 9, 13))

Command line usage:
    parsers.py 2015-09-13
"""
from datetime import datetime

import defopt


@defopt.parser(datetime)
def parse_date(string):
    return datetime.strptime(string, '%Y-%m-%d')


@defopt.main
def main(date):
    """Example function with datetime argument.

    :param datetime date: Date to display
    """
    print(date)


if __name__ == '__main__':
    defopt.run()
