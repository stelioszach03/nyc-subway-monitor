import { useState } from 'react';
import { useSubwayData } from '../contexts/SubwayDataContext';
import ReactECharts from 'echarts-for-react';
import { ROUTE_COLORS } from '../types/subway';

const Metrics = () => {
  const { delays, trains } = useSubwayData();
  const [timeWindow, setTimeWindow] = useState('5m');
  const [viewMode, setViewMode] = useState<'table' | 'chart'>('chart');
  const [chartType, setChartType] = useState<'delay' | 'anomaly'>('delay');
  const [sortedDelays, setSortedDelays] = useState(delays);
  const [totalActive, setTotalActive] = useState(0);
  const [totalDelayed, setTotalDelayed] = useState(0);
  
  // Calculate stats
  useState(() => {
    // Sort delays by average delay (descending)
    setSortedDelays([...delays].sort((a, b) => b.avg_delay - a.avg_delay));
    
    // Calculate overall stats
    setTotalActive(trains.length);
    setTotalDelayed(trains.filter(t => t.delay && t.delay > 60).length);
  });

  // Generate chart options for delay bar chart
  const getDelayChartOptions = () => {
    const routeData = sortedDelays.slice(0, 15).map(delay => ({
      name: `${delay.route_id} Line`,
      value: Math.round(delay.avg_delay),
      itemStyle: {
        color: ROUTE_COLORS[delay.route_id] || '#888'
      }
    }));

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'shadow'
        },
        formatter: (params: any) => {
          const data = params[0];
          return `<div style="font-weight: bold">${data.name}</div>
                  <div>${data.value} seconds avg delay</div>`;
        }
      },
      grid: {
        left: '5%',
        right: '5%',
        top: '5%',
        bottom: '10%',
        containLabel: true
      },
      xAxis: {
        type: 'category',
        data: routeData.map(item => item.name),
        axisLabel: {
          rotate: 45,
          fontSize: 11
        }
      },
      yAxis: {
        type: 'value',
        name: 'Avg Delay (seconds)',
        nameLocation: 'end',
        nameTextStyle: {
          padding: [0, 0, 0, 10]
        }
      },
      series: [
        {
          type: 'bar',
          data: routeData,
          barWidth: '60%',
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: 'rgba(0, 0, 0, 0.5)'
            }
          }
        }
      ]
    };
  };

  // Generate chart options for anomaly scatter chart
  const getAnomalyChartOptions = () => {
    const scatterData = sortedDelays
      .filter(delay => delay.anomaly_score !== undefined)
      .map(delay => ([
        Math.round(delay.avg_delay),
        delay.anomaly_score,
        delay.route_id
      ]));

    return {
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          return `<div style="font-weight: bold">${params.data[2]} Line</div>
                  <div>Avg Delay: ${params.data[0]} seconds</div>
                  <div>Anomaly Score: ${params.data[1]?.toFixed(2) || 'N/A'}</div>`;
        }
      },
      grid: {
        left: '5%',
        right: '5%',
        top: '5%',
        bottom: '10%',
        containLabel: true
      },
      xAxis: {
        type: 'value',
        name: 'Avg Delay (seconds)',
        nameLocation: 'end'
      },
      yAxis: {
        type: 'value',
        name: 'Anomaly Score',
        nameLocation: 'end',
        min: 0,
        max: 1
      },
      series: [
        {
          type: 'scatter',
          symbolSize: (data: any) => {
            return Math.max(20, Math.min(40, data[1] * 50));
          },
          itemStyle: {
            color: (params: any) => {
              return ROUTE_COLORS[params.data[2]] || '#888';
            }
          },
          data: scatterData
        }
      ]
    };
  };

  // Calculate system health score based on delays and anomalies
  const getSystemHealthScore = () => {
    if (delays.length === 0) return 100;
    
    const avgDelayScore = Math.max(0, 100 - (delays.reduce((sum, d) => sum + d.avg_delay, 0) / delays.length) / 3);
    const anomalyScore = delays.some(d => d.anomaly_score !== undefined) 
      ? Math.max(0, 100 - (delays.reduce((sum, d) => sum + (d.anomaly_score || 0), 0) / delays.length) * 100)
      : 100;
      
    return Math.round((avgDelayScore * 0.7) + (anomalyScore * 0.3));
  };

  const systemHealth = getSystemHealthScore();
  const healthColor = systemHealth > 80 
    ? 'text-green-600' 
    : systemHealth > 60 
      ? 'text-yellow-600' 
      : 'text-red-600';

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col justify-between space-y-4 sm:flex-row sm:items-center sm:space-y-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Metrics</h1>
          <p className="mt-1 text-sm text-gray-600">
            Performance monitoring and statistics
          </p>
        </div>
        
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <select
              className="h-10 rounded-lg border border-gray-300 bg-white pl-3 pr-8 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={timeWindow}
              onChange={(e) => setTimeWindow(e.target.value)}
              aria-label="Select time window"
            >
              <option value="5m">Last 5 minutes</option>
              <option value="15m">Last 15 minutes</option>
              <option value="1h">Last hour</option>
              <option value="3h">Last 3 hours</option>
            </select>
          </div>
          
          <div className="flex rounded-md bg-gray-100 p-1 shadow-sm">
            <button
              className={`px-3 py-1.5 text-sm font-medium rounded-md ${
                viewMode === 'chart' 
                  ? 'bg-white text-blue-600 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-800'
              }`}
              onClick={() => setViewMode('chart')}
            >
              Charts
            </button>
            <button
              className={`px-3 py-1.5 text-sm font-medium rounded-md ${
                viewMode === 'table' 
                  ? 'bg-white text-blue-600 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-800'
              }`}
              onClick={() => setViewMode('table')}
            >
              Table
            </button>
          </div>
        </div>
      </div>
      
      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-white p-5 shadow-sm">
          <div className="flex items-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-blue-600">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-semibold uppercase text-gray-500">System Health</h3>
            </div>
          </div>
          <div className="mt-4">
            <div className="flex items-baseline">
              <p className={`text-4xl font-bold ${healthColor}`}>{systemHealth}%</p>
            </div>
            <div className="mt-1">
              <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
                <div 
                  className={`h-full rounded-full ${
                    systemHealth > 80 
                      ? 'bg-green-500' 
                      : systemHealth > 60 
                        ? 'bg-yellow-500' 
                        : 'bg-red-500'
                  }`}
                  style={{ width: `${systemHealth}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-lg bg-white p-5 shadow-sm">
          <div className="flex items-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-green-100 text-green-600">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-semibold uppercase text-gray-500">Active Routes</h3>
            </div>
          </div>
          <div className="mt-4">
            <div className="flex items-baseline">
              <p className="text-4xl font-bold text-gray-900">{delays.length}</p>
              <p className="ml-2 text-sm text-gray-600">routes</p>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              Out of 24 total subway lines
            </p>
          </div>
        </div>

        <div className="rounded-lg bg-white p-5 shadow-sm">
          <div className="flex items-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-semibold uppercase text-gray-500">Active Trains</h3>
            </div>
          </div>
          <div className="mt-4">
            <div className="flex items-baseline">
              <p className="text-4xl font-bold text-gray-900">{totalActive}</p>
              <p className="ml-2 text-sm text-gray-600">vehicles</p>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              Currently in service
            </p>
          </div>
        </div>

        <div className="rounded-lg bg-white p-5 shadow-sm">
          <div className="flex items-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-yellow-100 text-yellow-600">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-semibold uppercase text-gray-500">Delayed Trains</h3>
            </div>
          </div>
          <div className="mt-4">
            <div className="flex items-baseline">
              <p className="text-4xl font-bold text-gray-900">{totalDelayed}</p>
              <p className="ml-2 text-sm text-gray-600">vehicles</p>
            </div>
            <p className="mt-1 text-sm text-gray-500">
              More than 60 seconds late
            </p>
          </div>
        </div>
      </div>
      
      {/* Main content */}
      {viewMode === 'chart' ? (
        <div className="space-y-6">
          <div className="flex flex-col space-y-4 rounded-lg bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
            <h2 className="text-lg font-semibold text-gray-900">Performance Visualization</h2>
            
            <div className="flex rounded-md bg-gray-100 p-1 shadow-sm">
              <button
                className={`px-3 py-1.5 text-sm font-medium rounded-md ${
                  chartType === 'delay' 
                    ? 'bg-white text-blue-600 shadow-sm' 
                    : 'text-gray-600 hover:text-gray-800'
                }`}
                onClick={() => setChartType('delay')}
              >
                Delay Chart
              </button>
              <button
                className={`px-3 py-1.5 text-sm font-medium rounded-md ${
                  chartType === 'anomaly' 
                    ? 'bg-white text-blue-600 shadow-sm' 
                    : 'text-gray-600 hover:text-gray-800'
                }`}
                onClick={() => setChartType('anomaly')}
              >
                Anomaly Plot
              </button>
            </div>
          </div>
          
          <div className="rounded-lg bg-white p-5 shadow-sm">
            <div className="h-80">
              {chartType === 'delay' ? (
                <ReactECharts 
                  option={getDelayChartOptions()} 
                  style={{ height: '100%', width: '100%' }}
                  opts={{ renderer: 'canvas' }}
                />
              ) : (
                <ReactECharts 
                  option={getAnomalyChartOptions()} 
                  style={{ height: '100%', width: '100%' }}
                  opts={{ renderer: 'canvas' }}
                />
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-lg bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Route Performance Metrics</h2>
          
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
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {sortedDelays.map((delay) => {
                  // Determine delay status color
                  let statusText = 'Normal';
                  let statusColor = 'bg-green-100 text-green-800';
                  
                  if (delay.avg_delay > 300) {
                    statusText = 'Severe Delays';
                    statusColor = 'bg-red-100 text-red-800';
                  } else if (delay.avg_delay > 120) {
                    statusText = 'Moderate Delays';
                    statusColor = 'bg-yellow-100 text-yellow-800';
                  } else if (delay.anomaly_score && delay.anomaly_score > 0.7) {
                    statusText = 'Anomaly Detected';
                    statusColor = 'bg-purple-100 text-purple-800';
                  }
                  
                  return (
                    <tr key={delay.route_id}>
                      <td className="whitespace-nowrap px-6 py-4">
                        <div className="flex items-center">
                          <div 
                            className="flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold text-white"
                            style={{ backgroundColor: ROUTE_COLORS[delay.route_id] || '#666' }}
                          >
                            {delay.route_id}
                          </div>
                          <div className="ml-2 text-sm font-medium text-gray-900">{delay.route_id} Line</div>
                        </div>
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
                          {delay.anomaly_score 
                            ? (
                              <div className="flex items-center">
                                <span className="font-medium">{delay.anomaly_score.toFixed(2)}</span>
                                {delay.anomaly_score > 0.7 && (
                                  <svg xmlns="http://www.w3.org/2000/svg" className="ml-1 h-4 w-4 text-red-500" viewBox="0 0 20 20" fill="currentColor">
                                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                                  </svg>
                                )}
                              </div>
                            ) 
                            : 'N/A'
                          }
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${statusColor}`}>
                          {statusText}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default Metrics;