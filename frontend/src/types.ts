import { LiveConnectConfig, Part } from "@google/genai";

export type TutorMode =
  | "guided_reading"
  | "morphology_coach"
  | "translation_support"
  | "oral_reading";

export type LiveClientOptions = {
  apiBaseUrl?: string;
  runtimeUrl?: string;
  websocketUrl?: string;
  clientName?: string;
  mode?: TutorMode;
  targetText?: string;
  preferredResponseLanguage?: string;
};

export type ClientContentLog = {
  turns: Part[];
  turnComplete: boolean;
};

export type RuntimeSnapshot = {
  service_name: string;
  environment: string;
  google_cloud_project?: string | null;
  google_cloud_location: string;
  websocket_path: string;
  live_protocol_version: string;
  default_mode: TutorMode;
  use_google_adk: boolean;
  google_adk_available: boolean;
  google_adk_detail: string;
  google_genai_available: boolean;
  google_genai_detail: string;
  tools: string[];
};

export type TranscriptEntry = {
  id: string;
  turnId: string;
  speaker: "learner" | "tutor" | "system";
  text: string;
  source: string;
  isFinal: boolean;
};

export type SessionStatus = {
  phase: string;
  detail: string;
  turnId?: string | null;
};

type BaseBackendEvent = {
  type: string;
  protocol_version: string;
};

export type ServerReadyEvent = BaseBackendEvent & {
  type: "server.ready";
  connection_id: string;
  websocket_path: string;
};

export type ServerStatusEvent = BaseBackendEvent & {
  type: "server.status";
  phase: string;
  detail: string;
  session_id?: string | null;
  turn_id?: string | null;
};

export type ServerTranscriptEvent = BaseBackendEvent & {
  type: "server.transcript";
  session_id: string;
  turn_id: string;
  speaker: "learner" | "tutor";
  source: string;
  text: string;
  is_final: boolean;
  interrupted?: boolean;
};

export type ServerTextOutputEvent = BaseBackendEvent & {
  type: "server.output.text";
  session_id: string;
  turn_id: string;
  text: string;
  is_final: boolean;
};

export type ServerAudioOutputEvent = BaseBackendEvent & {
  type: "server.output.audio";
  session_id: string;
  turn_id: string;
  chunk_index: number;
  mime_type: string;
  data_base64: string;
  is_final_chunk: boolean;
};

export type ServerToolCallEvent = BaseBackendEvent & {
  type: "server.tool.call";
  session_id: string;
  turn_id: string;
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: "requested" | "started";
};

export type ServerToolResultEvent = BaseBackendEvent & {
  type: "server.tool.result";
  session_id: string;
  turn_id: string;
  tool_call_id: string;
  tool_name: string;
  status: "completed" | "failed";
  result?: Record<string, unknown> | null;
  error?: string | null;
};

export type ServerTurnEvent = BaseBackendEvent & {
  type: "server.turn";
  session_id: string;
  turn_id: string;
  event: "learner_turn_closed" | "generation_complete" | "turn_complete" | "interrupted";
  detail?: string | null;
};

export type ServerSessionUpdateEvent = BaseBackendEvent & {
  type: "server.session.update";
  session_id?: string | null;
  resumption_handle?: string | null;
  go_away?: boolean;
  time_left_ms?: number | null;
};

export type ServerErrorEvent = BaseBackendEvent & {
  type: "server.error";
  code: string;
  message: string;
  retryable: boolean;
  session_id?: string | null;
  detail?: Record<string, unknown>;
};

export type BackendServerEvent =
  | ServerReadyEvent
  | ServerStatusEvent
  | ServerTranscriptEvent
  | ServerTextOutputEvent
  | ServerAudioOutputEvent
  | ServerToolCallEvent
  | ServerToolResultEvent
  | ServerTurnEvent
  | ServerSessionUpdateEvent
  | ServerErrorEvent;

export type BackendEventLog = {
  eventType: BackendServerEvent["type"];
  payload: BackendServerEvent | Record<string, unknown>;
};

export type LocalModelContent = {
  modelTurn: {
    parts: Part[];
  };
  turnComplete?: boolean;
};

export type StreamingLog = {
  date: Date;
  type: string;
  count?: number;
  message: string | ClientContentLog | BackendEventLog | Record<string, unknown>;
};

export type ConnectSessionConfig = LiveConnectConfig;
