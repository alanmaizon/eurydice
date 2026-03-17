"use client"

import { useState, useRef, useEffect } from "react"
import { useSession } from "@/hooks/useSession"
import { useTheme } from "@/hooks/useTheme"
import { TopBar } from "@/components/layout/TopBar"
import { ComposerBar } from "@/components/layout/ComposerBar"
import { InspectorDrawer } from "@/components/layout/InspectorDrawer"
import { WelcomeView } from "@/components/welcome/WelcomeView"
import { TranscriptView } from "@/components/session/TranscriptView"
import { DEFAULT_SYSTEM_INSTRUCTION } from "@/lib/constants"

// ── Live camera preview strip ────────────────────────────────────────────────
// Uses its own local videoRef so it never competes with useCamera's videoRef
// (which is reserved for captureFrame / InspectorDrawer).
// The same MediaStream is shared to both consumers; MediaStream is multi-consumer safe.
function LiveCameraPreview({
  getStream,
  lastCapture,
  onDismissCapture,
}: {
  getStream: () => MediaStream | null
  lastCapture: string | null
  onDismissCapture: () => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const video = videoRef.current
    const stream = getStream()
    if (!video || !stream) {
      console.debug("[preview] mount — stream not yet available")
      return
    }
    video.srcObject = stream
    video.play().catch(() => {})

    const onMeta = () =>
      console.debug("[preview] ready — %dx%d", video.videoWidth, video.videoHeight)
    video.addEventListener("loadedmetadata", onMeta)
    return () => video.removeEventListener("loadedmetadata", onMeta)
    // getStream is stable (useCallback with no deps) — safe to omit from dep array
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      className="shrink-0"
      style={{ borderTop: "1px solid var(--border)", background: "var(--surface)" }}
    >
      <div className="max-w-3xl mx-auto px-4 py-2 flex items-end gap-4">
        {/* Live feed */}
        <div className="flex flex-col gap-1">
          <span
            className="text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--accent)" }}
          >
            ● Live
          </span>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="rounded-lg object-cover bg-black"
            style={{ width: 128, height: 96 }}
          />
        </div>

        {/* Captured frame — shown immediately after shutter press */}
        {lastCapture && (
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2">
              <span
                className="text-[10px] font-semibold uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                Captured
              </span>
              <button
                onClick={onDismissCapture}
                className="text-xs leading-none"
                style={{ color: "var(--text-muted)" }}
                title="Dismiss"
              >
                ✕
              </button>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`data:image/jpeg;base64,${lastCapture}`}
              alt="Captured frame"
              className="rounded-lg object-cover"
              style={{ width: 128, height: 96 }}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default function ConsolePage() {
  const { theme, toggle: toggleTheme } = useTheme()
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [systemInstruction, setSystemInstruction] = useState(DEFAULT_SYSTEM_INSTRUCTION)
  // Holds the most recent captured frame (base64 JPEG) for the preview strip.
  // Cleared when user dismisses or camera is toggled off.
  const [lastCapture, setLastCapture] = useState<string | null>(null)

  const {
    state,
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
  } = useSession()

  const hasSession =
    state.connectionState !== "idle" || state.transcript.length > 0

  return (
    <div
      className="flex flex-col h-screen"
      style={{ background: "var(--bg)", color: "var(--text-primary)" }}
    >
      <TopBar
        connectionState={state.connectionState}
        elapsedSeconds={state.elapsedSeconds}
        difficultyLevel={state.difficultyLevel}
        theme={theme}
        onToggleTheme={toggleTheme}
        onToggleInspector={() => setInspectorOpen((v) => !v)}
        inspectorOpen={inspectorOpen}
      />

      <main className="flex-1 overflow-hidden relative">
        <div className="h-full max-w-3xl mx-auto px-4 flex flex-col">
          {!hasSession ? (
            <WelcomeView
              systemInstruction={systemInstruction}
              onSystemInstructionChange={setSystemInstruction}
              difficultyLevel={state.difficultyLevel}
              onDifficultyChange={setDifficulty}
              onLoadPassage={(text) => loadPassage(text)}
            />
          ) : (
            <TranscriptView
              messages={state.transcript}
              isStreaming={state.isAssistantStreaming}
              connectionState={state.connectionState}
              pinnedPassage={state.pinnedPassage}
              onClearPassage={clearPassage}
            />
          )}
        </div>
      </main>

      {/* Live preview strip — appears between transcript and composer when camera is on */}
      {camera.isActive && (
        <LiveCameraPreview
          getStream={camera.getStream}
          lastCapture={lastCapture}
          onDismissCapture={() => setLastCapture(null)}
        />
      )}

      <ComposerBar
        connectionState={state.connectionState}
        isAudioCapturing={audio.isCapturing}
        isCameraActive={camera.isActive}
        audioError={audio.error}
        cameraError={camera.error}
        onStartSession={() => startSession(systemInstruction, state.difficultyLevel)}
        onEndSession={endSession}
        onSendText={sendText}
        onToggleMic={audio.toggle}
        onToggleCamera={() => {
          if (camera.isActive) setLastCapture(null) // clear stale capture on stop
          camera.toggle()
        }}
        onCaptureAndSendImage={() => {
          const b64 = camera.captureFrame()
          if (b64) {
            setLastCapture(b64)
            sendImage(b64)
          }
        }}
        onInterrupt={interrupt}
      />

      <InspectorDrawer
        open={inspectorOpen}
        onClose={() => setInspectorOpen(false)}
        events={state.inspectorEvents}
        toolCalls={state.toolCalls}
        tokenCount={state.tokenCount}
        isStreaming={state.isAssistantStreaming}
        isCameraActive={camera.isActive}
        videoRef={camera.videoRef}
        onClear={clearInspector}
      />

      {/* Demo hooks: hidden controls for Playwright automation */}
      <input
        type="file"
        accept="image/*"
        data-testid="image-upload-input"
        style={{ position: "absolute", left: "-9999px", opacity: 0 }}
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (!file) return
          const reader = new FileReader()
          reader.onload = () => {
            const result = reader.result as string
            const b64 = result.split(",")[1]
            sendImage(b64, file.type)
          }
          reader.readAsDataURL(file)
        }}
      />
      {/* Difficulty setters — allow Playwright to change level between sessions
          (WelcomeView is hidden once a session has started) */}
      {(["beginner", "intermediate", "advanced"] as const).map((level) => (
        <button
          key={level}
          data-testid={`set-difficulty-${level}`}
          style={{ position: "absolute", left: "-9999px", opacity: 0 }}
          onClick={() => setDifficulty(level)}
          tabIndex={-1}
          aria-hidden="true"
        />
      ))}
    </div>
  )
}
