import json
import unittest
from pathlib import Path

from lgsh.scanner.checks.driver import check_gpu_driver
from lgsh.scanner.runner import CommandResult, FileRead
from tests.helpers import load_fixture, make_snapshot


def lspci(vendor_line, driver):
    out = vendor_line + "\n\tSubsystem: Test [0000:0000]\n"
    if driver:
        out += f"\tKernel driver in use: {driver}\n"
    return CommandResult(["lspci", "-nnk"], 0, out, "", None)


NV = "01:00.0 VGA compatible controller [0300]: NVIDIA Corporation AD102 [GeForce RTX 4090] [10de:2684] (rev a1)"
AMD = "03:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Navi 21 [1002:73bf] (rev c1)"
INTEL = "00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2 [8086:46a6] (rev 0c)"
OTHER = "00:02.0 VGA compatible controller [0300]: Matrox Electronics Systems Ltd. G200eR2 [102b:0534]"


def dpkg(*names):
    out = "".join(f"{n}\tii \t1.0\n" for n in ("bash",) + names)
    return CommandResult(["dpkg-query"], 0, out, "", None)


def smi(stdout="", stderr="", rc=0, error=None):
    return CommandResult(["nvidia-smi"], None if error else rc, stdout, stderr, error)


def snap(line, driver, pkgs=None, smi_res=None, nvfile=None):
    cmds = {"lspci": lspci(line, driver)}
    if pkgs is not None:
        cmds["dpkg"] = dpkg(*pkgs)
    if smi_res is not None:
        cmds["nvidia_smi"] = smi_res
    files = {}
    if nvfile is not None:
        files["nvidia_version"] = FileRead("/proc/driver/nvidia/version", nvfile, None)
    return make_snapshot(commands=cmds, files=files)


