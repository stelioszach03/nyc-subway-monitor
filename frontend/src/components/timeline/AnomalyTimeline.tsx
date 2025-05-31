
import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import * as d3 from 'd3'
import { format } from 'date-fns'
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  Cell
} from 'recharts'
import { TimelineControls } from './TimelineControls'
import { LoadingSkeleton } from '../ui/LoadingSkeleton'
import { AnomalyCard } from '../ui/AnomalyCard'
import type { Anomaly } from '@/types'

interface AnomalyTimelineProps {
  anomalies: Anomaly[]
  timeRange: [Date, Date]
  onTimeRangeChange: (range: [Date, Date]) => void
  isLoading?: boolean
}

export function AnomalyTimeline({ 
  anomalies, 
  timeRange, 
  onTimeRangeChange,
  isLoading 
}: AnomalyTimelineProps) {
  const [selectedAnomaly, setSelectedAnomaly] = useState<Anomaly | null>(null)
  const [viewMode, setViewMode] = useState<'chart' | 'list'>('chart')

  // Prepare data for charts
  const chartData = anomalies.map(anomaly => ({
    time: new Date(anomaly.timestamp).getTime(),
    timeFormatted: format(new Date(anomaly.timestamp), 'HH:mm'),
    severity: anomaly.confidence * 100,
    type: anomaly.type,
    station: anomaly.station_name,
    color: getSeverityColor(anomaly.severity)
  }))

  const getSeverityColor = (severity: 'low' | 'medium' | 'high' | 'critical') => {
    switch (severity) {
      case 'low': return '#3B82F6'
      case 'medium': return '#F59E0B'
      case 'high': return '#EF4444'
      case 'critical': return '#DC2626'
      default: return '#6B7280'
    }
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      return (
        <motion.div
          className="bg-gray-900/95 backdrop-blur-xl border border-white/10 rounded-xl p-4 shadow-2xl"
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2 }}
        >
          <h3 className="text-white font-semibold mb-2">{data.type}</h3>
          <div className="space-y-1 text-sm">
            <div className="text-gray-300">
              <span className="text-gray-400">Station:</span> {data.station}
            </div>
            <div className="text-gray-300">
              <span className="text-gray-400">Time:</span> {data.timeFormatted}
            </div>
            <div className="text-gray-300">
              <span className="text-gray-400">Confidence:</span> {data.severity.toFixed(1)}%
            </div>
          </div>
        </motion.div>
      )
    }
    return null
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-white/10">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-white">Anomaly Timeline</h2>
            <p className="text-sm text-gray-400">
              {anomalies.length} anomalies detected
            </p>
          </div>
          
          {/* View Toggle */}
          <div className="flex bg-white/5 rounded-xl p-1">
            <motion.button
              className={`px-3 py-1 rounded-lg text-sm font-medium transition-all ${
                viewMode === 'chart' 
                  ? 'bg-blue-500 text-white' 
                  : 'text-gray-400 hover:text-white'
              }`}
              onClick={() => setViewMode('chart')}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              Chart
            </motion.button>
            <motion.button
              className={`px-3 py-1 rounded-lg text-sm font-medium transition-all ${
                viewMode === 'list' 
                  ? 'bg-blue-500 text-white' 
                  : 'text-gray-400 hover:text-white'
              }`}
              onClick={() => setViewMode('list')}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              List
            </motion.button>
          </div>
        </div>
        
        <TimelineControls
          timeRange={timeRange}
          onTimeRangeChange={onTimeRangeChange}
        />
      </div>
      
      {/* Content */}
      <div className="flex-1 p-4">
        <AnimatePresence mode="wait">
          {isLoading ? (
            <motion.div
              key="loading"
              className="h-full flex flex-col gap-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <LoadingSkeleton className="h-8 w-48" />
              <LoadingSkeleton className="h-64 w-full" />
              <div className="space-y-2">
                <LoadingSkeleton className="h-16 w-full" />
                <LoadingSkeleton className="h-16 w-full" />
                <LoadingSkeleton className="h-16 w-full" />
              </div>
            </motion.div>
          ) : anomalies.length === 0 ? (
            <motion.div
              key="empty"
              className="h-full flex items-center justify-center"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <div className="text-center">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-800 flex items-center justify-center">
                  <span className="text-2xl">📊</span>
                </div>
                <h3 className="text-lg font-medium text-gray-300 mb-2">
                  No anomalies detected
                </h3>
                <p className="text-gray-500">
                  No anomalies found in the selected time range
                </p>
              </div>
            </motion.div>
          ) : viewMode === 'chart' ? (
            <motion.div
              key="chart"
              className="h-full"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
            >
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis 
                    dataKey="time"
                    type="number"
                    scale="time"
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={(value) => format(new Date(value), 'HH:mm')}
                    stroke="#9CA3AF"
                  />
                  <YAxis 
                    dataKey="severity"
                    domain={[0, 100]}
                    tickFormatter={(value) => `${value}%`}
                    stroke="#9CA3AF"
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Scatter dataKey="severity" fill="#8884d8">
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </motion.div>
          ) : (
            <motion.div
              key="list"
              className="h-full overflow-y-auto custom-scrollbar space-y-3"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
            >
              {anomalies.map((anomaly, index) => (
                <AnomalyCard
                  key={anomaly.id}
                  anomaly={anomaly}
                  index={index}
                  onClick={() => setSelectedAnomaly(anomaly)}
                />
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}