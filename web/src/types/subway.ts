export interface Train {
  trip_id: string;
  route_id: string;
  timestamp: string;
  latitude: number;
  longitude: number;
  current_status: string;
  current_stop_sequence?: number;
  delay?: number;
  vehicle_id: string;
  direction_id: number;
}

export interface RouteDelay {
  route_id: string;
  avg_delay: number;
  max_delay: number;
  min_delay: number;
  train_count: number;
  window_start: string;
  window_end: string;
  anomaly_score?: number;
}

export interface Alert {
  id: string;
  route_id: string;
  timestamp: string;
  message: string;
  severity: string;
  anomaly_score: number;
}

// NYC subway line colors
export const ROUTE_COLORS: Record<string, string> = {
  '1': '#ff3c1f',
  '2': '#ff3c1f',
  '3': '#ff3c1f',
  '4': '#00933c',
  '5': '#00933c',
  '6': '#00933c',
  '7': '#b933ad',
  'A': '#0039a6',
  'C': '#0039a6',
  'E': '#0039a6',
  'B': '#ff6319',
  'D': '#ff6319',
  'F': '#ff6319',
  'M': '#ff6319',
  'G': '#6cbe45',
  'J': '#996633',
  'Z': '#996633',
  'L': '#a7a9ac',
  'N': '#fccc0a',
  'Q': '#fccc0a',
  'R': '#fccc0a',
  'W': '#fccc0a',
  'S': '#808183',
  'SI': '#0039a6'
};