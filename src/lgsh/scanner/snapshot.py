"""Raw command/file/folder results. Every check is a pure function over this."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .runner import (
    CommandResult,
    DirListing,
    FileRead,
    list_dir,
    read_file,
    run_command,
)

COMMANDS: dict[str, tuple[list[str], float]] = {
    "lspci": (["lspci", "-nnk"], 10),
    "vulkaninfo": (["vulkaninfo", "--summary"], 20),
    "foreign_arch": (["dpkg", "--print-foreign-architectures"], 10),
    "dpkg": (
        ["dpkg-query", "-W", "-f=${binary:Package}\t${db:Status-Abbrev}\t${Version}\n"],
        20,
    ),
    "snap": (["snap", "list"], 10),
    "flatpak": (["flatpak", "list", "--columns=application,version"], 10),
    "nvidia_smi": (
        ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
        10,
    ),
}

FILES: dict[str, str] = {
    "os_release": "/etc/os-release",
    "nvidia_version": "/proc/driver/nvidia/version",
}

# "~" is expanded only at collect time so saved fixtures stay portable.
DIRS: dict[str, str] = {
    "icd_usr": "/usr/share/vulkan/icd.d",
    "icd_etc": "/etc/vulkan/icd.d",
    "steam_root_compat": "~/.steam/root/compatibilitytools.d",
    "steam_share_compat": "~/.local/share/Steam/compatibilitytools.d",
    "steam_flatpak_compat": "~/.var/app/com.valvesoftware.Steam/data/Steam/compatibilitytools.d",
    "steam_snap_compat": "~/snap/steam/common/.local/share/Steam/compatibilitytools.d",
    "heroic_proton": "~/.config/heroic/tools/proton",
    "heroic_flatpak_proton": "~/.var/app/com.heroicgameslauncher.hgl/config/heroic/tools/proton",
    "heroic_config": "~/.config/heroic",
}

CAPTURE_NAME = "lgsh-capture.json"


@dataclass
class Snapshot:
    commands: dict[str, CommandResult]
    files: dict[str, FileRead]
    dirs: dict[str, DirListing]
    provenance: str = "live"

    def cmd(self, key: str) -> CommandResult:
        r = self.commands.get(key)
        if r is not None:
            return r
        return CommandResult(
            argv=list(COMMANDS[key][0]), returncode=None, stdout="", stderr="",
            error="not_found",
        )

    def file(self, key: str) -> FileRead:
        r = self.files.get(key)
        return r if r is not None else FileRead(FILES[key], None, "absent")

    def dir(self, key: str) -> DirListing:
        r = self.dirs.get(key)
        return r if r is not None else DirListing(DIRS[key], None, "absent")

    def to_dict(self) -> dict:
        return {
            "provenance": self.provenance,
            "commands": {k: v.to_dict() for k, v in self.commands.items()},
            "files": {k: v.to_dict() for k, v in self.files.items()},
            "dirs": {k: v.to_dict() for k, v in self.dirs.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> Snapshot:
        return cls(
            {k: CommandResult.from_dict(v) for k, v in d.get("commands", {}).items()},
            {k: FileRead.from_dict(v) for k, v in d.get("files", {}).items()},
            {k: DirListing.from_dict(v) for k, v in d.get("dirs", {}).items()},
            d.get("provenance", "live"),
        )


def collect(
    run=run_command, read=read_file, ls=list_dir, home: Path | None = None
) -> Snapshot:
    home = home if home is not None else Path.home()
    commands = {k: run(list(argv), timeout) for k, (argv, timeout) in COMMANDS.items()}
    files = {k: read(p) for k, p in FILES.items()}
    dirs = {}
    for k, p in DIRS.items():
        if p.startswith("~/"):
            p = str(home / p[2:])
        dirs[k] = ls(p)
    return Snapshot(commands, files, dirs)


def save_capture(snapshot: Snapshot, folder: Path) -> Path:
    folder = Path(folder)
    target = folder / CAPTURE_NAME
    if target.exists():
        raise FileExistsError(str(target))
    folder.mkdir(parents=True, exist_ok=True)
    provenance = snapshot.provenance
    if provenance == "live":
        provenance = f"captured {date.today().isoformat()}"
    data = Snapshot(snapshot.commands, snapshot.files, snapshot.dirs, provenance).to_dict()
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".lgsh-capture-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        # os.link fails with FileExistsError if target appeared meanwhile, so a
        # race can never overwrite an existing capture (os.replace would).
        try:
            os.link(tmp, target)
        except FileExistsError:
            raise
        except OSError:
            # Hard links unsupported (e.g. FAT/exFAT): exclusive create instead.
            with open(target, "x", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
    return target


def load_snapshot(path: Path) -> Snapshot:
    with open(path, encoding="utf-8") as f:
        return Snapshot.from_dict(json.load(f))
