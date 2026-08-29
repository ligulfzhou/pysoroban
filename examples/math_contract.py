from pysoroban import boolean, contract, i32, public


@contract
class Math:
    @public
    def add(self, left: i32, right: i32) -> i32:
        """Add two signed 32-bit integers."""
        return left + right

    @public
    def max(self, left: i32, right: i32) -> i32:
        if left > right:
            return left
        return right

    @public
    def is_positive(self, value: i32) -> boolean:
        return value > 0

