"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { WS_URL, RECONNECT_DELAYS_MS } from "@/lib/constants"
import type { ClientMessage, ServerMessage } from "@/lib/types"

export type WSStatus = "idle" | "connecting" | "open" | "closed" | "error"

interface UseWebSocketOptions {
  onMessage: (msg: ServerMessage) => void
  onStatusChange?: (status: WSStatus) => void
  autoReconnect?: boolean
}

export function useWebSocket({ onMessage, onStatusChange, autoReconnect = true }: UseWebSocketOptions) {
  const ws = useRef<WebSocket | null>(null)
  const reconnectAttempt = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [status, setStatus] = useState<WSStatus>("idle")
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const updateStatus = useCallback((s: WSStatus) => {
    setStatus(s)
    onStatusChange?.(s)
  }, [onStatusChange])

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
    if (ws.current) {
      ws.current.onclose = null
      ws.current.close()
      ws.current = null
    }
    updateStatus("closed")
    reconnectAttempt.current = 0
  }, [updateStatus])

  const connect = useCallback(() => {
    // Clean up any existing socket
    if (ws.current) {
      ws.current.onclose = null
      ws.current.close()
    }
    updateStatus("connecting")

    const socket = new WebSocket(WS_URL)
    ws.current = socket

    socket.onopen = () => {
      reconnectAttempt.current = 0
      updateStatus("open")
    }

    socket.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as ServerMessage
        onMessageRef.current(msg)
      } catch {
        // Ignore malformed messages
      }
    }

    socket.onerror = () => {
      updateStatus("error")
    }

    socket.onclose = () => {
      ws.current = null
      updateStatus("closed")
      if (autoReconnect) {
        const delay = RECONNECT_DELAYS_MS[
          Math.min(reconnectAttempt.current, RECONNECT_DELAYS_MS.length - 1)
        ]
        reconnectAttempt.current++
        reconnectTimer.current = setTimeout(connect, delay)
      }
    }
  }, [autoReconnect, updateStatus])

  const send = useCallback((msg: ClientMessage) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(msg))
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (ws.current) {
        ws.current.onclose = null
        ws.current.close()
      }
    }
  }, [])

  return { status, connect, disconnect, send }
}
