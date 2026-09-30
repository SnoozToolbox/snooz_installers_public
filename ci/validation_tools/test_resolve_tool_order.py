import json
import tempfile
import unittest
from pathlib import Path

from resolve_tool_order import resolve_tools


class ResolveToolOrderTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.adaptations = self.root / "adaptations.json"
        self.order = self.root / "order.json"
        self.adaptations.write_text(
            json.dumps({"ToolB": {"updates": [1]}, "ToolA": {"updates": [1]}}),
            encoding="utf-8",
        )
        self.order.write_text(json.dumps(["ToolB", "ToolA"]), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_returns_explicit_order(self):
        self.assertEqual(resolve_tools(self.adaptations, self.order), ["ToolB", "ToolA"])

    def test_requested_subset_keeps_explicit_order(self):
        self.assertEqual(resolve_tools(self.adaptations, self.order, "ToolA,ToolB"), ["ToolB", "ToolA"])

    def test_rejects_configured_tool_missing_from_order(self):
        self.order.write_text(json.dumps(["ToolA"]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "ToolB"):
            resolve_tools(self.adaptations, self.order)


if __name__ == "__main__":
    unittest.main()