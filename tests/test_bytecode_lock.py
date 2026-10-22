"""Lock Wasm bytes for the language surface that milestone 2 did not edit.

Hashes were captured from compiler 0.9.0a2 before contract errors existed.
Contracts whose source did not change must keep those bytes. The AMM kernel
is omitted here because its source now fails instead of returning zero; its
new bytes are covered by the deterministic build test.

The locked sources used to live as flat files under examples/. They now live
in tests/fixtures/compiler_suite/ so examples/ is only the soroban-examples
ports. The bytes stay locked because the fixture text is unchanged.
"""

import hashlib
import unittest
from pathlib import Path

from pysoroban import compile_file, compile_source


ROOT = Path(__file__).resolve().parents[1]

# sha256 of protocol-25 Wasm for each unchanged example.
EXAMPLE_SHA256 = {
    "counter_contract.py": "28e4105e5398a847d60f08aab26c9bdeadd3387c8e7d50ba6244076d50aeb01b",
    "cross_contract.py": "3d4cb2df0d1df69bceccf4579fb51566dd5cfe190437837722b7b959d59731a2",
    "map_contract.py": "a369c4bd3cd81840a1f01d601f48d975f8d222179e3dd41abebb7101d184da02",
    "math_contract.py": "bafa5a29c0ea41043364778d70e13b3059230166971758f25a031f1ab3ddd879",
    "typed_events_contract.py": "47fdf85ed49b0842eeebeca73f1dd4cd057a4d0ab2f56b63e42961852e3b08d3",
    "vector_contract.py": "f82806d9bd358c58e0ff59751145c0ad9998631f59c2c2b4ef9bd4c294067c3d",
    "void_call_contract.py": "40ff5f54bd8574ac402de5511a5a0ca73c8f1fca23fff66a6703b8f06559c3b1",
    "wide_integer_contract.py": "23b68120596540110facef4969e6830c838b94bf9429c12e034a4a0a3bd05759",
}

INTEGER_CORPUS = {
    "i32_wrap": (
        """
from pysoroban import contract, i32, public
@contract
class T:
    @public
    def add(self, left: i32, right: i32) -> i32:
        return left + right
""",
        "e26d26c24b3d07df25b7bf5c38b54c3c9be8a32841e378e1b5904c733a1ecb4e",
    ),
    "u32_div": (
        """
from pysoroban import contract, public, u32
@contract
class T:
    @public
    def div(self, left: u32, right: u32) -> u32:
        return left // right
""",
        "6d424c152910de52f2b13687f07c35458c4b42c4c9072f45b641930ff3b14904",
    ),
    "u128_add": (
        """
from pysoroban import contract, public, u128
@contract
class T:
    @public
    def add(self, left: u128, right: u128) -> u128:
        return left + right
""",
        "97a496e6f1ef697922a9dff0c8d99d5b71e6719cbbeefcbaaf66ff5fa0cd5182",
    ),
    "u128_mul_div": (
        """
from pysoroban import contract, public, u128
@contract
class T:
    @public
    def scale(self, left: u128, right: u128, denominator: u128) -> u128:
        return u128.mul_div_floor(left, right, denominator)
""",
        "b9a9b981fb4babbb59524d8cecd8c8c124d6ef47c420e971c480363dcde8e659",
    ),
}


class BytecodeLockTests(unittest.TestCase):
    def test_unchanged_examples_keep_their_wasm(self):
        for name, expected in EXAMPLE_SHA256.items():
            wasm = compile_file(ROOT / "tests" / "fixtures" / "compiler_suite" / name).wasm
            actual = hashlib.sha256(wasm).hexdigest()
            self.assertEqual(actual, expected, name)

    def test_integer_semantics_keep_their_wasm(self):
        for name, (source, expected) in INTEGER_CORPUS.items():
            wasm = compile_source(source, name).wasm
            actual = hashlib.sha256(wasm).hexdigest()
            self.assertEqual(actual, expected, name)
