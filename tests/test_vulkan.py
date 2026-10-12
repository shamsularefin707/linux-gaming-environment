import unittest

from lgsh.scanner.checks.vulkan import check_vulkan
from lgsh.scanner.model import Status
from lgsh.scanner.runner import CommandResult, DirListing
from tests.helpers import make_snapshot

# Hand-written in the real `vulkaninfo --summary` format (not captured from a machine).
HEAD = "==========\nVULKANINFO\n==========\n\nVulkan Instance Version: 1.3.289\n\n\nDevices:\n========\n"
REAL = HEAD + """GPU0:
\tapiVersion         = 1.3.289
\tdriverVersion      = 24.2.8
\tvendorID           = 0x8086
\tdeviceID           = 0x46a6
\tdeviceType         = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU
\tdeviceName         = Intel(R) Iris(R) Xe Graphics (ADL GT2)
\tdriverID           = DRIVER_ID_INTEL_OPEN_SOURCE_MESA
\tdriverName         = Intel open-source Mesa driver
\tdriverInfo         = Mesa 24.2.8-1ubuntu1~24.04.1
\tconformanceVersion = 1.3.6.0
GPU1:
\tapiVersion         = 1.3.289
\tdriverVersion      = 0.0.1
\tvendorID           = 0x10005
\tdeviceID           = 0x0000
\tdeviceType         = PHYSICAL_DEVICE_TYPE_CPU
\tdeviceName         = llvmpipe (LLVM 19.1.1, 256 bits)
\tdriverID           = DRIVER_ID_MESA_LLVMPIPE
\tdriverName         = llvmpipe
\tdriverInfo         = Mesa 24.2.8 (LLVM 19.1.1)
\tconformanceVersion = 1.3.1.1
"""
LLVM_ONLY = HEAD + "GPU0:\n" + REAL.split("GPU1:\n")[1]
NO_TYPE = HEAD + "GPU0:\n\tdeviceName         = Mystery GPU\n\tdriverName         = mystery\n"

LSPCI_DRV = ("00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2 "
             "[8086:46a6] (rev 0c)\n\tKernel driver in use: i915\n")
LSPCI_NODRV = ("00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2 "
               "[8086:46a6] (rev 0c)\n")


def vk(stdout="", rc=0, error=None, stderr=""):
    return CommandResult(["vulkaninfo", "--summary"], None if error else rc,
                         stdout, stderr, error)


def lspci(out):
    return CommandResult(["lspci", "-nnk"], 0, out, "", None)


def d(path, entries=None, error=None):
    return DirListing(path, entries or [], error)


