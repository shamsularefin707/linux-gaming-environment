import errno
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from lgsh.scanner.runner import CommandResult, DirListing, FileRead
from lgsh.scanner.snapshot import (
    COMMANDS,
    DIRS,
    FILES,
    Snapshot,
    collect,
    load_snapshot,
    save_capture,
)
from tests.helpers import make_snapshot


class CollectTests(unittest.TestCase):
    def test_collect_calls_every_command_once(self):
        calls = []

        def run(argv, timeout):
            calls.append(list(argv))
            return CommandResult(list(argv), 0, "", "", None)

        collect(run=run, read=lambda p: FileRead(p, "", None),
                ls=lambda p: DirListing(p, [], None), home=Path("/home/test"))
        self.assertEqual(len(calls), len(COMMANDS))
        self.assertEqual({tuple(c) for c in calls},
                         {tuple(v[0]) for v in COMMANDS.values()})

    def test_collect_expands_home(self):
        seen = []

        def ls(p):
            seen.append(p)
            return DirListing(p, [], None)

        snap = collect(run=lambda a, t: CommandResult(a, 0, "", "", None),
                       read=lambda p: FileRead(p, "", None), ls=ls,
                       home=Path("/home/test"))
        self.assertIn("/home/test/.steam/root/compatibilitytools.d", seen)
        self.assertEqual(snap.dir("steam_root_compat").path,
                         "/home/test/.steam/root/compatibilitytools.d")
        self.assertEqual(set(snap.dirs), set(DIRS))
        self.assertEqual(set(snap.files), set(FILES))


class SnapshotTests(unittest.TestCase):
    def test_snapshot_roundtrip(self):
        snap = Snapshot(
            {"lspci": CommandResult(["lspci", "-nnk"], 0, "out", "", None)},
            {"os_release": FileRead("/etc/os-release", "ID=ubuntu\n", None)},
            {"icd_usr": DirListing("/usr/share/vulkan/icd.d", ["a.json"], None)},
            provenance="captured 2026-01-01",
        )
        again = Snapshot.from_dict(json.loads(json.dumps(snap.to_dict())))
        self.assertEqual(again, snap)
        self.assertEqual(snap.to_dict()["provenance"], "captured 2026-01-01")

    def test_missing_key_defaults(self):
        s = make_snapshot()
        self.assertEqual(s.cmd("lspci").error, "not_found")
        self.assertEqual(s.cmd("lspci").argv, ["lspci", "-nnk"])
        self.assertEqual(s.file("os_release").error, "absent")
        self.assertEqual(s.dir("icd_usr").error, "absent")
        self.assertEqual(s.provenance, "live")


class CaptureTests(unittest.TestCase):
    def test_save_capture_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "new" / "sub"
            snap = make_snapshot(
                files={"os_release": FileRead("/etc/os-release", "x", None)})
            path = save_capture(snap, folder)
            self.assertEqual(path, folder / "lgsh-capture.json")
            original = path.read_text()
            self.assertRegex(json.loads(original)["provenance"],
                             r"^captured \d{4}-\d{2}-\d{2}$")
            with self.assertRaises(FileExistsError):
                save_capture(make_snapshot(), folder)
            self.assertEqual(path.read_text(), original)
            self.assertEqual([p.name for p in folder.iterdir()],
                             ["lgsh-capture.json"])
            self.assertEqual(load_snapshot(path).file("os_release").content, "x")

    def test_save_capture_fallback_without_hard_links(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            snap = make_snapshot(
                files={"os_release": FileRead("/etc/os-release", "x", None)})
            with mock.patch.object(os, "link", side_effect=OSError(errno.EPERM, "no")):
                path = save_capture(snap, folder)
            self.assertEqual(load_snapshot(path).file("os_release").content, "x")
            self.assertEqual([p.name for p in folder.iterdir()],
                             ["lgsh-capture.json"])
            with mock.patch.object(os, "link", side_effect=OSError(errno.EPERM, "no")):
                with self.assertRaises(FileExistsError):
                    save_capture(snap, folder)


if __name__ == "__main__":
    unittest.main()
