from enum import Enum
import sys
import unittest

import defopt


if not hasattr(unittest.TestCase, 'assertRaisesRegex'):
    unittest.TestCase.assertRaisesRegex = unittest.TestCase.assertRaisesRegexp


class TestDefopt(unittest.TestCase):
    def setUp(self):
        self.calls = 0

    def test_main(self):
        main, args = self._def_main()
        defopt.run(main, argv=args)
        self.assertEqual(self.calls, 1)

    def test_subcommands(self):
        sub1, sub1_args = self._def_sub1()
        sub2, sub2_args = self._def_sub2()
        defopt.run(sub1, sub2, argv=sub1_args)
        defopt.run(sub1, sub2, argv=sub2_args)
        self.assertEqual(self.calls, 2)

    def test_keyword_only(self):
        """Test handling of keyword-only arguments.

        The exec avoids a SyntaxError on Python 2.x.
        """
        if sys.version_info.major >= 3:
            globals_ = {'self': self}
            exec('''def main(*, foo='bar'):
                """:type foo: str"""
                self.assertEqual(foo, 'baz')
                self.calls += 1
            ''', globals_)
            defopt.run(globals_['main'], argv=['--foo', 'baz'])
            self.assertEqual(self.calls, 1)

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
        sub1, _ = self._def_sub1()
        sub2, _ = self._def_sub2()
        with self.assertRaises(SystemExit):
            defopt.run(sub1, sub2, argv=[])

    def test_no_param_doc(self):
        def bad(foo):
            """Test function"""
        with self.assertRaisesRegex(ValueError, 'doc.*foo'):
            defopt.run(bad, argv=['foo'])

    def test_no_type_doc(self):
        def bad(foo):
            """:param foo: no type info"""
        with self.assertRaisesRegex(ValueError, 'type.*foo'):
            defopt.run(bad, argv=['foo'])

    def _def_main(self):
        def main(foo):
            """:type foo: str"""
            self.assertEqual(foo, 'foo')
            self.calls += 1
        return main, ['foo']

    def _def_sub1(self):
        def sub1(*bar):
            """:type bar: int"""
            self.assertEqual(bar, (1,))
            self.calls += 1
        return sub1, ['sub1', '1']

    def _def_sub2(self):
        def sub2(baz=None):
            """:type baz: float"""
            self.assertEqual(baz, 1.1)
            self.calls += 1
        return sub2, ['sub2', '--baz', '1.1']


class TestEvaluate(unittest.TestCase):
    def test_builtin(self):
        self.assertEqual(defopt._evaluate('int'), int)

    def test_dotted(self):
        self.assertEqual(defopt._evaluate('A.b', stack_depth=0), 'success')

    def test_nested(self):
        def lookup():
            self.assertEqual(defopt._evaluate('A', stack_depth=1), A)
        lookup()


class A:
    b = 'success'


class TestParsers(unittest.TestCase):
    def setUp(self):
        defopt._parsers = {}

    def test_parser(self):
        def main(value):
            """:type value: int"""
            self.assertEqual(value, 1)
        defopt.run(main, argv=['1'])

    def test_registered_parser(self):
        @defopt.parser(int)
        def parser(string):
            return int(string) * 2

        def main(value):
            """:type value: int"""
            self.assertEqual(value, 2)
        defopt.run(main, argv=['1'])

    def test_parse_bool(self):
        parser = defopt._get_parser(bool)
        self.assertEqual(parser('t'), True)
        self.assertEqual(parser('FALSE'), False)
        with self.assertRaises(ValueError):
            parser('foo')

    def test_double_parser(self):
        defopt.parser(int)(int)
        with self.assertRaises(Exception):
            defopt.parser(int)(int)

    def test_no_parser(self):
        with self.assertRaises(Exception):
            defopt._get_parser(A)

    def test_list(self):
        def main(foo):
            """:type foo: list[float]"""
            self.assertEqual(foo, [1.1, 2.2])
        defopt.run(main, argv=['--foo', '1.1', '2.2'])

    def test_list_kwarg(self):
        def main(foo=None):
            """Test function

            :type foo: list[float]
            """
            self.assertEqual(foo, [1.1, 2.2])
        defopt.run(main, argv=['--foo', '1.1', '2.2'])

    def test_other_container(self):
        def main(foo):
            """Test function

            :type foo: tuple[float]
            """
        with self.assertRaises(ValueError):
            defopt.run(main, argv=['--foo', '1.1', '2.2'])

    def test_list_bare(self):
        with self.assertRaises(ValueError):
            defopt._get_parser(list)


class TestEnums(unittest.TestCase):
    def test_enum(self):
        def main(foo):
            """:type foo: Choice"""
        defopt.run(main, argv=['one'])
        defopt.run(main, argv=['two'])
        with self.assertRaises(SystemExit):
            defopt.run(main, argv=['three'])

    def test_optional(self):
        def main(foo=None):
            """:type foo: Choice"""
        defopt.run(main, argv=['--foo', 'one'])
        defopt.run(main, argv=[])

    def test_subcommand(self):
        def sub1(foo):
            """:type foo: Choice"""
            self.assertEqual(foo, Choice.one)

        def sub2(bar):
            """:type bar: Choice"""
            self.assertEqual(bar, Choice.two)

        defopt.run(sub1, sub2, argv=['sub1', 'one'])
        defopt.run(sub1, sub2, argv=['sub2', 'two'])

    def test_valuedict(self):
        valuedict = defopt._ValueDict({'a': 1})
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
