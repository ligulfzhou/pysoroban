import fs from "node:fs";

const I32_TAG = 5n;
const U32_TAG = 4n;
const I64_SMALL_TAG = 7n;
const U64_SMALL_TAG = 6n;
const VOID_TAG = 2n;

function tagged32(value, tag) {
  const bits = BigInt.asUintN(32, BigInt(value));
  return BigInt.asIntN(64, (bits << 32n) | tag);
}

function decodeI32(value) {
  return BigInt.asIntN(32, BigInt.asUintN(64, value) >> 32n);
}

function decodeU32(value) {
  return BigInt.asUintN(64, value) >> 32n;
}

function vectorElement(type) {
  return type.startsWith("Vec[") && type.endsWith("]")
    ? type.slice(4, -1)
    : null;
}

function mapTypes(type) {
  const match = /^Map\[([^,]+), ([^\]]+)\]$/.exec(type);
  return match ? { key: match[1], value: match[2] } : null;
}

class MiniSorobanHost {
  constructor() {
    this.objects = new Map();
    this.nextObject = 1n;
    this.instance = null;
  }

  put(object) {
    const handle = (this.nextObject++ << 8n) | 64n;
    this.objects.set(handle.toString(), object);
    return handle;
  }

  get(handle) {
    const object = this.objects.get(BigInt.asUintN(64, handle).toString());
    if (!object) throw new Error(`unknown host object ${handle}`);
    return object;
  }

  encode(value, type) {
    if (type === "i32") return tagged32(value, I32_TAG);
    if (type === "u32") return tagged32(value, U32_TAG);
    if (type === "boolean") return value ? 1n : 0n;
    if (["i64", "u64", "i128", "u128"].includes(type)) {
      return this.put({ kind: type, value: BigInt(value) });
    }
    if (["Address", "Symbol", "String", "Bytes"].includes(type)) {
      return this.put({ kind: type, value });
    }
    const element = vectorElement(type);
    if (element) {
      return this.put({
        kind: "vec",
        element,
        values: value.map((item) => this.encode(item, element)),
      });
    }
    const map = mapTypes(type);
    if (map) {
      return this.put({
        kind: "map",
        key: map.key,
        value: map.value,
        entries: Object.entries(value).map(([key, item]) => [
          this.encode(key, map.key),
          this.encode(item, map.value),
        ]),
      });
    }
    throw new Error(`runner cannot encode ${type}`);
  }

  decode(value, type) {
    if (type === "i32") return decodeI32(value).toString();
    if (type === "u32") return decodeU32(value).toString();
    if (type === "boolean") return (BigInt.asUintN(64, value) & 0xffn) === 1n;
    if (type === "i64" || type === "u64") {
      const bits = BigInt.asUintN(64, value);
      const tag = bits & 0xffn;
      if (tag === I64_SMALL_TAG) return (BigInt.asIntN(64, bits) >> 8n).toString();
      if (tag === U64_SMALL_TAG) return (bits >> 8n).toString();
      return this.get(value).value.toString();
    }
    if (type === "i128" || type === "u128") {
      return this.get(value).value.toString();
    }
    if (["Address", "Symbol", "String", "Bytes"].includes(type)) {
      return this.get(value).value;
    }
    const element = vectorElement(type);
    if (element) {
      return this.get(value).values.map((item) => this.decode(item, element));
    }
    const map = mapTypes(type);
    if (map) {
      return Object.fromEntries(
        this.get(value).entries.map(([key, item]) => [this.decode(key, map.key), this.decode(item, map.value)]),
      );
    }
    if (type === "None" || type === "void") return null;
    throw new Error(`runner cannot decode ${type}`);
  }

  memoryObject(kind, offsetValue, lengthValue) {
    if (!this.instance) throw new Error("Wasm instance is not initialized");
    const offset = Number(decodeU32(offsetValue));
    const length = Number(decodeU32(lengthValue));
    const bytes = new Uint8Array(this.instance.exports.memory.buffer, offset, length);
    const value = kind === "Bytes" ? Buffer.from(bytes).toString("hex") : new TextDecoder().decode(bytes);
    return this.put({ kind, value });
  }

  equal(left, right) {
    const leftObject = this.objects.get(BigInt.asUintN(64, left).toString());
    const rightObject = this.objects.get(BigInt.asUintN(64, right).toString());
    if (!leftObject || !rightObject) return left === right;
    return leftObject.kind === rightObject.kind && leftObject.value === rightObject.value;
  }

