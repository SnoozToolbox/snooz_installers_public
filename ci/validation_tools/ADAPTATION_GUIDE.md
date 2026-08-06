# JSON Adaptation Rules Guide

This document explains how to configure tool input adaptations for CI validation workflows using [tool_json_adaptations.json](tool_json_adaptations.json).

## Overview

The `tool_json_adaptations.json` file contains per-tool rules that modify extracted process JSON files for CI headless execution. Each tool can define updates to specific node inputs using various value resolution strategies.

## File Structure

```json
{
  "ToolName": {
    "targetToolName": "DisplayName",
    "processingMode": "adapted",
    "updates": [
      {
        "identifier": "node-uuid",
        "inputName": "input_field_name",
        "required": true,
        "value": { ... value specification ... }
      }
    ]
  }
}
```

## Top-Level Keys

- **`targetToolName`** (string): Logical tool name written to JSON metadata.toolName
- **`processingMode`** (string, optional): Processing mode written to metadata.processingMode
- **`updates`** (array): List of input updates to apply in process_params.nodes

## Updates Entry Specification

Each entry in the `updates` array modifies one node input:

- **`identifier`** (string): UUID of the target node (required)
- **`inputName`** (string): Input name to modify on the target node (required)
- **`required`** (boolean, default: true): 
  - `true`: Fail if identifier/input not found or value cannot be resolved
  - `false`: Skip silently if identifier/input is absent or value cannot be resolved
- **`value`** (object): Value specification (see below)

## Value Specifications

Each value object specifies how to compute the final input value using a `kind` field.

### kind=`literal`

Fixed string value; no path or file resolution.

```json
{
  "kind": "literal",
  "value": "fixed-string-or-python-code"
}
```

**Parameters:**
- `value` (string): The literal value to inject

**Example:** Pass a constant or Python literal string:
```json
{
  "kind": "literal",
  "value": "0"
}
```

---

### kind=`workspacePath`

Create a path relative to the validation workspace; ensures parent directories exist.

```json
{
  "kind": "workspacePath",
  "relativePath": "output_file.tsv"
}
```

**Parameters:**
- `relativePath` (string): Path relative to validation-workspaces directory

**Example:** Output file path for a report:
```json
{
  "kind": "workspacePath",
  "relativePath": "DetectREMsYASA-report.tsv"
}
```

**Note:** Parent directories are automatically created; resolved path uses forward slashes for JSON compatibility.

---

### kind=`workspaceFileJson`

Read JSON file from workspace and inject its full content as the input value.

```json
{
  "kind": "workspaceFileJson",
  "relativePath": "../ci/validation_tools/DetectArtifacts-files.json"
}
```

**Parameters:**
- `relativePath` (string): Path to JSON file (relative to validation-workspaces)

**Use Case:** When input is large/complex and should be maintained in a separate file instead of embedded.

**Developer Workflow:**
1. Generate or open the adapted process JSON for your tool
2. Copy the exact value of the input field (e.g., "files", "alias")
3. Create a dedicated JSON file containing only that value
4. Reference it with `kind=workspaceFileJson` + `relativePath`
5. For private-dataset files in CI, use paths under `$GITHUB_WORKSPACE/private-dataset/inputs/`

---

### kind=`privateDatasetPath`

Resolve path within the private dataset directory.

```json
{
  "kind": "privateDatasetPath",
  "relativePath": "inputs/learn-nsrr01_annotations.txt",
  "output": "path"
}
```

**Parameters:**
- `relativePath` (string): Path relative to private-dataset directory (required)
- `output` (string, default: "path"):
  - `"path"`: Single path string
  - `"list"`: JSON array of paths
  - `"pythonListSingleQuoted"`: Python list literal with single-quoted strings

**Example:** Multiple input files:
```json
{
  "kind": "privateDatasetPath",
  "relativePath": "inputs/learn-nsrr01_annotations.txt",
  "output": "list"
}
```

---

### kind=`findPath`

Recursively search directories for files matching a regex pattern.

```json
{
  "kind": "findPath",
  "roots": ["private-dataset/inputs"],
  "itemType": "File",
  "matchRegex": "(learn-nsrr01-profusion\\.xml|learn-nsrr02-profusion\\.xml)$",
  "pick": "first",
  "output": "path"
}
```

**Parameters:**
- `roots` (array): List of root directories to search (required)
- `itemType` (string, default: "Directory"): "File" or "Directory"
- `matchRegex` (string): Regex matched against full file paths
- `pick` (string, default: "first"): "first" or "all"
- `output` (string, default: "path"):
  - `"path"`: Single path string
  - `"list"`: JSON array of paths
  - `"pythonListSingleQuoted"`: Python list literal with single-quoted strings

**Example:** Find all XML files matching pattern:
```json
{
  "kind": "findPath",
  "roots": ["private-dataset/inputs"],
  "itemType": "File",
  "matchRegex": "profusion\\.xml$",
  "pick": "all",
  "output": "pythonListSingleQuoted"
}
```

---

### kind=`pythonDictFromFileMapping`

Create a Python dictionary mapping file path to metadata.

```json
{
  "kind": "pythonDictFromFileMapping",
  "fileSpec": {
    "kind": "privateDatasetPath",
    "relativePath": "inputs/learn-nsrr01_annotations.txt"
  },
  "mapping": {
    "0": "stage",
    "1": "stage"
  }
}
```

