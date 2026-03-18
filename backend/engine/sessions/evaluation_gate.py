"""
Generic evaluation gate: N consecutive passes meeting configurable thresholds.

Domain-specific mastery gates configure this with their own score dimensions
and threshold values.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateAttempt:
    """Record of a single attempt against the gate."""
    attempt_number: int
    scores: dict[str, float]
    confidence: float
    passed: bool
    timestamp: float = field(default_factory=time.time)


@dataclass
class GateCheckResult:
    """Result of checking an attempt against the gate."""
    passed_this_attempt: bool
    consecutive_passes: int
    passes_needed: int
    gate_passed: bool  # all consecutive passes met
    attempt: GateAttempt
    gate_detail: dict[str, Any]


class EvaluationGate:
    """
    Generic gate: requires N consecutive passes where each scored dimension
    meets its threshold and confidence exceeds the confidence gate.
    """

    def __init__(
        self,
        thresholds: dict[str, float],
        consecutive_required: int = 3,
        confidence_gate: float = 0.70,
    ) -> None:
        self.thresholds = dict(thresholds)
        self.consecutive_required = consecutive_required
        self.confidence_gate = confidence_gate
        self.attempts: list[GateAttempt] = []
        self.consecutive_passes: int = 0
        self.gate_passed: bool = False

    def record_attempt(self, scores: dict[str, float], confidence: float) -> GateCheckResult:
        """
        Record an attempt with arbitrary score dimensions.
        Returns a GateCheckResult describing whether the attempt passed.
        """
        # Check all thresholds
        passed = confidence >= self.confidence_gate
        gate_detail: dict[str, Any] = {
            "confidence": {
                "score": confidence,
                "threshold": self.confidence_gate,
                "ok": confidence >= self.confidence_gate,
            },
        }
        for dim, threshold in self.thresholds.items():
            score = scores.get(dim, 0.0)
            dim_ok = score >= threshold
            passed = passed and dim_ok
            gate_detail[dim] = {
                "score": score,
                "threshold": threshold,
                "ok": dim_ok,
            }

        attempt = GateAttempt(
            attempt_number=len(self.attempts) + 1,
            scores=dict(scores),
            confidence=confidence,
            passed=passed,
        )
        self.attempts.append(attempt)

        if passed:
            self.consecutive_passes += 1
        else:
            self.consecutive_passes = 0

        if self.consecutive_passes >= self.consecutive_required:
            self.gate_passed = True

        return GateCheckResult(
            passed_this_attempt=passed,
            consecutive_passes=self.consecutive_passes,
            passes_needed=max(0, self.consecutive_required - self.consecutive_passes),
            gate_passed=self.gate_passed,
            attempt=attempt,
            gate_detail=gate_detail,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "consecutive_passes": self.consecutive_passes,
            "passes_needed": max(0, self.consecutive_required - self.consecutive_passes),
            "gate_passed": self.gate_passed,
            "total_attempts": len(self.attempts),
            "thresholds": dict(self.thresholds),
            "confidence_gate": self.confidence_gate,
            "consecutive_required": self.consecutive_required,
        }
