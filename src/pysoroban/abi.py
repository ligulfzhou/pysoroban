"""Stable, JSON-serializable descriptions of checked PySoroban contracts."""

from .model import Contract


def contract_abi(contract: Contract) -> dict:
    return {
        "contract": contract.name,
        "functions": [
            {
                "name": function.name,
                "doc": function.doc,
                "inputs": [
                    {"name": param.name, "type": param.type.value}
                    for param in function.params
                ],
                "outputs": [] if function.result.value == "void" else [function.result.value],
            }
            for function in contract.functions
        ],
        "events": [
            {
                "name": event.name,
                "doc": event.doc,
                "prefix_topics": [event.prefix],
                "topics": [
                    {"name": field.name, "type": field.type.value}
                    for field in event.fields if field.topic
                ],
                "data": [
                    {"name": field.name, "type": field.type.value}
                    for field in event.fields if not field.topic
                ],
                "data_format": "single-value",
            }
            for event in contract.events
        ],
    }
