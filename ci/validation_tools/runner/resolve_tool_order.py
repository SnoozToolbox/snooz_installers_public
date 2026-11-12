#!/usr/bin/env python3
"""Resolve validation tools using one explicit cross-platform execution order."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from configuration import load_adaptations
from validation_scenarios import configured_tools, expand_scenarios, load_manifest


def load_configured_tools(tools_dir: Path) -> set[str]:
    return configured_tools(load_adaptations(tools_dir))


def resolve_tools(tools_dir: Path, order_path: Path, requested: str = "") -> list[str]:
    configured = load_configured_tools(tools_dir)
    order = json.loads(order_path.read_text(encoding="utf-8"))
    if not isinstance(order, list) or not all(isinstance(name, str) and name for name in order):
        raise ValueError("Tool execution order must be a JSON array of non-empty tool names")
    if len(order) != len(set(order)):
        raise ValueError("Tool execution order contains duplicate names")

    ordered = set(order)
    missing = sorted(configured - ordered)
    unknown = sorted(ordered - configured)
    if missing:
        raise ValueError(f"Configured tools missing from execution order: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"Execution order contains tools without adaptations: {', '.join(unknown)}")

    requested_tools = [name.strip() for name in requested.split(",") if name.strip()]
    if not requested_tools:
        return order
    if len(requested_tools) != len(set(requested_tools)):
        raise ValueError("Requested tool list contains duplicate names")

    requested_set = set(requested_tools)
    invalid_requested = sorted(requested_set - configured)
    if invalid_requested:
        raise ValueError(f"Requested tools are not configured: {', '.join(invalid_requested)}")
    return [name for name in order if name in requested_set]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-dir", required=True)
    parser.add_argument("--order-file", required=True)
    parser.add_argument("--tools", default="", help="Optional comma-separated subset")
    parser.add_argument("--manifest", help="Resolve run ids from the generated scenario manifest")
    parser.add_argument("--format", choices=("lines", "shell", "tsv", "csv"), default="lines")
    args = parser.parse_args()

    tools = resolve_tools(Path(args.tools_dir), Path(args.order_file), args.tools)
    if args.manifest:
        runs = load_manifest(args.manifest)
        adaptations = load_adaptations(Path(args.tools_dir))
        expected = [
            run["run_id"] for tool in tools
            for run in expand_scenarios(tool, adaptations[tool], ".")
        ]
        tools = [run["run_id"] for run in runs]
        if tools != expected:
            raise ValueError("Scenario manifest does not match configured scenarios")
    if args.format == "tsv":
        if not args.manifest:
            raise ValueError("TSV run output requires --manifest")
        for run in runs:
            print(f"{run['run_id']}\t{run['json_path']}")
    elif args.format == "csv":
        print(",".join(tools))
    elif args.format == "shell":
        if any(any(character.isspace() for character in name) for name in tools):
            raise ValueError("Shell output does not support whitespace in tool names")
        print(" ".join(tools))
    else:
        print("\n".join(tools))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())