import { startTransition, useEffect, useRef, useState } from "react";

import {
  INPUT_AUDIO_MIME_TYPE,
  LIVE_PROTOCOL_VERSION,
  type ClientAudioInputEvent,
  type ClientHelloEvent,
  type ClientImageInputEvent,
  type ClientInterruptEvent,
  type ClientPingEvent,
  type ClientTextInputEvent,
  type ClientTurnEndEvent,
  type LiveServerEvent,
  type ServerAudioOutputEvent,
  type ServerTranscriptEvent,
} from "../live-protocol";
import { resolveLiveWebSocketUrl } from "../lib/api";
import type { SessionBootstrapResponse } from "../types";

export type LiveConnectionState = "idle" | "connecting" | "connected" | "error";

export interface TranscriptEntry {
  id: string;
  speaker: "learner" | "tutor" | "system";
  text: string;
  source: string;
  turnId: string | null;
  isFinal: boolean;
}

interface UseLiveAgentOptions {
  preferredResponseLanguage: string;
  session: SessionBootstrapResponse | null;
}

const MAX_TRANSCRIPT_ENTRIES = 300;
const DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE = 24000;

function trimTranscriptEntries(entries: TranscriptEntry[]) {
  if (entries.length <= MAX_TRANSCRIPT_ENTRIES) {
    return entries;
  }
  return entries.slice(entries.length - MAX_TRANSCRIPT_ENTRIES);
}

