import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")
  const s = (seconds % 60).toString().padStart(2, "0")
  return `${m}:${s}`
}

export function formatTimestamp(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** Convert a base64 string to a data URL for display. */
export function base64ToDataUrl(b64: string, mimeType = "image/jpeg"): string {
  return `data:${mimeType};base64,${b64}`
}

/**
 * Strip parenthetical transliterations that immediately follow a Greek-script
 * token. Matches: GreekWord (single-word-latin-only-≤30-chars)
 *
 * Strips:   εἰμί (eimi)      → εἰμί
 *           Πνεῦμα (Pneuma)  → Πνεῦμα
 * Preserves: Peter (not Paul) — no preceding Greek token
 *            εἰμί (to be)    — multi-word parenthetical
 */
const TRANSLIT_PARENS_RE =
  /([^\s]*[\u0370-\u03FF\u1F00-\u1FFF][^\s]*)\s*\(([A-Za-z\u00C0-\u024F'-]{1,30})\)/g

export function stripParentheticalTransliterations(text: string): string {
  return text.replace(TRANSLIT_PARENS_RE, "$1")
}

/**
 * Strip Gemini control tokens (<ctrlN>), non-printable chars, and
 * parenthetical transliterations from streamed transcript text before it
 * reaches the UI. Idempotent on clean strings.
 */
export function sanitizeText(raw: string): string {
  const stripped = raw
    .replace(/<ctrl\d+>/gi, "")        // e.g. <ctrl46> — Gemini internal token
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufeff]/g, "") // non-printable
  return stripParentheticalTransliterations(stripped)
}

/** Encode an ArrayBuffer of PCM data to base64. */
export function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ""
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return window.btoa(binary)
}
