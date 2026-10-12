"""32-bit (i386) support check."""
from __future__ import annotations

from ..model import Evidence, Item, Status
from ..snapshot import COMMANDS, Snapshot
from ..sources import PackageIndex, parse_gpus

_ID = "multiarch_32bit"
_TITLE = "32-bit support"
_MESA = "mesa-vulkan-drivers"
_NV_PREFIX = "libnvidia-gl-"


def _src(key: str) -> str:
    return " ".join(COMMANDS[key][0])


def _cmd_evidence(s: Snapshot, key: str) -> Evidence:
    r = s.cmd(key)
    return Evidence.of(_src(key), r.stdout if r.ok else f"failed: {r.error or r.returncode}")


def _nvidia_versions(index: PackageIndex) -> list[str]:
    versions: set[str] = set()
    for full in index.names_matching(_NV_PREFIX):
        name, _, arch = full.partition(":")
        if arch == "i386":
            continue
        n = name[len(_NV_PREFIX):]
        if n:
            versions.add(n)
    return sorted(versions)


def check_multiarch(s: Snapshot) -> Item:
    fa = s.cmd("foreign_arch")
    ev = [_cmd_evidence(s, "foreign_arch")]
    details: dict = {"i386_enabled": None, "needed": [], "missing": [], "notes": []}

    if not fa.ok:
        return Item(_ID, _TITLE, Status.UNKNOWN, True,
                    "Couldn't check whether 32-bit support is enabled.", details, ev)
    enabled = "i386" in fa.stdout.split()
    details["i386_enabled"] = enabled
    if not enabled:
        return Item(_ID, _TITLE, Status.MISSING, True,
                    "Not enabled. Steam and many games need it.", details, ev)

    unknown = Item(_ID, _TITLE, Status.UNKNOWN, True,
                   "Enabled, but the 32-bit graphics drivers couldn't be checked.",
                   details, ev)
    ev.append(_cmd_evidence(s, "lspci"))
    gpus = parse_gpus(s.cmd("lspci"))
    if not gpus:  # None (unreadable) or [] (no GPU found): can't tell what to need
        return unknown
    ev.append(_cmd_evidence(s, "dpkg"))
    index = PackageIndex.from_command(s.cmd("dpkg"))
    if index is None:
        return unknown

    vendors = {g.vendor for g in gpus}
    needed: list[str] = []
    if vendors & {"amd", "intel"}:
        needed.append(f"{_MESA}:i386")
    if "nvidia" in vendors:
        versions = _nvidia_versions(index)
        if not versions:
            details["notes"].append("NVIDIA driver not installed yet")
        needed.extend(f"{_NV_PREFIX}{v}:i386" for v in versions)

    missing = []
    for pkg in needed:
        name, _, arch = pkg.partition(":")
        if not index.installed(name, arch):
            missing.append(pkg)
    details["needed"] = needed
    details["missing"] = missing
    if missing:
        return Item(_ID, _TITLE, Status.MISSING, True,
                    f"Enabled, but the 32-bit graphics driver is missing ({', '.join(missing)}).",
                    details, ev)
    return Item(_ID, _TITLE, Status.OK, True, "Enabled", details, ev)