function mergeStreamingText(previousText: string, incomingText: string) {
  const previous = previousText.trimEnd();
  const incoming = incomingText.trim();

  if (!previous) {
    return incoming;
  }
  if (!incoming) {
    return previous;
  }
  if (incoming.startsWith(previous)) {
    return incoming;
  }
  if (previous.endsWith(incoming)) {
    return previous;
  }
  if (/^[,.;:!?)]/.test(incoming) || /[\s([{"'`-]$/.test(previous)) {
    return `${previous}${incoming}`;
  }
  return `${previous} ${incoming}`;
}

function parseAudioRate(mimeType: string) {
  const match = /rate=(\d+)/i.exec(mimeType);
  if (!match) {
    return DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE;
  }
  const parsed = Number.parseInt(match[1], 10);
  if (Number.isNaN(parsed) || parsed < 1000) {
    return DEFAULT_OUTPUT_AUDIO_SAMPLE_RATE;
  }
  return parsed;
}

function decodePcm16Base64(dataBase64: string) {
  const binary = atob(dataBase64);
  if (binary.length < 2) {
    return new Float32Array(0);
  }
  const sampleCount = Math.floor(binary.length / 2);
  const samples = new Float32Array(sampleCount);

  for (let index = 0; index < sampleCount; index += 1) {
    const byteOffset = index * 2;
    const low = binary.charCodeAt(byteOffset);
    const high = binary.charCodeAt(byteOffset + 1);
    let sample = (high << 8) | low;
    if (sample >= 0x8000) {
      sample -= 0x10000;
    }
    samples[index] = sample / 32768;
  }

  return samples;
}

function isLiveServerEvent(payload: unknown): payload is LiveServerEvent {
  return Boolean(
    payload &&
      typeof payload === "object" &&
      "type" in payload &&
      typeof (payload as { type?: unknown }).type === "string",
  );
}

export function useLiveAgent({ preferredResponseLanguage, session }: UseLiveAgentOptions) {
  const [connectionState, setConnectionState] = useState<LiveConnectionState>("idle");
  const [connectionDetail, setConnectionDetail] = useState("Start a session to enable live tutor.");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [transcriptEntries, setTranscriptEntries] = useState<TranscriptEntry[]>([]);

  const socketRef = useRef<WebSocket | null>(null);
  const entryCounterRef = useRef(0);
  const turnCounterRef = useRef(0);
  const intentionalCloseRef = useRef(false);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const thinkingTurnsRef = useRef<Set<string>>(new Set());
  const activeTutorTurnIdRef = useRef<string | null>(null);
  const audioTranscriptTurnsRef = useRef<Set<string>>(new Set());
  const streamedOutputTextTurnsRef = useRef<Set<string>>(new Set());
  const pendingOutputTextByTurnRef = useRef<Map<string, string>>(new Map());
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioCursorTimeRef = useRef(0);

  function stopPingLoop() {
    if (pingIntervalRef.current !== null) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }

  function appendTranscriptEntry(entry: Omit<TranscriptEntry, "id">) {
    const id = `entry-${Date.now()}-${entryCounterRef.current++}`;
    startTransition(() => {
      setTranscriptEntries((current) => {
        const next = [...current, { ...entry, id }];
        return trimTranscriptEntries(next);
      });
    });
  }

  function upsertTutorTranscript(
    event: Pick<ServerTranscriptEvent, "turn_id" | "source" | "text" | "is_final">,
  ) {
    const nextText = event.text.trim();
    if (!nextText) {
      return;
    }

    startTransition(() => {
      setTranscriptEntries((current) => {
        const entries = [...current];
        for (let index = entries.length - 1; index >= 0; index -= 1) {
          const entry = entries[index];
          if (
            entry.speaker === "tutor" &&
            entry.turnId === event.turn_id &&
            entry.source === event.source
          ) {
            entries[index] = {
              ...entry,
              text: mergeStreamingText(entry.text, nextText),
              isFinal: event.is_final,
            };
            return entries;
          }
        }

        const id = `entry-${Date.now()}-${entryCounterRef.current++}`;
        entries.push({
          id,
          speaker: "tutor",
          text: nextText,
          source: event.source,
          turnId: event.turn_id,
          isFinal: event.is_final,
        });
        return trimTranscriptEntries(entries);
      });
    });
  }

  function dropTutorOutputTextEntries(turnId: string) {
    startTransition(() => {
      setTranscriptEntries((current) =>
        current.filter(
          (entry) =>
            !(
              entry.speaker === "tutor" &&
              entry.turnId === turnId &&
              entry.source === "output_text"
            ),
        ),
      );
    });
  }

  function settleTutorTurn(turnId: string, options?: { markPendingTextFinal?: boolean }) {
    if (activeTutorTurnIdRef.current === turnId) {
      activeTutorTurnIdRef.current = null;
    }
    thinkingTurnsRef.current.delete(turnId);

    const pendingText = pendingOutputTextByTurnRef.current.get(turnId);
    if (
      options?.markPendingTextFinal !== false &&
      pendingText &&
      !audioTranscriptTurnsRef.current.has(turnId)
    ) {
      upsertTutorTranscript({
        turn_id: turnId,
        source: "output_text",
        text: pendingText,
        is_final: true,
      });
    }

    pendingOutputTextByTurnRef.current.delete(turnId);
    audioTranscriptTurnsRef.current.delete(turnId);
    streamedOutputTextTurnsRef.current.delete(turnId);
  }

  function ensureAudioContext() {
    if (typeof window === "undefined") {
      return null;
    }
    const browserWindow = window as Window & {
      AudioContext?: typeof AudioContext;
      webkitAudioContext?: typeof AudioContext;
    };
    const AudioContextConstructor = browserWindow.AudioContext ?? browserWindow.webkitAudioContext;
    if (!AudioContextConstructor) {
      return null;
    }
    if (!audioContextRef.current) {
      const audioContext = new AudioContextConstructor();
      audioContextRef.current = audioContext;
      audioCursorTimeRef.current = audioContext.currentTime;
    }
    return audioContextRef.current;
  }

  function queueAudioPlayback(event: ServerAudioOutputEvent) {
    if (!event.mime_type.startsWith("audio/pcm")) {
      return;
    }
    const audioContext = ensureAudioContext();
    if (!audioContext) {
      return;
    }
    if (audioContext.state === "suspended") {
      void audioContext.resume();
    }

    const samples = decodePcm16Base64(event.data_base64);
    if (samples.length === 0) {
      return;
    }

    const buffer = audioContext.createBuffer(1, samples.length, parseAudioRate(event.mime_type));
    buffer.copyToChannel(samples, 0);

    const sourceNode = audioContext.createBufferSource();
    sourceNode.buffer = buffer;
    sourceNode.connect(audioContext.destination);

    const startAt = Math.max(audioContext.currentTime + 0.02, audioCursorTimeRef.current);
    sourceNode.start(startAt);
    audioCursorTimeRef.current = startAt + buffer.duration;
  }

  function closeAudioContext() {
    if (!audioContextRef.current) {
      return;
    }
    void audioContextRef.current.close().catch(() => {
      // Ignore close races during rapid connect/disconnect.
    });
    audioContextRef.current = null;
    audioCursorTimeRef.current = 0;
  }

  function disconnect() {
    intentionalCloseRef.current = true;
    stopPingLoop();
    thinkingTurnsRef.current.clear();
    activeTutorTurnIdRef.current = null;
    audioTranscriptTurnsRef.current.clear();
    streamedOutputTextTurnsRef.current.clear();
    pendingOutputTextByTurnRef.current.clear();
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
    closeAudioContext();
    setConnectionState("idle");
    setConnectionDetail(session ? "Disconnected from live tutor." : "Start a session to enable live tutor.");
  }

  function maybeInterruptActiveTutorTurn(socket: WebSocket) {
    const activeTutorTurnId = activeTutorTurnIdRef.current;
    if (!activeTutorTurnId) {
      return;
    }

    const interruptEvent: ClientInterruptEvent = {
      type: "client.control.interrupt",
      protocol_version: LIVE_PROTOCOL_VERSION,
      turn_id: activeTutorTurnId,
      reason: "barge_in",
    };

    socket.send(JSON.stringify(interruptEvent));
    activeTutorTurnIdRef.current = null;
  }

  function connect() {
    if (!session) {
      setConnectionError("Start a tutor session before joining live.");
      return;
    }

    disconnect();
    intentionalCloseRef.current = false;
    setConnectionError(null);
    setConnectionState("connecting");
    setConnectionDetail("Connecting to live tutor...");

    const websocketUrl = resolveLiveWebSocketUrl(session.live_session.websocket_path);
    const socket = new WebSocket(websocketUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      setConnectionState("connected");
      setConnectionDetail("Connected. Sending live handshake...");
      const audioContext = ensureAudioContext();
      if (audioContext && audioContext.state === "suspended") {
        void audioContext.resume();
      }

      const helloEvent: ClientHelloEvent = {
        type: "client.hello",
        protocol_version: LIVE_PROTOCOL_VERSION,
        session_id: session.session_id,
        mode: session.mode,
        target_text: session.session_state.target_text ?? undefined,
        preferred_response_language: preferredResponseLanguage,
        capabilities: {
          audio_input: true,
          audio_output: true,
          image_input: true,
          supports_barge_in: true,
        },
        client_name: "web-frontend",
      };

      socket.send(JSON.stringify(helloEvent));
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      if (typeof event.data !== "string") {
        return;
      }

      let payload: unknown;
      try {
        payload = JSON.parse(event.data) as unknown;
      } catch {
        return;
      }

      if (!isLiveServerEvent(payload)) {
        return;
      }

      switch (payload.type) {
        case "server.ready":
          setConnectionDetail("Socket ready. Waiting for tutor status...");
          return;
        case "server.status":
          if (payload.phase === "speaking" || payload.detail.startsWith("Streaming tutor audio chunk")) {
            setConnectionDetail("Tutor is speaking...");
          } else {
            setConnectionDetail(payload.detail);
          }
          if (payload.phase === "thinking" && payload.turn_id) {
            activeTutorTurnIdRef.current = payload.turn_id;
            if (!thinkingTurnsRef.current.has(payload.turn_id)) {
              thinkingTurnsRef.current.add(payload.turn_id);
              appendTranscriptEntry({
                speaker: "system",
                text: "Thinking...",
                source: "thinking",
                turnId: payload.turn_id,
                isFinal: false,
              });
            }
          }
          return;
        case "server.transcript":
          if (payload.speaker === "tutor") {
            if (payload.source === "output_audio_transcription") {
              if (
                !audioTranscriptTurnsRef.current.has(payload.turn_id) &&
                streamedOutputTextTurnsRef.current.has(payload.turn_id)
              ) {
                dropTutorOutputTextEntries(payload.turn_id);
                streamedOutputTextTurnsRef.current.delete(payload.turn_id);
                pendingOutputTextByTurnRef.current.delete(payload.turn_id);
              }
              audioTranscriptTurnsRef.current.add(payload.turn_id);
              upsertTutorTranscript(payload);
              return;
            }
            if (payload.source === "output_text") {
              const currentText = pendingOutputTextByTurnRef.current.get(payload.turn_id) ?? "";
              pendingOutputTextByTurnRef.current.set(
                payload.turn_id,
                mergeStreamingText(currentText, payload.text),
              );
              if (!audioTranscriptTurnsRef.current.has(payload.turn_id)) {
                streamedOutputTextTurnsRef.current.add(payload.turn_id);
                upsertTutorTranscript(payload);
              }
              return;
            }
            upsertTutorTranscript(payload);
            return;
          }
          appendTranscriptEntry({
            speaker: payload.speaker,
            text: payload.text,
            source: payload.source,
            turnId: payload.turn_id,
            isFinal: payload.is_final,
          });
          return;
        case "server.output.audio":
          queueAudioPlayback(payload);
          return;
        case "server.turn":
          if (
            payload.event === "generation_complete" ||
            payload.event === "turn_complete" ||
            payload.event === "interrupted"
          ) {
            settleTutorTurn(payload.turn_id, {
              markPendingTextFinal: payload.event !== "interrupted",
            });
          }
          return;
        case "server.tool.call":
          appendTranscriptEntry({
            speaker: "system",
            text: `Tool call: ${payload.tool_name}`,
            source: "tool_call",
            turnId: payload.turn_id,
            isFinal: true,
          });
          return;
        case "server.tool.result":
          appendTranscriptEntry({
            speaker: "system",
            text:
              payload.status === "completed"
                ? `Tool result: ${payload.tool_name}`
                : `Tool failed: ${payload.tool_name}`,
            source: "tool_result",
            turnId: payload.turn_id,
            isFinal: true,
          });
          return;
        case "server.error":
          if (payload.code === "TURN_TIMEOUT" || payload.code === "TURN_IN_PROGRESS") {
            setConnectionDetail(payload.message);
            const detailTurnId = payload.detail?.turn_id;
            const activeTurnId = payload.detail?.active_turn_id;
            const relatedTurnId =
              typeof detailTurnId === "string"
                ? detailTurnId
                : typeof activeTurnId === "string"
                  ? activeTurnId
                  : activeTutorTurnIdRef.current;
            if (typeof detailTurnId === "string") {
              settleTutorTurn(detailTurnId);
            }
            if (typeof activeTurnId === "string" && activeTurnId !== detailTurnId) {
              settleTutorTurn(activeTurnId);
            }
            if (!detailTurnId && !activeTurnId && relatedTurnId) {
              settleTutorTurn(relatedTurnId);
            }
            appendTranscriptEntry({
              speaker: "system",
              text: `Error: ${payload.message}`,
              source: payload.code,
              turnId: relatedTurnId ?? null,
              isFinal: true,
            });
            return;
          } else {
            setConnectionError(payload.message);
            setConnectionState("error");
          }
          appendTranscriptEntry({
            speaker: "system",
            text: `Error: ${payload.message}`,
            source: payload.code,
            turnId: null,
            isFinal: true,
          });
          return;
        default:
          return;
      }
    };

    socket.onerror = () => {
      setConnectionError("Live websocket error. Please reconnect.");
      setConnectionState("error");
    };

    socket.onclose = () => {
      stopPingLoop();
      closeAudioContext();
      socketRef.current = null;

      if (intentionalCloseRef.current) {
        setConnectionState("idle");
        return;
      }

      setConnectionState("error");
      setConnectionDetail("Live tutor connection closed unexpectedly.");
    };
  }

  function sendTextTurn(text: string): boolean {
    const trimmed = text.trim();
    if (!trimmed) {
      return false;
    }

    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setConnectionError("Join live before sending transcript turns.");
      return false;
    }

    maybeInterruptActiveTutorTurn(socket);

    const turnId = createTurnId("turn-ui");
    const textEvent: ClientTextInputEvent = {
      type: "client.input.text",
      protocol_version: LIVE_PROTOCOL_VERSION,
      turn_id: turnId,
      text: trimmed,
      source: "typed",
      is_final: true,
    };
    const turnEndEvent: ClientTurnEndEvent = {
      type: "client.turn.end",
      protocol_version: LIVE_PROTOCOL_VERSION,
      turn_id: turnId,
      reason: "submit_click",
    };

    try {
      socket.send(JSON.stringify(textEvent));
      socket.send(JSON.stringify(turnEndEvent));
      return true;
    } catch {
      setConnectionError("Unable to send learner turn over websocket.");
      return false;
    }
  }

  function createTurnId(prefix = "turn-ui") {
    return `${prefix}-${Date.now()}-${turnCounterRef.current++}`;
  }

  function sendAudioChunk(params: {
    turnId: string;
    chunkIndex: number;
    dataBase64: string;
    isFinalChunk?: boolean;
    mimeType?: string;
  }) {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setConnectionError("Join live before sending microphone audio.");
      return false;
    }

    if (params.chunkIndex === 0) {
      maybeInterruptActiveTutorTurn(socket);
    }

    const audioEvent: ClientAudioInputEvent = {
      type: "client.input.audio",
      protocol_version: LIVE_PROTOCOL_VERSION,
      turn_id: params.turnId,
      chunk_index: params.chunkIndex,
      mime_type: params.mimeType ?? INPUT_AUDIO_MIME_TYPE,
      data_base64: params.dataBase64,
      is_final_chunk: params.isFinalChunk ?? false,
    };

    try {
      socket.send(JSON.stringify(audioEvent));
      return true;
    } catch {
      setConnectionError("Unable to send microphone audio over websocket.");
      return false;
    }
  }

  function sendImageFrame(params: {
    turnId: string;
    frameIndex: number;
    mimeType: "image/jpeg" | "image/png" | "image/webp";
    dataBase64: string;
    source: "camera_frame" | "worksheet_upload";
    width?: number;
    height?: number;
    isReference?: boolean;
  }) {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setConnectionError("Join live before sending image input.");
      return false;
    }

    const imageEvent: ClientImageInputEvent = {
      type: "client.input.image",
      protocol_version: LIVE_PROTOCOL_VERSION,
      turn_id: params.turnId,
      frame_index: params.frameIndex,
      mime_type: params.mimeType,
      source: params.source,
      data_base64: params.dataBase64,
      width: params.width,
      height: params.height,
      is_reference: params.isReference ?? false,
    };

    try {
      socket.send(JSON.stringify(imageEvent));
      return true;
    } catch {
      setConnectionError("Unable to send image input over websocket.");
      return false;
    }
  }

  function endTurn(turnId: string, reason: ClientTurnEndEvent["reason"] = "done") {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setConnectionError("Join live before ending a turn.");
      return false;
    }

    const turnEndEvent: ClientTurnEndEvent = {
      type: "client.turn.end",
      protocol_version: LIVE_PROTOCOL_VERSION,
      turn_id: turnId,
      reason,
    };

    try {
      socket.send(JSON.stringify(turnEndEvent));
      return true;
    } catch {
      setConnectionError("Unable to close the current turn over websocket.");
      return false;
    }
  }

  function clearTranscript() {
    setTranscriptEntries([]);
  }

  useEffect(() => {
    if (connectionState !== "connected") {
      stopPingLoop();
      return;
    }

    pingIntervalRef.current = setInterval(() => {
      const socket = socketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
      }
      const pingEvent: ClientPingEvent = {
        type: "client.control.ping",
        protocol_version: LIVE_PROTOCOL_VERSION,
        client_time: new Date().toISOString(),
      };
      socket.send(JSON.stringify(pingEvent));
    }, 20000);

    return () => {
      stopPingLoop();
    };
  }, [connectionState]);

  useEffect(() => {
    setTranscriptEntries([]);
    setConnectionError(null);
    setConnectionState("idle");
    setConnectionDetail(session ? "Session ready. Join live to begin." : "Start a session to enable live tutor.");
    intentionalCloseRef.current = true;
    thinkingTurnsRef.current.clear();
    activeTutorTurnIdRef.current = null;
    audioTranscriptTurnsRef.current.clear();
    streamedOutputTextTurnsRef.current.clear();
    pendingOutputTextByTurnRef.current.clear();
    stopPingLoop();
    closeAudioContext();
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }
  }, [session?.session_id]);

  useEffect(() => {
    return () => {
      intentionalCloseRef.current = true;
      thinkingTurnsRef.current.clear();
      activeTutorTurnIdRef.current = null;
      audioTranscriptTurnsRef.current.clear();
      streamedOutputTextTurnsRef.current.clear();
      pendingOutputTextByTurnRef.current.clear();
      stopPingLoop();
      closeAudioContext();
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, []);

  return {
    clearTranscript,
    connect,
    connectionDetail,
    connectionError,
    connectionState,
    disconnect,
    endTurn,
    sendTextTurn,
    sendAudioChunk,
    sendImageFrame,
    createTurnId,
    transcriptEntries,
  };
}
