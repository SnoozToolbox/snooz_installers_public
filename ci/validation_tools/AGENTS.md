# Working on validation tools

- Read [README.md](README.md) first, then the target tool's files under [tools/](tools/).
- Edit `tools/<ToolName>/adaptations.json` for inputs and node activation; edit
  `validations.json` for expected outputs. Do not restore global aggregate JSON files.
- `workspaceFileJson` paths are relative to the containing adaptation file.
  Output paths and dataset paths have different bases; see the README.
- Keep large tool-specific values in its `inputs/`. Shared values belong in
  `shared/inputs/`; do not share merely similar channel or event selections.
- Verify UUIDs, input names and value types against the installed process or an
  explicitly supplied local process. Do not guess missing settings.
- Preserve execution order, scenario order and common-update-then-override semantics.
  Tools and scenarios mutate a cumulative dataset; there is no automatic reset.
- Match validation scenario identifiers exactly, including disabled scenarios.
  Prefer separate generated output directories for different scenarios.
- Use `bag-comparison` with the established precision for unordered TSV reports;
  use the documented tolerance modes only when justified. Do not weaken existing
  comparisons to hide failures.
- Do not introduce personal metadata, credentials or local absolute paths into
  public configuration. A UI de-identification option may leave identifiers and
  demographics intact; inspect its actual result.
- Run from the repository root:
  `python ci\validation_tools\runner\validate_configuration.py` and
  `python -m unittest discover -s ci\validation_tools\tests -v`.
- For loader or runner changes, add focused regression tests in [tests/](tests/).
  Check all three platform workflows when changing entry points.
- Keep comments in English. Avoid template inheritance, implicit fallbacks and
  generic include systems when ordinary JSON and the shared loader suffice.
