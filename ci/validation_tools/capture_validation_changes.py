#!/usr/bin/env python3
"""Capture files changed by sequential validation tools and build checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path


def parse_roots(values: list[str]) -> dict[str, Path]:
    roots = {}
    for value in values:
        path = Path(value).resolve()
        name = path.name
        if not name or name in roots:
            raise ValueError(f"Validation root names must be unique: {value}")
        roots[name] = path
    return roots


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(roots: dict[str, Path]) -> dict[str, dict[str, int]]:
    files = {}
    for root_name, root_path in roots.items():
        if not root_path.exists():
            continue
        for path in sorted(root_path.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            stat = path.stat()
            key = f"{root_name}/{path.relative_to(root_path).as_posix()}"
            files[key] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return files


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_inventory_path(key: str, roots: dict[str, Path]) -> Path:
    root_name, relative_path = key.split("/", 1)
    return roots[root_name] / Path(relative_path)


def safe_tool_name(tool_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", tool_name).strip("._") or "tool"


def snapshot(args: argparse.Namespace) -> None:
    roots = parse_roots(args.root)
    write_json(Path(args.output), {"roots": list(roots), "files": inventory(roots)})


def capture(args: argparse.Namespace) -> None:
    roots = parse_roots(args.root)
    before_path = Path(args.manifest)
    before = load_json(before_path).get("files", {})
    after = inventory(roots)

    created = sorted(after.keys() - before.keys())
    deleted = sorted(before.keys() - after.keys())
    modified = sorted(key for key in after.keys() & before.keys() if after[key] != before[key])
    changed = created + modified

    tool_id = f"{args.sequence:02d}-{safe_tool_name(args.tool)}"
    output_dir = Path(args.output_dir)
    tool_dir = output_dir / "tools" / tool_id
    changes_dir = tool_dir / "changes"
    state_dir = output_dir / "checkpoint-state"
    state_files_dir = state_dir / "files"
    deleted_state_path = state_dir / "deleted-paths.json"
    deleted_state = set(load_json(deleted_state_path)) if deleted_state_path.exists() else set()

    file_records = []
    for key in changed:
        source = resolve_inventory_path(key, roots)
        destination = changes_dir / Path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

        state_destination = state_files_dir / Path(key)
        state_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, state_destination)
        deleted_state.discard(key)
        file_records.append({"path": key, "sha256": file_digest(source), **after[key]})

    for key in deleted:
        state_path = state_files_dir / Path(key)
        if state_path.exists():
            state_path.unlink()
        deleted_state.add(key)

    write_json(deleted_state_path, sorted(deleted_state))
    write_json(
        tool_dir / "changes.json",
        {
            "tool": args.tool,
            "sequence": args.sequence,
            "created": created,
            "modified": modified,
            "deleted": deleted,
            "files": file_records,
        },
    )
    write_json(before_path, {"roots": list(roots), "files": after})


def checkpoint(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    state_dir = output_dir / "checkpoint-state"
    tool_id = f"{args.sequence:02d}-{safe_tool_name(args.tool)}"
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    archive_path = checkpoint_dir / f"{tool_id}-before.zip"

    metadata = {
        "tool": args.tool,
        "sequence": args.sequence,
        "purpose": "Overlay to apply to the original validation dataset before running this tool.",
    }
    metadata_path = state_dir / "checkpoint.json"
    write_json(metadata_path, metadata)
    if not (state_dir / "deleted-paths.json").exists():
        write_json(state_dir / "deleted-paths.json", [])

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(state_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(state_dir).as_posix())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Record the current files in validation roots")
    snapshot_parser.add_argument("--root", action="append", required=True)
    snapshot_parser.add_argument("--output", required=True)
    snapshot_parser.set_defaults(function=snapshot)

    capture_parser = subparsers.add_parser("capture", help="Collect changes since the previous snapshot")
    capture_parser.add_argument("--root", action="append", required=True)
    capture_parser.add_argument("--manifest", required=True)
    capture_parser.add_argument("--output-dir", required=True)
    capture_parser.add_argument("--tool", required=True)
    capture_parser.add_argument("--sequence", type=int, required=True)
    capture_parser.set_defaults(function=capture)

    checkpoint_parser = subparsers.add_parser("checkpoint", help="Archive cumulative state before a tool runs")
    checkpoint_parser.add_argument("--output-dir", required=True)
    checkpoint_parser.add_argument("--tool", required=True)
    checkpoint_parser.add_argument("--sequence", type=int, required=True)
    checkpoint_parser.set_defaults(function=checkpoint)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.function(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())