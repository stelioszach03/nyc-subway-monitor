import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Train, RouteDelay, Alert } from '../types/subway';

// Fallback data for development mode
const getFallbackTrainData = (): Train[] => {
  return [
    {
      trip_id: "01A",
      route_id: "1",
      timestamp: new Date().toISOString(),
      latitude: 40.7580,
      longitude: -73.9855,
      current_status: "IN_TRANSIT_TO",
      vehicle_id: "1001",
      direction_id: 0
    },
    {
      trip_id: "02A",
      route_id: "2",
      timestamp: new Date().toISOString(),
      latitude: 40.7490,
      longitude: -73.9680,
      current_status: "STOPPED_AT",
      vehicle_id: "2001",
      direction_id: 1,
      delay: 120
    },
    {
      trip_id: "03A",
      route_id: "A",
      timestamp: new Date().toISOString(),
      latitude: 40.7630,
      longitude: -73.9780,
      current_status: "IN_TRANSIT_TO",
      vehicle_id: "3001",
      direction_id: 0,
      delay: 60
    }
  ];
};

const getFallbackDelayData = (): RouteDelay[] => {
  const now = new Date();
  const windowEnd = now.toISOString();
  const windowStart = new Date(now.getTime() - 300000).toISOString(); // 5 minutes ago
  
  return [
    {
      route_id: "1",
      avg_delay: 45.5,
      max_delay: 120,
      min_delay: 0,
      train_count: 12,
      window_start: windowStart,
      window_end: windowEnd,
      anomaly_score: 0.2
    },
    {
      route_id: "2",
      avg_delay: 95.2,
      max_delay: 240,
      min_delay: 10,
      train_count: 8,
      window_start: windowStart,
      window_end: windowEnd,
      anomaly_score: 0.4
    },
    {
      route_id: "A",
      avg_delay: 185.0,
      max_delay: 360,
      min_delay: 60,
      train_count: 15,
      window_start: windowStart,
      window_end: windowEnd,
      anomaly_score: 0.7
    }
  ];
};

const getFallbackAlertData = (): Alert[] => {
  return [
    {
      id: "alert1",
      route_id: "A",
      timestamp: new Date().toISOString(),
      message: "Significant delays detected on the A line due to signal problems",
      severity: "HIGH",
      anomaly_score: 0.85
    },
    {
      id: "alert2",
      route_id: "2",
      timestamp: new Date(Date.now() - 1800000).toISOString(), // 30 minutes ago
      message: "Delays of up to 15 minutes on the 2 line due to train traffic",
      severity: "MEDIUM",
      anomaly_score: 0.65
    },
    {
      id: "alert3",
      route_id: "G",
      timestamp: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
      message: "Minor delays on the G line",
      severity: "LOW",
      anomaly_score: 0.35
    }
  ];
};

interface SubwayDataContextType {
  trains: Train[];
  delays: RouteDelay[];
  alerts: Alert[];
  isLoading: boolean;
  error: string | null;
  fetchTrains: () => Promise<void>;
  fetchDelays: () => Promise<void>;
  fetchAlerts: () => Promise<void>;
}

const SubwayDataContext = createContext<SubwayDataContextType>({
  trains: [],
  delays: [],
  alerts: [],
  isLoading: false,
  error: null,
  fetchTrains: async () => {},
  fetchDelays: async () => {},
  fetchAlerts: async () => {}
});

export const useSubwayData = () => useContext(SubwayDataContext);

