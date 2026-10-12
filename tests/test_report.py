import glob
import unittest
from pathlib import Path

from lgsh.scanner.model import Item, ScanResult, Status
from lgsh.scanner.report import render_text
from lgsh.scanner.scan import run_scan
from tests.helpers import FIXTURES, load_fixture


def _item(id, title, status, required=False, summary="Summary.", details=None):
    return Item(id, title, status, required, summary, details or {})


def _distro(status=Status.OK, name="Ubuntu 26.04"):
    return _item("distro", "Distro", status, False, "x", {"pretty_name": name})


def _gpu(gpus=None, status=Status.OK):
    if gpus is None:
        gpus = [{"vendor": "intel", "vendor_id": "8086", "name": "Intel Iris Xe Graphics", "driver": "i915"}]
    return _item("gpu", "Graphics card", status, False, "x", {"gpus": gpus})


def _result(*items):
    return ScanResult(list(items), "2026-10-12T00:00:00+00:00", "0.1.0")


class ReportTests(unittest.TestCase):
    def test_intel_fixture_matches_expected(self):
        r = run_scan(load_fixture("intel_ubuntu2604"))
        expected = (FIXTURES / "intel_ubuntu2604.expected.txt").read_text(encoding="utf-8")
        self.assertEqual(render_text(r), expected)

    def test_ready_fixture_renders_all_good(self):
        out = render_text(run_scan(load_fixture("amd_deb_steam_ready")))
        self.assertTrue(out.endswith("\n\nEverything needed for gaming is in place.\n"))
        self.assertIn("  Vulkan            Working (radv)\n", out)
        for h in ("Needs attention", "Required installations", "Optional", "Couldn't check"):
            self.assertNotIn(h, out)

    def test_section_order(self):
        r = _result(
            _distro(), _gpu(),
            _item("a", "Alpha", Status.OK),
            _item("b", "Bravo", Status.WARNING),
            _item("c", "Charlie", Status.MISSING, True),
            _item("d", "Delta", Status.MISSING, False),
            _item("e", "Echo", Status.UNKNOWN),
        )
        out = render_text(r)
        heads = ["Your PC", "Ready", "Needs attention", "Required installations",
                 "Optional", "Couldn't check"]
        pos = [out.index("\n" + h + "\n") if h != "Your PC" else out.index(h) for h in heads]
        self.assertEqual(pos, sorted(pos))

    def test_empty_sections_omitted(self):
        out = render_text(_result(_distro(), _gpu(), _item("a", "Alpha", Status.OK)))
        self.assertIn("Ready", out)
        for h in ["Needs attention", "Required installations", "Optional", "Couldn't check"]:
            self.assertNotIn(h, out)

    def test_not_applicable_hidden(self):
        out = render_text(_result(_distro(), _gpu(), _item("a", "Alpha", Status.NOT_APPLICABLE)))
        self.assertNotIn("Alpha", out)

    def test_required_vs_optional_split(self):
        out = render_text(_result(
            _distro(), _gpu(),
            _item("c", "Charlie", Status.MISSING, True),
            _item("d", "Delta", Status.MISSING, False)))
        req = out.index("Required installations")
        opt = out.index("\nOptional\n")
        self.assertLess(req, out.index("Charlie"))
        self.assertLess(out.index("Charlie"), opt)
        self.assertGreater(out.index("Delta"), opt)

    def test_distro_and_gpu_only_in_header_when_ok(self):
        out = render_text(_result(_distro(), _gpu()))
        self.assertNotIn("Distro", out)
        self.assertNotIn("Graphics card", out)

    def test_distro_warning_also_in_section(self):
        out = render_text(_result(_distro(Status.WARNING), _gpu()))
        self.assertIn("Needs attention\n  Distro", out)

    def test_header_formats(self):
        two = _gpu([{"name": "Intel UHD", "driver": "i915"},
                    {"name": "NVIDIA RTX 3060", "driver": None}])
        out = render_text(_result(_distro(), two))
        self.assertTrue(out.startswith(
            "Your PC\n  Ubuntu 26.04 · Intel UHD (driver: i915) + NVIDIA RTX 3060 (driver: none)\n"))
        out = render_text(_result(_distro(), _gpu([])))
        self.assertTrue(out.startswith("Your PC\n  Ubuntu 26.04\n"))
        out = render_text(_result(_item("distro", "Distro", Status.UNKNOWN, False, "x"), _gpu([])))
        self.assertTrue(out.startswith("Your PC\n  Unknown system\n"))

    def test_long_title_gets_single_space(self):
        out = render_text(_result(_distro(), _gpu(),
                                  _item("a", "A" * 18, Status.OK, summary="Fine.")))
        self.assertIn("  " + "A" * 18 + " Fine.\n", out)
        out = render_text(_result(_distro(), _gpu(), _item("a", "Short", Status.OK, summary="Fine.")))
        self.assertIn("  Short" + " " * 13 + "Fine.\n", out)

    def test_formatting_rules(self):
        names = sorted(Path(p).stem for p in glob.glob(str(FIXTURES / "*.json")))
        for name in names:
            out = render_text(run_scan(load_fixture(name)))
            with self.subTest(fixture=name):
                self.assertTrue(out.endswith("\n"))
                self.assertFalse(out.endswith("\n\n"))
                self.assertNotIn("\n\n\n", out)
                for line in out.split("\n"):
                    self.assertEqual(line, line.rstrip())

    def test_no_emoji_or_exclamation(self):
        names = sorted(Path(p).stem for p in glob.glob(str(FIXTURES / "*.json")))
        self.assertTrue(names)
        for name in names:
            out = render_text(run_scan(load_fixture(name)))
            with self.subTest(fixture=name):
                self.assertNotIn("!", out)
                for ch in out:
                    self.assertTrue(ord(ch) <= 0x2FFF or ch == "·", repr(ch))

    def test_all_ok_message(self):
        out = render_text(_result(_distro(), _gpu(), _item("a", "Alpha", Status.OK)))
        self.assertTrue(out.endswith("\n\nEverything needed for gaming is in place.\n"))
        for bad in (Status.WARNING, Status.MISSING):
            out = render_text(_result(_distro(), _gpu(), _item("a", "Alpha", bad)))
            self.assertNotIn("Everything needed", out)
        out = render_text(_result(_distro(), _gpu(), _item("a", "Alpha", Status.MISSING, True)))
        self.assertNotIn("Everything needed", out)

    def test_all_ok_message_blocked_by_required_unknown(self):
        out = render_text(_result(_distro(), _gpu(), _item("a", "Alpha", Status.UNKNOWN, True)))
        self.assertNotIn("Everything needed", out)

    def test_all_ok_message_allows_optional_unknown(self):
        out = render_text(_result(_distro(), _gpu(), _item("a", "Alpha", Status.UNKNOWN, False)))
        self.assertIn("Everything needed", out)

    def test_none_gpu_name(self):
        out = render_text(_result(_distro(), _gpu([{"name": None, "driver": "i915"}])))
        self.assertIn("Unknown GPU (driver: i915)", out)
        self.assertNotIn("None", out)


if __name__ == "__main__":
    unittest.main()
