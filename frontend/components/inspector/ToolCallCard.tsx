"use client"

import { useState } from "react"
import { ChevronDown, ChevronRight, Wrench } from "lucide-react"
import type { ToolCallRecord } from "@/lib/types"
import { formatTimestamp } from "@/lib/utils"

interface ToolCallCardProps {
  record: ToolCallRecord
}

export function ToolCallCard({ record }: ToolCallCardProps) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: "1px solid var(--border)", background: "var(--bg)" }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[var(--surface-hover)] transition-colors"
      >
        <Wrench size={13} style={{ color: "var(--accent)" }} />
        <span
          className="inspector-mono text-xs font-medium flex-1"
          style={{ color: "var(--text-primary)" }}
        >
          {record.toolName}
        </span>
        <span className="inspector-mono text-xs" style={{ color: "var(--text-muted)" }}>
          {formatTimestamp(record.timestamp)}
        </span>
        {open ? (
          <ChevronDown size={13} style={{ color: "var(--text-muted)" }} />
        ) : (
          <ChevronRight size={13} style={{ color: "var(--text-muted)" }} />
        )}
      </button>

      {open && (
        <div
          className="px-3 py-2 space-y-2"
          style={{ borderTop: "1px solid var(--border-subtle)" }}
        >
          <div>
            <p className="inspector-mono text-xs mb-1" style={{ color: "var(--text-muted)" }}>
              Args
            </p>
            <pre
              className="inspector-mono text-xs p-2 rounded overflow-x-auto"
              style={{ background: "var(--surface)", color: "var(--text-secondary)" }}
            >
              {JSON.stringify(record.args, null, 2)}
            </pre>
          </div>

          {record.result !== undefined && (
            <div>
              <p className="inspector-mono text-xs mb-1" style={{ color: "var(--text-muted)" }}>
                Result
              </p>
              <pre
                className="inspector-mono text-xs p-2 rounded overflow-x-auto"
                style={{ background: "var(--surface)", color: "var(--text-secondary)" }}
              >
                {JSON.stringify(record.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
