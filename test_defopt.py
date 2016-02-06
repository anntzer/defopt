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
            pass

        defopt.main(bad)
        with self.assertRaises(ValueError):
            defopt.run()

    def _def_main(self):
        def main(foo):
            self.assertEqual(foo, 'foo')
            self.calls += 1
        defopt.main(main)
        return ['foo']

    def _def_sub1(self):
        def sub1(*bar):
            self.assertEqual(bar, ('bar',))
            self.calls += 1
        defopt.subcommand(sub1)
        return ['sub1', 'bar']

    def _def_sub2(self):
        def sub2(baz=None):
            self.assertEqual(baz, 'baz')
            self.calls += 1
        defopt.subcommand(sub2)
        return ['sub2', '--baz', 'baz']
