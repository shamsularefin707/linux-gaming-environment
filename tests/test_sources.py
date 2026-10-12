import unittest

from lgsh.scanner.runner import CommandResult
from lgsh.scanner.sources import (
    Gpu, PackageIndex, gpu_blocks, parse_flatpaks, parse_gpus, parse_snaps,
)
from lgsh.scanner.checks.distro import check_gpu
from tests.helpers import make_snapshot


def res(stdout="", returncode=0, error=None):
    return CommandResult(["x"], returncode, stdout, "", error)


INTEL = (
    "00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT2"
    " [Iris Xe Graphics] [8086:46a6] (rev 0c)\n"
    "\tSubsystem: Lenovo Device [17aa:3a29]\n"
    "\tKernel driver in use: i915\n"
    "\tKernel modules: i915, xe\n"
)
NVIDIA = (
    "01:00.0 3D controller [0302]: NVIDIA Corporation GA107M [GeForce RTX 3050 Mobile]"
    " [10de:25a2] (rev a1)\n"
    "\tKernel driver in use: nvidia\n"
)


class PackageIndexTests(unittest.TestCase):
    def test_package_index_installed_and_arch(self):
        idx = PackageIndex.from_command(res(
            "mesa-vulkan-drivers:amd64\tii \t24.2\n"
            "mesa-vulkan-drivers:i386\tii \t24.2\n"
            "steam-installer\trc \t1.0\n"))
        self.assertTrue(idx.installed("mesa-vulkan-drivers"))
        self.assertTrue(idx.installed("mesa-vulkan-drivers", "i386"))
        self.assertFalse(idx.installed("mesa-vulkan-drivers", "arm64"))
        self.assertFalse(idx.installed("steam-installer"))
        self.assertEqual(idx.version("mesa-vulkan-drivers"), "24.2")
        self.assertIsNone(idx.version("steam-installer"))
        self.assertEqual(idx.names_matching("mesa-"),
                         ["mesa-vulkan-drivers:amd64", "mesa-vulkan-drivers:i386"])

    def test_package_index_none_on_failure(self):
        self.assertIsNone(PackageIndex.from_command(res(returncode=1)))
        self.assertIsNone(PackageIndex.from_command(res(error="not_found", returncode=None)))

    def test_package_index_empty_ok_is_empty_not_none(self):
        idx = PackageIndex.from_command(res(""))
        self.assertIsNotNone(idx)
        self.assertFalse(idx.installed("steam"))

    def test_package_index_format_drift_is_none(self):
        self.assertIsNone(PackageIndex.from_command(res("garbage without tabs\n")))

    def test_unqualified_native_package_matches_without_arch(self):
        idx = PackageIndex.from_command(res("bash\tii \t5.2\n"))
        self.assertTrue(idx.installed("bash"))
        self.assertFalse(idx.installed("bash", "amd64"))

    def test_held_and_half_configured_count_as_installed(self):
        idx = PackageIndex.from_command(res(
            "gamemode\thi \t1.8\n"
            "libnvidia-gl-560:i386\thi \t560\n"
            "mangohud\tiW \t0.7\n"
            "steam-installer\tit \t1.0\n"))
        self.assertTrue(idx.installed("gamemode"))
        self.assertTrue(idx.installed("libnvidia-gl-560", "i386"))
        self.assertTrue(idx.installed("mangohud"))
        self.assertTrue(idx.installed("steam-installer"))
        self.assertFalse(idx.broken("gamemode"))

    def test_unfinished_setup_is_broken_not_installed(self):
        idx = PackageIndex.from_command(res(
            "gamemode\tiF \t1.8\n"
            "mesa-vulkan-drivers:i386\tiU \t24.2\n"
            "heroic\tiH \t2.15\n"
            "steam\trc \t1.0\n"))
        for name, arch in (("gamemode", None), ("mesa-vulkan-drivers", "i386"),
                           ("heroic", None)):
            self.assertFalse(idx.installed(name, arch), name)
            self.assertTrue(idx.broken(name, arch), name)
        self.assertFalse(idx.broken("steam"))
        self.assertFalse(idx.broken("mesa-vulkan-drivers", "amd64"))
        self.assertEqual(idx.broken_matching("mesa-"), ["mesa-vulkan-drivers:i386"])

    def test_describe_lists_each_package_state(self):
        idx = PackageIndex.from_command(res(
            "mesa-vulkan-drivers:i386\tii \t24.2\n"
            "gamemode\tiF \t1.8\n"
            "nvidia-driver-560\tii \t560\n"))
        self.assertEqual(
            idx.describe(["mesa-vulkan-drivers:i386", "libnvidia-gl-560:i386",
                          "gamemode", "nvidia-driver-*", "foo-*"]),
            "mesa-vulkan-drivers:i386: installed; libnvidia-gl-560:i386: not installed; "
            "gamemode: installed, but setup didn't finish; "
            "nvidia-driver-560: installed; foo-*: not installed")

    def test_snap_not_found_means_none(self):
        self.assertEqual(parse_snaps(res(error="not_found", returncode=None)), set())

    def test_snap_error_is_unknown(self):
        self.assertIsNone(parse_snaps(res(returncode=1)))
        self.assertIsNone(parse_snaps(res(error="timeout", returncode=None)))

    def test_snap_list(self):
        out = ("Name  Version  Rev  Tracking  Publisher  Notes\n"
               "steam 1.0.0.81 100 latest/stable canonical** -\n")
        self.assertEqual(parse_snaps(res(out)), {"steam"})
        self.assertEqual(parse_snaps(res("")), set())

    def test_flatpak(self):
        self.assertEqual(
            parse_flatpaks(res("com.heroicgameslauncher.hgl\t2.15\norg.x.Y\t1\n")),
            {"com.heroicgameslauncher.hgl", "org.x.Y"})
        self.assertEqual(parse_flatpaks(res("")), set())
        self.assertEqual(parse_flatpaks(res(error="not_found", returncode=None)), set())
        self.assertIsNone(parse_flatpaks(res(error="timeout", returncode=None)))


