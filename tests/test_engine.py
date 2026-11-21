from copy import deepcopy
import hashlib
import json
import random
import unittest
from unittest.mock import patch

from wirestep.engine import evaluate, simulate, truth_table
from wirestep.model import WirestepError, parse_circuit
from tests.helpers import buffer_circuit, dense_reference, event, half_adder


class SimulationTests(unittest.TestCase):
    def test_transport_preserves_return_pulse_while_earlier_transition_is_pending(self):
        circuit = parse_circuit(buffer_circuit(delay=5))
        report = simulate(circuit, [event(6, "a", "1"), event(7, "a", "0")], until=15)
        self.assertEqual(report["signals"]["out"], [
            {"time": 0, "value": "X"}, {"time": 5, "value": "0"},
            {"time": 11, "value": "1"}, {"time": 12, "value": "0"},
        ])
        self.assertEqual(report["status"], "quiescent")
        self.assertEqual(report["stats"]["processed_events"], 5)

    def test_simultaneous_input_changes_do_not_create_an_artificial_xor_glitch(self):
        data = half_adder()
        data["gates"] = [data["gates"][0]]
        data["outputs"] = ["sum"]
        report = simulate(parse_circuit(data), [event(5, "a", "1"), event(5, "b", "1")], until=10)
        self.assertEqual(report["signals"]["sum"], [{"time": 0, "value": "X"},
                                                      {"time": 2, "value": "0"}])
        self.assertEqual(report["stats"]["gate_evaluations"], 2)
        self.assertEqual(report["stats"]["processed_events"], 4)
        self.assertEqual(report["stats"]["transitions"], 3)

    def test_time_zero_override_is_applied_before_initial_samples_and_gate_evaluation(self):
        circuit = parse_circuit(buffer_circuit(initial="0", delay=3))
        report = simulate(circuit, [event(0, "a", "1")], until=3)
        self.assertEqual(report["signals"]["a"], [{"time": 0, "value": "1"}])
        self.assertEqual(report["signals"]["out"], [{"time": 0, "value": "X"},
                                                      {"time": 3, "value": "1"}])
        self.assertEqual(report["stats"]["processed_events"], 2)
        self.assertEqual(report["stats"]["scheduled_events"], 2)
        self.assertEqual(report["stats"]["transitions"], 1)

    def test_all_initial_gates_read_the_same_unknown_output_snapshot(self):
        data = buffer_circuit(delay=2)
        data["gates"].append({"id": "second", "op": "NOT", "inputs": ["out"],
                              "output": "final", "delay": 1})
        data["outputs"] = ["final"]
        report = simulate(parse_circuit(data), [], until=5)
        self.assertEqual(report["signals"]["final"], [{"time": 0, "value": "X"},
                                                        {"time": 3, "value": "1"}])
        self.assertEqual(report["stats"]["processed_events"], 3)

    def test_noop_deliveries_count_toward_budget_without_propagating(self):
        circuit = parse_circuit(buffer_circuit(initial="X", delay=2))
        report = simulate(circuit, [event(1, "a", "X")], until=10)
        self.assertEqual(report["stats"]["processed_events"], 2)
        self.assertEqual(report["stats"]["gate_evaluations"], 1)
        self.assertEqual(report["stats"]["transitions"], 0)
        self.assertEqual(report["signals"]["out"], [{"time": 0, "value": "X"}])
        self.assertEqual(report["status"], "quiescent")

    def test_horizon_is_inclusive_and_future_input_events_remain_pending(self):
        circuit = parse_circuit(buffer_circuit(delay=5))
        report = simulate(circuit, [event(9, "a", "1")], until=5)
        self.assertEqual(report["signals"]["out"][-1], {"time": 5, "value": "0"})
        self.assertEqual(report["status"], "horizon")
        self.assertEqual(report["completed_through"], 5)
        self.assertEqual(report["stats"]["pending_events"], 1)
        self.assertEqual(report["stats"]["processed_events"], 1)

    def test_event_at_horizon_can_schedule_a_future_output(self):
        report = simulate(parse_circuit(buffer_circuit(delay=5)), [event(5, "a", "1")], until=5)
        self.assertEqual(report["final"], {"a": "1", "out": "0"})
        self.assertEqual(report["status"], "horizon")
        self.assertEqual(report["stats"]["pending_events"], 1)

    def test_budget_stops_before_an_entire_timestamp_batch(self):
        circuit = parse_circuit(half_adder())
        events = [event(5, "a", "1"), event(5, "b", "1")]
        report = simulate(circuit, events, until=20, max_events=3)
        self.assertEqual(report["status"], "event_limit")
        self.assertEqual(report["completed_through"], 3)
        self.assertEqual(report["final"]["a"], "0")
        self.assertEqual(report["final"]["b"], "0")
        self.assertEqual(report["stats"]["processed_events"], 2)
        self.assertEqual(report["stats"]["pending_events"], 2)
        self.assertEqual(report["signals"]["a"], [{"time": 0, "value": "0"}])

    def test_initial_output_batch_is_not_partly_delivered_when_budget_is_too_small(self):
        data = half_adder()
        for gate in data["gates"]:
            gate["delay"] = 2
        report = simulate(parse_circuit(data), [], until=10, max_events=1)
        self.assertEqual(report["status"], "event_limit")
        self.assertEqual(report["completed_through"], 0)
        self.assertEqual(report["final"]["sum"], "X")
        self.assertEqual(report["final"]["carry"], "X")
        self.assertEqual(report["stats"]["processed_events"], 0)
        self.assertEqual(report["stats"]["pending_events"], 2)

    def test_oversized_time_zero_batch_is_fatal(self):
        with self.assertRaises(WirestepError):
            simulate(parse_circuit(half_adder()), [event(0, "a", "1"), event(0, "b", "1")],
                     until=0, max_events=1)

    def test_horizon_takes_precedence_over_future_budget_exhaustion(self):
        report = simulate(parse_circuit(buffer_circuit(delay=5)), [event(0, "a", "1")],
                          until=0, max_events=1)
        self.assertEqual(report["status"], "horizon")
        self.assertEqual(report["stats"]["processed_events"], 1)
        self.assertEqual(report["stats"]["pending_events"], 1)

    def test_direct_api_revalidates_stimulus_and_integer_limits(self):
        circuit = parse_circuit(half_adder())
        invalid_stimuli = [None, {}, [event(1, "sum", "0")], [event(True, "a", "0")],
                           [event(1, "a", "0"), event(1, "a", "0")],
                           [{**event(1, "a", "0"), "unknown": 1}]]
        for stimulus in invalid_stimuli:
            with self.subTest(stimulus=stimulus):
                with self.assertRaises(WirestepError):
                    simulate(circuit, stimulus, until=10)
        for until in (True, 1.0, -1, 1_000_000_001):
            with self.subTest(until=until):
                with self.assertRaises(WirestepError):
                    simulate(circuit, [], until=until)
        for budget in (True, 1.0, 0, -1, 10_000_001):
            with self.subTest(budget=budget):
                with self.assertRaises(WirestepError):
                    simulate(circuit, [], until=10, max_events=budget)

    def test_pending_queue_guard_checks_stimulus_and_new_gate_events(self):
        circuit = parse_circuit(half_adder())
        with patch("wirestep.engine.MAX_PENDING_EVENTS", 1):
            with self.assertRaises(WirestepError):
                simulate(circuit, [event(10, "a", "1"), event(11, "a", "0")], until=0)
            with self.assertRaises(WirestepError):
                simulate(circuit, [], until=0)

    def test_declaration_and_stimulus_order_do_not_change_report_or_digests(self):
        data = half_adder()
        events = [event(6, "b", "1"), event(1, "a", "1"), event(6, "a", "0")]
        original = simulate(parse_circuit(data), events, until=15)
        data["inputs"].reverse()
        data["gates"].reverse()
        reordered = simulate(parse_circuit(data), list(reversed(events)), until=15)
        self.assertEqual(original, reordered)
        normalized = {"version": 1, "events": sorted(events, key=lambda item: (item["time"], item["signal"]))}
        encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        self.assertEqual(original["stimulus_sha256"], hashlib.sha256(encoded).hexdigest())

    def test_small_seeded_dags_match_independent_dense_tick_reference(self):
        operations = ("BUF", "NOT", "AND", "OR", "XOR", "NAND", "NOR", "XNOR")
        for seed in range(14):
            randomizer = random.Random(seed)
            data = {"version": 1, "name": f"Synthetic DAG {seed}",
                    "inputs": [{"name": f"i{index}", "initial": randomizer.choice("01X")}
                               for index in range(3)], "gates": [], "outputs": []}
            wires = [item["name"] for item in data["inputs"]]
            for index in range(8):
                operation = randomizer.choice(operations)
                width = 1 if operation in ("BUF", "NOT") else randomizer.randint(2, 3)
                gate = {"id": f"g{index}", "op": operation,
                        "inputs": [randomizer.choice(wires) for _ in range(width)],
                        "output": f"w{index}", "delay": randomizer.randint(1, 4)}
                data["gates"].append(gate)
                wires.append(gate["output"])
            data["outputs"] = ["w7", "w6"]
            events = [event(time, f"i{index}", randomizer.choice("01X"))
                      for time in (0, 2, 5, 6, 11) for index in range(3)
                      if randomizer.random() < 0.65]
            for until, budget in ((0, 1000), (8, 1000), (40, 1000), (40, 15)):
                with self.subTest(seed=seed, until=until, budget=budget):
                    expected = dense_reference(data, events, until, budget)
                    actual = simulate(parse_circuit(data), events, until, budget)
                    for key in ("signals", "final", "status", "completed_through", "stats"):
                        self.assertEqual(actual[key], expected[key], key)


