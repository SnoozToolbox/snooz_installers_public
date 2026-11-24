import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "runner"
sys.path.insert(0, str(RUNNER))

from configuration import load_adaptations
from adapt_scenario_json import filter_scenario_inputs, resolve_configured_value
from natus_validation import NATUS_SUBJECT, filter_input, filter_report_rows
from resolve_tool_order import resolve_tools
from validate_configuration import validate_configuration
from validation_scenarios import expand_scenarios


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"INCLUDE_NATUS": "true"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = self.root / "tools"
        self.directory = self.tools / "Example"
        self.order = self.root / "config" / "tool_execution_order.json"
        self.adaptations = {
            "targetToolName": "Example",
            "processingMode": "adapted",
            "updates": [{
                "identifier": "reader",
                "inputName": "files",
                "value": {"kind": "workspaceFileJson", "relativePath": "../../shared/inputs/files.json"},
            }],
        }
        self.comparison = {
            "fileName": "report.tsv", "fileType": "bag-comparison", "precision": 4,
            "generatedSearchRoots": ["validation-workspaces/Example"],
        }
        self.validations = {"comparisons": [self.comparison]}
        write_json(self.root / "shared" / "inputs" / "files.json", {"record.edf": {"event_groups": []}})
        write_json(self.order, ["Example"])
        self.save()

    def save(self):
        write_json(self.directory / "adaptations.json", self.adaptations)
        write_json(self.directory / "validations.json", self.validations)

    def test_natus_filter_covers_all_configured_inputs_and_scenarios(self):
        definitions = load_adaptations(ROOT / "tools")
        for tool, definition in definitions.items():
            if tool == "SlowWaveClassification":
                continue
            for run in expand_scenarios(tool, definition, self.root):
                for update in run["updates"]:
                    spec = update.get("value")
                    if not spec or spec["kind"] not in ("literal", "workspaceFileJson"):
                        continue
                    with self.subTest(tool=tool, scenario=run["scenario_id"], input=update["inputName"]):
                        value = resolve_configured_value(spec, self.root, self.root)
                        self.assertNotIn(NATUS_SUBJECT, repr(filter_input(value)))
                        filter_scenario_inputs({"process_params": {"nodes": [{
                            "identifier": update["identifier"],
                            "inputs": {update["inputName"]: {"value": value}},
                        }]}}, tool)

    def test_natus_filter_preserves_types_and_checks_inherited_inputs(self):
        value = {f"{NATUS_SUBJECT}.eeg": {}, "record.edf": {"events": []}}
        self.assertEqual(filter_input(value), {"record.edf": {"events": []}})
        encoded = repr({NATUS_SUBJECT: ["F3"], "record": ["EEG"]})
        self.assertEqual(filter_input([encoded]), [repr({"record": ["EEG"]})])
        scenario = {"process_params": {"nodes": [{"identifier": "reader", "inputs": {
            "files": {"value": repr([f"{NATUS_SUBJECT}.eeg", "record.edf"])},
            "subjects": {"value": encoded},
        }}]}}
        filter_scenario_inputs(scenario, "Example")
        self.assertNotIn(NATUS_SUBJECT, repr(scenario))
        for value in (f"{NATUS_SUBJECT}.eeg", repr([f"{NATUS_SUBJECT}.eeg"])):
            with self.subTest(value=value), self.assertRaises(ValueError):
                filter_scenario_inputs({"process_params": {"nodes": [{"inputs": {
                    "files": {"value": value},
                }}]}}, "Example")

    def test_natus_exclusion_adapts_manifest_and_summary(self):
        self.adaptations["updates"][0]["value"] = {
            "kind": "literal", "value": repr({NATUS_SUBJECT: {}, "record.edf": {}}),
        }
        self.save()
        classifier = self.tools / "SlowWaveClassification"
        write_json(classifier / "adaptations.json", self.adaptations)
        write_json(classifier / "validations.json", self.validations)
        write_json(self.order, ["Example", "SlowWaveClassification"])
        source = self.root / "source" / "Example.json"
        write_json(source, {"process_params": {"nodes": [
            {"identifier": "reader", "inputs": {"files": {"value": ""}}},
        ]}})
        workspace = self.root / "validation-workspaces"
        manifest = self.root / "target" / "validation-logs" / "scenario-manifest.json"
        with patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
            self.run_script(
                "adapt_scenario_json.py", "--tools-dir", self.tools, "--order-file", self.order,
                "--source-dir", source.parent, "--workspace-dir", workspace,
                "--private-dataset-dir", self.root / "dataset", "--manifest", manifest,
            )
            data = json.loads(manifest.read_text())
            self.assertEqual(data["excluded_tools"], ["SlowWaveClassification"])
            self.assertEqual([r["run_id"] for r in data["runs"]], ["Example"])
            self.assertNotIn(NATUS_SUBJECT, (workspace / "Example.json").read_text())
            self.run_script(
                "resolve_tool_order.py", "--tools-dir", self.tools, "--order-file", self.order,
                "--manifest", manifest, "--format", "tsv",
            )
            self.validations["comparisons"] = [
                {"fileName": f"{NATUS_SUBJECT}.tsv", "fileType": "exists"},
            ]
            self.save()
            write_json(self.root / "status.json", {"Example": {"run_status": "pass"}})
            result = self.run_script(
                "compare_and_summarize.py", "--tools-dir", self.tools,
                "--run-status-file", self.root / "status.json",
                "--gold-standards-dir", self.root / "gold", "--gold-standard-tag", "test",
                "--compare-script", RUNNER / "compare_outputs.py", "--workspace-dir", workspace,
                "--output-summary-tsv", self.root / "summary.tsv",
                "--output-dir", self.root / "collected", "--append",
            )
            self.assertIn("SKIPPED (include_natus=false)", result.stdout)
            with (self.root / "summary.tsv").open() as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual([r["comparison_status"] for r in rows],
                             ["skipped-natus-excluded", "skipped-natus-excluded"])
            self.validations["comparisons"].append({
                "fileName": "record.tsv", "fileType": "exists",
                "generatedSearchRoots": [str(workspace)],
            })
            self.save()
            self.run_script(
                "compare_and_summarize.py", "--tools-dir", self.tools,
                "--run-status-file", self.root / "status.json",
                "--gold-standards-dir", self.root / "gold", "--gold-standard-tag", "test",
                "--compare-script", RUNNER / "compare_outputs.py", "--workspace-dir", workspace,
                "--output-summary-tsv", self.root / "summary.tsv",
                "--output-dir", self.root / "collected", "--append", expected_status=1,
            )
            with (self.root / "summary.tsv").open() as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(rows[-1]["comparison_status"], "fail")
            self.assertEqual(sum(r["tool_name"] == "SlowWaveClassification" for r in rows), 1)

    def test_natus_report_filter_keeps_other_subject_failures(self):
        reference = self.root / "reference.tsv"
        generated = self.root / "generated.tsv"
        reference.write_text(f"filename\tvalue\nrecord.edf\t2\n{NATUS_SUBJECT}.eeg\t9\n")
        generated.write_text("filename\tvalue\nrecord.edf\t2\n")
        for mode in ("generic", "bag-comparison", "absolute-tolerance", "table-tolerance"):
            extra = []
            if mode == "absolute-tolerance":
                extra = ["--absolute-tolerance", "0"]
            if mode == "table-tolerance":
                extra = ["--table-options", json.dumps({
                    "keyColumns": ["filename"],
                    "numericTolerance": {"columnPattern": "value", "relative": 0, "absolute": 0},
                })]
            with self.subTest(mode=mode), patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
                self.run_script("compare_outputs.py", "--tool-name", "Example",
                                "--reference-file", reference, "--generated-file", generated,
                                "--file-type", mode, *extra)
                generated.write_text("filename\tvalue\nrecord.edf\t3\n")
                self.run_script("compare_outputs.py", "--tool-name", "Example",
                                "--reference-file", reference, "--generated-file", generated,
                                "--file-type", mode, *extra, expected_status=1)
                generated.write_text("filename\tvalue\nrecord.edf\t2\n")
        self.run_script("compare_outputs.py", "--tool-name", "Example",
                        "--reference-file", reference, "--generated-file", generated, expected_status=1)
        for rows in ([["filename"], [NATUS_SUBJECT]], [[NATUS_SUBJECT], ["record"]]):
            with self.assertRaises(ValueError):
                filter_report_rows(rows, "report")

    def run_script(self, name, *arguments, expected_status=0):
        result = subprocess.run(
            [sys.executable, str(RUNNER / name), *map(str, arguments)],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected_status, result.stdout + result.stderr)
        return result

    def test_cli_adapts_config_relative_inputs_and_compares_outputs(self):
        self.adaptations["updates"].append({
            "identifier": "destination",
            "inputName": "constant",
            "value": {"kind": "workspacePath", "relativePath": "Example", "asDirectory": True},
        })
        self.save()
        source = self.root / "source" / "Example.json"
        write_json(source, {"process_params": {"nodes": [
            {"identifier": "reader", "inputs": {"files": {"value": ""}}},
            {"identifier": "destination", "inputs": {"constant": {"value": ""}}},
        ]}})
        workspace = self.root / "validation-workspaces"
        manifest = self.root / "manifest.json"
        self.run_script(
            "adapt_scenario_json.py", "--tools-dir", self.tools, "--order-file", self.order,
            "--source-dir", source.parent, "--workspace-dir", workspace,
            "--private-dataset-dir", self.root / "dataset", "--manifest", manifest,
        )
        adapted = json.loads((workspace / "Example.json").read_text(encoding="utf-8"))
        nodes = adapted["process_params"]["nodes"]
        self.assertEqual(nodes[0]["inputs"]["files"]["value"], {"record.edf": {"event_groups": []}})
        output = workspace / "Example"
        self.assertTrue(output.is_dir())
        self.assertEqual(Path(nodes[1]["inputs"]["constant"]["value"]).resolve(), output.resolve())
        runs = json.loads(manifest.read_text(encoding="utf-8"))["runs"]
        self.assertEqual([(run["run_id"], run["scenario_id"]) for run in runs], [("Example", "default")])
        self.run_script(
            "resolve_tool_order.py", "--tools-dir", self.tools, "--order-file", self.order,
            "--manifest", manifest, "--format", "tsv",
        )
        write_json(self.root / "status.json", {"Example": {"run_status": "pass"}})
        gold = self.root / "gold" / "Example"
        gold.mkdir(parents=True)
        (gold / "report.tsv").write_text("value\n1.123440\n2\n", encoding="utf-8")
        (output / "report.tsv").write_text("2\nvalue\n1.123441\n", encoding="utf-8")
        self.run_script(
            "compare_and_summarize.py", "--tools-dir", self.tools,
            "--run-status-file", self.root / "status.json", "--gold-standards-dir", gold.parent,
            "--gold-standard-tag", "test", "--compare-script", RUNNER / "compare_outputs.py",
            "--workspace-dir", workspace, "--output-summary-tsv", self.root / "summary.tsv",
            "--output-dir", self.root / "collected",
        )
        with (self.root / "summary.tsv").open(encoding="utf-8", newline="") as stream:
            row = next(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(row["comparison_status"], "pass")

    def test_missing_gold_standard_fails_and_preserves_generated_outputs(self):
        workspace = self.root / "validation-workspaces"
        output = workspace / "Example"
        output.mkdir(parents=True)
        content = "value\n1.1234\n"
        (output / "report.tsv").write_text(content, encoding="utf-8")
        for explicit in (False, True):
            for directory_exists in (False, True):
                with self.subTest(explicit=explicit, directory_exists=directory_exists):
                    self.validations = (
                        {"scenarios": {"example": {"comparisons": [self.comparison]}}}
                        if explicit else {"comparisons": [self.comparison]}
                    )
                    self.save()
                    name = "Example/example" if explicit else "Example"
                    gold = self.root / f"gold-{explicit}-{directory_exists}"
                    if directory_exists:
                        (gold / name).mkdir(parents=True)
                    write_json(self.root / "status.json", {"Example": {
                        "run_status": "pass", "tool_name": "Example",
                        "scenario_id": "example" if explicit else "default",
                        "explicit_scenario": explicit,
                    }})
                    result = self.run_script(
                        "compare_and_summarize.py", "--tools-dir", self.tools,
                        "--run-status-file", self.root / "status.json",
                        "--gold-standards-dir", gold, "--gold-standard-tag", "test",
                        "--compare-script", RUNNER / "compare_outputs.py",
                        "--workspace-dir", workspace,
                        "--output-summary-tsv", self.root / "summary.tsv",
                        "--output-dir", self.root / "collected", expected_status=1,
                    )
                    with (self.root / "summary.tsv").open(encoding="utf-8", newline="") as stream:
                        row = next(csv.DictReader(stream, delimiter="\t"))
                    self.assertEqual(row["comparison_status"], "fail-missing-gold-standard")
                    self.assertIn("FAIL (fail-missing-gold-standard)", result.stdout)
                    self.assertEqual(
                        (self.root / "collected" / name / "generated_report.tsv").read_text(encoding="utf-8"),
                        content,
                    )

    def test_empty_gold_tag_and_exists_checks_still_succeed(self):
        workspace = self.root / "validation-workspaces"
        output = workspace / "Example"
        output.mkdir(parents=True)
        (output / "report.tsv").write_text("value\n1\n", encoding="utf-8")
        write_json(self.root / "status.json", {"Example": {"run_status": "pass"}})
        for file_type, tag, status in (
            ("bag-comparison", "", "skipped-no-gold-standard-tag"),
            ("exists", "test", "pass"),
        ):
            with self.subTest(file_type=file_type):
                comparison = dict(self.comparison, fileType=file_type)
                if file_type == "exists":
                    comparison.pop("precision")
                self.validations = {"comparisons": [comparison]}
                self.save()
                self.run_script(
                    "compare_and_summarize.py", "--tools-dir", self.tools,
                    "--run-status-file", self.root / "status.json",
                    "--gold-standards-dir", self.root / "gold", "--gold-standard-tag", tag,
                    "--compare-script", RUNNER / "compare_outputs.py",
                    "--workspace-dir", workspace,
                    "--output-summary-tsv", self.root / "summary.tsv",
                    "--output-dir", self.root / "collected",
                )
                with (self.root / "summary.tsv").open(encoding="utf-8", newline="") as stream:
                    row = next(csv.DictReader(stream, delimiter="\t"))
                self.assertEqual(row["comparison_status"], status)

    def test_scenario_overrides_disabled_runs_and_order_are_preserved(self):
        self.adaptations["scenarios"] = [
            {"id": "enabled", "updates": [{
                "identifier": "reader", "inputName": "files",
                "value": {"kind": "literal", "value": "override"},
            }]},
            {"id": "disabled", "enabled": False, "updates": []},
        ]
        self.validations = {"scenarios": {
            key: {"comparisons": [self.comparison]} for key in ("enabled", "disabled")
        }}
        self.save()
        write_json(self.tools / "Earlier" / "adaptations.json", self.adaptations)
        write_json(self.tools / "Earlier" / "validations.json", self.validations)
        write_json(self.order, ["Earlier", "Example"])
        self.assertEqual(validate_configuration(self.tools, self.order), (2, 2))
        self.assertEqual(resolve_tools(self.tools, self.order, "Example,Earlier"), ["Earlier", "Example"])
        definitions = load_adaptations(self.tools)
        runs = expand_scenarios("Example", definitions["Example"], self.root)
        self.assertEqual([run["run_id"] for run in runs], ["Example__enabled"])
        self.assertEqual(runs[0]["updates"][-1]["value"]["value"], "override")
        self.assertTrue(Path(runs[0]["updates"][0]["value"]["relativePath"]).is_absolute())
        source = self.root / "source" / "Example.json"
        write_json(source, {"process_params": {"nodes": [
            {"identifier": "reader", "inputs": {"files": {"value": ""}}},
        ]}})
        workspace = self.root / "validation-workspaces"
        self.run_script(
            "adapt_scenario_json.py", "--tools-dir", self.tools, "--order-file", self.order,
            "--source-dir", source.parent, "--workspace-dir", workspace,
            "--private-dataset-dir", self.root / "dataset", "--manifest", self.root / "manifest.json",
            "--tools", "Example",
        )
        self.assertEqual([path.name for path in workspace.glob("*.json")], ["Example__enabled.json"])
        adapted = json.loads((workspace / "Example__enabled.json").read_text(encoding="utf-8"))
        self.assertEqual(adapted["process_params"]["nodes"][0]["inputs"]["files"]["value"], "override")
        self.assertEqual(adapted["metadata"]["scenarioId"], "enabled")

    def test_missing_references_order_and_scenario_mismatches_fail(self):
        with self.subTest("missing input"):
            (self.root / "shared" / "inputs" / "files.json").unlink()
            with self.assertRaisesRegex(ValueError, "Example:"):
                validate_configuration(self.tools, self.order)
            write_json(self.root / "shared" / "inputs" / "files.json", {})
        for order in ([], ["Unknown"], ["Example", "Example"]):
            with self.subTest(order=order):
                write_json(self.order, order)
                with self.assertRaises(ValueError):
                    validate_configuration(self.tools, self.order)
        write_json(self.order, ["Example"])
        self.adaptations["scenarios"] = [{"id": "one", "updates": []}]
        self.validations = {"scenarios": {"other": {"comparisons": [self.comparison]}}}
        self.save()
        with self.assertRaisesRegex(ValueError, "identifiers must match"):
            validate_configuration(self.tools, self.order)
        (self.directory / "validations.json").unlink()
        with self.assertRaises(FileNotFoundError):
            validate_configuration(self.tools, self.order)

    def test_invalid_comparisons_and_updates_are_rejected(self):
        for invalid in (
            {"fileType": "unknown"},
            {"precision": True},
            {"precision": -1},
            {"absoluteTolerance": 0.1},
            {"fileType": "absolute-tolerance", "absoluteTolerance": 0.1},
            {"fileType": "table-tolerance", "keyColumns": []},
        ):
            with self.subTest(invalid=invalid):
                self.validations = {"comparisons": [dict(self.comparison, **invalid)]}
                self.save()
                with self.assertRaises(ValueError):
                    validate_configuration(self.tools, self.order)
        self.validations = {"comparisons": [self.comparison, dict(self.comparison)]}
        self.save()
        with self.assertRaisesRegex(ValueError, "duplicate comparison"):
            validate_configuration(self.tools, self.order)
        self.validations = {"comparisons": [self.comparison]}
        self.adaptations["updates"][0]["value"]["kind"] = "unknown"
        self.save()
        with self.assertRaisesRegex(ValueError, "Unknown value kind"):
            validate_configuration(self.tools, self.order)

    def test_repository_configuration_is_consistent(self):
        tools, runs = validate_configuration(ROOT / "tools", ROOT / "config" / "tool_execution_order.json")
        self.assertGreater(tools, 0)
        self.assertGreater(runs, 0)


if __name__ == "__main__":
    unittest.main()
