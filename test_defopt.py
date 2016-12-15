from argparse import ArgumentParser
from enum import Enum
import subprocess
import sys
import textwrap
import typing
import unittest

import mock

import defopt
from examples import booleans, choices, lists, parsers, short, starargs, styles


if not hasattr(unittest.TestCase, 'assertRaisesRegex'):
    unittest.TestCase.assertRaisesRegex = unittest.TestCase.assertRaisesRegexp


class TestDefopt(unittest.TestCase):
    def test_main(self):
        def main(foo):
            """:type foo: str"""
            return foo
        self.assertEqual(defopt.run(main, argv=['foo']), 'foo')

    def test_subcommands(self):
        def sub1(*bar):
            """:type bar: float"""
            return bar
        def sub2(baz=None):
            """:type baz: int"""
            return baz
        self.assertEqual(defopt.run(sub1, sub2, argv=['sub1', '1.1']), (1.1,))
        self.assertEqual(defopt.run(sub1, sub2, argv=['sub2', '--baz', '1']), 1)

    def test_var_positional(self):
        def main(*foo):
            """:type foo: int"""
            return foo
        self.assertEqual(defopt.run(main, argv=['1', '2']), (1, 2))
        self.assertEqual(defopt.run(main, argv=[]), ())

    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_keyword_only(self):
        globals_ = {}
        exec(textwrap.dedent('''\
            def main(*, foo='bar'):
                """:type foo: str"""
                return foo
        '''), globals_)
        main = globals_['main']
        self.assertEqual(defopt.run(main, argv=['--foo', 'baz']), 'baz')
        self.assertEqual(defopt.run(main, argv=[]), 'bar')

    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_keyword_only_no_default(self):
        globals_ = {}
        exec(textwrap.dedent('''\
            def main(*, foo):
                """:type foo: str"""
                return foo
        '''), globals_)
        main = globals_['main']
        self.assertEqual(defopt.run(main, argv=['--foo', 'baz']), 'baz')
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=[])

    def test_var_keywords(self):
        def bad(**kwargs):
            """:type kwargs: str"""

        with self.assertRaises(ValueError):
            defopt.run(bad)

    def test_no_function(self):
        with self.assertRaisesRegex(ValueError, 'at least one'):
            defopt.run()

    def test_bad_arg(self):
        with self.assertRaises(TypeError):
            defopt.run(foo=None)

    def test_no_subparser_specified(self):
        def sub1():
            pass
        def sub2():
            pass
        with self.assertRaises(SystemExit):
            defopt.run(sub1, sub2, argv=[])

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
        def one():
            return 1

        def none():
            pass

        self.assertEqual(defopt.run(one, none, argv=['one']), 1)
        self.assertEqual(defopt.run(one, none, argv=['none']), None)

    def test_underscores(self):
        def main(a_b_c, d_e_f=None):
            """Test function

            :type a_b_c: int
            :type d_e_f: int
            """
            return a_b_c, d_e_f
        self.assertEqual(defopt.run(main, argv=['1', '--d-e-f', '2']), (1, 2))


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
        self.assertEqual(defopt.run(main, parsers={int: parser}, argv=['1']), 2)

    def test_parse_bool(self):
        parser = defopt._get_parser(bool)
        self.assertEqual(parser('t'), True)
        self.assertEqual(parser('FALSE'), False)
        self.assertEqual(parser('1'), True)
        with self.assertRaises(ValueError):
            parser('foo')

    def test_no_parser(self):
        with self.assertRaisesRegex(Exception, 'no parser'):
            defopt._get_parser(object, parsers={type: type})

    def test_list(self):
        def main(foo):
            """:type foo: list[float]"""
            return foo
        self.assertEqual(defopt.run(main, argv=['--foo', '1.1', '2.2']), [1.1, 2.2])

    def test_list_kwarg(self):
        def main(foo=None):
            """Test function

            :type foo: list[float]
            """
            return foo
        self.assertEqual(defopt.run(main, argv=['--foo', '1.1', '2.2']), [1.1, 2.2])

    def test_list_bare(self):
        with self.assertRaises(ValueError):
            defopt._get_parser(list)

    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_list_keyword_only(self):
        globals_ = {}
        exec(textwrap.dedent('''\
            def main(*, foo):
                """:type foo: list[int]"""
                return foo
        '''), globals_)
        main = globals_['main']
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
        self.assertEqual(defopt.run(main, argv=['--foo', '1', '0']), [True, False])

    def test_bool_var_positional(self):
        def main(*foo):
            """:type foo: bool"""
            return foo
        self.assertEqual(defopt.run(main, argv=['1', '1', '0']), (True, True, False))
        self.assertEqual(defopt.run(main, argv=[]), ())

    def test_bool_list_var_positional(self):
        def main(*foo):
            """:type foo: list[bool]"""
            return foo
        argv = ['--foo', '1', '--foo', '0', '0']
        self.assertEqual(defopt.run(main, argv=argv), ([True], [False, False]))
        self.assertEqual(defopt.run(main, argv=[]), ())

    def test_bool_kwarg(self):
        default = object()

        def main(foo=default):
            """:type foo: bool"""
            return foo
        self.assertIs(defopt.run(main, argv=['--foo']), True)
        self.assertIs(defopt.run(main, argv=['--no-foo']), False)
        self.assertIs(defopt.run(main, argv=[]), default)

    @unittest.skipIf(sys.version_info < (3, 4), 'expectedFailure ignores SystemExit')
    @unittest.expectedFailure
    def test_bool_kwarg_override(self):
        def main(foo=True):
            """:type foo: bool"""
            return foo
        self.assertIs(defopt.run(main, argv=['--foo', '--no-foo']), False)

    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_bool_keyword_only(self):
        globals_ = {}
        exec(textwrap.dedent('''\
            def main(*, foo):
                """:type foo: bool"""
                return foo
        '''), globals_)
        main = globals_['main']
        self.assertIs(defopt.run(main, argv=['--foo']), True)
        self.assertIs(defopt.run(main, argv=['--no-foo']), False)
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=[])


