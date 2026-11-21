from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from wirestep.cli import main
from tests.helpers import event, half_adder


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.circuit_path = self.root / "circuit.json"
        self.stimulus_path = self.root / "stimulus.json"
        self.circuit_path.write_text(json.dumps(half_adder()), encoding="utf-8")
        self.stimulus_path.write_text(json.dumps({"version": 1, "events": []}), encoding="utf-8")

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "wirestep", *map(str, arguments)],
            cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def simulation_arguments(self, *extra):
        return ["simulate", self.circuit_path, "--stimulus", self.stimulus_path,
                "--until", "20", *extra]

    def test_validation_and_truth_table_stdout_are_clean_json(self):
        validated = self.run_cli("validate", self.circuit_path)
        self.assertEqual(validated.returncode, 0, validated.stderr)
        self.assertEqual(validated.stderr, "")
        counts = json.loads(validated.stdout)
        self.assertEqual(counts["inputs"], 2)
        self.assertEqual(counts["gates"], 2)
        self.assertEqual(counts["signals"], 4)
        table = self.run_cli("table", self.circuit_path)
        self.assertEqual(table.returncode, 0, table.stderr)
        self.assertEqual(table.stderr, "")
        self.assertEqual(len(json.loads(table.stdout)["rows"]), 4)

    def test_quiescent_and_horizon_runs_both_return_success(self):
        settled = self.run_cli(*self.simulation_arguments())
        self.assertEqual(settled.returncode, 0, settled.stderr)
        self.assertEqual(json.loads(settled.stdout)["status"], "quiescent")
        horizon = self.run_cli("simulate", self.circuit_path, "--stimulus", self.stimulus_path,
                               "--until", "0")
        self.assertEqual(horizon.returncode, 0, horizon.stderr)
        self.assertEqual(json.loads(horizon.stdout)["status"], "horizon")

    def test_event_limit_returns_one_and_publishes_clearly_partial_reports(self):
        output, html = self.root / "partial.json", self.root / "partial.html"
        result = self.run_cli(*self.simulation_arguments("--max-events", "1", "--output", output,
                                                       "--html", html))
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "event_limit")
        self.assertEqual(report["completed_through"], 2)
        self.assertEqual(report["stats"]["processed_events"], 1)
        text = html.read_text(encoding="utf-8").lower()
        self.assertIn("partial", text)
        self.assertIn("<svg", text)
        self.assertNotIn("<script", text)

    def test_invalid_stimulus_is_fatal_without_publishing_outputs(self):
        self.stimulus_path.write_text(json.dumps({"version": 1,
                                                  "events": [event(1, "sum", "1")]}), encoding="utf-8")
        output, html = self.root / "report.json", self.root / "report.html"
        result = self.run_cli(*self.simulation_arguments("--output", output, "--html", html))
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(output.exists())
        self.assertFalse(html.exists())

    def test_invalid_circuit_json_is_reported_without_a_traceback(self):
        self.circuit_path.write_text('{"version":1,"version":1}', encoding="utf-8")
        result = self.run_cli("validate", self.circuit_path)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_existing_outputs_are_not_overwritten_and_all_paths_are_preflighted(self):
        for existing in ("json", "html"):
            with self.subTest(existing=existing):
                output, html = self.root / f"report-{existing}.json", self.root / f"report-{existing}.html"
                protected = output if existing == "json" else html
                other = html if existing == "json" else output
                protected.write_bytes(b"keep existing file")
                result = self.run_cli(*self.simulation_arguments("--output", output, "--html", html))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(protected.read_bytes(), b"keep existing file")
                self.assertFalse(other.exists())

    def test_source_files_and_same_output_alias_are_protected(self):
        for path in (self.circuit_path, self.stimulus_path):
            with self.subTest(source=path.name):
                before = path.read_bytes()
                result = self.run_cli(*self.simulation_arguments("--output", path))
                self.assertEqual(result.returncode, 2)
                self.assertEqual(path.read_bytes(), before)
        output = self.root / "same-output"
        result = self.run_cli(*self.simulation_arguments("--output", output, "--html", output))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())

    def test_missing_output_parent_is_not_created(self):
        output = self.root / "missing" / "report.json"
        result = self.run_cli(*self.simulation_arguments("--output", output))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.parent.exists())

    def test_html_escapes_circuit_name_and_has_no_external_assets(self):
        data = half_adder()
        data["name"] = "Circuit <script>alert('test')</script> & waveform"
        self.circuit_path.write_text(json.dumps(data), encoding="utf-8")
        html = self.root / "report.html"
        result = self.run_cli(*self.simulation_arguments("--html", html))
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["circuit"]["name"], data["name"])
        text = html.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script", text.lower())
        self.assertIn("<svg", text.lower())
        self.assertNotRegex(text, r'''(?:src|href)=["']https?://''')

    def test_missing_input_and_invalid_budget_fail_without_tracebacks(self):
        for arguments in (("validate", self.root / "missing.json"),
                          self.simulation_arguments("--max-events", "0")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)

    def test_unresolvable_output_path_is_a_domain_error(self):
        output = self.root / "report.json"
        stdout, stderr = io.StringIO(), io.StringIO()
        arguments = list(map(str, self.simulation_arguments("--output", output)))
        with patch("wirestep.cli.Path.resolve", side_effect=RuntimeError("Symlink loop")):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = main(arguments)
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertTrue(stderr.getvalue().strip())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
