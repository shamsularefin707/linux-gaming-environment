import unittest

from lgsh.scanner.model import Evidence, Item, ScanResult, Status, worst


class ModelTests(unittest.TestCase):
    def test_worst_order(self):
        self.assertEqual(worst([Status.OK, Status.WARNING, Status.UNKNOWN]), Status.WARNING)
        self.assertEqual(worst([Status.OK, Status.MISSING, Status.WARNING]), Status.MISSING)
        self.assertEqual(worst([]), Status.NOT_APPLICABLE)

    def test_evidence_trims(self):
        self.assertEqual(len(Evidence.of("x", "a" * 5000).output), 2000)

    def test_item_to_dict(self):
        item = Item("steam", "Steam", Status.OK, True, "installed", evidence=[Evidence.of("cmd", "out")])
        d = item.to_dict()
        self.assertEqual(d["status"], "ok")
        self.assertEqual(list(d), ["id", "title", "status", "required", "summary", "details", "evidence"])
        self.assertEqual(d["evidence"], [{"source": "cmd", "output": "out"}])

    def test_scan_result(self):
        item = Item("a", "A", Status.OK, False, "s")
        r = ScanResult([item], "2026-01-01T00:00:00Z", "0.1.0")
        self.assertIs(r.item("a"), item)
        self.assertEqual(r.to_dict()["schema_version"], 1)
        self.assertEqual(r.to_dict()["items"][0]["id"], "a")


if __name__ == "__main__":
    unittest.main()
