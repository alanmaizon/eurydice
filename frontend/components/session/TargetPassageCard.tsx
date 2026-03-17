"use client"

import { useEffect, useRef, useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import type { MasteryState } from "@/lib/types"
import { MasteryProgress, type MasteryHistoryEntry } from "./MasteryProgress"

interface TargetPassageCardProps {
  description: string
  targetBpm?: number | null
  masteryState: MasteryState | null
}

export function TargetPassageCard({
  description,
  targetBpm,
  masteryState,
}: TargetPassageCardProps) {
  const [collapsed, setCollapsed] = useState(false)
  const [history, setHistory] = useState<MasteryHistoryEntry[]>([])
  const prevAttemptRef = useRef(0)

  // Accumulate per-attempt history as masteryState updates arrive
  useEffect(() => {
    if (!masteryState) return
    if (masteryState.attemptNumber === prevAttemptRef.current) return
    prevAttemptRef.current = masteryState.attemptNumber
    const entry: MasteryHistoryEntry = {
      timing: masteryState.gateDetail.timing.score,
      notes: masteryState.gateDetail.notes.score,
      passed:
        masteryState.gateDetail.timing.ok &&
        masteryState.gateDetail.notes.ok &&
        masteryState.gateDetail.confidence.ok,
    }
    setHistory((prev) => [...prev, entry].slice(-10))
  }, [masteryState])

  return (
    <div
      className="rounded-xl overflow-hidden shrink-0 animate-fade-in"
      style={{ border: "1px solid var(--accent)", background: "var(--surface)" }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2"
        style={{ borderBottom: collapsed ? "none" : "1px solid var(--border)" }}
      >
        <span style={{ color: "var(--accent)", fontSize: 14 }}>♪</span>
        <span
          className="text-xs font-medium flex-1 truncate"
          style={{ color: "var(--accent)" }}
        >
          {description}
        </span>
        {targetBpm && (
          <span
            className="text-[11px] tabular-nums shrink-0"
            style={{ color: "var(--text-muted)" }}
          >
            {targetBpm} BPM
          </span>
        )}
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="p-0.5 rounded"
          style={{ color: "var(--text-muted)" }}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </button>
      </div>

      {/* Body */}
      {!collapsed && (
        masteryState ? (
          <MasteryProgress masteryState={masteryState} history={history} />
        ) : (
          <div className="px-4 py-2 text-xs" style={{ color: "var(--text-muted)" }}>
            No attempts yet — record a take to begin
          </div>
        )
      )}
    </div>
  )
}
