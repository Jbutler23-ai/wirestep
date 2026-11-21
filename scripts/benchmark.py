"""Check every buffer-chain trace against a delay formula and measure simulation."""

import argparse
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wirestep.engine import simulate
from wirestep.model import WirestepError, parse_circuit, parse_stimulus


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def run_benchmark(chains: int, depth: int, changes: int) -> dict:
    if chains > 64 or chains * depth > 20_000 or chains * changes > 100_000:
        raise WirestepError("Corpus exceeds circuit or stimulus size limits.")
    event_bound = chains * depth * (changes + 2) + chains * changes
    if event_bound > 10_000_000:
        raise WirestepError("Corpus exceeds the maximum delivered-event budget.")
    inputs, gates, outputs, events = [], [], [], []
    for chain in range(chains):
        source = f"input_{chain:02d}"
        inputs.append({"name": source, "initial": "0"})
        previous = source
        for level in range(1, depth + 1):
            wire = f"chain_{chain:02d}_{level:05d}"
            gates.append({"id": f"gate_{chain:02d}_{level:05d}", "op": "BUF", "inputs": [previous], "output": wire, "delay": chain % 3 + 1})
            previous = wire
        outputs.append(previous)
        events.extend({"time": change * 7, "signal": source, "value": str(change % 2)} for change in range(1, changes + 1))
    circuit = parse_circuit({"version": 1, "name": "Independent delayed buffer chains", "inputs": inputs, "gates": gates, "outputs": outputs})
    stimulus = parse_stimulus({"version": 1, "events": events}, circuit)
    until = changes * 7 + depth * 3 + 1
    tracemalloc.start()
    try:
        started = perf_counter()
        report = simulate(circuit, stimulus, until=until, max_events=max(1, event_bound))
        simulation_seconds = perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    checked_signals = 0
    for chain in range(chains):
        for level in range(depth + 1):
            name = f"input_{chain:02d}" if level == 0 else f"chain_{chain:02d}_{level:05d}"
            shift = level * (chain % 3 + 1)
            expected = [{"time": 0, "value": "0" if level == 0 else "X"}]
            if level:
                expected.append({"time": shift, "value": "0"})
            expected.extend({"time": change * 7 + shift, "value": str(change % 2)} for change in range(1, changes + 1))
            if report["signals"].get(name) != expected:
                raise RuntimeError(f"Trace differs from the independent delay formula: {name}")
            if report["final"].get(name) != str(changes % 2):
                raise RuntimeError(f"Wrong final value: {name}")
            checked_signals += 1
    if set(report["signals"]) != set(circuit.signals) or report["status"] != "quiescent":
        raise RuntimeError("Simulation did not finish with the exact expected signal set.")
    started = perf_counter()
    encoded = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    serialization_seconds = perf_counter() - started
    return {
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "corpus": {"generator": "wirestep-buffer-chains-v1", "chains": chains, "depth": depth, "gates": chains * depth, "input_changes_per_chain": changes, "stimulus_events": chains * changes, "until": until},
        "checks": {"all_signal_traces_match_formula": True, "signals_checked": checked_signals, "quiescent": True},
        "simulation_stats": report["stats"],
        "measurements": {"simulation_seconds": round(simulation_seconds, 6), "peak_traced_python_bytes": peak_bytes, "json_serialization_seconds": round(serialization_seconds, 6), "compact_json_bytes": len(encoded)},
        "measurement_scope": "Wall time with tracemalloc enabled. Peak traced Python allocations cover simulation, excluding corpus generation, formula checks, and JSON serialization; this is not process RSS.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chains", type=positive_integer, default=20)
    parser.add_argument("--depth", type=positive_integer, default=100)
    parser.add_argument("--changes", type=positive_integer, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_benchmark(args.chains, args.depth, args.changes)
        if args.json:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        else:
            print(f"Python {result['environment']['python']} on {result['environment']['platform']}")
            print(f"Corpus: {args.chains} chains x {args.depth} gates, {args.changes} input changes per chain")
            print(f"All {result['checks']['signals_checked']} signal traces match the independent delay formula.")
            print(json.dumps(result["simulation_stats"], indent=2))
            print(json.dumps(result["measurements"], indent=2))
            print(result["measurement_scope"])
            print("Measurements describe this local run only.")
        return 0
    except (WirestepError, OSError, RuntimeError) as error:
        print(f"benchmark: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("benchmark: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