class TestFlags(unittest.TestCase):
    def test_short_flags(self):
        def func(foo=1):
            """:type foo: int"""
            return foo
        out = defopt.run(func, short={'foo': 'f'}, argv=['-f', '2'])
        self.assertEqual(out, 2)

    def test_short_negation(self):
        def func(foo=False):
            """:type foo: bool"""
            return foo
        out = defopt.run(func, short={'foo': 'f', 'no-foo': 'F'}, argv=['-f'])
        self.assertIs(out, True)
        out = defopt.run(func, short={'foo': 'f', 'no-foo': 'F'}, argv=['-F'])
        self.assertIs(out, False)


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
        def main(foo=None):
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

        self.assertEqual(defopt.run(sub1, sub2, argv=['sub1', 'one']), Choice.one)
        self.assertEqual(defopt.run(sub1, sub2, argv=['sub2', 'two']), Choice.two)

    def test_valuedict(self):
        valuedict = defopt._ValueOrderedDict({'a': 1})
        self.assertEqual(list(valuedict), ['a'])
        self.assertIn(1, valuedict)
        self.assertNotIn('a', valuedict)

    def test_enumgetter(self):
        getter = defopt._enum_getter(Choice)
        self.assertEqual(getter('one'), Choice.one)
        self.assertEqual(getter('two'), Choice.two)
        self.assertEqual(getter('three'), 'three',
                         msg='argparse needs to report this value')


class Choice(Enum):
    one = 1
    two = 2


