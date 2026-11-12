"""Load per-tool configuration and resolve repository-owned input files."""

import json
from pathlib import Path

from validation_scenarios import validate_name


VALIDATION_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOOLS_DIR = VALIDATION_ROOT / "tools"
DEFAULT_ORDER_FILE = VALIDATION_ROOT / "config" / "tool_execution_order.json"


def read_json(path):
    with Path(path).open(encoding="utf-8-sig") as source:
        return json.load(source)


def load_tool_configs(tools_dir, filename):
    tools_dir = Path(tools_dir)
    if not tools_dir.is_dir():
        raise FileNotFoundError(f"Tool configuration directory not found: {tools_dir}")
    result = {}
    seen = set()
    for directory in sorted(tools_dir.iterdir()):
        if not directory.is_dir():
            continue
        validate_name(directory.name)
        if directory.name.casefold() in seen:
            raise ValueError(f"Duplicate tool name: {directory.name}")
        seen.add(directory.name.casefold())
        path = directory / filename
        definition = read_json(path)
        if not isinstance(definition, dict):
            raise ValueError(f"Expected a JSON object in {path}")
        result[directory.name] = definition
    if not result:
        raise ValueError(f"No tool configurations found in {tools_dir}")
    return result


def resolve_input_paths(spec, config_dir):
    if not isinstance(spec, dict):
        raise ValueError(f"Expected a value specification object in {config_dir}")
    if spec.get("kind") == "workspaceFileJson":
        relative_path = spec.get("relativePath")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError(f"workspaceFileJson requires relativePath in {config_dir}")
        spec["relativePath"] = str((config_dir / relative_path).resolve())
    if "fileSpec" in spec:
        resolve_input_paths(spec["fileSpec"], config_dir)


def load_adaptations(tools_dir):
    definitions = load_tool_configs(tools_dir, "adaptations.json")
    for tool, definition in definitions.items():
        config_dir = Path(tools_dir) / tool
        updates = definition.get("updates", [])
        scenarios = definition.get("scenarios", [])
        if not isinstance(updates, list) or not isinstance(scenarios, list):
            raise ValueError(f"{tool}: updates and scenarios must be arrays")
        all_updates = list(updates)
        for scenario in scenarios:
            if not isinstance(scenario, dict) or not isinstance(scenario.get("updates", []), list):
                raise ValueError(f"{tool}: each scenario must be an object with an updates array")
            all_updates.extend(scenario.get("updates", []))
        for update in all_updates:
            if not isinstance(update, dict):
                raise ValueError(f"{tool}: each update must be an object")
            if "value" in update:
                resolve_input_paths(update["value"], config_dir)
    return definitions


def load_validations(tools_dir):
    return load_tool_configs(tools_dir, "validations.json")
