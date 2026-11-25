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
from natus_validation import NATUS_SUBJECT, filter_comparisons, filter_input, filter_report_rows
from prepare_cohort_inputs import prepare_inputs
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

    def test_prepare_independent_non_natus_cohort_inputs(self):
        gold = self.root / "gold"
        workspace = self.root / "workspace"
        order = ROOT / "config" / "tool_execution_order.json"
        inputs = {
            "PowerSpectralAnalysis/pwelch/EEG_spectral_power_cohort_report_Welch_without_natus.tsv":
                "EEG_spectral_power_cohort_report_Welch.tsv",
            "PowerSpectralAnalysis/irasa/EEG_spectral_power_cohort_report_IRASA_periodic_without_natus.tsv":
                "EEG_spectral_power_cohort_report_IRASA_periodic.tsv",
            "SlowWaveDetection/Slow-Waves-Cohort-report_without_natus.tsv":
                "Slow-Waves-Cohort-report.tsv",
        }
        for path in inputs:
            source = gold / path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("filename\tvalue\nrecord.edf\t1\n", encoding="utf-8")
        requested = "PSAImages,PSACohortReview,DetectionsCohortReview"
        with patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
            prepare_inputs(ROOT / "tools", order, requested, gold, workspace)
            self.assertEqual({p.name for p in workspace.iterdir()}, set(inputs.values()))
            for source, target in inputs.items():
                self.assertEqual((workspace / target).read_bytes(), (gold / source).read_bytes())
            with self.assertRaises(FileExistsError):
                prepare_inputs(ROOT / "tools", order, requested, gold, workspace)

            other_workspace = self.root / "generated"
            prepare_inputs(ROOT / "tools", order,
                           requested + ",PowerSpectralAnalysis,SlowWaveDetection",
                           self.root / "missing", other_workspace)
            self.assertFalse(other_workspace.exists())
            partial_workspace = self.root / "partial"
            prepare_inputs(ROOT / "tools", order, requested + ",PowerSpectralAnalysis", gold, partial_workspace)
            self.assertEqual([p.name for p in partial_workspace.iterdir()], ["Slow-Waves-Cohort-report.tsv"])

        with patch.dict(os.environ, {"INCLUDE_NATUS": "true"}):
            prepare_inputs(ROOT / "tools", order, requested, self.root / "missing", self.root / "full")
            self.assertFalse((self.root / "full").exists())

    def test_prepare_inputs_rejects_missing_or_invalid_reference(self):
        gold = self.root / "gold"
        workspace = self.root / "workspace"
        source = gold / "PowerSpectralAnalysis" / "pwelch" / (
            "EEG_spectral_power_cohort_report_Welch_without_natus.tsv"
        )
        source.parent.mkdir(parents=True)
        order = ROOT / "config" / "tool_execution_order.json"
        with patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
            for content, error in ((None, FileNotFoundError), ("header\n", ValueError),
                                   (f"filename\n{NATUS_SUBJECT}\n", ValueError)):
                with self.subTest(content=content):
                    if content is not None:
                        source.write_text(content, encoding="utf-8")
                    with self.assertRaises(error):
                        prepare_inputs(ROOT / "tools", order, "PSAImages", gold, workspace)
                    self.assertFalse(workspace.exists())

    def test_psa_images_excludes_only_natus_channel_outputs(self):
        validations = json.loads((ROOT / "tools" / "PSAImages" / "validations.json").read_text())
        comparisons = validations["comparisons"]
        retained = filter_comparisons(comparisons, "PSAImages")
        excluded = {item["fileName"] for item in comparisons if item not in retained}
        self.assertEqual(len(excluded), 6)
        self.assertTrue(all(any(channel in name for channel in ("C3-RC", "F3-RC", "O1-RC"))
                            for name in excluded))
        self.assertTrue(any("cohort_psa_mean_std_Total_C3.pdf" == item["fileName"] for item in retained))

    def test_classifier_independent_inputs_and_missing_files(self):
        gold = self.root / "gold" / "SlowWaveDetection"
        gold.mkdir(parents=True)
        (gold / "Slow-Waves-Cohort-report_without_natus.tsv").write_text("filename\nrecord.edf\n")
        for directory, suffix in (("slow_wave_characteristics", "_sw_carrier.tsv"),
                                  ("slow_wave_sleep_stages", "_sw_carrier_stages.tsv")):
            (gold / directory).mkdir()
            for subject in ("01-01-0001", "learn-nsrr01", "learn-nsrr02"):
                (gold / directory / (subject + suffix)).write_text("header\ndata\n")
        workspace = self.root / "workspace"
        order = ROOT / "config" / "tool_execution_order.json"
        with patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
            prepare_inputs(ROOT / "tools", order, "SlowWaveClassification", gold.parent, workspace)
            self.assertEqual(len(list(workspace.rglob("*.tsv"))), 7)
            self.assertTrue((workspace / "Slow-Waves-Cohort-report.tsv").is_file())
            self.assertNotIn(NATUS_SUBJECT, repr([str(p) for p in workspace.rglob("*")]))
            missing = gold / "slow_wave_sleep_stages" / "learn-nsrr01_sw_carrier_stages.tsv"
            missing.unlink()
            with self.assertRaises(FileNotFoundError):
                prepare_inputs(ROOT / "tools", order, "SlowWaveClassification", gold.parent, self.root / "missing")
            self.assertFalse((self.root / "missing").exists())
            prepare_inputs(ROOT / "tools", order, "SlowWaveDetection,SlowWaveClassification",
                           self.root / "absent", self.root / "generated")
            self.assertFalse((self.root / "generated").exists())

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
        write_json(source.parent / "SlowWaveClassification.json", json.loads(source.read_text()))
        workspace = self.root / "validation-workspaces"
        manifest = self.root / "target" / "validation-logs" / "scenario-manifest.json"
        with patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
            self.run_script(
                "adapt_scenario_json.py", "--tools-dir", self.tools, "--order-file", self.order,
                "--source-dir", source.parent, "--workspace-dir", workspace,
                "--private-dataset-dir", self.root / "dataset", "--manifest", manifest,
            )
            data = json.loads(manifest.read_text())
            self.assertEqual(data["excluded_tools"], [])
            self.assertEqual([r["run_id"] for r in data["runs"]], ["Example", "SlowWaveClassification"])
            self.assertNotIn(NATUS_SUBJECT, (workspace / "Example.json").read_text())
            self.assertNotIn(NATUS_SUBJECT, (workspace / "SlowWaveClassification.json").read_text())
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
            self.assertEqual([r["comparison_status"] for r in rows], ["skipped-natus-excluded"])
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
            self.assertEqual(sum(r["tool_name"] == "SlowWaveClassification" for r in rows), 0)

    def test_distinct_non_natus_gold_reference_is_required(self):
        self.validations = {"comparisons": [{
            "fileName": "report.tsv", "goldFileNameWithoutNatus": "report_without_natus.tsv",
            "fileType": "bag-comparison", "generatedSearchRoots": [str(self.root / "output")],
        }]}
        self.save()
        gold = self.root / "gold" / "Example"
        gold.mkdir(parents=True)
        (gold / "report.tsv").write_text("subject\tvalue\nrecord\t2\n")
        alternate = gold / "report_without_natus.tsv"
        alternate.write_text("subject\tvalue\nrecord\t1\n")
        output = self.root / "output"
        output.mkdir()
        (output / "report.tsv").write_text("subject\tvalue\nrecord\t1\n")
        write_json(self.root / "status.json", {"Example": {"run_status": "pass"}})
        args = (
            "--tools-dir", self.tools, "--run-status-file", self.root / "status.json",
            "--gold-standards-dir", gold.parent, "--gold-standard-tag", "test",
            "--compare-script", RUNNER / "compare_outputs.py", "--workspace-dir", self.root,
            "--output-summary-tsv", self.root / "summary.tsv", "--output-dir", self.root / "collected",
        )
        with patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
            result = self.run_script("compare_and_summarize.py", *args)
            self.assertIn("report_without_natus.tsv", result.stdout)
            alternate.unlink()
            result = self.run_script("compare_and_summarize.py", *args, expected_status=1)
            self.assertIn("fail-missing-gold-standard", result.stdout)
        with patch.dict(os.environ, {"INCLUDE_NATUS": "true"}):
            result = self.run_script("compare_and_summarize.py", *args, expected_status=1)
            self.assertIn("Comparison FAILED", result.stdout)
            (output / "report.tsv").write_text("subject\tvalue\nrecord\t2\n")
            self.run_script("compare_and_summarize.py", *args)

    def test_psa_cohort_review_mode_specific_outputs_and_comparisons(self):
        definition = load_adaptations(ROOT / "tools")["PSACohortReview"]
        updates = definition["updates"] + [
            update for scenario in definition["scenarios"] for update in scenario["updates"]
        ]
        identifier = updates[0]["identifier"]
        source = self.root / "source" / "PSACohortReview.json"
        write_json(source, {"process_params": {"nodes": [{
            "identifier": identifier,
            "inputs": {update["inputName"]: {"value": ""} for update in updates},
        }]}})
        for enabled in ("true", "false"):
            with self.subTest(include_natus=enabled), patch.dict(os.environ, {"INCLUDE_NATUS": enabled}):
                workspace = self.root / "validation-workspaces"
                manifest = self.root / enabled / "manifest.json"
                self.run_script(
                    "adapt_scenario_json.py", "--tools-dir", ROOT / "tools",
                    "--source-dir", source.parent, "--workspace-dir", workspace,
                    "--private-dataset-dir", self.root / "dataset", "--manifest", manifest,
                    "--tools", "PSACohortReview",
                )
                status = {}
                for scenario, base in (("pwelch", "PSACohortReview"), ("irasa", "PSACohortReview_irasa")):
                    run_id = f"PSACohortReview__{scenario}"
                    adapted = json.loads((workspace / f"{run_id}.json").read_text())
                    inputs = adapted["process_params"]["nodes"][0]["inputs"]
                    expected_base = base + ("_without_natus" if enabled == "false" else "")
                    self.assertEqual(Path(inputs["output_dir"]["value"]).stem, expected_base)
                    if enabled == "false":
                        self.assertNotIn(NATUS_SUBJECT, repr(inputs))
                    gold = self.root / enabled / "gold" / "PSACohortReview" / scenario
                    gold.mkdir(parents=True)
                    for suffix in ("clean", "transposed"):
                        filename = f"{expected_base}_{suffix}.tsv"
                        (workspace / filename).write_text("subject\tvalue\nrecord\t1\n")
                        (gold / filename).write_text("subject\tvalue\nrecord\t1\n")
                    status[run_id] = {
                        "run_status": "pass", "tool_name": "PSACohortReview",
                        "scenario_id": scenario, "explicit_scenario": True,
                        "json_path": str(workspace / f"{run_id}.json"),
                    }
                status_file = self.root / enabled / "status.json"
                write_json(status_file, status)
                arguments = (
                    "--tools-dir", ROOT / "tools", "--run-status-file", status_file,
                    "--gold-standards-dir", self.root / enabled / "gold",
                    "--compare-script", RUNNER / "compare_outputs.py", "--workspace-dir", workspace,
                    "--output-summary-tsv", self.root / enabled / "summary.tsv",
                    "--output-dir", self.root / enabled / "collected",
                )
                self.run_script("compare_and_summarize.py", *arguments, "--gold-standard-tag", "test")
                self.run_script("compare_and_summarize.py", *arguments)
                collected = self.root / enabled / "collected" / "PSACohortReview" / "pwelch"
                expected_name = "PSACohortReview" + ("_without_natus" if enabled == "false" else "")
                self.assertTrue((collected / f"generated_{expected_name}_clean.tsv").is_file())

    def test_detections_review_non_natus_input_outputs_and_references(self):
        definition = load_adaptations(ROOT / "tools")["DetectionsCohortReview"]
        updates = definition["updates"]
        source = self.root / "source" / "DetectionsCohortReview.json"
        write_json(source, {"process_params": {"nodes": [{
            "identifier": updates[0]["identifier"],
            "inputs": {update["inputName"]: {"value": ""} for update in updates},
        }]}})
        workspace = self.root / "validation-workspaces"
        gold = self.root / "gold"
        cohort = gold / "SlowWaveDetection" / "Slow-Waves-Cohort-report_without_natus.tsv"
        cohort.parent.mkdir(parents=True)
        cohort.write_text("filename\tvalue\nrecord.edf\t1\n")
        for enabled in ("false", "true"):
            with self.subTest(include_natus=enabled), patch.dict(os.environ, {"INCLUDE_NATUS": enabled}):
                prepare_inputs(ROOT / "tools", ROOT / "config" / "tool_execution_order.json",
                               "DetectionsCohortReview", gold, workspace)
                self.run_script(
                    "adapt_scenario_json.py", "--tools-dir", ROOT / "tools",
                    "--source-dir", source.parent, "--workspace-dir", workspace,
                    "--private-dataset-dir", self.root / "dataset", "--tools", "DetectionsCohortReview",
                )
                adapted = json.loads((workspace / "DetectionsCohortReview.json").read_text())
                inputs = adapted["process_params"]["nodes"][0]["inputs"]
                base = "Slow-Waves-review-report" + ("_without_natus" if enabled == "false" else "")
                self.assertEqual(Path(inputs["output_file"]["value"]).name, base + ".tsv")
                if enabled == "false":
                    self.assertNotIn(NATUS_SUBJECT, repr(inputs))
                    self.assertIn("Slow-Waves-Cohort-report.tsv", inputs["filenames"]["value"])
                    self.assertEqual((workspace / "Slow-Waves-Cohort-report.tsv").read_bytes(),
                                     cohort.read_bytes())
                references = gold / "DetectionsCohortReview"
                references.mkdir(exist_ok=True)
                for suffix in ("clean", "transposed"):
                    filename = f"{base}_{suffix}.tsv"
                    (workspace / filename).write_text("subject\tvalue\nrecord\t1\n")
                    (references / filename).write_text("subject\tvalue\nrecord\t1\n")
                write_json(self.root / "status.json", {"DetectionsCohortReview": {"run_status": "pass"}})
                arguments = (
                    "--tools-dir", ROOT / "tools", "--run-status-file", self.root / "status.json",
                    "--gold-standards-dir", gold, "--compare-script", RUNNER / "compare_outputs.py",
                    "--workspace-dir", workspace, "--output-summary-tsv", self.root / "summary.tsv",
                    "--output-dir", self.root / "collected",
                )
                self.run_script("compare_and_summarize.py", *arguments, "--gold-standard-tag", "test")
                self.run_script("compare_and_summarize.py", *arguments)
                self.assertTrue((self.root / "collected" / "DetectionsCohortReview" /
                                 f"generated_{base}_clean.tsv").is_file())
                (references / f"{base}_clean.tsv").unlink()
                result = self.run_script("compare_and_summarize.py", *arguments,
                                         "--gold-standard-tag", "test", expected_status=1)
                self.assertIn("fail-missing-gold-standard", result.stdout)

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

    def test_non_natus_text_comparison_accepts_one_line_and_detects_differences(self):
        reference = self.root / "reference.txt"
        generated = self.root / "generated.txt"
        for mode in ("generic", "report"):
            for newline in ("", "\n", "\r\n"):
                with self.subTest(mode=mode, newline=newline), patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
                    reference.write_bytes(("Validation successful. No issues found." + newline).encode())
                    generated.write_bytes(reference.read_bytes())
                    args = ("--tool-name", "ValidateSnoozTSVFile", "--reference-file", reference,
                            "--generated-file", generated, "--file-type", mode)
                    self.run_script("compare_outputs.py", *args)
                    generated.write_bytes(("Validation failed." + newline).encode())
                    self.run_script("compare_outputs.py", *args, expected_status=1)
                    reference.write_bytes((NATUS_SUBJECT + "\nValidation failed." + newline).encode())
                    self.run_script("compare_outputs.py", *args)
                    reference.write_text(NATUS_SUBJECT + "\n")
                    result = self.run_script("compare_outputs.py", *args, expected_status=1)
                    self.assertIn("no data remains for comparison", result.stderr)
        with patch.dict(os.environ, {"INCLUDE_NATUS": "false"}):
            reference.write_text("filename\tvalue\n")
            generated.write_text(reference.read_text())
            self.run_script("compare_outputs.py", "--tool-name", "Example",
                            "--reference-file", reference, "--generated-file", generated,
                            "--file-type", "bag-comparison", expected_status=1)

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
            {"requiresNatus": "true"},
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