export const SubwayDataProvider = ({ children }: { children: ReactNode }) => {
  const [trains, setTrains] = useState<Train[]>([]);
  const [delays, setDelays] = useState<RouteDelay[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connectionAttempts, setConnectionAttempts] = useState(0);

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  
  // Log configuration on init
  useEffect(() => {
    console.log('Subway Data Provider initialized with API URL:', apiUrl);
    
    // Initialize with fallback data immediately for development
    setTrains(getFallbackTrainData());
    setDelays(getFallbackDelayData());
    setAlerts(getFallbackAlertData());
  }, [apiUrl]);

  // Fetch initial train data
  const fetchTrains = async () => {
    setIsLoading(true);
    try {
      console.log('Fetching train data from:', `${apiUrl}/trains`);
      const response = await fetch(`${apiUrl}/trains`, { 
        signal: AbortSignal.timeout(5000) // 5 second timeout
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch train data: ${response.status}`);
      }
      
      const data = await response.json();
      console.log(`Received ${data.length} trains`);
      setTrains(data);
      setError(null);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred fetching train data';
      console.error('Error fetching train data:', errorMessage);
      setError(errorMessage);
      
      // Keep using fallback data
      if (trains.length === 0) {
        setTrains(getFallbackTrainData());
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch route delays
  const fetchDelays = async () => {
    setIsLoading(true);
    try {
      console.log('Fetching delay data from:', `${apiUrl}/metrics`);
      const response = await fetch(`${apiUrl}/metrics`, {
        signal: AbortSignal.timeout(5000) // 5 second timeout
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch delay data: ${response.status}`);
      }
      
      const data = await response.json();
      console.log(`Received ${data.length} delay records`);
      setDelays(data);
      setError(null);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred fetching delay data';
      console.error('Error fetching delay data:', errorMessage);
      setError(errorMessage);
      
      // Keep using fallback data
      if (delays.length === 0) {
        setDelays(getFallbackDelayData());
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch alerts
  const fetchAlerts = async () => {
    setIsLoading(true);
    try {
      console.log('Fetching alert data from:', `${apiUrl}/alerts`);
      const response = await fetch(`${apiUrl}/alerts`, {
        signal: AbortSignal.timeout(5000) // 5 second timeout
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch alert data: ${response.status}`);
      }
      
      const data = await response.json();
      console.log(`Received ${data.length} alerts`);
      setAlerts(data);
      setError(null);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An error occurred fetching alert data';
      console.error('Error fetching alert data:', errorMessage);
      setError(errorMessage);
      
      // Keep using fallback data
      if (alerts.length === 0) {
        setAlerts(getFallbackAlertData());
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Set up WebSocket connection
  useEffect(() => {
    // In development, we only try to connect once for performance
    if (connectionAttempts > 0) {
      console.log('Not attempting WebSocket connection in development mode');
      return;
    }

    try {
      console.log('Attempting to establish WebSocket connection...');
      const wsUrl = `${apiUrl.replace(/^http/, 'ws')}/ws/live`;
      console.log('WebSocket URL:', wsUrl);
      
      const newSocket = new WebSocket(wsUrl);

      newSocket.onopen = () => {
        console.log('WebSocket connected successfully');
        setSocket(newSocket);
      };

      newSocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('WebSocket message received:', data.type);
          
          // Handle different message types
          if (data.type === 'initial') {
            setTrains(data.data);
          } else if (data.type === 'position') {
            // Update a single train position
            setTrains(prev => {
              const index = prev.findIndex(t => 
                t.trip_id === data.data.trip_id && t.route_id === data.data.route_id
              );
              
              if (index >= 0) {
                const updated = [...prev];
                updated[index] = data.data;
                return updated;
              } else {
                return [...prev, data.data];
              }
            });
          } else if (data.type === 'delay') {
            // Update delay information
            setDelays(prev => {
              const index = prev.findIndex(d => d.route_id === data.data.route_id);
              
              if (index >= 0) {
                const updated = [...prev];
                updated[index] = data.data;
                return updated;
              } else {
                return [...prev, data.data];
              }
            });
          } else if (data.type === 'alert') {
            // Add new alert
            setAlerts(prev => [data.data, ...prev]);
          }
        } catch (err) {
          console.error('Error processing WebSocket message:', err);
        }
      };

      newSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionAttempts(prev => prev + 1);
      };

      newSocket.onclose = (event) => {
        console.log(`WebSocket disconnected with code ${event.code}`, event.reason);
        setSocket(null);
      };

      return () => {
        console.log('Cleaning up WebSocket connection');
        if (newSocket && newSocket.readyState === WebSocket.OPEN) {
          newSocket.close(1000, 'Component unmounted');
        }
      };
    } catch (err) {
      console.error('Error setting up WebSocket:', err);
      setConnectionAttempts(prev => prev + 1);
    }
  }, [apiUrl, connectionAttempts]);

  // Initial data fetch and polling setup
  useEffect(() => {
    console.log('Setting up polling for data updates');
    
    // Setting up polling intervals
    const delayInterval = setInterval(fetchDelays, 60000); // Every minute
    const alertInterval = setInterval(fetchAlerts, 60000); // Every minute
    const trainInterval = setInterval(fetchTrains, 30000); // Every 30 seconds

    return () => {
      clearInterval(delayInterval);
      clearInterval(alertInterval);
      clearInterval(trainInterval);
    };
  }, []);

  return (
    <SubwayDataContext.Provider
      value={{
        trains,
        delays,
        alerts,
        isLoading,
        error,
        fetchTrains,
        fetchDelays,
        fetchAlerts
      }}
    >
      {children}
    </SubwayDataContext.Provider>
  );
};

export { SubwayDataContext };
export default SubwayDataProvider;
