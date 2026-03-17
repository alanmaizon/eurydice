"use client"

import { useState } from "react"
import { BookOpen, ChevronDown, ChevronUp, X } from "lucide-react"

interface PinnedPassageCardProps {
  text: string
  onClear: () => void
}

export function PinnedPassageCard({ text, onClear }: PinnedPassageCardProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div
      className="rounded-xl overflow-hidden shrink-0 animate-fade-in"
      style={{ border: "1px solid var(--accent)", background: "var(--surface)" }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2"
        style={{ borderBottom: collapsed ? "none" : "1px solid var(--border-subtle)" }}
      >
        <BookOpen size={14} style={{ color: "var(--accent)" }} />
        <span
          className="text-xs font-medium flex-1"
          style={{ color: "var(--accent)" }}
        >
          Passage — close reading mode
        </span>
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="p-0.5 rounded transition-colors"
          style={{ color: "var(--text-muted)" }}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </button>
        <button
          onClick={onClear}
          className="p-0.5 rounded transition-colors"
          style={{ color: "var(--text-muted)" }}
          title="Clear passage"
        >
          <X size={14} />
        </button>
      </div>

      {/* Passage text */}
      {!collapsed && (
        <pre
          className="greek px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap overflow-y-auto max-h-40"
          style={{ color: "var(--text-primary)" }}
        >
          {text}
        </pre>
      )}
    </div>
  )
}
