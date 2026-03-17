"""
Generic session manager: typed in-memory store for session objects.

Domain modules provide a factory to create their specific session type.
"""

from __future__ import annotations

from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class SessionManager(Generic[T]):
    """In-memory session store keyed by session_id."""

    def __init__(self) -> None:
        self._sessions: dict[str, T] = {}

    def create(self, session_id: str, factory: Callable[[str], T]) -> T:
        session = factory(session_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> T | None:
        return self._sessions.get(session_id)

    def drop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def all_ids(self) -> list[str]:
        return list(self._sessions.keys())
