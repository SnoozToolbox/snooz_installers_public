import json
import tempfile
import unittest
import zipfile
from argparse import Namespace
from pathlib import Path

import capture_validation_changes as capture


class CaptureValidationChangesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.dataset = self.root / "private-dataset"
        self.workspace = self.root / "validation-workspaces"
        self.output = self.root / "validation-outputs"
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
            "tool": "Tool One",
            "sequence": 1,
        }
        defaults.update(values)
        return Namespace(**defaults)

    def test_capture_records_created_modified_and_deleted_files(self):
        (self.dataset / "existing.tsv").write_text("modified content", encoding="utf-8")
        (self.workspace / "new.tsv").write_text("new", encoding="utf-8")
        deleted = self.dataset / "deleted.tsv"
        deleted.write_text("delete me", encoding="utf-8")
        capture.snapshot(self.args(output=str(self.manifest)))
        deleted.unlink()
        (self.dataset / "existing.tsv").write_text("modified again", encoding="utf-8")
        (self.workspace / "another.tsv").write_text("another", encoding="utf-8")

        capture.capture(self.args())

        changes_path = self.output / "tools" / "01-Tool_One" / "changes.json"
        changes = json.loads(changes_path.read_text(encoding="utf-8"))
        self.assertEqual(changes["created"], ["validation-workspaces/another.tsv"])
        self.assertEqual(changes["modified"], ["private-dataset/existing.tsv"])
        self.assertEqual(changes["deleted"], ["private-dataset/deleted.tsv"])
        self.assertTrue((self.output / "tools" / "01-Tool_One" / "changes" / "private-dataset" / "existing.tsv").is_file())
        self.assertTrue((self.output / "checkpoint-state" / "files" / "validation-workspaces" / "another.tsv").is_file())

    def test_checkpoint_contains_cumulative_overlay_and_deletions(self):
        (self.dataset / "existing.tsv").write_text("changed", encoding="utf-8")
        capture.capture(self.args())
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
        capture.capture(self.args())
        capture.finalize(self.args(sequence=1))

        archive_path = self.output / "checkpoints" / "final-state.zip"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(archive.read("files/private-dataset/existing.tsv"), b"final")
            metadata = json.loads(archive.read("checkpoint.json"))
        self.assertEqual(metadata["state"], "after-all-tools")
        self.assertEqual(metadata["sequence"], 1)


if __name__ == "__main__":
    unittest.main()