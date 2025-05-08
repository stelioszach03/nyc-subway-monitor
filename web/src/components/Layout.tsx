import { Link, Outlet } from 'react-router-dom';
import { useAlerts } from '../contexts/AlertContext';
import { useSubwayData } from '../contexts/SubwayDataContext';

const Layout = () => {
  const { highPriorityAlerts } = useAlerts();
  const { isLoading } = useSubwayData();

  return (
    <div className="flex h-screen flex-col bg-gray-100">
      <header className="bg-blue-800 text-white shadow-md">
        <div className="container mx-auto flex items-center justify-between p-4">
          <h1 className="text-2xl font-bold">NYC Subway Monitor</h1>
          <nav>
            <ul className="flex space-x-6">
              <li>
                <Link to="/" className="hover:text-blue-200">Dashboard</Link>
              </li>
              <li>
                <Link to="/alerts" className="hover:text-blue-200">
                  Alerts
                  {highPriorityAlerts.length > 0 && (
                    <span className="ml-2 rounded-full bg-red-500 px-2 py-1 text-xs">
                      {highPriorityAlerts.length}
                    </span>
                  )}
                </Link>
              </li>
              <li>
                <Link to="/metrics" className="hover:text-blue-200">Metrics</Link>
              </li>
            </ul>
          </nav>
        </div>
      </header>
      
      {isLoading && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="rounded-lg bg-white p-4 shadow-lg">
            <p className="text-lg">Loading data...</p>
          </div>
        </div>
      )}
      
      <main className="container mx-auto flex-1 p-4">
        <Outlet />
      </main>
      
      <footer className="bg-gray-800 text-center text-white py-4">
        <p>NYC Subway Monitor &copy; {new Date().getFullYear()}</p>
      </footer>
    </div>
  );
};

export default Layout;
