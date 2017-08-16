Features
========

Docstring Styles
----------------

In addition to the standard Sphinx_-style, you can also use Google_- and
Numpy_-style docstrings. These are converted using Napoleon_ [#]_. If you are
using one of these alternate styles and generating documentation with
`sphinx.ext.autodoc`, be sure to also enable `sphinx.ext.napoleon`.

A runnable example is available at `examples/styles.py`_.

Types
-----

Argument types are read from your function's docstring. Both
``param`` and ``type`` (and their variants [#]_) are supported. ::

    :param <type> <name>: <description>

::

    :param <name>: <description>
    :type <name>: <type>

``<type>`` is evaluated in the function's global namespace when `defopt.run`
is called. See Booleans_, Lists_, Choices_, Tuples_ and Parsers_ for more
information on specific types.

Type information can be automatically added to the help text by passing
``show_types=True`` to `defopt.run`.

Subcommands
-----------

If a list of commands are passed to `defopt.run`, they are treated as
subcommands which are run by name. ::

    defopt.run([func1, func2])

The command line usage will indicate this. ::

    usage: test.py [-h] {func1,func2} ...

    positional arguments:
      {func1,func2}

Flags
-----

Python positional-or-keyword parameters are converted to CLI positional
parameters, with their name unmodified.  Python keyword-only parameters are
converted to CLI flags, with underscores replaced by hyphens.  Additionally,
one-letter short flags are generated for all flags that do not share their
initial with other flags.

Parameters that have a default (regardless of whether they are
positional-or-keyword or keyword-only) are optional; those that do not have a
default are required.

    usage: test.py [-h] [-k KWONLY] positional_no_default [positional_with_default]

    positional arguments:
      positional_no_default
      positional_with_default

    optional arguments:
      -h, --help            show this help message and exit
      -k KWONLY, --kwonly KWONLY

Python 2 does not have keyword-only parameters; the standard way to
suggest that a parameter should be used with its keyword is to use a
positional-or-keyword parameter with a default.  It is possible (on both Python
2 and Python 3) to use this interpretation (Python parameters with a default
become CLI flags, and keyword-only ones do too; others become CLI positional
parameters) by passing ``strick_kwonly=False`` to `defopt.run`.

Auto-generated short flags can be overridden by passing a dictionary to
`defopt.run` which maps flag names to single letters::

    defopt.run(main, short={'keyword-arg': 'a'})

Now, ``-a`` is exactly equivalent to ``--keyword-arg``::

      -a KEYWORD_ARG, --keyword-arg KEYWORD_ARG

A runnable example is available at `examples/short.py`_.

Passing an empty dictionary suppresses automatic short flag generation, without
adding new flags.

Booleans
--------

Boolean keyword-only parameters are automatically converted to two separate
flags: ``--name`` which stores `True` and ``--no-name`` which stores
`False`. Your help text and the default will be displayed next to the
``--name`` flag::

    --flag      Set "flag" to True
                (default: False)
    --no-flag

Note that this does not apply to mandatory boolean parameters; these must be
specified as one of ``1/t/true`` or ``0/f/false`` (case insensitive).

A runnable example is available at `examples/booleans.py`_.

If ``strict_kwonly`` is unset, then all boolean parameters with a default or
that are keyword-only are converted in such a way.

Lists
-----

Lists are automatically converted to flags which take zero or more arguments.
If the argument is positional, the flag is marked as required.

When declaring that a parameter is a list, use the established convention of
putting the contained type inside square brackets. ::

    :param list[int] numbers: A sequence of numbers

You can now specify your list on the command line using multiple arguments. ::

    test.py --numbers 1 2 3

A runnable example is available at `examples/lists.py`_.

Choices
-------

If one of your argument types is a subclass of `enum.Enum` [#]_, this is
handled specially on the command line to produce more helpful output. ::

    positional arguments:
      {red,blue,yellow}  Your favorite color

This also produces a more helpful message when you choose an invalid option. ::

    test.py: error: argument color: invalid choice: 'black'
                                    (choose from 'red', 'blue', 'yellow')

A runnable example is available at `examples/choices.py`_.

Tuples
------

Typed tuples and typed namedtuples (as defined using `typing.Tuple` and
`typing.NamedTuple`) consume as many command-line arguments as the tuple
has fields, convert each argument to the correct type, and wrap them into the
annotation class.  When a `typing.NamedTuple` is used for an optional argument,
the names of the fields are used in the help.

Parsers
-------

You can use arbitrary argument types as long as you provide functions to parse
them from strings. ::

    def parse_person(string):
        last, first = string.split(',')
        return Person(first.strip(), last.strip())

    defopt.run(..., parsers={Person: parse_person})

You can now build ``Person`` objects directly from the command line. ::

    test.py --person "VAN ROSSUM, Guido"

A runnable example is available at `examples/parsers.py`_.

Variable Positional Arguments
-----------------------------

If your function definition contains ``*args``, the parser will accept zero or
more positional arguments. When specifying a type, specify the type of the
elements, not the container. ::

    def main(*numbers):
        """:param int numbers: Positional numeric arguments"""

This will create a parser that accepts zero or more positional arguments which
are individually parsed as integers. They are passed as they would be from code
and received as a tuple. ::

    test.py 1 2 3

If the argument is a list type (see Lists_ and Annotations_), this will instead
create a flag that can be specified multiple times, each time creating a new
list.

Variable keyword arguments (``**kwargs``) are not supported.

A runnable example is available at `examples/starargs.py`_.

Private Arguments
-----------------

Arguments whose name start with an underscore will not be added to the parser.

Entry Points
------------

To use your script as a console entry point with setuptools, you need to create
a function that can be called without arguments. ::

    def entry_point():
        defopt.run(main)

You can then reference this entry point in your ``setup.py`` file. ::

    setup(
        ...,
        entry_points={'console_scripts': ['name=test:entry_point']}
    )

Annotations
-----------

Python 3 introduced function annotations, and `PEP 0484`_ standardized their
use for type hints.

When passed to `defopt.run`, any function annotations are assumed to be type
hints. `~typing.List`, `~typing.Sequence` and `~typing.Iterable` from the
`typing` module [#]_ are all treated in the same way as `list` (see Lists_). ::

    from typing import Iterable
    def func(arg1: int, arg2: Iterable[float]):
        """No further type information required."""

You may mix annotations with types in your docstring, but if type information
for a parameter is given in both, they must be the same.

A runnable example is available at `examples/annotations.py`_.

.. _Sphinx: http://www.sphinx-doc.org/en/stable/domains.html#info-field-lists
.. _Google: http://google.github.io/styleguide/pyguide.html
.. _Numpy: https://github.com/numpy/numpy/blob/master/doc/HOWTO_DOCUMENT.rst.txt
.. _Napoleon: https://sphinxcontrib-napoleon.readthedocs.io/en/latest/
.. _PEP 0484: https://www.python.org/dev/peps/pep-0484/
.. _examples/styles.py: https://github.com/evanunderscore/defopt/blob/master/examples/styles.py
.. _examples/short.py: https://github.com/evanunderscore/defopt/blob/master/examples/short.py
.. _examples/booleans.py: https://github.com/evanunderscore/defopt/blob/master/examples/booleans.py
.. _examples/lists.py: https://github.com/evanunderscore/defopt/blob/master/examples/lists.py
.. _examples/choices.py: https://github.com/evanunderscore/defopt/blob/master/examples/choices.py
.. _examples/parsers.py: https://github.com/evanunderscore/defopt/blob/master/examples/parsers.py
.. _examples/starargs.py: https://github.com/evanunderscore/defopt/blob/master/examples/starargs.py
.. _examples/annotations.py: https://github.com/evanunderscore/defopt/blob/master/examples/annotations.py

.. [#] While Napoleon is included with Sphinx as `sphinx.ext.napoleon`, defopt
   depends on ``sphinxcontrib-napoleon`` so that end users of your command line
   tool are not required to install Sphinx and all of its dependencies.
.. [#] Any of ``param``, ``parameter``, ``arg``, ``argument``, ``key``, and
    ``keyword`` can be used interchangeably, as can ``type`` and ``kwtype``.
    Consistency is recommended but not enforced.
.. [#] `enum` was introduced in Python 3.4. If you are using an older version
   of Python, the backport will be installed as a dependency.
.. [#] `typing` was introduced in Python 3.5. If you are using an older version
   of Python, the backport will be installed as a dependency.
