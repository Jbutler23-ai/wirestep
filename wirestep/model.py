"""Validate circuits and input events before starting a simulation."""

from dataclasses import dataclass
import hashlib
import heapq
import json
from pathlib import Path
import re

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TIME = 10**9
OPS = {"BUF", "NOT", "AND", "OR", "XOR", "NAND", "NOR", "XNOR"}
VALUES = {"0", "1", "X"}
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,63}\Z")


class WirestepError(ValueError):
    """Invalid input or an operation beyond the supported limits."""


def canonical_digest(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                         allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise WirestepError(f"{label} requires exactly: {', '.join(fields)}")


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise WirestepError(f"{label} must be an integer between {low} and {high}")


def _identifier(value, label):
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise WirestepError(f"Invalid {label}: use a letter or underscore, then letters, digits, . : - or _ (64 characters maximum)")


def _value(value):
    if not isinstance(value, str) or value not in VALUES:
        raise WirestepError("Logic values must be strings: 0, 1, or X")


def _version(value):
    if type(value) is not int or value != 1:
        raise WirestepError("Only format version 1 is supported")


@dataclass(frozen=True)
class Input:
    name: str
    initial: str

    def to_dict(self):
        return {"name": self.name, "initial": self.initial}


@dataclass(frozen=True)
class Gate:
    id: str
    op: str
    inputs: tuple[str, ...]
    output: str
    delay: int

    def to_dict(self):
        return {"id": self.id, "op": self.op, "inputs": list(self.inputs),
                "output": self.output, "delay": self.delay}


@dataclass(frozen=True)
class Circuit:
    name: str
    inputs: tuple[Input, ...]
    gates: tuple[Gate, ...]
    outputs: tuple[str, ...]
    order: tuple[str, ...]

    @property
    def signals(self):
        return tuple(sorted([item.name for item in self.inputs] + [gate.output for gate in self.gates]))

    def to_dict(self):
        return {"version": 1, "name": self.name, "inputs": [item.to_dict() for item in self.inputs],
                "gates": [gate.to_dict() for gate in self.gates], "outputs": list(self.outputs)}

    @property
    def digest(self):
        return canonical_digest(self.to_dict())


def parse_circuit(data) -> Circuit:
    _exact(data, ("version", "name", "inputs", "gates", "outputs"), "Circuit")
    _version(data["version"])
    name = data["name"]
    if (not isinstance(name, str) or not 1 <= len(name) <= 120
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in name)):
        raise WirestepError("Circuit name must be 1 to 120 characters without controls or surrogates")
    if not isinstance(data["inputs"], list) or not 1 <= len(data["inputs"]) <= 64:
        raise WirestepError("Circuit needs between 1 and 64 primary inputs")
    if not isinstance(data["gates"], list) or len(data["gates"]) > 20_000:
        raise WirestepError("Circuit supports at most 20000 gates")
    inputs, gates = [], []
    wires, gate_ids = set(), set()
    drivers = {}
    for spec in data["inputs"]:
        _exact(spec, ("name", "initial"), "Primary input")
        _identifier(spec["name"], "input name")
        _value(spec["initial"])
        if spec["name"] in wires:
            raise WirestepError(f"Duplicate input: {spec['name']}")
        wires.add(spec["name"])
        inputs.append(Input(spec["name"], spec["initial"]))
    for spec in data["gates"]:
        _exact(spec, ("id", "op", "inputs", "output", "delay"), "Gate")
        _identifier(spec["id"], "gate id")
        _identifier(spec["output"], "gate output")
        if spec["id"] in gate_ids:
            raise WirestepError(f"Duplicate gate id: {spec['id']}")
        if spec["output"] in wires:
            raise WirestepError(f"Multiple drivers for signal: {spec['output']}")
        if not isinstance(spec["op"], str) or spec["op"] not in OPS:
            raise WirestepError("Unknown gate operation")
        pins = spec["inputs"]
        if not isinstance(pins, list):
            raise WirestepError("Gate inputs must be a list of signal names")
        arity = len(pins)
        if (spec["op"] in {"BUF", "NOT"} and arity != 1) or (spec["op"] not in {"BUF", "NOT"} and not 2 <= arity <= 16):
            raise WirestepError(f"Invalid input count for {spec['op']}")
        for pin in pins:
            _identifier(pin, "gate input")
        _integer(spec["delay"], 1, 1_000_000, "Gate delay")
        gate_ids.add(spec["id"])
        wires.add(spec["output"])
        drivers[spec["output"]] = spec["id"]
        gates.append(Gate(spec["id"], spec["op"], tuple(pins), spec["output"], spec["delay"]))
    outputs = data["outputs"]
    if not isinstance(outputs, list) or not 1 <= len(outputs) <= 256:
        raise WirestepError("Circuit needs between 1 and 256 output signals")
    for output in outputs:
        _identifier(output, "output name")
        if output not in wires:
            raise WirestepError(f"Unknown output signal: {output}")
    if len(set(outputs)) != len(outputs):
        raise WirestepError("Output signals must be unique")
    # A heap gives a stable topological order independent of declaration order.
    indegree = {}
    dependents = {gate.id: set() for gate in gates}
    for gate in gates:
        for pin in gate.inputs:
            if pin not in wires:
                raise WirestepError(f"Unknown signal {pin} on gate {gate.id}")
        predecessors = {drivers[pin] for pin in gate.inputs if pin in drivers}
        indegree[gate.id] = len(predecessors)
        for predecessor in predecessors:
            dependents[predecessor].add(gate.id)
    ready = [key for key, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        current = heapq.heappop(ready)
        order.append(current)
        for successor in sorted(dependents[current]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                heapq.heappush(ready, successor)
    if len(order) != len(gates):
        raise WirestepError("Combinational cycles are not supported")
    return Circuit(name, tuple(sorted(inputs, key=lambda item: item.name)),
                   tuple(sorted(gates, key=lambda gate: gate.id)), tuple(outputs), tuple(order))


def parse_stimulus(data, circuit: Circuit) -> tuple[dict, ...]:
    _exact(data, ("version", "events"), "Stimulus")
    _version(data["version"])
    if not isinstance(data["events"], list) or len(data["events"]) > 100_000:
        raise WirestepError("Stimulus events must be a list of at most 100000 assignments")
    names = {item.name for item in circuit.inputs}
    seen, result = set(), []
    for event in data["events"]:
        _exact(event, ("time", "signal", "value"), "Stimulus event")
        _integer(event["time"], 0, MAX_TIME, "Stimulus time")
        _identifier(event["signal"], "stimulus signal")
        _value(event["value"])
        if event["signal"] not in names:
            raise WirestepError(f"Stimulus can only drive primary inputs: {event['signal']}")
        key = event["time"], event["signal"]
        if key in seen:
            raise WirestepError(f"Repeated assignment to {key[1]} at time {key[0]}")
        seen.add(key)
        result.append(dict(event))
    return tuple(sorted(result, key=lambda event: (event["time"], event["signal"])))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WirestepError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise WirestepError(f"Invalid JSON constant: {value}")


def _load(path):
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise WirestepError("JSON input exceeds the 16 MiB file limit")
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_object, parse_constant=_constant)
    except WirestepError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise WirestepError(f"Cannot read JSON: {exc}") from exc


def load_circuit(path) -> Circuit:
    return parse_circuit(_load(path))


def load_stimulus(path, circuit: Circuit) -> tuple[dict, ...]:
    return parse_stimulus(_load(path), circuit)
