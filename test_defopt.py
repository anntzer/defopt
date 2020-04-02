import builtins
import contextlib
import inspect
import re
import subprocess
import sys
import typing
import unittest
from contextlib import ExitStack
from enum import Enum
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

import defopt
from defopt import __version__
from examples import (
    annotations, booleans, choices, exceptions, lists, parsers, short,
    starargs, styles)


Choice = Enum('Choice', [('one', 1), ('two', 2), ('%', 0.01)])
Pair = typing.NamedTuple('Pair', [('first', int), ('second', str)])


class ConstructibleFromStr:
    def __init__(self, s):
        """:type s: str"""
        self.s = s


class NotConstructibleFromStr:
    def __init__(self, s):
        pass


class TestDefopt(unittest.TestCase):
    def test_main(self):
        def main(foo):
            """:type foo: str"""
            return foo
        self.assertEqual(defopt.run(main, argv=['foo']), 'foo')

    def test_subcommands(self):
        def sub(*bar):
            """:type bar: float"""
            return bar
        def sub_with_dash(*, baz=None):
            """:type baz: int"""
            return baz
        self.assertEqual(
            defopt.run([sub, sub_with_dash], argv=['sub', '1.1']), (1.1,))
        self.assertEqual(
            defopt.run([sub, sub_with_dash],
                       argv=['sub-with-dash', '--baz', '1']), 1)
        self.assertEqual(
            defopt.run({"sub1": sub, "sub_2": sub_with_dash},
                       argv=['sub1', '1.2']), (1.2,))
        self.assertEqual(
            defopt.run({"sub1": sub, "sub_2": sub_with_dash},
                       argv=['sub_2', '--baz', '1']), 1)

    def test_var_positional(self):
        for doc in [
                ":type foo: int", r":type \*foo: int", ":param int foo: doc"]:
            def main(*foo): return foo
            main.__doc__ = doc
            self.assertEqual(defopt.run(main, argv=['1', '2']), (1, 2))
            self.assertEqual(defopt.run(main, argv=[]), ())

    def test_no_default(self):
        def main(a):
            """:type a: str"""
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=[])

    def test_keyword_only(self):
        def main(foo='bar', *, baz='quux'):
            """
            :type foo: str
            :type baz: str
            """
            return foo, baz
        self.assertEqual(defopt.run(main, argv=['FOO', '--baz', 'BAZ']),
                         ('FOO', 'BAZ'))
        self.assertEqual(defopt.run(main, argv=[]), ('bar', 'quux'))

    def test_keyword_only_no_default(self):
        def main(*, foo):
            """:type foo: str"""
            return foo
        self.assertEqual(defopt.run(main, argv=['--foo', 'baz']), 'baz')
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=[])

    def test_var_keywords(self):
        def bad(**kwargs):
            """:type kwargs: str"""

        with self.assertRaises(ValueError):
            defopt.run(bad)

    def test_bad_arg(self):
        with self.assertRaises(TypeError):
            defopt.run(foo=None)

    def test_no_subparser_specified(self):
        def sub1(): assert False
        def sub2(): assert False
        with self.assertRaises(SystemExit):
            defopt.run([sub1, sub2], argv=[])

    def test_no_param_doc(self):
        def bad(foo):
            """Test function"""
        with self.assertRaisesRegex(ValueError, 'type.*foo'):
            defopt.run(bad, argv=['foo'])

    def test_no_type_doc(self):
        def bad(foo):
            """:param foo: no type info"""
        with self.assertRaisesRegex(ValueError, 'type.*foo'):
            defopt.run(bad, argv=['foo'])

    def test_return(self):
        def one(): return 1
        def none(): pass
        self.assertEqual(defopt.run([one, none], argv=['one']), 1)
        self.assertEqual(defopt.run([one, none], argv=['none']), None)

    def test_underscores(self):
        def main(a_b_c, *, d_e_f=None):
            """Test function

            :type a_b_c: int
            :type d_e_f: int
            """
            return a_b_c, d_e_f
        self.assertEqual(defopt.run(main, argv=['1', '--d-e-f', '2']), (1, 2))

    def test_private_with_default(self):
        def main(_a=None): pass
        defopt.run(main, argv=[])

    def test_private_without_default(self):
        def main(_a: int): assert False
        with self.assertRaisesRegex(ValueError,
                                    # Older Pythons have no space post-colon.
                                    r'Parameter _a of main\(_a: ?int\) is '
                                    r'private but has no default'):
            defopt.run(main, argv=[])

    def test_argparse_kwargs(self):
        def main(*, a=None):
            """:type a: str"""
            return a
        self.assertEqual(
            defopt.run(main, argparse_kwargs={'prefix_chars': '+'},
                       argv=['+a', 'foo']),
            'foo')


