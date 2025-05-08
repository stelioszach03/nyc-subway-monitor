import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Train, RouteDelay, Alert } from '../types/subway';

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
  // Websocket is created but not used yet - keeping it for future implementation
  const [_socket, setSocket] = useState<WebSocket | null>(null);

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  // Fetch initial train data
  const fetchTrains = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${apiUrl}/trains`);
      if (!response.ok) {
        throw new Error('Failed to fetch train data');
      }
      const data = await response.json();
      setTrains(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Error fetching train data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch route delays
  const fetchDelays = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${apiUrl}/metrics`);
      if (!response.ok) {
        throw new Error('Failed to fetch delay data');
      }
      const data = await response.json();
      setDelays(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Error fetching delay data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch alerts
  const fetchAlerts = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${apiUrl}/alerts`);
      if (!response.ok) {
        throw new Error('Failed to fetch alert data');
      }
      const data = await response.json();
      setAlerts(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Error fetching alert data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Set up WebSocket connection
  useEffect(() => {
    const wsUrl = `${apiUrl.replace(/^http/, 'ws')}/ws/live`;
    const newSocket = new WebSocket(wsUrl);

    newSocket.onopen = () => {
      console.log('WebSocket connected');
    };

    newSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
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
    };

    newSocket.onclose = () => {
      console.log('WebSocket disconnected');
    };

    setSocket(newSocket);

    // Clean up on unmount
    return () => {
      if (newSocket.readyState === WebSocket.OPEN) {
        newSocket.close();
      }
    };
  }, [apiUrl]);

  // Initial data fetch
  useEffect(() => {
    fetchTrains();
    fetchDelays();
    fetchAlerts();

    // Set up polling for data that might not come through WebSocket
    const delayInterval = setInterval(fetchDelays, 60000); // Every minute
    const alertInterval = setInterval(fetchAlerts, 60000); // Every minute

    return () => {
      clearInterval(delayInterval);
      clearInterval(alertInterval);
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
