import { useState } from 'react';
import { useAlerts } from '../contexts/AlertContext';
import { ROUTE_COLORS } from '../types/subway';
import { Alert } from '../types/subway';

const AlertCard = ({ alert, onDismiss }: { alert: Alert; onDismiss: (id: string) => void }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Get severity color
  const getSeverityColor = (severity: string) => {
    switch (severity.toUpperCase()) {
      case 'HIGH':
        return 'bg-red-100 text-red-800 border-red-500';
      case 'MEDIUM':
        return 'bg-yellow-100 text-yellow-800 border-yellow-500';
      case 'LOW':
        return 'bg-blue-100 text-blue-800 border-blue-500';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-500';
    }
  };
  
  // Format timestamp
  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      hour12: true
    }).format(date);
  };
  
  return (
    <div 
      className={`rounded-lg border-l-4 bg-white p-4 shadow-sm transition-all duration-200 ${
        getSeverityColor(alert.severity)
      } ${isExpanded ? 'ring-2 ring-blue-300 ring-opacity-50' : ''}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2">
            <div 
              className="flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold text-white"
              style={{ backgroundColor: ROUTE_COLORS[alert.route_id] || '#666' }}
            >
              {alert.route_id}
            </div>
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
          
          <p className="mt-1 text-gray-700">
            {alert.message}
          </p>
          
          <div className="mt-3 flex items-center justify-between text-sm text-gray-500">
            <div className="flex items-center space-x-2">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{formatTimestamp(alert.timestamp)}</span>
            </div>
            
            <div 
              className="cursor-pointer text-blue-600 hover:text-blue-800"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? 'Show less' : 'Details'}
            </div>
          </div>
          
          {isExpanded && (
            <div className="mt-3 rounded-md bg-gray-50 p-3">
              <div className="grid grid-cols-2 gap-y-2 text-sm">
                <div className="text-gray-600">Alert ID:</div>
                <div className="font-mono text-gray-800">{alert.id}</div>
                
                <div className="text-gray-600">Anomaly Score:</div>
                <div className="font-medium text-gray-800">{alert.anomaly_score.toFixed(2)}</div>
                
                <div className="text-gray-600">Detected at:</div>
                <div className="text-gray-800">{new Date(alert.timestamp).toLocaleString()}</div>
              </div>
            </div>
          )}
        </div>
        
        <button
          onClick={() => onDismiss(alert.id)}
          className="ml-4 flex-shrink-0 rounded-md bg-gray-200 px-3 py-1 text-sm text-gray-700 hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-400"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
};

const Alerts = () => {
  const { alerts, dismissAlert, clearAllDismissed, dismissedAlerts } = useAlerts();
  const [filter, setFilter] = useState('all');
  const [sortBy, setSortBy] = useState<'newest' | 'severity'>('newest');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Filter alerts
  const filteredAlerts = alerts
    .filter(alert => {
      // Filter by severity
      if (filter !== 'all' && alert.severity.toLowerCase() !== filter.toLowerCase()) {
        return false;
      }
      
      // Filter by search query
      if (searchQuery && 
          !alert.message.toLowerCase().includes(searchQuery.toLowerCase()) && 
          !alert.route_id.toLowerCase().includes(searchQuery.toLowerCase())) {
        return false;
      }
      
      return true;
    })
    .sort((a, b) => {
      // Sort by timestamp (newest first) or severity
      if (sortBy === 'newest') {
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      } else {
        // Sort by severity (HIGH > MEDIUM > LOW)
        const severityOrder = { 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1 };
        return (severityOrder[b.severity as keyof typeof severityOrder] || 0) - 
               (severityOrder[a.severity as keyof typeof severityOrder] || 0);
      }
    });

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Alerts</h1>
          <p className="mt-1 text-sm text-gray-600">
            Monitoring anomalies and delays across the subway system
          </p>
        </div>
        
        {dismissedAlerts.length > 0 && (
          <button
            onClick={clearAllDismissed}
            className="mt-3 flex items-center rounded-md bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100 sm:mt-0"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="mr-1.5 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Restore {dismissedAlerts.length} dismissed
          </button>
        )}
      </div>
      
      {/* Filters */}
      <div className="flex flex-col space-y-3 rounded-lg bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
        <div className="flex flex-1 items-center space-x-3">
          <div className="relative flex-1 sm:max-w-xs">
            <input
              type="text"
              placeholder="Search alerts..."
              className="w-full rounded-md border border-gray-300 py-2 pl-10 pr-3 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <div className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-400">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>
          
          <div>
            <select
              className="rounded-md border border-gray-300 py-2 pl-3 pr-8 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Filter by severity"
            >
              <option value="all">All Severities</option>
              <option value="high">High Priority</option>
              <option value="medium">Medium Priority</option>
              <option value="low">Low Priority</option>
            </select>
          </div>
        </div>
        
        <div className="flex items-center space-x-2 text-sm text-gray-600">
          <span>Sort by:</span>
          <div className="flex rounded-md bg-gray-100 p-1">
            <button
              className={`rounded px-3 py-1 ${
                sortBy === 'newest' 
                  ? 'bg-white font-medium shadow-sm text-blue-600' 
                  : 'text-gray-600 hover:text-gray-800'
              }`}
              onClick={() => setSortBy('newest')}
            >
              Newest
            </button>
            <button
              className={`rounded px-3 py-1 ${
                sortBy === 'severity' 
                  ? 'bg-white font-medium shadow-sm text-blue-600' 
                  : 'text-gray-600 hover:text-gray-800'
              }`}
              onClick={() => setSortBy('severity')}
            >
              Severity
            </button>
          </div>
        </div>
      </div>
      
      {/* Alerts list */}
      {filteredAlerts.length === 0 ? (
        <div className="mt-8 rounded-lg bg-gray-50 p-8 text-center shadow-sm">
          <div className="mx-auto h-12 w-12 rounded-full bg-gray-100 text-gray-400 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
            </svg>
          </div>
          <h3 className="mt-3 text-lg font-medium text-gray-900">No alerts found</h3>
          <p className="mt-2 text-sm text-gray-500">
            {searchQuery || filter !== 'all' 
              ? 'Try adjusting your filters or search query' 
              : 'There are currently no active alerts in the system'}
          </p>
          {(searchQuery || filter !== 'all') && (
            <button
              onClick={() => {
                setSearchQuery('');
                setFilter('all');
              }}
              className="mt-4 rounded-md bg-white px-4 py-2 text-sm font-medium text-blue-600 shadow-sm hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>{filteredAlerts.length} {filteredAlerts.length === 1 ? 'alert' : 'alerts'} found</span>
          </div>
          
          {filteredAlerts.map(alert => (
            <AlertCard 
              key={alert.id} 
              alert={alert} 
              onDismiss={dismissAlert}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default Alerts;