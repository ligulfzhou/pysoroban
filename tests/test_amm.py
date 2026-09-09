import unittest
from pathlib import Path

from pysoroban import compile_file
from pysoroban.testing import AuthorizationError, ContractTest, Event, InvocationError


ROOT = Path(__file__).resolve().parents[1]
AMM = ROOT / "examples" / "amm_kernel_contract.py"


class AmmKernelTests(unittest.TestCase):
    def test_compiles_to_deterministic_soroban_wasm(self):
        first = compile_file(AMM)
        second = compile_file(AMM)
        self.assertEqual(first.wasm, second.wasm)
        self.assertEqual(
            [function.name for function in first.contract.functions],
            ["initialize", "quote", "swap_a_for_b", "reserve_a", "reserve_b", "total_shares"],
        )

    def test_quotes_constant_product_swap_with_fee(self):
        amm = ContractTest.from_file(AMM)
        self.assertEqual(amm.invoke("quote", 100, 1_000, 1_000), 90)
        self.assertEqual(amm.invoke("quote", 0, 1_000, 1_000), 0)

    def test_quotes_with_a_product_larger_than_u128(self):
        amm = ContractTest.from_file(AMM)
        amount_in = 2**80
        reserve_in = 2**100
        reserve_out = 2**100
        expected = (amount_in * 997 * reserve_out) // (reserve_in * 1000 + amount_in * 997)
        self.assertGreater(amount_in * 997 * reserve_out, 2**128)
        self.assertEqual(amm.invoke("quote", amount_in, reserve_in, reserve_out), expected)

    def test_initializes_once_with_authorization(self):
        amm = ContractTest.from_file(AMM)
        with self.assertRaises(AuthorizationError):
            amm.invoke("initialize", "provider", 1_000, 1_000)
        self.assertEqual(amm.invoke("initialize", "provider", 1_000, 1_000, auth={"provider"}), 1_000)
        self.assertEqual(amm.last_events, (Event(("pool_initialized", "provider"), 1_000),))
        self.assertEqual(amm.invoke("reserve_a"), 1_000)
        self.assertEqual(amm.invoke("reserve_b"), 1_000)
        self.assertEqual(amm.invoke("total_shares"), 1_000)
        self.assertEqual(amm.invoke("initialize", "provider", 5, 7, auth={"provider"}), 0)

    def test_swap_enforces_minimum_output_before_state_change(self):
        amm = ContractTest.from_file(AMM)
        amm.invoke("initialize", "provider", 1_000, 1_000, auth={"provider"})

        self.assertEqual(amm.invoke("swap_a_for_b", "trader", 100, 91, auth={"trader"}), 0)
        self.assertEqual((amm.invoke("reserve_a"), amm.invoke("reserve_b")), (1_000, 1_000))

        amount_out = amm.invoke("swap_a_for_b", "trader", 100, 90, auth={"trader"})
        self.assertEqual(amount_out, 90)
        self.assertEqual(amm.last_events, (Event(("swapped", "trader"), 90),))
        self.assertEqual((amm.invoke("reserve_a"), amm.invoke("reserve_b")), (1_100, 910))
        self.assertGreaterEqual(1_100 * 910, 1_000 * 1_000)

    def test_large_swap_preserves_constant_product(self):
        amm = ContractTest.from_file(AMM)
        reserve = 2**100
        amount_in = 2**80
        amm.invoke("initialize", "provider", reserve, reserve, auth={"provider"})
        expected = (amount_in * 997 * reserve) // (reserve * 1000 + amount_in * 997)

        amount_out = amm.invoke("swap_a_for_b", "trader", amount_in, expected, auth={"trader"})
        updated_a = reserve + amount_in
        updated_b = reserve - amount_out
        self.assertEqual(amount_out, expected)
        self.assertEqual((amm.invoke("reserve_a"), amm.invoke("reserve_b")), (updated_a, updated_b))
        self.assertGreaterEqual(updated_a * updated_b, reserve * reserve)

    def test_arithmetic_trap_leaves_reserves_unchanged(self):
        amm = ContractTest.from_file(AMM)
        reserve = 1_000
        amm.invoke("initialize", "provider", reserve, reserve, auth={"provider"})
        before = dict(amm.storage)

        with self.assertRaisesRegex(InvocationError, "result overflow"):
            amm.invoke("swap_a_for_b", "trader", 2**128 - 1, 0, auth={"trader"})

        self.assertEqual(dict(amm.storage), before)
        self.assertEqual(amm.last_events, ())


if __name__ == "__main__":
    unittest.main()
