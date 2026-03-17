"use client"

import { useState, useRef, KeyboardEvent } from "react"
import {
  Mic,
  MicOff,
  Camera,
  CameraOff,
  Circle,
  Square,
  Play,
  Send,
  Zap,
} from "lucide-react"
import type { ConnectionState } from "@/lib/types"
import type { RecordingState } from "@/hooks/useRecording"
import { IS_EURYDICE } from "@/lib/constants"
import { cn } from "@/lib/utils"

interface ComposerBarProps {
  connectionState: ConnectionState
  isAudioCapturing: boolean
  isCameraActive: boolean
  audioError: string | null
  cameraError: string | null
  onStartSession: () => void
  onEndSession: () => void
  onSendText: (text: string) => void
  onToggleMic: () => void
  onToggleCamera: (videoEl?: HTMLVideoElement) => void
  onCaptureAndSendImage: () => void
  onInterrupt: () => void
  // Eurydice recording
  recordingState?: RecordingState
  recordingDurationS?: number
  onStartRecording?: () => void
  onStopRecording?: () => void
}

export function ComposerBar({
  connectionState,
  isAudioCapturing,
  isCameraActive,
  audioError,
  cameraError,
  onStartSession,
  onEndSession,
  onSendText,
  onToggleMic,
  onToggleCamera,
  onCaptureAndSendImage,
  onInterrupt,
  recordingState = "idle",
  recordingDurationS = 0,
  onStartRecording,
  onStopRecording,
}: ComposerBarProps) {
  const [text, setText] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isLive = connectionState === "live"
  const isConnecting = connectionState === "connecting"
  const isIdle = connectionState === "idle"
  const isEnded = connectionState === "ended"
  const isError = connectionState === "error"

  const canInteract = isLive
  const canStart = isIdle || isEnded || isError

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || !isLive) return
    onSendText(trimmed)
    setText("")
    textareaRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const error = audioError ?? cameraError

  return (
    <div
      className="shrink-0"
      style={{
        background: "var(--composer)",
        borderTop: "1px solid var(--composer-border)",
      }}
    >
      {/* Error banner */}
      {error && (
        <div
          className="px-4 py-1.5 text-xs"
          style={{ color: "var(--error)", background: "var(--error-surface)" }}
        >
          {error}
        </div>
      )}

      <div className="flex items-end gap-2 px-3 py-2 max-w-3xl mx-auto">
        {/* Media controls */}
        <div className="flex items-center gap-1 pb-1">
          {IS_EURYDICE ? (
            /* ── Eurydice: Record button replaces streaming mic ─────────────── */
            recordingState === "recording" ? (
              <button
                onClick={onStopRecording}
                disabled={!canInteract}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors",
                  "text-[var(--error)] bg-[var(--error-surface)] animate-pulse",
                  !canInteract && "opacity-40 cursor-not-allowed"
                )}
                title="Stop recording"
              >
                <Circle size={10} className="fill-current" />
                <span className="font-mono">
                  {Math.floor(recordingDurationS / 60) > 0
                    ? `${Math.floor(recordingDurationS / 60)}:${(recordingDurationS % 60).toString().padStart(2, "0")}`
                    : `${recordingDurationS}s`}
                </span>
              </button>
            ) : (
              <button
                onClick={onStartRecording}
                disabled={!canInteract || recordingState === "ready"}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs font-medium transition-colors",
                  audioError
                    ? "text-[var(--error)] bg-[var(--error-surface)]"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]",
                  (!canInteract || recordingState === "ready") && "opacity-40 cursor-not-allowed"
                )}
                title="Record a guitar take"
              >
                <Circle size={10} className="fill-current text-[var(--error)]" />
                <span>Record</span>
              </button>
            )
          ) : (
            /* ── Logos: streaming mic (original) ──────────────────────────── */
            <button
              onClick={onToggleMic}
              disabled={!canInteract}
              className={cn(
                "p-2 rounded-lg transition-colors",
                audioError
                  ? "text-[var(--error)] bg-[var(--error-surface)]"
                  : isAudioCapturing
                    ? "text-[var(--accent)] bg-[var(--surface-hover)]"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]",
                !canInteract && "opacity-40 cursor-not-allowed"
              )}
              title={isAudioCapturing ? "Stop mic" : "Start mic"}
            >
              {isAudioCapturing ? <Mic size={18} /> : <MicOff size={18} />}
            </button>
          )}

          {/*
           * Camera toggle — state semantics:
           *   off (default)   → CameraOff icon, muted grey styling
           *   on (active)     → Camera icon,    accent/active styling
           *   error/denied    → CameraOff icon, error/red styling
           */}
          <button
            onClick={() => onToggleCamera()}
            disabled={!canInteract}
            className={cn(
              "p-2 rounded-lg transition-colors",
              cameraError
                ? "text-[var(--error)] bg-[var(--error-surface)]"
                : isCameraActive
                  ? "text-[var(--accent)] bg-[var(--surface-hover)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]",
              !canInteract && "opacity-40 cursor-not-allowed"
            )}
            title={isCameraActive ? "Stop camera" : "Start camera"}
          >
            {isCameraActive ? <Camera size={18} /> : <CameraOff size={18} />}
          </button>

          {/* When camera is on: shutter button replaces interrupt */}
          {canInteract && isCameraActive ? (
            <button
              onClick={onCaptureAndSendImage}
              className="p-2 rounded-lg text-[var(--accent)] hover:opacity-80 transition-opacity"
              title="Take photo"
            >
              <Circle size={18} />
            </button>
          ) : (
            canInteract && (
              <button
                onClick={onInterrupt}
                className="p-2 rounded-lg text-[var(--text-secondary)] hover:text-[var(--error)] hover:bg-[var(--error-surface)] transition-colors"
                title="Interrupt"
              >
                <Zap size={18} />
              </button>
            )
          )}
        </div>

        {/* Text input */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!canInteract}
          placeholder={
            isLive
              ? "Type a message… (Enter to send, Shift+Enter for newline)"
              : "Start a session to begin"
          }
          rows={1}
          className={cn(
            "flex-1 resize-none rounded-lg px-3 py-2 text-sm outline-none transition-colors",
            "min-h-[36px] max-h-[120px] overflow-y-auto",
            "bg-transparent placeholder:text-[var(--text-muted)]",
            !canInteract && "cursor-not-allowed opacity-60"
          )}
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            color: "var(--text-primary)",
          }}
        />

        {/* Send button (when live) */}
        {canInteract && (
          <button
            onClick={handleSend}
            disabled={!text.trim()}
            className={cn(
              "p-2 rounded-lg transition-colors pb-1",
              text.trim()
                ? "text-[var(--accent)] hover:opacity-80"
                : "text-[var(--text-muted)] cursor-not-allowed"
            )}
            title="Send"
          >
            <Send size={18} />
          </button>
        )}

        {/* Start / End session button */}
        {canStart && (
          <button
            onClick={onStartSession}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{
              background: "var(--accent)",
              color: "var(--accent-fg)",
            }}
          >
            <Play size={15} />
            <span>Start session</span>
          </button>
        )}

        {isConnecting && (
          <button
            disabled
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium opacity-60 cursor-not-allowed"
            style={{ background: "var(--accent)", color: "var(--accent-fg)" }}
          >
            <span className="w-3 h-3 border-2 border-white/60 border-t-white rounded-full animate-spin" />
            <span>Connecting…</span>
          </button>
        )}

        {isLive && (
          <button
            onClick={onEndSession}
            data-testid="end-session-btn"
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{
              border: "1px solid var(--border)",
              color: "var(--text-secondary)",
            }}
          >
            <Square size={13} />
            <span>End</span>
          </button>
        )}
      </div>
    </div>
  )
}