class TestParsers(unittest.TestCase):
    def test_parser(self):
        def main(value):
            """:type value: int"""
            return value
        self.assertEqual(defopt.run(main, argv=['1']), 1)

    def test_overridden_parser(self):
        def parser(string):
            return int(string) * 2

        def main(value):
            """:type value: int"""
            return value
        self.assertEqual(
            defopt.run(main, parsers={int: parser}, argv=['1']), 2)

    def test_parse_bool(self):
        parser = defopt._get_parser(bool, {})
        self.assertEqual(parser('t'), True)
        self.assertEqual(parser('FALSE'), False)
        self.assertEqual(parser('1'), True)
        with self.assertRaises(ValueError):
            parser('foo')

    @unittest.skipIf(Path is None, 'pathlib not installed')
    def test_parse_path(self):
        def main(value):
            """:type value: Path"""
            return value
        self.assertEqual(defopt.run(main, argv=['foo']), Path('foo'))

    def test_parse_slice(self):
        parser = defopt._get_parser(slice, {})
        self.assertEqual(parser(':'), slice(None))
        self.assertEqual(parser(':1'), slice(None, 1))
        self.assertEqual(parser('"a":"b":"c"'), slice("a", "b", "c"))
        with self.assertRaises(ValueError):
            parser('1')

    def test_no_parser(self):
        with self.assertRaisesRegex(Exception, 'no parser'):
            defopt._get_parser(object, parsers={type: type})

    def test_list(self):
        def main(foo):
            """:type foo: list[float]"""
            return foo
        self.assertEqual(
            defopt.run(main, argv=['--foo', '1.1', '2.2']), [1.1, 2.2])

    def test_list_kwarg(self):
        def main(foo=None):
            """Test function

            :type foo: list[float]
            """
            return foo
        self.assertEqual(
            defopt.run(main, argv=['--foo', '1.1', '2.2']), [1.1, 2.2])

    def test_list_bare(self):
        with self.assertRaises(ValueError):
            defopt._get_parser(list, {})

    def test_list_keyword_only(self):
        def main(*, foo):
            """:type foo: list[int]"""
            return foo
        self.assertEqual(defopt.run(main, argv=['--foo', '1', '2']), [1, 2])
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=[])

    def test_list_var_positional(self):
        def modern(*foo):
            """:type foo: typing.Iterable[int]"""
            return foo
        def legacy(*foo):
            """:type foo: list[int]"""
            return foo
        for func in modern, legacy:
            out = defopt.run(func, argv=['--foo', '1', '--foo', '2', '3'])
            self.assertEqual(out, ([1], [2, 3]))
            self.assertEqual(defopt.run(func, argv=[]), ())

    def test_bool(self):
        def main(foo):
            """:type foo: bool"""
            return foo
        self.assertIs(defopt.run(main, argv=['1']), True)
        self.assertIs(defopt.run(main, argv=['0']), False)
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=[])

    def test_bool_list(self):
        def main(foo):
            """:type foo: list[bool]"""
            return foo
        self.assertEqual(
            defopt.run(main, argv=['--foo', '1', '0']), [True, False])

    def test_bool_var_positional(self):
        def main(*foo):
            """:type foo: bool"""
            return foo
        self.assertEqual(
            defopt.run(main, argv=['1', '1', '0']), (True, True, False))
        self.assertEqual(
            defopt.run(main, argv=[]), ())

    def test_bool_list_var_positional(self):
        def main(*foo):
            """:type foo: list[bool]"""
            return foo
        argv = ['--foo', '1', '--foo', '0', '0']
        self.assertEqual(
            defopt.run(main, argv=argv), ([True], [False, False]))
        self.assertEqual(
            defopt.run(main, argv=[]), ())

    def test_bool_kwarg(self):
        def main(foo='default'):
            """:type foo: bool"""
            return foo
        self.assertIs(defopt.run(main, strict_kwonly=False,
                                 argv=[]), 'default')
        self.assertIs(defopt.run(main, strict_kwonly=False,
                                 argv=['--foo']), True)
        self.assertIs(defopt.run(main, strict_kwonly=False,
                                 argv=['--no-foo']), False)
        self.assertIs(defopt.run(main, strict_kwonly=False,
                                 argv=['--foo', '--no-foo']), False)

    def test_bool_keyword_only(self):
        def main(*, foo):
            """:type foo: bool"""
            return foo
        self.assertIs(defopt.run(main, argv=['--foo']), True)
        self.assertIs(defopt.run(main, argv=['--no-foo']), False)
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=[])

    def test_implicit_parser(self):
        def ok(foo):
            """:type foo: ConstructibleFromStr"""
            return foo

        self.assertEqual(defopt.run(ok, argv=["foo"]).s, "foo")

    def test_implicit_noparser(self):
        def notok(foo):
            """:type foo: NotConstructibleFromStr"""

        with self.assertRaises(Exception):
            defopt.run(notok, argv=["foo"])