class GpuTests(unittest.TestCase):
    def test_parse_gpus_intel_block(self):
        self.assertEqual(parse_gpus(res(INTEL)), [Gpu(
            "intel", "8086", "Intel Corporation Alder Lake-P GT2 [Iris Xe Graphics]",
            "i915")])

    def test_parse_gpus_hybrid(self):
        gpus = parse_gpus(res(INTEL + NVIDIA))
        self.assertEqual([g.vendor for g in gpus], ["intel", "nvidia"])
        self.assertEqual(gpus[1].driver, "nvidia")

    def test_parse_gpus_skips_other_classes_and_no_driver(self):
        out = ("00:1f.3 Audio device [0403]: Intel Corporation X [8086:1111]\n"
               "\tKernel driver in use: snd\n"
               "03:00.0 VGA compatible controller [0300]: Foo Inc Bar [abcd:0001]\n")
        gpus = parse_gpus(res(out))
        self.assertEqual(gpus, [Gpu("other", "abcd", "Foo Inc Bar", None)])

    def test_parse_gpus_failure_is_none(self):
        self.assertIsNone(parse_gpus(res(returncode=1)))

    def test_parse_gpus_empty_output_is_unknown_item(self):
        self.assertEqual(parse_gpus(res("")), [])
        s = make_snapshot(commands={"lspci": res("")})
        self.assertEqual(check_gpu(s).status.value, "unknown")
        s = make_snapshot(commands={"lspci": res(error="not_found", returncode=None)})
        self.assertEqual(check_gpu(s).status.value, "unknown")

    def test_gpu_item_evidence_is_gpu_blocks_only(self):
        audio = ("00:1f.3 Audio device [0403]: Intel Corporation X [8086:1111]\n"
                 "\tKernel driver in use: snd_hda_intel\n")
        item = check_gpu(make_snapshot(commands={"lspci": res(audio + INTEL + NVIDIA)}))
        self.assertEqual(item.evidence[0].output, (INTEL + NVIDIA).rstrip("\n"))
        self.assertEqual(gpu_blocks(res(audio)), [])
        self.assertIsNone(gpu_blocks(res(returncode=1)))

    def test_gpu_item_ok_and_other(self):
        item = check_gpu(make_snapshot(commands={"lspci": res(INTEL)}))
        self.assertEqual(item.status.value, "ok")
        self.assertEqual(item.id, "gpu")
        self.assertEqual(item.evidence[0].source, "lspci -nnk")
        self.assertEqual(item.details["gpus"][0]["driver"], "i915")
        item = check_gpu(make_snapshot(commands={"lspci": res(
            "03:00.0 VGA compatible controller [0300]: Foo Inc Bar [abcd:0001]\n")}))
        self.assertEqual(item.status.value, "warning")
        self.assertEqual(item.summary, "This graphics card isn't supported yet.")


if __name__ == "__main__":
    unittest.main()
