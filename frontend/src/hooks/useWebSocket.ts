import { useEffect, useState, useCallback, useRef } from 'react'
import { getWebSocket } from '@/lib/websocket'

interface UseWebSocketOptions {
  onAnomalyReceived?: (anomaly: any) => void
  onStatsReceived?: (stats: any) => void
  filters?: Record<string, any>
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<any>(null)
  const [connectionError, setConnectionError] = useState<Error | null>(null)
  
  // Use ref to avoid re-render dependency issues
  const optionsRef = useRef(options)
  optionsRef.current = options

  useEffect(() => {
    const ws = getWebSocket()

    // Set up event listeners
    ws.on('connected', () => {
      setIsConnected(true)
      setConnectionError(null)
      
      // Apply filters if provided
      if (optionsRef.current.filters) {
        ws.subscribe(optionsRef.current.filters)
      }
    })

    ws.on('disconnected', () => {
      setIsConnected(false)
    })

    ws.on('error', (error) => {
      setConnectionError(error)
    })

    ws.on('anomaly', (anomaly) => {
      setLastMessage({ type: 'anomaly', data: anomaly })
      optionsRef.current.onAnomalyReceived?.(anomaly)
    })

    ws.on('stats', (stats) => {
      setLastMessage({ type: 'stats', data: stats })
      optionsRef.current.onStatsReceived?.(stats)
    })

    // Connect
    ws.connect()

    // Cleanup
    return () => {
      ws.removeAllListeners()
      // Don't disconnect as other components might be using it
    }
  }, [])

  const updateFilters = useCallback((filters: Record<string, any>) => {
    const ws = getWebSocket()
    ws.subscribe(filters)
  }, [])

  return {
    isConnected,
    lastMessage,
    connectionError,
    updateFilters,
  }
}