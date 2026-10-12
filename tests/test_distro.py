import unittest

from lgsh.scanner.checks.distro import check_distro
from lgsh.scanner.runner import FileRead
from tests.helpers import load_fixture, make_snapshot


def snap(text):
    return make_snapshot(files={"os_release": FileRead("/etc/os-release", text, None)})


class DistroTests(unittest.TestCase):
    def test_distro_ubuntu_2604_ok(self):
        item = check_distro(load_fixture("intel_ubuntu2604"))
        self.assertEqual(item.status.value, "ok")
        self.assertEqual(item.summary, "Ubuntu 26.04 LTS")
        self.assertEqual(item.id, "distro")
        self.assertEqual(item.title, "System")
        self.assertFalse(item.required)
        self.assertEqual(item.details["id"], "ubuntu")
        self.assertEqual(item.details["version"], "26.04")
        self.assertEqual(item.evidence[0].source, "/etc/os-release")

    def test_distro_ubuntu_2204_warning(self):
        item = check_distro(snap('PRETTY_NAME="Ubuntu 22.04.5 LTS"\nID=ubuntu\nVERSION_ID="22.04"\n'))
        self.assertEqual(item.status.value, "warning")
        self.assertEqual(item.summary, "Ubuntu 22.04 is older than supported (24.04 or newer).")

    def test_distro_mint_22_ok(self):
        for v in ("22", "22.1"):
            item = check_distro(snap(
                f'PRETTY_NAME="Linux Mint {v}"\nID=linuxmint\nVERSION_ID="{v}"\n'
                'ID_LIKE="ubuntu debian"\nUBUNTU_CODENAME=noble\n'))
            self.assertEqual(item.status.value, "ok", v)
            self.assertEqual(item.details["ubuntu_codename"], "noble")

    def test_distro_mint_21_warning(self):
        item = check_distro(snap('PRETTY_NAME="Linux Mint 21.3"\nID=linuxmint\nVERSION_ID="21.3"\n'))
        self.assertEqual(item.status.value, "warning")

    def test_distro_popos_unsupported_warning(self):
        item = check_distro(snap(
            'PRETTY_NAME="Pop!_OS 22.04 LTS"\nID=pop\nID_LIKE="ubuntu debian"\nVERSION_ID="22.04"\n'))
        self.assertEqual(item.status.value, "warning")
        self.assertEqual(item.summary,
                         "Pop!_OS 22.04 LTS isn't supported yet. All checks still ran.")

    def test_distro_missing_file_unknown(self):
        item = check_distro(make_snapshot())
        self.assertEqual(item.status.value, "unknown")
        self.assertTrue(item.evidence)

    def test_distro_unparseable_version_is_warning_not_crash(self):
        item = check_distro(snap('PRETTY_NAME="Ubuntu"\nID=ubuntu\n'))
        self.assertIn(item.status.value, ("warning", "unknown"))


if __name__ == "__main__":
    unittest.main()
