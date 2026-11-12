# Output comparisons

Each tool owns a `validations.json` file under [tools/](../tools/).
Use `fileName` when the generated and reference names match, or set both
`generatedFileName` and `goldFileName`. `generatedSearchRoots` remain relative
to the repository execution directory, not the configuration file.

## Comparison modes

- `bag-comparison`: unordered lines, preserving duplicate counts; numeric
  fields are rounded using `precision` and time formats are normalized.
- `generic` and `report`: ordered text comparisons.
- `exists`: generated file must be non-empty; PDFs must have a valid header
  and EOF marker. No gold standard is required.
- Numeric tolerance modes are detailed below.

An empty gold-standard tag skips gold comparisons, but not `exists` checks.
Missing gold standards are reported as skipped, not passed. Missing generated
files fail comparisons. Generated files are collected for bootstrap runs.

```json
{
  "comparisons": [{
    "fileName": "report.tsv",
    "fileType": "bag-comparison",
    "precision": 4,
    "generatedSearchRoots": ["validation-workspaces/Example"]
  }]
}
```

## Absolute numeric tolerance

Use `fileType: "absolute-tolerance"` to compare numeric cells by position without
rounding. Set `absoluteTolerance` per file, in the same comparison entry where
`precision` would normally be specified:

```json
{
  "fileName": "01-01-0001_dpli_convalue.tsv",
  "fileType": "absolute-tolerance",
  "absoluteTolerance": 0.015,
  "generatedSearchRoots": ["validation-workspaces"]
}
```

Each numeric cell passes when `abs(generated - reference) <= absoluteTolerance`.
The threshold must be finite and nonnegative; zero requires numeric equality.
Headers, row/column counts, row order and nonnumeric labels must match exactly.
An empty top-left header cell is supported for connectivity matrices. NaN,
infinite values, malformed tables and tables without numeric data are rejected.
All numeric data cells are checked, including the diagonal.

Do not combine this mode with `precision` or table comparison options.
The CLI equivalent is `--file-type absolute-tolerance --absolute-tolerance 0.01`.
Thresholds should be calibrated on repeated runs; the example is not a universal
threshold for all connectivity methods.

### Keyed table tolerance

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
[`compare_outputs.py`](../runner/compare_outputs.py), not by the exported TSV. Column
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
