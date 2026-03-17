"use client"

import type { AudioAnalysisResult, VisionAnalysisResult } from "@/lib/types"

// ── Score bar ─────────────────────────────────────────────────────────────────

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100)
  const color =
    value >= 0.85 ? "#0f9d58" : value >= 0.70 ? "#b8860b" : "#ea4335"
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-14 shrink-0" style={{ color: "var(--text-secondary)" }}>
        {label}
      </span>
      <div
        className="flex-1 rounded-full overflow-hidden"
        style={{ height: 6, background: "var(--border)" }}
      >
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="w-8 text-right font-mono" style={{ color }}>
        {pct}%
      </span>
    </div>
  )
}

// ── Audio Analysis Card ───────────────────────────────────────────────────────

export function AudioAnalysisCard({ result }: { result: AudioAnalysisResult }) {
  const { mode, tempo_bpm, tempo_confidence, performance_scores, alignment, warnings } = result
  return (
    <div
      className="rounded-xl px-4 py-3 mt-2 text-sm space-y-2"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--accent)" }}>
          Audio Analysis
        </span>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded"
          style={{ background: "var(--border)", color: "var(--text-muted)" }}
        >
          {mode}
        </span>
      </div>

      {/* Tempo */}
      {tempo_bpm != null && (
        <div className="flex items-center gap-3">
          <span style={{ color: "var(--text-secondary)" }} className="text-xs w-14 shrink-0">Tempo</span>
          <span className="font-mono font-semibold" style={{ color: "var(--text-primary)" }}>
            {tempo_bpm.toFixed(1)} BPM
          </span>
          {tempo_confidence != null && (
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              ({Math.round(tempo_confidence * 100)}% confidence)
            </span>
          )}
        </div>
      )}

      {/* Performance scores */}
      {performance_scores && (
        <div className="space-y-1.5 pt-1">
          <ScoreBar label="Timing" value={performance_scores.timing} />
          <ScoreBar label="Notes" value={performance_scores.notes} />
          <ScoreBar label="Overall" value={performance_scores.overall} />
        </div>
      )}

      {/* Alignment */}
      {alignment?.mean_onset_error_ms != null && (
        <div className="text-xs pt-1" style={{ color: "var(--text-secondary)" }}>
          Mean onset error: <span className="font-mono">{alignment.mean_onset_error_ms.toFixed(0)} ms</span>
          {alignment.note_f1 != null && (
            <> · Note F1: <span className="font-mono">{(alignment.note_f1 * 100).toFixed(0)}%</span></>
          )}
        </div>
      )}

      {/* Warnings */}
      {warnings && warnings.length > 0 && (
        <div className="text-xs space-y-0.5 pt-1">
          {warnings.map((w, i) => (
            <div key={i} style={{ color: "#b8860b" }}>⚠ {w}</div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Vision Analysis Card ──────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<string, string> = {
  low: "#0f9d58",
  medium: "#b8860b",
  high: "#ea4335",
}

export function VisionAnalysisCard({ result }: { result: VisionAnalysisResult }) {
  const { hands_detected, handedness, technique_flags, capture_warnings } = result
  return (
    <div
      className="rounded-xl px-4 py-3 mt-2 text-sm space-y-2"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "#1a73e8" }}>
          Technique Analysis
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {hands_detected} hand{hands_detected !== 1 ? "s" : ""} detected
          {handedness && ` (${handedness.join(", ")})`}
        </span>
      </div>

      {/* Technique flags */}
      {technique_flags && technique_flags.length > 0 ? (
        <div className="space-y-2 pt-1">
          {technique_flags.map((flag, i) => (
            <div key={i} className="flex items-start gap-2">
              <span
                className="text-[10px] font-semibold px-1.5 py-0.5 rounded mt-0.5 shrink-0"
                style={{
                  background: `color-mix(in srgb, ${SEVERITY_COLOR[flag.severity] ?? "#888"} 15%, transparent)`,
                  color: SEVERITY_COLOR[flag.severity] ?? "#888",
                }}
              >
                {flag.severity.toUpperCase()}
              </span>
              <div>
                <div className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>
                  {flag.flag.replace(/_/g, " ")}
                </div>
                {flag.description && (
                  <div className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                    {flag.description}
                  </div>
                )}
                <div className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {Math.round(flag.confidence * 100)}% confidence
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs" style={{ color: "var(--text-secondary)" }}>
          No technique issues detected.
        </div>
      )}

      {/* Capture warnings */}
      {capture_warnings && capture_warnings.length > 0 && (
        <div className="text-xs space-y-0.5 pt-1">
          {capture_warnings.map((w, i) => (
            <div key={i} style={{ color: "#b8860b" }}>⚠ {w}</div>
          ))}
        </div>
      )}
    </div>
  )
}
