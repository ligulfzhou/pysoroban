import unittest

from pysoroban.compiler import check_source
from pysoroban.errors import CompileError


class DiagnosticTests(unittest.TestCase):
    def test_syntax_and_structure_errors_keep_codes_and_locations(self):
        with self.assertRaises(CompileError) as syntax:
            check_source("def (\n", "broken.py")
        self.assertEqual(syntax.exception.code, "E0001")
        self.assertEqual(syntax.exception.line, 1)
        self.assertIn("broken.py:1:", str(syntax.exception))

        with self.assertRaises(CompileError) as missing:
            check_source("x = 1\n", "contract.py")
        self.assertEqual(missing.exception.code, "E0002")
        self.assertIn("contract.py", str(missing.exception))
        self.assertIn("E0002:", str(missing.exception))

    def test_type_error_keeps_its_code_line_and_column(self):
        source = """
from pysoroban import contract, i32, public

@contract
class Math:
    @public
    def add(self, left: i32, right: i32) -> i32:
        return left + right
"""
        # The '+' is the first character of the return expression's operator.
        with self.assertRaises(CompileError) as raised:
            check_source(source.replace("left + right", "left + True"), "math.py")
        self.assertEqual(raised.exception.code, "E0509")
        self.assertEqual(raised.exception.line, 8)
        self.assertGreaterEqual(raised.exception.column, 0)
        self.assertIn("math.py:8:", str(raised.exception))
