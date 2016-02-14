Features
========

Types
-----

Argument types are read from your function's docstring. Both
``param`` and ``type`` are supported.

::

    :param <type> <name>: <description>

::

    :param <name>: <description>
    :type <name>: <type>

``<type>`` is evaluated in the function's global namespace when `defopt.run` is
called. See Lists_, Choices_ and Parsers_ for more information on specific
types.

Subcommands
-----------

If multiple commands are passed to `defopt.run`, they are treated as
subcommands which are run by name.

::

    defopt.run(func1, func2)

The command line usage will indicate this.

::

    usage: test.py [-h] {func1,func2} ...

    positional arguments:
      {func1,func2}

Lists
-----

Lists are automatically converted to flags which take zero or more arguments.
If the argument is positional, the flag is marked as required.

When declaring that a parameter is a list, use the established convention of
putting the contained type inside square brackets.

::

    :param list[int] numbers: A sequence of numbers

You can now specify your list on the command line using multiple arguments.

::

    test.py --numbers 1 2 3

A runnable example is available at `examples/lists.py`_.

Choices
-------

If one of your argument types is a subclass of `enum.Enum` [1]_, this is
handled specially on the command line to produce more helpful output.

::

    positional arguments:
      {red,blue,yellow}  Your favorite color

This also produces a more helpful message when you choose an invalid option.

::

    test.py: error: argument color: invalid choice: 'black'
                                    (choose from 'red', 'blue', 'yellow')

A runnable example is available at `examples/choices.py`_.

Parsers
-------

You can use arbitrary argument types as long as you provide functions to parse
them from strings.

::

    @defopt.parser(Person)
    def parse_person(string):
        last, first = string.split(',')
        return Person(first.strip(), last.strip())

You can now build ``Person`` objects directly from the command line.

::

    test.py --person "VAN ROSSUM, Guido"

A runnable example is available at `examples/parsers.py`_.

Variable Positional Arguments
-----------------------------

If your function definition contains ``*args``, the parser will accept zero or
more positional arguments. When specifying a type, specify the type of the
elements, not the container.

::

    def main(*numbers):
        """:param int numbers: Positional numeric arguments"""

This will create a parser that accepts zero or more positional arguments which
are individually parsed as integers. They are passed as they would be from code
and received as a tuple.

::

    test.py 1 2 3

Variable keyword arguments (``**kwargs``) are not supported.

Entry Points
------------

To use your script as a console entry point with setuptools, you need to create
a function that can be called without arguments.

::

    def entry_point():
        defopt.run(main)

You can then reference this entry point in your ``setup.py`` file.

::

    setup(
        ...,
        entry_points={'console_scripts': ['name=test:entry_point']}
    )

.. _examples/lists.py: https://github.com/evanunderscore/defopt/blob/master/examples/lists.py
.. _examples/choices.py: https://github.com/evanunderscore/defopt/blob/master/examples/choices.py
.. _examples/parsers.py: https://github.com/evanunderscore/defopt/blob/master/examples/parsers.py

.. [1] The ``enum`` module was introduced in Python 3.4. If you are using an
   older version of Python, the backport will be installed as a dependency.
