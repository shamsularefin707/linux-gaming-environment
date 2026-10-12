"""Parsers for package and hardware sources.

None means "couldn't read"; an empty value means "read it and found nothing".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .runner import CommandResult


class PackageIndex:
    def __init__(self, packages: dict[str, str]):
        # full dpkg name (maybe with ":arch") -> version, installed only
        self._packages = packages

    @classmethod
    def from_command(cls, r: CommandResult) -> PackageIndex | None:
        if not r.ok:
            return None
        packages: dict[str, str] = {}
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2 or not parts[1].startswith("ii"):
                continue
            packages[parts[0]] = parts[2].strip() if len(parts) > 2 else ""
        return cls(packages)

    def _matches(self, name: str, arch: str | None) -> list[str]:
        if arch is not None:
            full = f"{name}:{arch}"
            return [full] if full in self._packages else []
        return [
            k for k in self._packages if k == name or k.startswith(f"{name}:")
        ]

    def installed(self, name: str, arch: str | None = None) -> bool:
        return bool(self._matches(name, arch))

    def version(self, name: str) -> str | None:
        found = self._matches(name, None)
        return self._packages[found[0]] if found else None

    def names_matching(self, prefix: str) -> list[str]:
        return sorted(k for k in self._packages if k.startswith(prefix))


def _first_column_after_header(r: CommandResult) -> set[str] | None:
    if r.error == "not_found":
        return set()  # no such tool means nothing installed through it
    if not r.ok:
        return None
    ids: set[str] = set()
    for line in r.stdout.splitlines()[1:]:
        fields = line.split()
        if fields:
            ids.add(fields[0])
    return ids


def parse_snaps(r: CommandResult) -> set[str] | None:
    return _first_column_after_header(r)


def parse_flatpaks(r: CommandResult) -> set[str] | None:
    # `flatpak list --columns=...` prints no header.
    if r.error == "not_found":
        return set()
    if not r.ok:
        return None
    ids: set[str] = set()
    for line in r.stdout.splitlines():
        fields = line.split()
        if fields:
            ids.add(fields[0])
    return ids


@dataclass
class Gpu:
    vendor: str  # "amd" | "nvidia" | "intel" | "other"
    vendor_id: str
    name: str
    driver: str | None


_VENDORS = {"1002": "amd", "10de": "nvidia", "8086": "intel"}
_GPU_LINE = re.compile(
    r"^\S+\s.*?\[(0300|0302|0380)\]: (.*) \[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]"
    r"(?: \(rev [0-9a-fA-F]+\))?\s*$"
)
_DRIVER = re.compile(r"^\s+Kernel driver in use:\s*(\S+)")


def parse_gpus(r: CommandResult) -> list[Gpu] | None:
    if not r.ok:
        return None
    blocks: list[list[str]] = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        if line[0] in " \t":
            if blocks:
                blocks[-1].append(line)
        else:
            blocks.append([line])
    gpus: list[Gpu] = []
    for block in blocks:
        m = _GPU_LINE.match(block[0])
        if not m:
            continue
        vendor_id = m.group(3).lower()
        driver = None
        for extra in block[1:]:
            d = _DRIVER.match(extra)
            if d:
                driver = d.group(1)
                break
        gpus.append(Gpu(_VENDORS.get(vendor_id, "other"), vendor_id, m.group(2), driver))
    return gpus
