"use client"

import { Moon, Sun, Terminal, ChevronLeft } from "lucide-react"
import type { ConnectionState, DifficultyLevel } from "@/lib/types"
import type { Theme } from "@/hooks/useTheme"
import { APP_NAME, APP_NAME_GREEK, DIFFICULTY_LABELS, DIFFICULTY_COLORS } from "@/lib/constants"
import { formatElapsed } from "@/lib/utils"
import { cn } from "@/lib/utils"

interface TopBarProps {
  connectionState: ConnectionState
  elapsedSeconds: number
  difficultyLevel: DifficultyLevel
  theme: Theme
  onToggleTheme: () => void
  onToggleInspector: () => void
  inspectorOpen: boolean
}

const STATE_LABEL: Record<ConnectionState, string> = {
  idle: "Not connected",
  connecting: "Connecting…",
  live: "Live",
  error: "Error",
  ended: "Session ended",
}

export function TopBar({
  connectionState,
  elapsedSeconds,
  difficultyLevel,
  theme,
  onToggleTheme,
  onToggleInspector,
  inspectorOpen,
}: TopBarProps) {
  const isLive = connectionState === "live"
  const isConnecting = connectionState === "connecting"
  const isError = connectionState === "error"

  return (
    <header
      className="flex items-center justify-between px-4 h-12 shrink-0"
      style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--bg)",
      }}
    >
      {/* Left: back arrow + product name */}
      <div className="flex items-center gap-3">
        <button
          className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors p-1 rounded"
          aria-label="Back"
          onClick={() => window.history.back()}
        >
          <ChevronLeft size={18} />
        </button>
        <div className="flex items-center gap-2">
          <span
            className="font-greek text-[var(--accent)] font-semibold text-lg select-none"
          >
            {APP_NAME_GREEK}
          </span>
          <span
            className="hidden sm:block text-[var(--text-secondary)] text-sm"
            style={{ fontFamily: "DM Sans, sans-serif" }}
          >
            {APP_NAME}
          </span>
        </div>
      </div>

      {/* Center: connection status */}
      <div className="flex items-center gap-2 text-sm">
        <span
          className={cn(
            "inline-block w-2 h-2 rounded-full",
            isLive && "status-dot-live",
            isConnecting && "bg-[var(--accent)] animate-pulse",
            isError && "bg-[var(--error)]",
            !isLive && !isConnecting && !isError && "bg-[var(--text-muted)]"
          )}
        />
        <span style={{ color: "var(--text-secondary)" }}>{STATE_LABEL[connectionState]}</span>
        {isLive && elapsedSeconds > 0 && (
          <span
            className="tabular-nums text-xs"
            style={{ color: "var(--text-muted)" }}
          >
            {formatElapsed(elapsedSeconds)}
          </span>
        )}
        {/* Feature E: difficulty badge */}
        <span
          className="text-xs px-1.5 py-0.5 rounded-full font-medium"
          style={{
            background: `color-mix(in srgb, ${DIFFICULTY_COLORS[difficultyLevel]} 15%, transparent)`,
            color: DIFFICULTY_COLORS[difficultyLevel],
            border: `1px solid color-mix(in srgb, ${DIFFICULTY_COLORS[difficultyLevel]} 30%, transparent)`,
          }}
        >
          {DIFFICULTY_LABELS[difficultyLevel]}
        </span>
      </div>

      {/* Right: inspector toggle + theme toggle */}
      <div className="flex items-center gap-1">
        <button
          onClick={onToggleInspector}
          className={cn(
            "p-1.5 rounded transition-colors",
            inspectorOpen
              ? "text-[var(--accent)]"
              : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          )}
          title="Toggle inspector"
          aria-label="Toggle inspector"
        >
          <Terminal size={16} />
        </button>
        <button
          onClick={onToggleTheme}
          className="p-1.5 rounded text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          title="Toggle theme"
          aria-label="Toggle theme"
        >
          {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
        </button>
      </div>
    </header>
  )
}
