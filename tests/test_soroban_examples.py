"""Behavioral tests for the stellar/soroban-examples ports."""

import unittest
from pathlib import Path

from pysoroban import compile_file
from pysoroban.testing import AuthorizationError, ContractError, ContractTest, InvocationError


ROOT = Path(__file__).resolve().parents[1]
SOROBAN = ROOT / "examples"

UPSTREAM = [
    "account", "alloc", "assets", "atomic_multiswap", "atomic_swap", "auth",
    "bls_signature", "cross_contract", "custom_types", "deep_contract_auth",
    "deployer", "errors", "eth_abi", "events", "fuzzing", "groth16_verifier",
    "hello_world", "import_ark_bn254", "increment", "increment_with_fuzz",
    "increment_with_pause", "liquidity_pool", "logging", "merkle_distribution",
    "mint-lock", "modular_account", "multisig_1_of_n_account", "other_custom_types",
    "pause", "privacy-pools", "simple_account", "single_offer", "timelock",
    "token", "ttl", "upgradeable_contract", "workspace",
]


def load(name: str) -> ContractTest:
    return ContractTest.from_file(SOROBAN / name / "contract.py")


def make_token(address: str) -> ContractTest:
    token = ContractTest.from_file(SOROBAN / "token" / "contract.py")
    token.contract_address = address
    token.invoke("__constructor", "GADMIN", 7, "Example", auth=["GADMIN"])
    return token


class SorobanExampleCoverageTests(unittest.TestCase):
    def test_every_upstream_example_is_ported_or_explained(self):
        for name in UPSTREAM:
            directory = SOROBAN / name
            self.assertTrue(directory.is_dir(), name)
            contracts = list(directory.rglob("contract.py"))
            readme = directory / "README.md"
            if contracts:
                for path in contracts:
                    compile_file(path)
            else:
                text = readme.read_text(encoding="utf-8")
                self.assertGreater(len(text), 40, name)

    def test_catalog_names_every_gap(self):
        catalog = (SOROBAN / "README.md").read_text(encoding="utf-8")
        for name in UPSTREAM:
            self.assertIn(name, catalog)


