Changelog
=========

3.0.0 (develop)
---------------

* Changed keyword-only arguments without defaults to required flags
* Added support for all variants of ``param`` and ``type``

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

* Added ``parsers`` argument to ``defopt.run``
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
* Changed ``defopt.run`` to return the value from the called function

1.0.1 (2016-02-14)
------------------

* Added workaround to display raw text of any unparsed element (issue #1)

1.0.0 (2016-02-14)
------------------

* Removed decorator interface and added simpler ``defopt.run`` interface
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
