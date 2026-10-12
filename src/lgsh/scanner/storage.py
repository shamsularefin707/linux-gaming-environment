"""Results file location and atomic writing."""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path


def default_results_path(env: Mapping[str, str] = os.environ, home: Path | None = None) -> Path:
    state = env.get("XDG_STATE_HOME")
    base = Path(state) if state else (home if home is not None else Path.home()) / ".local" / "state"
    return base / "lgsh" / "last-scan.json"


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
