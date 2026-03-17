"use client"

import type { MasteryState } from "@/lib/types"

export interface MasteryHistoryEntry {
  timing: number
  notes: number
  passed: boolean
}

// ── Score bar with threshold marker ──────────────────────────────────────────

function ScoreBar({
  label,
  score,
  threshold,
  ok,
}: {
  label: string
  score: number
  threshold: number
  ok: boolean
}) {
  const pct = Math.min(100, Math.round(score * 100))
  const thPct = Math.round(threshold * 100)
  const fillColor = ok ? "#0f9d58" : score >= threshold * 0.85 ? "#b8860b" : "var(--text-muted)"

  return (
    <div className="flex items-center gap-2">
      <span
        className="text-[10px] font-semibold uppercase tracking-wider w-12 shrink-0 text-right"
        style={{ color: ok ? "#0f9d58" : "var(--text-muted)" }}
      >
        {label}
      </span>

      {/* Bar container */}
      <div
        className="flex-1 relative h-2 rounded-full"
        style={{ background: "var(--border)" }}
      >
        {/* Fill */}
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-300"
          style={{ width: `${pct}%`, background: fillColor }}
        />
        {/* Threshold marker — sits on top */}
        <div
          className="absolute top-1/2 -translate-y-1/2 w-px h-3 rounded-full"
          style={{ left: `${thPct}%`, background: "var(--text-primary)", opacity: 0.4 }}
        />
      </div>

      <span
        className="text-[10px] w-8 text-right tabular-nums shrink-0"
        style={{ color: ok ? "#0f9d58" : "var(--text-secondary)" }}
      >
        {pct}%
      </span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface MasteryProgressProps {
  masteryState: MasteryState
  history?: MasteryHistoryEntry[]
}

export function MasteryProgress({ masteryState, history }: MasteryProgressProps) {
  const { consecutivePasses, passesNeeded, mastered, attemptNumber, gateDetail } = masteryState

  // Status badge
  const statusLabel = mastered
    ? "Mastered 🎸"
    : consecutivePasses > 0 && consecutivePasses >= passesNeeded - 1
    ? "Almost there"
    : attemptNumber > 0
    ? "In progress"
    : "Not started"

  const statusColor = mastered
    ? "#0f9d58"
    : consecutivePasses > 0 && consecutivePasses >= passesNeeded - 1
    ? "#b8860b"
    : attemptNumber > 0
    ? "var(--accent)"
    : "var(--text-muted)"

  return (
    <div className="space-y-3 px-4 py-3">
      {/* Row: attempt count · streak dots · status badge */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
            {attemptNumber > 0 ? `Attempt #${attemptNumber}` : "No attempts yet"}
          </span>

          {/* Streak dots */}
          <div className="flex items-center gap-1">
            {Array.from({ length: passesNeeded }).map((_, i) => (
              <div
                key={i}
                className="w-2.5 h-2.5 rounded-full transition-all duration-300"
                style={{
                  background:
                    mastered || i < consecutivePasses ? "#0f9d58" : "var(--border)",
                  border: "1px solid",
                  borderColor:
                    mastered || i < consecutivePasses ? "#0f9d58" : "var(--border)",
                }}
              />
            ))}
            <span className="text-[10px] ml-0.5" style={{ color: "var(--text-muted)" }}>
              {consecutivePasses}/{passesNeeded}
            </span>
          </div>
        </div>

        <span className="text-[11px] font-medium shrink-0" style={{ color: statusColor }}>
          {statusLabel}
        </span>
      </div>

      {/* Score bars — only after at least one attempt */}
      {attemptNumber > 0 && (
        <div className="space-y-1.5">
          <ScoreBar
            label="Timing"
            score={gateDetail.timing.score}
            threshold={gateDetail.timing.threshold}
            ok={gateDetail.timing.ok}
          />
          <ScoreBar
            label="Notes"
            score={gateDetail.notes.score}
            threshold={gateDetail.notes.threshold}
            ok={gateDetail.notes.ok}
          />
        </div>
      )}

      {/* History dots — last 10 attempts */}
      {history && history.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] shrink-0" style={{ color: "var(--text-muted)" }}>
            History
          </span>
          <div className="flex items-center gap-1">
            {history.slice(-10).map((h, i) => (
              <div
                key={i}
                className="w-2 h-2 rounded-full"
                title={`Timing ${Math.round(h.timing * 100)}% · Notes ${Math.round(h.notes * 100)}%`}
                style={{ background: h.passed ? "#0f9d58" : "#e53e3e" }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
