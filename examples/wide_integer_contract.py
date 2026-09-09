from pysoroban import Address, Map, Symbol, Topic, Vec, boolean, contract, event, events, i128, public, storage, u128


@event
class AmountRecorded:
    owner: Topic[Address]
    amount: i128


@contract
class WideIntegers:
    @public
    def echo_i128(self, value: i128) -> i128:
        return value

    @public
    def echo_u128(self, value: u128) -> u128:
        return value

    @public
    def minimum_i128(self) -> i128:
        return i128(-170141183460469231731687303715884105728)

    @public
    def maximum_u128(self) -> u128:
        return u128(340282366920938463463374607431768211455)

    @public
    def less_i128(self, left: i128, right: i128) -> boolean:
        return left < right

    @public
    def less_u128(self, left: u128, right: u128) -> boolean:
        return left < right

    @public
    def add_i128(self, left: i128, right: i128) -> i128:
        return left + right

    @public
    def subtract_i128(self, left: i128, right: i128) -> i128:
        return left - right

    @public
    def add_u128(self, left: u128, right: u128) -> u128:
        return left + right

    @public
    def subtract_u128(self, left: u128, right: u128) -> u128:
        return left - right

    @public
    def mul_div_floor(self, left: u128, right: u128, denominator: u128) -> u128:
        return u128.mul_div_floor(left, right, denominator)

    @public
    def composed_scale(self, left: u128, bonus: u128, right: u128, denominator: u128) -> u128:
        return u128.mul_div_floor(left + bonus, right, denominator)

    @public
    def echo_i128s(self, values: Vec[i128]) -> Vec[i128]:
        return values

    @public
    def lookup_u128(self, values: Map[Symbol, u128], key: Symbol) -> u128:
        return values[key]

    @public
    def record(self, owner: Address, amount: i128) -> i128:
        owner.require_auth()
        storage.instance.set(owner, amount)
        events.publish(AmountRecorded(owner, amount))
        return storage.instance.get_i128(owner)

    @public
    def remote_balance(self, token: Address, owner: Address) -> i128:
        return token.call_i128(Symbol("balance"), owner)
