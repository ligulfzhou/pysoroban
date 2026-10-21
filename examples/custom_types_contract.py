from pysoroban import Address, Vec, contract, enum, public, struct, u32


@struct
class User:
    """A contract-defined record stored and returned as a Soroban map."""

    id: u32
    admin: Address


@enum
class Color:
    RED = 0
    GREEN = 1
    BLUE = 2


@contract
class CustomTypes:
    @public
    def make(self, id: u32, admin: Address) -> User:
        return User(id, admin)

    @public
    def admin_of(self, user: User) -> Address:
        return user.admin

    @public
    def paint(self, color: Color) -> Color:
        if color == Color.RED:
            return Color.BLUE
        return color

    @public
    def ids(self, users: Vec[User]) -> u32:
        if len(users) == 0:
            return u32(0)
        return users[0].id
