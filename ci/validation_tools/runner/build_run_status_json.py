#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert a simple run_id<TAB>status TSV file (written by the platform
headless execution loops) into the run-status.json consumed by
compare_and_summarize.py.

Usage:
    python build_run_status_json.py --input run-status.tsv --output run-status.json --exec-log-dir target/validation-logs
"""

import argparse
import json
from pathlib import Path

from validation_scenarios import load_manifest


def main():
    parser = argparse.ArgumentParser(description="Convert per-scenario run-status.tsv to run-status.json")
    parser.add_argument('--input', required=True, help='Path to the run-status.tsv file')
    parser.add_argument('--output', required=True, help='Destination path for run-status.json')
    parser.add_argument('--exec-log-dir', required=True, help='Directory containing per-tool execution logs')
    parser.add_argument('--manifest', help='Generated scenario manifest (optional for legacy callers)')

    args = parser.parse_args()
    runs = {run["run_id"]: run for run in load_manifest(args.manifest)} if args.manifest else None

    data = {}
    with open(args.input, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 2:
                raise ValueError(f"Invalid run status row: {line!r}")
            tool_name, status = parts
            if status not in ("pass", "fail") or tool_name in data:
                raise ValueError(f"Invalid or duplicate run status: {line!r}")
            data[tool_name] = {
                "run_status": status,
                "execution_log": str(Path(args.exec_log_dir) / f"{tool_name}-exec.log"),
            }
            if runs is not None:
                if tool_name not in runs:
                    raise ValueError(f"Run not found in scenario manifest: {tool_name}")
                data[tool_name].update(runs[tool_name])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as out:
        json.dump(data, out, indent=2)


if __name__ == '__main__':
    main()
