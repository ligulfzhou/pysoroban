from pysoroban import Address, Symbol, contract, env, error, fail, public, storage, struct, u128


@error
class OfferError:
    ALREADY_CREATED = 1
    ZERO_PRICE = 2
    PRICE_TOO_LOW = 3


@struct
class Offer:
    seller: Address
    sell_token: Address
    buy_token: Address
    sell_price: u128
    buy_price: u128


@contract
class SingleOffer:
    """One seller, many buyers, constant price.

    Prices and amounts are u128 so the quote can use mul_div_floor. Upstream
    stores prices as u32 and amounts as i128. Struct fields are replaced by
    constructing a new Offer because field assignment is not supported.
    """

    @public
    def create(
        self,
        seller: Address,
        sell_token: Address,
        buy_token: Address,
        sell_price: u128,
        buy_price: u128,
    ) -> None:
        if storage.instance.has(Symbol("offer")):
            fail(OfferError.ALREADY_CREATED)
        if buy_price == u128(0):
            fail(OfferError.ZERO_PRICE)
        if sell_price == u128(0):
            fail(OfferError.ZERO_PRICE)
        seller.require_auth()
        storage.instance.set(
            Symbol("offer"),
            Offer(seller, sell_token, buy_token, sell_price, buy_price),
        )

    @public
    def trade(self, buyer: Address, buy_token_amount: u128, min_sell_token_amount: u128) -> None:
        buyer.require_auth()
        offer: Offer = storage.instance.get(Symbol("offer"), Offer)
        sell_token_amount: u128 = u128.mul_div_floor(buy_token_amount, offer.sell_price, offer.buy_price)
        if sell_token_amount < min_sell_token_amount:
            fail(OfferError.PRICE_TOO_LOW)
        me: Address = env.current_contract_address()
        buy_token: Address = offer.buy_token
        sell_token: Address = offer.sell_token
        seller: Address = offer.seller
        buy_token.call_void(Symbol("transfer"), buyer, me, buy_token_amount)
        sell_token.call_void(Symbol("transfer"), me, buyer, sell_token_amount)
        buy_token.call_void(Symbol("transfer"), me, seller, buy_token_amount)

    @public
    def withdraw(self, token: Address, amount: u128) -> None:
        offer: Offer = storage.instance.get(Symbol("offer"), Offer)
        seller: Address = offer.seller
        seller.require_auth()
        token.call_void(Symbol("transfer"), env.current_contract_address(), seller, amount)

    @public
    def updt_price(self, sell_price: u128, buy_price: u128) -> None:
        if buy_price == u128(0):
            fail(OfferError.ZERO_PRICE)
        if sell_price == u128(0):
            fail(OfferError.ZERO_PRICE)
        offer: Offer = storage.instance.get(Symbol("offer"), Offer)
        seller: Address = offer.seller
        seller.require_auth()
        storage.instance.set(
            Symbol("offer"),
            Offer(offer.seller, offer.sell_token, offer.buy_token, sell_price, buy_price),
        )

    @public
    def get_offer(self) -> Offer:
        return storage.instance.get(Symbol("offer"), Offer)
