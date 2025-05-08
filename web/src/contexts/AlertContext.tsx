import { createContext, useContext, useState, ReactNode } from 'react';
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
  const { alerts } = useSubwayData();
  const [dismissedAlerts, setDismissedAlerts] = useState<string[]>([]);

  // Filter out dismissed alerts
  const filteredAlerts = alerts.filter(alert => !dismissedAlerts.includes(alert.id));
  
  // Get high priority alerts (severity HIGH)
  const highPriorityAlerts = filteredAlerts.filter(alert => alert.severity === 'HIGH');

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
