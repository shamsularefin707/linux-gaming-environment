"""The only place the scanner touches the system. Read-only by construction."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

ALLOWED_PROGRAMS = frozenset(
    {"lspci", "vulkaninfo", "dpkg-query", "dpkg", "snap", "flatpak", "nvidia-smi"}
)


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    error: str | None  # None, "not_found", "timeout", "os_error"

    @property
    def ok(self) -> bool:
        return self.error is None and self.returncode == 0

    def to_dict(self) -> dict:
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CommandResult:
        return cls(
            list(d["argv"]), d["returncode"], d["stdout"], d["stderr"], d["error"]
        )


@dataclass
class FileRead:
    path: str
    content: str | None
    error: str | None  # None, "absent", "os_error"

    def to_dict(self) -> dict:
        return {"path": self.path, "content": self.content, "error": self.error}

    @classmethod
    def from_dict(cls, d: dict) -> FileRead:
        return cls(d["path"], d["content"], d["error"])


@dataclass
class DirListing:
    path: str
    entries: list[str] | None
    error: str | None  # None, "absent", "os_error"

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "entries": None if self.entries is None else list(self.entries),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DirListing:
        entries = d["entries"]
        return cls(d["path"], None if entries is None else list(entries), d["error"])


def _text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    return data.decode("utf-8", errors="replace")


def run_command(argv: list[str], timeout: float = 10.0) -> CommandResult:
    if not argv or argv[0] not in ALLOWED_PROGRAMS:
        raise ValueError(f"program not allowed: {argv[0] if argv else None!r}")
    argv = list(argv)
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    # Resolve on the same PATH the program would run with, then run that exact
    # file. argv keeps the bare name so evidence and fixtures stay stable.
    program = shutil.which(argv[0], path=env.get("PATH"))
    if program is None:
        return CommandResult(argv, None, "", "", "not_found")
    try:
        cp = subprocess.run(
            [program, *argv[1:]],
            shell=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        return CommandResult(argv, None, "", "", "not_found")
    except subprocess.TimeoutExpired as e:
        return CommandResult(argv, None, _text(e.stdout), _text(e.stderr), "timeout")
    except OSError:
        return CommandResult(argv, None, "", "", "os_error")
    return CommandResult(argv, cp.returncode, _text(cp.stdout), _text(cp.stderr), None)


def read_file(path: str) -> FileRead:
    try:
        with open(path, "rb") as f:
            return FileRead(path, _text(f.read()), None)
    except FileNotFoundError:
        return FileRead(path, None, "absent")
    except OSError:
        return FileRead(path, None, "os_error")


def list_dir(path: str) -> DirListing:
    try:
        return DirListing(path, sorted(os.listdir(path)), None)
    except FileNotFoundError:
        return DirListing(path, None, "absent")
    except OSError:
        return DirListing(path, None, "os_error")
