import { LiveClientToolResponse, LiveConnectConfig, Part } from "@google/genai";
import { EventEmitter } from "eventemitter3";
import {
  BackendServerEvent,
  ClientContentLog,
  LiveClientOptions,
  LocalModelContent,
  RuntimeSnapshot,
  ServerAudioOutputEvent,
  ServerErrorEvent,
  ServerTextOutputEvent,
  ServerToolCallEvent,
  ServerTurnEvent,
  StreamingLog,
} from "../types";
import { base64ToArrayBuffer } from "./utils";

export interface LiveClientEventTypes {
  audio: (data: ArrayBuffer) => void;
  backendevent: (event: BackendServerEvent) => void;
  close: (event: CloseEvent) => void;
  content: (data: LocalModelContent) => void;
  error: (error: ErrorEvent) => void;
  interrupted: () => void;
  log: (log: StreamingLog) => void;
  open: () => void;
  setupcomplete: () => void;
  toolcall: (toolCall: ServerToolCallEvent) => void;
  toolcallcancellation: (toolcallCancellation: { ids: string[] }) => void;
  turncomplete: () => void;
}

const DEFAULT_RUNTIME_PATH = "/api/runtime";
const DEFAULT_WEBSOCKET_PATH = "/ws/live";
const DEFAULT_MODE = "guided_reading";

type OutboundChunk = {
  mimeType: string;
  data: string;
};

function buildHttpUrl(path: string, baseUrl?: string): string {
  if (/^https?:\/\//.test(path)) {
    return path;
  }

  if (baseUrl) {
    const resolvedBase = new URL(baseUrl, window.location.origin);
    return new URL(
      path,
      resolvedBase.toString().endsWith("/")
        ? resolvedBase.toString()
        : `${resolvedBase.toString()}/`
    ).toString();
  }

  return new URL(path, window.location.origin).toString();
}

function buildWebSocketUrl(path: string, baseUrl?: string, explicitUrl?: string): string {
  if (explicitUrl) {
    return explicitUrl;
  }

  if (/^wss?:\/\//.test(path)) {
    return path;
  }

  const resolvedBase = baseUrl
    ? new URL(baseUrl, window.location.origin)
    : new URL(window.location.origin);
  const protocol = resolvedBase.protocol === "https:" ? "wss:" : "ws:";
  return new URL(path, `${protocol}//${resolvedBase.host}`).toString();
}

function createErrorEvent(message: string): ErrorEvent {
  return new ErrorEvent("error", { message });
}

function normalizeParts(parts: Part | Part[]): Part[] {
  return Array.isArray(parts) ? parts : [parts];
}

function textParts(parts: Part[]): Part[] {
  return parts.filter((part) => typeof part.text === "string" && part.text.trim().length > 0);
}

export class GenAILiveClient extends EventEmitter<LiveClientEventTypes> {
  private socket: WebSocket | null = null;
  private pingIntervalId: number | null = null;
  private activeRealtimeTurnId: string | null = null;
  private audioChunkIndex = 0;
  private imageFrameIndex = 0;
  private runtimeSnapshot: RuntimeSnapshot | null = null;
  private turnSequence = 0;
  private setupComplete = false;

  private _status: "connected" | "disconnected" | "connecting" = "disconnected";
  public get status() {
    return this._status;
  }

  private _model: string | null = null;
  public get model() {
    return this._model;
  }

  protected config: LiveConnectConfig | null = null;

  public getConfig() {
    return { ...this.config };
  }

  constructor(private readonly options: LiveClientOptions) {
    super();
    this.send = this.send.bind(this);
  }

  protected log(type: string, message: StreamingLog["message"]) {
    const log: StreamingLog = {
      date: new Date(),
      type,
      message,
    };
    this.emit("log", log);
  }

