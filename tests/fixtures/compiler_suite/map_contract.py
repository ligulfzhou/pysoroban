from pysoroban import Map, Symbol, boolean, contract, i32, public


@contract
class Scores:
    @public
    def score(self, scores: Map[Symbol, i32], player: Symbol) -> i32:
        return scores[player]

    @public
    def contains(self, scores: Map[Symbol, i32], player: Symbol) -> boolean:
        return scores.has(player)

    @public
    def count(self, scores: Map[Symbol, i32]) -> i32:
        return len(scores)

    @public
    def echo(self, scores: Map[Symbol, i32]) -> Map[Symbol, i32]:
        return scores
