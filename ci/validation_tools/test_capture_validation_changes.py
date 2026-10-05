import json
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import capture_validation_changes as capture


class CaptureValidationChangesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.dataset = self.root / "private-dataset"
        self.workspace = self.root / "validation-workspaces"
        self.output = self.root / "validation-outputs"
        self.captures = self.root / "captures"
        self.manifest = self.root / "manifest.json"
        self.dataset.mkdir()
        self.workspace.mkdir()
        (self.dataset / "existing.tsv").write_text("original", encoding="utf-8")
        capture.snapshot(self.args(output=str(self.manifest)))

    def tearDown(self):
        self.temp_dir.cleanup()

    def args(self, **values):
        defaults = {
            "root": [str(self.dataset), str(self.workspace)],
            "manifest": str(self.manifest),
            "output_dir": str(self.output),
            "state_dir": str(self.output / "checkpoint-state"),
            "tool": "Tool One",
            "sequence": 1,
        }
        defaults.update(values)
        return Namespace(**defaults)

    def capture_args(self, **values):
        return self.args(output_dir=str(self.captures), **values)

    def test_capture_records_created_modified_and_deleted_files(self):
        (self.dataset / "existing.tsv").write_text("modified content", encoding="utf-8")
        (self.workspace / "new.tsv").write_text("new", encoding="utf-8")
        deleted = self.dataset / "deleted.tsv"
        deleted.write_text("delete me", encoding="utf-8")
        capture.snapshot(self.args(output=str(self.manifest)))
        deleted.unlink()
        (self.dataset / "existing.tsv").write_text("modified again", encoding="utf-8")
        (self.workspace / "another.tsv").write_text("another", encoding="utf-8")

        capture.capture(self.capture_args())

        changes_path = self.captures / "01-Tool_One" / "changes.json"
        changes = json.loads(changes_path.read_text(encoding="utf-8"))
        self.assertEqual(changes["created"], ["validation-workspaces/another.tsv"])
        self.assertEqual(changes["modified"], ["private-dataset/existing.tsv"])
        self.assertEqual(changes["deleted"], ["private-dataset/deleted.tsv"])
        self.assertTrue((self.captures / "01-Tool_One" / "existing.tsv").is_file())
        self.assertTrue((self.output / "checkpoint-state" / "files" / "validation-workspaces" / "another.tsv").is_file())

    def test_checkpoint_contains_cumulative_overlay_and_deletions(self):
        (self.dataset / "existing.tsv").write_text("changed", encoding="utf-8")
        capture.capture(self.capture_args())
        capture.checkpoint(self.args(tool="Tool Two", sequence=2))

        archive_path = self.output / "checkpoints" / "02-Tool_Two-before.zip"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertIn("files/private-dataset/existing.tsv", archive.namelist())
            self.assertIn("deleted-paths.json", archive.namelist())
            metadata = json.loads(archive.read("checkpoint.json"))
        self.assertEqual(metadata["tool"], "Tool Two")
        self.assertEqual(metadata["sequence"], 2)

    def test_finalize_contains_state_after_last_tool(self):
        (self.dataset / "existing.tsv").write_text("final", encoding="utf-8")
        capture.capture(self.capture_args())
        capture.finalize(self.args(sequence=1))

        archive_path = self.output / "checkpoints" / "final-state.zip"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(archive.read("files/private-dataset/existing.tsv"), b"final")
            metadata = json.loads(archive.read("checkpoint.json"))
        self.assertEqual(metadata["state"], "after-all-tools")
        self.assertEqual(metadata["sequence"], 1)

    def test_flat_capture_preserves_filename_and_checkpoint_source_path(self):
        filename = "COV-015~ Covid_5250d3a3-5e68-4a00-ad3c-628b6639c9db_YASA_REMs_summary.tsv"
        source = self.workspace / "DetectREMsYASA" / "results" / filename
        source.parent.mkdir(parents=True)
        source.write_text("REM summary", encoding="utf-8")
        args = self.capture_args(tool="DetectREMsYASA", sequence=5)

        capture.capture(args)
        capture.finalize(self.args(sequence=5))

        tool_dir = self.captures / "05-DetectREMsYASA"
        self.assertEqual((tool_dir / filename).read_text(encoding="utf-8"), "REM summary")
        changes = json.loads((tool_dir / "changes.json").read_text(encoding="utf-8"))
        source_key = f"validation-workspaces/DetectREMsYASA/results/{filename}"
        self.assertEqual(changes["files"][0]["path"], source_key)
        self.assertEqual(changes["files"][0]["captured_path"], filename)
        self.assertFalse((self.output / "tools").exists())
        with zipfile.ZipFile(self.output / "checkpoints" / "final-state.zip") as archive:
            self.assertEqual(archive.read(f"files/{source_key}"), b"REM summary")

        archive_path = self.root / "assets.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in tool_dir.iterdir():
                archive.write(path, path.relative_to(self.root).as_posix())
        extraction_dir = self.root / "extracted"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertIsNone(archive.testzip())
            archive.extractall(extraction_dir)
        self.assertEqual(
            (extraction_dir / "captures" / "05-DetectREMsYASA" / filename).read_bytes(),
            source.read_bytes(),
        )
        destination = Path(r"C:\Users\klacourse\Downloads\windows-validation-assets") / "captures" / "05-DetectREMsYASA" / filename
        self.assertLess(len(str(destination)), 260)

    def test_flat_capture_disambiguates_duplicate_and_reserved_names(self):
        (self.dataset / "summary.tsv").write_text("dataset", encoding="utf-8")
        (self.workspace / "SUMMARY.tsv").write_text("workspace", encoding="utf-8")
        (self.workspace / "changes.json").write_text("source JSON", encoding="utf-8")

        capture.capture(self.capture_args())

        tool_dir = self.captures / "01-Tool_One"
        changes = json.loads((tool_dir / "changes.json").read_text(encoding="utf-8"))
        names = [record["captured_path"] for record in changes["files"]]
        self.assertEqual(len(set(name.casefold() for name in names)), 3)
        self.assertNotIn("changes.json", names)
        for record in changes["files"]:
            self.assertEqual(
                (tool_dir / record["captured_path"]).read_bytes(),
                capture.resolve_inventory_path(
                    record["path"], capture.parse_roots(self.args().root)
                ).read_bytes(),
            )
        keys = [record["path"] for record in changes["files"]]
        self.assertEqual(capture.flat_capture_names(keys), capture.flat_capture_names(keys[::-1]))

    def test_flat_capture_does_not_advance_manifest_when_copy_fails(self):
        (self.workspace / "new.tsv").write_text("new", encoding="utf-8")
        original_manifest = self.manifest.read_bytes()

        with patch.object(capture.shutil, "copy2", side_effect=OSError("copy denied")):
            with self.assertRaisesRegex(RuntimeError, "Capture failed"):
                capture.capture(self.capture_args())

        self.assertEqual(self.manifest.read_bytes(), original_manifest)
        changes = json.loads((self.captures / "01-Tool_One" / "changes.json").read_text(encoding="utf-8"))
        self.assertEqual(changes["copy_errors"], [
            {"path": "validation-workspaces/new.tsv", "error": "copy denied"}
        ])

    def test_parser_accepts_capture_and_state_directories(self):
        args = capture.build_parser().parse_args([
            "capture", "--root", str(self.workspace),
            "--manifest", str(self.manifest), "--output-dir", str(self.captures),
            "--state-dir", str(self.output / "checkpoint-state"),
            "--tool", "Tool", "--sequence", "1",
        ])
        self.assertEqual(args.output_dir, str(self.captures))
        self.assertEqual(args.state_dir, str(self.output / "checkpoint-state"))

    def test_checkpoint_write_errors_fail_explicitly(self):
        for operation in (capture.checkpoint, capture.finalize):
            with self.subTest(operation=operation.__name__):
                with patch.object(zipfile.ZipFile, "write", side_effect=OSError("read denied")):
                    with self.assertRaisesRegex(RuntimeError, "incomplete"):
                        operation(self.args())


if __name__ == "__main__":
    unittest.main()