#!/usr/bin/env python3
"""Validate repository configuration without a dataset, installer or gold standard."""

import argparse
import re
import sys
from pathlib import Path

from compare_outputs import validate_comparison_options
from configuration import (
    DEFAULT_ORDER_FILE, DEFAULT_TOOLS_DIR, load_adaptations, load_validations, read_json,
)
from resolve_tool_order import resolve_tools
from validation_scenarios import expand_scenarios


def require_string(value, context):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")


def validate_value(spec):
    if not isinstance(spec, dict):
        raise ValueError("Value specification must be an object")
    kind = spec.get("kind")
    for flag in ("required", "asDirectory"):
        if flag in spec and not isinstance(spec[flag], bool):
            raise ValueError(f"{flag} must be a boolean")
    if kind == "literal":
        if "value" not in spec:
            raise ValueError("literal requires value")
    elif kind in ("workspaceFileJson", "workspacePath", "privateDatasetPath"):
        require_string(spec.get("relativePath"), f"{kind}.relativePath")
        if kind == "workspaceFileJson":
            read_json(spec["relativePath"])
    elif kind == "pythonDictFromFileMapping":
        validate_value(spec.get("fileSpec"))
        if not isinstance(spec.get("mapping"), dict):
            raise ValueError("pythonDictFromFileMapping requires a mapping object")
    elif kind == "findPath":
        roots = spec.get("roots")
        if not isinstance(roots, list) or not roots:
            raise ValueError("findPath requires a non-empty roots array")
        for root in roots:
            require_string(root, "findPath root")
        if spec.get("itemType", "Directory") not in ("File", "Directory"):
            raise ValueError("findPath.itemType must be File or Directory")
        if spec.get("pick", "first") not in ("first", "all"):
            raise ValueError("findPath.pick must be first or all")
        if "matchRegex" in spec:
            re.compile(spec["matchRegex"])
    else:
        raise ValueError(f"Unknown value kind: {kind!r}")
    if kind == "privateDatasetPath" and spec.get("output", "path") not in (
        "path", "list", "pythonListSingleQuoted",
    ):
        raise ValueError("Invalid privateDatasetPath.output")
    if kind == "findPath" and spec.get("output", "path") not in (
        "path", "list", "pythonListSingleQuoted", "pythonDictByPath",
    ):
        raise ValueError("Invalid findPath.output")


def validate_updates(updates):
    for update in updates:
        if not isinstance(update, dict):
            raise ValueError("Each update must be an object")
        require_string(update.get("identifier"), "identifier")
        if "required" in update and not isinstance(update["required"], bool):
            raise ValueError("Update required must be a boolean")
        if "activationState" in update:
            if update["activationState"] not in ("activated", "deactivated", "bypass"):
                raise ValueError("Invalid activationState")
            if "inputName" in update or "value" in update:
                raise ValueError("Activation updates cannot also change an input")
        else:
            require_string(update.get("inputName"), "inputName")
            validate_value(update.get("value"))


def validate_comparisons(definition, context):
    if not isinstance(definition, dict):
        raise ValueError(f"{context} must be an object")
    comparisons = definition.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise ValueError(f"{context} requires a non-empty comparisons array")
    seen = set()
    for comparison in comparisons:
        if not isinstance(comparison, dict):
            raise ValueError(f"{context}: each comparison must be an object")
        generated = comparison.get("generatedFileName") or comparison.get("fileName")
        gold = comparison.get("goldFileName") or comparison.get("fileName")
        require_string(generated, f"{context} generated filename")
        if comparison.get("fileType") != "exists":
            require_string(gold, f"{context} gold filename")
        key = generated.casefold()
        if key in seen:
            raise ValueError(f"{context}: duplicate comparison for {generated}")
        seen.add(key)
        if "generatedSearchRoots" in comparison:
            roots = comparison["generatedSearchRoots"]
            if not isinstance(roots, list) or not roots:
                raise ValueError(f"{context}: generatedSearchRoots must be a non-empty array")
            for root in roots:
                require_string(root, f"{context} search root")
        validate_comparison_options(comparison)


def validate_configuration(tools_dir, order_file):
    adaptations = load_adaptations(tools_dir)
    validations = load_validations(tools_dir)
    order = resolve_tools(tools_dir, order_file)
    run_count = 0
    for tool in order:
        definition = adaptations[tool]
        try:
            if "targetToolName" in definition:
                require_string(definition["targetToolName"], "targetToolName")
            if "processingMode" in definition:
                require_string(definition["processingMode"], "processingMode")
            runs = expand_scenarios(tool, definition, ".")
            run_count += len(runs)
            validate_updates(definition.get("updates", []))
            for scenario in definition.get("scenarios", []):
                validate_updates(scenario.get("updates", []))
            comparison = validations[tool]
            if "scenarios" in definition:
                expected = {scenario["id"] for scenario in definition["scenarios"]}
                actual = comparison.get("scenarios")
                if not isinstance(actual, dict) or set(actual) != expected:
                    raise ValueError("Adaptation and validation scenario identifiers must match exactly")
                if "comparisons" in comparison:
                    raise ValueError("Explicit scenarios cannot also define tool-level comparisons")
                for scenario_id, rules in actual.items():
                    validate_comparisons(rules, f"{tool}:{scenario_id}")
            else:
                if "scenarios" in comparison:
                    raise ValueError("Validation scenarios require explicit adaptation scenarios")
                validate_comparisons(comparison, tool)
        except (ValueError, OSError) as error:
            raise ValueError(f"{tool}: {error}") from error
    return len(order), run_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools-dir", type=Path, default=DEFAULT_TOOLS_DIR)
    parser.add_argument("--order-file", type=Path, default=DEFAULT_ORDER_FILE)
    args = parser.parse_args()
    try:
        tools, runs = validate_configuration(args.tools_dir, args.order_file)
    except (ValueError, OSError) as error:
        print(f"Configuration validation failed: {error}", file=sys.stderr)
        return 1
    print(f"Configuration valid: {tools} tools, {runs} enabled runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
