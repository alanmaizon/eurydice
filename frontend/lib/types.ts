// ── Shared WebSocket message types ──────────────────────────────────────────
// Keep in sync with backend/models.py

// Client → Server
export type ClientMessage =
  | { type: "session.start"; config: SessionConfig }
  | { type: "session.end" }
  | { type: "input.text"; text: string }
  | { type: "input.audio"; audio: string } // base64 PCM 16-bit 16kHz mono
  | { type: "input.image"; image: string; mime_type: string }
  | { type: "input.interrupt" }

export interface SessionConfig {
  system_instruction: string
  voice?: string
}

// Server → Client
export type ServerMessage =
  | { type: "session.started"; session_id: string }
  | { type: "session.ended" }
  | { type: "output.text.delta"; delta: string }
  | { type: "output.text.done"; full_text: string }
  | { type: "output.audio.delta"; audio: string }
  | { type: "output.audio.done" }
  | { type: "tool.call"; tool_name: string; args: Record<string, unknown>; call_id: string }
  | { type: "tool.result"; call_id: string; result: unknown }
  | { type: "error"; message: string; code?: string }
  | { type: "status"; state: ConnectionState }
  | { type: "log"; event: string; data?: unknown; timestamp?: string }

export type ConnectionState = "idle" | "connecting" | "live" | "error" | "ended"

// ── Transcript ────────────────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant" | "system"

export interface TranscriptMessage {
  id: string
  role: MessageRole
  content: string
  isStreaming?: boolean
  interrupted?: boolean
  timestamp: Date
  image?: string       // base64 data URL for inline images
  mimeType?: string
  // Tool result cards — at most one is set per message
  // Logos tools
  parseResult?: ParseResult
  lexiconResult?: LexiconResult
  scanResult?: ScansionResult
  // Eurydice tools
  audioAnalysisResult?: AudioAnalysisResult
  visionAnalysisResult?: VisionAnalysisResult
}

// ── Tool results ──────────────────────────────────────────────────────────────

export interface ParseResult {
  word: string
  lemma: string
  transliteration: string
  part_of_speech: string
  tense?: string
  voice?: string
  mood?: string
  person?: string
  number?: string
  gender?: string
  case?: string
  degree?: string
  definition: string
  principal_parts?: string
  ipa?: string
  notes?: string
}

export interface LexiconResult {
  lemma: string
  transliteration?: string
  part_of_speech: string
  definitions: (string | Record<string, unknown>)[]
  usage?: string
  key_refs?: string[]
  principal_parts?: string
}

export interface ScansionFoot {
  foot: number
  syllables: string
  pattern: string
  type: string
  notes?: string
}

export interface ScansionResult {
  line: string
  meter: string
  pattern: string
  analysis: string | ScansionFoot[]
}

// ── Eurydice tool results ──────────────────────────────────────────────────────

export interface PerformanceScores {
  timing: number   // 0–1
  notes: number    // 0–1
  overall: number  // 0–1
}

export interface NoteEvent {
  onset_s: number
  offset_s: number
  midi: number
  confidence?: number
}

export interface AudioAnalysisResult {
  mode: "quick" | "deep"
  tempo_bpm?: number
  tempo_confidence?: number
  performance_scores?: PerformanceScores
  note_events?: NoteEvent[]
  alignment?: {
    mean_onset_error_ms?: number
    max_onset_error_ms?: number
    note_f1?: number
  }
  warnings?: string[]
  _note?: string
}

export interface TechniqueFlag {
  flag: string
  severity: "low" | "medium" | "high"
  confidence: number
  description?: string
}

export interface VisionAnalysisResult {
  hands_detected: number
  handedness?: string[]
  technique_flags?: TechniqueFlag[]
  capture_warnings?: string[]
  _note?: string
}

// ── Inspector ─────────────────────────────────────────────────────────────────

export interface InspectorEvent {
  id: string
  timestamp: Date
  event: string
  data?: unknown
}

export interface ToolCallRecord {
  id: string
  callId: string
  toolName: string
  args: Record<string, unknown>
  result?: unknown
  timestamp: Date
}

// ── Feature E: Difficulty ─────────────────────────────────────────────────────

export type DifficultyLevel = "beginner" | "intermediate" | "advanced"

// ── Session state ─────────────────────────────────────────────────────────────

export interface SessionState {
  connectionState: ConnectionState
  sessionId: string | null
  transcript: TranscriptMessage[]
  inspectorEvents: InspectorEvent[]
  toolCalls: ToolCallRecord[]
  isAssistantStreaming: boolean
  elapsedSeconds: number
  tokenCount: number
  /** Feature D: text of the currently pinned passage for close reading */
  pinnedPassage: string | null
  /** Feature E: current learner difficulty level */
  difficultyLevel: DifficultyLevel
}
