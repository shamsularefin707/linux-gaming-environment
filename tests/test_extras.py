import unittest

from lgsh.scanner.checks.extras import check_ge_proton, check_gamemode, check_mangohud
from lgsh.scanner.model import Status
from lgsh.scanner.runner import CommandResult, DirListing
from tests.helpers import make_snapshot

SNAP_HDR = "Name    Version  Rev  Tracking  Publisher  Notes\n"
MISSING_GE = "Not installed. Extra fixes that help some games run."


def cmd(stdout="", error=None, rc=0):
    return CommandResult(["x"], None if error else rc, stdout, "", error)


def pk(*names):
    return "".join(f"{n}\tii \t1.0\n" for n in names)


def d(key, entries=(), error=None):
    return key, DirListing(f"/p/{key}", list(entries), error)


def snap(dpkg=(), flatpaks=(), dirs=(), dpkg_err=None, flatpak_err=None):
    return make_snapshot(commands={
        "dpkg": cmd(pk(*dpkg), dpkg_err),
        "snap": cmd(SNAP_HDR),
        "flatpak": cmd("".join(f"{n}\t1.0\n" for n in flatpaks), flatpak_err),
    }, dirs=dict(dirs))


class GeProtonTests(unittest.TestCase):
    def test_ge_proton_no_launchers_not_applicable(self):
        item = check_ge_proton(snap())
        self.assertEqual((item.id, item.required), ("ge_proton", False))
        self.assertEqual(item.status, Status.NOT_APPLICABLE)
        self.assertEqual(item.summary, "No game launcher installed.")

    def test_ge_proton_launchers_unreadable_unknown(self):
        item = check_ge_proton(snap(dpkg_err="os_error", flatpak_err="os_error"))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Couldn't check which game launchers are installed.")

    def test_ge_proton_steam_never_opened_missing(self):
        s = snap(dpkg=["steam-installer"], dirs=[
            d("steam_root_compat", error="absent"), d("steam_share_compat", error="absent")])
        item = check_ge_proton(s)
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.summary, MISSING_GE)
        self.assertEqual(list(item.details["per_launcher"]), ["steam"])
        self.assertTrue(item.evidence)

    def test_ge_proton_found_lists_versions(self):
        s = snap(dpkg=["steam-installer"], dirs=[
            d("steam_root_compat", ["GE-Proton10-4", "Proton 9", "GE-Proton9-20"]),
            d("steam_share_compat", ["GE-Proton9-20"])])
        item = check_ge_proton(s)
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(item.summary, "Installed (GE-Proton10-4, GE-Proton9-20)")
        self.assertEqual(item.details["per_launcher"]["steam"]["status"], "ok")
        self.assertEqual(sorted(item.details["per_launcher"]["steam"]["versions"]),
                         ["GE-Proton10-4", "GE-Proton9-20"])

    def test_ge_proton_permission_error_unknown(self):
        s = snap(dpkg=["steam-installer"], dirs=[
            d("steam_root_compat", error="os_error"), d("steam_share_compat", error="absent")])
        item = check_ge_proton(s)
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Couldn't read the GE-Proton folders.")

    def test_ge_proton_heroic_flatpak_path(self):
        s = snap(flatpaks=["com.heroicgameslauncher.hgl"], dirs=[
            d("heroic_flatpak_proton", ["GE-Proton9-27"])])
        item = check_ge_proton(s)
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(list(item.details["per_launcher"]), ["heroic"])
        self.assertEqual(item.details["per_launcher"]["heroic"]["versions"], ["GE-Proton9-27"])

    def test_ge_proton_one_launcher_ok_other_missing_is_ok(self):
        s = snap(dpkg=["steam-installer", "heroic"], dirs=[
            d("steam_root_compat", error="absent"), d("steam_share_compat", error="absent"),
            d("heroic_proton", ["GE-Proton8-1"])])
        item = check_ge_proton(s)
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(item.details["per_launcher"]["steam"]["status"], "missing")

    def test_ge_proton_one_launcher_unreadable_other_none(self):
        s = snap(dpkg=["steam-installer"], dirs=[d("steam_root_compat", [])],
                 flatpak_err="os_error")
        # steam found via deb; heroic None (flatpak unreadable) -> only steam considered
        item = check_ge_proton(s)
        self.assertEqual(item.status, Status.MISSING)


class MangoHudTests(unittest.TestCase):
    LAYER = "org.freedesktop.Platform.VulkanLayer.MangoHud"

    def test_mangohud_deb_ok(self):
        item = check_mangohud(snap(dpkg=["mangohud"]))
        self.assertEqual((item.id, item.required, item.status), ("mangohud", False, Status.OK))
        self.assertEqual(item.summary, "Installed.")
        self.assertTrue(item.evidence)

    def test_mangohud_flatpak_layer_ok(self):
        self.assertEqual(check_mangohud(snap(flatpaks=[self.LAYER])).status, Status.OK)

    def test_mangohud_missing(self):
        item = check_mangohud(snap())
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.summary, "Not installed. Shows FPS and temperatures in game.")

    def test_mangohud_dpkg_unreadable_flatpak_found_ok(self):
        self.assertEqual(check_mangohud(snap(dpkg_err="os_error", flatpaks=[self.LAYER])).status,
                         Status.OK)

    def test_mangohud_dpkg_unreadable_unknown(self):
        item = check_mangohud(snap(dpkg_err="os_error"))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "The package list couldn't be read.")

    def test_mangohud_flatpak_unreadable_unknown(self):
        self.assertEqual(check_mangohud(snap(flatpak_err="os_error")).status, Status.UNKNOWN)


class GameModeTests(unittest.TestCase):
    def test_gamemode_ok(self):
        item = check_gamemode(snap(dpkg=["gamemode"]))
        self.assertEqual((item.id, item.required, item.status), ("gamemode", False, Status.OK))
        self.assertEqual(item.summary, "Installed.")

    def test_gamemode_missing(self):
        item = check_gamemode(snap())
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.summary, "Not installed. Lets games ask for full CPU speed.")
        self.assertTrue(item.evidence)

    def test_gamemode_dpkg_unreadable_unknown(self):
        item = check_gamemode(snap(dpkg_err="os_error"))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "The package list couldn't be read.")
        self.assertTrue(item.evidence)


if __name__ == "__main__":
    unittest.main()
