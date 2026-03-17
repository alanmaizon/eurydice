"use client"

import { useCallback, useEffect, useRef, useState } from "react"

export function useCamera() {
  const [isActive, setIsActive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    if (videoRef.current) videoRef.current.srcObject = null
    setIsActive(false)
  }, [])

  const start = useCallback(async (videoEl?: HTMLVideoElement) => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: 640, height: 480 },
      })
      streamRef.current = stream

      // Diagnostic: log video track capabilities (torch, zoom, dimensions, facing)
      const track = stream.getVideoTracks()[0]
      if (track) {
        const caps = track.getCapabilities?.() as Record<string, unknown> | undefined ?? {}
        const settings = track.getSettings?.() ?? {}
        console.debug(
          "[camera] track capabilities — torch=%s zoom=%s facing=%s widthRange=%s heightRange=%s",
          "torch" in caps ? String(caps.torch) : "not supported",
          "zoom" in caps ? JSON.stringify(caps.zoom) : "not supported",
          settings.facingMode ?? "unknown",
          "width" in caps ? `${(caps.width as {min?: number})?.min}–${(caps.width as {max?: number})?.max}` : "n/a",
          "height" in caps ? `${(caps.height as {min?: number})?.min}–${(caps.height as {max?: number})?.max}` : "n/a",
        )
        console.debug(
          "[camera] active settings — %dx%d facing=%s",
          settings.width, settings.height, settings.facingMode,
        )
      }

      // videoRef.current may be null here — CameraPreview only mounts after
      // setIsActive(true) triggers a re-render.  The useEffect below picks up
      // the stream assignment once the video element is in the DOM.
      const el = videoEl ?? videoRef.current
      if (el) {
        el.srcObject = stream
        el.play().catch(() => {})
      }
      setIsActive(true)
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Camera permission denied. Please allow camera access and try again."
          : "Failed to start camera."
      setError(msg)
    }
  }, [])

  // After setIsActive(true) React re-renders and CameraPreview mounts the
  // <video ref={videoRef}> element.  React sets refs during the commit phase,
  // before useEffect fires, so videoRef.current is guaranteed to be the video
  // element by the time this effect runs.  Assign the stream if start() ran
  // before the element existed (the common case when no videoEl is passed).
  useEffect(() => {
    const video = videoRef.current
    const stream = streamRef.current
    if (isActive && video && stream && !video.srcObject) {
      console.debug("[camera] assigning stream to video element after mount")
      video.srcObject = stream
      video.play().catch(() => {})
    }
  }, [isActive])

  const toggle = useCallback(
    async (videoEl?: HTMLVideoElement) => {
      if (isActive) {
        stop()
      } else {
        await start(videoEl)
      }
    },
    [isActive, start, stop]
  )

  /** Capture the current video frame as a JPEG base64 string. */
  const captureFrame = useCallback((quality = 0.85): string | null => {
    const video = videoRef.current
    if (!video || !isActive) return null

    const { videoWidth, videoHeight, readyState, paused } = video

    // Diagnostic: log video element state before drawing
    console.debug(
      "[camera] captureFrame — readyState=%d %dx%d paused=%s srcObject=%s",
      readyState, videoWidth, videoHeight, paused,
      video.srcObject ? "set" : "null"
    )

    // Guard: video must have decoded at least one frame (HAVE_CURRENT_DATA=2).
    // Drawing a canvas before this produces solid-black pixels.
    if (readyState < 2 || videoWidth === 0 || videoHeight === 0) {
      console.warn(
        "[camera] captureFrame: video not ready (readyState=%d %dx%d) — aborting",
        readyState, videoWidth, videoHeight
      )
      return null
    }

    const canvas = document.createElement("canvas")
    canvas.width = videoWidth
    canvas.height = videoHeight
    const ctx = canvas.getContext("2d")
    if (!ctx) return null
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    const dataUrl = canvas.toDataURL("image/jpeg", quality)
    // Strip the data:image/jpeg;base64, prefix
    const b64 = dataUrl.split(",")[1] ?? null

    if (b64) {
      const approxBytes = Math.floor(b64.length * 0.75)
      // Valid JPEG base64 always starts with "/9j/" (0xFF 0xD8 0xFF)
      const isJpeg = b64.startsWith("/9j/")
      console.debug(
        "[camera] captured frame — %dx%d ~%d bytes isJPEG=%s",
        videoWidth, videoHeight, approxBytes, isJpeg
      )
      if (!isJpeg) {
        console.warn(
          "[camera] unexpected frame prefix (first 12 chars: %s) — may not be a valid JPEG",
          b64.slice(0, 12)
        )
      }
    }

    return b64
  }, [isActive])

  // Stable getter so consumers (e.g. the inline preview) can subscribe to the
  // same stream without needing a second ref passed through props.
  const getStream = useCallback(() => streamRef.current, [])

  useEffect(() => () => stop(), [stop])

  return { isActive, error, videoRef, getStream, start, stop, toggle, captureFrame }
}
