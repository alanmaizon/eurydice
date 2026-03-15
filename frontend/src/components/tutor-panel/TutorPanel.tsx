import "./tutor-panel.scss";
import cn from "classnames";
import { memo } from "react";
import { useLiveAPIContext } from "../../contexts/LiveAPIContext";

function TutorPanelComponent() {
  const { connected, runtime, runtimeError, sessionId, status, transcript } =
    useLiveAPIContext();

  return (
    <section className="tutor-panel">
      <header className="tutor-panel__header">
        <div>
          <p className="tutor-panel__eyebrow">Ancient Greek Live Tutor</p>
          <h1>Text-First Live Session</h1>
          <p className="tutor-panel__description">
            We are keeping the official-console shell, but grounding it in the
            local tutor backend first. Mic and camera can come back once the
            core chat loop is solid.
          </p>
        </div>
        <div className="tutor-panel__badges">
          <span className={cn("tutor-panel__badge", { connected })}>
            {connected ? "Connected" : "Disconnected"}
          </span>
          {runtime ? (
            <span className="tutor-panel__badge">{runtime.environment}</span>
          ) : null}
          {sessionId ? (
            <span className="tutor-panel__badge">Session {sessionId}</span>
          ) : null}
        </div>
      </header>

      <section className="tutor-panel__runtime">
        <div className="tutor-panel__runtime-card">
          <span className="label">Service</span>
          <strong>{runtime?.service_name || "Backend offline"}</strong>
        </div>
        <div className="tutor-panel__runtime-card">
          <span className="label">WebSocket</span>
          <strong>{runtime?.websocket_path || "/ws/live"}</strong>
        </div>
        <div className="tutor-panel__runtime-card">
          <span className="label">Mode</span>
          <strong>{runtime?.default_mode || "guided_reading"}</strong>
        </div>
        <div className="tutor-panel__runtime-card">
          <span className="label">Tools</span>
          <strong>{runtime?.tools.join(", ") || "Loading..."}</strong>
        </div>
      </section>

      <section className="tutor-panel__status">
        <span className="label">Session status</span>
        <strong>{status?.phase || "idle"}</strong>
        <p>{runtimeError || status?.detail || "Connect, then send a learner turn from the console panel."}</p>
      </section>

      <section className="tutor-panel__transcript">
        <header>
          <h2>Transcript</h2>
          <p>Backend session context accumulates here turn by turn.</p>
        </header>

        <div className="tutor-panel__transcript-list">
          {transcript.length === 0 ? (
            <div className="tutor-panel__empty">
              <p>No turns yet.</p>
              <span>Press connect, then type in the console sidebar.</span>
            </div>
          ) : (
            transcript.map((entry) => (
              <article
                className={cn("tutor-panel__entry", entry.speaker)}
                key={entry.id}
              >
                <div className="tutor-panel__entry-meta">
                  <span className="speaker">{entry.speaker}</span>
                  <span className="source">{entry.source}</span>
                </div>
                <p>{entry.text}</p>
              </article>
            ))
          )}
        </div>
      </section>
    </section>
  );
}

export const TutorPanel = memo(TutorPanelComponent);
