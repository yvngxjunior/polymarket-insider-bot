'use client'
import { useState, useEffect, useRef } from 'react'

interface WebSocketMessage {
  type: string
  timestamp: number
  liveStatus?: any
  [key: string]: any
}

export function useWebSocket(url: string) {
  const [data, setData] = useState<WebSocketMessage | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    function connect() {
      try {
        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
          console.log('[WS] Connected')
          setIsConnected(true)
        }

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data)
            setData(message)
          } catch (e) {
            console.error('[WS] Parse error:', e)
          }
        }

        ws.onerror = (error) => {
          console.error('[WS] Error:', error)
        }

        ws.onclose = () => {
          console.log('[WS] Disconnected')
          setIsConnected(false)
          // Auto-reconnect after 3 seconds
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('[WS] Reconnecting...')
            connect()
          }, 3000)
        }
      } catch (e) {
        console.error('[WS] Connection failed:', e)
        // Retry after 5 seconds
        reconnectTimeoutRef.current = setTimeout(connect, 5000)
      }
    }

    connect()

    // Cleanup
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [url])

  return { data, isConnected }
}
