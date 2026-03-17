"use client"

import { useState } from "react"
import type { ReactNode } from "react"
import { Copy, Check } from "lucide-react"
import type { TranscriptMessage } from "@/lib/types"

// ── Minimal markdown renderer (no external deps) ─────────────────────────────
// Handles the subset Gemini actually emits: **bold**, *italic*, `code`,
// # headings (1-3 levels), • / – / - bullet lists, blank-line paragraphs.
// All text is inserted as React children — no dangerouslySetInnerHTML.

function renderInline(text: string): ReactNode[] {
  // Matches **bold**, *italic*, `code` — in that priority order.
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g
  const nodes: ReactNode[] = []
  let cursor = 0
  let m: RegExpExecArray | null
  let k = 0
  while ((m = re.exec(text)) !== null) {
    if (m.index > cursor) nodes.push(text.slice(cursor, m.index))
    if (m[2] !== undefined)      nodes.push(<strong key={k++}>{m[2]}</strong>)
    else if (m[3] !== undefined) nodes.push(<em key={k++}>{m[3]}</em>)
    else if (m[4] !== undefined) nodes.push(
      <code key={k++} className="font-mono text-xs px-1 rounded"
        style={{ background: "rgba(0,0,0,.08)" }}>{m[4]}</code>
    )
    cursor = m.index + m[0].length
  }
  if (cursor < text.length) nodes.push(text.slice(cursor))
  return nodes
}

function MarkdownText({ text }: { text: string }) {
  // Split on blank lines → blocks (paragraphs / lists / headings)
  const blocks = text.split(/\n{2,}/)
  return (
    <div className="space-y-2">
      {blocks.map((block, bi) => {
        const trimmed = block.trim()
        if (!trimmed) return null

        // Heading: # / ## / ###
        const hm = trimmed.match(/^(#{1,3})\s+(.+)/)
        if (hm) {
          const depth = hm[1].length
          const cls = depth === 1
            ? "text-base font-semibold mt-1"
            : depth === 2
              ? "text-sm font-semibold mt-0.5"
              : "text-sm font-medium mt-0.5"
          return <p key={bi} className={cls}>{renderInline(hm[2])}</p>
        }

        // Bullet list: lines starting with •, –, -, or *
        const lines = trimmed.split("\n")
        const bulletRe = /^[•\-–*]\s+/
        if (lines.every(l => bulletRe.test(l.trim()))) {
          return (
            <ul key={bi} className="list-disc list-inside space-y-0.5 pl-1">
              {lines.map((l, li) => (
                <li key={li}>{renderInline(l.trim().replace(bulletRe, ""))}</li>
              ))}
            </ul>
          )
        }

        // Numbered list: lines starting with "1. " etc.
        const numRe = /^\d+\.\s+/
        if (lines.every(l => numRe.test(l.trim()))) {
          return (
            <ol key={bi} className="list-decimal list-inside space-y-0.5 pl-1">
              {lines.map((l, li) => (
                <li key={li}>{renderInline(l.trim().replace(numRe, ""))}</li>
              ))}
            </ol>
          )
        }

        // Plain paragraph — preserve single newlines as <br>
        return (
          <p key={bi}>
            {lines.flatMap((l, li) => [
              ...renderInline(l),
              li < lines.length - 1 ? <br key={`br${li}`} /> : null,
            ]).filter(Boolean)}
          </p>
        )
      })}
    </div>
  )
}
import { formatTimestamp, cn } from "@/lib/utils"
import { ParseCard } from "./ParseCard"
import { LexiconCard } from "./LexiconCard"
import { ScansionCard } from "./ScansionCard"
import { ImageMessage } from "./ImageMessage"
import { StreamingIndicator } from "./StreamingIndicator"

interface MessageBubbleProps {
  message: TranscriptMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false)

  const isUser = message.role === "user"
  const isSystem = message.role === "system"

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  if (isSystem) {
    return (
      <div className="flex justify-center py-1">
        <span
          className="text-xs px-3 py-1 rounded-full"
          style={{ background: "var(--surface)", color: "var(--text-muted)", border: "1px solid var(--border)" }}
        >
          {message.content}
        </span>
      </div>
    )
  }

  return (
    <div
      className={cn(
        "group flex flex-col gap-1 animate-fade-in",
        isUser ? "items-end" : "items-start"
      )}
    >
      {/* Speaker label + timestamp */}
      <div
        className="flex items-center gap-2 px-1"
        style={{ color: "var(--text-muted)" }}
      >
        <span className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
          {isUser ? "You" : "Logos"}
        </span>
        <span className="text-xs">{formatTimestamp(message.timestamp)}</span>
        {message.interrupted && (
          <span className="text-xs italic" style={{ color: "var(--error)" }}>
            [interrupted]
          </span>
        )}
      </div>

      {/* Message content */}
      <div className="relative max-w-[90%]">
        {/* Inline image */}
        {message.image && (
          <ImageMessage src={message.image} />
        )}

        {/* Text content */}
        {message.content && message.content !== "[Image sent]" && (
          <div
            className={cn(
              "rounded-xl px-4 py-3 text-sm leading-relaxed transcript-prose",
              // User messages: plain pre-wrap text; assistant: parsed markdown
              isUser && "whitespace-pre-wrap rounded-tr-sm",
              !isUser && "rounded-tl-sm",
              message.isStreaming && !isUser && "streaming-cursor"
            )}
            style={{
              background: isUser ? "var(--accent)" : "var(--surface)",
              color: isUser ? "var(--accent-fg)" : "var(--text-primary)",
              border: isUser ? "none" : "1px solid var(--border)",
            }}
          >
            {isUser ? message.content : <MarkdownText text={message.content} />}
          </div>
        )}

        {/* Streaming dots (when no content yet) */}
        {message.isStreaming && !message.content && (
          <div
            className="rounded-xl rounded-tl-sm px-4 py-3"
            style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
          >
            <StreamingIndicator />
          </div>
        )}

        {/* Tool result cards */}
        {message.parseResult && <ParseCard result={message.parseResult} />}
        {message.lexiconResult && <LexiconCard result={message.lexiconResult} />}
        {message.scanResult && <ScansionCard result={message.scanResult} />}

        {/* Copy button */}
        {message.content && !message.isStreaming && (
          <button
            onClick={handleCopy}
            className="absolute -right-7 top-2 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity"
            style={{ color: "var(--text-muted)" }}
            title="Copy message"
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
        )}
      </div>
    </div>
  )
}
