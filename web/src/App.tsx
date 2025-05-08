import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Alerts from './pages/Alerts';
import Metrics from './pages/Metrics';
import Layout from './components/Layout';
import { AlertProvider } from './contexts/AlertContext';
import { SubwayDataProvider } from './contexts/SubwayDataContext';

const App = () => {
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // Check API connection
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    fetch(`${apiUrl}/health`)
      .then(response => {
        if (response.ok) {
          setIsConnected(true);
        }
      })
      .catch(error => {
        console.error('API connection failed:', error);
        setIsConnected(false);
      });
  }, []);

  if (!isConnected) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-gray-100">
        <div className="rounded-lg bg-white p-8 shadow-lg">
          <h1 className="text-2xl font-bold text-red-600">Connection Error</h1>
          <p className="mt-4 text-gray-700">
            Could not connect to the NYC Subway Monitor API. Please check your connection and try again.
          </p>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <SubwayDataProvider>
        <AlertProvider>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="alerts" element={<Alerts />} />
              <Route path="metrics" element={<Metrics />} />
            </Route>
          </Routes>
        </AlertProvider>
      </SubwayDataProvider>
    </BrowserRouter>
  );
};

export default App;
