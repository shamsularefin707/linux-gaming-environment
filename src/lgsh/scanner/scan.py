"""Runs every check and collects the results."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from lgsh import __version__
from lgsh.scanner.checks.distro import check_distro, check_gpu
from lgsh.scanner.checks.driver import check_gpu_driver
from lgsh.scanner.checks.extras import check_ge_proton, check_gamemode, check_mangohud
from lgsh.scanner.checks.launchers import check_heroic, check_steam
from lgsh.scanner.checks.multiarch import check_multiarch
from lgsh.scanner.checks.vulkan import check_vulkan
from lgsh.scanner.model import Evidence, Item, ScanResult, Status
from lgsh.scanner.snapshot import Snapshot

ALL_CHECKS: list[tuple[str, str, bool, Callable[[Snapshot], Item]]] = [
    ("distro", "System", False, check_distro),
    ("gpu", "Graphics card", False, check_gpu),
    ("gpu_driver", "Graphics driver", True, check_gpu_driver),
    ("vulkan", "Vulkan", True, check_vulkan),
    ("multiarch_32bit", "32-bit support", True, check_multiarch),
    ("steam", "Steam", True, check_steam),
    ("heroic", "Heroic", False, check_heroic),
    ("ge_proton", "GE-Proton", False, check_ge_proton),
    ("mangohud", "MangoHud", False, check_mangohud),
    ("gamemode", "GameMode", False, check_gamemode),
]


def run_scan(s: Snapshot, now: datetime | None = None) -> ScanResult:
    items: list[Item] = []
    for item_id, title, required, fn in ALL_CHECKS:
        try:
            items.append(fn(s))
        except Exception as exc:
            items.append(Item(
                item_id, title, Status.UNKNOWN, required,
                "The scanner hit an internal error on this check.",
                details={"error": repr(exc)},
                evidence=[Evidence.of("scanner", repr(exc))],
            ))
    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    return ScanResult(items=items, scanned_at=stamp, scanner_version=__version__)