class TestFlags(unittest.TestCase):
    def test_short_flags(self):
        def func(foo=1):
            """:type foo: int"""
            return foo
        self.assertEqual(
            defopt.run(func, short={'foo': 'f'}, strict_kwonly=False,
                       argv=['-f', '2']),
            2)

    def test_short_negation(self):
        def func(*, foo=False):
            """:type foo: bool"""
            return foo
        self.assertIs(
            defopt.run(func, short={'foo': 'f', 'no-foo': 'F'}, argv=['-f']),
            True)
        self.assertIs(
            defopt.run(func, short={'foo': 'f', 'no-foo': 'F'}, argv=['-F']),
            False)

    def test_auto_short(self):
        def func(*, foo=1, bar=2, baz=3):
            """
            :type foo: int
            :type bar: int
            :type baz: int
            """
            return foo
        self.assertEqual(defopt.run(func, argv=['-f', '2']), 2)
        with self.assertRaises(SystemExit):
            defopt.run(func, argv=['-b', '2'])

    def test_auto_short_help(self):
        def func(*, hello="world"):
            """:type hello: str"""
        defopt.run(func, argv=[])


class TestEnums(unittest.TestCase):
    def test_enum(self):
        def main(foo):
            """:type foo: Choice"""
            return foo
        self.assertEqual(defopt.run(main, argv=['one']), Choice.one)
        self.assertEqual(defopt.run(main, argv=['two']), Choice.two)
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=['three'])

    def test_optional(self):
        def main(*, foo=None):
            """:type foo: Choice"""
            return foo
        self.assertEqual(defopt.run(main, argv=['--foo', 'one']), Choice.one)
        self.assertIs(defopt.run(main, argv=[]), None)

    def test_subcommand(self):
        def sub1(foo):
            """:type foo: Choice"""
            return foo
        def sub2(bar):
            """:type bar: Choice"""
            return bar
        self.assertEqual(
            defopt.run([sub1, sub2], argv=['sub1', 'one']), Choice.one)
        self.assertEqual(
            defopt.run([sub1, sub2], argv=['sub2', 'two']), Choice.two)


class TestTuple(unittest.TestCase):
    def test_tuple(self):
        def main(foo):
            """:param typing.Tuple[int,str] foo: foo"""
            return foo
        self.assertEqual(defopt.run(main, argv=['1', '2']), (1, '2'))

    def test_tupleenum(self):
        def main(foo):
            """:param typing.Tuple[Choice] foo: foo"""
            return foo
        self.assertEqual(defopt.run(main, argv=['one']), (Choice.one,))

    def test_namedtuple(self):
        # Add a second argument after the tuple to ensure that the converter
        # closes over the correct type.
        def main(foo, bar):
            """
            :param Pair foo: foo
            :param int bar: bar
            """
            return foo
        # Instances of the Pair class compare equal to tuples, so we compare
        # their __str__ instead to make sure that the type is correct too.
        self.assertEqual(str(defopt.run(main, argv=['1', '2', '3'])),
                         str(Pair(1, '2')))


class TestUnion(unittest.TestCase):
    def test_union(self):
        def main(foo, bar = None):
            """
            :param typing.Union[int,str] foo: foo
            :param bar: bar
            :type bar: float or str
            """
            return type(foo), type(bar)
        self.assertEqual(defopt.run(main, argv=['1', '2']), (int, float))
        self.assertEqual(defopt.run(main, argv=['1', 'b']), (int, str))
        self.assertEqual(defopt.run(main, argv=['a', '2']), (str, float))

    def test_bad_parse(self):
        def main(foo):
            """:param typing.Union[int,float] foo: foo"""
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=['bar'])

    def test_bad_union(self):
        def main(foo):
            """:param typing.Union[int,typing.List[str]] foo: foo"""
        with self.assertRaises(ValueError):
            defopt.run(main, argv=['1'])
        def main(foo):
            """
            :param foo: foo
            :type foo: int or list[str]
            """
        with self.assertRaises(ValueError):
            defopt.run(main, argv=['1'])


