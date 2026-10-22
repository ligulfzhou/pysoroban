from pysoroban import String, Vec, contract, public


@contract
class HelloContract:
    @public
    def hello(self, to: String) -> Vec[String]:
        result: Vec[String] = Vec()
        result.push(String("Hello"))
        result.push(to)
        return result