  async fetchRuntimeSnapshot(force = false): Promise<RuntimeSnapshot | null> {
    if (this.runtimeSnapshot && !force) {
      return this.runtimeSnapshot;
    }

    const runtimeUrl = buildHttpUrl(
      this.options.runtimeUrl || DEFAULT_RUNTIME_PATH,
      this.options.apiBaseUrl
    );
    const response = await fetch(runtimeUrl, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Runtime request failed with status ${response.status}`);
    }
    const payload = (await response.json()) as RuntimeSnapshot;
    this.runtimeSnapshot = payload;
    return payload;
  }

  async connect(model: string, config: LiveConnectConfig): Promise<boolean> {
    if (this._status === "connected" || this._status === "connecting") {
      return false;
    }

    this._status = "connecting";
    this._model = model;
    this.config = config;
    this.setupComplete = false;

    let runtime: RuntimeSnapshot | null = null;
    try {
      runtime = await this.fetchRuntimeSnapshot();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed loading backend runtime";
      this._status = "disconnected";
      this.emit("error", createErrorEvent(message));
      this.log("client.error", message);
      return false;
    }

    const websocketPath = runtime?.websocket_path || DEFAULT_WEBSOCKET_PATH;
    const websocketUrl = buildWebSocketUrl(
      websocketPath,
      this.options.apiBaseUrl,
      this.options.websocketUrl
    );

    return await new Promise<boolean>((resolve) => {
      const socket = new WebSocket(websocketUrl);
      let settled = false;

      socket.addEventListener("open", () => {
        this.socket = socket;
        this._status = "connected";
        this.audioChunkIndex = 0;
        this.imageFrameIndex = 0;
        this.activeRealtimeTurnId = null;
        this.log("client.hello", {
          hasGeminiApiKey: Boolean(this.options.geminiApiKey),
          mode: this.options.mode || runtime?.default_mode || DEFAULT_MODE,
          targetTextPresent: Boolean(this.options.targetText),
        });
        this.sendJson({
          type: "client.hello",
          session_id: null,
          mode: this.options.mode || runtime?.default_mode || DEFAULT_MODE,
          target_text: this.options.targetText,
          preferred_response_language:
            this.options.preferredResponseLanguage || "English",
          gemini_api_key: this.options.geminiApiKey,
          client_name: this.options.clientName || "live-api-web-console",
          capabilities: {
            audio_input: true,
            audio_output: true,
            image_input: true,
            supports_barge_in: true,
          },
        });
        this.startPingLoop();
        this.log("client.open", `Connected to ${websocketUrl}`);
        this.emit("open");
        if (!settled) {
          settled = true;
          resolve(true);
        }
      });

      socket.addEventListener("message", (event) => {
        this.onmessage(event);
      });

      socket.addEventListener("error", () => {
        const errorEvent = createErrorEvent("Live websocket error");
        this.emit("error", errorEvent);
        this.log("server.error", errorEvent.message);
        if (!settled) {
          settled = true;
          this._status = "disconnected";
          resolve(false);
        }
      });

      socket.addEventListener("close", (event) => {
        this.stopPingLoop();
        this.socket = null;
        this.activeRealtimeTurnId = null;
        this._status = "disconnected";
        this.log(
          "server.close",
          `disconnected ${event.reason ? `with reason: ${event.reason}` : ""}`.trim()
        );
        this.emit("close", event);
        if (!settled) {
          settled = true;
          resolve(false);
        }
      });
    });
  }

  public disconnect() {
    this.endRealtimeTurn();
    this.stopPingLoop();
    if (!this.socket) {
      this._status = "disconnected";
      return false;
    }
    this.socket.close(1000, "client disconnect");
    this.socket = null;
    this._status = "disconnected";
    this.log("client.close", "Disconnected");
    return true;
  }

  public endRealtimeTurn(reason: "done" | "stop_recording" = "stop_recording") {
    if (!this.activeRealtimeTurnId) {
      return;
    }
    this.sendJson({
      type: "client.turn.end",
      turn_id: this.activeRealtimeTurnId,
      reason,
    });
    this.activeRealtimeTurnId = null;
    this.audioChunkIndex = 0;
    this.imageFrameIndex = 0;
  }

  sendRealtimeInput(chunks: OutboundChunk[]) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    if (!this.activeRealtimeTurnId) {
      this.activeRealtimeTurnId = this.nextTurnId("media");
      this.audioChunkIndex = 0;
      this.imageFrameIndex = 0;
    }

    let hasAudio = false;
    let hasVideo = false;

    chunks.forEach((chunk) => {
      if (chunk.mimeType.startsWith("audio/")) {
        hasAudio = true;
        this.sendJson({
          type: "client.input.audio",
          turn_id: this.activeRealtimeTurnId,
          chunk_index: this.audioChunkIndex,
          mime_type: chunk.mimeType,
          data_base64: chunk.data,
          is_final_chunk: false,
        });
        this.audioChunkIndex += 1;
        return;
      }

      if (chunk.mimeType.startsWith("image/")) {
        hasVideo = true;
        this.sendJson({
          type: "client.input.image",
          turn_id: this.activeRealtimeTurnId,
          frame_index: this.imageFrameIndex,
          mime_type: chunk.mimeType,
          source: "camera_frame",
          data_base64: chunk.data,
          is_reference: false,
        });
        this.imageFrameIndex += 1;
      }
    });

    const description =
      hasAudio && hasVideo
        ? "audio + video"
        : hasAudio
        ? "audio"
        : hasVideo
        ? "video"
        : "unknown";
    this.log("client.realtimeInput", description);
  }

  sendToolResponse(toolResponse: LiveClientToolResponse) {
    if (
      toolResponse.functionResponses &&
      toolResponse.functionResponses.length > 0
    ) {
      this.log("client.toolResponse", {
        ignored: true,
        reason: "Backend-owned tools do not accept browser-side tool responses.",
      });
    }
  }

  send(parts: Part | Part[], turnComplete = true) {
    const normalizedParts = normalizeParts(parts);
    const contentLog: ClientContentLog = {
      turns: normalizedParts,
      turnComplete,
    };
    this.log("client.send", contentLog);

    const text = textParts(normalizedParts)
      .map((part) => part.text?.trim() || "")
      .filter(Boolean)
      .join("\n");

    if (!text || !this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    const turnId = this.nextTurnId("text");
    this.sendJson({
      type: "client.input.text",
      turn_id: turnId,
      text,
      source: "typed",
      is_final: true,
    });

    if (turnComplete) {
      this.sendJson({
        type: "client.turn.end",
        turn_id: turnId,
        reason: "submit_click",
      });
    }
  }

  private onmessage(event: MessageEvent<string>) {
    let parsed: BackendServerEvent;
    try {
      parsed = JSON.parse(event.data) as BackendServerEvent;
    } catch (_error) {
      this.log("server.invalid", event.data);
      return;
    }

    this.emit("backendevent", parsed);
    this.log("server.receive", {
      eventType: parsed.type,
      payload: parsed,
    });

    switch (parsed.type) {
      case "server.ready":
        if (!this.setupComplete) {
          this.setupComplete = true;
          this.emit("setupcomplete");
        }
        return;
      case "server.output.audio":
        this.handleAudioOutput(parsed);
        return;
      case "server.output.text":
        this.handleTextOutput(parsed);
        return;
      case "server.tool.call":
        this.emit("toolcall", parsed);
        return;
      case "server.turn":
        this.handleTurnEvent(parsed);
        return;
      case "server.error":
        this.handleServerError(parsed);
        return;
      default:
        return;
    }
  }

  private handleAudioOutput(event: ServerAudioOutputEvent) {
    const data = base64ToArrayBuffer(event.data_base64);
    this.emit("audio", data);
    this.log("server.audio", `buffer (${data.byteLength})`);
  }

  private handleTextOutput(event: ServerTextOutputEvent) {
    const content: LocalModelContent = {
      modelTurn: {
        parts: [{ text: event.text } as Part],
      },
      turnComplete: event.is_final,
    };
    this.emit("content", content);
    if (event.is_final) {
      this.emit("turncomplete");
    }
  }

  private handleTurnEvent(event: ServerTurnEvent) {
    if (event.event === "interrupted") {
      this.emit("interrupted");
      return;
    }
    if (event.event === "turn_complete" || event.event === "generation_complete") {
      this.emit("turncomplete");
    }
  }

  private handleServerError(event: ServerErrorEvent) {
    if (event.retryable) {
      this.log("server.notice", {
        eventType: event.type,
        payload: event,
      });
      return;
    }
    const errorEvent = createErrorEvent(event.message);
    this.emit("error", errorEvent);
  }

  private sendPing() {
    this.sendJson({
      type: "client.control.ping",
      client_time: new Date().toISOString(),
    });
  }

  private startPingLoop() {
    this.stopPingLoop();
    this.pingIntervalId = window.setInterval(() => {
      this.sendPing();
    }, 15000);
  }

  private stopPingLoop() {
    if (this.pingIntervalId !== null) {
      window.clearInterval(this.pingIntervalId);
      this.pingIntervalId = null;
    }
  }

  private sendJson(payload: Record<string, unknown>) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return;
    }
    this.socket.send(JSON.stringify(payload));
  }

  private nextTurnId(prefix: string) {
    this.turnSequence += 1;
    return `${prefix}-${Date.now()}-${this.turnSequence}`;
  }
}
