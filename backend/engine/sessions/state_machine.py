"""
Generic state machine base class.

Domain-specific sessions (EurydiceSession, etc.) subclass this and
define their own states and valid transitions.
"""

from __future__ import annotations

import time
from typing import Any


class StateMachine:
    """
    Base state machine with transition validation and history tracking.

    Subclasses define states as strings and provide valid_transitions as
    a set of (from_state, to_state) tuples.
    """

    def __init__(self, initial_state: str, valid_transitions: set[tuple[str, str]]) -> None:
        self.state: str = initial_state
        self._valid_transitions = valid_transitions
        self._history: list[tuple[str, str, float]] = []

    def transition(self, to: str) -> bool:
        """
        Attempt a state transition. Returns True if allowed, False if not.
        Records the attempt in history regardless.
        """
        allowed = (self.state, to) in self._valid_transitions
        self._history.append((self.state, to, time.time()))
        if allowed:
            self.state = to
        return allowed

    def force_state(self, to: str) -> None:
        """Set state unconditionally (e.g. on error recovery)."""
        self._history.append((self.state, to, time.time()))
        self.state = to

    @property
    def history(self) -> list[tuple[str, str, float]]:
        return list(self._history)
