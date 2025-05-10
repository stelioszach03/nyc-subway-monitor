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
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connectionAttempts, setConnectionAttempts] = useState(0);
  const [socketReconnectTimer, setSocketReconnectTimer] = useState<number | null>(null);

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  
  // FIX: Increase timeout
  const FETCH_TIMEOUT = 12000; // 12 seconds instead of 8
  
  // Log configuration on init
  useEffect(() => {
    console.log('Subway Data Provider initialized with API URL:', apiUrl);
  }, [apiUrl]);

  // Fetch initial train data
  const fetchTrains = async () => {
    setIsLoading(true);
    try {
      console.log('Fetching train data from:', `${apiUrl}/trains`);
      const response = await fetch(`${apiUrl}/trains`, { 
        signal: AbortSignal.timeout(FETCH_TIMEOUT)
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
    } finally {
      setIsLoading(false);
    }
  };

  // FIX: Change endpoint from /metrics to /subway-metrics
  const fetchDelays = async () => {
    setIsLoading(true);
    try {
      console.log('Fetching delay data from:', `${apiUrl}/subway-metrics`);
      const response = await fetch(`${apiUrl}/subway-metrics`, {
        signal: AbortSignal.timeout(FETCH_TIMEOUT)
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
      // Don't set error for timeouts - this might be expected behavior
      if (!errorMessage.includes('timeout')) {
        setError(errorMessage);
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
        signal: AbortSignal.timeout(FETCH_TIMEOUT)
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
      // Don't set error for timeouts - this might be expected behavior
      if (!errorMessage.includes('timeout')) {
        setError(errorMessage);
      }
    } finally {
      setIsLoading(false);
    }
  };
  
  // Function to establish WebSocket connection
  const connectWebSocket = () => {
    try {
      if (socket !== null && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        console.log('WebSocket connection already exists');
        return;
      }
      
      console.log('Attempting to establish WebSocket connection...');
      const wsUrl = `${apiUrl.replace(/^http/, 'ws')}/ws/live`;
      console.log('WebSocket URL:', wsUrl);
      
      const newSocket = new WebSocket(wsUrl);

      newSocket.onopen = () => {
        console.log('WebSocket connected successfully');
        setSocket(newSocket);
        setConnectionAttempts(0); // Reset connection attempts on successful connection
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
        
        // Try to reconnect with exponential backoff
        const delay = Math.min(30000, Math.pow(2, connectionAttempts) * 1000); // Max 30 seconds
        console.log(`Attempting to reconnect in ${delay/1000} seconds...`);
        
        if (socketReconnectTimer) {
          window.clearTimeout(socketReconnectTimer);
        }
        
        const timerId = window.setTimeout(() => {
          connectWebSocket();
        }, delay);
        
        setSocketReconnectTimer(timerId);
      };
    } catch (err) {
      console.error('Error setting up WebSocket:', err);
      setConnectionAttempts(prev => prev + 1);
    }
  };

  // Set up WebSocket connection
  useEffect(() => {
    // Initial connection attempt
    connectWebSocket();
    
    // Clean up on unmount
    return () => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close(1000, 'Component unmounted');
      }
      
      if (socketReconnectTimer) {
        window.clearTimeout(socketReconnectTimer);
      }
    };
  }, [apiUrl, connectionAttempts]);

  // Initial data fetch and polling setup
  useEffect(() => {
    console.log('Setting up initial data fetch and polling');
    
    // Initial data fetch
    fetchTrains();
    fetchDelays();
    fetchAlerts();
    
    // FIX: Increase polling intervals to reduce load
    const delayInterval = setInterval(fetchDelays, 90000); // Every 1.5 minutes
    const alertInterval = setInterval(fetchAlerts, 90000); // Every 1.5 minutes
    const trainInterval = setInterval(fetchTrains, 60000); // Every minute

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