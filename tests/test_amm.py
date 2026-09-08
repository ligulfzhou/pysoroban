import unittest
from pathlib import Path

from pysoroban import compile_file
from pysoroban.testing import AuthorizationError, ContractTest, Event


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


if __name__ == "__main__":
    unittest.main()
