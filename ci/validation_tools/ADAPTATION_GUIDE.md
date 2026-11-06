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

## Multiple scenarios per tool

Tools without `scenarios` keep their existing behavior: one `<ToolName>.json`,
the existing output paths, validation rules and gold-standard directory. They
appear with `scenario_id=default` in the summary.

To opt in, add a non-empty `scenarios` array. The following example is illustrative;
replace the node identifiers and input names with those from the installed tool:

```json
{
  "PowerSpectralAnalysis": {
    "targetToolName": "PowerSpectralAnalysis",
    "processingMode": "adapted",
    "updates": [],
    "scenarios": [
      {
        "id": "pwelch",
        "updates": [
          {
            "identifier": "analysis-node-uuid",
            "inputName": "method",
            "value": { "kind": "literal", "value": "pwelch" }
          },
          {
            "identifier": "report-node-uuid",
            "inputName": "filename",
            "value": {
              "kind": "workspacePath",
              "relativePath": "PowerSpectralAnalysis/pwelch/report.tsv"
            }
          }
        ]
      },
      {
        "id": "irasa",
        "updates": [
          {
            "identifier": "analysis-node-uuid",
            "inputName": "method",
            "value": { "kind": "literal", "value": "irasa" }
          },
          {
            "identifier": "report-node-uuid",
            "inputName": "filename",
            "value": {
              "kind": "workspacePath",
              "relativePath": "PowerSpectralAnalysis/irasa/report.tsv"
            }
          }
        ]
      }
    ]
  }
}
```

- Common `updates` run first, followed by the scenario's `updates`. A scenario
  can override a common input value or activation state. All existing value
  specifications and `required` semantics still apply.
- Each JSON starts from the original installed JSON, never from another adapted
  scenario. Explicitly configure all modules needed for the selected analysis.
- Tool and scenario identifiers use ASCII letters, digits, `_` and `-`, starting
  with a letter or digit. The separator `__` is reserved. Scenario identifiers
  must be unique within their tool, including case-insensitive matches.
- Outputs are named `<ToolName>__<scenario-id>.json`, even for one explicit
  scenario. Metadata includes `scenarioId` and `runId`.
- Tool order comes from [tool_execution_order.json](tool_execution_order.json);
  scenario order is the array order. `tools_to_process` still selects tools,
  and selecting a tool runs all its scenarios.
- **Dataset changes are cumulative**, both between tools and between scenarios.
  There is no automatic reset or isolated dataset copy. Each scenario is
  captured and compared immediately, before the next one runs.
- Prefer distinct output paths per scenario. If a later tool consumes a report,
  keep its configured input pointing to the intended producer's output.

### Scenario-specific validation rules

For an explicit scenario, define a matching entry in `scenarios` in
[tool_validations.json](tool_validations.json). Each entry requires a non-empty
`comparisons` array; it does not implicitly inherit the legacy tool comparisons.

```json
{
  "PowerSpectralAnalysis": {
    "scenarios": {
      "pwelch": {
        "comparisons": [{
          "fileName": "report.tsv",
          "fileType": "bag-comparison",
          "precision": 4,
          "generatedSearchRoots": ["validation-workspaces/PowerSpectralAnalysis/pwelch"]
        }]
      },
      "irasa": {
        "comparisons": [{
          "fileName": "report.tsv",
          "fileType": "bag-comparison",
          "precision": 4,
          "generatedSearchRoots": ["validation-workspaces/PowerSpectralAnalysis/irasa"]
        }]
      }
    }
  }
}
```

Keep search roots specific: multiple matching generated files or gold standards
are errors for explicit scenarios, rather than selecting the first match.
The existing `exists` checks, numeric precision and bootstrap behavior remain
available. A skipped gold-standard comparison is not a successful comparison.

#### Numeric table tolerances

Use `fileType: "table-tolerance"` for header-based TSV reports that need numeric
tolerances instead of decimal rounding. Do not combine this mode with `precision`.
For example:

```json
{
  "fileName": "EEG_spectral_power_cohort_report_FOOOF_periodic.tsv",
  "fileType": "table-tolerance",
  "keyColumns": ["filename", "channel_label", "freq_low_Hz", "freq_high_Hz"],
  "numericTolerance": {
    "columnPattern": "*_act",
    "relative": 0.001,
    "absolute": 1e-8
  },
  "generatedSearchRoots": ["validation-workspaces"]
}
```