class TestLiteral(unittest.TestCase):
    def test_literal(self):
        def main(foo):
            """:param defopt.Literal["bar","baz"] foo: foo"""
            return foo
        self.assertEqual(defopt.run(main, argv=["bar"]), "bar")
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=["quux"])


class TestExceptions(unittest.TestCase):
    def test_exceptions(self):
        def main(name):
            """
            :param str name: name
            :raises RuntimeError:
            """
            raise getattr(builtins, name)("oops")

        with self.assertRaises(SystemExit):
            defopt.run(main, argv=["RuntimeError"])
        with self.assertRaises(ValueError):
            defopt.run(main, argv=["ValueError"])


class TestDoc(unittest.TestCase):
    def test_parse_docstring(self):
        doc = """
        Test function

        :param one: first param
        :type one: int
        :param float two: second param
        :returns: str
        :junk one two: nothing
        """
        doc = defopt._parse_docstring(inspect.cleandoc(doc))
        self.assertEqual(doc.text, 'Test function')
        one = doc.params['one']
        self.assertEqual(one.text, 'first param')
        self.assertEqual(one.type, 'int')
        two = doc.params['two']
        self.assertEqual(two.text, 'second param')
        self.assertEqual(two.type, 'float')

    def test_parse_params(self):
        doc = """
        Test function

        :param first: first param
        :parameter int second: second param
        :arg third: third param
        :argument float fourth: fourth param
        :key fifth: fifth param
        :keyword str sixth: sixth param
        """
        doc = defopt._parse_docstring(inspect.cleandoc(doc))
        self.assertEqual(doc.params['first'].text, 'first param')
        self.assertEqual(doc.params['second'].text, 'second param')
        self.assertEqual(doc.params['third'].text, 'third param')
        self.assertEqual(doc.params['fourth'].text, 'fourth param')
        self.assertEqual(doc.params['fifth'].text, 'fifth param')
        self.assertEqual(doc.params['sixth'].text, 'sixth param')

    def test_parse_doubles(self):
        doc = """
        Test function

        :param int param: the parameter
        :type param: int
        """
        with self.assertRaises(ValueError):
            defopt._parse_docstring(inspect.cleandoc(doc))

        doc = """Test function

        :type param: int
        :param int param: the parameter
        """
        with self.assertRaises(ValueError):
            defopt._parse_docstring(inspect.cleandoc(doc))

    def test_no_doc(self):
        doc = defopt._parse_docstring(None)
        self.assertEqual(doc.text, '')
        self.assertEqual(doc.params, {})

    def test_param_only(self):
        doc = defopt._parse_docstring(""":param int param: test""")
        self.assertEqual(doc.text, '')
        param = doc.params['param']
        self.assertEqual(param.text, 'test')
        self.assertEqual(param.type, 'int')

    def test_implicit_role(self):
        doc = defopt._parse_docstring("""start `int` end""")
        self.assertEqual(doc.text, 'start \033[4mint\033[0m end')

    def test_explicit_role(self):
        doc = defopt._parse_docstring("""start :py:class:`int` end""")
        self.assertEqual(doc.text, 'start int end')

    def test_sphinx(self):
        doc = """
        One line summary.

        Extended description.

        :param int arg1: Description of arg1
        :param str arg2: Description of arg2
        :keyword float arg3: Description of arg3
        :returns: Description of return value.
        :rtype: str

        .. rubric:: examples

        >>> print("hello, world")
        """
        doc = defopt._parse_docstring(inspect.cleandoc(doc))
        self._check_doc(doc)

    def test_google(self):
        # Docstring taken from Napoleon's example (plus a keyword argument).
        doc = """
        One line summary.

        Extended description.

        Args:
          arg1(int): Description of arg1
          arg2(str): Description of arg2

        Keyword Arguments:
          arg3(float): Description of arg3

        Returns:
          str: Description of return value.

        Examples:
          >>> print("hello, world")
        """
        doc = defopt._parse_docstring(inspect.cleandoc(doc))
        self._check_doc(doc)

    def test_numpy(self):
        # Docstring taken from Napoleon's example (plus a keyword argument).
        doc = """
        One line summary.

        Extended description.

        Parameters
        ----------
        arg1 : int
            Description of arg1
        arg2 : str
            Description of arg2

        Keyword Arguments
        -----------------
        arg3 : float
            Description of arg3

        Returns
        -------
        str
            Description of return value.

        Examples
        --------
        >>> print("hello, world")
        """
        doc = defopt._parse_docstring(inspect.cleandoc(doc))
        self._check_doc(doc)

    def _check_doc(self, doc):
        self.assertRegex(
            doc.text,
            r'\AOne line summary\. \n \nExtended description\.( \n)+'
            r'examples: \n>>> print\("hello, world"\)\Z')
        self.assertEqual(len(doc.params), 3)
        self.assertEqual(doc.params['arg1'].text, 'Description of arg1')
        self.assertEqual(doc.params['arg1'].type, 'int')
        self.assertEqual(doc.params['arg2'].text, 'Description of arg2')
        self.assertEqual(doc.params['arg2'].type, 'str')
        self.assertEqual(doc.params['arg3'].text, 'Description of arg3')
        self.assertEqual(doc.params['arg3'].type, 'float')

    def test_sequence(self):
        globalns = {'Sequence': typing.Sequence}
        self.assertEqual(
            defopt._get_type_from_doc('Sequence[int]', globalns),
            typing.List[int])

    def test_iterable(self):
        globalns = {'typing': typing}
        self.assertEqual(
            defopt._get_type_from_doc('typing.Iterable[int]', globalns),
            typing.List[int])

    def test_other(self):
        with self.assertRaisesRegex(ValueError, 'unsupported.*tuple'):
            defopt._get_type_from_doc('tuple[int]', {})

    def test_literal_block(self):
        doc = """
        ::

            Literal block
                Multiple lines
        """
        doc = defopt._parse_docstring(inspect.cleandoc(doc))
        self.assertEqual(doc.text, '    Literal block\n        Multiple lines')

    def test_newlines(self):
        doc = """
        Bar
        Baz

        .. a comment

        - bar
        - baz

        quux::

            hello


        1. bar
        #. baz

        ii. bar
        #.  baz
        """
        doc = defopt._parse_docstring(inspect.cleandoc(doc))
        # Use inspect.cleandoc and not textwrap.dedent, as we want to keep
        # whitespace in lines that contain more than the common leading
        # whitespace.
        self.assertEqual(doc.text, inspect.cleandoc("""\
            Bar
            Baz 
             
            - bar 
            - baz 
             
            quux: 
             
                hello 
             
             
            1. bar 
            2. baz 
             
            ii.  bar 
            iii. baz"""))