  function(module, name) {
    const key = `${module}.${name}`;
    if (key === "i._") return (value) => this.put({ kind: "u64", value: BigInt.asUintN(64, value) });
    if (key === "i.0") return (value) => BigInt.asIntN(64, this.get(value).value);
    if (key === "i.1") return (value) => this.put({ kind: "i64", value: BigInt.asIntN(64, value) });
    if (key === "i.2") return (value) => BigInt.asIntN(64, this.get(value).value);
    if (key === "i.3") return (hi, lo) => this.put({
      kind: "u128",
      value: (BigInt.asUintN(64, hi) << 64n) | BigInt.asUintN(64, lo),
    });
    if (key === "i.4") return (value) => BigInt.asIntN(64, this.get(value).value);
    if (key === "i.5") return (value) => BigInt.asIntN(64, this.get(value).value >> 64n);
    if (key === "i.6") return (hi, lo) => this.put({
      kind: "i128",
      value: BigInt.asIntN(128, (BigInt.asUintN(64, hi) << 64n) | BigInt.asUintN(64, lo)),
    });
    if (key === "i.7") return (value) => BigInt.asIntN(64, this.get(value).value);
    if (key === "i.8") return (value) => BigInt.asIntN(64, this.get(value).value >> 64n);
    if (key === "i.9") return (hiHi, hiLo, loHi, loLo) => this.put({
      kind: "u256",
      value: (BigInt.asUintN(64, hiHi) << 192n)
        | (BigInt.asUintN(64, hiLo) << 128n)
        | (BigInt.asUintN(64, loHi) << 64n)
        | BigInt.asUintN(64, loLo),
    });
    if (["i.c", "i.d", "i.e", "i.f"].includes(key)) return (value) => {
      const shifts = { "i.c": 192n, "i.d": 128n, "i.e": 64n, "i.f": 0n };
      return BigInt.asIntN(64, this.get(value).value >> shifts[key]);
    };
    if (key === "i.p") return (left, right) => this.put({
      kind: "u256",
      value: this.get(left).value * this.get(right).value,
    });
    if (key === "i.q") return (left, right) => {
      const denominator = this.get(right).value;
      if (denominator === 0n) throw new WebAssembly.RuntimeError("unreachable: division by zero");
      return this.put({ kind: "u256", value: this.get(left).value / denominator });
    };
    if (key === "b.3") return (offset, length) => this.memoryObject("Bytes", offset, length);
    if (key === "b.i") return (offset, length) => this.memoryObject("String", offset, length);
    if (key === "b.j") return (offset, length) => this.memoryObject("Symbol", offset, length);
    if (key === "v.3") return (vector) => tagged32(this.get(vector).values.length, U32_TAG);
    if (key === "v.1") return (vector, index) => this.get(vector).values[Number(decodeU32(index))];
    if (key === "m.3") return (map) => tagged32(this.get(map).entries.length, U32_TAG);
    if (key === "m.4") return (map, wanted) => this.get(map).entries.some(([key]) => this.equal(key, wanted)) ? 1n : 0n;
    if (key === "m.1") return (map, wanted) => {
      const entry = this.get(map).entries.find(([key]) => this.equal(key, wanted));
      if (!entry) throw new Error("map key not found");
      return entry[1];
    };
    if (key === "x.0") {
      return (left, right) => {
        const leftValue = this.get(left).value;
        const rightValue = this.get(right).value;
        if (leftValue === rightValue) return 0n;
        return leftValue < rightValue ? -1n : 1n;
      };
    }
    if (key === "x.1") return () => VOID_TAG;
    return () => {
      throw new Error(`differential host function ${key} is not implemented`);
    };
  }
}

async function executeSuite(suite) {
  const bytes = fs.readFileSync(suite.wasm);
  const module = new WebAssembly.Module(bytes);
  const host = new MiniSorobanHost();
  const imports = {};
  for (const item of WebAssembly.Module.imports(module)) {
    imports[item.module] ??= {};
    imports[item.module][item.name] = host.function(item.module, item.name);
  }
  const instance = new WebAssembly.Instance(module, imports);
  host.instance = instance;

  const results = [];
  for (const testCase of suite.cases) {
    const fn = instance.exports[testCase.function];
    if (typeof fn !== "function") throw new Error(`missing export ${testCase.function}`);
    const args = testCase.args.map((value, index) => host.encode(value, testCase.params[index]));
    try {
      const actual = host.decode(fn(...args), testCase.result);
      const matched = !testCase.expectedTrap
        && JSON.stringify(actual) === JSON.stringify(testCase.expected);
      results.push({ name: testCase.name, actual, expected: testCase.expected, matched });
    } catch (error) {
      const actual = String(error);
      const matched = Boolean(testCase.expectedTrap && actual.includes(testCase.expectedTrap));
      results.push({ name: testCase.name, actual, expected: testCase.expectedTrap, matched });
    }
  }
  return results;
}

const manifest = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const results = [];
for (const suite of manifest.suites) results.push(...await executeSuite(suite));
const failed = results.filter((item) => !item.matched);
process.stdout.write(JSON.stringify({ total: results.length, matched: results.length - failed.length, failed }));
if (failed.length) process.exitCode = 1;
