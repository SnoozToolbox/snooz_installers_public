#!/usr/bin/env python3
"""Capture files changed by sequential validation tools and build checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path


def enable_long_paths():
    """Enable long path support on Windows to handle paths > 260 characters."""
    if sys.platform == "win32":
        try:
            # Use \\?\ prefix for absolute paths on Windows to bypass MAX_PATH
            # This is handled by pathlib on Python 3.6+, but we ensure registry entry exists
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
                    value = winreg.QueryValueEx(key, "LongPathsEnabled")[0]
                    if value:
                        print("Long paths already enabled in registry", file=sys.stderr)
            except (WindowsError, FileNotFoundError):
                print("Warning: Unable to check long paths registry; continuing anyway", file=sys.stderr)
        except (ImportError, Exception) as e:
            print(f"Warning: {e}", file=sys.stderr)


def to_windows_long_path(path: Path) -> Path:
    """Convert path to Windows long path format if needed."""
    if sys.platform != "win32":
        return path
    try:
        # Convert to absolute path and use UNC format for long paths
        abs_path = path.resolve()
        # Check if path is already a long path
        if str(abs_path).startswith("\\\\?\\"):
            return abs_path
        # For local paths > 260 chars, use \\?\ prefix
        if len(str(abs_path)) > 260:
            # Don't add prefix for network paths (starting with \\)
            if not str(abs_path).startswith("\\\\"):
                return Path(f"\\\\?\\{abs_path}")
        return abs_path
    except Exception:
        return path


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
    path = to_windows_long_path(path)
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


def flat_capture_names(keys: list[str]) -> dict[str, str]:
    counts = {}
    for key in keys:
        name = Path(key).name.casefold()
        counts[name] = counts.get(name, 0) + 1

    names = {}
    used = {"changes.json"}
    for key in sorted(keys):
        filename = Path(key).name
        if counts[filename.casefold()] > 1 or filename.casefold() == "changes.json":
            path = Path(filename)
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            filename = f"{path.stem[:120]}-{digest}{path.suffix[:20]}"
        if filename.casefold() in used:
            raise ValueError(f"Capture filename collision for {key}: {filename}")
        used.add(filename.casefold())
        names[key] = filename
    return names


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
    tool_dir = output_dir / tool_id
    capture_names = flat_capture_names(changed)
    state_dir = Path(args.state_dir)
    state_files_dir = state_dir / "files"
    deleted_state_path = state_dir / "deleted-paths.json"
    deleted_state = set(load_json(deleted_state_path)) if deleted_state_path.exists() else set()

    # Enable long paths for Windows
    if sys.platform == "win32":
        state_files_dir = to_windows_long_path(state_files_dir)

    file_records = []
    copy_errors = []
    
    print(f"Capturing {len(changed)} changed files for tool {args.tool} (sequence {args.sequence})", file=sys.stderr)
    
    for key in changed:
        try:
            source = resolve_inventory_path(key, roots)
            captured_path = capture_names[key]
            destination = tool_dir / Path(captured_path)
            destination = to_windows_long_path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

            state_destination = state_files_dir / Path(key)
            state_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, state_destination)
            deleted_state.discard(key)
            file_records.append({
                "path": key,
                "captured_path": captured_path,
                "sha256": file_digest(source),
                **after[key],
            })
        except OSError as e:
            copy_errors.append({"path": key, "error": str(e)})
            print(f"Warning: Failed to copy {key}: {e}", file=sys.stderr)
            continue

    if copy_errors:
        print(f"Error: {len(copy_errors)} files failed to copy:", file=sys.stderr)
        for entry in copy_errors[:10]:  # Show first 10 errors
            print(f"  - {entry['path']}: {entry['error']}", file=sys.stderr)
        if len(copy_errors) > 10:
            print(f"  ... and {len(copy_errors) - 10} more", file=sys.stderr)

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
            "copy_errors": copy_errors,
        },
    )
    if copy_errors:
        raise RuntimeError(f"Capture failed for {args.tool}: {len(copy_errors)} files could not be copied")
    write_json(before_path, {"roots": list(roots), "files": after})
    
    print(f"Successfully captured {len(file_records)} files for tool {args.tool}", file=sys.stderr)


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

    failed_files = []
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(state_dir.rglob("*")):
            if path.is_file():
                try:
                    # Use the actual path (with long path support on Windows)
                    source_path = to_windows_long_path(path) if sys.platform == "win32" else path
                    arcname = path.relative_to(state_dir).as_posix()
                    archive.write(source_path, arcname)
                except OSError as e:
                    failed_files.append({"file": str(path), "error": str(e)})
                    print(f"Warning: Failed to add {path} to checkpoint archive: {e}", file=sys.stderr)
    
    if failed_files:
        print(f"Warning: {len(failed_files)} files failed to add to checkpoint archive", file=sys.stderr)
        for entry in failed_files:
            print(f"  - {entry['file']}: {entry['error']}", file=sys.stderr)
        raise RuntimeError(f"Checkpoint incomplete: {len(failed_files)} files could not be archived")


def finalize(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    state_dir = output_dir / "checkpoint-state"
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    archive_path = checkpoint_dir / "final-state.zip"

    write_json(
        state_dir / "checkpoint.json",
        {
            "state": "after-all-tools",
            "sequence": args.sequence,
            "purpose": "Overlay to apply to the original validation dataset after all tools have run.",
        },
    )
    if not (state_dir / "deleted-paths.json").exists():
        write_json(state_dir / "deleted-paths.json", [])

    failed_files = []
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(state_dir.rglob("*")):
            if path.is_file():
                try:
                    # Use the actual path (with long path support on Windows)
                    source_path = to_windows_long_path(path) if sys.platform == "win32" else path
                    arcname = path.relative_to(state_dir).as_posix()
                    archive.write(source_path, arcname)
                except OSError as e:
                    failed_files.append({"file": str(path), "error": str(e)})
                    print(f"Warning: Failed to add {path} to finalize archive: {e}", file=sys.stderr)
    
    if failed_files:
        print(f"Warning: {len(failed_files)} files failed to add to finalize archive", file=sys.stderr)
        for entry in failed_files:
            print(f"  - {entry['file']}: {entry['error']}", file=sys.stderr)
        raise RuntimeError(f"Final checkpoint incomplete: {len(failed_files)} files could not be archived")


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
    capture_parser.add_argument("--output-dir", required=True, help="Directory containing flat per-tool captures")
    capture_parser.add_argument(
        "--state-dir", required=True,
        help="Cumulative checkpoint-state directory used by checkpoint and finalize",
    )
    capture_parser.add_argument("--tool", required=True)
    capture_parser.add_argument("--sequence", type=int, required=True)
    capture_parser.set_defaults(function=capture)

    checkpoint_parser = subparsers.add_parser("checkpoint", help="Archive cumulative state before a tool runs")
    checkpoint_parser.add_argument("--output-dir", required=True)
    checkpoint_parser.add_argument("--tool", required=True)
    checkpoint_parser.add_argument("--sequence", type=int, required=True)
    checkpoint_parser.set_defaults(function=checkpoint)

    finalize_parser = subparsers.add_parser("finalize", help="Archive cumulative state after all tools have run")
    finalize_parser.add_argument("--output-dir", required=True)
    finalize_parser.add_argument("--sequence", type=int, required=True)
    finalize_parser.set_defaults(function=finalize)
    return parser


def main() -> int:
    enable_long_paths()
    args = build_parser().parse_args()
    args.function(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())