#!/usr/bin/env python3
"""Prepare non-NATUS cohort inputs when their producer is not selected."""

import argparse
import ast
import shutil
from pathlib import Path

from configuration import load_adaptations
from natus_validation import NATUS_SUBJECT, filter_input, include_natus
from resolve_tool_order import resolve_tools
from validation_scenarios import expand_scenarios


def prepare_inputs(tools_dir, order_file, requested, gold_dir, workspace_dir):
    tools = set(resolve_tools(tools_dir, order_file, requested))
    if include_natus():
        return

    adaptations = load_adaptations(tools_dir)
    review_scenarios = {
        run["scenario_id"]
        for run in expand_scenarios("PSACohortReview", adaptations["PSACohortReview"], workspace_dir)
    } if "PSACohortReview" in tools else set()
    needed = []
    if "PowerSpectralAnalysis" not in tools:
        if "PSAImages" in tools or "pwelch" in review_scenarios:
            needed.append(("PowerSpectralAnalysis/pwelch", "EEG_spectral_power_cohort_report_Welch.tsv"))
        if "irasa" in review_scenarios:
            needed.append(("PowerSpectralAnalysis/irasa", "EEG_spectral_power_cohort_report_IRASA_periodic.tsv"))
    if {"DetectionsCohortReview", "SlowWaveClassification"} & tools and "SlowWaveDetection" not in tools:
        needed.append(("SlowWaveDetection", "Slow-Waves-Cohort-report.tsv"))

    copies = []
    for folder, filename in needed:
        name = Path(filename)
        source = gold_dir / folder / f"{name.stem}_without_natus{name.suffix}"
        destination = workspace_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"Required non-NATUS gold-standard input not found: {source}")
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite cohort input: {destination}")
        nonempty_lines = 0
        with source.open(encoding="utf-8-sig") as stream:
            for line in stream:
                if NATUS_SUBJECT in line:
                    raise ValueError(f"NATUS subject found in non-NATUS gold-standard input: {source}")
                if line.strip():
                    nonempty_lines += 1
        if nonempty_lines < 2:
            raise ValueError(f"Non-NATUS gold-standard input has no data rows: {source}")
        copies.append((source, destination))
    if "SlowWaveClassification" in tools and "SlowWaveDetection" not in tools:
        updates = adaptations["SlowWaveClassification"]["updates"]
        for input_name, directory in (("sw_char_files", "slow_wave_characteristics"),
                                      ("sw_stages_files", "slow_wave_sleep_stages")):
            matches = [update for update in updates if update.get("inputName") == input_name]
            if len(matches) != 1 or matches[0]["value"]["kind"] != "literal":
                raise ValueError(f"Expected one literal SlowWaveClassification {input_name} input")
            paths = ast.literal_eval(filter_input(matches[0]["value"]["value"]))
            if not isinstance(paths, list) or not paths:
                raise ValueError(f"SlowWaveClassification {input_name} must be a non-empty list")
            prefix = f"$GITHUB_WORKSPACE/validation-workspaces/{directory}/"
            for path in paths:
                if not isinstance(path, str) or not path.startswith(prefix):
                    raise ValueError(f"Unexpected SlowWaveClassification {input_name} path: {path!r}")
                filename = path[len(prefix):]
                if not filename or Path(filename).name != filename or "\\" in filename:
                    raise ValueError(f"Invalid SlowWaveClassification input filename: {filename!r}")
                source = gold_dir / "SlowWaveDetection" / directory / filename
                destination = workspace_dir / directory / filename
                if not source.is_file() or source.stat().st_size == 0:
                    raise FileNotFoundError(f"Required SlowWaveClassification input missing or empty: {source}")
                if destination.exists():
                    raise FileExistsError(f"Refusing to overwrite classification input: {destination}")
                copies.append((source, destination))
    if copies:
        workspace_dir.mkdir(parents=True, exist_ok=True)
    for source, destination in copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        print(f"Prepared cohort input: {source} -> {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-dir", type=Path, required=True)
    parser.add_argument("--order-file", type=Path, required=True)
    parser.add_argument("--tools", default="")
    parser.add_argument("--gold-standards-dir", type=Path, required=True)
    parser.add_argument("--workspace-dir", type=Path, required=True)
    args = parser.parse_args()
    prepare_inputs(args.tools_dir, args.order_file, args.tools, args.gold_standards_dir, args.workspace_dir)


if __name__ == "__main__":
    main()
