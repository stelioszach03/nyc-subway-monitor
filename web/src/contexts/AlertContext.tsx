import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { Alert } from '../types/subway';
import { useSubwayData } from './SubwayDataContext';

interface AlertContextType {
  alerts: Alert[];
  highPriorityAlerts: Alert[];
  dismissAlert: (id: string) => void;
  dismissedAlerts: string[];
  clearAllDismissed: () => void;
}

const AlertContext = createContext<AlertContextType>({
  alerts: [],
  highPriorityAlerts: [],
  dismissAlert: () => {},
  dismissedAlerts: [],
  clearAllDismissed: () => {}
});

export const useAlerts = () => useContext(AlertContext);

export const AlertProvider = ({ children }: { children: ReactNode }) => {
  const { alerts: allAlerts } = useSubwayData();
  const [dismissedAlerts, setDismissedAlerts] = useState<string[]>([]);
  
  // Load dismissed alerts from localStorage if available
  useEffect(() => {
    try {
      const savedDismissed = localStorage.getItem('dismissedAlerts');
      if (savedDismissed) {
        setDismissedAlerts(JSON.parse(savedDismissed));
      }
    } catch (err) {
      console.error('Error loading dismissed alerts from localStorage:', err);
    }
  }, []);
  
  // Save dismissed alerts to localStorage when they change
  useEffect(() => {
    try {
      localStorage.setItem('dismissedAlerts', JSON.stringify(dismissedAlerts));
    } catch (err) {
      console.error('Error saving dismissed alerts to localStorage:', err);
    }
  }, [dismissedAlerts]);

  // Filter out dismissed alerts
  const filteredAlerts = allAlerts.filter(alert => !dismissedAlerts.includes(alert.id));
  
  // Get high priority alerts (severity HIGH)
  const highPriorityAlerts = filteredAlerts.filter(alert => alert.severity === 'HIGH');

  // Play sound for new high priority alerts
  useEffect(() => {
    // Only play for new alerts (not on initial load)
    if (highPriorityAlerts.length > 0 && allAlerts.length > 0) {
      try {
        // Check if this is a new alert (less than 10 seconds old)
        const newestAlert = highPriorityAlerts[0];
        const alertTime = new Date(newestAlert.timestamp).getTime();
        const now = Date.now();
        const isNewAlert = now - alertTime < 10000; // 10 seconds
        
        if (isNewAlert && !dismissedAlerts.includes(newestAlert.id)) {
          // Try to play alert sound
          const alertSound = new Audio('/alert.mp3');
          alertSound.volume = 0.5;
          alertSound.play().catch(err => {
            // Browser may block autoplay, that's fine
            console.log('Could not play alert sound:', err);
          });
        }
      } catch (err) {
        console.error('Error playing alert sound:', err);
      }
    }
  }, [highPriorityAlerts, allAlerts, dismissedAlerts]);

  const dismissAlert = (id: string) => {
    setDismissedAlerts(prev => [...prev, id]);
  };

  const clearAllDismissed = () => {
    setDismissedAlerts([]);
  };

  return (
    <AlertContext.Provider
      value={{
        alerts: filteredAlerts,
        highPriorityAlerts,
        dismissAlert,
        dismissedAlerts,
        clearAllDismissed
      }}
    >
      {children}
    </AlertContext.Provider>
  );
};

export default AlertContext;