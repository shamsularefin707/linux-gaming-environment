"""Parsers for package and hardware sources.

None means "couldn't read"; an empty value means "read it and found nothing".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .runner import CommandResult


# Second character of dpkg's db:Status-Abbrev (the current state).
_INSTALLED_STATES = frozenset("iWt")  # installed / triggers awaited / pending
_BROKEN_STATES = frozenset("UFH")  # unpacked / half-configured / half-installed


class PackageIndex:
    def __init__(self, packages: dict[str, str], broken: dict[str, str] | None = None):
        # full dpkg name (maybe with ":arch") -> version
        self._packages = packages  # installed (held packages included)
        self._broken = broken or {}  # present, but setup didn't finish

    @classmethod
    def from_command(cls, r: CommandResult) -> PackageIndex | None:
        if not r.ok:
            return None
        packages: dict[str, str] = {}
        broken: dict[str, str] = {}
        rows = 0
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            rows += 1
            state = parts[1][1:2]
            version = parts[2].strip() if len(parts) > 2 else ""
            if state in _INSTALLED_STATES:
                packages[parts[0]] = version
            elif state in _BROKEN_STATES:
                broken[parts[0]] = version
        if rows == 0 and r.stdout.strip():
            return None  # output present but unrecognisable: couldn't read it
        return cls(packages, broken)

    @staticmethod
    def _find(table: dict[str, str], name: str, arch: str | None) -> list[str]:
        if arch is not None:
            full = f"{name}:{arch}"
            return [full] if full in table else []
        return [k for k in table if k == name or k.startswith(f"{name}:")]

    def _matches(self, name: str, arch: str | None) -> list[str]:
        return self._find(self._packages, name, arch)

    def installed(self, name: str, arch: str | None = None) -> bool:
        """Pass arch only for a foreign architecture such as i386; for native
        packages call installed(name)."""
        return bool(self._matches(name, arch))

    def broken(self, name: str, arch: str | None = None) -> bool:
        """Present but not installed: its setup didn't finish (dpkg state
        unpacked, half-configured or half-installed)."""
        return bool(self._find(self._broken, name, arch))

    def version(self, name: str) -> str | None:
        found = self._matches(name, None)
        return self._packages[found[0]] if found else None

    def names_matching(self, prefix: str) -> list[str]:
        return sorted(k for k in self._packages if k.startswith(prefix))

    def broken_matching(self, prefix: str) -> list[str]:
        return sorted(k for k in self._broken if k.startswith(prefix))

    def _state(self, name: str, arch: str | None) -> str:
        if self.installed(name, arch):
            return "installed"
        if self.broken(name, arch):
            return "installed, but setup didn't finish"
        return "not installed"

    def describe(self, names: list[str]) -> str:
        """Evidence text: the state of each consulted package. "name:arch"
        means that architecture; a trailing "*" lists every match."""
        parts: list[str] = []
        for full in names:
            if full.endswith("*"):
                prefix = full[:-1]
                found = sorted(set(self.names_matching(prefix))
                               | set(self.broken_matching(prefix)))
                if not found:
                    parts.append(f"{full}: not installed")
                for f in found:
                    name, _, arch = f.partition(":")
                    parts.append(f"{f}: {self._state(name, arch or None)}")
                continue
            name, _, arch = full.partition(":")
            parts.append(f"{full}: {self._state(name, arch or None)}")
        return "; ".join(parts)


def _first_column(r: CommandResult, skip_header: bool) -> set[str] | None:
    if r.error == "not_found":
        return set()  # no such tool means nothing installed through it
    if not r.ok:
        return None
    lines = r.stdout.splitlines()
    if skip_header:
        lines = lines[1:]
    return {line.split()[0] for line in lines if line.split()}


def parse_snaps(r: CommandResult) -> set[str] | None:
    return _first_column(r, skip_header=True)


def parse_flatpaks(r: CommandResult) -> set[str] | None:
    # `flatpak list --columns=...` prints no header.
    return _first_column(r, skip_header=False)


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


def _gpu_block_lines(r: CommandResult) -> list[list[str]] | None:
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
    return [b for b in blocks if _GPU_LINE.match(b[0])]


def gpu_blocks(r: CommandResult) -> list[str] | None:
    """The text of each graphics-card block of `lspci -nnk`."""
    blocks = _gpu_block_lines(r)
    return None if blocks is None else ["\n".join(b) for b in blocks]


def parse_gpus(r: CommandResult) -> list[Gpu] | None:
    blocks = _gpu_block_lines(r)
    if blocks is None:
        return None
    gpus: list[Gpu] = []
    for block in blocks:
        m = _GPU_LINE.match(block[0])
        vendor_id = m.group(3).lower()
        driver = None
        for extra in block[1:]:
            d = _DRIVER.match(extra)
            if d:
                driver = d.group(1)
                break
        gpus.append(Gpu(_VENDORS.get(vendor_id, "other"), vendor_id, m.group(2), driver))
    return gpus