class TestAnnotations(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(defopt._get_type_from_hint(int), int)

    def test_container(self):
        self.assertEqual(defopt._get_type_from_hint(typing.Sequence[int]),
                         typing.List[int])

    def test_optional(self):
        self.assertEqual(defopt._get_type_from_hint(typing.Optional[int]), int)

    def test_conflicting(self):
        def foo(bar: int):
            """:type bar: float"""
        with self.assertRaisesRegex(ValueError, 'bar.*float.*int'):
            defopt.run(foo, argv=['1'])

    def test_none(self):
        def foo(bar):
            """No type information"""
        with self.assertRaisesRegex(ValueError, 'no type'):
            defopt.run(foo, argv=['1'])

    def test_same(self):
        def foo(bar: int):
            """:type bar: int"""
            return bar
        self.assertEqual(defopt.run(foo, argv=['1']), 1)


class TestHelp(unittest.TestCase):
    def test_type(self):
        def foo(bar):
            """:param int bar: baz"""
        self.assert_in_help('(type: int)', foo, 'dt')
        self.assert_in_help('(type: int)', foo, 't')
        self.assert_not_in_help('(', foo, 'd')
        self.assert_not_in_help('(', foo, '')

    def test_enum_and_no_help(self):
        def foo(bar):
            """:param Choice bar:"""
        self.assert_not_in_help('(', foo, 'dt')
        self.assert_not_in_help('(', foo, 't')
        self.assert_not_in_help('(', foo, 'd')
        self.assert_not_in_help('(', foo, '')

    def test_default(self):
        def foo(bar=1):
            """:param int bar: baz"""
        self.assert_in_help('(type: int, default: 1)', foo, 'dt')
        self.assert_in_help('(type: int)', foo, 't')
        self.assert_in_help('(default: 1)', foo, 'd')
        self.assert_not_in_help('(', foo, '')

    def test_default_list(self):
        def foo(bar=[]):
            """:param typing.List[int] bar: baz"""
        self.assert_in_help('(type: int, default: [])', foo, 'dt')
        self.assert_in_help('(type: int)', foo, 't')
        self.assert_in_help('(default: [])', foo, 'd')
        self.assert_not_in_help('(', foo, '')

    def test_default_bool(self):
        def foo(bar=False):
            """:param bool bar: baz"""
        self.assert_in_help('(default: False)', foo, 'dt')
        self.assert_not_in_help('(', foo, 't')
        self.assert_in_help('(default: False)', foo, 'd')
        self.assert_not_in_help('(', foo, '')

    def test_keyword_only(self):
        def foo(*, bar):
            """:param int bar: baz"""
        self.assert_in_help('(type: int)', foo, 'dt')
        self.assert_in_help('(type: int)', foo, 't')
        self.assert_not_in_help('(', foo, 'd')
        self.assert_not_in_help('(', foo, '')

    def test_keyword_only_bool(self):
        def foo(*, bar):
            """:param bool bar: baz"""
        self.assert_not_in_help('default', foo, 'dt')

    def test_keyword_only_enum_percent_escape(self):
        def foo(*, bar=Choice['%']):
            """:param Choice bar:"""
        self.assert_not_in_help('Choice', foo, 'dt')
        self.assert_in_help('{one,two,%}', foo, 'dt')
        self.assert_not_in_help('Choice', foo, 't')
        self.assert_not_in_help('Choice', foo, 'd')
        self.assert_in_help('{one,two,%}', foo, 'd')
        self.assert_not_in_help('Choice', foo, '')
        # ("{one,two,%}" always shows up at least in the usage line.)

    def test_keyword_only_literal_percent_escape(self):
        def foo(*, bar):
            """:param defopt.Literal["1%","everything"] bar: 1%"""
        self.assert_not_in_help('Literal', foo, 'dt')
        self.assert_not_in_help('Literal', foo, 't')
        self.assert_not_in_help('Literal', foo, 'd')
        self.assert_not_in_help('Literal', foo, '')

    def test_tuple(self):
        def main(foo=None):
            """:param typing.Tuple[int,str] foo: help"""
        self.assert_in_help('--foo FOO FOO', main, '')

    def test_namedtuple(self):
        def main(foo=None):
            """:param Pair foo: help"""
        self.assert_in_help('--foo first second', main, '')

    def test_var_positional(self):
        for doc in [
                ":type bar: int", r":type \*bar: int", ":param int bar: baz"]:
            def foo(*bar): assert False
            foo.__doc__ = doc
            self.assert_not_in_help('default', foo, 'dt')

    def test_list_var_positional(self):
        def foo(*bar):
            """:param list[int] bar: baz"""
        self.assert_not_in_help('default', foo, 'dt')

    def test_private(self):
        def foo(bar, _baz=None):
            """:param int bar: bar help"""
        self.assert_not_in_help('baz', foo, 'dt')

    def test_no_interpolation(self):
        def foo(bar):
            """:param int bar: %(prog)s"""
        self.assert_in_help('%(prog)s', foo, '')
        self.assert_not_in_help('%%', foo, '')

    def test_rst_ansi(self):
        def foo():
            """**bold** *italic* `underlined`"""
        self.assert_in_help(
            '\033[1mbold\033[0m \033[3mitalic\033[0m \033[4munderlined\033[0m',
            foo, '')

    def test_multiple(self):
        def foo():
            """summary-of-foo

            Implements FOO.
            """

        def bar():
            """summary-of-bar

            Implements BAR."""

        self.assert_in_help('summary-of-foo', [foo, bar], '')
        self.assert_not_in_help('FOO', [foo, bar], '')

    def assert_in_help(self, s, funcs, flags):
        self.assertIn(s, self._get_help(funcs, flags))

    def assert_not_in_help(self, s, funcs, flags):
        self.assertNotIn(s, self._get_help(funcs, flags))

    def _get_help(self, funcs, flags):
        self.assertLessEqual({*flags}, {'d', 't'})
        parser = defopt._create_parser(
            funcs, show_defaults='d' in flags, show_types='t' in flags,
            strict_kwonly=False)
        return parser.format_help()


class TestVersion(unittest.TestCase):
    def test_no_version(self):
        for funcs in [[], lambda: None, [lambda: None]]:
            with self.assertRaises(SystemExit), \
                 self._assert_streams(
                     stdout=r'\A\Z',
                     stderr='unrecognized arguments: --version'):
                defopt.run([], version=False, argv=['--version'])

    def test_auto_version(self):
        with self.assertRaises(SystemExit), \
             self._assert_streams(
                 stdout=r'\A{}\n\Z'.format(re.escape(__version__))):
            defopt.run(lambda: None, argv=['--version'])
        with self.assertRaises(SystemExit), \
             self._assert_streams(
                 stdout=r'\A\Z',
                 stderr='unrecognized arguments: --version'):
            defopt.run([], argv=['--version'])

    def test_manual_version(self):
        with self.assertRaises(SystemExit), \
             self._assert_streams(stdout=r'\Afoo 42\n\Z'):
            defopt.run([], version='foo 42', argv=['--version'])

    @contextlib.contextmanager
    def _assert_streams(self, *, stdout=None, stderr=None):
        with ExitStack() as stack:
            if stdout is not None:
                r_stdout = stack.enter_context(
                    contextlib.redirect_stdout(StringIO()))
                stack.callback(
                    lambda: self.assertRegex(r_stdout.getvalue(), stdout))
            if stderr is not None:
                r_stderr = stack.enter_context(
                    contextlib.redirect_stderr(StringIO()))
                stack.callback(
                    lambda: self.assertRegex(r_stderr.getvalue(), stderr))
            yield


class TestExamples(unittest.TestCase):
    def test_annotations(self):
        for command in [annotations.documented, annotations.undocumented]:
            with self._assert_stdout('[1, 8]\n'):
                command([1, 2], 3)

    def test_annotations_cli(self):
        for command in ['documented', 'undocumented']:
            args = [command, '--numbers', '1', '2', '--', '3']
            output = self._run_example(annotations, args)
            self.assertEqual(output, b'[1.0, 8.0]\n')

    def test_booleans(self):
        with self._assert_stdout('test\ntest\n'):
            booleans.main('test', upper=False, repeat=True)
        with self._assert_stdout('TEST\n'):
            booleans.main('test')

    def test_booleans_cli(self):
        output = self._run_example(
            booleans, ['test', '--no-upper', '--repeat'])
        self.assertEqual(output, b'test\ntest\n')
        output = self._run_example(
            booleans, ['test'])
        self.assertEqual(output, b'TEST\n')

    def test_choices(self):
        with self._assert_stdout('Choice.one (1)\n'):
            choices.choose_enum(choices.Choice.one)
        with self._assert_stdout('Choice.one (1)\nChoice.two (2.0)\n'):
            choices.choose_enum(choices.Choice.one, opt=choices.Choice.two)
        with self.assertRaises(AttributeError):
            choices.choose_enum('one')
        with self._assert_stdout('foo\n'):
            choices.choose_literal('foo')
        with self._assert_stdout('foo\nbaz\n'):
            choices.choose_literal('foo', opt='baz')

    def test_choices_cli(self):
        output = self._run_example(choices, ['choose-enum', 'one'])
        self.assertEqual(output, b'Choice.one (1)\n')
        output = self._run_example(
            choices, ['choose-enum', 'one', '--opt', 'two'])
        self.assertEqual(output, b'Choice.one (1)\nChoice.two (2.0)\n')
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self._run_example(choices, ['choose-enum', 'four'])
        self.assertIn(b'four', error.exception.output)
        self.assertIn(b'{one,two,three}', error.exception.output)
        output = self._run_example(choices, ['choose-literal', 'foo'])
        self.assertEqual(output, b'foo\n')
        output = self._run_example(
            choices, ['choose-literal', 'foo', '--opt', 'baz'])
        self.assertEqual(output, b'foo\nbaz\n')
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self._run_example(choices, ['choose-literal', 'baz'])
        self.assertIn(b'baz', error.exception.output)
        self.assertIn(b'{foo,bar}', error.exception.output)

    def test_exceptions(self):
        self._run_example(exceptions, ['1'])
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self._run_example(exceptions, ['0'])
        self.assertIn(b"Don't do this!", error.exception.output)
        self.assertNotIn(b"Traceback", error.exception.output)

    def test_lists(self):
        with self._assert_stdout('[2.4, 6.8]\n'):
            lists.main([1.2, 3.4], 2)
        with self._assert_stdout('[2, 4, 6]\n'):
            lists.main([1, 2, 3], 2)

    def test_lists_cli(self):
        output = self._run_example(
            lists, ['2', '--numbers', '1.2', '3.4'])
        self.assertEqual(output, b'[2.4, 6.8]\n')
        output = self._run_example(
            lists, ['--numbers', '1.2', '3.4', '--', '2'])
        self.assertEqual(output, b'[2.4, 6.8]\n')

    def test_parsers(self):
        date = parsers.datetime(2015, 9, 13)
        with self._assert_stdout('{}\n'.format(date)):
            parsers.main(date)
        with self._assert_stdout('junk\n'):
            parsers.main('junk')

    def test_parsers_cli(self):
        output = self._run_example(parsers, ['2015-09-13'])
        self.assertEqual(output, b'2015-09-13 00:00:00\n')
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self._run_example(parsers, ['junk'])
        self.assertIn(b'datetime', error.exception.output)
        self.assertIn(b'junk', error.exception.output)

    def test_short(self):
        with self._assert_stdout('hello!\n'):
            short.main()
        with self._assert_stdout('hello!\nhello!\n'):
            short.main(count=2)

    def test_short_cli(self):
        output = self._run_example(short, ['--count', '2'])
        self.assertEqual(output, b'hello!\nhello!\n')
        output = self._run_example(short, ['-C', '2'])
        self.assertEqual(output, b'hello!\nhello!\n')

    def test_starargs(self):
        with self._assert_stdout('1\n2\n3\n'):
            starargs.plain(1, 2, 3)
        with self._assert_stdout('[1, 2]\n[3, 4, 5]\n'):
            starargs.iterable([1, 2], [3, 4, 5])

    def test_starargs_cli(self):
        output = self._run_example(starargs, ['plain', '1', '2', '3'])
        self.assertEqual(output, b'1\n2\n3\n')
        args = ['iterable', '--groups', '1', '2', '--groups', '3', '4', '5']
        output = self._run_example(starargs, args)
        self.assertEqual(output, b'[1, 2]\n[3, 4, 5]\n')

    def test_styles(self):
        for command in [styles.sphinx, styles.google, styles.numpy]:
            with self._assert_stdout('4\n'):
                command(2)
            with self._assert_stdout('4\nbye\n'):
                command(2, farewell='bye')

    def test_styles_cli(self):
        for style in ['sphinx', 'google', 'numpy']:
            args = [style, '2', '--farewell', 'bye']
            output = self._run_example(styles, args)
            self.assertEqual(output, b'4\nbye\n')

    @contextlib.contextmanager
    def _assert_stdout(self, s):
        with contextlib.redirect_stdout(StringIO()) as file:
            yield
            self.assertEqual(file.getvalue(), s)

    def _run_example(self, example, argv):
        output = subprocess.check_output(
            [sys.executable, '-m', example.__name__] + argv,
            stderr=subprocess.STDOUT)
        return output.replace(b'\r\n', b'\n')


class TestRunAny(unittest.TestCase):  # TODO: Reuse TestExamples.
    def test_lists_cli(self):
        output = self._run_any(
            'examples.lists.main', ['2', '--numbers', '1.2', '3.4'])
        self.assertEqual(output, b'[2.4, 6.8]\n')
        output = self._run_any(
            'examples.lists.main', ['--numbers', '1.2', '3.4', '--', '2'])
        self.assertEqual(output, b'[2.4, 6.8]\n')

    def test_failed_imports(self):
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self._run_any('does-not-exist', [])
        self.assertIn(b"Failed to locate 'does-not-exist'",
                      error.exception.output)
        with TemporaryDirectory() as tmpdir:
            Path(tmpdir, 'bad_module.py').write_text('1+')
            with self.assertRaises(subprocess.CalledProcessError) as error:
                self._run_any('bad_module', [], cwd=tmpdir)
            self.assertRegex(error.exception.output,
                             br'SyntaxError: invalid syntax\n\Z')

    def _run_any(self, command, argv, **kwargs):
        output = subprocess.check_output(
            [sys.executable, '-m', 'defopt', command] + argv,
            stderr=subprocess.STDOUT, **kwargs)
        return output.replace(b'\r\n', b'\n')


class TestDefaultsPreserved(unittest.TestCase):
    def test_defaults_preserved(self):
        """Check that mutable defaults are not modified."""
        params = inspect.signature(defopt.run).parameters
        self.assertEqual(params['parsers'].default, {})
        self.assertEqual(params['argparse_kwargs'].default, {})
