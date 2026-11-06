#!/usr/bin/env python3
"""Simple, configurable output comparison utility for CI validation."""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


NUMERIC_FIELD_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
TIME_FIELD_PATTERN = re.compile(r"^\d{1,3}:\d{1,2}(:\d{1,2})?(\.\d+)?$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare a generated file against a reference file with optional numeric tolerance."
    )
    parser.add_argument("--tool-name", required=True, help="Tool name (for logs only).")
    parser.add_argument("--generated-file", required=True, help="Path to generated output file.")
    parser.add_argument("--reference-file", required=True, help="Path to reference output file.")
    parser.add_argument(
        "--file-type",
        default="generic",
        choices=["generic", "bag-comparison", "report", "table-tolerance", "fooof-fit-quality"],
        help="Comparison mode.",
    )
    parser.add_argument(
        "--table-options",
        type=json.loads,
        help="JSON object containing keyColumns and numericTolerance or fitQuality for table modes.",
    )
    parser.add_argument(
        "--precision",
        type=float,
        default=None,
        help="Numeric rounding precision in decimals (omit for no rounding, use 0 for integer rounding).",
    )
    parser.add_argument(
        "--delimiter",
        default="\t",
        help="Column delimiter for numeric normalization and table comparison (default: tab).",
    )
    parser.add_argument(
        "--max-diff-lines",
        type=int,
        default=20,
        help="Maximum number of differences to print.",
    )
    return parser.parse_args()