**Parameters:**
- `fileSpec` (object): Nested value spec that resolves a single file path (required)
- `mapping` (object): Key/value map used as dictionary content for that file (required)

**Output:** Python dictionary literal: `{'resolved_file_path': {'key1': 'val1', ...}}`

**Use Case:** When you need to associate file paths with metadata/flags.

---

## Cross-Platform Path Handling

### The `$GITHUB_WORKSPACE` Placeholder

In GitHub Actions, `${{ github.workspace }}` is a **context variable** that contains the **complete repository checkout path** for the current runner:

- **Windows:** `D:/a/snooz_installers_public/snooz_installers_public` (the full repo path)
- **macOS:** `/Users/runner/work/snooz_installers_public/snooz_installers_public` (the full repo path)
- **Linux:** `/home/runner/work/snooz_installers_public/snooz_installers_public` (the full repo path)

Configuration files use `$GITHUB_WORKSPACE` as a **literal placeholder token**. At workflow runtime, `adapt_json_paths.py` performs a simple string substitution:

```python
adapted_content = content.replace('$GITHUB_WORKSPACE', workspace_root_normalized)
```

**Why write the full path?** Because `$GITHUB_WORKSPACE` already IS the complete repository path. When you write:
- `$GITHUB_WORKSPACE/private-dataset/inputs/file.edf`

It literally becomes:
- Windows: `D:/a/snooz_installers_public/snooz_installers_public/private-dataset/inputs/file.edf`
- macOS: `/Users/runner/work/snooz_installers_public/snooz_installers_public/private-dataset/inputs/file.edf`
- Linux: `/home/runner/work/snooz_installers_public/snooz_installers_public/private-dataset/inputs/file.edf`

**Important:** Do NOT duplicate repository directories in your relative paths. The workspace is already the repository root.

### Example

In `tool_json_adaptations.json`, dictionary values with `$GITHUB_WORKSPACE`:
```json
"value": "{'$GITHUB_WORKSPACE/private-dataset/inputs/learn-nsrr01.edf': 'None', ...}"
```

After `adapt_json_paths.py` runs on Windows, `$GITHUB_WORKSPACE` is replaced with the absolute path:
```json
"value": "{'D:/a/snooz_installers_public/snooz_installers_public/private-dataset/inputs/learn-nsrr01.edf': 'None', ...}"
```

On macOS or Linux, the same substitution occurs with the respective runner paths.

**Note:** The placeholder replaces cleanly because it's already the complete repository path—no duplication needed.

---

## Adding a New Tool

1. **Identify the tool's JSON process file** (e.g., `DetectArtifacts.json`)
2. **Extract or generate** a sample adapted JSON in CI
3. **For each input** you want to override:
   - Find the target node UUID (`identifier`)
   - Determine the input field name (`inputName`)
   - Choose the value resolution strategy (`kind`)
   - Add an entry to `updates`
4. **Test locally** or in a branch before merging
5. **Document** in git commit message which inputs were modified and why

### Example: Adding DetectArtifacts

```json
{
  "DetectArtifacts": {
    "targetToolName": "DetectArtifacts",
    "processingMode": "adapted",
    "updates": [
      {
        "identifier": "41a6b6f1-08b3-417c-bafb-30dc2274c24b",
        "inputName": "dictionary",
        "required": true,
        "value": {
          "kind": "literal",
          "value": "{'$GITHUB_WORKSPACE/private-dataset/inputs/learn-nsrr01.edf': 'None', ...}"
        }
      },
      {
        "identifier": "64feff16-15d2-4acf-b2e5-195412e476ba",
        "inputName": "files",
        "required": true,
        "value": {
          "kind": "workspaceFileJson",
          "relativePath": "../ci/validation_tools/DetectArtifacts-files.json"
        }
      }
    ]
  }
}
```

---

## Testing Adaptations

1. **Validate JSON syntax:**
   ```bash
   jq . tool_json_adaptations.json
   ```

2. **Run workflows locally with limited tools:**
   ```bash
   # Test only DetectArtifacts
   gh workflow run validation_orchestrator.yml -f tools_to_process="DetectArtifacts"
   ```

3. **Check adapted JSON files** in `validation-workspaces/` directory after workflow

4. **Verify path substitution** in adapted JSONs (should contain absolute paths, not `$GITHUB_WORKSPACE`)

---

## Common Patterns

### Input with Multiple File Paths
Use `findPath` with `output: "pythonListSingleQuoted"`:
```json
{
  "kind": "findPath",
  "roots": ["private-dataset/inputs"],
  "itemType": "File",
  "matchRegex": "\\.edf$",
  "pick": "all",
  "output": "pythonListSingleQuoted"
}
```

### Large Configuration Files
Use `workspaceFileJson` to keep process JSON readable:
```json
{
  "kind": "workspaceFileJson",
  "relativePath": "../ci/validation_tools/ToolName-config.json"
}
```

### Optional Inputs
Set `required: false` to skip silently if value cannot be resolved:
```json
{
  "required": false,
  "value": { "kind": "findPath", ... }
}
```

---

## See Also

- [tool_json_adaptations.json](tool_json_adaptations.json) — Current configuration
- [adapt_json_paths.py](adapt_json_paths.py) — Cross-platform path substitution
- [.github/workflows/validation_windows.yml](.../../.github/workflows/validation_windows.yml) — Workflow that applies adaptations
