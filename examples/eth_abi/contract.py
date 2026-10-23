from pysoroban import Bytes, contract, error, fail, public, u256, u32


@error
class Error:
    DECODE = 1


@contract
class EthAbiContract:
    """Add two words from a static Ethereum ABI blob.

    Upstream decodes an alloy struct of ``bytes32``, ``uint256``, and
    ``uint256``. Those fields are static, so the encoding is three
    concatenated 32-byte words and has no offset header. A length other
    than 96 bytes fails with ``DECODE``. The sum uses checked ``u256``
    addition, so overflow traps instead of wrapping the way a Solidity
    ``uint256`` would. The result is the static encoding of the original
    ``bytes32`` and that sum. Dynamic ABI types, selectors, and a general
    decoder are not implemented.
    """

    @public
    def exec(self, data: Bytes) -> Bytes:
        if len(data) != 96:
            fail(Error.DECODE)
        word: Bytes = data.slice(u32(0), u32(32))
        left: u256 = u256.from_be_bytes(data.slice(u32(32), u32(64)))
        right: u256 = u256.from_be_bytes(data.slice(u32(64), u32(96)))
        total: u256 = left + right
        word.append(total.to_be_bytes())
        return word
