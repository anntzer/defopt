Changelog
=========

development
-----------

* Removed decorator interface and added simpler ``defopt.run`` interface
* Added full documentation hosted on Read the Docs
* Added more informative exceptions for type lookup failures
* Fixed bug where ``defopt.parser()`` was not returning the input function
* Fixed bug where subcommands did not properly parse Enums
* Fixed Enum handling to display members in the order they were defined
* Fixed type lookups to occur in each respective function's global namespace

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
