interface TokenMonitorProps {
  tokenCount: number
  isStreaming: boolean
}

export function TokenMonitor({ tokenCount, isStreaming }: TokenMonitorProps) {
  return (
    <section>
      <h3
        className="inspector-mono text-xs uppercase tracking-wider mb-2"
        style={{ color: "var(--text-muted)" }}
      >
        Activity
      </h3>
      <div
        className="rounded-lg px-3 py-2 flex items-center justify-between"
        style={{ background: "var(--bg)", border: "1px solid var(--border)" }}
      >
        <div>
          <p className="inspector-mono text-xs" style={{ color: "var(--text-muted)" }}>
            Tokens received
          </p>
          <p
            className="inspector-mono text-lg font-medium tabular-nums"
            style={{ color: "var(--text-primary)" }}
          >
            {tokenCount.toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${isStreaming ? "status-dot-live" : ""}`}
            style={{
              background: isStreaming ? "var(--live)" : "var(--text-muted)",
            }}
          />
          <span className="inspector-mono text-xs" style={{ color: "var(--text-muted)" }}>
            {isStreaming ? "Streaming" : "Idle"}
          </span>
        </div>
      </div>
    </section>
  )
}
