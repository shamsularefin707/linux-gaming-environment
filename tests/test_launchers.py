import unittest

from lgsh.scanner.checks.launchers import (
    check_heroic, check_steam, heroic_installs, steam_installs)
from lgsh.scanner.model import Status
from lgsh.scanner.runner import CommandResult, DirListing
from tests.helpers import load_fixture, make_snapshot

SNAP_HDR = "Name    Version  Rev  Tracking  Publisher  Notes\n"


def cmd(stdout="", error=None, rc=0):
    return CommandResult(["x"], None if error else rc, stdout, "", error)


def pk(*names):
    return "".join(f"{n}\tii \t1.0\n" for n in names)


def snap(dpkg=(), snaps=(), flatpaks=(), config=None, dpkg_err=None,
         snap_err=None, flatpak_err=None):
    dirs = {}
    if config is not None:
        dirs["heroic_config"] = config
    return make_snapshot(commands={
        "dpkg": cmd(pk(*dpkg), dpkg_err),
        "snap": cmd(SNAP_HDR + "".join(f"{n} 1 1 latest/stable x -\n" for n in snaps),
                    snap_err),
        "flatpak": cmd("".join(f"{n}\t1.0\n" for n in flatpaks), flatpak_err),
    }, dirs=dirs)


class SteamTests(unittest.TestCase):
    def test_steam_deb_ok(self):
        item = check_steam(snap(dpkg=["steam-installer:i386"]))
        self.assertEqual((item.id, item.required), ("steam", True))
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(item.details["installs"], ["deb"])
        self.assertEqual(item.evidence[0].source.split()[0], "dpkg-query")
        self.assertEqual(item.evidence[0].output,
                         "steam-installer: installed; steam-launcher: not installed; "
                         "steam: not installed")

    def test_steam_deb_and_snap_ok_lists_both(self):
        s = snap(dpkg=["steam-launcher"], snaps=["steam"])
        self.assertEqual(check_steam(s).status, Status.OK)
        self.assertEqual(check_steam(s).details["installs"], ["deb", "snap"])
        self.assertEqual(steam_installs(s), ["deb", "snap"])

    def test_steam_snap_only_warning(self):
        item = check_steam(load_fixture("amd_snap_steam"))
        self.assertEqual(item.status, Status.WARNING)
        self.assertEqual(item.summary, "Installed as a Snap, which often breaks games. "
                                       "The regular version is recommended.")
        self.assertEqual(item.details["installs"], ["snap"])

    def test_steam_flatpak_only_warning(self):
        item = check_steam(load_fixture("mint22_flatpak_steam"))
        self.assertEqual(item.status, Status.WARNING)
        self.assertEqual(item.summary,
                         "Installed as a Flatpak. The regular version is recommended.")
        self.assertEqual(item.details["installs"], ["flatpak"])
        self.assertTrue(any("not installed (no snaps)" in e.output for e in item.evidence))

    def test_steam_snap_and_flatpak_uses_snap_message(self):
        item = check_steam(snap(snaps=["steam"], flatpaks=["com.valvesoftware.Steam"]))
        self.assertEqual(item.status, Status.WARNING)
        self.assertIn("Snap", item.summary)
        self.assertEqual(item.details["installs"], ["snap", "flatpak"])

    def test_steam_none_missing(self):
        item = check_steam(snap())
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.summary, "Not installed. The main store and launcher for most games.")
        self.assertEqual(item.details["installs"], [])
        self.assertEqual(steam_installs(snap()), [])
        self.assertTrue(item.evidence)

    def test_steam_flatpak_tool_failed_unknown(self):
        s = snap(flatpak_err="timeout")
        self.assertEqual(check_steam(s).status, Status.UNKNOWN)
        self.assertIsNone(steam_installs(s))
        self.assertEqual(check_steam(s).details["installs"], [])

    def test_steam_dpkg_failed_unknown_but_found_is_kept(self):
        self.assertEqual(check_steam(snap(dpkg_err="os_error")).status, Status.UNKNOWN)
        s = snap(dpkg_err="os_error", snaps=["steam"])
        self.assertEqual(steam_installs(s), ["snap"])

    def test_steam_snap_with_dpkg_unreadable_unknown(self):
        item = check_steam(snap(dpkg_err="os_error", snaps=["steam"]))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Found Steam as a Snap, "
                                       "but couldn't check for the regular version.")
        self.assertEqual(item.details["installs"], ["snap"])
        item = check_steam(snap(dpkg_err="os_error", flatpaks=["com.valvesoftware.Steam"]))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Found Steam as a Flatpak, "
                                       "but couldn't check for the regular version.")


