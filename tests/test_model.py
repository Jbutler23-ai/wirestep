from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from wirestep.model import WirestepError, load_circuit, load_stimulus, parse_circuit, parse_stimulus
from tests.helpers import buffer_circuit, event, half_adder


class CircuitTests(unittest.TestCase):
    def test_normalization_and_round_trip_preserve_the_digest(self):
        data = half_adder()
        circuit = parse_circuit(data)
        reordered = deepcopy(data)
        reordered["inputs"].reverse()
        reordered["gates"].reverse()
        self.assertEqual(circuit.digest, parse_circuit(reordered).digest)
        self.assertEqual(circuit.digest, parse_circuit(circuit.to_dict()).digest)
        self.assertEqual(tuple(item.name for item in circuit.inputs), ("a", "b"))
        self.assertEqual(circuit.signals, ("a", "b", "carry", "sum"))

    def test_output_order_and_gate_delays_are_part_of_the_digest(self):
        original = half_adder()
        digest = parse_circuit(original).digest
        reversed_outputs = deepcopy(original)
        reversed_outputs["outputs"].reverse()
        changed_delay = deepcopy(original)
        changed_delay["gates"][0]["delay"] += 1
        self.assertNotEqual(digest, parse_circuit(reversed_outputs).digest)
        self.assertNotEqual(digest, parse_circuit(changed_delay).digest)

    def test_forward_references_and_lexical_topological_ties(self):
        data = {
            "version": 1, "name": "Forward references",
            "inputs": [{"name": "i", "initial": "0"}],
            "gates": [
                {"id": "a_finish", "op": "BUF", "inputs": ["middle"], "output": "out", "delay": 1},
                {"id": "z_branch", "op": "BUF", "inputs": ["i"], "output": "branch", "delay": 1},
                {"id": "b_source", "op": "BUF", "inputs": ["i"], "output": "middle", "delay": 1},
            ],
            "outputs": ["out", "branch"],
        }
        self.assertEqual(parse_circuit(data).order, ("b_source", "a_finish", "z_branch"))

    def test_primary_outputs_and_zero_gates_are_allowed(self):
        data = buffer_circuit()
        data["gates"] = []
        data["outputs"] = ["a"]
        circuit = parse_circuit(data)
        self.assertEqual(circuit.gates, ())
        self.assertEqual(circuit.outputs, ("a",))

    def test_repeated_gate_inputs_and_separate_id_namespace_are_allowed(self):
        data = buffer_circuit(initial="X")
        data["gates"][0].update(id="a", op="XOR", inputs=["a", "a"])
        circuit = parse_circuit(data)
        self.assertEqual(circuit.gates[0].inputs, ("a", "a"))

    def test_combinational_cycles_are_rejected(self):
        data = buffer_circuit()
        data["gates"] = [
            {"id": "first", "op": "NOT", "inputs": ["out"], "output": "middle", "delay": 1},
            {"id": "second", "op": "NOT", "inputs": ["middle"], "output": "out", "delay": 1},
        ]
        with self.assertRaises(WirestepError):
            parse_circuit(data)

    def test_missing_wires_and_multiple_drivers_are_rejected(self):
        cases = []
        missing = buffer_circuit()
        missing["gates"][0]["inputs"] = ["unknown"]
        cases.append(missing)
        input_collision = buffer_circuit()
        input_collision["gates"][0]["output"] = "a"
        input_collision["outputs"] = ["a"]
        cases.append(input_collision)
        gate_collision = buffer_circuit()
        gate_collision["gates"].append({**gate_collision["gates"][0], "id": "second"})
        cases.append(gate_collision)
        for index, data in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(WirestepError):
                    parse_circuit(data)

    def test_duplicate_input_gate_ids_and_outputs_are_rejected(self):
        for field in ("inputs", "gates", "outputs"):
            with self.subTest(field=field):
                data = half_adder()
                data[field].append(deepcopy(data[field][0]))
                with self.assertRaises(WirestepError):
                    parse_circuit(data)

    def test_unknown_and_missing_fields_are_rejected_at_every_level(self):
        for location in ("root", "input", "gate"):
            for mutation in ("extra", "missing"):
                with self.subTest(location=location, mutation=mutation):
                    data = half_adder()
                    target = {"root": data, "input": data["inputs"][0], "gate": data["gates"][0]}[location]
                    if mutation == "extra":
                        target["extra"] = 1
                    else:
                        del target["version" if location == "root" else "initial" if location == "input" else "delay"]
                    with self.assertRaises(WirestepError):
                        parse_circuit(data)

    def test_versions_delays_and_logic_values_are_strictly_typed(self):
        for value in (True, 1.0, "1", 0, 2):
            with self.subTest(version=value):
                data = half_adder()
                data["version"] = value
                with self.assertRaises(WirestepError):
                    parse_circuit(data)
        for value in (True, 1.0, "1", 0, -1, 1_000_001):
            with self.subTest(delay=value):
                data = buffer_circuit(delay=value)
                with self.assertRaises(WirestepError):
                    parse_circuit(data)
        for value in (True, 0, 1, "Z", "x", None):
            with self.subTest(initial=value):
                with self.assertRaises(WirestepError):
                    parse_circuit(buffer_circuit(initial=value))

    def test_identifiers_names_and_operation_arity_are_checked(self):
        for identifier in ("", "0leading", "with space", "café", "a" * 65):
            with self.subTest(identifier=identifier):
                data = half_adder()
                data["gates"][0]["id"] = identifier
                with self.assertRaises(WirestepError):
                    parse_circuit(data)
        for name in ("", "bad\nname", "bad\x7fname", "\ud800", "x" * 121):
            with self.subTest(name=repr(name)):
                data = half_adder()
                data["name"] = name
                with self.assertRaises(WirestepError):
                    parse_circuit(data)
        for operation, inputs in (("AND", ["a"]), ("BUF", ["a", "a"]),
                                  ("XOR", ["a"] * 17), ("UNKNOWN", ["a"])):
            with self.subTest(operation=operation, inputs=inputs):
                data = buffer_circuit()
                data["gates"][0].update(op=operation, inputs=inputs)
                with self.assertRaises(WirestepError):
                    parse_circuit(data)

    def test_input_count_and_empty_or_missing_outputs_are_rejected(self):
        for count in (0, 65):
            with self.subTest(input_count=count):
                data = buffer_circuit()
                data["inputs"] = [{"name": f"i{index}", "initial": "0"} for index in range(count)]
                with self.assertRaises(WirestepError):
                    parse_circuit(data)
        for outputs in ([], ["missing"]):
            with self.subTest(outputs=outputs):
                data = half_adder()
                data["outputs"] = outputs
                with self.assertRaises(WirestepError):
                    parse_circuit(data)