class SettledEvaluationTests(unittest.TestCase):
    def test_half_adder_table_matches_binary_arithmetic(self):
        table = truth_table(parse_circuit(half_adder()))
        self.assertEqual(table["inputs"], ["a", "b"])
        self.assertEqual(table["outputs"], ["sum", "carry"])
        self.assertEqual([tuple(row["inputs"].values()) for row in table["rows"]],
                         [("0", "0"), ("0", "1"), ("1", "0"), ("1", "1")])
        for row in table["rows"]:
            total = int(row["inputs"]["a"]) + int(row["inputs"]["b"])
            self.assertEqual(row["outputs"], {"sum": str(total % 2), "carry": str(total // 2)})

    def test_settled_evaluation_requires_exact_input_names_and_values(self):
        circuit = parse_circuit(half_adder())
        for inputs in (None, [], {"a": "0"}, {"a": "0", "b": "1", "extra": "0"},
                       {"a": True, "b": "0"}, {"a": "Z", "b": "0"}):
            with self.subTest(inputs=inputs):
                with self.assertRaises(WirestepError):
                    evaluate(circuit, inputs)
        self.assertEqual(evaluate(circuit, {"a": "0", "b": "X"})["carry"], "0")

    def test_truth_table_input_and_work_limits_are_enforced_before_expansion(self):
        data = buffer_circuit()
        data["inputs"] = [{"name": f"i{index}", "initial": "0"} for index in range(13)]
        data["gates"] = []
        data["outputs"] = ["i0"]
        with self.assertRaises(WirestepError):
            truth_table(parse_circuit(data))
        data["inputs"].pop()
        data["gates"] = [{"id": f"g{index}", "op": "BUF", "inputs": ["i0"],
                          "output": f"w{index}", "delay": 1} for index in range(500)]
        data["outputs"] = ["w499"]
        with self.assertRaises(WirestepError):
            truth_table(parse_circuit(data))


if __name__ == "__main__":
    unittest.main()