class TestDoc(unittest.TestCase):
    def test_parse_doc(self):
        def test(one, two):
            """Test function

            :param one: first param
            :type one: int
            :param float two: second param
            :returns: str
            :junk one two: nothing
            """
        doc = defopt._parse_doc(test)
        self.assertEqual(doc.text, 'Test function')
        one = doc.params['one']
        self.assertEqual(one.text, 'first param')
        self.assertEqual(one.type, 'int')
        two = doc.params['two']
        self.assertEqual(two.text, 'second param')
        self.assertEqual(two.type, 'float')

    def test_parse_params(self):
        def test(first, second, third, fourth, fifth, sixth):
            """Test function

            :param first: first param
            :parameter int second: second param
            :arg third: third param
            :argument float fourth: fourth param
            :key fifth: fifth param
            :keyword str sixth: sixth param
            """
        doc = defopt._parse_doc(test)
        self.assertEqual(doc.params['first'].text, 'first param')
        self.assertEqual(doc.params['second'].text, 'second param')
        self.assertEqual(doc.params['third'].text, 'third param')
        self.assertEqual(doc.params['fourth'].text, 'fourth param')
        self.assertEqual(doc.params['fifth'].text, 'fifth param')
        self.assertEqual(doc.params['sixth'].text, 'sixth param')

    def test_parse_doubles(self):
        def test(param):
            """Test function

            :param int param: the parameter
            :type param: int
            """
        with self.assertRaises(ValueError):
            defopt._parse_doc(test)

        def test(param):
            """Test function

            :type param: int
            :param int param: the parameter
            """
        with self.assertRaises(ValueError):
            defopt._parse_doc(test)

    def test_no_doc(self):
        def test(param):
            pass
        doc = defopt._parse_doc(test)
        self.assertEqual(doc.text, '')
        self.assertEqual(doc.params, {})

    def test_param_only(self):
        def test(param):
            """:param int param: test"""
        doc = defopt._parse_doc(test)
        self.assertEqual(doc.text, '')
        param = doc.params['param']
        self.assertEqual(param.text, 'test')
        self.assertEqual(param.type, 'int')

    def test_implicit_role(self):
        def test():
            """start `int` end"""
        doc = defopt._parse_doc(test)
        self.assertEqual(doc.text, 'start int end')

    @unittest.expectedFailure
    def test_explicit_role_desired(self):
        """Desired output for issue #1."""
        def test():
            """start :py:class:`int` end"""
        doc = defopt._parse_doc(test)
        self.assertEqual(doc.text, 'start int end')

    def test_explicit_role_actual(self):
        """Workaround output for issue #1."""
        def test():
            """start :py:class:`int` end"""
        doc = defopt._parse_doc(test)
        self.assertEqual(doc.text, 'start :py:class:`int` end')

    def test_sphinx(self):
        def func(arg1, arg2, arg3=None):
            """One line summary.

            Extended description.

            :param int arg1: Description of `arg1`
            :param str arg2: Description of `arg2`
            :keyword float arg3: Description of `arg3`
            :returns: Description of return value.
            :rtype: str
            """
        doc = defopt._parse_doc(func)
        self._check_doc(doc)

    def test_google(self):
        # Docstring taken from Napoleon's example (plus a keyword argument).
        def func(arg1, arg2, arg3=None):
            """One line summary.

            Extended description.

            Args:
              arg1(int): Description of `arg1`
              arg2(str): Description of `arg2`
            Keyword Arguments:
              arg3(float): Description of `arg3`
            Returns:
              str: Description of return value.
            """
        doc = defopt._parse_doc(func)
        self._check_doc(doc)

    def test_numpy(self):
        # Docstring taken from Napoleon's example (plus a keyword argument).
        def func(arg1, arg2, arg3=None):
            """One line summary.

            Extended description.

            Parameters
            ----------
            arg1 : int
                Description of `arg1`
            arg2 : str
                Description of `arg2`
            Keyword Arguments
            -----------------
            arg3 : float
                Description of `arg3`
            Returns
            -------
            str
                Description of return value.
            """
        doc = defopt._parse_doc(func)
        self._check_doc(doc)

    def _check_doc(self, doc):
        self.assertEqual(doc.text, 'One line summary.\n\nExtended description.')
        self.assertEqual(len(doc.params), 3)
        self.assertEqual(doc.params['arg1'].text, 'Description of arg1')
        self.assertEqual(doc.params['arg1'].type, 'int')
        self.assertEqual(doc.params['arg2'].text, 'Description of arg2')
        self.assertEqual(doc.params['arg2'].type, 'str')
        self.assertEqual(doc.params['arg3'].text, 'Description of arg3')
        self.assertEqual(doc.params['arg3'].type, 'float')

    def test_sequence(self):
        globalns = {'Sequence': typing.Sequence}
        type_ = defopt._get_type_from_doc('Sequence[int]', globalns)
        self.assertEqual(type_.container, list)
        self.assertEqual(type_.type, int)

    def test_iterable(self):
        globalns = {'typing': typing}
        type_ = defopt._get_type_from_doc('typing.Iterable[int]', globalns)
        self.assertEqual(type_.container, list)
        self.assertEqual(type_.type, int)

    def test_other(self):
        with self.assertRaisesRegexp(ValueError, 'unsupported.*tuple'):
            defopt._get_type_from_doc('tuple[int]', {})

    def test_literal_block(self):
        def func():
            """
            ::

                Literal block
                    Multiple lines
            """
        doc = defopt._parse_doc(func)
        self.assertEqual(doc.text, '    Literal block\n        Multiple lines')