class DriverTests(unittest.TestCase):
    def test_nvidia_working(self):
        item = check_gpu_driver(load_fixture("nvidia_proprietary"))
        self.assertEqual(item.id, "gpu_driver")
        self.assertEqual(item.title, "Graphics driver")
        self.assertTrue(item.required)
        self.assertEqual(item.status.value, "ok")
        self.assertEqual(item.summary, "Working (NVIDIA 560.35.03)")
        self.assertEqual(item.details["nvidia_version"], "560.35.03")
        self.assertEqual(len(item.details["per_gpu"]), 1)
        self.assertEqual(set(item.details["per_gpu"][0]),
                         {"name", "vendor", "driver", "status", "note"})
        self.assertEqual(item.evidence[0].source, "lspci -nnk")

    def test_nvidia_version_from_proc_when_smi_missing(self):
        nvrm = "NVRM version: NVIDIA UNIX x86_64 Kernel Module  550.54.14  Tue Feb 27 2024\n"
        item = check_gpu_driver(snap(NV, "nvidia", [], smi(error="not_found"), nvrm))
        self.assertEqual(item.summary, "Working (NVIDIA 550.54.14)")

    def test_nvidia_version_unknown(self):
        item = check_gpu_driver(snap(NV, "nvidia", [], smi(error="not_found")))
        self.assertEqual(item.status.value, "ok")
        self.assertEqual(item.summary, "Working (NVIDIA)")
        self.assertIsNone(item.details["nvidia_version"])

    def test_nvidia_not_responding(self):
        msg = "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver."
        item = check_gpu_driver(snap(NV, "nvidia", [], smi(stdout=msg, rc=9)))
        self.assertEqual(item.status.value, "warning")
        self.assertEqual(item.summary,
                         "Installed, but not responding. A restart usually fixes this.")
        self.assertTrue(any("nvidia-smi" in e.source for e in item.evidence))

    def test_nvidia_nouveau_with_package_pending(self):
        item = check_gpu_driver(load_fixture("nvidia_nouveau_pending"))
        self.assertEqual(item.status.value, "warning")
        self.assertEqual(item.summary,
                         "Installed, but not active yet. A restart is usually needed.")
        self.assertTrue(any("dpkg-query" in e.source for e in item.evidence))

    def test_nvidia_no_driver_with_package_pending(self):
        item = check_gpu_driver(snap(NV, None, ["nvidia-driver-560"]))
        self.assertEqual(item.status.value, "warning")
        self.assertIn("not active yet", item.summary)

    def test_nvidia_package_with_arch_suffix_counts(self):
        item = check_gpu_driver(snap(NV, "nouveau", ["nvidia-driver-560:amd64"]))
        self.assertIn("not active yet", item.summary)

    def test_nvidia_nouveau_no_package(self):
        item = check_gpu_driver(snap(NV, "nouveau", []))
        self.assertEqual(item.status.value, "warning")
        self.assertEqual(item.summary,
                         "Using the open-source nouveau driver, which is slow for games.")

    def test_nvidia_no_driver_no_package_missing(self):
        item = check_gpu_driver(snap(NV, None, []))
        self.assertEqual(item.status.value, "missing")
        self.assertEqual(item.summary, "No NVIDIA driver installed.")
        self.assertTrue(item.evidence)

    def test_dpkg_unreadable_nvidia_no_driver_is_unknown(self):
        s = snap(NV, None)
        s.commands["dpkg"] = CommandResult(["dpkg-query"], None, "", "", "not_found")
        item = check_gpu_driver(s)
        self.assertEqual(item.status.value, "unknown")

    def test_nvidia_unrecognised_driver_unknown(self):
        for pkgs in ([], ["nvidia-driver-560"]):
            item = check_gpu_driver(snap(NV, "vfio-pci", pkgs))
            self.assertEqual(item.status.value, "unknown")
            self.assertEqual(item.summary, "Unrecognised driver in use: vfio-pci.")

    def test_nouveau_dpkg_unreadable_is_warning(self):
        s = snap(NV, "nouveau")
        s.commands["dpkg"] = CommandResult(["dpkg-query"], None, "", "", "not_found")
        item = check_gpu_driver(s)
        self.assertEqual(item.status.value, "warning")
        self.assertIn("nouveau", item.summary)

    def test_evidence_not_duplicated_for_two_nvidia_gpus(self):
        text = lspci(NV, None).stdout + lspci(NV, None).stdout
        s = make_snapshot(commands={
            "lspci": CommandResult(["lspci", "-nnk"], 0, text, "", None),
            "dpkg": dpkg()})
        item = check_gpu_driver(s)
        self.assertEqual(len([e for e in item.evidence if "dpkg-query" in e.source]), 1)

    def test_smi_failure_evidence_kept(self):
        item = check_gpu_driver(snap(NV, "nvidia", [], smi(stderr="boom", rc=1)))
        self.assertTrue(any("nvidia-smi" in e.source for e in item.evidence))

    def test_amd_amdgpu_ok(self):
        item = check_gpu_driver(snap(AMD, "amdgpu", []))
        self.assertEqual(item.status.value, "ok")
        self.assertEqual(item.summary, "Working (amdgpu)")

    def test_amd_radeon_legacy_warning(self):
        item = check_gpu_driver(load_fixture("amd_radeon_legacy"))
        self.assertEqual(item.status.value, "warning")
        self.assertEqual(item.summary, "Using the old radeon driver. Games need amdgpu.")

    def test_intel_i915_and_xe_ok(self):
        for drv in ("i915", "xe"):
            item = check_gpu_driver(snap(INTEL, drv, []))
            self.assertEqual(item.status.value, "ok")
            self.assertEqual(item.summary, f"Working ({drv})")

    def test_amd_and_intel_no_driver_warning(self):
        for line in (AMD, INTEL):
            item = check_gpu_driver(snap(line, None, []))
            self.assertEqual(item.status.value, "warning")
            self.assertEqual(item.summary, "No driver is active for this card.")

    def test_other_vendor_not_applicable(self):
        item = check_gpu_driver(snap(OTHER, "mgag200", []))
        self.assertEqual(item.status.value, "not_applicable")
        self.assertEqual(item.details["per_gpu"][0]["status"], "not_applicable")

    def test_hybrid_both_listed(self):
        item = check_gpu_driver(load_fixture("hybrid_intel_nvidia"))
        self.assertEqual(item.status.value, "ok")
        self.assertEqual(len(item.details["per_gpu"]), 2)
        self.assertEqual(item.summary,
                         "Intel: Working (i915); NVIDIA: Working (NVIDIA 560.35.03)")

    def test_other_gpu_does_not_hide_real_problem(self):
        text = lspci(OTHER, "mgag200").stdout + lspci(AMD, "radeon").stdout
        s = make_snapshot(commands={"lspci": CommandResult(["lspci", "-nnk"], 0, text, "", None)})
        item = check_gpu_driver(s)
        self.assertEqual(item.status.value, "warning")

    def test_no_gpus_unknown(self):
        item = check_gpu_driver(make_snapshot())
        self.assertEqual(item.status.value, "unknown")
        self.assertEqual(item.details["per_gpu"], [])
        self.assertTrue(item.evidence)

    def test_fixtures_have_provenance_and_cover_later_checks(self):
        d = Path(__file__).parent / "fixtures"
        for name in ("nvidia_proprietary", "nvidia_nouveau_pending",
                     "hybrid_intel_nvidia", "amd_radeon_legacy"):
            data = json.loads((d / f"{name}.json").read_text())
            self.assertTrue(data["provenance"])
            for key in ("lspci", "dpkg", "foreign_arch", "snap", "flatpak"):
                self.assertIn(key, data["commands"])
            self.assertIn("os_release", data["files"])

    def test_proprietary_fixture_has_no_i386_gl_but_i386_enabled(self):
        s = load_fixture("nvidia_proprietary")
        self.assertIn("i386", s.cmd("foreign_arch").stdout)
        out = s.cmd("dpkg").stdout
        self.assertIn("libnvidia-gl-560:amd64", out)
        self.assertNotIn("libnvidia-gl-560:i386", out)


if __name__ == "__main__":
    unittest.main()
