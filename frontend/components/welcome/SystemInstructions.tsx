"use client"

import { useState } from "react"
import { ChevronDown, ChevronRight, Settings2 } from "lucide-react"

interface SystemInstructionsProps {
  value: string
  onChange: (v: string) => void
}

export function SystemInstructions({ value, onChange }: SystemInstructionsProps) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ border: "1px solid var(--border)", background: "var(--surface)" }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-[var(--surface-hover)]"
      >
        <Settings2 size={14} style={{ color: "var(--accent)" }} />
        <span className="text-sm font-medium flex-1" style={{ color: "var(--text-primary)" }}>
          System Instructions
        </span>
        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          {open ? "Click to collapse" : "Click to expand"}
        </span>
        {open ? (
          <ChevronDown size={15} style={{ color: "var(--text-secondary)" }} />
        ) : (
          <ChevronRight size={15} style={{ color: "var(--text-secondary)" }} />
        )}
      </button>

      {open && (
        <div style={{ borderTop: "1px solid var(--border-subtle)" }}>
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            rows={12}
            className="w-full px-4 py-3 text-xs resize-y outline-none"
            style={{
              fontFamily: "JetBrains Mono, monospace",
              background: "transparent",
              color: "var(--text-secondary)",
              lineHeight: "1.6",
            }}
            placeholder="Enter system instructions for the model…"
          />
        </div>
      )}
    </div>
  )
}
