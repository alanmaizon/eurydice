"use client"

import { Send, Trash2 } from "lucide-react"

interface RecordingCardProps {
  durationS: number
  onSend: () => void
  onDiscard: () => void
}

/**
 * Appears above the composer bar after the user stops recording.
 * Shows duration and send / discard actions.
 */
export function RecordingCard({ durationS, onSend, onDiscard }: RecordingCardProps) {
  const mins = Math.floor(durationS / 60)
  const secs = durationS % 60
  const label = mins > 0 ? `${mins}:${secs.toString().padStart(2, "0")}` : `${secs}s`

  return (
    <div
      className="shrink-0"
      style={{ borderTop: "1px solid var(--border)", background: "var(--surface)" }}
    >
      <div className="max-w-3xl mx-auto px-4 py-2 flex items-center gap-4">
        {/* Waveform placeholder — simple animated bars */}
        <div className="flex items-center gap-0.5 h-8">
          {Array.from({ length: 20 }).map((_, i) => (
            <div
              key={i}
              className="w-1 rounded-full"
              style={{
                background: "var(--accent)",
                opacity: 0.4 + (i % 3) * 0.2,
                height: `${28 + Math.sin(i * 1.3) * 12}%`,
              }}
            />
          ))}
        </div>

        {/* Duration badge */}
        <span
          className="text-xs font-mono font-semibold px-2 py-0.5 rounded"
          style={{
            background: "var(--surface-hover)",
            color: "var(--text-primary)",
            border: "1px solid var(--border)",
          }}
        >
          {label}
        </span>

        <span
          className="text-xs flex-1"
          style={{ color: "var(--text-secondary)" }}
        >
          Take ready — send for analysis or discard
        </span>

        <button
          onClick={onDiscard}
          className="p-1.5 rounded-lg transition-colors"
          style={{ color: "var(--text-muted)" }}
          title="Discard take"
        >
          <Trash2 size={15} />
        </button>

        <button
          onClick={onSend}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          title="Send for analysis"
        >
          <Send size={13} />
          Send
        </button>
      </div>
    </div>
  )
}
