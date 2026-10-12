"""Graphics driver check: is the right driver loaded for each graphics card?"""
from __future__ import annotations

import re

from ..model import Evidence, Item, Status, worst
from ..snapshot import COMMANDS, Snapshot
from ..sources import Gpu, PackageIndex, parse_gpus

_SHORT = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "other": "Other"}
_NVRM = re.compile(r"NVRM version:.*Kernel Module\s+(\d+(?:\.\d+)+)")
_PKG_PREFIX = "nvidia-driver-"


def _add_ev(ev: list[Evidence], source: str, text: str) -> None:
    if not any(e.source == source for e in ev):
        ev.append(Evidence.of(source, text))


def _nvidia_version(s: Snapshot, ev: list[Evidence]) -> str | None:
    smi = s.cmd("nvidia_smi")
    if smi.error != "not_found":
        _add_ev(ev, " ".join(COMMANDS["nvidia_smi"][0]),
                smi.stdout if smi.ok else
                f"failed: {smi.error or smi.returncode} {smi.stderr}".strip())
    if smi.ok:
        lines = smi.stdout.strip().splitlines()
        if lines and lines[0].strip():
            return lines[0].strip()
    f = s.file("nvidia_version")
    if f.content is not None:
        _add_ev(ev, "/proc/driver/nvidia/version", f.content)
        m = _NVRM.search(f.content)
        if m:
            return m.group(1)
    return None


def _smi_not_responding(s: Snapshot) -> bool:
    smi = s.cmd("nvidia_smi")
    return "couldn't communicate" in (smi.stdout + smi.stderr).lower()


def _nvidia(gpu: Gpu, s: Snapshot, index: PackageIndex | None,
            ev: list[Evidence], version: list) -> tuple[Status, str]:
    if gpu.driver == "nvidia":
        if _smi_not_responding(s):
            _add_ev(ev, " ".join(COMMANDS["nvidia_smi"][0]),
                    (s.cmd("nvidia_smi").stdout + s.cmd("nvidia_smi").stderr).strip())
            return (Status.WARNING,
                    "Installed, but not responding. A restart usually fixes this.")
        if not version:
            version.append(_nvidia_version(s, ev))
        v = version[0]
        return Status.OK, f"Working (NVIDIA {v})" if v else "Working (NVIDIA)"

    if gpu.driver not in (None, "nouveau"):
        return Status.UNKNOWN, f"Unrecognised driver in use: {gpu.driver}."
    # nouveau or no driver in use
    pkgs = [n.split(":")[0] for n in index.names_matching(_PKG_PREFIX)] if index else []
    if index is not None:
        _add_ev(ev, " ".join(COMMANDS["dpkg"][0]),
            f"packages starting {_PKG_PREFIX}: " + (", ".join(pkgs) or "none"))
    if pkgs:
        return (Status.WARNING,
                "Installed, but not active yet. A restart is usually needed.")
    if gpu.driver == "nouveau":
        return (Status.WARNING,
                "Using the open-source nouveau driver, which is slow for games.")
    if index is None:
        return Status.UNKNOWN, "Couldn't check whether an NVIDIA driver is installed."
    return Status.MISSING, "No NVIDIA driver installed."


def _per_gpu(gpu: Gpu, s: Snapshot, index: PackageIndex | None,
             ev: list[Evidence], version: list) -> tuple[Status, str]:
    if gpu.vendor == "nvidia":
        return _nvidia(gpu, s, index, ev, version)
    if gpu.vendor == "amd":
        if gpu.driver == "amdgpu":
            return Status.OK, "Working (amdgpu)"
        if gpu.driver == "radeon":
            return Status.WARNING, "Using the old radeon driver. Games need amdgpu."
    elif gpu.vendor == "intel":
        if gpu.driver in ("i915", "xe"):
            return Status.OK, f"Working ({gpu.driver})"
    else:
        return Status.NOT_APPLICABLE, "Not checked for this card."
    if gpu.driver is None:
        return Status.WARNING, "No driver is active for this card."
    return Status.UNKNOWN, f"Unrecognised driver in use: {gpu.driver}."


def check_gpu_driver(s: Snapshot) -> Item:
    r = s.cmd("lspci")
    ev = [Evidence.of("lspci -nnk", r.stdout if r.ok else
                      f"failed: {r.error or r.returncode}")]
    title = "Graphics driver"
    gpus = parse_gpus(r)
    if not gpus:
        return Item("gpu_driver", title, Status.UNKNOWN, True,
                    "Couldn't find a graphics card to check.",
                    {"per_gpu": [], "nvidia_version": None}, ev)

    index = PackageIndex.from_command(s.cmd("dpkg"))
    version: list = []
    per_gpu: list[dict] = []
    results: list[tuple[Gpu, Status, str]] = []
    for g in gpus:
        status, note = _per_gpu(g, s, index, ev, version)
        results.append((g, status, note))
        per_gpu.append({"name": g.name, "vendor": g.vendor, "driver": g.driver,
                        "status": status.value, "note": note})

    overall = worst([st for _, st, _ in results])
    if len(results) == 1:
        summary = results[0][2]
    else:
        considered = [(g, n) for g, st, n in results
                      if st is not Status.NOT_APPLICABLE] or \
                     [(g, n) for g, _, n in results]
        summary = "; ".join(f"{_SHORT[g.vendor]}: {n}" for g, n in considered)
    details = {"per_gpu": per_gpu, "nvidia_version": version[0] if version else None}
    return Item("gpu_driver", title, overall, True, summary, details, ev)
