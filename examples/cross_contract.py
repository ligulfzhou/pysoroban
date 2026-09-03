from pysoroban import Address, Symbol, contract, i32, public


@contract
class MathProxy:
    @public
    def add_with(self, target: Address, left: i32, right: i32) -> i32:
        """Call add on another contract and return its result."""
        return target.call_i32(Symbol("add"), left, right)

    @public
    def sum_with(self, target: Address, stop: i32) -> i32:
        """Call sum_to on another contract."""
        return target.call_i32(Symbol("sum_to"), stop)
