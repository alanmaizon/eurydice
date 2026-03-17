import type { ScansionFoot, ScansionResult } from "@/lib/types"

interface ScansionCardProps {
  result: ScansionResult
}

export function ScansionCard({ result }: ScansionCardProps) {
  const feet: ScansionFoot[] | null = Array.isArray(result.analysis)
    ? (result.analysis as ScansionFoot[])
    : null
  const analysisSummary = typeof result.analysis === "string" ? result.analysis : null

  return (
    <div
      className="rounded-xl p-4 mt-2 animate-fade-in"
      style={{ border: "1px solid var(--border)", background: "var(--surface)" }}
    >
      {/* Header */}
      <div className="flex items-baseline gap-2 mb-2">
        <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
          {result.meter}
        </span>
      </div>

      {/* Line */}
      <p className="greek text-sm mb-2" style={{ color: "var(--text-primary)" }}>
        {result.line}
      </p>

      {/* Scansion pattern */}
      {result.pattern && (
        <p
          className="inspector-mono text-sm mb-3 tracking-widest"
          style={{ color: "var(--text-secondary)" }}
        >
          {result.pattern}
        </p>
      )}

      {/* Foot-by-foot breakdown */}
      {feet && feet.length > 0 && (
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr style={{ color: "var(--text-muted)" }}>
              <th className="text-left pr-3 pb-1 font-medium">Foot</th>
              <th className="text-left pr-3 pb-1 font-medium">Syllables</th>
              <th className="text-left pr-3 pb-1 font-medium">Pattern</th>
              <th className="text-left pb-1 font-medium">Type</th>
            </tr>
          </thead>
          <tbody>
            {feet.map((f) => (
              <tr key={f.foot} style={{ borderTop: "1px solid var(--border)" }}>
                <td className="pr-3 py-1" style={{ color: "var(--text-muted)" }}>
                  {f.foot}
                </td>
                <td className="pr-3 py-1 greek" style={{ color: "var(--text-primary)" }}>
                  {f.syllables}
                </td>
                <td className="pr-3 py-1 inspector-mono" style={{ color: "var(--text-secondary)" }}>
                  {f.pattern}
                </td>
                <td className="py-1" style={{ color: "var(--text-primary)" }}>
                  {f.type}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Plain-text analysis fallback */}
      {analysisSummary && (
        <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
          {analysisSummary}
        </p>
      )}
    </div>
  )
}
