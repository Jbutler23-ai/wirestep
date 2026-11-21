# Roadmap

The current engine simulates acyclic combinational circuits with positive transport delays. The nine sessions below add the state, timing rules, and tooling needed to inspect more complex digital designs. They describe remaining work.

## 1. Hierarchy and elaboration

Add reusable modules with validated ports, stable instance paths, and diagnostics that point back to the source definition. Elaborate modules into a flat execution model while rejecting recursive instantiation and invalid connections.

Check: nested modules and their hand-flattened equivalents produce identical traces. Repeated instances stay independent, and invalid connections identify the instance and port involved.

## 2. Zero-delay evaluation

Define delta cycles and update phases so gates can react without advancing simulated time. Bound work within a timestamp and report whether execution settled, repeated a known state, or reached its work limit.

Check: zero-delay chains settle predictably, simultaneous changes stay independent of declaration order, and nonsettling examples stop without hanging. Reaching a limit alone isn't called proof of oscillation.

## 3. Sequential components

Add D flip-flops, latches, clock sources, registers, and reset behavior. Specify when inputs are sampled and outputs become visible, including simultaneous data, clock, and reset changes. Define conservative behavior for unknown controls.

Check: counters, shift registers, and latch examples match independent state-transition references. Cover initialization, reset priority, clock/data coincidences, and unknown edges. These are digital rules, not predictions of physical metastability.

## 4. Inertial delay and cancellation

Add an explicit inertial mode alongside transport delay. Define the rejection interval, cancellation rules, and equal-time boundaries. Track pending assignments without losing unrelated future transitions.

Check: hand-derived traces cover pulses shorter than, equal to, and longer than the rejection interval. Run the same circuit under both modes and verify their expected differences.

## 5. Tri-state signals and multiple drivers

Add `Z` and a documented resolution table. Keep driver values separate from resolved wire values, propagate changes only after resolution, and expose contention in the report.

Check: undriven, agreeing, conflicting, disabled, and unknown drivers match an independent table. Reordering drivers doesn't affect results. Shared-bus examples exercise the interaction with sequential components and delays.

## 6. Checkpoints and reuse after edits

Persist the execution position, signal and driver values, component state, pending events, and inertial cancellation state. Identify the circuit and stimuli in each checkpoint. Reuse work after supported edits only when its dependencies remain valid.

Check: resumed and uninterrupted traces match exactly. Interrupted checkpoint writes recover to a complete checkpoint or a clear error. Changed inputs or incompatible circuits are rejected. Reused execution matches a fresh run of the edited circuit.

The baseline already schedules only gates affected by signal changes. This milestone adds persistence and reuse across edited runs, beyond that existing event-driven behavior.

## 7. Stuck-at component testing

Allow a simulated gate output to be fixed at `0` or `1` and compare the resulting trace with an unfaulted run. Record the injected component, test stimulus, and first observable difference. Keep unknown outcomes separate from confirmed detection.

Check: exhaustive small circuits match a separate reference. Report detected, undetected, and inconclusive cases accurately, and exercise fault effects through registers and resolved buses. This operates on synthetic circuit models, without connecting to devices.

## 8. Offline circuit editor

Build a local editor with bundled HTML, CSS, and JavaScript and a Python service on localhost. Edit circuits and stimuli, inspect component state, and navigate waveforms. Use the CLI's parser and engine for every run.

Check: create, save, reopen, simulate, and inspect a synthetic circuit without internet access. UI and CLI traces agree. Invalid edits have useful diagnostics, and old results are visibly separated from the current circuit revision.

## 9. Reference and performance suite

Expand generated circuits, sequential reference cases, delay-boundary tests, driver resolution cases, and checkpoint interruption checks. Run the same correctness suite on Windows and Linux. Stream traces so long runs don't require keeping every sample in memory.

The unmeasured target is 100,000 gates and 10,000,000 delivered assignments within 512 MiB of peak process memory. Raise current model limits only alongside validation and resource checks. Measure fanout-heavy and lightly active designs separately, record queue and trace sizes, and set the runtime budget from observed results.

Check: performance cases match independent expected traces or reference cases, and streamed results match retained traces on small runs. No speed or memory result counts as passing when transitions are missing.

## Scope

Wirestep remains a digital simulator with documented abstract timing rules. The plan doesn't include transistor models, analog voltages, power estimates, physical hardware control, a full HDL implementation, or external services. All development circuits and stimuli are synthetic.
