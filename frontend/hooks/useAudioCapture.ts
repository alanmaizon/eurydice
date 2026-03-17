"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { AUDIO_SAMPLE_RATE } from "@/lib/constants"
import { arrayBufferToBase64 } from "@/lib/utils"

interface UseAudioCaptureOptions {
  onAudioChunk: (base64Pcm: string) => void
}

export function useAudioCapture({ onAudioChunk }: UseAudioCaptureOptions) {
  const [isCapturing, setIsCapturing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const audioContextRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const workletNodeRef = useRef<AudioWorkletNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const onChunkRef = useRef(onAudioChunk)
  onChunkRef.current = onAudioChunk

  const stop = useCallback(() => {
    workletNodeRef.current?.port.close()
    workletNodeRef.current?.disconnect()
    sourceRef.current?.disconnect()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    audioContextRef.current?.close()
    workletNodeRef.current = null
    sourceRef.current = null
    streamRef.current = null
    audioContextRef.current = null
    setIsCapturing(false)
  }, [])

  const start = useCallback(async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // AudioContext resamples the device's native rate to AUDIO_SAMPLE_RATE (16 kHz).
      // Gemini Live expects PCM 16-bit 16 kHz mono.
      const ctx = new AudioContext({ sampleRate: AUDIO_SAMPLE_RATE })
      audioContextRef.current = ctx

      // Load the AudioWorkletProcessor from /public/pcm-processor.js.
      // The worklet runs off the main thread, so heavy React renders won't
      // cause audio frame drops.
      await ctx.audioWorklet.addModule("/pcm-processor.js")

      const source = ctx.createMediaStreamSource(stream)
      sourceRef.current = source

      const workletNode = new AudioWorkletNode(ctx, "pcm-processor")
      workletNodeRef.current = workletNode

      // The processor posts Int16 ArrayBuffers via MessagePort.
      workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        onChunkRef.current(arrayBufferToBase64(event.data))
      }

      source.connect(workletNode)
      // Connect to destination to keep the audio graph active (silent output).
      workletNode.connect(ctx.destination)

      setIsCapturing(true)
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone permission denied. Please allow microphone access and try again."
          : "Failed to start microphone capture."
      setError(msg)
    }
  }, [])

  const toggle = useCallback(async () => {
    console.debug("[mic] toggle — isCapturing=%s", isCapturing)
    if (isCapturing) {
      stop()
      console.debug("[mic] stopped")
    } else {
      await start()
      // isCapturing state reflects the result after start() resolves
      const track = streamRef.current?.getAudioTracks()[0]
      console.debug(
        "[mic] started — track=%s enabled=%s muted=%s",
        track?.label ?? "none",
        track?.enabled ?? "n/a",
        track?.muted ?? "n/a",
      )
    }
  }, [isCapturing, start, stop])

  useEffect(() => () => stop(), [stop])

  return { isCapturing, error, start, stop, toggle }
}
