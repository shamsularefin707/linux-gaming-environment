import glob
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from lgsh.scanner import scan
from lgsh.scanner.model import Status
from lgsh.scanner.runner import CommandResult, DirListing, FileRead
from lgsh.scanner.snapshot import COMMANDS, DIRS, FILES, Snapshot
from tests.helpers import FIXTURES, load_fixture

IDS = ["distro", "gpu", "gpu_driver", "vulkan", "multiarch_32bit",
       "steam", "heroic", "ge_proton", "mangohud", "gamemode"]


class ScanTests(unittest.TestCase):
    def test_all_items_present_in_order(self):
        r = scan.run_scan(load_fixture("intel_ubuntu2604"))
        self.assertEqual([i.id for i in r.items], IDS)

    def test_scanned_at_and_version(self):
        now = datetime(2026, 10, 12, 8, 30, 5, 123, tzinfo=timezone.utc)
        r = scan.run_scan(load_fixture("intel_ubuntu2604"), now)
        self.assertEqual(r.scanned_at, "2026-10-12T08:30:05+00:00")
        self.assertEqual(r.schema_version, 1)

    def test_source_comes_from_snapshot_provenance(self):
        s = load_fixture("intel_ubuntu2604")
        self.assertEqual(scan.run_scan(s).to_dict()["source"], s.provenance)
        self.assertEqual(scan.run_scan(Snapshot({}, {}, {})).source, "live")

    def test_check_exception_becomes_unknown(self):
        def boom(s):
            raise ValueError("bad")
        checks = [(i, t, req, boom if i == "vulkan" else fn) for i, t, req, fn in scan.ALL_CHECKS]
        with mock.patch.object(scan, "ALL_CHECKS", checks):
            r = scan.run_scan(load_fixture("intel_ubuntu2604"))
        by = {i.id: i for i in r.items}
        self.assertEqual(len(r.items), 10)
        self.assertEqual(by["vulkan"].status, Status.UNKNOWN)
        self.assertTrue(by["vulkan"].required)
        self.assertEqual(by["vulkan"].title, "Vulkan")
        self.assertEqual(by["vulkan"].details, {"error": repr(ValueError("bad"))})
        self.assertEqual([(e.source, e.output) for e in by["vulkan"].evidence],
                         [("scanner", repr(ValueError("bad")))])
        self.assertEqual(by["distro"].status, Status.OK)
        self.assertEqual(by["steam"].status, Status.WARNING)

    def test_intel_fixture_statuses(self):
        r = scan.run_scan(load_fixture("intel_ubuntu2604"))
        got = {i.id: i.status for i in r.items}
        self.assertEqual(got, {
            "distro": Status.OK, "gpu": Status.OK, "gpu_driver": Status.OK,
            "vulkan": Status.UNKNOWN, "multiarch_32bit": Status.MISSING,
            "steam": Status.WARNING, "heroic": Status.MISSING,
            "ge_proton": Status.MISSING, "mangohud": Status.MISSING,
            "gamemode": Status.MISSING,
        })

    def test_summaries_are_plain_sentences(self):
        snaps = {Path(p).stem: load_fixture(Path(p).stem)
                 for p in glob.glob(str(FIXTURES / "*.json"))}
        for error in ("os_error", "timeout"):
            snaps[error] = Snapshot(
                {k: CommandResult(list(v[0]), None, "", "boom\nline two", error)
                 for k, v in COMMANDS.items()},
                {k: FileRead(p, None, error if error == "os_error" else "absent")
                 for k, p in FILES.items()},
                {k: DirListing(p, None, "os_error") for k, p in DIRS.items()})
        for name, s in snaps.items():
            for item in scan.run_scan(s).items:
                with self.subTest(snapshot=name, item=item.id):
                    for bad in ("_error", "not_found", "timeout", "\n"):
                        self.assertNotIn(bad, item.summary)
                    self.assertFalse(item.summary.endswith(".."))

    def test_every_item_has_evidence(self):
        names = sorted(Path(p).stem for p in glob.glob(str(FIXTURES / "*.json")))
        self.assertTrue(names)
        for name in names:
            r = scan.run_scan(load_fixture(name))
            for item in r.items:
                if item.status is not Status.NOT_APPLICABLE:
                    with self.subTest(fixture=name, item=item.id):
                        self.assertGreaterEqual(len(item.evidence), 1)


if __name__ == "__main__":
    unittest.main()
