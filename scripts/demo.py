"""Check a half adder and a hand-derived transport pulse in temporary reports."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from wirestep.cli import main as cli_main
from wirestep.engine import simulate, truth_table
from wirestep.model import load_circuit, load_stimulus


def main() -> None:
    examples = ROOT / "examples"
    adder = load_circuit(examples / "half-adder.json")
    table = truth_table(adder)
    if len(table["rows"]) != 4:
        raise RuntimeError("Half-adder truth table must contain four rows.")
    for row in table["rows"]:
        a, b = int(row["inputs"]["a"]), int(row["inputs"]["b"])
        expected = {"sum": str((a + b) % 2), "carry": str((a + b) // 2)}
        if row["outputs"] != expected:
            raise RuntimeError("Half-adder outputs do not match independent arithmetic.")
    timed_adder = simulate(adder, load_stimulus(examples / "half-adder-stimulus.json", adder), until=25)
    adder_expected = {
        "sum": [(0, "X"), (2, "0"), (7, "1"), (12, "0"), (17, "1"), (22, "0")],
        "carry": [(0, "X"), (3, "0"), (13, "1"), (18, "0")],
    }
    for name, samples in adder_expected.items():
        if timed_adder["signals"][name] != [{"time": tick, "value": value} for tick, value in samples]:
            raise RuntimeError(f"Unexpected half-adder timing for {name}.")
    circuit = load_circuit(examples / "reconvergent.json")
    stimulus = load_stimulus(examples / "reconvergent-stimulus.json", circuit)
    expected = {
        "a": [(0, "0"), (10, "1"), (11, "0")],
        "not_a": [(0, "X"), (5, "1"), (15, "0"), (16, "1")],
        "pulse": [(0, "X"), (3, "0"), (13, "1"), (14, "0")],
    }
    expected = {name: [{"time": tick, "value": value} for tick, value in samples] for name, samples in expected.items()}
    with TemporaryDirectory(prefix="wirestep-demo-") as temporary:
        root = Path(temporary)
        output, html = root / "pulse.json", root / "pulse.html"
        status = cli_main(["simulate", str(examples / "reconvergent.json"), "--stimulus", str(examples / "reconvergent-stimulus.json"), "--until", "20", "--output", str(output), "--html", str(html)])
        if status:
            raise RuntimeError(f"Pulse simulation exited with {status}.")
        report = json.loads(output.read_text(encoding="utf-8"))
        if report["signals"] != expected or report["status"] != "quiescent":
            raise RuntimeError("Pulse trace differs from the hand-derived result.")
        if "<svg" not in html.read_text(encoding="utf-8"):
            raise RuntimeError("Waveform report has no SVG.")
        partial = simulate(circuit, stimulus, until=20, max_events=1)
        if partial["status"] != "event_limit" or partial["completed_through"] != 3:
            raise RuntimeError("Event budget did not stop before the next full timestamp batch.")
        print("Half-adder truth table matches arithmetic for all four input vectors.")
        print("Half-adder timed outputs match the expected delayed transitions.")
        print("Reconvergent pulse is high at tick 13 and returns low at tick 14.")
        print("A one-event budget stops with a partial report completed through tick 3.")
        print("JSON and HTML reports were checked. Temporary files are removed on exit.")


if __name__ == "__main__":
    main()
