import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lgsh.scanner.runner import (
    CommandResult,
    DirListing,
    FileRead,
    list_dir,
    read_file,
    run_command,
)


class RunCommandTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("shutil.which", side_effect=lambda name, path=None: f"/usr/bin/{name}")
        self.which = patcher.start()
        self.addCleanup(patcher.stop)

    def test_not_on_path_is_not_found_without_running(self):
        self.which.side_effect = None
        self.which.return_value = None
        with mock.patch("subprocess.run") as m:
            r = run_command(["vulkaninfo", "--summary"])
        m.assert_not_called()
        self.assertEqual(r.error, "not_found")
        self.assertEqual(r.argv, ["vulkaninfo", "--summary"])

    def test_runs_resolved_path_with_same_path_env(self):
        cp = subprocess.CompletedProcess(["x"], 0, b"", b"")
        with mock.patch.dict(os.environ, {"PATH": "/opt/x:/usr/bin"}), \
                mock.patch("subprocess.run", return_value=cp) as m:
            r = run_command(["lspci", "-nnk"])
        self.which.assert_called_once_with("lspci", path="/opt/x:/usr/bin")
        self.assertEqual(m.call_args.args[0], ["/usr/bin/lspci", "-nnk"])
        self.assertEqual(m.call_args.kwargs["env"]["PATH"], "/opt/x:/usr/bin")
        self.assertEqual(r.argv, ["lspci", "-nnk"])

    def test_allowlist_checked_before_resolving(self):
        with mock.patch("subprocess.run") as m:
            with self.assertRaises(ValueError):
                run_command(["/usr/bin/lspci"])
            m.assert_not_called()
        self.which.assert_not_called()

    def test_rejects_unlisted_program(self):
        with mock.patch("subprocess.run") as m:
            with self.assertRaises(ValueError):
                run_command(["rm", "-rf", "/tmp/x"])
            m.assert_not_called()

    def test_rejects_empty_argv(self):
        with self.assertRaises(ValueError):
            run_command([])

    def test_not_found(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            r = run_command(["lspci"])
        self.assertEqual(r.error, "not_found")
        self.assertFalse(r.ok)

    def test_timeout(self):
        exc = subprocess.TimeoutExpired(cmd=["lspci"], timeout=1)
        with mock.patch("subprocess.run", side_effect=exc):
            r = run_command(["lspci"], timeout=1)
        self.assertEqual(r.error, "timeout")
        self.assertFalse(r.ok)

    def test_os_error(self):
        with mock.patch("subprocess.run", side_effect=PermissionError()):
            r = run_command(["lspci"])
        self.assertEqual(r.error, "os_error")

    def test_runs_without_shell_and_with_c_locale(self):
        cp = subprocess.CompletedProcess(["lspci"], 0, b"out", b"")
        with mock.patch("subprocess.run", return_value=cp) as m:
            r = run_command(["lspci", "-nn"])
        kwargs = m.call_args.kwargs
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["env"]["LC_ALL"], "C")
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(m.call_args.args[0], ["/usr/bin/lspci", "-nn"])
        self.assertEqual(r.argv, ["lspci", "-nn"])
        self.assertTrue(r.ok)
        self.assertEqual(r.stdout, "out")

    def test_decodes_odd_bytes(self):
        cp = subprocess.CompletedProcess(["lspci"], 1, b"a\xffb", b"\xfe")
        with mock.patch("subprocess.run", return_value=cp):
            r = run_command(["lspci"])
        self.assertIn("a", r.stdout)
        self.assertFalse(r.ok)
        self.assertEqual(r.returncode, 1)

    def test_command_result_roundtrip(self):
        r = CommandResult(["lspci", "-nn"], 0, "o", "e", None)
        self.assertEqual(CommandResult.from_dict(r.to_dict()), r)
        r2 = CommandResult(["snap"], None, "", "", "timeout")
        self.assertEqual(CommandResult.from_dict(r2.to_dict()), r2)


class ReaderTests(unittest.TestCase):
    def test_read_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "f")
            p.write_bytes(b"hi\xff")
            fr = read_file(str(p))
            self.assertIsNone(fr.error)
            self.assertTrue(fr.content.startswith("hi"))
            self.assertEqual(read_file(str(Path(d, "nope"))).error, "absent")
            self.assertEqual(FileRead.from_dict(fr.to_dict()), fr)

    def test_read_file_directory_is_os_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(read_file(d).error, "os_error")

    def test_list_dir_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("b", "a", "c"):
                Path(d, n).touch()
            dl = list_dir(d)
            self.assertEqual(dl.entries, ["a", "b", "c"])
            self.assertIsNone(dl.error)
            self.assertEqual(DirListing.from_dict(dl.to_dict()), dl)

    def test_list_dir_absent_vs_denied(self):
        with tempfile.TemporaryDirectory() as d:
            missing = list_dir(os.path.join(d, "missing"))
            self.assertEqual(missing.error, "absent")
            self.assertIsNone(missing.entries)
            if os.geteuid() == 0:
                self.skipTest("root bypasses chmod 000")
            locked = Path(d, "locked")
            locked.mkdir()
            locked.chmod(0)
            try:
                self.assertEqual(list_dir(str(locked)).error, "os_error")
            finally:
                locked.chmod(stat.S_IRWXU)


if __name__ == "__main__":
    unittest.main()
