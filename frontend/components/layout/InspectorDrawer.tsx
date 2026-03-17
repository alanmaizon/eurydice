"use client"

import { X, Trash2 } from "lucide-react"
import type { InspectorEvent, ToolCallRecord } from "@/lib/types"
import { EventLog } from "@/components/inspector/EventLog"
import { ToolCallCard } from "@/components/inspector/ToolCallCard"
import { TokenMonitor } from "@/components/inspector/TokenMonitor"
import { CameraPreview } from "@/components/inspector/CameraPreview"
import { cn } from "@/lib/utils"

interface InspectorDrawerProps {
  open: boolean
  onClose: () => void
  events: InspectorEvent[]
  toolCalls: ToolCallRecord[]
  tokenCount: number
  isStreaming: boolean
  isCameraActive: boolean
  videoRef: React.RefObject<HTMLVideoElement>
  onClear: () => void
}

export function InspectorDrawer({
  open,
  onClose,
  events,
  toolCalls,
  tokenCount,
  isStreaming,
  isCameraActive,
  videoRef,
  onClear,
}: InspectorDrawerProps) {
  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 z-20 sm:hidden"
          style={{ background: "rgba(0,0,0,0.3)" }}
          onClick={onClose}
        />
      )}

      {/* Drawer panel */}
      <aside
        className={cn(
          "fixed top-0 right-0 h-full z-30 flex flex-col",
          "w-full sm:w-[380px]",
          "transition-transform duration-250",
          open ? "translate-x-0 animate-slide-in" : "translate-x-full"
        )}
        style={{
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 h-12 shrink-0"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <span className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
            Inspector
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={onClear}
              className="p-1.5 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title="Clear log"
            >
              <Trash2 size={15} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
              title="Close inspector"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          {/* Token monitor */}
          <TokenMonitor tokenCount={tokenCount} isStreaming={isStreaming} />

          {/* Camera preview */}
          {isCameraActive && (
            <CameraPreview videoRef={videoRef} />
          )}

          {/* Tool calls */}
          {toolCalls.length > 0 && (
            <section>
              <h3
                className="inspector-mono text-xs uppercase tracking-wider mb-2"
                style={{ color: "var(--text-muted)" }}
              >
                Tool Calls
              </h3>
              <div className="space-y-2">
                {toolCalls.map((tc) => (
                  <ToolCallCard key={tc.id} record={tc} />
                ))}
              </div>
            </section>
          )}

          {/* Event log */}
          <section>
            <h3
              className="inspector-mono text-xs uppercase tracking-wider mb-2"
              style={{ color: "var(--text-muted)" }}
            >
              Event Log
            </h3>
            <EventLog events={events} />
          </section>
        </div>
      </aside>
    </>
  )
}
