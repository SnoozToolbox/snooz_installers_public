#!/usr/bin/env python3
"""Convert python-literal .txt files to JSON .json files in-place.
Usage: python convert_python_literals_to_json.py
"""
import ast
import json
from pathlib import Path

base = Path(__file__).parent
files = ['DetectArtifacts-alias.txt','DetectArtifacts-files.txt']
for fn in files:
    p = base / fn
    if not p.exists():
        print(f"Skipping missing: {p}")
        continue
    txt = p.read_text(encoding='utf8')
    try:
        obj = ast.literal_eval(txt)
    except Exception as e:
        print(f"Failed to parse {p}: {e}")
        continue
    out = p.with_suffix('.json')
    out.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf8')
    print(f"Wrote {out}")
