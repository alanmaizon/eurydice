import type { LexiconResult } from "@/lib/types"

interface LexiconCardProps {
  result: LexiconResult
}

export function LexiconCard({ result }: LexiconCardProps) {
  return (
    <div
      className="rounded-xl p-4 mt-2 animate-fade-in"
      style={{ border: "1px solid var(--border)", background: "var(--surface)" }}
    >
      {/* Header */}
      <div className="flex items-baseline gap-2 mb-3">
        <span className="greek text-lg font-medium" style={{ color: "var(--accent)" }}>
          {result.lemma}
        </span>
        {result.transliteration && (
          <span className="text-xs italic" style={{ color: "var(--text-muted)" }}>
            ({result.transliteration})
          </span>
        )}
        <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {result.part_of_speech}
        </span>
      </div>

      {/* Definitions */}
      {result.definitions && result.definitions.length > 0 && (
        <ol className="list-decimal list-inside mb-2 space-y-0.5">
          {result.definitions.map((def, i) => {
            let text: string
            if (typeof def === "string") {
              text = def
            } else if (typeof (def as any).sense === "string") {
              text = (def as any).sense
            } else if (typeof (def as any).definition === "string") {
              text = (def as any).definition
            } else {
              text = JSON.stringify(def)
            }
            return (
              <li key={i} className="text-sm" style={{ color: "var(--text-primary)" }}>
                {text}
              </li>
            )
          })}
        </ol>
      )}

      {/* Usage note */}
      {result.usage && (
        <p className="text-xs italic mt-2" style={{ color: "var(--text-secondary)" }}>
          {typeof result.usage === "string" ? result.usage : JSON.stringify(result.usage)}
        </p>
      )}

      {/* Principal parts */}
      {result.principal_parts && (
        <p className="text-xs mt-1.5 greek leading-relaxed" style={{ color: "var(--text-secondary)" }}>
          {typeof result.principal_parts === "string" ? result.principal_parts : JSON.stringify(result.principal_parts)}
        </p>
      )}

      {/* Key refs */}
      {result.key_refs && result.key_refs.length > 0 && (
        <p className="text-xs mt-1.5 inspector-mono" style={{ color: "var(--text-muted)" }}>
          {result.key_refs.map((r: unknown) => (typeof r === "string" ? r : JSON.stringify(r))).join(" · ")}
        </p>
      )}
    </div>
  )
}
