"use client"

import type { CoachingResponse } from "@/lib/types"

// ── Per-section styling ────────────────────────────────────────────────────────

const SECTIONS = [
  {
    key: "observed_issue",
    label: "Observed",
    // subtle grey — this is data, not instruction
    accent: "var(--text-secondary)",
    bg: "transparent",
    border: "var(--border)",
  },
  {
    key: "primary_correction",
    label: "Fix",
    // amber — the highest-leverage instruction
    accent: "#b8860b",
    bg: "color-mix(in srgb, #b8860b 8%, transparent)",
    border: "color-mix(in srgb, #b8860b 30%, transparent)",
  },
  {
    key: "drill",
    label: "Drill",
    // blue — practice exercise
    accent: "#1a73e8",
    bg: "color-mix(in srgb, #1a73e8 8%, transparent)",
    border: "color-mix(in srgb, #1a73e8 30%, transparent)",
  },
  {
    key: "success_criterion",
    label: "Pass when",
    // green — goal
    accent: "#0f9d58",
    bg: "color-mix(in srgb, #0f9d58 8%, transparent)",
    border: "color-mix(in srgb, #0f9d58 30%, transparent)",
  },
] as const

const MASTERY_BADGE: Record<string, { label: string; color: string }> = {
  progressing: { label: "Progressing",  color: "var(--text-secondary)" },
  close:       { label: "Almost there", color: "#b8860b" },
  mastered:    { label: "Mastered 🎸",  color: "#0f9d58" },
}

export function CoachingCard({ result }: { result: CoachingResponse }) {
  const badge = result.mastery_status ? MASTERY_BADGE[result.mastery_status] : null

  return (
    <div
      className="rounded-xl mt-2 text-sm overflow-hidden"
      style={{ border: "1px solid var(--border)" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}
      >
        <span
          className="text-xs font-semibold uppercase tracking-wider"
          style={{ color: "var(--accent)" }}
        >
          Coaching
        </span>
        {badge && (
          <span className="text-[11px] font-medium" style={{ color: badge.color }}>
            {badge.label}
          </span>
        )}
      </div>

      {/* Sections */}
      <div style={{ background: "var(--bg)" }}>
        {SECTIONS.map(({ key, label, accent, bg, border }) => {
          const text = result[key as keyof CoachingResponse]
          if (!text) return null
          return (
            <div
              key={key}
              className="flex gap-3 px-4 py-3"
              style={{
                background: bg,
                borderBottom: `1px solid var(--border)`,
              }}
            >
              <span
                className="text-[10px] font-semibold uppercase tracking-wider pt-0.5 w-16 shrink-0 text-right"
                style={{ color: accent }}
              >
                {label}
              </span>
              <div
                className="flex-1 pl-3 text-sm leading-relaxed"
                style={{
                  color: "var(--text-primary)",
                  borderLeft: `2px solid ${border}`,
                }}
              >
                {text as string}
              </div>
            </div>
          )
        })}

        {/* Likely cause — shown inline under Observed if present */}
        {result.likely_cause && (
          <div
            className="flex gap-3 px-4 py-2"
            style={{ borderBottom: "1px solid var(--border)" }}
          >
            <span
              className="text-[10px] font-semibold uppercase tracking-wider pt-0.5 w-16 shrink-0 text-right"
              style={{ color: "var(--text-muted)" }}
            >
              Why
            </span>
            <div
              className="flex-1 pl-3 text-xs italic leading-relaxed"
              style={{ color: "var(--text-secondary)", borderLeft: "2px solid var(--border)" }}
            >
              {result.likely_cause}
            </div>
          </div>
        )}

        {/* Confidence note */}
        {result.confidence_note && (
          <div className="px-4 py-2 text-xs" style={{ color: "#b8860b" }}>
            ⚠ {result.confidence_note}
          </div>
        )}
      </div>
    </div>
  )
}
