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
        "errors": [
            {
                "name": error.name,
                "doc": error.doc,
                "cases": [
                    {"doc": case.doc, "name": case.name, "value": case.value}
                    for case in error.cases
                ],
            }
            for error in contract.errors
        ],
        "structs": [
            {
                "name": struct.name,
                "doc": struct.doc,
                "fields": [
                    {"doc": field.doc, "name": field.name, "type": field.type.value}
                    for field in struct.fields
                ],
            }
            for struct in contract.structs
        ],
        "enums": [
            {
                "name": enum.name,
                "doc": enum.doc,
                "cases": [
                    {"doc": case.doc, "name": case.name, "value": case.value}
                    for case in enum.cases
                ],
            }
            for enum in contract.enums
        ],
    }
