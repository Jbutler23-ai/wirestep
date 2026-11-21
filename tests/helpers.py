from itertools import product


def half_adder():
    return {
        "version": 1, "name": "Half adder",
        "inputs": [{"name": "a", "initial": "0"}, {"name": "b", "initial": "0"}],
        "gates": [
            {"id": "sum_gate", "op": "XOR", "inputs": ["a", "b"], "output": "sum", "delay": 2},
            {"id": "carry_gate", "op": "AND", "inputs": ["a", "b"], "output": "carry", "delay": 3},
        ],
        "outputs": ["sum", "carry"],
    }


def buffer_circuit(*, initial="0", delay=5):
    return {
        "version": 1, "name": "Transport buffer",
        "inputs": [{"name": "a", "initial": initial}],
        "gates": [{"id": "buffer", "op": "BUF", "inputs": ["a"], "output": "out", "delay": delay}],
        "outputs": ["out"],
    }


def event(time, signal, value):
    return {"time": time, "signal": signal, "value": value}


def boolean_possibilities(op, values):
    """Evaluate each possible binary interpretation of independent X inputs."""
    options = [(0, 1) if value == "X" else (int(value),) for value in values]
    results = set()
    for vector in product(*options):
        if op == "BUF":
            result = vector[0]
        elif op == "NOT":
            result = 1 - vector[0]
        elif op in ("AND", "NAND"):
            result = int(all(vector))
            if op == "NAND":
                result = 1 - result
        elif op in ("OR", "NOR"):
            result = int(any(vector))
            if op == "NOR":
                result = 1 - result
        elif op in ("XOR", "XNOR"):
            result = sum(vector) % 2
            if op == "XNOR":
                result = 1 - result
        else:
            raise AssertionError(f"Unknown reference operation: {op}")
        results.add(str(result))
    return next(iter(results)) if len(results) == 1 else "X"


def dense_reference(circuit, events, until, max_events=1_000_000):
    """Tick-by-tick reference using per-tick buckets, with no event heap."""
    values = {item["name"]: item["initial"] for item in circuit["inputs"]}
    values.update({gate["output"]: "X" for gate in circuit["gates"]})
    buckets = {}
    processed = 0
    scheduled = len(events)
    evaluations = 0
    transitions = 0
    initial_events = [item for item in events if item["time"] == 0]
    if len(initial_events) > max_events:
        raise ValueError("Reference initialization exceeds budget")
    for item in events:
        if item["time"] == 0:
            values[item["signal"]] = item["value"]
            processed += 1
        else:
            buckets.setdefault(item["time"], []).append((item["signal"], item["value"]))
    traces = {signal: [{"time": 0, "value": value}] for signal, value in sorted(values.items())}
    for gate in circuit["gates"]:
        result = boolean_possibilities(gate["op"], [values[signal] for signal in gate["inputs"]])
        buckets.setdefault(gate["delay"], []).append((gate["output"], result))
        scheduled += 1
        evaluations += 1
    pending = sum(map(len, buckets.values()))
    peak_pending = pending
    completed = 0
    status = None
    for tick in range(1, until + 1):
        batch = buckets.get(tick, [])
        if not batch:
            continue
        if processed + len(batch) > max_events:
            status = "event_limit"
            break
        del buckets[tick]
        pending -= len(batch)
        processed += len(batch)
        changed = set()
        for signal, value in batch:
            if values[signal] != value:
                changed.add(signal)
            values[signal] = value
        for signal in sorted(changed):
            traces[signal].append({"time": tick, "value": values[signal]})
        transitions += len(changed)
        for gate in circuit["gates"]:
            if not any(signal in changed for signal in gate["inputs"]):
                continue
            result = boolean_possibilities(gate["op"], [values[signal] for signal in gate["inputs"]])
            buckets.setdefault(tick + gate["delay"], []).append((gate["output"], result))
            pending += 1
            scheduled += 1
            evaluations += 1
        peak_pending = max(peak_pending, pending)
        completed = tick
    if status is None:
        status = "horizon" if pending else "quiescent"
        completed = until
    return {
        "signals": traces, "final": values, "status": status, "completed_through": completed,
        "stats": {"processed_events": processed, "scheduled_events": scheduled,
                  "gate_evaluations": evaluations, "transitions": transitions,
                  "pending_events": pending, "peak_pending_events": peak_pending},
    }
