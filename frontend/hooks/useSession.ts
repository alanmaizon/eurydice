"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useWebSocket } from "./useWebSocket"
import { useAudioCapture } from "./useAudioCapture"
import { useCamera } from "./useCamera"
import type {
  ConnectionState,
  DifficultyLevel,
  InspectorEvent,
  LexiconResult,
  ParseResult,
  ScansionResult,
  SessionState,
  ToolCallRecord,
  TranscriptMessage,
  ServerMessage,
} from "@/lib/types"
import { DIFFICULTY_INSTRUCTIONS } from "@/lib/constants"
import { generateId, sanitizeText } from "@/lib/utils"

const INITIAL_STATE: SessionState = {
  connectionState: "idle",
  sessionId: null,
  transcript: [],
  inspectorEvents: [],
  toolCalls: [],
  isAssistantStreaming: false,
  elapsedSeconds: 0,
  tokenCount: 0,
  pinnedPassage: null,
  difficultyLevel: "intermediate",
}

export function useSession() {
  const [state, setState] = useState<SessionState>(INITIAL_STATE)
  const streamingMessageIdRef = useRef<string | null>(null)
  // Maps call_id → tool_name so tool.result knows which card to attach.
  const toolCallNamesRef = useRef<Map<string, string>>(new Map())
  // Holds a tool result that arrived before any text delta for the current turn
  // (i.e. the model called a tool before speaking). Applied to the first message
  // chunk created for this turn. Stores whichever card field is appropriate.
  type PendingToolResult = Pick<TranscriptMessage, "parseResult" | "lexiconResult" | "scanResult">
  const pendingToolResultRef = useRef<PendingToolResult | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const systemInstructionRef = useRef<string>("")
  // Tracks whether the pinned passage has already been forwarded to Gemini in
  // the current session. Reset on each startSession call so a pre-loaded
  // passage is re-sent whenever a new session begins.
  const pinnedPassageSentRef = useRef(false)

  // ── Gapless audio playback ───────────────────────────────────────────────
  // Each incoming PCM chunk is scheduled precisely at the end of the previous
  // one using AudioContext's internal clock, eliminating clicks/pops.
  const audioCtxRef = useRef<AudioContext | null>(null)
  const nextStartTimeRef = useRef(0)
  // Set false on interrupt/endSession so in-flight audio.delta chunks
  // don't recreate the AudioContext after it has been intentionally stopped.
  const playbackEnabledRef = useRef(false)

  const scheduleAudioChunk = useCallback((base64Pcm: string) => {
    if (!playbackEnabledRef.current) return
    try {
      const binary = atob(base64Pcm)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioContext({ sampleRate: 24000 })
      }
      const ctx = audioCtxRef.current
      if (ctx.state === "suspended") ctx.resume()

      const int16 = new Int16Array(bytes.buffer)
      const float32 = new Float32Array(int16.length)
      for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768

      const audioBuffer = ctx.createBuffer(1, float32.length, ctx.sampleRate)
      audioBuffer.copyToChannel(float32, 0)

      const source = ctx.createBufferSource()
      source.buffer = audioBuffer
      source.connect(ctx.destination)

      // Schedule this chunk to start exactly when the previous one ends.
      // Math.max guards against scheduling in the past if there's a gap.
      const startTime = Math.max(ctx.currentTime, nextStartTimeRef.current)
      source.start(startTime)
      nextStartTimeRef.current = startTime + audioBuffer.duration
    } catch {
      // Ignore decode / context errors
    }
  }, [])

  const stopAudio = useCallback(() => {
    playbackEnabledRef.current = false
    audioCtxRef.current?.close()
    audioCtxRef.current = null
    nextStartTimeRef.current = 0
  }, [])

  // ── Inspector ─────────────────────────────────────────────────────────────

  const addInspectorEvent = useCallback((event: string, data?: unknown) => {
    const entry: InspectorEvent = {
      id: generateId(),
      timestamp: new Date(),
      event,
      data,
    }
    setState((s) => ({ ...s, inspectorEvents: [...s.inspectorEvents, entry] }))
  }, [])

  // ── WebSocket message handler ─────────────────────────────────────────────

  const handleMessage = useCallback(
    (msg: ServerMessage) => {
      addInspectorEvent(msg.type, msg)

      switch (msg.type) {
        case "status":
          setState((s) => ({ ...s, connectionState: msg.state as ConnectionState }))
          if (msg.state === "live") {
            playbackEnabledRef.current = true
            startTimer()
          }
          if (msg.state === "ended" || msg.state === "error") {
            playbackEnabledRef.current = false
            stopTimer()
          }
          break

        case "session.started":
          setState((s) => ({ ...s, sessionId: msg.session_id }))
          break

        case "session.ended":
          setState((s) => ({ ...s, connectionState: "ended" }))
          stopTimer()
          break

        case "output.text.delta": {
          const delta = sanitizeText(msg.delta)
          if (!delta) break // nothing left after stripping control chars
          const existingId = streamingMessageIdRef.current
          if (existingId) {
            // Append to the existing streaming message.
            setState((s) => ({
              ...s,
              isAssistantStreaming: true,
              tokenCount: s.tokenCount + 1,
              transcript: s.transcript.map((m) =>
                m.id === existingId ? { ...m, content: m.content + delta } : m
              ),
            }))
          } else {
            // First chunk of a new turn — assign ref BEFORE setState so the
            // updater is pure under React Strict Mode's double-invocation.
            // Also drain any tool result that arrived before this first chunk.
            const newId = generateId()
            streamingMessageIdRef.current = newId
            const pendingTool = pendingToolResultRef.current
            pendingToolResultRef.current = null
            const newMsg: TranscriptMessage = {
              id: newId,
              role: "assistant",
              content: delta,
              isStreaming: true,
              timestamp: new Date(),
              ...(pendingTool ?? {}),
            }
            setState((s) => ({
              ...s,
              isAssistantStreaming: true,
              tokenCount: s.tokenCount + 1,
              transcript: [...s.transcript, newMsg],
            }))
          }
          break
        }

        case "output.text.done": {
          // Capture and clear refs BEFORE setState — pure updater, Strict Mode safe.
          const doneId = streamingMessageIdRef.current
          streamingMessageIdRef.current = null
          pendingToolResultRef.current = null // discard stale pending tool result
          const fullText = sanitizeText(msg.full_text)
          setState((s) => ({
            ...s,
            isAssistantStreaming: false,
            transcript: s.transcript.map((m) =>
              m.id === doneId
                ? { ...m, isStreaming: false, content: fullText }
                : m
            ),
          }))
          break
        }

        case "output.audio.delta":
          scheduleAudioChunk(msg.audio)
          break

        case "output.audio.done":
          // Audio turn complete — streaming indicator can go away even if
          // the text transcription hasn't arrived yet.
          setState((s) => ({ ...s, isAssistantStreaming: false }))
          break

        case "tool.call": {
          toolCallNamesRef.current.set(msg.call_id, msg.tool_name)
          const record: ToolCallRecord = {
            id: generateId(),
            callId: msg.call_id,
            toolName: msg.tool_name,
            args: msg.args,
            timestamp: new Date(),
          }
          setState((s) => ({ ...s, toolCalls: [...s.toolCalls, record] }))
          break
        }

        case "tool.result": {
          const toolName = toolCallNamesRef.current.get(msg.call_id) ?? "parse_greek"
          // Route result to the correct card field based on which tool fired.
          const cardPatch: Pick<TranscriptMessage, "parseResult" | "lexiconResult" | "scanResult"> =
            toolName === "lookup_lexicon"
              ? { lexiconResult: msg.result as LexiconResult }
              : toolName === "scan_meter"
              ? { scanResult: msg.result as ScansionResult }
              : { parseResult: msg.result as ParseResult }

          const currentId = streamingMessageIdRef.current
          if (currentId) {
            // Streaming message already exists — attach card to it.
            setState((s) => ({
              ...s,
              toolCalls: s.toolCalls.map((tc) =>
                tc.callId === msg.call_id ? { ...tc, result: msg.result } : tc
              ),
              transcript: s.transcript.map((m) =>
                m.id === currentId ? { ...m, ...cardPatch } : m
              ),
            }))
          } else {
            // No streaming message yet — the model called the tool before
            // emitting any text. Park the result; it will be applied to
            // the next message chunk in output.text.delta.
            pendingToolResultRef.current = cardPatch
            setState((s) => ({
              ...s,
              toolCalls: s.toolCalls.map((tc) =>
                tc.callId === msg.call_id ? { ...tc, result: msg.result } : tc
              ),
            }))
          }
          break
        }

        case "error":
          setState((s) => ({ ...s, connectionState: "error" }))
          addTranscriptMessage("system", `Error: ${msg.message}`)
          stopTimer()
          break

        case "log":
          break
      }
    },
    [scheduleAudioChunk, addInspectorEvent] // eslint-disable-line react-hooks/exhaustive-deps
  )

  const { status: wsStatus, connect, disconnect, send } = useWebSocket({
    onMessage: handleMessage,
    autoReconnect: false,
  })

  // ── Timer ─────────────────────────────────────────────────────────────────
  const startTimer = () => {
    if (timerRef.current) return
    timerRef.current = setInterval(() => {
      setState((s) => ({ ...s, elapsedSeconds: s.elapsedSeconds + 1 }))
    }, 1000)
  }
  const stopTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  useEffect(() => () => stopTimer(), [])

  // ── Transcript helpers ────────────────────────────────────────────────────
  const addTranscriptMessage = (
    role: TranscriptMessage["role"],
    content: string,
    extra?: Partial<TranscriptMessage>
  ) => {
    setState((s) => ({
      ...s,
      transcript: [
        ...s.transcript,
        { id: generateId(), role, content, timestamp: new Date(), ...extra },
      ],
    }))
  }

  // ── Public actions ────────────────────────────────────────────────────────

  const startSession = useCallback(
    (systemInstruction: string, difficulty: DifficultyLevel) => {
      // Append difficulty modifier to the system instruction
      const fullInstruction = systemInstruction + DIFFICULTY_INSTRUCTIONS[difficulty]
      systemInstructionRef.current = fullInstruction
      pinnedPassageSentRef.current = false // allow pre-loaded passage to be sent
      setState((s) => ({
        ...INITIAL_STATE,
        connectionState: "connecting",
        difficultyLevel: difficulty,
        pinnedPassage: s.pinnedPassage, // preserve any pre-loaded passage
      }))
      connect()
    },
    [connect]
  )

  // Send session.start once WS is open
  useEffect(() => {
    if (wsStatus === "open" && state.connectionState === "connecting") {
      send({
        type: "session.start",
        config: { system_instruction: systemInstructionRef.current },
      })
    }
  }, [wsStatus, state.connectionState, send])

  const endSession = useCallback(() => {
    send({ type: "session.end" })
    disconnect()
    stopAudio()
    stopTimer()
    setState((s) => ({ ...s, connectionState: "ended" }))
  }, [send, disconnect, stopAudio])

  const sendText = useCallback(
    (text: string) => {
      addTranscriptMessage("user", text)
      send({ type: "input.text", text })
    },
    [send] // eslint-disable-line react-hooks/exhaustive-deps
  )

  const sendImage = useCallback(
    (base64: string, mimeType = "image/jpeg") => {
      addTranscriptMessage("user", "[Image sent]", {
        image: `data:${mimeType};base64,${base64}`,
        mimeType,
      })
      send({ type: "input.image", image: base64, mime_type: mimeType })
    },
    [send] // eslint-disable-line react-hooks/exhaustive-deps
  )

  const interrupt = useCallback(() => {
    send({ type: "input.interrupt" })
    stopAudio() // Stop any currently playing audio immediately
    // Clear both streaming and pending-tool refs so stale results from the
    // interrupted turn cannot attach to the next assistant message.
    streamingMessageIdRef.current = null
    pendingToolResultRef.current = null
    setState((s) => ({
      ...s,
      isAssistantStreaming: false,
      transcript: s.transcript.map((m) =>
        m.isStreaming ? { ...m, isStreaming: false, interrupted: true } : m
      ),
    }))
  }, [send, stopAudio])

  // ── Feature D: Contextual Passage Mode ───────────────────────────────────

  // If the passage was pinned BEFORE the session started, send it as soon as
  // the session goes live. The ref prevents double-sending if loadPassage
  // already forwarded it in-session.
  useEffect(() => {
    if (
      state.connectionState === "live" &&
      state.pinnedPassage !== null &&
      !pinnedPassageSentRef.current
    ) {
      pinnedPassageSentRef.current = true
      send({
        type: "input.text",
        text: `[Passage loaded for close reading]\n\n${state.pinnedPassage}\n\nPlease acknowledge this passage and stand by for questions about it.`,
      })
      setState((s) =>
        s.pinnedPassage
          ? {
              ...s,
              transcript: [
                ...s.transcript,
                {
                  id: generateId(),
                  role: "user" as const,
                  content: `[Passage loaded for close reading]\n\n${s.pinnedPassage}`,
                  timestamp: new Date(),
                },
              ],
            }
          : s
      )
    }
  }, [state.connectionState, state.pinnedPassage, send])

  const loadPassage = useCallback(
    (text: string) => {
      setState((s) => ({ ...s, pinnedPassage: text }))
      if (state.connectionState === "live") {
        // Send the passage to the model as context
        pinnedPassageSentRef.current = true
        send({
          type: "input.text",
          text: `[Passage loaded for close reading]\n\n${text}\n\nPlease acknowledge this passage and stand by for questions about it.`,
        })
        addTranscriptMessage(
          "user",
          `[Passage loaded for close reading]\n\n${text}`
        )
      }
    },
    [state.connectionState, send] // eslint-disable-line react-hooks/exhaustive-deps
  )

  const clearPassage = useCallback(() => {
    setState((s) => ({ ...s, pinnedPassage: null }))
  }, [])

  // ── Feature E: Adaptive Difficulty ───────────────────────────────────────
  const setDifficulty = useCallback((level: DifficultyLevel) => {
    setState((s) => ({ ...s, difficultyLevel: level }))
  }, [])

  const clearInspector = useCallback(() => {
    setState((s) => ({ ...s, inspectorEvents: [], toolCalls: [] }))
  }, [])

  const audio = useAudioCapture({
    onAudioChunk: useCallback(
      (b64: string) => send({ type: "input.audio", audio: b64 }),
      [send]
    ),
  })

  const camera = useCamera()

  return {
    state,
    wsStatus,
    startSession,
    endSession,
    sendText,
    sendImage,
    interrupt,
    loadPassage,
    clearPassage,
    setDifficulty,
    clearInspector,
    audio,
    camera,
  }
}