class TestAnnotations(unittest.TestCase):
    def test_simple(self):
        type_ = defopt._get_type_from_hint(int)
        self.assertEqual(type_.type, int)
        self.assertEqual(type_.container, None)

    def test_container(self):
        type_ = defopt._get_type_from_hint(typing.Sequence[int])
        self.assertEqual(type_.type, int)
        self.assertEqual(type_.container, list)

    def test_optional(self):
        type_ = defopt._get_type_from_hint(typing.Optional[int])
        self.assertEqual(type_.type, int)
        self.assertEqual(type_.container, None)

    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_conflicting(self):
        globals_ = {}
        exec(textwrap.dedent('''\
            def foo(bar: int):
                """:type bar: float"""
        '''), globals_)
        with self.assertRaisesRegex(ValueError, 'bar.*float.*int'):
            defopt.run(globals_['foo'], argv=['1'])

    def test_none(self):
        def foo(bar):
            """No type information"""
        with self.assertRaisesRegex(ValueError, 'no type'):
            defopt.run(foo, argv=['1'])

    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_same(self):
        globals_ = {}
        exec(textwrap.dedent('''\
            def foo(bar: int):
                """:type bar: int"""
                return bar
        '''), globals_)
        self.assertEqual(defopt.run(globals_['foo'], argv=['1']), 1)


class TestTyping(unittest.TestCase):
    def test_old_union(self):
        union = mock.Mock()
        self.assertFalse(defopt._is_generic_type(union, typing.Union))
        union.__union_params__ = []
        self.assertFalse(defopt._is_generic_type(union, typing.Union))
        union.__union_params__ = [int]
        self.assertTrue(defopt._is_generic_type(union, typing.Union))


class TestHelp(unittest.TestCase):
    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_keyword_only(self):
        globals_ = {}
        exec(textwrap.dedent('''\
            def foo(*, bar):
                """:param int bar: baz"""
                return bar
        '''), globals_)
        self.assertNotIn('default', self._get_help(globals_['foo']))

    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_keyword_only_bool(self):
        globals_ = {}
        exec(textwrap.dedent('''\
            def foo(*, bar):
                """:param bool bar: baz"""
                return bar
        '''), globals_)
        self.assertNotIn('default', self._get_help(globals_['foo']))

    def test_var_positional(self):
        def foo(*bar):
            """:param int bar: baz"""
            return bar
        self.assertNotIn('default', self._get_help(foo))

    def test_list_var_positional(self):
        def foo(*bar):
            """:param list[int] bar: baz"""
            return bar
        self.assertNotIn('default', self._get_help(foo))

    def test_no_interpolation(self):
        def foo(bar):
            """:param int bar: %(prog)s"""
            return bar
        self.assertIn('%(prog)s', self._get_help(foo))
        self.assertNotIn('%%', self._get_help(foo))

    def _get_help(self, func):
        parser = ArgumentParser(formatter_class=defopt._Formatter)
        defopt._populate_parser(func, parser, {}, {})
        return parser.format_help()


