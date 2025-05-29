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
  
  const optionsRef = useRef(options)
  optionsRef.current = options

  useEffect(() => {
    // Only run on client side
    if (typeof window === 'undefined') return

    const ws = getWebSocket()

    const handleConnected = () => {
      setIsConnected(true)
      setConnectionError(null)
      
      if (optionsRef.current.filters) {
        ws.subscribe(optionsRef.current.filters)
      }
    }

    const handleDisconnected = () => {
      setIsConnected(false)
    }

    const handleError = (error: Error) => {
      setConnectionError(error)
    }

    const handleAnomaly = (anomaly: any) => {
      setLastMessage({ type: 'anomaly', data: anomaly })
      optionsRef.current.onAnomalyReceived?.(anomaly)
    }

    const handleStats = (stats: any) => {
      setLastMessage({ type: 'stats', data: stats })
      optionsRef.current.onStatsReceived?.(stats)
    }

    // Register event listeners
    ws.on('connected', handleConnected)
    ws.on('disconnected', handleDisconnected)
    ws.on('error', handleError)
    ws.on('anomaly', handleAnomaly)
    ws.on('stats', handleStats)

    // Connect
    ws.connect()

    // Cleanup
    return () => {
      ws.removeListener('connected', handleConnected)
      ws.removeListener('disconnected', handleDisconnected)
      ws.removeListener('error', handleError)
      ws.removeListener('anomaly', handleAnomaly)
      ws.removeListener('stats', handleStats)
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