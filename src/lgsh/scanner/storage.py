"""Results file location and atomic writing."""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path


_MAX_RESULTS_BYTES = 16 * 1024 * 1024


class NotResultsFile(Exception):
    """The target exists and isn't an lgsh results file, so it is never replaced."""


def default_results_path(env: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    state = env.get("XDG_STATE_HOME")
    # The XDG spec says relative paths are invalid and must be ignored.
    if state and os.path.isabs(state):
        base = Path(state)
    else:
        base = (home if home is not None else Path.home()) / ".local" / "state"
    return base / "lgsh" / "last-scan.json"


def _is_results_file(path: Path) -> bool:
    """True when path holds an lgsh results file. Raises OSError if it can't
    be read (other than not being a regular file)."""
    if path.is_symlink() and not path.exists():
        return False  # dangling link: never replace something we can't see
    if not path.is_file():
        return False
    with open(path, "rb") as f:
        raw = f.read(_MAX_RESULTS_BYTES + 1)
    if len(raw) > _MAX_RESULTS_BYTES:
        return False
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    return isinstance(data, dict) and "schema_version" in data and "scanner_version" in data


def write_results(path: Path, data: dict) -> None:
    """Write the results file, but never replace a file that isn't one."""
    path = Path(path)
    if os.path.lexists(path) and not _is_results_file(path):
        raise NotResultsFile(str(path))
    write_json_atomic(path, data)


def write_json_atomic(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False,
            prefix=".last-scan-", suffix=".tmp",
        ) as tmp:
            tmp_name = tmp.name
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
        raise
