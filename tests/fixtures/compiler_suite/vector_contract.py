from pysoroban import Vec, contract, i32, public


@contract
class VectorMath:
    @public
    def count(self, values: Vec[i32]) -> i32:
        return len(values)

    @public
    def first(self, values: Vec[i32]) -> i32:
        return values[0]

    @public
    def sum(self, values: Vec[i32]) -> i32:
        total: i32 = 0
        for index in range(len(values)):
            total = total + values[index]
        return total

    @public
    def echo(self, values: Vec[i32]) -> Vec[i32]:
        return values
