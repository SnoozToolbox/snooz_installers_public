#!/usr/bin/env python3
"""Simple, configurable output comparison utility for CI validation."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path


NUMERIC_FIELD_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


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
        choices=["generic", "annotation", "report"],
        help="File type selector for future custom logic.",
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
        help="Column delimiter used when precision > 0 (default: tab).",
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


def normalize_line(line: str, delimiter: str, round_precision: int | None) -> str:
    fields = line.split(delimiter)
    normalized_fields = [normalize_numeric_field(field, round_precision) for field in fields]
    return delimiter.join(normalized_fields)


def normalize_lines(lines: list[str], delimiter: str, round_precision: int | None) -> list[str]:
    return [normalize_line(line, delimiter, round_precision) for line in lines]


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
        return "(lines differ but no differing tab-separated field detected)"

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
        else:
            print(f"  only in ref: {ref_value}")
            print(f"  only in gen: {gen_value}")
        shown += 1
        if shown >= max_diff_lines:
            print(f"... showing first {max_diff_lines} differences only")
            break

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

    round_precision: int | None = None
    if args.precision is not None:
        if args.precision < 0:
            print("Precision must be >= 0 when provided.")
            return 1
        if not float(args.precision).is_integer():
            print("Precision must be an integer number of decimals when provided (e.g. 0, 2, 4).")
            return 1
        round_precision = int(args.precision)

    ref_lines = read_normalized_lines(reference)
    gen_lines = read_normalized_lines(generated)
    ref_lines = normalize_lines(ref_lines, args.delimiter, round_precision)
    gen_lines = normalize_lines(gen_lines, args.delimiter, round_precision)

    if args.file_type == "annotation":
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
