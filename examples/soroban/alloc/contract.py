from pysoroban import contract, i32, public


@contract
class AllocContract:
    """Sum of 0 .. count.

    The upstream function allocates a Rust Vec with the global allocator and
    then sums it. PySoroban has no allocator API and range bounds are i32, so
    the sum is computed directly from an i32 count. The numeric result matches
    for counts that fit in i32.
    """

    @public
    def sum(self, count: i32) -> i32:
        total: i32 = 0
        for index in range(count):
            total = total + index
        return total
