defopt
======

defopt is a lightweight, no-effort argument parser.

defopt will:

- Allow functions to be run from code and the command line without modification
- Reward you for documenting your functions
- Save you from writing, testing and maintaining argument parsing code

defopt will not:

- Modify your functions in any way
- Allow you to build highly complex or customized command line tools

If you want total control over how your command line looks or behaves, try
docopt_, click_ or argh_. If you just want to write Python code and leave the
command line interface up to someone else, defopt is for you.

Usage
-----

Once you have written and documented_ your function, simply pass it to
`defopt.run()` and you're done.

::

    import defopt

    def main(greeting, count=1):
        """Display a friendly greeting.

        :param str greeting: Greeting to display
        :param int count: Number of times to display the greeting
        """
        for _ in range(count):
            print(greeting)

    if __name__ == '__main__':
        defopt.run(main)

Descriptions of the parameters and the function itself are used to build an
informative help message.

::

    $ python test.py -h
    usage: test.py [-h] [--count COUNT] greeting

    Display a friendly greeting.

    positional arguments:
      greeting       Greeting to display

    optional arguments:
      -h, --help     show this help message and exit
      --count COUNT  Number of times to display the greeting (default: 1)

Your function can now be called identically from Python and the command line.

::

    >>> from test import main
    >>> main('hello!', count=2)
    hello!
    hello!

::

    $ python test.py hello! --count 2
    hello!
    hello!

Philosopy
---------

defopt was developed with the following guiding principles in mind:

#. **The interface can be fully understood in seconds.** If it took any longer,
   your time would be better spent learning a more flexible tool.

#. **Anything you learn applies to the existing ecosystem.** The exact same
   docstrings used by defopt are also used by Sphinx's autodoc_ extension to
   generate documentation, and by your IDE to do type checking. Chances are you
   already know everything you need to know to use defopt.

#. **Everything is handled for you.** If you're using defopt, it's because you
   don't want to write any argument parsing code *at all*. You can trust it to
   build a logically consistent command line interface to your functions
   with no configuration required.

#. **Your Python functions are never modified.** Type conversions are only ever
   applied to data originating from the command line. When used in code,
   duck-typing still works exactly as you expect with no surprises.

Development
-----------

For source code, examples, questions, feature requests and bug reports, visit
the `GitHub repository`_.

Documentation
-------------

Documentation is hosted on `Read the Docs`_.

.. _autodoc: http://www.sphinx-doc.org/en/stable/ext/autodoc.html
.. _docopt: http://docopt.org/
.. _click: http://click.pocoo.org/
.. _argh: http://argh.readthedocs.io/en/latest/
.. _documented: http://defopt.readthedocs.io/en/latest/features.html#docstring-styles
.. _GitHub repository: https://github.com/evanunderscore/defopt
.. _Read the Docs: http://defopt.readthedocs.io/en/latest/

.. This document is included in docs/index.rst; table of contents appears here.
