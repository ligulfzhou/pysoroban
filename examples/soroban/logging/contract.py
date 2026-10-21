from pysoroban import String, Symbol, contract, log, public


@contract
class Contract:
    """logging example.

    The upstream contract formats the Symbol into the log. PySoroban log()
    takes a String and there is no Symbol-to-String conversion, so the message
    is the static text and the Symbol is accepted only to keep the signature.
    """

    @public
    def hello(self, value: Symbol) -> None:
        if value == Symbol("value"):
            log(String("Hello value"))
        else:
            log(String("Hello"))
