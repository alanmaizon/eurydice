import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./hooks/use-live-api", () => {
  const client = {
    on: vi.fn().mockReturnThis(),
    off: vi.fn().mockReturnThis(),
    send: vi.fn(),
    sendRealtimeInput: vi.fn(),
    endRealtimeTurn: vi.fn(),
    disconnect: vi.fn(),
  };

  return {
    useLiveAPI: () => ({
      client,
      config: {},
      setConfig: vi.fn(),
      model: "models/gemini-2.5-flash-native-audio-latest",
      setModel: vi.fn(),
      connected: false,
      connect: vi.fn(),
      disconnect: vi.fn(),
      volume: 0,
      runtime: {
        service_name: "Ancient Greek Live Tutor",
        environment: "development",
        google_cloud_project: null,
        google_cloud_location: "us-central1",
        websocket_path: "/ws/live",
        live_protocol_version: "2026-03-15",
        default_mode: "guided_reading",
        use_google_adk: true,
        google_adk_available: false,
        google_adk_detail: "google-adk is not installed yet",
        google_genai_available: true,
        google_genai_detail: "google-genai import succeeded",
        tools: ["resolve_reference", "parse_passage"],
      },
      runtimeError: null,
      sessionId: "session-test",
      status: {
        phase: "idle",
        detail: "Connect, then send a learner turn from the console panel.",
      },
      transcript: [],
      clearTranscript: vi.fn(),
    }),
  };
});

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the tutor workspace shell", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: /text-first live session/i })
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/ancient greek live tutor/i).length
    ).toBeGreaterThan(0);
    expect(screen.getByText(/transcript/i)).toBeInTheDocument();
  });
});
