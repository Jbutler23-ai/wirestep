# Prototype baseline

These results describe one local run, not runtime guarantees. Checks ran on Windows 11 (10.0.26200) with Python 3.12.14. Linux validation is planned.

`python -m unittest discover -s tests -v` passed all 54 tests without skips. An independent dense-tick reference matched complete traces, final values, completion status, and event counters for 14 generated circuits under four horizon and budget settings. Separate gate tests enumerate ternary inputs against a Boolean-possibility reference.

## Example checks

`python scripts/demo.py` passed the half-adder's arithmetic truth table and exact timed traces. It also checked the reconvergent example against hand-derived traces for every wire and verified an event-limited run.

The reconvergent input rises at tick 10 and falls at tick 11. Its output pulse runs from tick 13 up to tick 14. Transport delay preserves that pulse; a settled truth table wouldn't describe it.

## Buffer-chain benchmark

```sh
python scripts/benchmark.py --chains 20 --depth 100 --changes 100 --json
```

The corpus has 20 independent buffer chains, each 100 gates deep, with 100 input changes per chain. Gate delays vary between chains. Each wire's entire trace was checked against a separate formula that shifts the input transitions by the accumulated delay. All 2,020 signal traces matched, and the run reached quiescence by the requested tick 1,001.

| Quantity | Observed value |
| --- | ---: |
| Gates | 2,000 |
| Stimulus assignments | 2,000 |
| Delivered assignments | 205,980 |
| Gate evaluations | 203,980 |
| Recorded changes, excluding initial samples | 204,000 |
| Peak queued assignments | 4,000 |
| Pending assignments at completion | 0 |
| Simulation time | 2.407417 seconds |
| Peak traced Python allocations | 42,407,144 bytes |
| Compact JSON serialization | 0.092633 seconds |
| Compact JSON report | 5,415,049 bytes |

Simulation time includes tracing overhead. Peak traced allocations cover simulation, excluding circuit generation, formula checks, and JSON serialization. This is not total process memory. Serialization was timed separately without allocation tracing. Indented CLI JSON and HTML have different sizes.

This corpus checks propagation along chains. It doesn't establish performance for heavy fanout, reconvergent logic, sequential state, or zero-delay loops. Those need separate workloads as the engine expands.

## Future target

The target is 100,000 gates and 10,000,000 delivered assignments within 512 MiB of peak process memory, with streamed traces. It hasn't been measured. The prototype's 20,000-gate limit and in-memory trace storage remain in place. Future benchmarks must record topology, activity, queue size, trace volume, runtime, and process memory. Runtime budgets will follow those measurements.
