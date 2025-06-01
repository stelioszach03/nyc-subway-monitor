const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'

let wsConnection: WebSocket | null = null

export function getWebSocket(): WebSocket {
  if (!wsConnection || wsConnection.readyState === WebSocket.CLOSED) {
    wsConnection = new WebSocket(`${WS_BASE_URL}/ws`)
  }
  return wsConnection
}

export function closeWebSocket() {
  if (wsConnection) {
    wsConnection.close()
    wsConnection = null
  }
}