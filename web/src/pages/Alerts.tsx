import { useState } from 'react';
import { useAlerts } from '../contexts/AlertContext';

const Alerts = () => {
  const { alerts, dismissAlert } = useAlerts();
  const [filter, setFilter] = useState('all');

  const filteredAlerts = filter === 'all' 
    ? alerts 
    : alerts.filter(alert => alert.severity.toLowerCase() === filter.toLowerCase());

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">System Alerts</h2>
        <div>
          <select
            className="rounded-md border border-gray-300 px-4 py-2"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All Severities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>
      
      {filteredAlerts.length === 0 ? (
        <div className="mt-8 rounded-lg bg-gray-100 p-8 text-center">
          <p className="text-lg text-gray-600">No alerts matching your criteria</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredAlerts.map(alert => (
            <div 
              key={alert.id} 
              className={`rounded-lg border-l-4 bg-white p-4 shadow ${
                alert.severity === 'HIGH' 
                  ? 'border-red-500' 
                  : alert.severity === 'MEDIUM' 
                    ? 'border-yellow-500' 
                    : 'border-blue-500'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-lg font-bold">{alert.route_id} Line</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                      alert.severity === 'HIGH' 
                        ? 'bg-red-100 text-red-800' 
                        : alert.severity === 'MEDIUM' 
                          ? 'bg-yellow-100 text-yellow-800' 
                          : 'bg-blue-100 text-blue-800'
                    }`}>
                      {alert.severity}
                    </span>
                  </div>
                  <p className="mt-1 text-gray-700">{alert.message}</p>
                  <p className="mt-2 text-sm text-gray-500">
                    {new Date(alert.timestamp).toLocaleString()}
                  </p>
                </div>
                <button
                  onClick={() => dismissAlert(alert.id)}
                  className="rounded-md bg-gray-200 px-3 py-1 text-sm text-gray-700 hover:bg-gray-300"
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Alerts;
