/**
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GenAILiveClient } from "../lib/genai-live-client";
import {
  BackendServerEvent,
  LiveClientOptions,
  RuntimeSnapshot,
  SessionStatus,
  TranscriptEntry,
} from "../types";
import { AudioStreamer } from "../lib/audio-streamer";
import { audioContext } from "../lib/utils";
import VolMeterWorket from "../lib/worklets/vol-meter";
import { LiveConnectConfig } from "@google/genai";
import { useLoggerStore } from "../lib/store-logger";

export type UseLiveAPIResults = {
  client: GenAILiveClient;
  setConfig: (config: LiveConnectConfig) => void;
  config: LiveConnectConfig;
  model: string;
  setModel: (model: string) => void;
  connected: boolean;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  volume: number;
  runtime: RuntimeSnapshot | null;
  runtimeError: string | null;
  sessionId: string | null;
  status: SessionStatus | null;
  transcript: TranscriptEntry[];
  clearTranscript: () => void;
};

function mergeTranscriptText(previousText: string, incomingText: string) {
  const previous = previousText.trim();
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

export function useLiveAPI(options: LiveClientOptions): UseLiveAPIResults {
  const client = useMemo(() => new GenAILiveClient(options), [options]);
  const audioStreamerRef = useRef<AudioStreamer | null>(null);

  const [model, setModel] = useState<string>("models/gemini-2.0-flash-exp");
  const [config, setConfig] = useState<LiveConnectConfig>({});
  const [connected, setConnected] = useState(false);
  const [volume, setVolume] = useState(0);
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);

  // register audio for streaming server -> speakers
  useEffect(() => {
    if (!audioStreamerRef.current) {
      audioContext({ id: "audio-out" }).then((audioCtx: AudioContext) => {
        audioStreamerRef.current = new AudioStreamer(audioCtx);
        audioStreamerRef.current
          .addWorklet<any>("vumeter-out", VolMeterWorket, (ev: any) => {
            setVolume(ev.data.volume);
          })
          .then(() => {
            // Successfully added worklet
        });
      });
    }
  }, [audioStreamerRef]);

  useEffect(() => {
    let cancelled = false;

    client
      .fetchRuntimeSnapshot()
      .then((snapshot) => {
        if (cancelled) {
          return;
        }
        setRuntime(snapshot);
        setRuntimeError(null);
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        const message =
          error instanceof Error ? error.message : "Failed loading backend runtime";
        setRuntimeError(message);
      });

    return () => {
      cancelled = true;
    };
  }, [client]);

  useEffect(() => {
    const { clearLogs } = useLoggerStore.getState();
    const resumeAudioStreamer = () => {
      void audioStreamerRef.current?.resume();
    };

    const onOpen = () => {
      setConnected(true);
      clearLogs();
      setTranscript([]);
      resumeAudioStreamer();
      setStatus({
        phase: "connected",
        detail: "Socket open. Waiting for backend session handshake.",
      });
    };

    const onClose = () => {
      audioStreamerRef.current?.stop();
      setConnected(false);
      setStatus({
        phase: "closed",
        detail: "Disconnected from the live backend.",
      });
    };

    const onError = (error: ErrorEvent) => {
      console.error("error", error);
      audioStreamerRef.current?.stop();
      setStatus({
        phase: "error",
        detail: error.message || "Live session error",
      });
    };

    const stopAudioOutput = () => {
      audioStreamerRef.current?.stop();
    };
    const completeAudioStreamer = () => audioStreamerRef.current?.complete();

    const onAudio = (data: ArrayBuffer) => {
      const streamer = audioStreamerRef.current;
      if (!streamer) {
        return;
      }
      void streamer.resume().then(() => {
        streamer.addPCM16(new Uint8Array(data));
      });
    };

    const onBackendEvent = (event: BackendServerEvent) => {
      if ("session_id" in event && typeof event.session_id === "string") {
        setSessionId(event.session_id);
      }

      switch (event.type) {
        case "server.status":
          setStatus({
            phase: event.phase,
            detail: event.detail,
            turnId: event.turn_id,
          });
          return;
        case "server.transcript":
          setSessionId(event.session_id);
          setTranscript((previous) => {
            const entryId = `${event.turn_id}:${event.speaker}`;
            const existing = previous.find((entry) => entry.id === entryId);
            const nextEntry: TranscriptEntry = {
              id: entryId,
              turnId: event.turn_id,
              speaker: event.speaker,
              text: existing
                ? mergeTranscriptText(existing.text, event.text)
                : event.text,
              source: event.source,
              isFinal: event.is_final,
            };

            if (!existing) {
              return [...previous, nextEntry];
            }

            return previous.map((entry) =>
              entry.id === entryId
                ? {
                    ...nextEntry,
                    isFinal: entry.isFinal || nextEntry.isFinal,
                  }
                : entry
            );
          });
          return;
        case "server.tool.call":
          setTranscript((previous) => [
            ...previous,
            {
              id: `tool-call:${event.tool_call_id}`,
              turnId: event.turn_id,
              speaker: "system",
              text: `Tool call: ${event.tool_name}`,
              source: event.type,
              isFinal: true,
            },
          ]);
          return;
        case "server.tool.result":
          setTranscript((previous) => [
            ...previous,
            {
              id: `tool-result:${event.tool_call_id}:${event.status}`,
              turnId: event.turn_id,
              speaker: "system",
              text:
                event.status === "completed"
                  ? `Tool result: ${event.tool_name}`
                  : `Tool failed: ${event.tool_name}`,
              source: event.type,
              isFinal: true,
            },
          ]);
          return;
        case "server.error":
          setTranscript((previous) => [
            ...previous,
            {
              id: `error:${event.code}:${previous.length}`,
              turnId:
                typeof event.detail?.turn_id === "string"
                  ? event.detail.turn_id
                  : "system",
              speaker: "system",
              text: `Error: ${event.message}`,
              source: event.type,
              isFinal: true,
            },
          ]);
          setStatus({
            phase: "error",
            detail: event.message,
          });
          return;
        case "server.output.text":
          return;
        case "server.output.audio":
          return;
        case "server.turn":
          if (event.event === "turn_complete" || event.event === "generation_complete") {
            setStatus({
              phase: "listening",
              detail: "Turn complete. Ready for the next learner message.",
              turnId: event.turn_id,
            });
          }
          return;
        default:
          return;
      }
    };

    client
      .on("error", onError)
      .on("open", onOpen)
      .on("close", onClose)
      .on("interrupted", stopAudioOutput)
      .on("turncomplete", completeAudioStreamer)
      .on("audio", onAudio)
      .on("backendevent", onBackendEvent);

    return () => {
      client
        .off("error", onError)
        .off("open", onOpen)
        .off("close", onClose)
        .off("interrupted", stopAudioOutput)
        .off("turncomplete", completeAudioStreamer)
        .off("audio", onAudio)
        .off("backendevent", onBackendEvent)
        .disconnect();
    };
  }, [client]);

  const connect = useCallback(async () => {
    if (!config) {
      throw new Error("config has not been set");
    }
    client.disconnect();
    await client.connect(model, config);
  }, [client, config, model]);

  const disconnect = useCallback(async () => {
    client.disconnect();
    setConnected(false);
  }, [setConnected, client]);

  return {
    client,
    config,
    setConfig,
    model,
    setModel,
    connected,
    connect,
    disconnect,
    volume,
    runtime,
    runtimeError,
    sessionId,
    status,
    transcript,
    clearTranscript: () => setTranscript([]),
  };
}
