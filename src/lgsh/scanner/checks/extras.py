"""GE-Proton, MangoHud and GameMode checks (all optional)."""
from __future__ import annotations

from ..model import Evidence, Item, Status
from ..snapshot import Snapshot
from ..sources import PackageIndex, parse_flatpaks, parse_snaps
from .common import BROKEN, dpkg_evidence
from .common import argv as _argv, failure as _failure
from .launchers import heroic_installs, steam_installs

MANGOHUD_LAYER = "org.freedesktop.Platform.VulkanLayer.MangoHud"

# launcher -> install type -> snapshot folder keys
GE_FOLDERS = {
    "steam": {
        "deb": ("steam_root_compat", "steam_share_compat"),
        "flatpak": ("steam_flatpak_compat",),
        "snap": ("steam_snap_compat",),
    },
    "heroic": {
        "deb": ("heroic_proton",),
        "flatpak": ("heroic_flatpak_proton",),
    },
}



def _launcher(s: Snapshot, name: str, installs: list[str], ev: list[Evidence]) -> dict:
    keys: list[str] = []
    for kind in installs:
        for k in GE_FOLDERS[name].get(kind, ()):
            if k not in keys:
                keys.append(k)
    versions: set[str] = set()
    errored = False
    for k in keys:
        listing = s.dir(k)
        if listing.error == "absent":
            ev.append(Evidence.of(listing.path, "folder absent"))
        elif listing.error is not None:
            errored = True
            ev.append(Evidence.of(listing.path, f"unreadable: {listing.error}"))
        else:
            ge = [e for e in listing.entries if e.startswith("GE-Proton")]
            versions.update(ge)
            ev.append(Evidence.of(listing.path, "GE-Proton: " + ", ".join(sorted(ge))
                                  if ge else "no GE-Proton folders"))
    if versions:
        status = Status.OK
    elif errored:
        status = Status.UNKNOWN
    else:
        status = Status.MISSING
    return {"versions": sorted(versions), "status": status}


def check_ge_proton(s: Snapshot) -> Item:
    def item(status, summary, details=None, ev=None):
        return Item("ge_proton", "GE-Proton", status, False, summary,
                    details or {}, ev or [])

    steam, heroic = steam_installs(s), heroic_installs(s)
    if steam == [] and heroic == []:
        return item(Status.NOT_APPLICABLE, "No game launcher installed.")

    def launchers_unknown(extra=None, details=None):
        ev = list(extra or [])
        failed = _failed_sources(s, [n for n, v in (("steam", steam), ("heroic", heroic))
                                     if v != []])
        ev += [Evidence.of(_argv(k), _failure(s, k)) for k in failed]
        if not ev:
            ev = [Evidence.of(_argv("dpkg"), "launcher lists could not be read")]
        return item(Status.UNKNOWN, "Couldn't check which game launchers are installed.",
                    details, ev)

    if not steam and not heroic:
        return launchers_unknown()

    ev: list[Evidence] = []
    results: dict[str, dict] = {}
    for name, installs in (("steam", steam), ("heroic", heroic)):
        if installs:
            results[name] = _launcher(s, name, installs, ev)
    details = {"per_launcher": {n: {"versions": r["versions"], "status": r["status"].value}
                                for n, r in results.items()}}
    statuses = [r["status"] for r in results.values()]
    if Status.OK in statuses:
        versions = sorted({v for r in results.values() for v in r["versions"]})
        return item(Status.OK, f"Installed ({', '.join(versions)})", details, ev)
    if steam is None or heroic is None:
        return launchers_unknown(ev, details)
    if Status.UNKNOWN in statuses:
        return item(Status.UNKNOWN, "Couldn't read the GE-Proton folders.", details, ev)
    failed = _failed_sources(s, list(results))
    if failed:
        ev += [Evidence.of(_argv(k), _failure(s, k)) for k in failed]
        return item(Status.UNKNOWN,
                    "Couldn't check every place GE-Proton could be installed.", details, ev)
    return item(Status.MISSING, "Not installed. Extra fixes that help some games run.",
                details, ev)


def _failed_sources(s: Snapshot, launchers) -> list[str]:
    failed = []
    if PackageIndex.from_command(s.cmd("dpkg")) is None:
        failed.append("dpkg")
    if "steam" in launchers and parse_snaps(s.cmd("snap")) is None:
        failed.append("snap")
    if parse_flatpaks(s.cmd("flatpak")) is None:
        failed.append("flatpak")
    return failed


def check_mangohud(s: Snapshot) -> Item:
    ev: list[Evidence] = []

    def item(status, summary):
        return Item("mangohud", "MangoHud", status, False, summary, {}, ev)

    index = PackageIndex.from_command(s.cmd("dpkg"))
    deb = index is not None and index.installed("mangohud")
    ev.append(dpkg_evidence(s, index, ["mangohud"]))
    flatpaks = parse_flatpaks(s.cmd("flatpak"))
    layer = False
    if flatpaks is None:
        ev.append(Evidence.of(_argv("flatpak"), _failure(s, "flatpak")))
    else:
        layer = MANGOHUD_LAYER in flatpaks
        if s.cmd("flatpak").error == "not_found":
            text = "not installed (no flatpaks)"
        else:
            text = f"{MANGOHUD_LAYER} " + ("installed" if layer else "not installed")
        ev.append(Evidence.of(_argv("flatpak"), text))

    if deb or layer:
        return item(Status.OK, "Installed.")
    if index is not None and index.broken("mangohud"):
        return item(Status.WARNING, BROKEN)
    if index is None or flatpaks is None:
        return item(Status.UNKNOWN, "The package list couldn't be read.")
    return item(Status.MISSING, "Not installed. Shows FPS and temperatures in game.")


def check_gamemode(s: Snapshot) -> Item:
    index = PackageIndex.from_command(s.cmd("dpkg"))

    def item(status, summary):
        return Item("gamemode", "GameMode", status, False, summary, {},
                    [dpkg_evidence(s, index, ["gamemode"])])

    if index is None:
        return item(Status.UNKNOWN, "The package list couldn't be read.")
    if index.installed("gamemode"):
        return item(Status.OK, "Installed.")
    if index.broken("gamemode"):
        return item(Status.WARNING, BROKEN)
    return item(Status.MISSING, "Not installed. Lets games ask for full CPU speed.")
