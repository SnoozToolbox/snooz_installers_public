#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare generated tool outputs against gold-standard references, write a
tool-run-summary.tsv, and collect generated/reference files per tool into
validation-outputs/.

This is the shared, cross-platform (Windows/macOS/Linux) equivalent of the
comparison logic previously embedded only in validation_windows.yml's
PowerShell, so all three platforms produce identical comparison results and
artifacts.

Usage:
    python compare_and_summarize.py \
        --run-status-file target/validation-logs/run-status.json \
        --tool-validations-file ci/validation_tools/tool_validations.json \
        --gold-standards-dir gold-standards/extracted \
        --gold-standard-tag v1.0.0 \
        --compare-script ci/validation_tools/compare_outputs.py \
        --workspace-dir validation-workspaces \
        --output-summary-tsv tool-run-summary.tsv \
        --output-dir validation-outputs
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def find_first_file_by_name(roots, file_name):
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        matches = sorted(root_path.rglob(file_name), key=lambda p: str(p))
        if matches:
            return matches[0]
    return None


def get_tool_version(scenario_path):
    if not scenario_path.exists():
        return "unknown"
    try:
        with open(scenario_path, 'r', encoding='utf-8') as f:
            scenario = json.load(f)
        return str(scenario.get("tool_params", {}).get("tool_version", "unknown"))
    except Exception:
        return "unknown"


