from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.services.llm import LlmClient
from app.services.query_gateway import QueryGateway


EventSink = Callable[[str, dict[str, Any]], None]


@dataclass
class AgentContext:
    conn: sqlite3.Connection
    llm: LlmClient
    gateway: QueryGateway
    emit: EventSink
    next_suggestions_count: int = 3
    require_approval: bool = False
    cancel_event: threading.Event | None = None

    def cancelled(self) -> bool:
        return bool(self.cancel_event and self.cancel_event.is_set())