BROKEN = "Installed, but the package setup didn't finish. Run the software updater."


def raw_dpkg(text, **kw):
    s = snap(**kw)
    s.commands["dpkg"] = cmd(text)
    return s


class HeldAndBrokenTests(unittest.TestCase):
    def test_held_steam_ok(self):
        self.assertEqual(check_steam(raw_dpkg("steam-installer\thi \t1.0\n")).status,
                         Status.OK)

    def test_half_installed_steam_warning(self):
        item = check_steam(raw_dpkg("steam-installer\tiF \t1.0\n"))
        self.assertEqual(item.status, Status.WARNING)
        self.assertEqual(item.summary, BROKEN)

    def test_half_installed_heroic_warning(self):
        cfg = DirListing("~/.config/heroic", None, "absent")
        item = check_heroic(raw_dpkg("heroic\tiH \t2.15\n", config=cfg))
        self.assertEqual(item.status, Status.WARNING)
        self.assertEqual(item.summary, BROKEN)


class HeroicTests(unittest.TestCase):
    def test_heroic_flatpak_ok(self):
        item = check_heroic(load_fixture("amd_snap_steam"))
        self.assertEqual((item.id, item.required), ("heroic", False))
        self.assertEqual(item.status, Status.OK)
        self.assertEqual(item.details["installs"], ["flatpak"])
        self.assertEqual(heroic_installs(load_fixture("amd_snap_steam")), ["flatpak"])

    def test_heroic_deb_ok(self):
        self.assertEqual(heroic_installs(snap(dpkg=["heroic"])), ["deb"])

    def test_heroic_appimage_config_unknown(self):
        cfg = DirListing("~/.config/heroic", [], None)
        item = check_heroic(snap(config=cfg))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Heroic settings found, but no installed package. "
                                       "It may be an AppImage, which this check can't see.")

    def test_heroic_none_missing(self):
        cfg = DirListing("~/.config/heroic", None, "absent")
        item = check_heroic(snap(config=cfg))
        self.assertEqual(item.status, Status.MISSING)
        self.assertEqual(item.summary, "Not installed. Plays your Epic and GOG games.")
        self.assertTrue(item.evidence)
        self.assertEqual(check_heroic(load_fixture("mint22_flatpak_steam")).status,
                         Status.MISSING)

    def test_heroic_package_and_config_ok_wins(self):
        cfg = DirListing("~/.config/heroic", ["config.json"], None)
        item = check_heroic(snap(dpkg=["heroic"], config=cfg))
        self.assertEqual(item.status, Status.OK)

    def test_heroic_dpkg_unreadable_nothing_found_unknown(self):
        cfg = DirListing("~/.config/heroic", None, "absent")
        s = snap(dpkg_err="os_error", config=cfg)
        self.assertEqual(check_heroic(s).status, Status.UNKNOWN)
        self.assertIsNone(heroic_installs(s))

    def test_heroic_config_os_error_unknown(self):
        cfg = DirListing("~/.config/heroic", None, "os_error")
        item = check_heroic(snap(config=cfg))
        self.assertEqual(item.status, Status.UNKNOWN)
        self.assertEqual(item.summary, "Couldn't check for Heroic settings.")

    def test_heroic_flatpak_failed_unknown(self):
        cfg = DirListing("~/.config/heroic", None, "absent")
        s = snap(config=cfg, flatpak_err="timeout")
        self.assertEqual(check_heroic(s).status, Status.UNKNOWN)
        self.assertIsNone(heroic_installs(s))


if __name__ == "__main__":
    unittest.main()
