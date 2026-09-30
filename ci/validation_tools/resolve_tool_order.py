#!/usr/bin/env python3
"""Resolve validation tools using one explicit cross-platform execution order."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_configured_tools(adaptations_path: Path) -> set[str]:
    adaptations = json.loads(adaptations_path.read_text(encoding="utf-8"))
    return {
        name
        for name, config in adaptations.items()
        if isinstance(config, dict) and config.get("updates")
    }


def resolve_tools(adaptations_path: Path, order_path: Path, requested: str = "") -> list[str]:
    configured = load_configured_tools(adaptations_path)
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
    parser.add_argument("--adaptations-file", required=True)
    parser.add_argument("--order-file", required=True)
    parser.add_argument("--tools", default="", help="Optional comma-separated subset")
    parser.add_argument("--format", choices=("lines", "shell"), default="lines")
    args = parser.parse_args()

    tools = resolve_tools(Path(args.adaptations_file), Path(args.order_file), args.tools)
    if args.format == "shell":
        if any(any(character.isspace() for character in name) for name in tools):
            raise ValueError("Shell output does not support whitespace in tool names")
        print(" ".join(tools))
    else:
        print("\n".join(tools))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())