class VulkanTests(unittest.TestCase):
    def test_real_gpu_ok(self):
        item = check_vulkan(make_snapshot({"vulkaninfo": vk(REAL)}))
        self.assertEqual(item.id, "vulkan")
        self.assertEqual(item.title, "Vulkan")
        self.assertTrue(item.required)
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(item.summary, "Working (Intel open-source Mesa driver)")
        self.assertEqual(len(item.details["devices"]), 2)
        self.assertEqual(item.details["devices"][0],
                         {"name": "Intel(R) Iris(R) Xe Graphics (ADL GT2)",
                          "type": "PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU",
                          "driver": "Intel open-source Mesa driver"})
        self.assertIn("vulkaninfo --summary", item.evidence[0].source)

    def test_llvmpipe_only_warning(self):
        item = check_vulkan(make_snapshot({"vulkaninfo": vk(LLVM_ONLY)}))
        self.assertEqual(item.status, Status.WARNING)
        self.assertEqual(item.summary,
                         "Only the slow software renderer was found, so games won't run well.")

    def test_missing_device_type_unknown(self):
        item = check_vulkan(make_snapshot({"vulkaninfo": vk(NO_TYPE)}))
        self.assertEqual(item.status, Status.UNKNOWN)

    def test_failed_with_driver_warning(self):
        snap = make_snapshot({"vulkaninfo": vk("", rc=1, stderr="ERROR: no ICD"),
                              "lspci": lspci(LSPCI_DRV)})
        item = check_vulkan(snap)
        self.assertEqual(item.status, Status.WARNING)
        self.assertEqual(item.summary,
                         "Vulkan failed to start. The graphics driver may need a restart or reinstall.")
        self.assertTrue(item.evidence)

    def test_failed_without_driver_unknown(self):
        snap = make_snapshot({"vulkaninfo": vk("", rc=1),
                              "lspci": lspci(LSPCI_NODRV)})
        item = check_vulkan(snap)
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertIn("lspci -nnk", [e.source for e in item.evidence])
        self.assertEqual(check_vulkan(make_snapshot({"vulkaninfo": vk("", rc=1)})).status,
                         Status.UNKNOWN)

    def test_timeout_unknown(self):
        item = check_vulkan(make_snapshot({"vulkaninfo": vk(error="timeout")}))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Vulkan check timed out.")
        self.assertTrue(item.evidence)

    def test_os_error_unknown(self):
        item = check_vulkan(make_snapshot({"vulkaninfo": vk(error="os_error", stderr="boom")}))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Couldn't run vulkaninfo.")
        self.assertIn("os_error", item.evidence[0].output)
        self.assertIn("boom", item.evidence[0].output)

    def test_tool_missing_icd_present_no_capable_driver(self):
        for lspci_res in (None, lspci(LSPCI_NODRV), lspci(LSPCI_DRV.replace("i915", "vfio-pci"))):
            cmds = {"vulkaninfo": vk(error="not_found")}
            if lspci_res is not None:
                cmds["lspci"] = lspci_res
            snap = make_snapshot(cmds, dirs={
                "icd_usr": d("/usr/share/vulkan/icd.d", ["intel_icd.x86_64.json"])})
            item = check_vulkan(snap)
            self.assertEqual(item.status, Status.UNKNOWN)
            self.assertEqual(item.summary,
                             "The vulkaninfo tool isn't installed, so Vulkan couldn't be checked.")
            self.assertIn("lspci -nnk", [e.source for e in item.evidence])

    def test_tool_missing_icd_present_unknown(self):
        snap = make_snapshot(
            {"vulkaninfo": vk(error="not_found"), "lspci": lspci(LSPCI_DRV)},
            dirs={"icd_usr": d("/usr/share/vulkan/icd.d", ["intel_icd.x86_64.json", "README"])})
        item = check_vulkan(snap)
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary,
                         "The vulkaninfo tool isn't installed. Driver files are present, so Vulkan is likely fine.")
        self.assertEqual(item.details["icd_files"], ["intel_icd.x86_64.json"])
        self.assertGreaterEqual(len(item.evidence), 2)

    def test_tool_missing_no_icd_missing(self):
        snap = make_snapshot(
            {"vulkaninfo": vk(error="not_found")},
            dirs={"icd_usr": d("/usr/share/vulkan/icd.d", error="absent"),
                  "icd_etc": d("/etc/vulkan/icd.d", ["notes.txt"])})
        item = check_vulkan(snap)
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.summary, "No Vulkan driver installed. Most games need it.")
        self.assertEqual(make_snapshot({"vulkaninfo": vk(error="not_found")}).dir("icd_usr").error, "absent")
        self.assertEqual(check_vulkan(make_snapshot({"vulkaninfo": vk(error="not_found")})).status,
                         Status.MISSING)

    def test_tool_missing_listing_error_unknown(self):
        snap = make_snapshot(
            {"vulkaninfo": vk(error="not_found")},
            dirs={"icd_usr": d("/usr/share/vulkan/icd.d", error="os_error")})
        self.assertEqual(check_vulkan(snap).status, Status.UNKNOWN)

    def test_empty_output_unknown(self):
        item = check_vulkan(make_snapshot({"vulkaninfo": vk("Devices:\n========\n")}))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertTrue(item.evidence)


if __name__ == "__main__":
    unittest.main()
