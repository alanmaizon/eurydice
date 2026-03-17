"use client"

import { useEffect } from "react"

interface CameraPreviewProps {
  videoRef: React.RefObject<HTMLVideoElement>
}

export function CameraPreview({ videoRef }: CameraPreviewProps) {
  return (
    <section>
      <h3
        className="inspector-mono text-xs uppercase tracking-wider mb-2"
        style={{ color: "var(--text-muted)" }}
      >
        Camera Preview
      </h3>
      <div
        className="rounded-lg overflow-hidden"
        style={{ border: "1px solid var(--border)" }}
      >
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="w-full aspect-video object-cover bg-black"
          style={{ maxHeight: "160px" }}
        />
      </div>
    </section>
  )
}
