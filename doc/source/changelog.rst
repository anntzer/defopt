Changelog
=========

6.1.0 (2021-02-25)
------------------
* Boolean flags are now implemented using a variant of
  ``argparse.BooleanOptionalAction``.
* Added ``no_negated_flags``.
* A custom parser set for ``type(None)`` now affects parsing of
  `typing.Optional` too.

6.0.2 (2020-12-08)
------------------
* Don't get tripped by Attributes sections.
* Added support for Python 3.9.

6.0.1 (2020-09-18)
------------------
* Fixed support for container types defaulting to None.

6.0.0 (2020-05-11)
------------------
* Added support for Union and Literal types.
* Assume that types annotated as constructible from a single str are their own
  parser.
* Added support for catching exceptions.
* Added support for passing functions as a ``{name: function}`` mapping (Thanks
  to @johnfarina).
* Removed support for Python<=3.4.
* Disallowed ``parsers=None`` as a synonym for ``parsers={}``.
* Added `defopt.signature` to separate the signature-and-docstring parsing from
  the ArgumentParser construction.
* Fixed removal of comments from help string.
* Added support for ``--version``.
* Fixed displaying of defaults for parameters with no help, and added
  ``show_defaults``.
* Support varargs documented under ``*args`` instead of ``args``.
* Support standard Sphinx roles in the Python domain (``:py:func:``,
  ``:func:``, etc.); they are just stripped out.
* Arbitrary type-hinted functions can now by run with
  ``python -mdefopt dotted.name args ...``, as if ``dotted.name`` was passed
  to `defopt.run`.
* Support more RST constructs: doctest blocks, rubrics (used by Napoleon for
  sectioning).

5.1.0 (2019-03-01)
------------------
* Added ``argparse_kwargs``.
* Fixed short flag generation to avoid collision with ``-h``.

5.0.0 (2018-10-18)
------------------
* Added default parser for `slice`.
* Removed support for passing multiple functions positionally.
* Added support for Python 3.7.
* Removed support for Python 3.3.

4.0.1 (2017-11-26)
------------------
* Fixed crash when handing a NamedTuple followed by other arguments

4.0.0 (2017-11-07)
------------------
* Changed parser generation to only make flags from keyword-only arguments,
  treating arguments with defaults as optional positionals
* Changed subparser generation to replace dashes in names with underscores
* Added support for RST lists
* Added support for typed Tuple and NamedTuple arguments
* Added __all__
* Ignored arguments whose names start with underscores

3.2.0 (2017-05-30)
------------------

* Added ``show_types`` option to automatically display variable types
  (Thanks to @anntzer)
* Added default parser for `pathlib.Path` when it is available
  (Thanks to @anntzer)
* Added annotations example to the generated documentation

3.1.1 (2017-04-12)
------------------

* Fixed environment markers in wheels

3.1.0 (2017-04-12)
------------------

Thanks to @anntzer for contributing the features in this release.

* Changed `defopt.run` to take multiple functions as a single list
* Deprecated passing multiple functions positionally
* Added subcommand summaries to the help message for multiple functions
* Added automatic short flags where they are unambiguous
* Added rendering of italic, bold and underlined text from docstrings
* Added Python 3.6 classifier to setup.py
* Dropped nose as a test runner

3.0.0 (2016-12-16)
------------------

* Added support for Python 3.6
* Changed keyword-only arguments without defaults to required flags
* Added support for all variants of ``param`` and ``type``
* Added support for list-typed variable positional arguments
* Fixed help message formatting to avoid argparse's string interpolation
* Added __version__ attribute

2.0.1 (2016-09-13)
------------------

* Fixed handling of generic types in Python 3.5.2 (and typing 3.5.2)

2.0.0 (2016-05-10)
------------------

* Added ability to specify short flags
* Added automatic ``--name`` and ``--no-name`` flags for optional booleans
* Added automatic translation of underscores to hyphens in all flags
* Removed ``defopt.parser``

1.3.0 (2016-03-21)
------------------

* Added ``parsers`` argument to `defopt.run`
* Deprecated ``defopt.parser``

1.2.0 (2016-02-25)
------------------

* Added support for type annotations
* Added parameter defaults to help text
* Removed default line wrapping of help text
* Added '1' and '0' as accepted values for True and False respectively

1.1.0 (2016-02-21)
------------------

* Added support for Google- and Numpy-style docstrings
* Changed `defopt.run` to return the value from the called function

1.0.1 (2016-02-14)
------------------

* Added workaround to display raw text of any unparsed element (issue #1)

1.0.0 (2016-02-14)
------------------

* Removed decorator interface and added simpler `defopt.run` interface
* Added full documentation hosted on Read the Docs
* Added more informative exceptions for type lookup failures
* Fixed bug where ``defopt.parser`` was not returning the input function
* Fixed type lookups to occur in each respective function's global namespace
* Fixed bug where subcommands did not properly parse Enums
* Fixed Enum handling to display members in the order they were defined

0.3.1 (2016-02-10)
------------------

* Added support for docstrings that only contain parameter information
* Added more informative exceptions for insufficiently documented functions
* Fixed type parsing bug on Python 2 when future is installed
* Switched to building universal wheels

0.3.0 (2016-02-10)
------------------

* Added support for Python 2.7
* Fixed code that was polluting the logging module's root logger

0.2.0 (2016-02-09)
------------------

* Added support for combined parameter type and description definitions
* Fixed crashing bug when an optional Enum-typed flag wasn't specified

0.1.0 (2016-02-08)
------------------

* Initial version
