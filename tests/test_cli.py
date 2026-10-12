import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lgsh.scanner.cli import main
from tests.helpers import FIXTURES, load_fixture

USER = lambda: 1000  # noqa: E731


def run(argv, **kw):
    out, err = io.StringIO(), io.StringIO()
    kw.setdefault("euid_fn", USER)
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv, **kw)
    return code, out.getvalue(), err.getvalue()


def fail_collect():
    raise AssertionError("collect must not be called")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.fx = str(FIXTURES / "intel_ubuntu2604.json")

    def test_refuses_root(self):
        called = []
        code, out, err = run([], euid_fn=lambda: 0, collect_fn=lambda: called.append(1))
        self.assertEqual(code, 2)
        self.assertEqual(err.strip(), "Run this as your normal user, without sudo.")
        self.assertEqual(out, "")
        self.assertEqual(called, [])

    def test_from_capture_prints_report(self):
        res = self.dir / "r.json"
        code, out, err = run(["--from-capture", self.fx, "--output", str(res)],
                             collect_fn=fail_collect)
        self.assertEqual(code, 0, err)
        self.assertIn("Required installations", out)
        self.assertEqual(json.loads(res.read_text())["schema_version"], 1)

    def test_json_flag_outputs_valid_json(self):
        code, out, _ = run(["--json", "--from-capture", self.fx, "--output", "-"],
                           collect_fn=fail_collect)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["schema_version"], 1)

    def _state(self):
        state = self.dir / "state"
        old = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = str(state)
        self.addCleanup(lambda: os.environ.pop("XDG_STATE_HOME") if old is None
                        else os.environ.__setitem__("XDG_STATE_HOME", old))
        return state / "lgsh" / "last-scan.json"

    def test_from_capture_does_not_save_by_default(self):
        default = self._state()
        code, out, err = run(["--from-capture", self.fx], collect_fn=fail_collect)
        self.assertEqual(code, 0, err)
        self.assertIn("Required installations", out)
        self.assertFalse(default.parent.parent.exists())

    def test_live_scan_saves_to_default_and_marks_source(self):
        default = self._state()
        snap = load_fixture("intel_ubuntu2604")
        snap.provenance = "live"
        code, _, err = run([], collect_fn=lambda: snap)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(default.read_text())["source"], "live")

    def test_json_source_is_capture_provenance(self):
        code, out, _ = run(["--json", "--from-capture", self.fx], collect_fn=fail_collect)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["source"], load_fixture("intel_ubuntu2604").provenance)

    def test_output_refuses_non_lgsh_file(self):
        target = self.dir / "notes.json"
        target.write_text("my notes")
        code, out, err = run(["--from-capture", self.fx, "--output", str(target)])
        self.assertEqual(code, 1)
        self.assertIn("Required installations", out)
        self.assertEqual(err.strip(),
                         f"{target} already exists and isn't an lgsh results file.")
        self.assertEqual(target.read_text(), "my notes")

    def test_output_replaces_previous_results(self):
        target = self.dir / "r.json"
        for _ in range(2):
            code, _, err = run(["--from-capture", self.fx, "--output", str(target)])
            self.assertEqual(code, 0, err)

    def test_default_path_refuses_non_lgsh_file(self):
        default = self._state()
        default.parent.mkdir(parents=True)
        default.write_text("{}")
        snap = load_fixture("intel_ubuntu2604")
        code, _, err = run([], collect_fn=lambda: snap)
        self.assertEqual(code, 1)
        self.assertEqual(err.strip(),
                         f"{default} already exists and isn't an lgsh results file.")
        self.assertEqual(default.read_text(), "{}")

    def test_output_dash_does_not_save(self):
        state = self.dir / "state"
        old = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = str(state)
        self.addCleanup(lambda: os.environ.pop("XDG_STATE_HOME") if old is None
                        else os.environ.__setitem__("XDG_STATE_HOME", old))
        code, _, _ = run(["--from-capture", self.fx, "--output", "-"])
        self.assertEqual(code, 0)
        self.assertFalse(state.exists())

    def test_save_failure_exit_code(self):
        blocker = self.dir / "blocker"
        blocker.write_text("x")
        code, out, err = run(["--from-capture", self.fx,
                              "--output", str(blocker / "sub" / "r.json")])
        self.assertEqual(code, 1)
        self.assertIn("Required installations", out)
        self.assertTrue(err.startswith("Couldn't save results:"))

    def test_capture_writes_and_refuses_existing(self):
        folder = self.dir / "cap"
        snap = load_fixture("intel_ubuntu2604")
        argv = ["--capture", str(folder), "--output", "-"]
        code, _, err = run(argv, collect_fn=lambda: snap)
        self.assertEqual(code, 0, err)
        target = folder / "lgsh-capture.json"
        self.assertTrue(target.exists())
        target.write_text("original")
        code, out, err = run(argv, collect_fn=lambda: snap)
        self.assertEqual(code, 1)
        self.assertEqual(target.read_text(), "original")
        self.assertIn(f"A capture already exists in {folder}. Choose an empty folder.", err)
        self.assertEqual(out, "")

    def test_bad_capture_file(self):
        bad = self.dir / "bad.json"
        bad.write_text("{not json")
        for path in (bad, self.dir / "missing.json"):
            code, out, err = run(["--from-capture", str(path), "--output", "-"])
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("Couldn't read the capture file:"))
            self.assertEqual(out, "")

    def test_tools_missing_fixture_no_crash(self):
        code, out, err = run(["--json", "--output", "-", "--from-capture",
                              str(FIXTURES / "tools_missing.json")])
        self.assertEqual(code, 0, err)
        items = {i["id"]: i for i in json.loads(out)["items"]}
        self.assertEqual(items["distro"]["status"], "ok")
        # Vulkan is deliberately "missing" here: vulkaninfo is not installed and
        # both ICD folders are positively absent (see test_vulkan).
        self.assertEqual(items["vulkan"]["status"], "missing")
        for key, item in items.items():
            if key not in ("distro", "vulkan"):
                self.assertIn(item["status"], ("unknown", "not_applicable"), key)


if __name__ == "__main__":
    unittest.main()
