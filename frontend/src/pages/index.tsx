import { useState, useEffect } from 'react'
import Head from 'next/head'
import dynamic from 'next/dynamic'
import { Layout } from '@/components/layout/Layout'
import { AnomalyTimeline } from '@/components/timeline/AnomalyTimeline'
import { useAnomalies } from '@/hooks/useAnomalies'
import { useWebSocket } from '@/hooks/useWebSocket'
import type { Anomaly, LineInfo } from '@/types'

// Dynamic import to prevent SSR issues
const SubwayMap = dynamic(
  () => import('@/components/map/SubwayMap').then(mod => mod.SubwayMap),
  { 
    ssr: false,
    loading: () => <div className="w-full h-full bg-gray-900 animate-pulse" />
  }
)

export default function Home() {
  const [selectedLine, setSelectedLine] = useState<string | null>(null)
  const [selectedStation, setSelectedStation] = useState<string | null>(null)
  const [timeRange, setTimeRange] = useState<[Date, Date]>([
    new Date(Date.now() - 24 * 60 * 60 * 1000),
    new Date()
  ])
  const [mounted, setMounted] = useState(false)

  // Prevent hydration errors
  useEffect(() => {
    setMounted(true)
  }, [])

  // Fetch anomalies
  const { anomalies, stats, isLoading } = useAnomalies({
    line: selectedLine,
    station: selectedStation,
    startDate: timeRange[0],
    endDate: timeRange[1],
  })

  // WebSocket for real-time updates
  const { isConnected } = useWebSocket({
    onAnomalyReceived: (anomaly: Anomaly) => {
      console.log('New anomaly:', anomaly)
    },
  })

  // Loading state for SSR
  if (!mounted) {
    return (
      <Layout>
        <div className="flex flex-col h-screen bg-gray-950">
          <div className="px-6 py-4 bg-gray-900 border-b border-gray-800">
            <div className="animate-pulse h-20 bg-gray-800 rounded" />
          </div>
          <div className="flex-1 bg-gray-900 animate-pulse" />
        </div>
      </Layout>
    )
  }

  return (
    <>
      <Head>
        <title>NYC Subway Monitor - Real-time Anomaly Detection</title>
      </Head>

      <Layout>
        <div className="flex flex-col h-screen bg-gray-950">
          {/* Header Stats */}
          <div className="px-6 py-4 bg-gray-900 border-b border-gray-800">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                label="Active Anomalies"
                value={stats?.total_active || 0}
                color="text-red-400"
              />
              <StatCard
                label="Today's Total"
                value={stats?.total_today || 0}
                color="text-yellow-400"
              />
              <StatCard
                label="High Severity"
                value={stats?.severity_distribution?.high || 0}
                color="text-orange-400"
              />
              <StatCard
                label="Connection"
                value={isConnected ? 'Live' : 'Offline'}
                color={isConnected ? 'text-green-400' : 'text-gray-400'}
              />
            </div>
          </div>

          {/* Main Content */}
          <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
            {/* Map */}
            <div className="flex-1 relative">
              {mounted && (
                <SubwayMap
                  anomalies={anomalies}
                  onStationClick={setSelectedStation}
                  selectedStation={selectedStation}
                />
              )}
              
              {/* Line Filter */}
              <div className="absolute top-4 left-4 bg-gray-900/90 backdrop-blur-sm rounded-lg p-3 shadow-xl">
                <LineSelector
                  selectedLine={selectedLine}
                  onChange={setSelectedLine}
                  anomalyCounts={stats?.by_line}
                />
              </div>
            </div>

            {/* Timeline */}
            <div className="h-64 lg:h-auto lg:w-96 bg-gray-900 border-t lg:border-t-0 lg:border-l border-gray-800">
              <AnomalyTimeline
                anomalies={anomalies}
                timeRange={timeRange}
                onTimeRangeChange={setTimeRange}
                isLoading={isLoading}
              />
            </div>
          </div>
        </div>
      </Layout>
    </>
  )
}

// Client-only components
interface StatCardProps {
  label: string
  value: string | number
  color?: string
}

function StatCard({ label, value, color = 'text-gray-100' }: StatCardProps) {
  const [isClient, setIsClient] = useState(false)
  
  useEffect(() => {
    setIsClient(true)
  }, [])
  
  if (!isClient) {
    return (
      <div className="bg-gray-800/50 rounded-lg p-3">
        <p className="text-xs text-gray-400 mb-1">{label}</p>
        <p className="text-2xl font-bold text-gray-500">-</p>
      </div>
    )
  }
  
  return (
    <div className="bg-gray-800/50 rounded-lg p-3">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  )
}

interface LineSelectorProps {
  selectedLine: string | null
  onChange: (line: string | null) => void
  anomalyCounts?: Record<string, number>
}

function LineSelector({ selectedLine, onChange, anomalyCounts = {} }: LineSelectorProps) {
  const lines: LineInfo[] = [
    { id: '123456', label: '1/2/3/4/5/6', color: 'bg-red-500' },
    { id: '7', label: '7', color: 'bg-purple-500' },
    { id: 'ace', label: 'A/C/E', color: 'bg-blue-500' },
    { id: 'bdfm', label: 'B/D/F/M', color: 'bg-orange-500' },
    { id: 'g', label: 'G', color: 'bg-green-500' },
    { id: 'jz', label: 'J/Z', color: 'bg-amber-700' },
    { id: 'l', label: 'L', color: 'bg-gray-400' },
    { id: 'nqrw', label: 'N/Q/R/W', color: 'bg-yellow-500' },
    { id: 's', label: 'S', color: 'bg-gray-500' },
  ]

  return (
    <div>
      <h3 className="text-sm font-medium text-gray-300 mb-2">Filter by Line</h3>
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onChange(null)}
          className={`px-3 py-1 rounded text-sm transition-all ${
            selectedLine === null
              ? 'bg-blue-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          All Lines
        </button>
        {lines.map(line => (
          <button
            key={line.id}
            onClick={() => onChange(line.id)}
            className={`px-3 py-1 rounded text-sm transition-all flex items-center gap-1 ${
              selectedLine === line.id
                ? 'bg-gray-800 text-white ring-2 ring-blue-500'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
          >
            <span className={`w-3 h-3 rounded-full ${line.color}`} />
            {line.label}
            {anomalyCounts[line.id] && (
              <span className="ml-1 text-xs text-gray-400">
                ({anomalyCounts[line.id]})
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}