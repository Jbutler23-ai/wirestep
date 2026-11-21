# Architecture

Wirestep separates circuit validation, gate logic, event scheduling, and reporting. The current engine models combinational digital circuits in abstract integer ticks. Its timing rules are defined here; it doesn't implement Verilog, VHDL, or an analog circuit model.

## Circuit and stimulus formats

`model.py` accepts version 1 JSON circuits with exactly `version`, `name`, `inputs`, `gates`, and `outputs`. Each primary input declares its name and initial value. Each gate declares an ID, operation, input wires, output wire, and delay. Outputs select existing wires to expose as circuit outputs.

Signal and gate IDs match `[A-Za-z_][A-Za-z0-9_.:-]{0,63}`. Gate IDs have their own namespace. Each signal has exactly one driver, either a primary input or a gate. Wires can be referenced before their gate is declared, but unknown wires and combinational cycles are rejected.

The parser checks these bounds:

| Item | Limit |
| --- | --- |
| Circuit name | 1 to 120 characters, without control characters or unpaired surrogates |
| Primary inputs | 1 to 64 |
| Gates | 0 to 20,000 |
| Selected outputs | 1 to 256 distinct signals |
| Gate delay | Integer from 1 to 1,000,000 ticks |
| Stimulus events | At most 100,000 |
| Stimulus time and `until` | Integer from 0 to 1,000,000,000 ticks |
| Each JSON input file | At most 16 MiB, UTF-8 with an optional byte order mark |

Boolean values don't count as integers. Unknown fields, duplicate JSON keys, nonfinite constants, and incorrect types are errors.

Stimulus JSON contains `version` and `events`. Each event has `time`, `signal`, and `value`; only primary inputs can be driven. Two assignments to the same input at the same timestamp are rejected, even if their values agree.

Inputs and gates are normalized by name and ID. Stimulus events are sorted by time and signal. Output selection order is retained. Canonical JSON digests identify the normalized circuit and stimulus, so declaration order alone doesn't change a run's identity.

## Gate logic

`logic.py` evaluates `0`, `1`, and `X`. `X` means unknown. `BUF` and `NOT` take one input; the other gates take 2 to 16. Repeated input wires are allowed.

- `AND` returns `0` if any input is `0`, `1` if all inputs are `1`, and `X` otherwise.
- `OR` returns `1` if any input is `1`, `0` if all inputs are `0`, and `X` otherwise.
- `XOR` uses Boolean parity when all inputs are known and returns `X` otherwise.
- `NAND`, `NOR`, and `XNOR` invert their corresponding result. Inverting `X` leaves it unknown.
- `BUF` preserves its input.

Unknowns aren't symbolic variables. For example, `XOR(a, a)` produces `X` while `a` is unknown. The engine doesn't track the correlation needed to simplify that expression to zero.

## Initialization and event delivery

`engine.py` starts primary inputs at their declared values and every gate output at `X`. It applies all time-zero stimulus assignments, then records one initial sample for every signal at tick zero. It evaluates every gate once against that same initial snapshot and queues each result at the gate's delay.

After initialization, a heap holds assignments by timestamp. At each timestamp the engine:

1. Checks that the complete batch fits the remaining delivery budget.
2. Applies every assignment in the batch before evaluating any gate.
3. Records the wires that changed value.
4. Evaluates each affected gate once, in sorted ID order, and queues its result at the current time plus its delay.

Positive delays prevent same-tick cascading. Duplicate stimulus assignments and multiple drivers are rejected, so a wire can't receive competing assignments at one timestamp in the supported model.

Every gate evaluation schedules its result, even when that result equals the current output. Consider a buffer with delay 3 whose output is already `0`. An input rise at tick 5 queues a `1` for tick 8. A fall at tick 6 must still queue a `0` for tick 9, although the output is currently `0`. Omitting that second assignment would lose the return edge.

Assignments aren't cancelled. A delivered assignment that doesn't change a value consumes budget but doesn't trigger downstream evaluation. This is the prototype's transport-delay rule; inertial pulse rejection is future work.

## Limits and completion

`until` includes assignments at the specified tick. Those assignments may schedule later ones, leaving a horizon result. Stimulus beyond the horizon also remains queued.

The event budget defaults to 1,000,000 and can be set from 1 to 10,000,000. It counts delivered assignments, including redundant writes and time-zero stimulus assignments. Initial gate evaluations don't count as deliveries, but their queued outputs count when delivered.

If a timestamp batch would exceed the budget, none of that batch is applied. The report has status `event_limit` and identifies the last completed timestamp, or zero if no later batch completed. If time-zero stimuli alone exceed the budget, initialization fails instead of returning a partial initial state.

The pending queue has a separate fixed limit of 1,000,000 assignments. Exceeding it is a fatal error with no simulation report. Both the queue and complete trace are currently held in memory.

| Status | `completed_through` | Pending work |
| --- | --- | --- |
| `quiescent` | Requested `until` | Queue empty |
| `horizon` | Requested `until` | Next assignment is after `until` |
| `event_limit` | Last fully processed timestamp | A batch within the requested interval couldn't be processed |

Quiescence doesn't mean every signal is Boolean. A circuit can settle to `X`. The event guard isn't a convergence proof. Supported circuits are acyclic, so finite stimuli generate finite work, but that work can still exceed the limits.

## Reports and counters

The JSON report includes the normalized circuit, circuit and stimulus digests, requested horizon, completion status, signal traces, final values, selected outputs, and counters. Traces contain initial samples and actual changes, not every redundant assignment.

| Counter | Meaning |
| --- | --- |
| `processed_events` | Delivered assignments, including time-zero stimuli |
| `scheduled_events` | All input assignments and scheduled gate results, including work beyond the horizon |
| `gate_evaluations` | Initial and subsequent gate evaluations |
| `transitions` | Recorded value changes, excluding initial samples |
| `pending_events` | Assignments remaining in the queue |
| `peak_pending_events` | Largest queued assignment count during the run |

Reports contain no runtime measurements, timestamps, or absolute paths. Identical normalized inputs and run limits produce the same result. An event-limited report is a partial trace, not a checkpoint that can be resumed.

The HTML view uses inline styles and SVG, escapes source text, and needs no network connection. It displays the first 80 signals in lexical order and up to 400 samples per displayed signal. A notice identifies capped reports, and shading marks undisplayed or unsimulated spans. The JSON trace is unaffected. New output files are created exclusively. Source files and existing outputs aren't overwritten, but multiple output files don't form a transaction.

## Settled evaluation

`evaluate` computes all wire values in topological order for an exact set of primary input values. It ignores delays. `table` applies that evaluator to binary input vectors in lexicographic order, using sorted input names and the circuit's selected output order.

Truth tables are limited to 12 inputs and `2 ** input_count * max(1, gate_count) <= 2,000,000`. They establish settled behavior under these gate rules. They don't verify pulses, event ordering, or the timed engine independently.

## Technical background

[Baylor's Event Driven Simulation chapter](https://cs.baylor.edu/~maurer/aida/desauto/chapter3.pdf) explains event queues, fanout scheduling, and the separation between applying events and evaluating gates. Wirestep's explicit batching and transport rules above define its own supported model.

[Hao Zheng's Logic Simulation slides](https://cse.usf.edu/~haozheng/teach/psv/slides/3-LogicSimulation.pdf) discuss unknown logic values, reconvergent paths, and transport versus inertial delay. These distinctions motivate separate checks for settled values and timed waveforms. No external simulator is required at runtime or for the project's acceptance checks.
