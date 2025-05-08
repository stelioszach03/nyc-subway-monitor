import { useState } from 'react';
import { useSubwayData } from '../contexts/SubwayDataContext';

const Metrics = () => {
  const { delays } = useSubwayData();
  const [timeWindow, setTimeWindow] = useState('5m');
  
  // Sort delays by average delay (descending)
  const sortedDelays = [...delays].sort((a, b) => b.avg_delay - a.avg_delay);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">System Metrics</h2>
        <div>
          <select
            className="rounded-md border border-gray-300 px-4 py-2"
            value={timeWindow}
            onChange={(e) => setTimeWindow(e.target.value)}
          >
            <option value="5m">Last 5 minutes</option>
            <option value="15m">Last 15 minutes</option>
            <option value="1h">Last hour</option>
            <option value="3h">Last 3 hours</option>
          </select>
        </div>
      </div>
      
      <div className="rounded-lg bg-white p-6 shadow">
        <h3 className="mb-4 text-xl font-semibold">Average Delays by Line</h3>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Line
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Avg. Delay (sec)
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Active Trains
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Anomaly Score
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {sortedDelays.map((delay) => (
                <tr key={delay.route_id}>
                  <td className="whitespace-nowrap px-6 py-4">
                    <div className="text-sm font-medium text-gray-900">{delay.route_id} Line</div>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <div className={`text-sm ${
                      delay.avg_delay > 300 
                        ? 'font-bold text-red-600' 
                        : delay.avg_delay > 120 
                          ? 'font-medium text-yellow-600' 
                          : 'text-gray-900'
                    }`}>
                      {Math.round(delay.avg_delay)}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <div className="text-sm text-gray-900">{delay.train_count}</div>
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <div className="text-sm text-gray-900">
                      {delay.anomaly_score ? delay.anomaly_score.toFixed(2) : 'N/A'}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Metrics;
