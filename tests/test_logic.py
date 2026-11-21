from itertools import product
import unittest

from wirestep.logic import gate_value
from wirestep.model import WirestepError
from tests.helpers import boolean_possibilities


class LogicTests(unittest.TestCase):
    def test_unary_gates_match_all_binary_possibilities(self):
        for operation in ("BUF", "NOT"):
            for value in ("0", "1", "X"):
                with self.subTest(operation=operation, value=value):
                    self.assertEqual(gate_value(operation, [value]),
                                     boolean_possibilities(operation, [value]))

    def test_multi_input_gates_match_all_ternary_vectors_through_four_inputs(self):
        for operation in ("AND", "OR", "XOR", "NAND", "NOR", "XNOR"):
            for width in (2, 3, 4):
                for values in product("01X", repeat=width):
                    with self.subTest(operation=operation, values=values):
                        self.assertEqual(gate_value(operation, values),
                                         boolean_possibilities(operation, values))

    def test_sixteen_input_boundary_handles_parity_and_controlling_values(self):
        vectors = [["0"] * 16, ["1"] * 16, ["1"] * 15 + ["0"],
                   ["X", "0"] + ["1"] * 14, ["X", "1"] + ["0"] * 14]
        for operation in ("AND", "OR", "XOR", "NAND", "NOR", "XNOR"):
            for values in vectors:
                with self.subTest(operation=operation, values=values):
                    self.assertEqual(gate_value(operation, values),
                                     boolean_possibilities(operation, values))

    def test_unknown_values_are_not_treated_as_symbolically_correlated(self):
        self.assertEqual(gate_value("XOR", ["X", "X"]), "X")
        self.assertEqual(gate_value("XNOR", ["X", "X"]), "X")

    def test_invalid_operation_arity_and_values_raise_domain_errors(self):
        cases = [("unknown", ["0", "1"]), ("and", ["0", "1"]),
                 ("BUF", []), ("BUF", ["0", "1"]), ("AND", ["0"]),
                 ("XOR", ["0"] * 17), ("OR", ["0", "Z"]),
                 ("NOT", [True]), ("AND", [0, 1]), ("NOT", [None])]
        for operation, values in cases:
            with self.subTest(operation=operation, values=values):
                with self.assertRaises(WirestepError):
                    gate_value(operation, values)


if __name__ == "__main__":
    unittest.main()
