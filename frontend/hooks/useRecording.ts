"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useAudioCapture } from "./useAudioCapture"
import { encodeWavBase64 } from "@/lib/wav"
import { AUDIO_SAMPLE_RATE } from "@/lib/constants"

export type RecordingState = "idle" | "recording" | "ready"

export interface UseRecordingReturn {
  recordingState: RecordingState
  durationS: number
  wavB64: string | null
  start: () => Promise<void>
  stop: () => void
  discard: () => void
  error: string | null
}

/**
 * Records a full guitar take into a WAV buffer.
 *
 * Unlike useAudioCapture (which streams PCM chunks to the server),
 * this hook accumulates all chunks client-side and exports a single
 * base64 WAV on stop — ready to send as input.audio_recording.
 */
export function useRecording(): UseRecordingReturn {
  const [recordingState, setRecordingState] = useState<RecordingState>("idle")
  const [durationS, setDurationS] = useState(0)
  const [wavB64, setWavB64] = useState<string | null>(null)

  const chunksRef = useRef<Int16Array[]>([])
  const startTimeRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Use a ref to check current state inside the onAudioChunk callback
  // (avoids stale closure issues with the setState-based isRecording flag)
  const isRecordingRef = useRef(false)

  const audio = useAudioCapture({
    onAudioChunk: useCallback((b64: string) => {
      if (!isRecordingRef.current) return
      // Decode base64 PCM → Int16Array and accumulate
      try {
        const binary = atob(b64)
        const bytes = new Uint8Array(binary.length)
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
        chunksRef.current.push(new Int16Array(bytes.buffer.slice(0)))
      } catch {
        // Ignore decode errors on individual chunks
      }
    }, []),
  })

  const start = useCallback(async () => {
    chunksRef.current = []
    setWavB64(null)
    setDurationS(0)
    startTimeRef.current = Date.now()
    isRecordingRef.current = true

    timerRef.current = setInterval(() => {
      setDurationS(Math.floor((Date.now() - startTimeRef.current) / 1000))
    }, 500)

    await audio.start()
    setRecordingState("recording")
  }, [audio])

  const stop = useCallback(() => {
    isRecordingRef.current = false
    audio.stop()

    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000)
    setDurationS(elapsed)

    // Assemble all chunks into a single Int16Array
    const totalSamples = chunksRef.current.reduce((n, c) => n + c.length, 0)
    if (totalSamples === 0) {
      setRecordingState("idle")
      return
    }
    const combined = new Int16Array(totalSamples)
    let offset = 0
    for (const chunk of chunksRef.current) {
      combined.set(chunk, offset)
      offset += chunk.length
    }
    chunksRef.current = []

    const b64 = encodeWavBase64(combined, AUDIO_SAMPLE_RATE)
    setWavB64(b64)
    setRecordingState("ready")
  }, [audio])

  const discard = useCallback(() => {
    setWavB64(null)
    setDurationS(0)
    setRecordingState("idle")
    chunksRef.current = []
  }, [])

  // Auto-stop at 35 seconds to avoid huge payloads
  useEffect(() => {
    if (recordingState === "recording" && durationS >= 35) {
      stop()
    }
  }, [recordingState, durationS, stop])

  // Cleanup on unmount
  useEffect(() => () => {
    if (timerRef.current) clearInterval(timerRef.current)
    isRecordingRef.current = false
  }, [])

  return {
    recordingState,
    durationS,
    wavB64,
    start,
    stop,
    discard,
    error: audio.error,
  }
}
