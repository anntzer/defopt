.. highlight:: none

Features
========

Types
-----

Argument types are read from the function's type hints (see
`examples/annotations.py`_) or docstring.  If type information for a parameter
is given both as type hint and in the docstring, the types must match.

.. code-block:: python

    def func(arg1: int, arg2: str):
        ...

Docstrings can use the standard Sphinx_-style

.. code-block:: rst

    :param <type> <name>: <description>

    .. or

    :param <name>: <description>
    :type <name>: <type>

    .. Any of ``param``, ``parameter``, ``arg``, ``argument``, ``key``, and
       ``keyword`` can be used interchangeably, as can ``type`` and
       ``kwtype``.  Consistency is recommended but not enforced.

or Google_- and Numpy_-style docstrings (see `examples/styles.py`_), which are
converted using Napoleon_ [#]_. If using one of these alternate styles and
generating documentation with `sphinx.ext.autodoc`, be sure to also enable
`sphinx.ext.napoleon`.

``<type>`` is evaluated in the function's global namespace when `defopt.run`
is called.

See `Standard types`_, Booleans_, Lists_, Choices_, Tuples_, Unions_, and
Parsers_ for more information on specific types.

.. [#] While Napoleon is included with Sphinx as `sphinx.ext.napoleon`, defopt
   depends on ``sphinxcontrib-napoleon`` so that end users of the command line
   tool are not required to install Sphinx and all of its dependencies.

Subcommands
-----------

If a list of commands are passed to `defopt.run`, they are treated as
subcommands which are run by name.

.. code-block:: python

    defopt.run([func1, func2])

The command line usage will indicate this. ::

    usage: test.py [-h] {func1,func2} ...

    positional arguments:
      {func1,func2}

Underscores in function names are replaced by hyphens.

Friendlier subcommand names can be provided by calling `defopt.run` with a dict
mapping subcommand names to functions.  In that case, no underscore replacement
occurs (as one can directly set names with hyphens).
￼
.. code-block:: python
￼
￼   defopt.run({"friendly_func": awkward_name, "func2": other_name})
￼
Command line usage will use the new names ::

    usage: test.py [-h] {friendly_func,func2} ...

    positional arguments:
      {friendly_func,func2}

Standard types
--------------

For parameters annotated as `str`, `int`, `float`, and `pathlib.Path`, the type
constructor is directly called on the argument passed in.

For parameters annotated as `slice`, the argument passed in is split at
``":"``, the resulting fragments evaluated with `ast.literal_eval` (with empty
fragments being converted to None), and the results passed to the `slice`
constructor.  For example, ``1::2`` results in ``slice(1, None, 2)``, which
corresponds to the normal indexing syntax.

Flags
-----

Python positional-or-keyword parameters are converted to CLI positional
arguments, with their name unmodified [#]_. Python keyword-only parameters are
converted to CLI flags, with underscores replaced by hyphens.  Additionally,
one-letter short flags are generated for all flags that do not share their
initial with other flags.

Optional Python parameters (i.e. with a default) are converted to optional CLI
arguments (regardless of whether the Python parameter is positional-or-keyword
or keyword-only); required Python parameters (i.e. with no default) are
converted to required CLI arguments. ::

    usage: test.py [-h] [-k KWONLY] positional_no_default [positional_with_default]

    positional arguments:
      positional_no_default
      positional_with_default

    optional arguments:
      -h, --help            show this help message and exit
      -k KWONLY, --kwonly KWONLY

Alternatively, one can make all optional Python parameters, regardless of
whether they are keyword-only or not, also map to CLI flags, by passing
``strict_kwonly=False`` to `defopt.run`.  (This behavior is similar to the
informal approach previously commonly found on Python 2, which was to consider
required parameters as positional and optional parameters as keyword.)

Auto-generated short flags can be overridden by passing a dictionary to
`defopt.run` which maps flag names to single letters:

.. code-block:: python

    defopt.run(main, short={'keyword-arg': 'a'})

Now, ``-a`` is exactly equivalent to ``--keyword-arg``::

      -a KEYWORD_ARG, --keyword-arg KEYWORD_ARG

A runnable example is available at `examples/short.py`_.

Passing an empty dictionary suppresses automatic short flag generation, without
adding new flags.

.. [#] As an exception, sequence parameters are always converted to flags, as
    described below.

Booleans
--------

Boolean keyword-only parameters (or, as above, parameters with defaults, if
``strict_kwonly=False``) are automatically converted to two separate flags:
``--name`` which stores `True` and ``--no-name`` which stores `False`.  The
help text and the default are displayed next to the ``--name`` flag::

    --flag      Set "flag" to True
                (default: False)
    --no-flag

Note that this does not apply to mandatory boolean parameters; these must be
specified as one of ``1/t/true`` or ``0/f/false`` (case insensitive).

If ``no_negated_flags=True`` is passed to `defopt.run`, no negated flags
(``--no-name``) are generated for boolean arguments that have `False`
as their default value.

A runnable example is available at `examples/booleans.py`_.

Lists
-----

Lists are automatically converted to flags (regardless of whether they are
positional-or-keyword, or keyword-only) which take zero or more arguments.

When declaring that a parameter is a list in a docstring, use the established
convention of putting the contained type inside square brackets. ::

    :param list[int] numbers: A sequence of numbers

`typing.List`, `typing.Sequence` and `typing.Iterable` are all treated in the
same way as `list`.

The list can now be specified on the command line using multiple arguments. ::

    test.py --numbers 1 2 3

A runnable example is available at `examples/lists.py`_.

Choices
-------

Subclasses of `enum.Enum` are handled specially on the command line to produce
more helpful output. ::

    positional arguments:
      {red,blue,yellow}  Your favorite color

This also produces a more helpful message when an invalid option is chosen. ::

    test.py: error: argument color: invalid choice: 'black'
                                    (choose from 'red', 'blue', 'yellow')

A runnable example is available at `examples/choices.py`_.

Likewise, `typing.Literal` and its backport ``typing_extensions.Literal`` are
also supported.

Tuples
------

Typed tuples and typed namedtuples (as defined using `typing.Tuple` and
`typing.NamedTuple`) consume as many command-line arguments as the tuple
has fields, convert each argument to the correct type, and wrap them into the
annotation class.  When a `typing.NamedTuple` is used for an optional argument,
the names of the fields are used in the help.

Unions
------

Union types can be specified with ``typing.Union[type1, type2]``, or, when
using docstring annotations, as ``type1 or type2``.  When an argument is
annotated with a union type, an attempt is made to convert the command-line
argument with the parser for each of the members of the union, in the order
they are given; the value returned by the first parser that does not raise a
`ValueError` is used.

``typing.Optional[type1]``, i.e. ``Union[type1, type(None)]``, is normally
equivalent to ``type1``.  This is implemented using a parser for ``type(None)``
that raises ``ValueError`` on all inputs, and can thus be overloaded by
setting a custom parser for ``type(None)``.

Collection types are not supported in unions; e.g. ``Union[List[type1]]``
is not supported (with the exception of ``Optional[List[type1]]``, which is
*always* equivalent to ``List[type1]``.

Parsers
-------

Arbitrary argument types can be used as long as functions to parse them from
strings are provided.

.. code-block:: python

    def parse_person(string):
        last, first = string.split(',')
        return Person(first.strip(), last.strip())

    defopt.run(..., parsers={Person: parse_person})

``Person`` objects can be now built directly from the command line. ::

    test.py --person "VAN ROSSUM, Guido"

A runnable example is available at `examples/parsers.py`_.

If the type of an annotation can be called with a single parameter and that
parameter is annotated as `str`, then `defopt` will assume that the type is
its own parser.

.. code-block:: python

    class StrWrapper:
        def __init__(self, s: str):
            self.s = s

    def main(s: StrWrapper):
        pass

    defopt.run(main)

``StrWrapper`` objects can now be built directly from the command line. ::

    test.py foo

Variable positional arguments
-----------------------------

If the function definition contains ``*args``, the parser will accept zero or
more positional arguments. When specifying a type, specify the type of the
elements, not the container.

.. code-block:: python

    def main(*numbers: int):
        """:param numbers: Positional numeric arguments"""

This will create a parser that accepts zero or more positional arguments which
are individually parsed as integers. They are passed as they would be from code
and received as a tuple. ::

    test.py 1 2 3

If the argument is a list type (see Lists_), this will instead create a flag
that can be specified multiple times, each time creating a new list.

Variable keyword arguments (``**kwargs``) are not supported.

A runnable example is available at `examples/starargs.py`_.

Private arguments
-----------------

Arguments whose name start with an underscore will not be added to the parser.

Exceptions
----------

Exception types can also be listed in the function's docstring, with ::

    :raises <type>: <description>

If the function call raises an exception whose type is mentioned in such a
``:raises:`` clause, the exception message is printed and the program exits
with status code 1, but the traceback is suppressed.

A runnable example is available at `examples/exceptions.py`_.

Additional parser features
--------------------------

Type information can be automatically added to the help text by passing
``show_types=True`` to `defopt.run`.  Defaults are displayed by default (sic),
but this can be turned off by passing ``show_defaults=False``.

By default, a ``--version`` flag will be added; the version string is
autodetected from the module where the function is defined (and the flag
is suppressed if the version detection fails).  Passing ``version="..."``
to `defopt.run` forces the version string, and passing ``version=False``
suppresses the flag.

Entry points
------------

To use a script as a console entry point with setuptools, one needs to create
a function that can be called without arguments.

.. code-block:: python

    def entry_point():
        defopt.run(main)

This entry point can now be referenced in the ``setup.py`` file.

.. code-block:: python

    setup(
        ...,
        entry_points={'console_scripts': ['name=test:entry_point']}
    )

Alternatively, arbitrary type-hinted functions can be directly run from the
command line with

.. code-block:: sh

    $ python -m defopt dotted.name args ...

which is equivalent to passing the ``dotted.name`` function to `defopt.run` and
calling the resulting script with ``args ...``.  This may be useful to make the
script importable independently of `defopt`.

.. _Sphinx: http://www.sphinx-doc.org/en/stable/domains.html#info-field-lists
.. _Google: http://google.github.io/styleguide/pyguide.html
.. _Numpy: https://github.com/numpy/numpy/blob/master/doc/HOWTO_DOCUMENT.rst.txt
.. _Napoleon: https://sphinxcontrib-napoleon.readthedocs.io/en/latest/
.. _examples/annotations.py: https://github.com/anntzer/defopt/blob/master/examples/annotations.py
.. _examples/booleans.py: https://github.com/anntzer/defopt/blob/master/examples/booleans.py
.. _examples/choices.py: https://github.com/anntzer/defopt/blob/master/examples/choices.py
.. _examples/exceptions.py: https://github.com/anntzer/defopt/blob/master/examples/exceptions.py
.. _examples/lists.py: https://github.com/anntzer/defopt/blob/master/examples/lists.py
.. _examples/parsers.py: https://github.com/anntzer/defopt/blob/master/examples/parsers.py
.. _examples/short.py: https://github.com/anntzer/defopt/blob/master/examples/short.py
.. _examples/starargs.py: https://github.com/anntzer/defopt/blob/master/examples/starargs.py
.. _examples/styles.py: https://github.com/anntzer/defopt/blob/master/examples/styles.py
