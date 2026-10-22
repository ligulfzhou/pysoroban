from pysoroban import contract, public, u32


@contract
class ContractA:
    """u32 addition.

    Upstream uses checked_add and panics on overflow. u32 arithmetic here wraps,
    matching the rest of the PySoroban 32-bit integers.
    """

    @public
    def add(self, x: u32, y: u32) -> u32:
        return x + y
