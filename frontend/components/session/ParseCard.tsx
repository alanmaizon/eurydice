import type { ParseResult } from "@/lib/types"

interface ParseCardProps {
  result: ParseResult
}

const Row = ({ label, value }: { label: string; value?: string }) =>
  value ? (
    <tr>
      <td
        className="pr-4 py-0.5 text-xs whitespace-nowrap"
        style={{ color: "var(--text-secondary)" }}
      >
        {label}
      </td>
      <td className="py-0.5 text-xs" style={{ color: "var(--text-primary)" }}>
        {value}
      </td>
    </tr>
  ) : null

export function ParseCard({ result }: ParseCardProps) {
  return (
    <div
      className="rounded-xl p-4 mt-2 animate-fade-in"
      style={{ border: "1px solid var(--border)", background: "var(--surface)" }}
    >
      {/* Header */}
      <div className="flex items-baseline gap-2 mb-3">
        <span
          className="greek text-lg font-medium"
          style={{ color: "var(--accent)" }}
        >
          {result.word}
        </span>
        <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
          → <span className="greek">{result.lemma}</span>
        </span>
        {result.transliteration && (
          <span className="text-xs italic" style={{ color: "var(--text-muted)" }}>
            ({result.transliteration})
          </span>
        )}
      </div>

      {/* Morphology table */}
      <table className="mb-2">
        <tbody>
          <Row label="Part of Speech" value={result.part_of_speech} />
          <Row label="Tense" value={result.tense} />
          <Row label="Voice" value={result.voice} />
          <Row label="Mood" value={result.mood} />
          <Row label="Person" value={result.person} />
          <Row label="Number" value={result.number} />
          <Row label="Gender" value={result.gender} />
          <Row label="Case" value={result.case} />
          <Row label="Degree" value={result.degree} />
          <Row label="IPA" value={result.ipa} />
        </tbody>
      </table>

      {/* Definition */}
      <p className="text-sm" style={{ color: "var(--text-primary)" }}>
        <span className="font-medium" style={{ color: "var(--text-secondary)" }}>
          Meaning:{" "}
        </span>
        &ldquo;{result.definition}&rdquo;
      </p>

      {/* Principal parts */}
      {result.principal_parts && (
        <p
          className="text-xs mt-1.5 greek leading-relaxed"
          style={{ color: "var(--text-secondary)" }}
        >
          {result.principal_parts}
        </p>
      )}

      {/* Notes */}
      {result.notes && (
        <p className="text-xs mt-1.5 italic" style={{ color: "var(--text-muted)" }}>
          {result.notes}
        </p>
      )}
    </div>
  )
}
