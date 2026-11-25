# Validation tools

Start with the tool's directory under [tools/](tools/). Each directory owns:

- `adaptations.json`: input values and node activation changes for the installed process.
- `validations.json`: expected outputs, comparison modes and tolerances.
- `inputs/`: large JSON input values specific to that tool.

The directory name is the installed tool basename. Do not wrap either configuration
in another object keyed by that name. Both files are required for every tool.
There are no generated or manually maintained aggregate configuration files.

## Layout

| Location | Responsibility |
| --- | --- |
| [tools/](tools/) | Per-tool adaptation and validation configuration |
| [shared/inputs/](shared/inputs/) | Inputs intentionally reused by multiple tools |
| [config/tool_execution_order.json](config/tool_execution_order.json) | Explicit cross-platform execution order |
| [runner/](runner/) | Shared loader, configuration validator and CI execution scripts |
| [maintenance/](maintenance/) | Developer utilities, not invoked by validation workflows |
| [docs/](docs/) | Adaptation, comparison and scenario reference |
| [tests/](tests/) | Standard-library regression tests |

`shared/inputs/psg-files-without-chan-selection.json` replaces the identical input
files previously named for SleepCycleExport, ExtractAnnotation and
ImportTextAnnotations. SleepReport, SleepBouts and CompareEventsFromPSG use it too. `spindle-files.json` is shared by
the three spindle detection tools. Other input files remain separate because
their selections may differ.

ValidateSnoozTSVFile checks four private-dataset `*_fake_text_annot.tsv` files
and `SC4001E0-PSG.tsv`, then compares its five validation text logs exactly.
Developers must run ImportEDFPlusAnnotations first to generate `SC4001E0-PSG.tsv`.
Selecting ValidateSnoozTSVFile does not automatically select or run that importer.

## Paths

- `workspaceFileJson.relativePath` is relative to the **containing
  adaptations.json**, including references inside scenario updates or `fileSpec`.
  For a tool-owned input use `inputs/files.json`. For the shared PSG input use
  `../../shared/inputs/psg-files-without-chan-selection.json`.
- `workspacePath.relativePath` remains relative to `--workspace-dir`.
  `asDirectory: true` creates the directory before execution.
- `privateDatasetPath.relativePath` remains relative to `--private-dataset-dir`.
- `findPath.roots` and `generatedSearchRoots` remain relative to the execution
  working directory, normally the repository root.
- `$GITHUB_WORKSPACE` inside input values is replaced **after** adaptation, in
  generated process JSONs only. Source configuration and input files are not changed.

## Check changes

Run from the repository root; no installer, private dataset or gold standard is needed:

```powershell
python ci\validation_tools\runner\validate_configuration.py
python -m unittest discover -s ci\validation_tools\tests -v
```

The platform workflows run these checks immediately after checkout. The validator
rejects missing configurations or input files, invalid JSON, inconsistent execution
order or scenario identifiers, duplicate output comparisons and invalid comparison
options. It also checks disabled scenarios. It cannot verify node UUIDs against an
installer; adaptation still fails explicitly if a required node or input is absent.

## Add or change a tool

Recommended starting point: run the tool locally in Snooz with the desired inputs
and settings, then save the workspace. From Snooz, ask the AI to compare that
workspace with the installed/distributed tool workspace. The AI can usually create
the required per-tool files and infer most adaptations. Treat the result as a draft:
verify node identifiers, input names and types, settings, paths and output names
against the saved workspace and installed process.

1. Edit or create `tools/<ToolName>/adaptations.json` and `validations.json`.
2. Keep large values in that tool's `inputs/`. Share only genuinely identical inputs.
3. Use node identifiers and input types from the installed process.
4. Configure all options needed to generate the expected outputs. For example,
   SleepReport explicitly enables `save_events_report` for its `_EVENTS_` TSV files.
5. Add the tool once to [execution order](config/tool_execution_order.json), where
   the required dataset state is available. Changes are cumulative between runs.
