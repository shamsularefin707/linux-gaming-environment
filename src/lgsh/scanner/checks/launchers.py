"""Steam and Heroic launcher checks.

steam_installs / heroic_installs are reused by the Proton-GE check.
"""
from __future__ import annotations

from ..model import Evidence, Item, Status
from ..snapshot import Snapshot
from ..sources import PackageIndex, parse_flatpaks, parse_snaps
from .common import BROKEN, dpkg_evidence
from .common import argv as _argv, failure as _failure

STEAM_DEBS = ("steam-installer", "steam-launcher", "steam")
STEAM_SNAP = "steam"
STEAM_FLATPAK = "com.valvesoftware.Steam"
HEROIC_DEB = "heroic"
HEROIC_FLATPAK = "com.heroicgameslauncher.hgl"


def _detect(s: Snapshot, deb_names, snap_name, flatpak_name):
    """Return (installs, any_source_unreadable, evidence)."""
    installs: list[str] = []
    unreadable = False
    ev: list[Evidence] = []

    index = PackageIndex.from_command(s.cmd("dpkg"))
    if index is None:
        unreadable = True
    elif any(index.installed(n) for n in deb_names):
        installs.append("deb")
    ev.append(dpkg_evidence(s, index, list(deb_names)))

    if snap_name is not None:
        snaps = parse_snaps(s.cmd("snap"))
        if snaps is None:
            unreadable = True
            ev.append(Evidence.of(_argv("snap"), _failure(s, "snap")))
        else:
            if snap_name in snaps:
                installs.append("snap")
            if s.cmd("snap").error == "not_found":
                text = "not installed (no snaps)"
            else:
                text = f"snap {snap_name} installed" if snap_name in snaps \
                    else f"snap {snap_name} not installed"
            ev.append(Evidence.of(_argv("snap"), text))

    flatpaks = parse_flatpaks(s.cmd("flatpak"))
    if flatpaks is None:
        unreadable = True
        ev.append(Evidence.of(_argv("flatpak"), _failure(s, "flatpak")))
    else:
        if flatpak_name in flatpaks:
            installs.append("flatpak")
        if s.cmd("flatpak").error == "not_found":
            text = "not installed (no flatpaks)"
        else:
            text = f"{flatpak_name} installed" if flatpak_name in flatpaks \
                else f"{flatpak_name} not installed"
        ev.append(Evidence.of(_argv("flatpak"), text))

    return installs, unreadable, ev


def steam_installs(s: Snapshot) -> list[str] | None:
    installs, unreadable, _ = _detect(s, STEAM_DEBS, STEAM_SNAP, STEAM_FLATPAK)
    if installs:
        return installs
    return None if unreadable else []


def heroic_installs(s: Snapshot) -> list[str] | None:
    installs, unreadable, _ = _detect(s, (HEROIC_DEB,), None, HEROIC_FLATPAK)
    if installs:
        return installs
    return None if unreadable else []


def _deb_broken(s: Snapshot, deb_names) -> bool:
    index = PackageIndex.from_command(s.cmd("dpkg"))
    return index is not None and any(index.broken(n) for n in deb_names)


def check_steam(s: Snapshot) -> Item:
    installs, unreadable, ev = _detect(s, STEAM_DEBS, STEAM_SNAP, STEAM_FLATPAK)
    details = {"installs": installs}

    def item(status: Status, summary: str) -> Item:
        return Item("steam", "Steam", status, True, summary, details, ev)

    if "deb" in installs:
        also = " and ".join(k for k, v in (("a Snap", "snap"), ("a Flatpak", "flatpak"))
                            if v in installs)
        return item(Status.OK, f"Installed (also as {also})" if also else "Installed")
    if _deb_broken(s, STEAM_DEBS):
        return item(Status.WARNING, BROKEN)
    if installs and PackageIndex.from_command(s.cmd("dpkg")) is None:
        kind = "a Snap" if "snap" in installs else "a Flatpak"
        return item(Status.UNKNOWN, f"Found Steam as {kind}, "
                                    "but couldn't check for the regular version.")
    if "snap" in installs:
        return item(Status.WARNING, "Installed as a Snap, which often breaks games. "
                                    "The regular version is recommended.")
    if "flatpak" in installs:
        return item(Status.WARNING, "Installed as a Flatpak, which can break some games. "
                                    "The regular version is recommended.")
    if unreadable:
        return item(Status.UNKNOWN, "Couldn't check whether Steam is installed.")
    return item(Status.MISSING, "Not installed. The main store and launcher for most games.")


def check_heroic(s: Snapshot) -> Item:
    installs, unreadable, ev = _detect(s, (HEROIC_DEB,), None, HEROIC_FLATPAK)
    details = {"installs": installs}

    def item(status: Status, summary: str) -> Item:
        return Item("heroic", "Heroic", status, False, summary, details, ev)

    if installs:
        return item(Status.OK, "Installed")
    if _deb_broken(s, (HEROIC_DEB,)):
        return item(Status.WARNING, BROKEN)

    cfg = s.dir("heroic_config")
    if cfg.error is None:
        ev.append(Evidence.of(cfg.path, "folder exists"))
        if unreadable:
            return item(Status.UNKNOWN,
                        "Heroic settings found, but the package list couldn't be read.")
        return item(Status.UNKNOWN, "Heroic settings found, but no installed package. "
                                    "It may be an AppImage, which this check can't see.")
    if cfg.error == "absent":
        ev.append(Evidence.of(cfg.path, "folder absent"))
    else:
        ev.append(Evidence.of(cfg.path, f"unreadable: {cfg.error}"))
    if unreadable:
        return item(Status.UNKNOWN, "Couldn't check whether Heroic is installed.")
    if cfg.error == "absent":
        return item(Status.MISSING, "Not installed. Plays your Epic and GOG games.")
    return item(Status.UNKNOWN, "Couldn't check for Heroic settings.")
