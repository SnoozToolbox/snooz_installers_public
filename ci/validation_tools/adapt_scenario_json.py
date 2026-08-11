#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adapt extracted CEAMSTools scenario JSON files into runnable validation workspace
scenarios, applying the per-tool node input updates defined in
tool_json_adaptations.json.

This is the Linux/macOS (Python) equivalent of the PowerShell
Convert-ExtractedJson / Resolve-ConfiguredValue logic used in
validation_windows.yml, so that all three platforms apply identical
transformations (private dataset paths, workspace paths, literal values,
embedded JSON file contents, etc.) before running headless scenarios.

Usage:
    python adapt_scenario_json.py \
        --source-dir validation-json \
        --workspace-dir validation-workspaces \
        --adaptations-file ci/validation_tools/tool_json_adaptations.json \
        --private-dataset-dir private-dataset \
        [--tools Tool1,Tool2]
"""

import argparse
import json
import re
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def convert_to_json_path(path_str):
    """Normalize a filesystem path to forward slashes for JSON compatibility."""
    return str(path_str).replace('\\', '/')


def convert_to_python_literal(value):
    """Render a Python value as the Python-literal-syntax string expected by Snooz JSON inputs."""
    if value is None:
        return "None"
    if isinstance(value, str):
        return "'" + value.replace("'", "\\'") + "'"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, dict):
        parts = [f"{convert_to_python_literal(k)}: {convert_to_python_literal(v)}" for k, v in value.items()]
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(convert_to_python_literal(v) for v in value) + "]"
    return str(value)


def resolve_configured_value(spec, workspace_dir, private_dataset_dir):
    """Resolve a value specification (the 'value' object of an update entry) to its concrete value."""
    if not spec or "kind" not in spec:
        raise ValueError("Invalid value specification: missing kind")

    kind = spec["kind"]
    required = spec.get("required", True)

    if kind == "literal":
        return spec["value"]

    if kind == "workspacePath":
        relative_path = spec.get("relativePath")
        if not relative_path:
            raise ValueError("workspacePath specification requires relativePath")
        full_path = (workspace_dir / relative_path).resolve()
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return convert_to_json_path(full_path)

    if kind == "workspaceFileJson":
        relative_path = spec.get("relativePath")
        if not relative_path:
            raise ValueError("workspaceFileJson specification requires relativePath")
        full_path = (workspace_dir / relative_path).resolve()
        if not full_path.exists():
            if required:
                raise FileNotFoundError(f"workspaceFileJson target not found: {full_path}")
            return None
        with open(full_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    if kind == "privateDatasetPath":
        relative_path = spec.get("relativePath")
        if not relative_path:
            raise ValueError("privateDatasetPath specification requires relativePath")
        output = spec.get("output", "path")
        full_path = (private_dataset_dir / relative_path).resolve()
        if not full_path.exists():
            if required:
                raise FileNotFoundError(f"privateDatasetPath target not found: {full_path}")
            return None
        resolved_path = convert_to_json_path(full_path)
        if output == "list":
            return [resolved_path]
        if output == "pythonListSingleQuoted":
            return f"['{resolved_path}']"
        return resolved_path

    if kind == "findPath":
        roots = [str(r) for r in spec.get("roots", [])]
        if not roots:
            raise ValueError("findPath specification requires at least one root")

        item_type = spec.get("itemType", "Directory")
        match_regex = spec.get("matchRegex")
        pick = spec.get("pick", "first")
        output = spec.get("output", "path")

        found_paths = []
        for root in roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            candidates = root_path.rglob("*")
            if item_type == "File":
                candidates = [p for p in candidates if p.is_file()]
            else:
                candidates = [p for p in candidates if p.is_dir()]
            if match_regex:
                pattern = re.compile(match_regex)
                candidates = [p for p in candidates if pattern.search(str(p))]
            found_paths.extend(candidates)

        found_paths = sorted(found_paths, key=lambda p: str(p))
        if not found_paths:
            if required:
                raise FileNotFoundError(f"No path matched for findPath roots={roots} regex='{match_regex}'")
            return None

        if pick == "all":
            selected = [convert_to_json_path(p) for p in found_paths]
        else:
            selected = [convert_to_json_path(found_paths[0])]

        if output == "list":
            return selected
        if output == "pythonDictByPath":
            dictionary_map = spec.get("dictionaryMap")
            if not dictionary_map:
                raise ValueError("findPath output=pythonDictByPath requires dictionaryMap")
            escaped_path = selected[0].replace("'", "\\'")
            pairs = []
            for map_key, map_value in dictionary_map.items():
                escaped_key = str(map_key).replace("'", "\\'")
                escaped_value = str(map_value).replace("'", "\\'")
                pairs.append(f"'{escaped_key}': '{escaped_value}'")
            return "{'" + escaped_path + "': {" + ", ".join(pairs) + "}}"
        if output == "pythonListSingleQuoted":
            return "[" + ",".join(f"'{p}'" for p in selected) + "]"
        return selected[0]

    if kind == "pythonDictFromFileMapping":
        file_spec = spec.get("fileSpec")
        mapping = spec.get("mapping")
        if file_spec is None:
            raise ValueError("pythonDictFromFileMapping specification requires fileSpec")
        if mapping is None:
            raise ValueError("pythonDictFromFileMapping specification requires mapping")

        resolved_file_path = resolve_configured_value(file_spec, workspace_dir, private_dataset_dir)
        if not resolved_file_path:
            if required:
                raise ValueError("pythonDictFromFileMapping could not resolve file path")
            return None

        return convert_to_python_literal({resolved_file_path: mapping})

    raise ValueError(f"Unsupported value specification kind: {kind}")


def format_value_for_log(value):
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def update_node_inputs_by_identifier(json_obj, identifier, input_name, input_value):
    """Find node(s) matching identifier and update the named input's value, preserving array-ness."""
    process_params = json_obj.get("process_params")
    if not process_params or "nodes" not in process_params:
        return False

    updated = False
    for node in process_params["nodes"]:
        if node.get("identifier") != identifier:
            continue
        inputs = node.get("inputs", {})
        if input_name not in inputs:
            continue

        existing_value = inputs[input_name].get("value")
        existing_is_list = isinstance(existing_value, list)
        input_is_list = isinstance(input_value, list)

        new_value = input_value
        if existing_is_list and not input_is_list:
            new_value = [input_value]
        elif not existing_is_list and input_is_list and len(input_value) == 1:
            new_value = input_value[0]

        inputs[input_name]["value"] = new_value
        updated = True

    return updated