Rows are matched by the exact key values, independently of row order. Missing,
extra, empty or duplicate keys fail, as do mismatched headers or malformed rows.
The case-sensitive glob `columnPattern` must match at least one non-key column
and no key columns. Matched numeric cells pass when
`abs(generated - reference) <= absolute + relative * abs(reference)`.
Both tolerances must be finite and non-negative. `relative: 0.001` means 0.1%.
All other cells are compared exactly, without rounding or time normalization.
Empty strings, `nan` and `NaN` are recognized missing values in tolerant columns
and must match exactly; they are never equivalent to zero. Other non-numeric or
infinite values fail, even if identical in both files.

UTF-8 BOMs and empty physical lines are accepted. Extra empty header fields and
tab-only malformed rows are not silently discarded. Logs report the configured
tolerances, missing/extra keys and differing cells, with numeric errors and
allowed thresholds.

#### FOOOF fitting quality

The FOOOF periodic and aperiodic reports use `fileType: "fooof-fit-quality"`.
This validates full-model fitting quality degradation, **not equivalence of component
energies**. Their `_info.tsv` reports keep their existing comparisons.

Each comparison entry may include an optional `description` string to explain
its rules in the configuration. This field is informational only: it is not
passed to the comparator or displayed in workflow logs. Place it beside
`fileType`, not inside the strictly validated `fitQuality` object.

```json
{
  "fileName": "EEG_spectral_power_cohort_report_FOOOF_periodic.tsv",
  "description": "Exact keyed comparison except *_act (informational numeric differences) and *_fit_err/*_fit_r2 (one-sided degradation limits).",
  "fileType": "fooof-fit-quality",
  "keyColumns": ["filename", "channel_label", "freq_low_Hz", "freq_high_Hz"],
  "fitQuality": {
    "fitKeyColumns": ["filename", "channel_label"],
    "maxErrorIncrease": 0.005,
    "maxR2Decrease": 0.015
  },
  "generatedSearchRoots": ["validation-workspaces"]
}
```

These starting tolerances accommodate the examined reference/generated FOOOF
reports; confirm them against accepted runs on all supported platforms.
Error increases are absolute differences in log10 power space; R2 decreases
are absolute score differences, not relative percentages. Every available
score must satisfy its one-sided degradation bound:

- `err_generated - err_reference <= maxErrorIncrease`
- `r2_reference - r2_generated <= maxR2Decrease`

| Configuration field | Applies to | Meaning |
| --- | --- | --- |
| `keyColumns` | Row matching | Exact column names forming a unique row key. |
| `fitQuality.fitKeyColumns` | Fit grouping | Subset of `keyColumns` identifying one fit across frequency bands. |
| `fitQuality.maxErrorIncrease` | Columns ending in `_fit_err` | Maximum allowed `generated - reference`; finite and >= 0. |
| `fitQuality.maxR2Decrease` | Columns ending in `_fit_r2` | Maximum allowed `reference - generated`; finite and in [0, 1]. |

These configuration names are defined by `validate_fit_options` in
[`compare_outputs.py`](compare_outputs.py), not by the exported TSV. Column
suffix matching is case-sensitive and checks the end of the name, not whether
the label appears anywhere within it. In this mode, `*_act` has no numeric
tolerance: finite numeric differences are informational only.

Improvements do not fail validation. Absolute fitting quality remains visible
in the logged score ranges but does not determine pass/fail: a poor fit already
present in the approved reference is not an installer regression. The former
`maxError` and `minR2` options are no longer supported and must be removed from
comparison configurations. Numeric domain and integrity checks still apply.

All paired `*_fit_err` / `*_fit_r2` columns are discovered from the header,
including total, sleep-stage, clock-hour, cycle and stage-hour fits.
`total_fit_err` and `total_fit_r2` are required. The scores describe the full
model, even when exported in a component report. They must be consistent across
bands within each `fitKeyColumns` group and are counted once per group/metric,
not once per band. `fitKeyColumns` must be a non-empty proper subset of the
unique row keys. Errors must be finite and non-negative; R2 must be in [0, 1].

