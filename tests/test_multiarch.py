import unittest

from lgsh.scanner.checks.multiarch import check_multiarch
from lgsh.scanner.model import Status
from lgsh.scanner.runner import CommandResult
from tests.helpers import load_fixture, make_snapshot

LSPCI_INTEL = ("00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2 "
               "[8086:46a6] (rev 0c)\n\tKernel driver in use: i915\n")
LSPCI_NV = ("01:00.0 VGA compatible controller [0300]: NVIDIA Corporation AD104 "
            "[10de:2782] (rev a1)\n\tKernel driver in use: nvidia\n")
LSPCI_OTHER = ("00:02.0 VGA compatible controller [0300]: Matrox Electronics Systems Ltd. G200 "
               "[102b:0522]\n")


def cmd(stdout, argv=("x",), returncode=0, error=None):
    return CommandResult(list(argv), returncode, stdout, "", error)


def snap(arch="i386\n", lspci=LSPCI_INTEL, dpkg=""):
    return make_snapshot(commands={
        "foreign_arch": cmd(arch),
        "lspci": cmd(lspci),
        "dpkg": cmd(dpkg),
    })


def pk(*names):
    return "".join(f"{n}\tii \t1.0\n" for n in names)


class MultiarchTests(unittest.TestCase):
    def test_i386_off_missing(self):
        item = check_multiarch(load_fixture("intel_ubuntu2604"))
        self.assertEqual(item.id, "multiarch_32bit")
        self.assertEqual(item.title, "32-bit support")
        self.assertTrue(item.required)
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.summary, "Not enabled. Steam and many games need it.")
        self.assertIs(item.details["i386_enabled"], False)
        self.assertTrue(item.evidence)

    def test_foreign_arch_unreadable_unknown(self):
        s = make_snapshot(commands={"foreign_arch": cmd("", error="not_found", returncode=None)})
        item = check_multiarch(s)
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertIsNone(item.details["i386_enabled"])
        self.assertTrue(item.evidence)

    def test_intel_needs_mesa_i386(self):
        item = check_multiarch(snap(dpkg=pk("mesa-vulkan-drivers:amd64")))
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.summary, "Enabled, but the 32-bit graphics driver is missing "
                                       "(mesa-vulkan-drivers:i386). Games need it.")
        self.assertEqual(item.details["needed"], ["mesa-vulkan-drivers:i386"])
        self.assertEqual(item.details["missing"], ["mesa-vulkan-drivers:i386"])
        self.assertTrue(item.details["i386_enabled"])

    def test_nvidia_only_never_needs_mesa(self):
        item = check_multiarch(load_fixture("nvidia_proprietary"))
        self.assertEqual(item.status, Status.MISSING)
        self.assertIn("libnvidia-gl-560:i386", item.summary)
        self.assertNotIn("mesa-vulkan-drivers:i386", item.details["needed"])
        self.assertEqual(item.details["missing"], ["libnvidia-gl-560:i386"])

    def test_nvidia_without_driver_is_unknown(self):
        item = check_multiarch(snap(lspci=LSPCI_NV, dpkg=pk("mesa-vulkan-drivers:amd64")))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Enabled. The 32-bit NVIDIA driver can be checked "
                                       "once the NVIDIA driver is installed.")
        self.assertEqual(item.details["needed"], [])
        self.assertTrue(any("NVIDIA driver not installed yet" in n for n in item.details["notes"]))
        dpkg_ev = [e for e in item.evidence if e.source.startswith("dpkg-query")]
        self.assertEqual(dpkg_ev[0].output, "libnvidia-gl-*: not installed")

    def test_hybrid_without_nvidia_driver_mesa_present_unknown(self):
        item = check_multiarch(snap(lspci=LSPCI_INTEL + LSPCI_NV,
                                    dpkg=pk("mesa-vulkan-drivers:i386")))
        self.assertEqual(item.status, Status.UNKNOWN)

    def test_hybrid_without_nvidia_driver_mesa_missing_wins(self):
        item = check_multiarch(snap(lspci=LSPCI_INTEL + LSPCI_NV, dpkg=pk()))
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.details["missing"], ["mesa-vulkan-drivers:i386"])

    def test_nvidia_multiple_versions_each_need_i386(self):
        item = check_multiarch(snap(lspci=LSPCI_NV, dpkg=pk(
            "libnvidia-gl-550:amd64", "libnvidia-gl-560:amd64", "libnvidia-gl-550:i386")))
        self.assertEqual(item.details["needed"],
                         ["libnvidia-gl-550:i386", "libnvidia-gl-560:i386"])
        self.assertEqual(item.details["missing"], ["libnvidia-gl-560:i386"])
        self.assertEqual(item.status, Status.MISSING)

    def test_nvidia_unqualified_native_name(self):
        item = check_multiarch(snap(lspci=LSPCI_NV, dpkg=pk("libnvidia-gl-560")))
        self.assertEqual(item.details["needed"], ["libnvidia-gl-560:i386"])

    def test_hybrid_needs_both(self):
        item = check_multiarch(load_fixture("hybrid_intel_nvidia"))
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(sorted(item.details["needed"]),
                         ["libnvidia-gl-560:i386", "mesa-vulkan-drivers:i386"])
        self.assertEqual(item.details["missing"], [])

    def test_hybrid_missing_one(self):
        item = check_multiarch(snap(
            lspci=LSPCI_INTEL + LSPCI_NV,
            dpkg=pk("mesa-vulkan-drivers:i386", "libnvidia-gl-560:amd64")))
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.details["missing"], ["libnvidia-gl-560:i386"])
        self.assertEqual(sorted(item.details["needed"]),
                         ["libnvidia-gl-560:i386", "mesa-vulkan-drivers:i386"])

    def test_all_present_ok(self):
        item = check_multiarch(snap(dpkg=pk("mesa-vulkan-drivers:i386")))
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(item.summary, "Enabled")
        self.assertEqual(item.details["missing"], [])
        sources = [e.source for e in item.evidence]
        self.assertIn("dpkg --print-foreign-architectures", sources)
        self.assertTrue(any(x.startswith("dpkg-query") for x in sources))
        self.assertTrue(any(x.startswith("lspci") for x in sources))
        dpkg_ev = [e for e in item.evidence if e.source.startswith("dpkg-query")]
        self.assertEqual(dpkg_ev[0].output, "mesa-vulkan-drivers:i386: installed")
        lspci_ev = [e for e in item.evidence if e.source.startswith("lspci")]
        self.assertEqual(lspci_ev[0].output, LSPCI_INTEL.rstrip("\n"))

    def test_held_nvidia_i386_satisfies(self):
        item = check_multiarch(snap(lspci=LSPCI_NV, dpkg=(
            "libnvidia-gl-560:amd64\thi \t560\nlibnvidia-gl-560:i386\thi \t560\n")))
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(item.details["missing"], [])

    def test_half_configured_mesa_i386_warning(self):
        item = check_multiarch(snap(dpkg="mesa-vulkan-drivers:i386\tiF \t24.2\n"))
        self.assertEqual(item.status, Status.WARNING)
        self.assertEqual(item.summary, "Installed, but the package setup didn't finish. Run the software updater.")
        self.assertEqual(item.details["missing"], [])
        self.assertEqual(item.details["broken"], ["mesa-vulkan-drivers:i386"])

    def test_amd_needs_mesa_i386(self):
        item = check_multiarch(load_fixture("amd_radeon_legacy"))
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.details["needed"], ["mesa-vulkan-drivers:i386"])

    def test_other_gpu_ignored(self):
        item = check_multiarch(snap(lspci=LSPCI_OTHER, dpkg=pk()))
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(item.details["needed"], [])

    def test_dpkg_unreadable_unknown(self):
        s = make_snapshot(commands={
            "foreign_arch": cmd("i386\n"), "lspci": cmd(LSPCI_INTEL),
            "dpkg": cmd("", error="not_found", returncode=None)})
        item = check_multiarch(s)
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary,
                         "Enabled, but the 32-bit graphics drivers couldn't be checked.")
        self.assertTrue(item.details["i386_enabled"])

    def test_gpus_unreadable_unknown(self):
        for lspci in (cmd("", error="not_found", returncode=None), cmd("")):
            s = make_snapshot(commands={
                "foreign_arch": cmd("i386\n"), "lspci": lspci, "dpkg": cmd(pk())})
            item = check_multiarch(s)
            self.assertEqual(item.status, Status.UNKNOWN)
            self.assertTrue(item.evidence)


if __name__ == "__main__":
    unittest.main()
