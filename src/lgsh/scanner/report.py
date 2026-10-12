"""Plain-text terminal report."""
from __future__ import annotations

from .model import Item, ScanResult, Status

_TITLE_WIDTH = 18
_ALL_GOOD = "Everything needed for gaming is in place."


def _header(result: ScanResult) -> str:
    name = "Unknown system"
    gpus: list = []
    for item in result.items:
        if item.id == "distro":
            name = item.details.get("pretty_name") or name
        elif item.id == "gpu":
            gpus = item.details.get("gpus") or []
    parts = [f"{g.get('name', 'Unknown GPU')} (driver: {g.get('driver') or 'none'})" for g in gpus]
    line = f"  {name}"
    if parts:
        line += " · " + " + ".join(parts)
    return line


def _line(item: Item) -> str:
    title = item.title
    pad = title.ljust(_TITLE_WIDTH) if len(title) < _TITLE_WIDTH else title + " "
    return f"  {pad}{item.summary}".rstrip()


def render_text(result: ScanResult) -> str:
    shown = [
        i for i in result.items
        if i.status is not Status.NOT_APPLICABLE
        and (i.id not in ("distro", "gpu") or i.status in (Status.WARNING, Status.UNKNOWN))
    ]
    sections = [
        ("Ready", lambda i: i.status is Status.OK),
        ("Needs attention", lambda i: i.status is Status.WARNING),
        ("Required installations", lambda i: i.status is Status.MISSING and i.required),
        ("Optional", lambda i: i.status is Status.MISSING and not i.required),
        ("Couldn't check", lambda i: i.status is Status.UNKNOWN),
    ]
    blocks = ["Your PC\n" + _header(result)]
    for heading, pred in sections:
        items = [i for i in shown if pred(i)]
        if items:
            blocks.append(heading + "\n" + "\n".join(_line(i) for i in items))
    if not any(i.status in (Status.WARNING, Status.MISSING) for i in result.items):
        blocks.append(_ALL_GOOD)
    return "\n\n".join(blocks) + "\n"
