"""Timestamp-batched transport simulation with a bounded event budget."""

import heapq
from itertools import product

from .logic import gate_value
from .model import Circuit, MAX_TIME, WirestepError, canonical_digest, parse_stimulus

MAX_PENDING_EVENTS = 1_000_000


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise WirestepError(f"{label} must be an integer between {low} and {high}")


def simulate(circuit: Circuit, stimulus, until: int, max_events: int = 1_000_000) -> dict:
    _integer(until, 0, MAX_TIME, "Stop time")
    _integer(max_events, 1, 10_000_000, "Event budget")
    if not isinstance(stimulus, (list, tuple)):
        raise WirestepError("Stimulus must be a list or tuple of assignments")
    stimulus = parse_stimulus({"version": 1, "events": list(stimulus)}, circuit)
    initial_events = [event for event in stimulus if event["time"] == 0]
    if len(initial_events) > max_events:
        raise WirestepError("Time-zero input batch exceeds the event budget")
    values = {name: "X" for name in circuit.signals}
    for item in circuit.inputs:
        values[item.name] = item.initial
    for event in initial_events:
        values[event["signal"]] = event["value"]
    traces = {name: [{"time": 0, "value": value}] for name, value in values.items()}
    gates = {gate.id: gate for gate in circuit.gates}
    fanout = {name: set() for name in circuit.signals}
    for gate in circuit.gates:
        for pin in gate.inputs:
            fanout[pin].add(gate.id)
    queue = [(event["time"], event["signal"], event["value"]) for event in stimulus if event["time"] > 0]
    if len(queue) > MAX_PENDING_EVENTS:
        raise WirestepError("Pending event limit exceeded; reduce the stimulus")
    heapq.heapify(queue)
    stats = {"processed_events": len(initial_events), "scheduled_events": len(stimulus),
             "gate_evaluations": 0, "transitions": 0, "pending_events": 0,
             "peak_pending_events": len(queue)}

    def schedule(gate, time):
        if len(queue) >= MAX_PENDING_EVENTS:
            raise WirestepError("Pending event limit exceeded; reduce the circuit or stimulus")
        result = gate_value(gate.op, [values[pin] for pin in gate.inputs])
        # Even a value equal to the current output may be needed after an
        # earlier queued transition. Transport events are never cancelled.
        heapq.heappush(queue, (time + gate.delay, gate.output, result))
        stats["scheduled_events"] += 1
        stats["gate_evaluations"] += 1
        stats["peak_pending_events"] = max(stats["peak_pending_events"], len(queue))

    for gate in circuit.gates:
        schedule(gate, 0)
    status, last_time = "quiescent", 0
    while queue:
        time = queue[0][0]
        if time > until:
            status = "horizon"
            break
        batch = []
        while queue and queue[0][0] == time:
            batch.append(heapq.heappop(queue))
        if stats["processed_events"] + len(batch) > max_events:
            for item in batch:
                heapq.heappush(queue, item)
            status = "event_limit"
            break
        affected = set()
        # All assignments at this timestamp become visible together. No gate
        # reads a half-applied batch or a newly scheduled output at this tick.
        for _, wire, value in batch:
            if values[wire] != value:
                values[wire] = value
                traces[wire].append({"time": time, "value": value})
                stats["transitions"] += 1
                affected.update(fanout[wire])
        stats["processed_events"] += len(batch)
        last_time = time
        for identifier in sorted(affected):
            schedule(gates[identifier], time)
    stats["pending_events"] = len(queue)
    return {"version": 1, "circuit": circuit.to_dict(), "circuit_sha256": circuit.digest,
            "stimulus_sha256": canonical_digest({"version": 1, "events": list(stimulus)}),
            "until": until, "status": status,
            "completed_through": last_time if status == "event_limit" else until,
            "signals": traces, "final": values, "outputs": list(circuit.outputs), "stats": stats}


def evaluate(circuit: Circuit, inputs: dict) -> dict:
    names = {item.name for item in circuit.inputs}
    if not isinstance(inputs, dict) or set(inputs) != names:
        raise WirestepError("Settled evaluation needs exactly the primary input names")
    if any(not isinstance(value, str) or value not in {"0", "1", "X"} for value in inputs.values()):
        raise WirestepError("Logic values must be strings: 0, 1, or X")
    values = dict(inputs)
    gates = {gate.id: gate for gate in circuit.gates}
    for identifier in circuit.order:
        gate = gates[identifier]
        values[gate.output] = gate_value(gate.op, [values[pin] for pin in gate.inputs])
    return {name: values[name] for name in circuit.signals}


def truth_table(circuit: Circuit) -> dict:
    count = len(circuit.inputs)
    if count > 12 or 2**count * max(1, len(circuit.gates)) > 2_000_000:
        raise WirestepError("Truth table exceeds the limit: 12 inputs and 2000000 gate evaluations")
    names = [item.name for item in circuit.inputs]
    rows = []
    for bits in product(("0", "1"), repeat=count):
        inputs = dict(zip(names, bits))
        values = evaluate(circuit, inputs)
        rows.append({"inputs": inputs, "outputs": {name: values[name] for name in circuit.outputs}})
    return {"version": 1, "circuit_sha256": circuit.digest, "inputs": names,
            "outputs": list(circuit.outputs), "rows": rows}
