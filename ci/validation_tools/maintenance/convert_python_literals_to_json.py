#!/usr/bin/env python3
"""Convert python-literal .txt files to JSON .json files in-place.
Usage: python convert_python_literals_to_json.py path/to/input.txt [...]
"""
import argparse
import ast
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    for source in args.files:
        obj = ast.literal_eval(source.read_text(encoding="utf-8-sig"))
        destination = source.with_suffix(".json")
        destination.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