6. Run the checks above, then validate the selected tool against its installer and
   gold standard in CI.

See [adaptations](docs/adaptations.md), [comparisons](docs/comparisons.md) and
[scenarios](docs/scenarios.md) for details. Keep ordinary tools in two configuration
files; split scenarios further only if a concrete maintenance need justifies it.

## CI entry points

### Installers without NATUS

The orchestrator and all platform workflows expose `include_natus` (default:
`true`, preserving the complete CEAMS validation). Set it to `false` when
validating public `snooz-toolbox` installers without the NATUS reader.

The runners receive this option through `INCLUDE_NATUS=true|false`. They exclude
the configured NATUS subject from all final scenario node inputs, including
shared JSON values, tool-specific values and Python-literal containers. An
unfilterable scalar reference or an input emptied by exclusion fails explicitly.
Source configurations and installed workspaces are not modified.

Individual NATUS output checks are excluded. Text and table comparisons remove
NATUS data rows from both generated and reference reports, without changing
headers, tolerances or saved artifacts. Other missing outputs still fail.
An empty comparison or a NATUS reference in a header fails rather than passing.
The same gold standards can therefore be used for per-subject reports.

When `include_natus=false`, selecting PSAImages or PSACohortReview without
PowerSpectralAnalysis, or DetectionsCohortReview or SlowWaveClassification without SlowWaveDetection,
requires a gold-standard tag and these inputs in the producer archives:

- `PowerSpectralAnalysis.zip`: `pwelch/EEG_spectral_power_cohort_report_Welch_without_natus.tsv`
  and, for PSACohortReview, `irasa/EEG_spectral_power_cohort_report_IRASA_periodic_without_natus.tsv`.
- `SlowWaveDetection.zip`: `Slow-Waves-Cohort-report_without_natus.tsv`.
- For SlowWaveClassification, `SlowWaveDetection.zip` also needs each non-NATUS
  subject's `slow_wave_characteristics/*_sw_carrier.tsv` and
  `slow_wave_sleep_stages/*_sw_carrier_stages.tsv` files.

The inputs must contain no NATUS subject. They are copied under the normal
report names into `validation-workspaces`, so existing scenario paths and PDF
names remain unchanged. When a producer is selected, its generated report is
used instead; a missing generated report is not replaced by a gold standard.
Without a gold-standard tag, run the producers with the consumers.
PSAImages checks for plots of NATUS-only channels are excluded in this mode.

`SlowWaveClassification` uses the non-NATUS cohort and per-subject inputs.
Its results depend on the complete cohort, so `SlowWaveClassification.zip` must
contain separate gold standards for the non-NATUS run:

- `01-01-0001_sw_carrier_without_natus.tsv`
- `learn-nsrr01_sw_carrier_without_natus.tsv`
- `learn-nsrr02_sw_carrier_without_natus.tsv`
- `sw_cohort_details_per_categories_without_natus.tsv`
- `sw_cohort_details_per_categories_info_without_natus.tsv`

Generate these references from a validated non-NATUS run; removing rows from
the full-cohort classification results is not sufficient. With a gold-standard
tag, a missing non-NATUS reference fails comparison. For the first run, leave
the tag empty and select SlowWaveDetection as well as SlowWaveClassification;
then inspect the captured outputs before publishing the new references.

Adaptation and comparison commands take `--tools-dir ci/validation_tools/tools`.
The former `--adaptations-file` and `--tool-validations-file` aggregate-file
arguments have been removed.

```powershell
python ci\validation_tools\runner\adapt_scenario_json.py `
  --tools-dir ci\validation_tools\tools `
  --source-dir validation-json `
  --workspace-dir validation-workspaces `
  --private-dataset-dir private-dataset `
  --tools SleepReport
```

The manifest, adapted filenames, output directories, capture layout and gold-standard
layout are unchanged. Generated outputs do not belong in this configuration tree.
