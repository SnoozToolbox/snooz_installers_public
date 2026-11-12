"""Shared identities and configuration expansion for validation scenarios."""

import json
import re
import sys
from pathlib import Path


def configured_tools(adaptations):
    return {
        name for name, config in adaptations.items()
        if isinstance(config, dict) and (config.get("updates") or "scenarios" in config)
    }


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
        raise ValueError(f"Invalid validation name: {name!r}")
    if "__" in name:
        raise ValueError(f"Validation names cannot contain the reserved separator '__': {name}")


def expand_scenarios(tool_name, definition, workspace_dir):
    validate_name(tool_name)
    common = definition.get("updates", [])
    if not isinstance(common, list):
        raise ValueError(f"{tool_name}.updates must be an array")
    explicit = "scenarios" in definition
    scenarios = definition.get("scenarios", [{"id": "default", "updates": []}])
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError(f"{tool_name}.scenarios must be a non-empty array")
    seen = set()
    runs = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError(f"{tool_name}: each scenario must be an object")
        scenario_id = scenario.get("id")
        validate_name(scenario_id)
        if scenario_id.casefold() in seen:
            raise ValueError(f"{tool_name}: duplicate scenario id {scenario_id!r}")
        seen.add(scenario_id.casefold())
        updates = scenario.get("updates", [])
        if not isinstance(updates, list):
            raise ValueError(f"{tool_name}:{scenario_id}.updates must be an array")
        enabled = scenario.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"{tool_name}:{scenario_id}.enabled must be a boolean")
        if not enabled:
            print(f"Skipping disabled scenario: {tool_name}:{scenario_id}", file=sys.stderr)
            continue
        run_id = f"{tool_name}__{scenario_id}" if explicit else tool_name
        runs.append({
            "tool_name": tool_name,
            "scenario_id": scenario_id,
            "run_id": run_id,
            "json_path": (Path(workspace_dir) / f"{run_id}.json").as_posix(),
            "explicit_scenario": explicit,
            "updates": common + updates,
        })
    return runs


def load_manifest(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if (
        not isinstance(data, dict) or data.get("schema_version") != 1
        or not isinstance(data.get("runs"), list) or not data["runs"]
    ):
        raise ValueError(f"Invalid or empty scenario manifest: {path}")
    seen = set()
    for run in data["runs"]:
        validate_name(run["tool_name"])
        validate_name(run["scenario_id"])
        if not isinstance(run.get("explicit_scenario"), bool):
            raise ValueError(f"Missing explicit_scenario flag: {run}")
        if not run["explicit_scenario"] and run["scenario_id"] != "default":
            raise ValueError(f"Legacy runs must use the default scenario: {run}")
        expected = (
            f"{run['tool_name']}__{run['scenario_id']}"
            if run["explicit_scenario"] else run["tool_name"]
        )
        if run["run_id"] != expected or expected.casefold() in seen:
            raise ValueError(f"Invalid or duplicate manifest run: {run['run_id']}")
        seen.add(expected.casefold())
        scenario_path = Path(run["json_path"])
        if scenario_path.name != f"{expected}.json" or not scenario_path.is_file():
            raise ValueError(f"Scenario JSON missing or incorrectly named: {scenario_path}")
    return data["runs"]
