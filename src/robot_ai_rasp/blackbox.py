from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SafetyEvent:
    timestamp: float
    event: str
    session_id: int = 0
    operation_id: int = 0
    detail: str = ""


class SafetyBlackBox:
    """Bounded in-memory black box with optional JSONL persistence."""

    def __init__(self, capacity: int = 256, persist_path: str | Path | None = None):
        self._events: deque[SafetyEvent] = deque(maxlen=capacity)
        self._persist_path = Path(persist_path) if persist_path else None

    def record(self, event: str, session_id: int = 0, operation_id: int = 0, detail: str = "") -> None:
        item = SafetyEvent(time.time(), event, session_id, operation_id, detail)
        self._events.append(item)
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            with self._persist_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    def snapshot(self) -> tuple[SafetyEvent, ...]:
        return tuple(self._events)
