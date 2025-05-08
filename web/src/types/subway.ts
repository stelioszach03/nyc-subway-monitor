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
  anomaly_score?: number; // Προσθήκη του anomaly_score ως προαιρετικό πεδίο
}

export interface Alert {
  id: string;
  route_id: string;
  timestamp: string;
  message: string;
  severity: string;
  anomaly_score: number;
}
