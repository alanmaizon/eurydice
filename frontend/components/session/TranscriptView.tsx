"use client"

import { useEffect, useRef, useState } from "react"
import type { ConnectionState, TranscriptMessage } from "@/lib/types"
import { MessageBubble } from "./MessageBubble"
import { PinnedPassageCard } from "./PinnedPassageCard"
import { StreamingIndicator } from "./StreamingIndicator"
import { cn } from "@/lib/utils"

interface TranscriptViewProps {
  messages: TranscriptMessage[]
  isStreaming: boolean
  connectionState: ConnectionState
  pinnedPassage?: string | null
  onClearPassage?: () => void
}

export function TranscriptView({
  messages,
  isStreaming,
  connectionState,
  pinnedPassage,
  onClearPassage,
}: TranscriptViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages, autoScroll])

  // Detect user scrolling up → pause auto-scroll
  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    setAutoScroll(nearBottom)
  }

  const isConnecting = connectionState === "connecting"
  const isEnded = connectionState === "ended"

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Feature D: Pinned passage card (always visible above scroll area) */}
      {pinnedPassage && (
        <div className="pt-3 shrink-0">
          <PinnedPassageCard text={pinnedPassage} onClear={onClearPassage ?? (() => {})} />
        </div>
      )}
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto py-4 space-y-4"
    >
      {/* Connecting state */}
      {isConnecting && messages.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 gap-3 animate-fade-in">
          <div className="flex items-center gap-2">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: "var(--accent)", animation: "pulse-dot 1s ease-in-out infinite" }}
            />
            <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
              Connecting to Logos…
            </span>
          </div>
        </div>
      )}

      {/* Messages */}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {/* Assistant streaming (when last message is not yet in transcript) */}
      {isStreaming && messages.length === 0 && (
        <div className="flex items-start">
          <div
            className="rounded-xl rounded-tl-sm px-4 py-3"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            <StreamingIndicator />
          </div>
        </div>
      )}

      {/* Session ended banner */}
      {isEnded && (
        <div
          className="text-center text-sm py-4 animate-fade-in"
          style={{ color: "var(--text-muted)" }}
        >
          Session ended — start a new session to continue
        </div>
      )}

      {/* Scroll anchor */}
      <div ref={bottomRef} />
    </div>
    </div>
  )
}