Missing scores (`""`, `nan`, `NaN`) are accepted only when missing in both files
and explicitly reported as unevaluated. A missing R2 with an available error is
allowed (undefined correlation); an R2 without a fit error fails. Both reports
must contain rows. Old references lacking the new score columns fail and must
be regenerated before enabling this comparison against a gold standard.

Headers, row keys and all other cells remain exact. Row order is irrelevant.
This is a keyed comparison, not `bag-comparison`: it does not apply decimal
rounding or time normalization to the other cells.
`*_act` energy values are checked for numeric validity and matching availability,
but their finite numeric differences do not fail validation. Logs include the
number of changed energy cells and their maximum absolute difference, changed
scores (limited by `--max-diff-lines`), generated score ranges, mean and maximum
score degradation, the worst fit, unevaluated scores and failures. The generated
and reference TSVs remain collected by the existing workflow for detailed review.
Do not combine this mode with `precision` or `numericTolerance`.

Publish one gold-standard zip per tool, with scenario folders at the archive
root, for example `pwelch/report.tsv` and `irasa/report.tsv`. After extraction,
references live under `gold-standards/extracted/<ToolName>/<scenario-id>`.
Legacy tools continue to use `gold-standards/extracted/<ToolName>`.
Collected files use the corresponding `validation-outputs/<ToolName>/<scenario-id>`
layout, preventing scenarios with identical report names from overwriting one
another's artifacts.

### Manifest and results

[adapt_scenario_json.py](adapt_scenario_json.py) writes
`target/validation-logs/scenario-manifest.json` by default (`--manifest` overrides
it). It lists `tool_name`, `scenario_id`, `run_id`, `json_path` and
`explicit_scenario` for every expected execution, in execution order.
The manifest is kept outside the workspace JSON directory so path adaptation
does not rewrite it.

All three platform workflows consume this manifest through
[resolve_tool_order.py](resolve_tool_order.py) with `--manifest` and `--format tsv`.
Missing JSONs, unknown tools and inconsistent manifests fail explicitly.
Logs, status files and capture identifiers use `run_id`. Each run is compared
immediately; execution or comparison failures fail the job while allowing later
runs to execute. The summary adds `scenario_id`, preserves `tool_name`, and records
the actual adapted filename in `json_name`. Multiplatform consolidation keeps
each tool/scenario pair separate and still accepts older summary files.

No existing tool is migrated automatically. To test the mechanism locally:

```powershell
python -m unittest discover -s ci\validation_tools\tests -v
```

## Updates Entry Specification

Each entry in the `updates` array modifies one node input:

- **`identifier`** (string): UUID of the target node (required)
- **`inputName`** (string): Input name to modify on the target node (required)
- **`required`** (boolean, default: true): 
  - `true`: Fail if identifier/input not found or value cannot be resolved
  - `false`: Skip silently if identifier/input is absent or value cannot be resolved
- **`value`** (object): Value specification (see below)

### Module activation state

An entry can instead change the `activation_state` of a module (node), using `activationState` in place of `inputName` and `value`. This is needed because enabling an option in the Snooz UI can activate another module, which does not happen when the JSON is edited directly.

- **`identifier`** (string): UUID of the target node (required)
- **`activationState`** (string): one of `activated` (node is executed), `deactivated` (node is ignored), `bypass` (node lets the data pass through)
- **`required`** (boolean, default: true): fail if the identifier is not found

```json
{
  "description": "Activate the output report module.",
  "identifier": "0308c274-4216-4642-9093-0ac919e9a0de",
  "activationState": "activated",
  "required": true
}
```
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
- `asDirectory` (boolean, optional): If `true` (or if `relativePath` ends with `/`), create the path as a directory and return it with a trailing `/`. Use this for folder inputs such as `SavedDestination`.

**Example:** Output file path for a report:
```json
{
  "kind": "workspacePath",
  "relativePath": "DetectREMsYASA-report.tsv"
}
```

**Example:** Output directory:
```json
{
  "kind": "workspacePath",
  "relativePath": "ScoreSleepStagesYASA_outputs/",
  "asDirectory": true
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
