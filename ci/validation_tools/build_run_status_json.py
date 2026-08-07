#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convert a simple tool_name<TAB>status TSV file (written by the Linux/macOS
headless execution loop) into the run-status.json consumed by
compare_and_summarize.py.

Usage:
    python build_run_status_json.py --input run-status.tsv --output run-status.json --exec-log-dir target/validation-logs
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Convert run-status.tsv to run-status.json")
    parser.add_argument('--input', required=True, help='Path to the run-status.tsv file')
    parser.add_argument('--output', required=True, help='Destination path for run-status.json')
    parser.add_argument('--exec-log-dir', required=True, help='Directory containing per-tool execution logs')

    args = parser.parse_args()

    data = {}
    with open(args.input, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 2:
                continue
            tool_name, status = parts
            data[tool_name] = {
                "run_status": status,
                "execution_log": str(Path(args.exec_log_dir) / f"{tool_name}-exec.log"),
            }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as out:
        json.dump(data, out, indent=2)


if __name__ == '__main__':
    main()
