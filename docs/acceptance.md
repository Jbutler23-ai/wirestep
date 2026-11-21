# Acceptance checks

The prototype's checks cover combinational circuits, three-valued gate behavior, positive transport delays, and report handling. Sequential behavior, zero-delay settling, and checkpoint recovery belong to later milestones.

Run from the repository root:

```sh
python -m unittest discover -s tests -v
python scripts/demo.py
python scripts/benchmark.py --chains 20 --depth 100 --changes 100 --json
```

## Prototype checks

| Area | Required result |
| --- | --- |
| Validation | Reject unknown fields and wires, duplicate names and JSON keys, multiple drivers, cycles, invalid values, incorrect arity, and invalid limits. Accept gates declared before their dependencies. |
| Gate logic | Match an independent Boolean-possibility reference for ternary input cases. Treat unknown occurrences independently, including repeated inputs. |
| Settled behavior | Match the half-adder's independently known sum and carry table. Enforce both truth-table limits. |
| Timing | Match a separate dense-tick reference on small generated acyclic circuits. Preserve transport pulses and their return edges. |
| Simultaneous events | Apply a timestamp's assignments together, avoiding glitches introduced only by declaration or iteration order. |
| Initialization | Apply time-zero stimuli before initial samples, start gate outputs at `X`, and evaluate all gates from the same snapshot. |
| Stopping | Include events at `until`, leave later events pending, and stop before an entire batch that exceeds the budget. Distinguish a partial result from a completed horizon. |
| Determinism | Reordering gate and stimulus declarations doesn't change the normalized result. |
| Outputs | Preserve existing files and inputs, return the documented exit codes, escape source text, and label partial HTML reports visibly. |

The reconvergent fixture has a direct input path and an inverted path with different delays. Its input pulse spans ticks 10 to 11, and the output pulse spans ticks 13 to 14. Compare the complete expected trace, including initialization, rather than checking only its final value.

The benchmark uses independent buffer chains. For each wire, the expected trace follows from the input trace shifted by the sum of delays along its chain, with an initial unknown interval. Check every wire and transition against that formula.

Benchmark generation, reference checks, and JSON serialization are outside the timed simulation. Simulation time is measured with allocation tracing enabled. Peak traced Python allocations aren't process RSS; serialized trace size is reported separately. Local results describe the measured corpus, not every circuit with the same gate count.

## Future acceptance bar

The [roadmap](roadmap.md) must establish these additional behaviors:

- Elaborated modules match equivalent flat circuits and retain source locations for diagnostics.
- Zero-delay circuits settle according to documented delta-cycle rules or stop with a clear reason. A work limit isn't reported as proof of oscillation.
- Sequential circuits follow explicit sampling and reset rules, including unknown controls and simultaneous clock/data changes.
- Inertial cancellation preserves or rejects pulses exactly at the documented boundaries.
- Multiple-driver resolution is independent of driver order and distinguishes high impedance from unknown values.
- Resumed execution matches uninterrupted execution, including pending assignments, sequential state, and cancellation state. Incompatible checkpoints are rejected.
- Reusing unaffected work after a circuit edit gives the same result as a fresh run of the edited circuit.
- Stuck-at component checks report detection only when an observable known difference supports it; unknown outcomes can remain inconclusive.
- The offline editor uses the same validation and simulation engine as the CLI.
- Independent reference, interruption, and regression checks pass on Windows and Linux.

The future scale target is 100,000 gates and 10,000,000 delivered assignments within 512 MiB of peak process memory, using streamed traces. This target hasn't been measured. It exceeds the current circuit limit and requires bounded trace storage. Set a runtime budget after measuring representative cases.

Record the circuit shape, fanout, input activity, delivered assignments, peak pending assignments, trace size, runtime, process memory, Python version, and hardware with a performance result. A result only passes if its correctness checks also pass.
