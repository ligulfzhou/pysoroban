"""Custom-account __check_auth and authorize_as_current_contract."""

import unittest

from pysoroban.testing import AuthorizationError, ContractError, ContractTest


ROOT = "examples"
KEY_A = b"\x01" + b"\x00" * 31
KEY_B = b"\x02" + b"\x00" * 31
PAYLOAD = b"\x11" * 32
SIG_A = b"\x21" * 64
SIG_B = b"\x22" * 64

SPENDER = """
from pysoroban import Address, contract, public

@contract
class Spender:
    @public
    def go(self, account: Address) -> None:
        account.require_auth()
"""


def transfer_context(amount: int):
    return ("union", "Contract", ({
        "contract": "CTOKEN",
        "fn_name": "transfer",
        "args": ["CACCOUNT", "GDEST", amount],
    },))


class AccountTests(unittest.TestCase):
    def test_simple_account_verifies_the_owner_signature(self):
        account = ContractTest.from_file(f"{ROOT}/simple_account/contract.py")
        account.contract_address = "CACCOUNT"
        account.invoke("initialize", KEY_A)
        with self.assertRaises(ContractError):
            account.invoke("initialize", KEY_B)
        account.allow_signature(KEY_A, PAYLOAD, SIG_A)
        spender = ContractTest.from_source(SPENDER)
        spender.register_contract("CACCOUNT", account)
        spender.authorize_account("CACCOUNT", PAYLOAD, SIG_A)
        spender.invoke("go", "CACCOUNT")
        spender.authorize_account("CACCOUNT", PAYLOAD, SIG_B)
        with self.assertRaises(AuthorizationError):
            spender.invoke("go", "CACCOUNT")

    def test_multisig_accepts_one_configured_signer(self):
        account = ContractTest.from_file(f"{ROOT}/multisig_1_of_n_account/contract.py")
        account.contract_address = "CACCOUNT"
        account.invoke("initialize", [KEY_A, KEY_B])
        account.allow_signature(KEY_B, PAYLOAD, SIG_B)
        spender = ContractTest.from_source(SPENDER)
        spender.register_contract("CACCOUNT", account)
        signature = {"public_key": KEY_B, "signature": SIG_B}
        spender.authorize_account("CACCOUNT", PAYLOAD, signature)
        spender.invoke("go", "CACCOUNT")
        unknown = {"public_key": b"\x09" + b"\x00" * 31, "signature": SIG_A}
        spender.authorize_account("CACCOUNT", PAYLOAD, unknown)
        with self.assertRaises(AuthorizationError):
            spender.invoke("go", "CACCOUNT")

    def test_account_spend_limit_uses_the_supplied_context(self):
        account = ContractTest.from_file(f"{ROOT}/account/contract.py")
        account.contract_address = "CACCOUNT"
        account.invoke("initialize", [KEY_A, KEY_B])
        account.allow_signature(KEY_A, PAYLOAD, SIG_A)
        account.allow_signature(KEY_B, PAYLOAD, SIG_B)
        both = [
            {"public_key": KEY_A, "signature": SIG_A},
            {"public_key": KEY_B, "signature": SIG_B},
        ]
        account.authorize_account("CACCOUNT", PAYLOAD, both)
        account.invoke("add_limit", "CTOKEN", 30)
        spender = ContractTest.from_source(SPENDER)
        spender.register_contract("CACCOUNT", account)
        one = [{"public_key": KEY_A, "signature": SIG_A}]
        spender.authorize_account("CACCOUNT", PAYLOAD, one, [transfer_context(20)])
        spender.invoke("go", "CACCOUNT")
        spender.authorize_account("CACCOUNT", PAYLOAD, one, [transfer_context(40)])
        with self.assertRaises(AuthorizationError):
            spender.invoke("go", "CACCOUNT")
        reversed_sigs = [
            {"public_key": KEY_B, "signature": SIG_B},
            {"public_key": KEY_A, "signature": SIG_A},
        ]
        spender.authorize_account("CACCOUNT", PAYLOAD, reversed_sigs, [transfer_context(1)])
        with self.assertRaises(AuthorizationError):
            spender.invoke("go", "CACCOUNT")

    def test_deep_contract_auth_authorizes_only_the_named_subcall(self):
        contract_a = ContractTest.from_file(f"{ROOT}/deep_contract_auth/contract_a/contract.py")
        contract_b = ContractTest.from_file(f"{ROOT}/deep_contract_auth/contract_b/contract.py")
        contract_c = ContractTest.from_file(f"{ROOT}/deep_contract_auth/contract_c/contract.py")
        contract_a.contract_address = "CA"
        contract_b.contract_address = "CB"
        contract_c.contract_address = "CC"
        contract_a.register_contract("CB", contract_b)
        contract_b.register_contract("CC", contract_c)
        contract_a.invoke("call_b", "CB", "CC")

        direct = ContractTest.from_source(
            """
from pysoroban import Address, Symbol, contract, env, public

@contract
class Direct:
    @public
    def call_b(self, contract_b: Address, contract_c: Address) -> None:
        me: Address = env.current_contract_address()
        contract_b.call_void(Symbol("authorized_fn_b"), me, contract_c)
"""
        )
        direct.contract_address = "CA"
        direct.register_contract("CB", contract_b)
        with self.assertRaises(AuthorizationError):
            direct.invoke("call_b", "CB", "CC")


if __name__ == "__main__":
    unittest.main()
