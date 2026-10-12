"""Shared wording and evidence helpers for the checks."""
from __future__ import annotations

from ..model import Evidence
from ..snapshot import COMMANDS, Snapshot
from ..sources import PackageIndex, gpu_blocks

BROKEN = "Installed, but the package setup didn't finish. Run the software updater."


def argv(key: str) -> str:
    return " ".join(COMMANDS[key][0])


def failure(s: Snapshot, key: str) -> str:
    r = s.cmd(key)
    return f"failed: {r.error or r.returncode}"


def dpkg_evidence(s: Snapshot, index: PackageIndex | None, names: list[str]) -> Evidence:
    """The state of each package consulted, not the whole package list."""
    if index is None:
        return Evidence.of(argv("dpkg"), failure(s, "dpkg"))
    return Evidence.of(argv("dpkg"), index.describe(names))


def lspci_evidence(s: Snapshot) -> Evidence:
    """Only the graphics-card blocks of `lspci -nnk`."""
    r = s.cmd("lspci")
    blocks = gpu_blocks(r)
    if blocks is None:
        return Evidence.of(argv("lspci"), f"failed: {r.error or r.returncode}")
    return Evidence.of(argv("lspci"), "\n".join(blocks) if blocks
                       else "no graphics cards listed")
