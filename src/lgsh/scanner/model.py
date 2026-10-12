from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterable

EVIDENCE_LIMIT = 2000


class Status(StrEnum):
    OK = "ok"
    WARNING = "warning"
    MISSING = "missing"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


_SEVERITY = {
    Status.MISSING: 4,
    Status.WARNING: 3,
    Status.UNKNOWN: 2,
    Status.OK: 1,
    Status.NOT_APPLICABLE: 0,
}


def worst(statuses: Iterable[Status]) -> Status:
    return max(statuses, key=_SEVERITY.__getitem__, default=Status.NOT_APPLICABLE)


@dataclass
class Evidence:
    source: str
    output: str

    @classmethod
    def of(cls, source: str, text: str) -> Evidence:
        return cls(source, text[:EVIDENCE_LIMIT])

    def to_dict(self) -> dict:
        return {"source": self.source, "output": self.output}


@dataclass
class Item:
    id: str
    title: str
    status: Status
    required: bool
    summary: str
    details: dict = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "required": self.required,
            "summary": self.summary,
            "details": self.details,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class ScanResult:
    items: list[Item]
    scanned_at: str
    scanner_version: str
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "scanner_version": self.scanner_version,
            "scanned_at": self.scanned_at,
            "items": [i.to_dict() for i in self.items],
        }

    def item(self, id: str) -> Item:
        for i in self.items:
            if i.id == id:
                return i
        raise KeyError(id)
