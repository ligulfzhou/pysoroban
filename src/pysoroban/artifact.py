"""Inspect and structurally validate PySoroban-generated Wasm artifacts."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Dict, List, Tuple, Union


WASM_HEADER = b"\x00asm\x01\x00\x00\x00"
REQUIRED_CUSTOM_SECTIONS = (
    "contractenvmetav0",
    "contractspecv0",
    "contractmetav0",
)

SECTION_NAMES = {
    0: "custom",
    1: "type",
    2: "import",
    3: "function",
    4: "table",
    5: "memory",
    6: "global",
    7: "export",
    8: "start",
    9: "element",
    10: "code",
    11: "data",
    12: "data_count",
    13: "tag",
}

# Section 13 (tag) precedes globals, and data-count precedes code, despite
# their numeric IDs. Custom sections may appear anywhere.
SECTION_ORDER = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    13: 6,
    6: 7,
    7: 8,
    8: 9,
    9: 10,
    12: 11,
    10: 12,
    11: 13,
}

SPEC_TYPE_NAMES = {
    1: "boolean",
    2: "void",
    4: "u32",
    5: "i32",
    6: "u64",
    7: "i64",
    10: "u128",
    11: "i128",
    14: "Bytes",
    16: "String",
    17: "Symbol",
    19: "Address",
}


class ArtifactError(ValueError):
    """A malformed or unsupported PySoroban Wasm artifact."""


@dataclass(frozen=True)
class Section:
    id: int
    payload: bytes


def _read_uleb(data: bytes, offset: int) -> Tuple[int, int]:
    value = 0
    shift = 0
    start = offset
    while offset < len(data) and shift < 35:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if value > 0xFFFFFFFF:
                raise ArtifactError("unsigned LEB128 value exceeds u32")
            return value, offset
        shift += 7
    if offset >= len(data):
        raise ArtifactError("truncated unsigned LEB128 value")
    raise ArtifactError(f"invalid unsigned LEB128 value at byte {start}")


def _read_name(data: bytes, offset: int) -> Tuple[str, int]:
    length, offset = _read_uleb(data, offset)
    end = offset + length
    if end > len(data):
        raise ArtifactError("truncated Wasm name")
    try:
        return data[offset:end].decode("utf-8"), end
    except UnicodeDecodeError as exc:
        raise ArtifactError("Wasm name is not valid UTF-8") from exc


def _parse_sections(data: bytes) -> Tuple[Section, ...]:
    if data[:8] != WASM_HEADER:
        raise ArtifactError("not a WebAssembly 1 binary")

    sections: List[Section] = []
    offset = 8
    seen = set()
    previous_order = 0
    while offset < len(data):
        section_id = data[offset]
        offset += 1
        if section_id not in SECTION_NAMES:
            raise ArtifactError(f"unknown Wasm section id {section_id}")
        size, offset = _read_uleb(data, offset)
        end = offset + size
        if end > len(data):
            raise ArtifactError(f"truncated {SECTION_NAMES[section_id]} section")
        if section_id:
            if section_id in seen:
                raise ArtifactError(f"duplicate {SECTION_NAMES[section_id]} section")
            order = SECTION_ORDER[section_id]
            if order <= previous_order:
                raise ArtifactError(f"{SECTION_NAMES[section_id]} section is out of order")
            seen.add(section_id)
            previous_order = order
        sections.append(Section(section_id, data[offset:end]))
        offset = end
    return tuple(sections)


class _XdrReader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.offset

    def u32(self) -> int:
        if self.remaining < 4:
            raise ArtifactError("truncated contract XDR")
        value = struct.unpack_from(">I", self.data, self.offset)[0]
        self.offset += 4
        return value

    def string(self) -> str:
        length = self.u32()
        end = self.offset + length
        padded_end = end + (-length % 4)
        if padded_end > len(self.data):
            raise ArtifactError("truncated contract XDR string")
        raw = self.data[self.offset:end]
        padding = self.data[end:padded_end]
        if any(padding):
            raise ArtifactError("non-zero contract XDR string padding")
        self.offset = padded_end
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ArtifactError("contract XDR string is not valid UTF-8") from exc


def _custom_sections(sections: Tuple[Section, ...]) -> Dict[str, bytes]:
    result: Dict[str, bytes] = {}
    for section in sections:
        if section.id != 0:
            continue
        name, offset = _read_name(section.payload, 0)
        if name in result:
            raise ArtifactError(f"duplicate custom section {name!r}")
        result[name] = section.payload[offset:]
    missing = [name for name in REQUIRED_CUSTOM_SECTIONS if name not in result]
    if missing:
        raise ArtifactError("missing Soroban custom section(s): " + ", ".join(missing))
    return result


def _read_spec_type(reader: _XdrReader) -> str:
    kind = reader.u32()
    if kind == 1002:
        return "Vec[{}]".format(_read_spec_type(reader))
    if kind == 1004:
        return "Map[{}, {}]".format(_read_spec_type(reader), _read_spec_type(reader))
    if kind not in SPEC_TYPE_NAMES:
        raise ArtifactError(f"unsupported contract spec type {kind}")
    return SPEC_TYPE_NAMES[kind]


def _contract_spec(data: bytes) -> Tuple[List[dict], List[dict]]:
    reader = _XdrReader(data)
    functions = []
    events = []
    while reader.remaining:
        entry_kind = reader.u32()
        if entry_kind == 0:
            doc = reader.string()
            name = reader.string()
            inputs = []
            for _ in range(reader.u32()):
                reader.string()  # parameter documentation
                input_name = reader.string()
                inputs.append({"name": input_name, "type": _read_spec_type(reader)})
            outputs = [_read_spec_type(reader) for _ in range(reader.u32())]
            functions.append({"name": name, "doc": doc, "inputs": inputs, "outputs": outputs})
            continue
        if entry_kind == 5:
            doc = reader.string()
            reader.string()  # library
            name = reader.string()
            prefix_topics = [reader.string() for _ in range(reader.u32())]
            topics = []
            event_data = []
            for _ in range(reader.u32()):
                reader.string()  # field documentation
                field_name = reader.string()
                field = {"name": field_name, "type": _read_spec_type(reader)}
                (topics if reader.u32() else event_data).append(field)
            data_format = reader.u32()
            if data_format != 0:
                raise ArtifactError(f"unsupported event data format {data_format}")
            events.append({
                "name": name,
                "doc": doc,
                "prefix_topics": prefix_topics,
                "topics": topics,
                "data": event_data,
                "data_format": "single-value",
            })
            continue
        raise ArtifactError(f"unsupported contract spec entry {entry_kind}")
    return functions, events


def _environment_protocol(data: bytes) -> int:
    reader = _XdrReader(data)
    if reader.u32() != 0:
        raise ArtifactError("unsupported contract environment metadata entry")
    protocol = reader.u32()
    reader.u32()  # pre-release protocol
    if reader.remaining:
        raise ArtifactError("unexpected trailing contract environment metadata")
    return protocol


def _contract_metadata(data: bytes) -> Dict[str, str]:
    reader = _XdrReader(data)
    result = {}
    while reader.remaining:
        if reader.u32() != 0:
            raise ArtifactError("unsupported contract metadata entry")
        key = reader.string()
        result[key] = reader.string()
    return result


def _section_payload(sections: Tuple[Section, ...], section_id: int) -> bytes:
    return next((section.payload for section in sections if section.id == section_id), b"")


def _parse_imports(data: bytes) -> List[dict]:
    if not data:
        return []
    count, offset = _read_uleb(data, 0)
    imports = []
    for _ in range(count):
        module, offset = _read_name(data, offset)
        name, offset = _read_name(data, offset)
        if offset >= len(data):
            raise ArtifactError("truncated import descriptor")
        kind = data[offset]
        offset += 1
        if kind != 0:
            raise ArtifactError("PySoroban artifacts only support function imports")
        type_index, offset = _read_uleb(data, offset)
        imports.append({"module": module, "name": name, "kind": "function", "type_index": type_index})
    if offset != len(data):
        raise ArtifactError("unexpected trailing import data")
    return imports


def _parse_exports(data: bytes) -> List[dict]:
    if not data:
        return []
    count, offset = _read_uleb(data, 0)
    kinds = {0: "function", 1: "table", 2: "memory", 3: "global", 4: "tag"}
    exports = []
    for _ in range(count):
        name, offset = _read_name(data, offset)
        if offset >= len(data):
            raise ArtifactError("truncated export descriptor")
        kind = data[offset]
        offset += 1
        if kind not in kinds:
            raise ArtifactError(f"unknown export kind {kind}")
        index, offset = _read_uleb(data, offset)
        exports.append({"name": name, "kind": kinds[kind], "index": index})
    if offset != len(data):
        raise ArtifactError("unexpected trailing export data")
    return exports


def _vector_count(data: bytes, label: str) -> int:
    if not data:
        return 0
    count, offset = _read_uleb(data, 0)
    if label == "function":
        for _ in range(count):
            _, offset = _read_uleb(data, offset)
    elif label == "code":
        for _ in range(count):
            size, offset = _read_uleb(data, offset)
            offset += size
            if offset > len(data):
                raise ArtifactError("truncated function body")
    if offset != len(data):
        raise ArtifactError(f"unexpected trailing {label} section data")
    return count


def inspect_wasm(data: bytes) -> dict:
    """Return stable JSON-compatible information for a PySoroban artifact."""
    sections = _parse_sections(data)
    section_ids = {section.id for section in sections}
    required_ids = {1, 2, 3, 5, 7, 10, 11}
    missing_ids = sorted(required_ids - section_ids)
    if missing_ids:
        raise ArtifactError(
            "missing Wasm section(s): "
            + ", ".join(SECTION_NAMES[section_id] for section_id in missing_ids)
        )
    custom = _custom_sections(sections)
    functions, events = _contract_spec(custom["contractspecv0"])
    metadata = _contract_metadata(custom["contractmetav0"])
    if not metadata.get("name"):
        raise ArtifactError("contract metadata does not contain a name")
    if metadata.get("source_lang") != "pysoroban":
        raise ArtifactError("contract metadata is not marked as pysoroban")
    function_count = _vector_count(_section_payload(sections, 3), "function")
    code_count = _vector_count(_section_payload(sections, 10), "code")
    if function_count != code_count:
        raise ArtifactError("function and code section counts do not match")
    if function_count != len(functions):
        raise ArtifactError("contract spec and function section counts do not match")
    imports = _parse_imports(_section_payload(sections, 2))
    exports = _parse_exports(_section_payload(sections, 7))
    function_exports = [item["name"] for item in exports if item["kind"] == "function"]
    if function_exports != [item["name"] for item in functions]:
        raise ArtifactError("contract spec and function exports do not match")
    if not any(item["name"] == "memory" and item["kind"] == "memory" for item in exports):
        raise ArtifactError("contract does not export memory")

    return {
        "status": "valid",
        "format": "wasm",
        "contract": metadata.get("name"),
        "source_lang": metadata.get("source_lang"),
        "protocol": _environment_protocol(custom["contractenvmetav0"]),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "functions": functions,
        "events": events,
        "imports": imports,
        "exports": exports,
        "custom_sections": [
            {"name": name, "size": len(payload)} for name, payload in custom.items()
        ],
        "sections": [
            {"id": section.id, "name": SECTION_NAMES[section.id], "size": len(section.payload)}
            for section in sections
        ],
    }


def inspect_wasm_file(path: Union[str, Path]) -> dict:
    return inspect_wasm(Path(path).read_bytes())


def validate_wasm(data: bytes) -> None:
    """Validate Wasm framing plus the PySoroban/Soroban sections we emit."""
    inspect_wasm(data)


def validate_wasm_file(path: Union[str, Path]) -> None:
    validate_wasm(Path(path).read_bytes())
