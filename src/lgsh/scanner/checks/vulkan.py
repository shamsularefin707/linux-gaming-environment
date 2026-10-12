"""Vulkan check: can games talk to the graphics card through Vulkan?"""
from __future__ import annotations

import re

from ..model import Evidence, Item, Status
from ..snapshot import COMMANDS, Snapshot
from ..sources import parse_gpus

_CPU = "PHYSICAL_DEVICE_TYPE_CPU"
_GPU_HEADER = re.compile(r"^\s*GPU\d+\s*:\s*$")
_KV = re.compile(r"^\s*(\w+)\s*=\s*(.*?)\s*$")
_ICD_DIRS = (("icd_usr", "/usr/share/vulkan/icd.d"), ("icd_etc", "/etc/vulkan/icd.d"))


def _parse_devices(text: str) -> list[dict]:
    devices: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        if _GPU_HEADER.match(line):
            cur = {}
            devices.append(cur)
            continue
        if cur is None:
            continue
        m = _KV.match(line)
        if m:
            cur[m.group(1)] = m.group(2)
        elif line.strip() and not line[0].isspace():
            cur = None  # a new unindented section ends the block
    return [{"name": d.get("deviceName"), "type": d.get("deviceType"),
             "driver": d.get("driverName")}
            for d in devices if d.get("deviceName") or d.get("deviceType")]


def _icd_evidence(s: Snapshot, ev: list[Evidence]) -> list[str]:
    files: list[str] = []
    for key, default in _ICD_DIRS:
        d = s.dir(key)
        names = sorted(e for e in (d.entries or []) if e.endswith(".json"))
        files += names
        shown = ", ".join(names) if names else (
            f"unreadable: {d.error}" if d.error == "os_error"
            else "absent" if d.error == "absent" else "no .json files")
        ev.append(Evidence.of(d.path or default, shown))
    return files


def check_vulkan(s: Snapshot) -> Item:
    r = s.cmd("vulkaninfo")
    source = " ".join(COMMANDS["vulkaninfo"][0])
    title = "Vulkan"
    ev: list[Evidence] = []
    if r.error != "not_found":
        ev.append(Evidence.of(source, r.stdout if r.ok else
                              f"failed: {r.error or r.returncode} {r.stderr}".strip()))
    details: dict = {"devices": [], "icd_files": []}

    def item(status: Status, summary: str) -> Item:
        return Item("vulkan", title, status, True, summary, details, ev)

    if r.error in ("timeout", "os_error"):
        return item(Status.UNKNOWN, "Vulkan check timed out." if r.error == "timeout"
                    else f"Couldn't run the Vulkan check: {r.stderr.strip() or r.error}.")

    if r.error is None and r.returncode == 0:
        devices = _parse_devices(r.stdout)
        details["devices"] = devices
        if not devices:
            return item(Status.UNKNOWN, "Vulkan ran but listed no graphics devices.")
        real = [d for d in devices if d["type"] and d["type"] != _CPU]
        if real:
            drivers = list(dict.fromkeys(d["driver"] for d in real if d["driver"]))
            return item(Status.OK, f"Working ({', '.join(drivers)})" if drivers else "Working")
        if any(d["type"] == _CPU for d in devices):
            return item(Status.WARNING,
                        "Only the slow software renderer was found, so games won't run well.")
        return item(Status.UNKNOWN, "Vulkan listed devices but not what kind they are.")

    if r.error is None:  # ran and failed
        lspci = s.cmd("lspci")
        gpus = parse_gpus(lspci) or []
        ev.append(Evidence.of("lspci -nnk", lspci.stdout if lspci.ok else
                              f"failed: {lspci.error or lspci.returncode}"))
        if any(g.driver is not None for g in gpus):
            return item(Status.WARNING,
                        "Vulkan failed to start. The graphics driver may need a restart or reinstall.")
        return item(Status.UNKNOWN, "Vulkan failed to run, and no graphics driver is active.")

    # not_found
    files = _icd_evidence(s, ev)
    details["icd_files"] = files
    if files:
        return item(Status.UNKNOWN,
                    "The vulkaninfo tool isn't installed. Driver files are present, so Vulkan is likely fine.")
    if any(s.dir(k).error == "os_error" for k, _ in _ICD_DIRS):
        return item(Status.UNKNOWN, "Couldn't read the Vulkan driver folders.")
    return item(Status.MISSING, "No Vulkan driver installed.")
