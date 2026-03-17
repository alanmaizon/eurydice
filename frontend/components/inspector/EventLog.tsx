import type { InspectorEvent } from "@/lib/types"
import { formatTimestamp } from "@/lib/utils"

interface EventLogProps {
  events: InspectorEvent[]
}

const EVENT_COLOR: Record<string, string> = {
  "session.start": "#1a73e8",
  "session.started": "#34a853",
  "session.end": "#5f6368",
  "session.ended": "#5f6368",
  "input.text": "#1a73e8",
  "input.audio": "#1a73e8",
  "input.image": "#1a73e8",
  "input.interrupt": "#ea4335",
  "output.text.delta": "#34a853",
  "output.text.done": "#34a853",
  "output.audio.delta": "#0f9d58",
  "tool.call": "#b8860b",
  "tool.result": "#c8a84e",
  error: "#ea4335",
}

export function EventLog({ events }: EventLogProps) {
  if (events.length === 0) {
    return (
      <p className="inspector-mono" style={{ color: "var(--text-muted)" }}>
        No events yet.
      </p>
    )
  }

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: "1px solid var(--border)", background: "var(--bg)" }}
    >
      <div className="max-h-64 overflow-y-auto">
        {events.map((ev) => (
          <div
            key={ev.id}
            className="flex items-start gap-2 px-3 py-1.5 border-b last:border-b-0"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <span
              className="inspector-mono text-xs shrink-0 tabular-nums"
              style={{ color: "var(--text-muted)" }}
            >
              {formatTimestamp(ev.timestamp)}
            </span>
            <span
              className="inspector-mono text-xs font-medium shrink-0"
              style={{ color: EVENT_COLOR[ev.event] ?? "var(--text-secondary)" }}
            >
              {ev.event}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
