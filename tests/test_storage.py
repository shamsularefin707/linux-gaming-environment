import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lgsh.scanner import storage


class StorageTests(unittest.TestCase):
    def test_results_path_xdg(self):
        p = storage.default_results_path({"XDG_STATE_HOME": "/x"}, Path("/h"))
        self.assertEqual(p, Path("/x/lgsh/last-scan.json"))

    def test_results_path_default(self):
        self.assertEqual(storage.default_results_path({}, Path("/h")),
                         Path("/h/.local/state/lgsh/last-scan.json"))
        self.assertEqual(storage.default_results_path({"XDG_STATE_HOME": ""}, Path("/h")),
                         Path("/h/.local/state/lgsh/last-scan.json"))

    def test_write_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "a" / "b" / "last-scan.json"
            data = {"name": "café", "n": [1, 2]}
            storage.write_json_atomic(path, data)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(json.loads(text), data)
            self.assertIn("café", text)
            self.assertTrue(text.endswith("\n"))
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_write_failure_leaves_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "last-scan.json"
            with mock.patch("os.replace", side_effect=OSError("boom")):
                with self.assertRaises(OSError):
                    storage.write_json_atomic(path, {"a": 1})
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(d).glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
