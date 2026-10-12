"""Shared test helpers: fixture loading and snapshot building."""
from __future__ import annotations

from pathlib import Path

from lgsh.scanner.snapshot import Snapshot, load_snapshot

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Snapshot:
    return load_snapshot(FIXTURES / f"{name}.json")


def make_snapshot(commands=None, files=None, dirs=None) -> Snapshot:
    return Snapshot(dict(commands or {}), dict(files or {}), dict(dirs or {}))
