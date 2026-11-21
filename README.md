# Wirestep

Wirestep simulates digital logic circuits and shows how signal values change over time. Circuits and input changes are described in JSON. Results are available as JSON traces and a standalone HTML waveform report.

The prototype supports combinational circuits with `0`, `1`, and `X` values and positive transport delays. It uses abstract integer ticks. It doesn't model analog voltages, physical device accuracy, or an HDL standard.

The [roadmap](docs/roadmap.md) adds hierarchy, sequential components, more timing models, resolved buses, checkpointing, and an offline editor. Those features are still planned.

## Run it

Use Python 3.11 or later from the repository directory. No installation or third-party runtime dependencies are required.

```sh
python -m wirestep validate examples/half-adder.json
python -m wirestep table examples/half-adder.json
python -m wirestep simulate examples/half-adder.json --stimulus examples/half-adder-stimulus.json --until 25 --output trace.json --html waveform.html
```

Open `waveform.html` directly in a browser. It has no external assets or server requirement. Output files must not already exist, and their parent directories must exist. Omit `--output` to write JSON to standard output.

The reconvergent example demonstrates a pulse preserved by transport delay:

```sh
python -m wirestep simulate examples/reconvergent.json --stimulus examples/reconvergent-stimulus.json --until 20 --output pulse.json --html pulse.html
```

Its input rises at tick 10 and falls at tick 11. The output is high from tick 13 to tick 14. A settled truth table alone wouldn't show that pulse.

## Reading a result

| Status | Meaning |
| --- | --- |
| `quiescent` | No assignments remain queued. Signals can still be `X`. |
| `horizon` | The requested interval is complete, with assignments remaining after `until`. |
| `event_limit` | The next whole timestamp batch would exceed the event budget. The report is partial. |

`until` is inclusive. `completed_through` identifies how far the report can be read. It equals `until` for a quiescent or horizon result, and the last processed timestamp for an event-limited result.

Successful validation, truth tables, and quiescent or horizon simulations return exit code `0`. A partial event-limited simulation returns `1`; invalid input or output returns `2`; interruption returns `130`.

JSON includes every recorded signal transition, the final values, circuit and stimulus digests, and event counts. HTML displays at most 80 signals and 400 samples per signal, with a notice when capped. JSON retains the full returned trace.

## Current limits

- Circuits are directed acyclic graphs with one driver per signal. There are no registers, latches, clocks, feedback loops, zero delays, or tri-state buses.
- Gates are `BUF`, `NOT`, `AND`, `OR`, `XOR`, `NAND`, `NOR`, and `XNOR`. Unknown values use conservative three-valued logic, not symbolic reasoning.
- A circuit can have up to 64 primary inputs and 20,000 gates. Circuit and stimulus files are each limited to 16 MiB.
- Traces stay in memory. The default delivery budget is one million assignments, and the pending queue is capped at one million assignments.
- Truth tables allow at most 12 inputs and two million vector-gate evaluations.

Source files aren't changed. JSON and HTML output files aren't committed as one transaction. See [the architecture](docs/architecture.md) for exact parsing, timing, and budget rules.

## Checks

```sh
python -m unittest discover -s tests -v
python scripts/demo.py
python scripts/benchmark.py --chains 20 --depth 100 --changes 100 --json
```

The demo checks the half-adder, a known pulse trace, and an event-limited run. The benchmark builds buffer chains and checks every wire's trace against a separate delay formula. Its allocation measurement uses `tracemalloc`, which doesn't measure total process memory.

## Project notes

- [Architecture and timing rules](docs/architecture.md)
- [Acceptance checks](docs/acceptance.md)
- [Measured prototype baseline](docs/baseline.md)
- [Nine-session roadmap](docs/roadmap.md)
- [Data and license](docs/data-and-license.md)

All circuits and stimuli are synthetic. The project runs offline without a GPU, Docker, sound, external accounts, or platform-specific software.

Licensed under the [MIT license](LICENSE).
