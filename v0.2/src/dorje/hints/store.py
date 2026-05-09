"""Corpus-local hint storage.

Hints are lightweight user guidance records stored in the folder being worked on:

    .dorje/hints.jsonl

They are intentionally simple: multiple active hints, append/rewrite JSONL, and a
small todo-like CLI surface. Hints are not skills; they are corpus-local user
intent that the runtime should respect when planning/indexing/searching.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import orjson

HintStatus = Literal["active", "deleted"]


@dataclass(frozen=True)
class Hint:
    id: int
    text: str
    status: HintStatus
    created_at: str
    updated_at: str
    source: str = "user"

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "Hint":
        status = value.get("status", "active")
        if status not in ("active", "deleted"):
            status = "active"
        return cls(
            id=int(value["id"]),
            text=str(value["text"]),
            status=status,
            created_at=str(value["created_at"]),
            updated_at=str(value["updated_at"]),
            source=str(value.get("source", "user")),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source": self.source,
        }


class HintStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path.cwd()).resolve()
        self.dorje_dir = self.root / ".dorje"
        self.path = self.dorje_dir / "hints.jsonl"

    def list(self, include_deleted: bool = False) -> list[Hint]:
        if not self.path.exists():
            return []
        hints: list[Hint] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            hint = Hint.from_json(orjson.loads(line))
            if include_deleted or hint.status != "deleted":
                hints.append(hint)
        return hints

    def active(self) -> list[Hint]:
        return self.list(include_deleted=False)

    def add(self, text: str, source: str = "user") -> Hint:
        clean = text.strip()
        if not clean:
            raise ValueError("hint text must not be empty")
        hints = self.list(include_deleted=True)
        next_id = max((hint.id for hint in hints), default=0) + 1
        now = _now()
        hint = Hint(id=next_id, text=clean, status="active", created_at=now, updated_at=now, source=source)
        self._write([*hints, hint])
        return hint

    def get(self, hint_id: int, include_deleted: bool = False) -> Hint:
        for hint in self.list(include_deleted=include_deleted):
            if hint.id == hint_id:
                return hint
        raise KeyError(f"unknown hint id: {hint_id}")

    def delete(self, hint_id: int) -> Hint:
        hints = self.list(include_deleted=True)
        now = _now()
        updated: list[Hint] = []
        deleted: Hint | None = None
        for hint in hints:
            if hint.id == hint_id:
                deleted = Hint(
                    id=hint.id,
                    text=hint.text,
                    status="deleted",
                    created_at=hint.created_at,
                    updated_at=now,
                    source=hint.source,
                )
                updated.append(deleted)
            else:
                updated.append(hint)
        if deleted is None:
            raise KeyError(f"unknown hint id: {hint_id}")
        self._write(updated)
        return deleted

    def clear(self) -> int:
        hints = self.list(include_deleted=True)
        now = _now()
        changed = 0
        updated: list[Hint] = []
        for hint in hints:
            if hint.status == "active":
                changed += 1
                updated.append(
                    Hint(
                        id=hint.id,
                        text=hint.text,
                        status="deleted",
                        created_at=hint.created_at,
                        updated_at=now,
                        source=hint.source,
                    )
                )
            else:
                updated.append(hint)
        self._write(updated)
        return changed

    def _write(self, hints: list[Hint]) -> None:
        self.dorje_dir.mkdir(parents=True, exist_ok=True)
        data = b"".join(orjson.dumps(hint.to_json(), option=orjson.OPT_APPEND_NEWLINE) for hint in hints)
        self.path.write_bytes(data)


def format_active_hints(hints: list[Hint]) -> str:
    if not hints:
        return ""
    lines = ["# Corpus-local active hints", "", "Respect these user hints for this folder/corpus:", ""]
    for hint in hints:
        lines.append(f"- [{hint.id}] {hint.text}")
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(UTC).isoformat()
