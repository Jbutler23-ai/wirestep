"""Validate circuits, simulate transport delays, and export truth tables."""

import argparse
import json
import os
from pathlib import Path
import sys

from .engine import simulate, truth_table
from .model import WirestepError, load_circuit, load_stimulus
from .reporting import render_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wirestep", description="Simulate digital logic using integer ticks and explicit gate delays.")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check a circuit without simulating it")
    validate.add_argument("circuit", type=Path)
    validate.add_argument("--output", type=Path)
    run = commands.add_parser("simulate", help="run a timed stimulus and record signal transitions")
    run.add_argument("circuit", type=Path)
    run.add_argument("--stimulus", required=True, type=Path)
    run.add_argument("--until", required=True, type=int, help="inclusive final tick")
    run.add_argument("--max-events", type=int, default=1_000_000, help="maximum delivered assignments")
    run.add_argument("--output", type=Path)
    run.add_argument("--html", type=Path, help="write a standalone waveform report")
    table = commands.add_parser("table", help="enumerate a bounded binary truth table")
    table.add_argument("circuit", type=Path)
    table.add_argument("--output", type=Path)
    return parser


def _normalized(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except (RuntimeError, OSError) as error:
        raise WirestepError(f"Cannot resolve output or source path: {path}: {error}") from error


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n"


def _write_outputs(outputs: list[tuple[Path, str]], inputs: list[Path]) -> None:
    normalized = [_normalized(path) for path, _ in outputs]
    if len(normalized) != len(set(normalized)):
        raise WirestepError("JSON and HTML output paths must be different.")
    sources = {_normalized(path) for path in inputs}
    if any(path in sources for path in normalized):
        raise WirestepError("An output cannot replace a circuit or stimulus input.")
    for path, _ in outputs:
        if path.exists() or path.is_symlink():
            raise WirestepError(f"Output already exists: {path}")
        if not path.parent.is_dir():
            raise WirestepError(f"Output directory does not exist: {path.parent}")
    created = []
    try:
        for path, content in outputs:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                info = os.fstat(stream.fileno())
                created.append((path, info.st_dev, info.st_ino))
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for path, device, inode in reversed(created):
            try:
                info = path.lstat()
                if (info.st_dev, info.st_ino) == (device, inode):
                    path.unlink()
            except OSError:
                pass
        raise


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        circuit = load_circuit(args.circuit)
        inputs = [args.circuit]
        outputs = []
        exit_code = 0
        if args.command == "validate":
            result = {"version": 1, "circuit_sha256": circuit.digest, "inputs": len(circuit.inputs), "gates": len(circuit.gates), "signals": len(circuit.signals), "outputs": len(circuit.outputs)}
        elif args.command == "table":
            result = truth_table(circuit)
        else:
            stimulus = load_stimulus(args.stimulus, circuit)
            inputs.append(args.stimulus)
            result = simulate(circuit, stimulus, until=args.until, max_events=args.max_events)
            exit_code = 1 if result["status"] == "event_limit" else 0
            if args.html:
                outputs.append((args.html, render_report(result)))
        if args.output:
            outputs.insert(0, (args.output, _json_text(result)))
        _write_outputs(outputs, inputs)
        if not args.output:
            sys.stdout.write(_json_text(result))
        return exit_code
    except (WirestepError, OSError) as error:
        print(f"wirestep: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("wirestep: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