class TestExamples(unittest.TestCase):
    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    @unittest.skipIf(sys.version_info.major == 2, 'print is unpatchable')
    @mock.patch('builtins.print')
    def test_annotations(self, print_):
        from examples import annotations
        for command in [annotations.documented, annotations.undocumented]:
            command([1, 2], 3)
            print_.assert_called_with([1, 8])

    @unittest.skipIf(sys.version_info.major == 2, 'Syntax not supported')
    def test_annotations_cli(self):
        from examples import annotations
        for command in ['documented', 'undocumented']:
            args = [command, '--numbers', '1', '2', '--', '3']
            output = self._run_example(annotations, args)
            self.assertEqual(output, b'[1.0, 8.0]\n')

    @unittest.skipIf(sys.version_info.major == 2, 'print is unpatchable')
    @mock.patch('builtins.print')
    def test_booleans(self, print_):
        booleans.main('test', upper=False, repeat=True)
        print_.assert_has_calls([mock.call('test'), mock.call('test')])
        booleans.main('test')
        print_.assert_called_with('TEST')

    def test_booleans_cli(self):
        output = self._run_example(booleans, ['test', '--no-upper', '--repeat'])
        self.assertEqual(output, b'test\ntest\n')
        output = self._run_example(booleans, ['test'])
        self.assertEqual(output, b'TEST\n')

    @unittest.skipIf(sys.version_info.major == 2, 'print is unpatchable')
    @mock.patch('builtins.print')
    def test_choices(self, print_):
        choices.main(choices.Choice.one)
        print_.assert_called_with('Choice.one (1)')
        choices.main(choices.Choice.one, choices.Choice.two)
        print_.assert_called_with('Choice.two (2.0)')
        with self.assertRaises(AttributeError):
            choices.main('one')

    def test_choices_cli(self):
        output = self._run_example(choices, ['one'])
        self.assertEqual(output, b'Choice.one (1)\n')
        output = self._run_example(choices, ['one', '--opt', 'two'])
        self.assertEqual(output, b'Choice.one (1)\nChoice.two (2.0)\n')
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self._run_example(choices, ['four'])
        self.assertIn(b'four', error.exception.output)
        self.assertIn(b'{one,two,three}', error.exception.output)

    @unittest.skipIf(sys.version_info.major == 2, 'print is unpatchable')
    @mock.patch('builtins.print')
    def test_lists(self, print_):
        lists.main([1.2, 3.4], 2)
        print_.assert_called_with([2.4, 6.8])
        lists.main([1, 2, 3], 2)
        print_.assert_called_with([2, 4, 6])

    def test_lists_cli(self):
        output = self._run_example(lists, ['2', '--numbers', '1.2', '3.4'])
        self.assertEqual(output, b'[2.4, 6.8]\n')
        output = self._run_example(lists, ['--numbers', '1.2', '3.4', '--', '2'])
        self.assertEqual(output, b'[2.4, 6.8]\n')

    @unittest.skipIf(sys.version_info.major == 2, 'print is unpatchable')
    @mock.patch('builtins.print')
    def test_parsers(self, print_):
        date = parsers.datetime(2015, 9, 13)
        parsers.main(date)
        print_.assert_called_with(date)
        parsers.main('junk')
        print_.assert_called_with('junk')

    def test_parsers_cli(self):
        output = self._run_example(parsers, ['2015-09-13'])
        self.assertEqual(output, b'2015-09-13 00:00:00\n')
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self._run_example(parsers, ['junk'])
        self.assertIn(b'datetime', error.exception.output)
        self.assertIn(b'junk', error.exception.output)

    @unittest.skipIf(sys.version_info.major == 2, 'print is unpatchable')
    @mock.patch('builtins.print')
    def test_short(self, print_):
        short.main()
        print_.assert_has_calls([mock.call('hello!')])
        short.main(count=2)
        print_.assert_has_calls([mock.call('hello!'), mock.call('hello!')])

    def test_short_cli(self):
        output = self._run_example(short, ['--count', '2'])
        self.assertEqual(output, b'hello!\nhello!\n')
        output = self._run_example(short, ['-c', '2'])
        self.assertEqual(output, b'hello!\nhello!\n')

    @unittest.skipIf(sys.version_info.major == 2, 'print is unpatchable')
    @mock.patch('builtins.print')
    def test_starargs(self, print_):
        starargs.plain(1, 2, 3)
        print_.assert_has_calls([mock.call(1), mock.call(2), mock.call(3)])
        starargs.iterable([1, 2], [3, 4, 5])
        print_.assert_has_calls([mock.call([1, 2]), mock.call([3, 4, 5])])

    def test_starargs_cli(self):
        output = self._run_example(starargs, ['plain', '1', '2', '3'])
        self.assertEqual(output, b'1\n2\n3\n')
        args = ['iterable', '--groups', '1', '2', '--groups', '3', '4', '5']
        output = self._run_example(starargs, args)
        self.assertEqual(output, b'[1, 2]\n[3, 4, 5]\n')

    @unittest.skipIf(sys.version_info.major == 2, 'print is unpatchable')
    @mock.patch('builtins.print')
    def test_styles(self, print_):
        for command in [styles.sphinx, styles.google, styles.numpy]:
            command(2)
            print_.assert_called_with(4)
            command(2, 'bye')
            print_.assert_called_with('bye')

    def test_styles_cli(self):
        for style in ['sphinx', 'google', 'numpy']:
            args = [style, '2', '--farewell', 'bye']
            output = self._run_example(styles, args)
            self.assertEqual(output, b'4\nbye\n')

    def _run_example(self, example, argv):
        argv = [sys.executable, '-m', example.__name__] + argv
        output = subprocess.check_output(argv, stderr=subprocess.STDOUT)
        return output.replace(b'\r\n', b'\n')
