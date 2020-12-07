defopt
======

| |GitHub| |PyPI| |conda-forge|
| |Read the Docs| |Build|

.. |GitHub|
   image:: https://img.shields.io/badge/github-anntzer%2Fdefopt-brightgreen
   :target: `GitHub repository`_
.. |PyPI|
   image:: https://img.shields.io/pypi/v/defopt.svg?color=brightgreen
   :target: https://pypi.python.org/pypi/defopt
.. |conda-forge|
   image:: https://img.shields.io/conda/v/conda-forge/defopt.svg?label=conda-forge&color=brightgreen
   :target: https://anaconda.org/conda-forge/defopt
.. |Read the Docs|
   image:: https://img.shields.io/readthedocs/defopt
   :target: `Read the Docs`_
.. |Build|
   image:: https://img.shields.io/github/workflow/status/anntzer/defopt/build
   :target: https://github.com/anntzer/defopt/actions

defopt is a lightweight, no-effort argument parser.

defopt will:

- Allow functions to be run from code and the command line without modification.
- Reward you for documenting your functions.
- Save you from writing, testing and maintaining argument parsing code.

defopt will not:

- Modify your functions in any way.
- Allow you to build highly complex or customized command line tools.

If you want total control over how your command line looks or behaves, try
docopt_, click_ or argh_. If you just want to write Python code and leave the
command line interface up to someone else, defopt is for you.

Usage
-----

Once you have written and documented_ your function, simply pass it to
`defopt.run()` and you're done.

.. code-block:: python

    import defopt

    # Use type hints:
    def main(greeting: str, *, count: int = 1):
        """
        Display a friendly greeting.

        :param greeting: Greeting to display
        :param count: Number of times to display the greeting
        """
        for _ in range(count):
            print(greeting)

    # ... or document parameter types in the docstring:
    def main(greeting, *, count=1):
        """
        Display a friendly greeting.

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
    usage: test.py [-h] [-c COUNT] greeting

    Display a friendly greeting.

    positional arguments:
      greeting              Greeting to display

    optional arguments:
      -h, --help            show this help message and exit
      -c COUNT, --count COUNT
                            Number of times to display the greeting
                            (default: 1)

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

.. _GitHub repository: https://github.com/anntzer/defopt
.. _Read the Docs: https://defopt.readthedocs.io/en/latest/
.. _autodoc: http://www.sphinx-doc.org/en/stable/ext/autodoc.html
.. _docopt: http://docopt.org/
.. _click: http://click.palletsprojects.com/
.. _argh: https://argh.readthedocs.io/en/latest/
.. _documented: https://defopt.readthedocs.io/en/latest/features.html#docstring-styles

.. This document is included in docs/index.rst; table of contents appears here.
