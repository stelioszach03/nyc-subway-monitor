import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Alerts from './pages/Alerts';
import Metrics from './pages/Metrics';
import Layout from './components/Layout';
import { AlertProvider } from './contexts/AlertContext';
import { SubwayDataProvider } from './contexts/SubwayDataContext';

// DEVELOPMENT MODE FLAG - Set to true to bypass API connection check
const DEVELOPMENT_MODE = false;

const App = () => {
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Check API connection on startup
  useEffect(() => {
    // In development mode, bypass API check
    if (DEVELOPMENT_MODE) {
      console.log('DEVELOPMENT MODE: Bypassing API connection check');
      setIsConnected(true);
      setConnectionError(null);
      return;
    }

    const checkConnection = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        console.log('Attempting to connect to API at:', apiUrl);
        
        const response = await fetch(`${apiUrl}/health`, { 
          signal: AbortSignal.timeout(8000) // 8 second timeout
        });
        
        if (response.ok) {
          const data = await response.json();
          console.log('API connection successful:', data);
          setIsConnected(true);
          setConnectionError(null);
        } else {
          console.error('API returned error status:', response.status);
          setIsConnected(false);
          setConnectionError(`API returned status ${response.status}`);
        }
      } catch (error) {
        console.error('API connection failed:', error);
        setIsConnected(false);
        setConnectionError(error instanceof Error ? error.message : 'Unknown error');
      }
    };

    checkConnection();
    
    // Retry connection periodically if it failed
    let intervalId: number;
    if (isConnected === false) {
      intervalId = setInterval(checkConnection, 10000) as unknown as number;
    }
    
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [isConnected]);

  // Loading state
  if (isConnected === null) {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center bg-gray-50">
        <div className="rounded-lg bg-white p-8 shadow-lg">
          <div className="flex flex-col items-center">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-600 border-t-transparent"></div>
            <h1 className="mt-4 text-xl font-bold text-gray-900">Initializing</h1>
            <p className="mt-2 text-center text-gray-600">
              Setting up the NYC Subway Monitor...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Connection error state
  if (!isConnected) {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center bg-gray-50">
        <div className="max-w-md rounded-lg bg-white p-8 shadow-lg">
          <div className="flex flex-col items-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h1 className="mt-4 text-xl font-bold text-red-600">Connection Error</h1>
            <p className="mt-2 text-center text-gray-700">
              Could not connect to the NYC Subway Monitor API. The service might be down or experiencing issues.
            </p>
            {connectionError && (
              <div className="mt-4 w-full rounded-md bg-red-50 p-3 text-sm text-red-800">
                <code>{connectionError}</code>
              </div>
            )}
            <div className="mt-6 flex space-x-4">
              <button
                onClick={() => setIsConnected(null)} // Trigger a reconnection attempt
                className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              >
                Try Again
              </button>
              
              {/* Option to use development mode */}
              <button
                onClick={() => setIsConnected(true)}
                className="rounded-md bg-gray-100 px-4 py-2 text-gray-700 hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-400 focus:ring-offset-2"
              >
                Continue Without API
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Main application
  return (
    <BrowserRouter>
      <SubwayDataProvider>
        <AlertProvider>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="alerts" element={<Alerts />} />
              <Route path="metrics" element={<Metrics />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </AlertProvider>
      </SubwayDataProvider>
    </BrowserRouter>
  );
};

export default App;