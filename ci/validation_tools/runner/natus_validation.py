"""Shared NATUS exclusions for validation inputs and comparisons."""

import ast
import os


NATUS_SUBJECT = "COV-015~ Covid_5250d3a3-5e68-4a00-ad3c-628b6639c9db"
def include_natus():
    value = os.environ.get("INCLUDE_NATUS", "true").lower()
    if value not in ("true", "false"):
        raise ValueError("INCLUDE_NATUS must be true or false")
    return value == "true"


def is_natus(value):
    return isinstance(value, str) and NATUS_SUBJECT in value


def filter_input(value):
    """Filter structured values, including containers encoded as Python literals."""
    if isinstance(value, dict):
        return {
            key: filter_input(item) for key, item in value.items()
            if not is_natus(key)
        }
    if isinstance(value, (list, tuple)):
        filtered = [filter_input(item) for item in value if not (
            is_natus(item) and not item.lstrip().startswith(("{", "[", "("))
        )]
        return tuple(filtered) if isinstance(value, tuple) else filtered
    if is_natus(value):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError) as error:
            raise ValueError("Cannot exclude NATUS from a scalar input; configure a non-NATUS input") from error
        if not isinstance(parsed, (dict, list, tuple)):
            raise ValueError("Cannot exclude NATUS from a scalar input")
        return repr(filter_input(parsed))
    return value


def filter_scenario_inputs(scenario, tool_name):
    for node in scenario.get("process_params", {}).get("nodes", []):
        for name, definition in node.get("inputs", {}).items():
            if "value" not in definition:
                continue
            original = definition["value"]
            filtered = filter_input(original)
            if filtered != original:
                print(f"{tool_name}: excluded NATUS from {node.get('identifier')}.{name}")
                if filtered in ({}, [], (), "{}", "[]", "()"):
                    raise ValueError(f"{tool_name}.{name}: NATUS exclusion left an empty input")
                definition["value"] = filtered
    for node in scenario.get("process_params", {}).get("nodes", []):
        if NATUS_SUBJECT in repr(node.get("inputs", {})):
            raise ValueError(f"{tool_name}: NATUS reference remains in scenario inputs")


def filter_comparisons(comparisons, tool_name):
    retained = []
    for comparison in comparisons:
        if comparison.get("requiresNatus") is True or any(is_natus(comparison.get(key)) for key in (
            "fileName", "generatedFileName", "goldFileName",
        )):
            print(f"{tool_name}: excluded NATUS comparison {comparison.get('fileName')}")
        else:
            retained.append(comparison)
    return retained


def filter_report_rows(rows, source):
    if not rows:
        return rows
    if any(is_natus(cell) for cell in rows[0]):
        raise ValueError(f"{source}: NATUS appears in the header; row exclusion is insufficient")
    retained = [rows[0]] + [
        row for row in rows[1:] if not any(is_natus(cell) for cell in row)
    ]
    removed = len(rows) - len(retained)
    if removed:
        print(f"{source}: excluded {removed} NATUS row(s)")
    if not any(any(cell.strip() for cell in row) for row in retained[1:]):
        raise ValueError(f"{source}: no data remains for comparison")
    return retained