def read_normalized_lines(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    return content.split("\n")


def normalize_numeric_field(field: str, round_precision: int | None) -> str:
    if round_precision is None:
        return field
    if not NUMERIC_FIELD_PATTERN.fullmatch(field):
        return field
    return f"{float(field):.{round_precision}f}"


def normalize_time_format(field: str) -> str:
    # Normalize time format MM:SS(.s) to H:MM:SS(.s) for consistent comparison.
    if not TIME_FIELD_PATTERN.fullmatch(field):
        return field
    parts = field.split(":")
    try:
        seconds = float(parts[-1])
        minutes = int(parts[-2])
        hours = int(parts[-3]) if len(parts) == 3 else 0
    except ValueError:
        return field
    if not (0 <= minutes < 60) or not (0 <= seconds < 60):
        return field
    return f"{hours}:{minutes:02d}:{seconds:.1f}"


def normalize_line(line: str, delimiter: str, round_precision: int | None, normalize_time: bool = False) -> str:
    fields = line.split(delimiter)
    normalized_fields = []
    for field in fields:
        normalized_field = normalize_numeric_field(field, round_precision)
        if normalize_time:
            normalized_field = normalize_time_format(normalized_field)
        normalized_fields.append(normalized_field)
    return delimiter.join(normalized_fields)


def normalize_lines(
    lines: list[str], delimiter: str, round_precision: int | None, normalize_time: bool = False
) -> list[str]:
    return [normalize_line(line, delimiter, round_precision, normalize_time) for line in lines]


def compare_as_text(reference: list[str], generated: list[str], max_diff_lines: int) -> int:
    if reference == generated:
        return 0

    print("Mismatch detected with exact text comparison.")
    max_len = max(len(reference), len(generated))
    shown = 0
    for idx in range(max_len):
        left = reference[idx] if idx < len(reference) else "<missing>"
        right = generated[idx] if idx < len(generated) else "<missing>"
        if left != right:
            print(f"Line {idx + 1}:")
            print(f"  ref: {left}")
            print(f"  gen: {right}")
            shown += 1
            if shown >= max_diff_lines:
                print(f"... showing first {max_diff_lines} differences only")
                break
    return 1


def validate_key_columns(keys: object) -> list[str]:
    if (
        not isinstance(keys, list) or not keys
        or any(not isinstance(key, str) or not key.strip() for key in keys)
        or len(set(keys)) != len(keys)
    ):
        raise ValueError("keyColumns must be a non-empty list of unique column names.")
    return keys


def validate_table_options(options: object) -> tuple[list[str], str, float, float]:
    if not isinstance(options, dict) or set(options) != {"keyColumns", "numericTolerance"}:
        raise ValueError("table-tolerance requires keyColumns and numericTolerance.")
    keys = validate_key_columns(options["keyColumns"])
    tolerance = options["numericTolerance"]
    if not isinstance(tolerance, dict) or set(tolerance) != {"columnPattern", "relative", "absolute"}:
        raise ValueError("numericTolerance requires columnPattern, relative and absolute.")
    pattern = tolerance["columnPattern"]
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("columnPattern must be a non-empty glob pattern.")
    for name in ("relative", "absolute"):
        value = tolerance[name]
        if (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0
        ):
            raise ValueError(f"{name} tolerance must be finite and >= 0.")
    return keys, pattern, float(tolerance["relative"]), float(tolerance["absolute"])


def read_keyed_table(
    path: Path, delimiter: str, keys: list[str]
) -> tuple[list[str], dict[tuple[str, ...], list[str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        header = next(reader, None)
        if not header or any(not name.strip() for name in header) or len(set(header)) != len(header):
            raise ValueError(f"{path}: missing, empty or duplicate column names.")
        if any(key not in header for key in keys):
            raise ValueError(f"{path}: missing key columns {keys!r}.")
        key_indices = [header.index(key) for key in keys]
        rows: dict[tuple[str, ...], list[str]] = {}
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError(f"{path}: line {reader.line_num} has {len(row)} fields; expected {len(header)}.")
            key = tuple(row[index] for index in key_indices)
            if any(not value.strip() for value in key):
                raise ValueError(f"{path}: empty key at line {reader.line_num}.")
            if key in rows:
                raise ValueError(f"{path}: duplicate key {key!r} at line {reader.line_num}.")
            rows[key] = row
        return header, rows


def validate_fit_options(options: object) -> tuple[list[str], list[str], dict[str, float]]:
    if not isinstance(options, dict) or set(options) != {"keyColumns", "fitQuality"}:
        raise ValueError("fooof-fit-quality requires keyColumns and fitQuality.")
    keys = validate_key_columns(options["keyColumns"])
    quality = options["fitQuality"]
    thresholds = {"maxError", "maxErrorIncrease", "minR2", "maxR2Decrease"}
    if not isinstance(quality, dict) or set(quality) != thresholds | {"fitKeyColumns"}:
        raise ValueError("fitQuality requires fitKeyColumns and " + ", ".join(sorted(thresholds)) + ".")
    fit_keys = quality["fitKeyColumns"]
    if (
        not isinstance(fit_keys, list) or not fit_keys
        or any(not isinstance(key, str) or key not in keys for key in fit_keys)
        or len(set(fit_keys)) != len(fit_keys)
        or set(fit_keys) == set(keys)
    ):
        raise ValueError("fitKeyColumns must be a non-empty, unique, proper subset of keyColumns.")
    for name in thresholds:
        value = quality[name]
        if (
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0
            or (name in {"minR2", "maxR2Decrease"} and value > 1)
        ):
            raise ValueError(f"{name} must be finite and >= 0 (and <= 1 for R2 thresholds).")
    return keys, fit_keys, {name: float(quality[name]) for name in thresholds}


def read_fit_number(field: str, context: str) -> float | None:
    if field in ("", "nan", "NaN"):
        return None
    if not NUMERIC_FIELD_PATTERN.fullmatch(field) or not math.isfinite(float(field)):
        raise ValueError(f"Invalid numeric value at {context}: {field!r}")
    return float(field)


def compare_fooof_fit_quality(
    reference: Path, generated: Path, delimiter: str, options: object, max_diff_lines: int
) -> int:
    keys, fit_keys, limits = validate_fit_options(options)
    if len(delimiter) != 1:
        raise ValueError("fooof-fit-quality requires a single-character delimiter.")
    header, ref_rows = read_keyed_table(reference, delimiter, keys)
    gen_header, gen_rows = read_keyed_table(generated, delimiter, keys)
    if header != gen_header:
        raise ValueError("Table headers differ (including column order).")
    if not ref_rows or not gen_rows:
        raise ValueError("Fit-quality tables must contain data rows.")
    error_names = {name for name in header if name.endswith("_fit_err")}
    r2_names = {name for name in header if name.endswith("_fit_r2")}
    if (
        "total_fit_err" not in error_names
        or {name.removesuffix("_err") + "_r2" for name in error_names} != r2_names
    ):
        raise ValueError("Expected total_fit_err/total_fit_r2 and paired *_fit_err/*_fit_r2 columns.")
    metric_indices = {i for i, name in enumerate(header) if name in error_names | r2_names}
    energy_indices = {i for i, name in enumerate(header) if fnmatch.fnmatchcase(name, "*_act")}
    if not energy_indices or any(header[i] in keys for i in metric_indices | energy_indices):
        raise ValueError("Expected non-key *_act and fit metric columns.")
    fit_indices = [header.index(name) for name in fit_keys]

    def group_scores(rows: dict[tuple[str, ...], list[str]], label: str) -> dict[tuple[str, ...], dict[str, float | None]]:
        groups: dict[tuple[str, ...], dict[str, float | None]] = {}
        for row in rows.values():
            fit_key = tuple(row[i] for i in fit_indices)
            scores = {}
            for i in sorted(metric_indices):
                name = header[i]
                value = read_fit_number(row[i], f"{label}, fit={fit_key!r}, column={name!r}")
                if value is not None and (value < 0 or (name in r2_names and value > 1)):
                    raise ValueError(f"{label}: out-of-domain score for fit={fit_key!r}, column={name!r}.")
                scores[name] = value
            for name in error_names:
                if scores[name] is None and scores[name.removesuffix("_err") + "_r2"] is not None:
                    raise ValueError(f"{label}: R2 present without fit error for fit={fit_key!r}, column={name!r}.")
            if fit_key in groups and groups[fit_key] != scores:
                raise ValueError(f"{label}: inconsistent fit scores across bands for fit={fit_key!r}.")
            groups[fit_key] = scores
        return groups

    ref_groups = group_scores(ref_rows, "reference")
    gen_groups = group_scores(gen_rows, "generated")
    failures = shown = 0

    def report(message: str, failed: bool = True) -> None:
        nonlocal failures, shown
        failures += int(failed)
        if shown < max_diff_lines:
            print(message)
            shown += 1

    print(f"FOOOF full-model quality (not component equivalence): {limits}; fit keys={fit_keys!r}")
    for key in sorted(ref_rows.keys() - gen_rows.keys()):
        report(f"Missing generated key: {key!r}")
    for key in sorted(gen_rows.keys() - ref_rows.keys()):
        report(f"Unexpected generated key: {key!r}")
    energy_changed = 0
    max_energy_error = 0.0
    for key in sorted(ref_rows.keys() & gen_rows.keys()):
        for i, (ref, gen) in enumerate(zip(ref_rows[key], gen_rows[key])):
            if i in metric_indices:
                continue
            if i in energy_indices:
                left = read_fit_number(ref, f"reference, key={key!r}, column={header[i]!r}")
                right = read_fit_number(gen, f"generated, key={key!r}, column={header[i]!r}")
                if (left is None) != (right is None):
                    report(f"Energy availability changed: key={key!r}, column={header[i]!r}")
                elif left is not None and right is not None:
                    energy_changed += int(left != right)
                    max_energy_error = max(max_energy_error, abs(right - left))
            elif ref != gen:
                report(f"Exact cell mismatch: key={key!r}, column={header[i]!r}, ref={ref!r}, gen={gen!r}")

    compared = missing = 0
    stats: dict[str, list[tuple[float, float, tuple[str, ...], str]]] = {"err": [], "r2": []}
    for key in sorted(ref_groups.keys() & gen_groups.keys()):
        for name, left in ref_groups[key].items():
            right = gen_groups[key][name]
            if left is None or right is None:
                if left != right:
                    report(f"Score availability changed: fit={key!r}, column={name!r}, ref={left}, gen={right}")
                else:
                    missing += 1
                continue
            compared += 1
            is_error = name in error_names
            kind = "err" if is_error else "r2"
            degradation = right - left if is_error else left - right
            stats[kind].append((right, degradation, key, name))
            bad = (
                right > limits["maxError"] or degradation > limits["maxErrorIncrease"]
                if is_error else
                right < limits["minR2"] or degradation > limits["maxR2Decrease"]
            )
            if bad or left != right:
                report(
                    f"{'FAIL' if bad else 'Score change'}: fit={key!r}, column={name!r}, "
                    f"ref={left:.12g}, gen={right:.12g}, degradation={degradation:.12g}", bad
                )
    for kind, values in stats.items():
        if values:
            worst = max(values, key=lambda value: value[1])
            print(
                f"Fit {kind}: count={len(values)}, generated_min={min(v[0] for v in values):.12g}, "
                f"generated_max={max(v[0] for v in values):.12g}, "
                f"mean_degradation={sum(v[1] for v in values) / len(values):.12g}, "
                f"max_degradation={worst[1]:.12g}, worst_fit={worst[2]!r}, column={worst[3]!r}"
            )
    if missing:
        print(f"WARNING: {missing} matching missing scores were not evaluated (counted once per fit).")
    print(
        f"Fit-quality summary: reference_groups={len(ref_groups)}, generated_groups={len(gen_groups)}, "
        f"compared_scores={compared}, unevaluated_scores={missing}, failures={failures}; "
        f"energy_changes_non_blocking={energy_changed}, max_absolute_energy_change={max_energy_error:.12g}"
    )
    return int(failures > 0)


def compare_table_tolerance(
    reference: Path, generated: Path, delimiter: str, options: object, max_diff_lines: int
) -> int:
    keys, pattern, relative, absolute = validate_table_options(options)
    if len(delimiter) != 1:
        raise ValueError("table-tolerance requires a single-character delimiter.")
    header, ref_rows = read_keyed_table(reference, delimiter, keys)
    gen_header, gen_rows = read_keyed_table(generated, delimiter, keys)
    if header != gen_header:
        raise ValueError("Table headers differ (including column order).")
    tolerant_indices = {i for i, name in enumerate(header) if fnmatch.fnmatchcase(name, pattern)}
    if not tolerant_indices:
        raise ValueError(f"columnPattern {pattern!r} matches no columns.")
    if any(header[i] in keys for i in tolerant_indices):
        raise ValueError("Tolerance must not apply to key columns.")
    print(f"Tolerance: columns={pattern!r}, relative={relative}, absolute={absolute}; keys={keys!r}")
    missing = ref_rows.keys() - gen_rows.keys()
    extra = gen_rows.keys() - ref_rows.keys()
    differences = numeric_differences = 0
    shown = 0

    def report(message: str) -> None:
        nonlocal shown
        if shown < max_diff_lines:
            print(message)
            shown += 1

    for key in sorted(missing):
        report(f"Missing generated key: {key!r}")
    for key in sorted(extra):
        report(f"Unexpected generated key: {key!r}")
    for key in sorted(ref_rows.keys() & gen_rows.keys()):
        for i, (ref, gen) in enumerate(zip(ref_rows[key], gen_rows[key])):
            detail = ""
            if i in tolerant_indices:
                values = []
                for field in (ref, gen):
                    if field in ("", "nan", "NaN"):
                        values.append(None)
                    else:
                        if not NUMERIC_FIELD_PATTERN.fullmatch(field) or not math.isfinite(float(field)):
                            raise ValueError(f"Invalid numeric value at key={key!r}, column={header[i]!r}: {field!r}")
                        values.append(float(field))
                left, right = values
                if left is None or right is None:
                    equal = ref == gen
                else:
                    error = abs(right - left)
                    limit = absolute + relative * abs(left)
                    if not math.isfinite(limit):
                        raise ValueError(f"Tolerance overflow at key={key!r}, column={header[i]!r}.")
                    equal = error <= limit
                    if not equal:
                        numeric_differences += 1
                        detail = f", absolute_error={error:.12g}, allowed={limit:.12g}"
            else:
                equal = ref == gen
            if not equal:
                differences += 1
                report(f"key={key!r}, column={header[i]!r}: ref={ref!r}, gen={gen!r}{detail}")
    print(
        f"Table summary: reference_rows={len(ref_rows)}, generated_rows={len(gen_rows)}, "
        f"missing_keys={len(missing)}, extra_keys={len(extra)}, "
        f"differing_cells={differences}, numeric_cells_outside_tolerance={numeric_differences}"
    )
    return int(bool(missing or extra or differences))


def compare_annotation_unordered(reference: list[str], generated: list[str], max_diff_lines: int) -> int:
    reference_counter = Counter(reference)
    generated_counter = Counter(generated)
    if reference_counter == generated_counter:
        return 0

    print("Mismatch detected with annotation unordered comparison.")
    only_in_reference = list((reference_counter - generated_counter).elements())
    only_in_generated = list((generated_counter - reference_counter).elements())

    def first_diff_field(ref_line: str, gen_line: str, delimiter: str = "\t") -> str:
        ref_fields = ref_line.split(delimiter)
        gen_fields = gen_line.split(delimiter)
        maxf = max(len(ref_fields), len(gen_fields))
        for i in range(maxf):
            r = ref_fields[i] if i < len(ref_fields) else "<missing>"
            g = gen_fields[i] if i < len(gen_fields) else "<missing>"
            if r != g:
                # limit output length for readability
                r_short = (r[:300] + "...") if len(r) > 300 else r
                g_short = (g[:300] + "...") if len(g) > 300 else g
                return f"first differing field #{i+1}: ref='{r_short}' vs gen='{g_short}'"
        # If no differing tab-separated field, fall back to first differing character
        if ref_line == gen_line:
            return "(lines identical)"
        maxc = max(len(ref_line), len(gen_line))
        for i in range(maxc):
            rc = ref_line[i] if i < len(ref_line) else "<EOL>"
            gc = gen_line[i] if i < len(gen_line) else "<EOL>"
            if rc != gc:
                # show context around the differing char
                start = max(0, i - 20)
                end = min(maxc, i + 20)
                ref_snip = ref_line[start:end]
                gen_snip = gen_line[start:end]
                rc_repr = f"U+{ord(rc):04X}" if len(rc) == 1 else rc
                gc_repr = f"U+{ord(gc):04X}" if len(gc) == 1 else gc
                return (
                    f"first differing char at index {i}: ref[{rc_repr}] vs gen[{gc_repr}]\n"
                    f"  ref context: ...{ref_snip}...\n"
                    f"  gen context: ...{gen_snip}..."
                )
        return "(lines differ but no differing character found)"

    shown = 0
    max_len = max(len(only_in_reference), len(only_in_generated))
    for idx in range(max_len):
        ref_value = only_in_reference[idx] if idx < len(only_in_reference) else "<none>"
        gen_value = only_in_generated[idx] if idx < len(only_in_generated) else "<none>"
        print(f"Diff {idx + 1}:")
        # Show concise first differing field when possible
        if ref_value != "<none>" and gen_value != "<none>":
            diff_info = first_diff_field(ref_value, gen_value)
            print(f"  {diff_info}")
        elif ref_value != "<none>" and gen_value == "<none>":
            # Try to find a best-match in generated lines by matching initial fields (id/key)
            ref_fields = ref_value.split("\t")
            best_match = None
            # try matching first 1..3 fields
            for k in range(1, min(4, len(ref_fields) + 1)):
                key = tuple(ref_fields[:k])
                for g in generated:
                    g_fields = g.split("\t")
                    if tuple(g_fields[:k]) == key:
                        best_match = g
                        break
                if best_match:
                    break
            if best_match:
                diff_info = first_diff_field(ref_value, best_match)
                # Show line counts if lines appear identical
                if diff_info == "(lines identical)":
                    ref_count = reference_counter.get(ref_value, 0)
                    gen_count = generated_counter.get(ref_value, 0)
                    print(f"  lines are identical but have different occurrence counts: ref={ref_count}, gen={gen_count}")
                else:
                    print(f"  only in ref (closest gen match): {diff_info}")
            else:
                print(f"  only in ref: {ref_value}")
        else:
            print(f"  only in ref: {ref_value}")
            print(f"  only in gen: {gen_value}")
        shown += 1
        if shown >= max_diff_lines:
            print(f"... showing first {max_diff_lines} differences only")
            break

    print(f"\nSummary: Reference has {len(reference)} lines, Generated has {len(generated)} lines")
    print(f"Unique lines in ref: {len(reference_counter)}, Unique lines in gen: {len(generated_counter)}")

    return 1


def main() -> int:
    args = parse_args()
    generated = Path(args.generated_file)
    reference = Path(args.reference_file)

    print(f"Tool: {args.tool_name}")
    print(f"File type: {args.file_type}")
    print(f"Generated file: {generated}")
    print(f"Reference file: {reference}")
    print(f"Precision: {args.precision}")

    if not generated.is_file():
        print(f"Generated file not found: {generated}")
        return 1
    if not reference.is_file():
        print(f"Reference file not found: {reference}")
        return 1

    if args.file_type in ("table-tolerance", "fooof-fit-quality"):
        try:
            if args.precision is not None:
                raise ValueError(f"{args.file_type} cannot be combined with precision rounding.")
            compare = compare_table_tolerance if args.file_type == "table-tolerance" else compare_fooof_fit_quality
            status = compare(
                reference, generated, args.delimiter, args.table_options, args.max_diff_lines
            )
        except (ValueError, OSError, UnicodeError, csv.Error) as error:
            print(f"Comparison failed: {error}")
            return 1
        print("Comparison succeeded." if status == 0 else "Comparison failed.")
        return status
    if args.table_options is not None:
        print("Comparison failed: table-options requires a table comparison mode.")
        return 1

    round_precision: int | None = None
    if args.precision is not None:
        if args.precision < 0:
            print("Precision must be >= 0 when provided.")
            return 1
        if not float(args.precision).is_integer():
            print("Precision must be an integer number of decimals when provided (e.g. 0, 2, 4).")
            return 1
        round_precision = int(args.precision)

    normalize_time = args.file_type == "bag-comparison"
    ref_lines = read_normalized_lines(reference)
    gen_lines = read_normalized_lines(generated)
    ref_lines = normalize_lines(ref_lines, args.delimiter, round_precision, normalize_time)
    gen_lines = normalize_lines(gen_lines, args.delimiter, round_precision, normalize_time)

    if args.file_type == "bag-comparison":
        status = compare_annotation_unordered(ref_lines, gen_lines, args.max_diff_lines)
    else:
        status = compare_as_text(ref_lines, gen_lines, args.max_diff_lines)

    if status == 0:
        print("Comparison succeeded.")
    else:
        print("Comparison failed.")

    return status


if __name__ == "__main__":
    sys.exit(main())
