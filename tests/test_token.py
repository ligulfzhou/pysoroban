import unittest

from pysoroban.testing import AuthorizationError, ContractError, ContractTest


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.token = ContractTest.from_file("examples/token_contract.py")
        self.token.invoke(
            "initialize",
            "GADMIN",
            7,
            "Example",
            auth=["GADMIN"],
        )

    def test_mint_transfer_and_allowance(self):
        self.token.invoke("mint", "GALICE", 1000, auth=["GADMIN"])
        self.assertEqual(self.token.invoke("balance", "GALICE"), 1000)
        self.token.invoke("transfer", "GALICE", "GBOB", 40, auth=["GALICE"])
        self.assertEqual(self.token.invoke("balance", "GALICE"), 960)
        self.assertEqual(self.token.invoke("balance", "GBOB"), 40)
        self.token.invoke("approve", "GALICE", "GSPEND", 25, auth=["GALICE"])
        self.token.invoke("transfer_from", "GSPEND", "GALICE", "GBOB", 25, auth=["GSPEND"])
        self.assertEqual(self.token.invoke("balance", "GBOB"), 65)
        self.assertEqual(self.token.invoke("allowance", "GALICE", "GSPEND"), 0)
        self.assertEqual(self.token.invoke("decimals"), 7)
        self.assertEqual(self.token.invoke("name"), "Example")

    def test_rejected_transfer_does_not_move_balance(self):
        self.token.invoke("mint", "GALICE", 10, auth=["GADMIN"])
        with self.assertRaises(ContractError):
            self.token.invoke("transfer", "GALICE", "GBOB", 11, auth=["GALICE"])
        self.assertEqual(self.token.invoke("balance", "GALICE"), 10)
        self.assertEqual(self.token.invoke("balance", "GBOB"), 0)
        with self.assertRaises(AuthorizationError):
            self.token.invoke("mint", "GALICE", 1)


if __name__ == "__main__":
    unittest.main()
