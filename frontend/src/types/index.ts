
/**
 * Type definitions for NYC Subway Monitor
 */

export interface Anomaly {
  id: number
  detected_at: string
  station_id: string | null
  line: string | null
  anomaly_type: string
  severity: number
  model_name: string
  model_version: string
  features: Record<string, number>
  meta_data: Record<string, any>
  resolved: boolean
  resolved_at: string | null
}

export interface AnomalyListResponse {
  anomalies: Anomaly[]
  total: number
  page: number
  page_size: number
}

export interface AnomalyStats {
  total_today: number
  total_active: number
  by_type: Record<string, number>
  by_line: Record<string, number>
  severity_distribution: {
    low: number
    medium: number
    high: number
  }
  trend_24h: Array<{
    hour: string
    count: number
    avg_severity: number
  }>
}

export interface TrainPosition {
  id: number
  timestamp: string
  trip_id: string
  route_id: string
  line: string
  direction: number
  current_station: string | null
  next_station: string | null
  arrival_time: string | null
  departure_time: string | null
  delay_seconds: number
  headway_seconds: number | null
  dwell_time_seconds: number | null
  schedule_adherence: number | null
}

export interface FeedUpdate {
  timestamp: string
  feed_id: string
  num_trips: number
  num_alerts: number
  processing_time_ms: number
  status: string
}

export interface Station {
  id: string
  name: string
  lat: number
  lon: number
  lines: string[]
  borough: string | null
}

export interface WebSocketMessage {
  type: 'anomaly' | 'heartbeat' | 'stats' | 'connected' | 'subscribed' | 'pong'
  timestamp: string
  data?: any
}

export interface LineInfo {
  id: string
  label: string
  color: string
}

export interface MapBounds {
  north: number
  south: number
  east: number
  west: number
}