class StimulusTests(unittest.TestCase):
    def setUp(self):
        self.circuit = parse_circuit(half_adder())

    def test_stimulus_normalizes_by_time_and_signal(self):
        parsed = parse_stimulus({"version": 1, "events": [event(5, "b", "1"), event(0, "a", "X"),
                                                            event(5, "a", "0")]}, self.circuit)
        self.assertEqual(parsed, (event(0, "a", "X"), event(5, "a", "0"), event(5, "b", "1")))
        self.assertEqual(parse_stimulus({"version": 1, "events": []}, self.circuit), ())

    def test_duplicate_same_tick_assignments_are_rejected_even_when_equal(self):
        for second_value in ("1", "0"):
            with self.subTest(second_value=second_value):
                with self.assertRaises(WirestepError):
                    parse_stimulus({"version": 1, "events": [event(2, "a", "1"),
                                                              event(2, "a", second_value)]}, self.circuit)

    def test_only_primary_inputs_can_be_driven(self):
        for signal in ("sum", "missing", [], None):
            with self.subTest(signal=signal):
                with self.assertRaises(WirestepError):
                    parse_stimulus({"version": 1, "events": [event(1, signal, "1")]}, self.circuit)

    def test_stimulus_time_and_value_types_are_strict(self):
        for time in (True, 1.0, "1", -1, 1_000_000_001, None):
            with self.subTest(time=time):
                with self.assertRaises(WirestepError):
                    parse_stimulus({"version": 1, "events": [event(time, "a", "1")]}, self.circuit)
        for value in (True, 0, "Z", "x", None):
            with self.subTest(value=value):
                with self.assertRaises(WirestepError):
                    parse_stimulus({"version": 1, "events": [event(1, "a", value)]}, self.circuit)

    def test_stimulus_rejects_unknown_fields_and_malformed_containers(self):
        cases = [None, [], {}, {"version": True, "events": []},
                 {"version": 1, "events": [], "extra": 1}, {"version": 1, "events": None},
                 {"version": 1, "events": [{**event(1, "a", "1"), "extra": 1}]},
                 {"version": 1, "events": [{"time": 1, "signal": "a"}]}]
        for index, data in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(WirestepError):
                    parse_stimulus(data, self.circuit)


class LoaderTests(unittest.TestCase):
    def test_utf8_bom_is_supported_for_circuit_and_stimulus(self):
        with tempfile.TemporaryDirectory() as temporary:
            circuit_path, stimulus_path = Path(temporary) / "circuit.json", Path(temporary) / "stimulus.json"
            circuit_path.write_text(json.dumps(half_adder()), encoding="utf-8-sig")
            stimulus_path.write_text(json.dumps({"version": 1, "events": [event(1, "a", "1")]}),
                                     encoding="utf-8-sig")
            circuit = load_circuit(circuit_path)
            self.assertEqual(load_stimulus(stimulus_path, circuit), (event(1, "a", "1"),))

    def test_duplicate_json_fields_nonfinite_numbers_and_bad_encoding_are_rejected(self):
        invalid = [b'{"version":1,"version":1}', b'{"inputs":[{"name":"a","name":"b"}]}',
                   b'{"value":NaN}', b'{"value":Infinity}', b"\xff", b"{broken"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.json"
            circuit = parse_circuit(half_adder())
            for content in invalid:
                with self.subTest(content=content):
                    path.write_bytes(content)
                    with self.assertRaises(WirestepError):
                        load_circuit(path)
                    with self.assertRaises(WirestepError):
                        load_stimulus(path, circuit)

    def test_file_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "oversized.json"
            with path.open("wb") as stream:
                stream.truncate(16 * 1024 * 1024 + 1)
            with self.assertRaises(WirestepError):
                load_circuit(path)


if __name__ == "__main__":
    unittest.main()