def run_comparison(compare_script, tool_name, generated_file, reference_file, file_type, precision):
    args = [
        sys.executable, str(compare_script),
        "--tool-name", tool_name,
        "--generated-file", str(generated_file),
        "--reference-file", str(reference_file),
        "--file-type", file_type,
        "--max-diff-lines", "50",
    ]
    if precision is not None:
        args += ["--precision", str(precision)]

    result = subprocess.run(args, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output


def compare_tool(tool_name, tool_config, gold_dir, generated_search_roots_default, compare_script):
    """Run all configured comparisons for one tool. Returns (status, validated_files, output_dir_files)."""
    comparisons = tool_config.get("comparisons", [])
    if not comparisons:
        return "skipped-no-comparisons-configured", [], []

    validated_files = []
    collected_files = []  # list of (generated_path, gold_path, file_name)

    for comparison in comparisons:
        file_name = comparison.get("fileName", "")
        generated_file_name = comparison.get("generatedFileName") or file_name
        gold_file_name = comparison.get("goldFileName") or file_name
        file_type = comparison.get("fileType", "generic")
        precision = comparison.get("precision")
        generated_roots = comparison.get("generatedSearchRoots") or generated_search_roots_default

        if not generated_file_name or not gold_file_name:
            print(f"::error::{tool_name} invalid comparison entry. Define fileName (or both generatedFileName and goldFileName).")
            return "fail", validated_files, collected_files

        generated_file = find_first_file_by_name(generated_roots, generated_file_name)
        if generated_file is None:
            print(f"::error::{tool_name} generated file not found: {generated_file_name}")
            for root in generated_roots:
                print(f"  Searched root: {root}")
            return "fail", validated_files, collected_files

        tool_gold_dir = Path(gold_dir) / tool_name
        if not tool_gold_dir.exists():
            print(f"::error::{tool_name} gold-standard directory not found: {tool_gold_dir}")
            return "fail", validated_files, collected_files

        gold_matches = sorted(tool_gold_dir.rglob(gold_file_name), key=lambda p: str(p))
        if not gold_matches:
            print(f"::error::{tool_name} gold-standard file not found in {tool_gold_dir}: {gold_file_name}")
            return "fail", validated_files, collected_files
        gold_file = gold_matches[0]

        print(f"Comparing {tool_name} output file: {generated_file_name}")
        print(f"Resolved generated path: {generated_file}")
        passed, output = run_comparison(compare_script, tool_name, generated_file, gold_file, file_type, precision)
        print(output)

        collected_files.append((generated_file, gold_file, generated_file_name))

        if not passed:
            print(f"::error::\u2717 Comparison FAILED for {tool_name} : {generated_file_name}")
            print(f"::error::Generated file: {generated_file}")
            print(f"::error::Gold standard: {gold_file}")
            return "fail", validated_files, collected_files

        print(f"\u2713 Comparison PASSED for {tool_name} : {generated_file_name}")
        if generated_file_name.lower() == gold_file_name.lower():
            validated_files.append(generated_file_name)
        else:
            validated_files.append(f"{generated_file_name} (ref: {gold_file_name})")

    return "pass", validated_files, collected_files


def collect_output_files(output_dir, tool_name, collected_files):
    tool_output_dir = Path(output_dir) / tool_name
    tool_output_dir.mkdir(parents=True, exist_ok=True)
    for generated_file, gold_file, _ in collected_files:
        dest_gen = tool_output_dir / f"generated_{generated_file.name}"
        dest_gold = tool_output_dir / f"reference_{gold_file.name}"
        dest_gen.write_bytes(generated_file.read_bytes())
        dest_gold.write_bytes(gold_file.read_bytes())
        print(f"Copied generated: {generated_file} -> {dest_gen}")
        print(f"Copied reference: {gold_file} -> {dest_gold}")


def main():
    parser = argparse.ArgumentParser(description="Compare tool outputs against gold standards and write a run summary")
    parser.add_argument('--run-status-file', required=True, help='JSON file mapping tool name to {run_status, execution_log}')
    parser.add_argument('--tool-validations-file', required=True, help='Path to tool_validations.json')
    parser.add_argument('--gold-standards-dir', required=True, help='Path to extracted gold standards (one subfolder per tool)')
    parser.add_argument('--gold-standard-tag', default='', help='Gold standard release tag (empty disables comparison)')
    parser.add_argument('--compare-script', required=True, help='Path to compare_outputs.py')
    parser.add_argument('--workspace-dir', required=True, help='Path to validation-workspaces (used for tool_version lookup)')
    parser.add_argument('--generated-search-roots', default='validation-workspaces,private-dataset', help='Comma-separated default search roots for generated files')
    parser.add_argument('--output-summary-tsv', required=True, help='Destination path for tool-run-summary.tsv')
    parser.add_argument('--output-dir', required=True, help='Destination directory for collected generated/reference files')
    parser.add_argument('--append', action='store_true', help='Append to the summary TSV and keep existing output-dir contents (use when validating one tool right after it runs, instead of all tools at the end)')

    args = parser.parse_args()

    with open(args.run_status_file, 'r', encoding='utf-8') as f:
        run_status = json.load(f)

    tool_validations = {}
    validations_path = Path(args.tool_validations_file)
    if validations_path.exists():
        with open(validations_path, 'r', encoding='utf-8') as f:
            tool_validations = json.load(f)

    generated_search_roots_default = [r.strip() for r in args.generated_search_roots.split(',') if r.strip()]
    workspace_dir = Path(args.workspace_dir)
    output_dir = Path(args.output_dir)
    if not args.append and output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    any_failure = False

    for tool_name, run_info in run_status.items():
        print("\n==========================================")
        print(f"\nRunning comparisons for: {tool_name}")
        # If run-status included an execution log, show a short tail for context
        exec_log = run_info.get("execution_log")
        if exec_log:
            try:
                exec_path = Path(exec_log)
                if exec_path.exists():
                    print(f"--- Headless execution log for {tool_name} (last 200 lines) ---")
                    try:
                        for line in exec_path.read_text(encoding='utf-8').splitlines()[-200:]:
                            print(line)
                    except Exception:
                        print(f"(Could not read execution log: {exec_path})")
                else:
                    print(f"(Execution log path listed but file not found: {exec_log})")
            except Exception:
                print(f"(Invalid execution log path: {exec_log})")

        tool_run_status = run_info.get("run_status", "fail")
        scenario_path = workspace_dir / f"{tool_name}.json"
        tool_version = get_tool_version(scenario_path)
        validated_files = []

        if tool_run_status != "pass":
            comparison_status = tool_run_status
            any_failure = True
        elif not args.gold_standard_tag:
            comparison_status = "skipped-no-gold-standard-tag"
        elif tool_name not in tool_validations or not isinstance(tool_validations.get(tool_name), dict):
            comparison_status = "not-configured"
        else:
            comparison_status, validated_files, collected_files = compare_tool(
                tool_name,
                tool_validations[tool_name],
                args.gold_standards_dir,
                generated_search_roots_default,
                args.compare_script,
            )
            if collected_files:
                collect_output_files(output_dir, tool_name, collected_files)
            if comparison_status == "fail":
                any_failure = True

        summary_rows.append({
            "tool_name": tool_name,
            "tool_version": tool_version,
            "json_name": f"{tool_name}.json",
            "run_status": tool_run_status,
            "comparison_status": comparison_status,
            "validated_files": "; ".join(validated_files) if validated_files else "none",
        })

    output_summary_path = Path(args.output_summary_tsv)
    output_summary_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not (args.append and output_summary_path.exists())
    with open(output_summary_path, 'a' if args.append else 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["tool_name", "tool_version", "json_name", "run_status", "comparison_status", "validated_files"], delimiter='\t')
        if write_header:
            writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Tool run summary TSV written to: {output_summary_path}")

    print("")
    print("==========================================")
    print("COMPARISON RESULTS SUMMARY")
    print("==========================================")
    for row in summary_rows:
        status = row["comparison_status"]
        if status in ("skipped-no-gold-standard-tag",):
            print(f"  \u2298 {row['tool_name']}: SKIPPED (no gold standard tag)")
        elif status == "skipped-no-comparisons-configured":
            print(f"  \u2298 {row['tool_name']}: SKIPPED (no comparisons configured)")
        elif status == "not-configured":
            print(f"  \u2298 {row['tool_name']}: NOT CONFIGURED")
        elif status == "pass":
            print(f"  \u2713 {row['tool_name']}: PASS")
        else:
            print(f"  \u2717 {row['tool_name']}: FAIL ({status})")
    print("==========================================")
    print("")

    return 1 if any_failure else 0


if __name__ == '__main__':
    sys.exit(main())