def adapt_tool_scenario(source_path, dest_path, tool_name, tool_definition, workspace_dir, private_dataset_dir):
    with open(source_path, 'r', encoding='utf-8') as f:
        scenario = json.load(f)

    metadata = scenario.setdefault("metadata", {})
    metadata["validationSource"] = "installed-package"
    metadata["validationTarget"] = "validation-workspaces"
    metadata["toolName"] = tool_definition.get("targetToolName", tool_name)

    processing_mode = tool_definition.get("processingMode")
    if processing_mode:
        metadata["processingMode"] = processing_mode
    elif "processingMode" in metadata:
        del metadata["processingMode"]

    for update in tool_definition.get("updates", []):
        identifier = update.get("identifier")
        input_name = update.get("inputName")
        required = update.get("required", True)
        value_spec = update.get("value")

        if not identifier:
            raise ValueError(f"Invalid updates entry in {tool_name}: missing identifier")
        if not input_name:
            raise ValueError(f"Invalid updates entry in {tool_name}: missing inputName")
        if value_spec is None:
            raise ValueError(f"Invalid updates entry in {tool_name}: missing value specification")

        resolved_value = resolve_configured_value(value_spec, workspace_dir, private_dataset_dir)
        print(f"{tool_name} update '{identifier}.{input_name}': {format_value_for_log(resolved_value)}")

        did_update = update_node_inputs_by_identifier(scenario, identifier, input_name, resolved_value)
        if not did_update and required:
            raise ValueError(f"Unable to update node '{identifier}' input '{input_name}' in {source_path}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, 'w', encoding='utf-8') as f:
        json.dump(scenario, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Adapt extracted CEAMSTools JSON scenarios for headless validation")
    parser.add_argument('--source-dir', required=True, help='Directory containing extracted *.json scenario files')
    parser.add_argument('--workspace-dir', required=True, help='Destination directory for adapted validation workspace scenarios')
    parser.add_argument('--adaptations-file', required=True, help='Path to tool_json_adaptations.json')
    parser.add_argument('--private-dataset-dir', required=True, help='Path to the private dataset directory')
    parser.add_argument('--tools', default='', help='Comma-separated tool basenames to process (default: all tools with updates in the adaptations file)')

    args = parser.parse_args()

    adaptations_path = Path(args.adaptations_file)
    if not adaptations_path.exists():
        print(f"Tool adaptations config not found: {adaptations_path}", file=sys.stderr)
        return 1

    with open(adaptations_path, 'r', encoding='utf-8') as f:
        adaptations = json.load(f)

    tools_to_process = [t.strip() for t in args.tools.split(',') if t.strip()]
    if not tools_to_process:
        tools_to_process = sorted(
            k for k, v in adaptations.items()
            if isinstance(v, dict) and v.get("updates")
        )

    if not tools_to_process:
        print("No tool definitions with updates found in tool_json_adaptations.json", file=sys.stderr)
        return 1

    print(f"Tools configured for this run: {', '.join(tools_to_process)}\n")

    source_dir = Path(args.source_dir)
    workspace_dir = Path(args.workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    private_dataset_dir = Path(args.private_dataset_dir)

    adapted_count = 0
    for tool_name in tools_to_process:
        source_path = source_dir / f"{tool_name}.json"
        if not source_path.exists():
            print(f"  x Warning: {tool_name}.json not found in {source_dir}")
            continue

        tool_definition = adaptations.get(tool_name, {})
        dest_path = workspace_dir / f"{tool_name}.json"

        try:
            adapt_tool_scenario(source_path, dest_path, tool_name, tool_definition, workspace_dir, private_dataset_dir)
            print(f"  [OK] Adapted: {tool_name}.json")
            adapted_count += 1
        except Exception as e:
            print(f"[ERROR] Failed to adapt {tool_name}.json: {e}", file=sys.stderr)
            return 1

    print(f"\nValidation workspaces prepared with {adapted_count} tool(s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
