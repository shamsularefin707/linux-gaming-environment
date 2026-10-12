"""System and graphics-card identification."""
from __future__ import annotations

from dataclasses import asdict

from ..model import Evidence, Item, Status
from ..snapshot import Snapshot
from ..sources import parse_gpus

_UBUNTU_MIN = (24, 4)
_MINT_MIN_MAJOR = 22


def _parse_os_release(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def _version_tuple(v: str) -> tuple[int, ...] | None:
    try:
        return tuple(int(p) for p in v.split("."))
    except ValueError:
        return None


def check_distro(s: Snapshot) -> Item:
    f = s.file("os_release")
    if f.content is None:
        return Item(
            "distro", "System", Status.UNKNOWN, False,
            "Couldn't read /etc/os-release.",
            evidence=[Evidence.of("/etc/os-release", f"unreadable: {f.error}")],
        )
    osr = _parse_os_release(f.content)
    distro_id = osr.get("ID", "")
    version = osr.get("VERSION_ID", "")
    pretty = osr.get("PRETTY_NAME") or distro_id or "Unknown system"
    details = {
        "id": distro_id,
        "version": version,
        "pretty_name": pretty,
        "ubuntu_codename": osr.get("UBUNTU_CODENAME"),
    }
    ev = [Evidence.of("/etc/os-release", f.content)]
    vt = _version_tuple(version)

    if distro_id in ("ubuntu", "linuxmint") and vt is None:
        return Item("distro", "System", Status.UNKNOWN, False,
                    f"Couldn't read the version of {pretty}.", details, ev)
    if distro_id == "ubuntu":
        if vt >= _UBUNTU_MIN:
            return Item("distro", "System", Status.OK, False, pretty, details, ev)
        return Item("distro", "System", Status.WARNING, False,
                    f"Ubuntu {version} is older than supported (24.04 or newer).",
                    details, ev)
    if distro_id == "linuxmint":
        if vt[0] >= _MINT_MIN_MAJOR:
            return Item("distro", "System", Status.OK, False, pretty, details, ev)
        return Item("distro", "System", Status.WARNING, False,
                    f"{pretty} is older than supported (Mint 22 or newer).",
                    details, ev)
    return Item("distro", "System", Status.WARNING, False,
                f"{pretty} isn't supported yet. All checks still ran.", details, ev)


def check_gpu(s: Snapshot) -> Item:
    r = s.cmd("lspci")
    ev = [Evidence.of("lspci -nnk", r.stdout if r.ok else
                      f"failed: {r.error or r.returncode}")]
    gpus = parse_gpus(r)
    if not gpus:
        return Item("gpu", "Graphics card", Status.UNKNOWN, False,
                    "Couldn't find a graphics card.", {"gpus": []}, ev)
    details = {"gpus": [asdict(g) for g in gpus]}
    if any(g.vendor != "other" for g in gpus):
        names = ", ".join(g.name for g in gpus)
        return Item("gpu", "Graphics card", Status.OK, False, names, details, ev)
    return Item("gpu", "Graphics card", Status.WARNING, False,
                "This graphics card isn't supported yet.", details, ev)