class SorobanExampleBehaviorTests(unittest.TestCase):
    def test_hello_increment_events_and_errors(self):
        hello = load("hello_world")
        self.assertEqual(hello.invoke("hello", "Ada"), ["Hello", "Ada"])

        counter = load("increment")
        self.assertEqual(counter.invoke("increment"), 1)
        self.assertEqual(counter.invoke("increment"), 2)
        self.assertEqual(counter.ttl_extensions[-1]["extend_to"], 100)

        fuzzed = load("increment_with_fuzz")
        self.assertEqual(fuzzed.invoke("increment"), 1)

        events = load("events")
        self.assertEqual(events.invoke("increment"), 1)
        self.assertEqual(events.last_events[0].data, 1)
        self.assertEqual(events.last_events[0].topics, ("increment",))

        limited = load("errors")
        for expected in range(1, 6):
            self.assertEqual(limited.invoke("increment"), expected)
        with self.assertRaises(ContractError):
            limited.invoke("increment")
        self.assertEqual(limited.storage["COUNTER"], 5)

        logged = load("logging")
        logged.invoke("hello", "value")
        self.assertEqual(logged.logs, ["Hello value"])

        total = load("alloc")
        self.assertEqual(total.invoke("sum", 10), 45)

    def test_auth_pause_and_cross_contract(self):
        auth = load("auth")
        self.assertEqual(auth.invoke("increment", "GALICE", 4, auth=["GALICE"]), 4)
        self.assertEqual(auth.invoke("increment", "GALICE", 3, auth=["GALICE"]), 7)
        with self.assertRaises(AuthorizationError):
            auth.invoke("increment", "GALICE", 1)

        pause = load("pause")
        gate = load("increment_with_pause")
        pause.contract_address = "CPAUSE"
        gate.register_contract("CPAUSE", pause)
        gate.invoke("__constructor", "CPAUSE")
        self.assertEqual(gate.invoke("increment"), 1)
        pause.invoke("set", True)
        with self.assertRaises(ContractError):
            gate.invoke("increment")
        self.assertEqual(gate.storage["COUNTER"], 1)

        math = ContractTest.from_file(SOROBAN / "cross_contract" / "contract_a" / "contract.py")
        proxy = ContractTest.from_file(SOROBAN / "cross_contract" / "contract_b" / "contract.py")
        math.contract_address = "CMATH"
        proxy.register_contract("CMATH", math)
        self.assertEqual(proxy.invoke("add_with", "CMATH", 20, 22), 42)

        left = ContractTest.from_file(SOROBAN / "workspace" / "contract_a" / "contract.py")
        right = ContractTest.from_file(SOROBAN / "workspace" / "contract_b" / "contract.py")
        left.contract_address = "CLEFT"
        right.register_contract("CLEFT", left)
        self.assertEqual(right.invoke("add_with", "CLEFT", 2, 3), 5)

    def test_types_ttl_deploy_and_upgrade(self):
        custom = load("custom_types")
        self.assertEqual(custom.invoke("increment", 4), 4)
        self.assertEqual(custom.invoke("get_state"), {"count": 4, "last_incr": 4})

        kinds = load("other_custom_types")
        self.assertEqual(kinds.invoke("u32_fail_on_even", 3), 3)
        with self.assertRaises(ContractError):
            kinds.invoke("u32_fail_on_even", 4)
        self.assertEqual(kinds.invoke("simple", 2), 2)
        self.assertEqual(kinds.invoke("inc"), 1)
        self.assertEqual(kinds.persistent["COUNTER"], 1)
        self.assertIsNone(kinds.invoke("woid"))
        kinds.invoke("auth", "GALICE", "world", auth=["GALICE"])
        self.assertEqual(kinds.last_events[0].data, "world")
        self.assertIsNone(kinds.invoke("option", None))
        self.assertEqual(kinds.invoke("option", 4), 4)
        self.assertEqual(kinds.invoke("tuple", ("leaf", 3)), ("leaf", 3))
        self.assertEqual(kinds.invoke("bytes_n", b"123456789"), b"123456789")
        self.assertEqual(kinds.invoke("u256_", 2**200), 2**200)
        self.assertEqual(kinds.invoke("val_", "raw"), "raw")
        self.assertEqual(kinds.invoke("odd", 3), ("ok", 3))
        self.assertEqual(kinds.invoke("odd", 4), ("err", 1))
        self.assertEqual(kinds.invoke("complex", ("union", "Void", ())), ("union", "Void", ()))
        claimed = ("union", "Struct", ({"a": 1, "b": True, "c": "z"},))
        self.assertEqual(kinds.invoke("complex", claimed), claimed)

        ttl = load("ttl")
        ttl.invoke("setup")
        ttl.invoke("extend_persistent")
        ttl.invoke("extend_instance")
        ttl.invoke("extend_temporary")
        self.assertEqual([item["extend_to"] for item in ttl.ttl_extensions], [5000, 10000, 7000])
        self.assertEqual(ttl.persistent["MyKey"], 0)
        self.assertEqual(ttl.storage["MyKey"], 1)
        self.assertEqual(ttl.temporary["MyKey"], 2)

        factory = ContractTest.from_file(SOROBAN / "deployer" / "deployer" / "contract.py")
        factory.invoke("__constructor", "GADMIN")
        with self.assertRaises(AuthorizationError):
            factory.invoke("deploy", b"hash", b"salt", 7)
        address = factory.invoke("deploy", b"hash", b"salt", 7, auth=["GADMIN"])
        self.assertEqual(address, factory.deployments[-1]["address"])
        self.assertEqual(factory.deployments[-1]["args"], (7,))

        upgraded = ContractTest.from_file(SOROBAN / "upgradeable_contract" / "old_contract" / "contract.py")
        upgraded.invoke("__constructor", "GADMIN")
        self.assertEqual(upgraded.invoke("version"), 1)
        upgraded.invoke("upgrade", b"wasm-v2", auth=["GADMIN"])
        self.assertEqual(upgraded.upgraded, b"wasm-v2")

        migrated = ContractTest.from_file(SOROBAN / "upgradeable_contract" / "new_contract" / "contract.py")
        migrated.invoke("__constructor", "GADMIN")
        migrated.invoke("handle_upgrade", auth=["GADMIN"])
        self.assertEqual(migrated.invoke("version"), 2)
        self.assertEqual(migrated.invoke("new_v2_fn"), 1010101)

    def test_atomic_swap_and_multiswap(self):
        token_a = make_token("CTA")
        token_b = make_token("CTB")
        token_a.invoke("mint", "GALICE", 100, auth=["GADMIN"])
        token_b.invoke("mint", "GBOB", 50, auth=["GADMIN"])
        swap = load("atomic_swap")
        swap.contract_address = "CSWAP"
        swap.register_contract("CTA", token_a)
        swap.register_contract("CTB", token_b)
        swap.invoke(
            "swap",
            "GALICE", "GBOB", "CTA", "CTB",
            100, 40, 50, 80,
            auth=["GALICE", "GBOB"],
        )
        self.assertEqual(token_a.invoke("balance", "GALICE"), 20)
        self.assertEqual(token_a.invoke("balance", "GBOB"), 80)
        self.assertEqual(token_b.invoke("balance", "GALICE"), 40)
        self.assertEqual(token_b.invoke("balance", "GBOB"), 10)
        self.assertEqual(token_a.invoke("balance", "CSWAP"), 0)

        multi = load("atomic_multiswap")
        multi.contract_address = "CMULTI"
        multi.register_contract("CSWAP", swap)
        token_a.invoke("mint", "GALICE", 100, auth=["GADMIN"])
        token_b.invoke("mint", "GBOB", 50, auth=["GADMIN"])
        spec_a = {"address": "GALICE", "amount": 100, "min_recv": 40}
        spec_b = {"address": "GBOB", "amount": 50, "min_recv": 80}
        multi.invoke(
            "multi_swap",
            "CSWAP", "CTA", "CTB",
            [spec_a], [spec_b],
            auth=["GALICE", "GBOB"],
        )
        self.assertEqual(token_a.invoke("balance", "GBOB"), 160)

    def test_timelock_and_single_offer(self):
        token = make_token("CTOK")
        token.invoke("mint", "GALICE", 50, auth=["GADMIN"])
        lock = load("timelock")
        lock.contract_address = "CLOCK"
        lock.ledger_timestamp = 100
        lock.register_contract("CTOK", token)
        lock.invoke(
            "deposit",
            "GALICE", "CTOK", 50, ["GBOB"],
            {"kind": 1, "timestamp": 90},
            auth=["GALICE"],
        )
        self.assertEqual(token.invoke("balance", "CLOCK"), 50)
        lock.invoke("claim", "GBOB", auth=["GBOB"])
        self.assertEqual(token.invoke("balance", "GBOB"), 50)
        self.assertNotIn("Balance", lock.storage)

        sell = make_token("CSELL")
        buy = make_token("CBUY")
        sell.invoke("mint", "GSELLER", 100, auth=["GADMIN"])
        buy.invoke("mint", "GBUYER", 10, auth=["GADMIN"])
        offer = load("single_offer")
        offer.contract_address = "COFFER"
        offer.register_contract("CSELL", sell)
        offer.register_contract("CBUY", buy)
        offer.invoke("create", "GSELLER", "CSELL", "CBUY", 1000, 100, auth=["GSELLER"])
        sell.invoke("transfer", "GSELLER", "COFFER", 100, auth=["GSELLER"])
        offer.invoke("trade", "GBUYER", 10, 100, auth=["GBUYER"])
        self.assertEqual(sell.invoke("balance", "GBUYER"), 100)
        self.assertEqual(buy.invoke("balance", "GSELLER"), 10)
        self.assertEqual(offer.invoke("get_offer")["sell_price"], 1000)

    def test_mint_lock_limit(self):
        token = ContractTest.from_file(SOROBAN / "token" / "contract.py")
        token.contract_address = "CTOKEN"
        # The token admin is the mint-lock contract, so its direct mint call is authorized.
        token.invoke("__constructor", "CMINTER", 7, "Limited", auth=["CMINTER"])
        locker = load("mint-lock")
        locker.contract_address = "CMINTER"
        locker.register_contract("CTOKEN", token)
        locker.ledger_sequence = 25
        locker.invoke("__constructor", "GADMIN")
        config = {"limit": 100, "epoch_length": 10}
        locker.invoke("set_minter", "CTOKEN", "GMINER", config, auth=["GADMIN"])
        info = locker.invoke("minter", "CTOKEN", "GMINER")
        self.assertEqual(info["epoch"], 2)
        locker.invoke("mint", "CTOKEN", "GMINER", "GALICE", 40, auth=["GMINER"])
        self.assertEqual(token.invoke("balance", "GALICE"), 40)
        with self.assertRaises(ContractError):
            locker.invoke("mint", "CTOKEN", "GMINER", "GALICE", 70, auth=["GMINER"])
        self.assertEqual(token.invoke("balance", "GALICE"), 40)
        self.assertTrue(locker.ttl_extensions)

    def test_liquidity_pool_deposit_swap_and_withdraw(self):
        token_a = make_token("CTA")
        token_b = make_token("CTB")
        token_a.invoke("mint", "GALICE", 5000, auth=["GADMIN"])
        token_b.invoke("mint", "GALICE", 5000, auth=["GADMIN"])
        pool = load("liquidity_pool")
        pool.contract_address = "CPOOL"
        pool.register_contract("CTA", token_a)
        pool.register_contract("CTB", token_b)
        pool.invoke("__constructor", "CTA", "CTB")
        pool.invoke("deposit", "GALICE", 1000, 0, 1000, 0, auth=["GALICE"])
        self.assertEqual(pool.invoke("balance_shares", "GALICE"), 1000)
        self.assertEqual(pool.invoke("get_rsrvs"), {"a": 1000, "b": 1000})
        pool.invoke("swap", "GALICE", True, 10, 100, auth=["GALICE"])
        self.assertEqual(pool.invoke("get_rsrvs"), {"a": 990, "b": 1011})
        self.assertEqual(token_a.invoke("balance", "GALICE"), 4010)
        withdrawn = pool.invoke("withdraw", "GALICE", 1000, 0, 0, auth=["GALICE"])
        self.assertEqual(withdrawn, {"a": 990, "b": 1011})
        self.assertEqual(pool.invoke("balance_shares", "GALICE"), 0)
        self.assertEqual(token_a.invoke("balance", "CPOOL"), 0)
        self.assertEqual(token_b.invoke("balance", "CPOOL"), 0)

    def test_merkle_distribution_claim(self):
        import hashlib

        token = make_token("CTOKEN")
        token.invoke("mint", "GFUNDER", 101, auth=["GADMIN"])
        helper = load("merkle_distribution")
        helper.contract_address = "CHELPER"
        helper.register_contract("CTOKEN", token)
        helper.invoke("__constructor", b"\x00" * 32, "CTOKEN", 1, "GFUNDER", auth=["GFUNDER"])
        first = helper.invoke("leaf_hash", 0, "GALICE", 40)
        second = helper.invoke("leaf_hash", 1, "GBOB", 60)
        merkle = load("merkle_distribution")
        merkle.contract_address = "CMERKLE"
        merkle.register_contract("CTOKEN", token)
        left, right = (first, second) if first < second else (second, first)
        root = hashlib.sha256(left + right).digest()
        merkle.invoke("__constructor", root, "CTOKEN", 100, "GFUNDER", auth=["GFUNDER"])
        self.assertEqual(token.invoke("balance", "CMERKLE"), 100)
        merkle.invoke("claim", 0, "GALICE", 40, [second], auth=["GALICE"])
        self.assertEqual(token.invoke("balance", "GALICE"), 40)
        with self.assertRaises(ContractError):
            merkle.invoke("claim", 0, "GALICE", 40, [second], auth=["GALICE"])
        with self.assertRaises(ContractError):
            merkle.invoke("claim", 1, "GBOB", 60, [b"\x00" * 32], auth=["GBOB"])
        self.assertEqual(token.invoke("balance", "CMERKLE"), 60)

    def test_eth_abi_adds_two_static_words(self):
        contract = load("eth_abi")
        word = b"\x01" * 32
        data = word + (1).to_bytes(32, "big") + (2).to_bytes(32, "big")
        self.assertEqual(contract.invoke("exec", data), word + (3).to_bytes(32, "big"))
        with self.assertRaises(ContractError) as raised:
            contract.invoke("exec", data[:-1])
        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(raised.exception.case, "DECODE")
        with self.assertRaises(ContractError):
            contract.invoke("exec", data + b"\x00")
        overflow = word + (2**256 - 1).to_bytes(32, "big") + (1).to_bytes(32, "big")
        with self.assertRaises(InvocationError):
            contract.invoke("exec", overflow)


if __name__ == "__main__":
    unittest.main()
