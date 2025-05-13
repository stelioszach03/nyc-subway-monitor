import { useState, useEffect } from 'react';
import SubwayMap from '../components/SubwayMap';
import { useSubwayData } from '../contexts/SubwayDataContext';
import { useAlerts } from '../contexts/AlertContext';
import { Link } from 'react-router-dom';
import { ROUTE_COLORS } from '../types/subway';

// Group subway routes by color family
const ROUTE_GROUPS = {
  'Red Lines': ['1', '2', '3'],
  'Green Lines': ['4', '5', '6'],
  'Blue Lines': ['A', 'C', 'E'],
  'Orange Lines': ['B', 'D', 'F', 'M'],
  'Purple Line': ['7'],
  'Brown Lines': ['J', 'Z'],
  'Light Green Line': ['G'],
  'Gray Line': ['L'],
  'Yellow Lines': ['N', 'Q', 'R', 'W'],
  'Shuttle': ['S'],
  'Staten Island': ['SI']
};

const Dashboard = () => {
  const { trains, delays } = useSubwayData();
  const { highPriorityAlerts } = useAlerts();
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);
  const [activeTrains, setActiveTrains] = useState<number>(0);
  const [totalDelayedTrains, setTotalDelayedTrains] = useState<number>(0);
  const [showStats, setShowStats] = useState<boolean>(true);

  // Filter trains by selected route
  const filteredTrains = selectedRoute
    ? trains.filter(train => train.route_id === selectedRoute)
    : trains;

  // Calculate stats when trains data changes
  useEffect(() => {
    setActiveTrains(filteredTrains.length);
    
    // Count trains with delays over 60 seconds
    const delayedTrains = filteredTrains.filter(train => 
      train.delay !== undefined && train.delay > 60
    ).length;
    
    setTotalDelayedTrains(delayedTrains);
  }, [filteredTrains]);

  // Find most delayed routes from delays data
  const topDelayedRoutes = [...delays]
    .sort((a, b) => b.avg_delay - a.avg_delay)
    .slice(0, 3);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col justify-between space-y-4 sm:flex-row sm:items-center sm:space-y-0">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Live Subway Map</h1>
          <p className="mt-1 text-sm text-gray-600">Real-time monitoring of the NYC subway system</p>
        </div>
        
        <div className="flex flex-wrap items-center gap-3">
          {/* Route selector */}
          <div className="group relative">
            <select
              className="h-10 rounded-lg border border-gray-300 bg-white pl-3 pr-8 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              onChange={(e) => setSelectedRoute(e.target.value === 'all' ? null : e.target.value)}
              value={selectedRoute || 'all'}
              aria-label="Select route"
            >
              <option value="all">All Lines</option>
              {Object.entries(ROUTE_GROUPS).map(([groupName, routes]) => (
                <optgroup key={groupName} label={groupName}>
                  {routes.map(route => (
                    <option key={route} value={route}>
                      {route} Line
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          
          {/* Toggle stats button */}
          <button
            onClick={() => setShowStats(!showStats)}
            className="flex h-10 items-center rounded-lg border border-gray-300 bg-white px-4 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
            aria-label={showStats ? "Hide statistics" : "Show statistics"}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            {showStats ? "Hide Stats" : "Show Stats"}
          </button>
        </div>
      </div>

      {/* Alert banner */}
      {highPriorityAlerts.length > 0 && (
        <div className="rounded-lg bg-red-50 p-4 shadow-sm">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-600" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="font-medium text-red-800">
                {highPriorityAlerts.length} high-priority {highPriorityAlerts.length === 1 ? 'alert' : 'alerts'} active
              </h3>
              <div className="mt-2 text-sm text-red-700">
                <Link to="/alerts" className="underline hover:text-red-800">
                  View all alerts
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        {/* Stats cards */}
        {showStats && (
          <div className="flex flex-col space-y-6 lg:col-span-1">
            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold uppercase text-gray-500">Active Trains</h3>
              <div className="mt-2 flex items-baseline">
                <p className="text-3xl font-bold text-gray-900">{activeTrains}</p>
                <p className="ml-2 text-sm text-gray-600">
                  vehicles
                </p>
              </div>
              <div className="mt-1 text-xs text-gray-500">
                {selectedRoute 
                  ? `On the ${selectedRoute} Line` 
                  : 'Across all lines'}
              </div>
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold uppercase text-gray-500">Delayed Trains</h3>
              <div className="mt-2 flex items-baseline">
                <p className="text-3xl font-bold text-gray-900">{totalDelayedTrains}</p>
                <p className="ml-2 text-sm text-gray-600">
                  vehicles
                </p>
              </div>
              <div className="mt-1 text-xs text-gray-500">
                With delays over 60 seconds
              </div>
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold uppercase text-gray-500">Top Delayed Routes</h3>
              <div className="mt-3 flex flex-col space-y-3">
                {topDelayedRoutes.length > 0 ? (
                  topDelayedRoutes.map(route => (
                    <div key={route.route_id} className="flex items-center justify-between">
                      <div className="flex items-center">
                        <div 
                          className="flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold text-white"
                          style={{ backgroundColor: ROUTE_COLORS[route.route_id] || '#666' }}
                        >
                          {route.route_id}
                        </div>
                        <span className="ml-2 text-sm font-medium">Line</span>
                      </div>
                      <div className="flex items-center">
                        <span className="text-sm font-semibold">
                          {Math.round(route.avg_delay)}s
                        </span>
                        <span className="ml-1 text-xs text-gray-500">avg delay</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center text-sm text-gray-500">No delay data available</div>
                )}
              </div>
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="text-sm font-semibold uppercase text-gray-500">Legend</h3>
              <div className="mt-3 grid grid-cols-2 gap-y-2 gap-x-4">
                {Object.keys(ROUTE_GROUPS).map(groupName => (
                  <div key={groupName} className="flex items-center">
                    <div className="flex">
                      {ROUTE_GROUPS[groupName as keyof typeof ROUTE_GROUPS].map((route, idx) => (
                        <div 
                          key={route} 
                          className="flex h-5 w-5 items-center justify-center rounded-full text-white text-xs font-bold mr-1"
                          style={{ 
                            backgroundColor: ROUTE_COLORS[route] || '#666',
                            marginLeft: idx > 0 ? '-5px' : '0'
                          }}
                        >
                          {route.length === 1 ? route : ''}
                        </div>
                      ))}
                    </div>
                    <span className="ml-1 text-xs text-gray-700">{groupName}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Map container */}
        <div className={`${showStats ? 'lg:col-span-3' : 'lg:col-span-4'} overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm h-[calc(100vh-220px)] min-h-[500px]`}>
          <SubwayMap selectedRoute={selectedRoute} />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;