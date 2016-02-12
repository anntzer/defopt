======
defopt
======

defopt allows you to effortlessly call Python functions from the command line.

defopt will:

- Allow functions to be called identically from code or the command line
- Reward you for documenting your functions
- Produce informative command line help messages
- Save you from writing and maintaining argument parsing code ever again

defopt will not:

- Modify your functions in any way
- Allow you to build complex command line tools (try docopt_ or click_)

Usage
-----

Once you have written and documented your main function (currently you must use
Sphinx-style_ docstrings), simply decorate it with ``@defopt.main``, then call
``defopt.run()`` to see the magic happen.

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

This function can now be called identically from Python and the command line.

::

    >>> from test import main
    >>> main('hello!', count=2)
    hello!
    hello!

::

    $ python test.py hello! --count 2
    hello!
    hello!

Development
-----------

For source code, examples, questions, feature requests and bug reports, visit
the `GitHub repository`_.

.. _Sphinx-style: http://www.sphinx-doc.org/en/stable/domains.html#info-field-lists
.. _docopt: http://docopt.org/
.. _click: http://click.pocoo.org/
.. _GitHub repository: https://github.com/evanunderscore/defopt
