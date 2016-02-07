from enum import Enum
from importlib import reload
import unittest

import defopt


class TestDefopt(unittest.TestCase):
    def setUp(self):
        reload(defopt)
        self.calls = 0

    def test_main(self):
        args = self._def_main()
        defopt.run(args)
        self.assertEqual(self.calls, 1)

    def test_subcommands(self):
        sub1_args = self._def_sub1()
        sub2_args = self._def_sub2()
        defopt.run(sub1_args)
        defopt.run(sub2_args)
        self.assertEqual(self.calls, 2)

    def test_main_subcommands(self):
        main_args = self._def_main()
        sub1_args = self._def_sub1()
        sub2_args = self._def_sub2()
        defopt.run(main_args + sub1_args)
        defopt.run(main_args + sub2_args)
        self.assertEqual(self.calls, 4)

    def test_keyword_only(self):
        def main(*, foo='bar'):
            """Test function

            :type foo: str
            """
            self.assertEqual(foo, 'baz')
            self.calls += 1
        defopt.main(main)
        defopt.run(['--foo', 'baz'])
        self.assertEqual(self.calls, 1)

    def test_double_main(self):
        self._def_main()
        with self.assertRaises(Exception):
            self._def_main()

    def test_var_keywords(self):
        def bad(**kwargs):
            """Test function

            :type kwargs: str
            """
            pass

        defopt.main(bad)
        with self.assertRaises(ValueError):
            defopt.run()

    def test_no_subparser_specified(self):
        args = self._def_main()
        self._def_sub1()
        with self.assertRaises(SystemExit):
            defopt.run(args)

    def _def_main(self):
        def main(foo):
            """Test function

            :type foo: str
            :return: None
            """
            self.assertEqual(foo, 'foo')
            self.calls += 1
        defopt.main(main)
        return ['foo']

    def _def_sub1(self):
        def sub1(*bar):
            """Test function

            :type bar: int
            """
            self.assertEqual(bar, (1,))
            self.calls += 1
        defopt.subcommand(sub1)
        return ['sub1', '1']

    def _def_sub2(self):
        def sub2(baz=None):
            """Test function

            :type baz: float
            """
            self.assertEqual(baz, 1.1)
            self.calls += 1
        defopt.subcommand(sub2)
        return ['sub2', '--baz', '1.1']


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
        reload(defopt)

    def test_parser(self):
        @defopt.main
        def main(value):
            """Test function

            :type value: int
            """
            self.assertEqual(value, 1)
        defopt.run(['1'])

    def test_registered_parser(self):
        @defopt.parser(int)
        def parser(string):
            return int(string) * 2

        @defopt.main
        def main(value):
            """Test function

            :type value: int
            """
            self.assertEqual(value, 2)
        defopt.run(['1'])

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
        @defopt.main
        def main(foo):
            """Test function

            :type foo: list[float]
            """
            self.assertEqual(foo, [1.1, 2.2])
        defopt.run(['--foo', '1.1', '2.2'])

    def test_other_container(self):
        @defopt.main
        def main(foo):
            """Test function

            :type foo: tuple[float]
            """
        with self.assertRaises(ValueError):
            defopt.run(['--foo', '1.1', '2.2'])

    def test_list_bare(self):
        with self.assertRaises(ValueError):
            defopt._get_parser(list)


class TestEnums(unittest.TestCase):
    def setUp(self):
        reload(defopt)

    def test_enum(self):
        @defopt.main
        def main(foo):
            """Test function

            :type foo: Choice
            """
        defopt.run(['one'])
        defopt.run(['two'])
        with self.assertRaises(SystemExit):
            defopt.run(['three'])


class Choice(Enum):
    one = 1
    two = 2
