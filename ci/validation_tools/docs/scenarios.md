# Scenarios

Tools without `scenarios` keep their existing behavior: one `<ToolName>.json`,
the existing output paths, validation rules and gold-standard directory. They
appear with `scenario_id=default` in the summary.

To opt in, add a non-empty `scenarios` array. The following example is illustrative;
replace the node identifiers and input names with those from the installed tool:

```json
{
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
          "value": {
            "kind": "literal",
            "value": "pwelch"
          }
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
      "enabled": true,
      "updates": [
        {
          "identifier": "analysis-node-uuid",
          "inputName": "method",
          "value": {
            "kind": "literal",
            "value": "irasa"
          }
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
- Tool order comes from [tool_execution_order.json](../config/tool_execution_order.json);
  scenario order is the array order. `tools_to_process` still selects tools,
  and selecting a tool runs all its enabled scenarios.
- Each scenario accepts an optional boolean `enabled` (default: `true`).
  Set `"enabled": false` to temporarily disable a scenario without removing its
  configuration. JSON comments are not supported. Disabled scenarios are
  reported in logs and omitted from adaptation, the manifest, execution and
  comparisons; their validation rules must remain configured. Names, uniqueness,
  the `updates` array and the boolean flag are still validated when disabled.
  A tool with all scenarios disabled is skipped. If no enabled scenario remains
  for the selected tools, preparation fails explicitly rather than reporting a
  successful validation. Existing legacy tools without `scenarios` are unchanged.
- **Dataset changes are cumulative**, both between tools and between scenarios.
  There is no automatic reset or isolated dataset copy. Each scenario is
  captured and compared immediately, before the next one runs.
- Prefer distinct output paths per scenario. If a later tool consumes a report,
  keep its configured input pointing to the intended producer's output.

### Scenario-specific validation rules

For an explicit scenario, define a matching entry in `scenarios` in
[per-tool validation files](../tools/). Each entry requires a non-empty
`comparisons` array; it does not implicitly inherit the legacy tool comparisons.

```json
{
  "scenarios": {
    "pwelch": {
      "comparisons": [
        {
          "fileName": "report.tsv",
          "fileType": "bag-comparison",
          "precision": 4,
          "generatedSearchRoots": [
            "validation-workspaces/PowerSpectralAnalysis/pwelch"
          ]
        }
      ]
    },
    "irasa": {
      "comparisons": [
        {
          "fileName": "report.tsv",
          "fileType": "bag-comparison",
          "precision": 4,
          "generatedSearchRoots": [
            "validation-workspaces/PowerSpectralAnalysis/irasa"
          ]
        }
      ]
    }
  }
}
```

Keep search roots specific: multiple matching generated files or gold standards
are errors for explicit scenarios, rather than selecting the first match.
The existing `exists` checks, numeric precision and bootstrap behavior remain
available. A skipped gold-standard comparison is not a successful comparison.

## Manifest and results

[adapt_scenario_json.py](../runner/adapt_scenario_json.py) writes
`target/validation-logs/scenario-manifest.json` by default (`--manifest` overrides
it). It lists `tool_name`, `scenario_id`, `run_id`, `json_path` and
`explicit_scenario` for every expected execution, in execution order.
The manifest is kept outside the workspace JSON directory so path adaptation
does not rewrite it.

All three platform workflows consume this manifest through
[resolve_tool_order.py](../runner/resolve_tool_order.py) with `--manifest` and `--format tsv`.
Missing JSONs, unknown tools and inconsistent manifests fail explicitly.
Logs, status files and capture identifiers use `run_id`. Each run is compared
immediately; execution or comparison failures fail the job while allowing later
runs to execute. The summary adds `scenario_id`, preserves `tool_name`, and records
the actual adapted filename in `json_name`. Multiplatform consolidation keeps
each tool/scenario pair separate and still accepts older summary files.

To test configuration loading and scenario execution locally:

```powershell
python -m unittest discover -s ci\validation_tools\tests -v
```
