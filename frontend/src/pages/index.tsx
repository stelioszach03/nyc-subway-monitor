import { useState, useEffect } from 'react'
import Head from 'next/head'
import dynamic from 'next/dynamic'
import { motion } from 'framer-motion'
import { Toaster } from 'react-hot-toast'
import { 
  TrainIcon, 
  ExclamationTriangleIcon, 
  SignalIcon,
  ClockIcon,
  MapPinIcon,
  ChartBarIcon,
  PlusIcon,
  ArrowUpIcon
} from '@heroicons/react/24/outline'
import { Layout } from '@/components/layout/Layout'
import { AnomalyTimeline } from '@/components/timeline/AnomalyTimeline'
import { useAnomalies } from '@/hooks/useAnomalies'
import { useWebSocket } from '@/hooks/useWebSocket'
import { HeroSection } from '@/components/ui/HeroSection'
import { ModernStatsCard } from '@/components/ui/ModernStatsCard'
import { GlassCard } from '@/components/ui/GlassCard'
import { StatusIndicator } from '@/components/ui/StatusIndicator'
import { LoadingSkeleton } from '@/components/ui/LoadingSkeleton'
import { FloatingActionButton } from '@/components/ui/FloatingActionButton'
import { showSuccess } from '@/components/ui/NotificationToast'
import type { Anomaly, LineInfo } from '@/types'

// Dynamic import to prevent SSR issues
const EnhancedSubwayMap = dynamic(
  () => import('@/components/map/EnhancedSubwayMap').then(mod => mod.EnhancedSubwayMap),
  { 
    ssr: false,
    loading: () => (
      <div className="w-full h-full bg-gray-900 animate-pulse rounded-2xl flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto mb-3" />
          <p className="text-gray-400 text-sm">Loading Enhanced Map...</p>
        </div>
      </div>
    )
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
        <meta name="description" content="Advanced real-time monitoring system for NYC subway operations with anomaly detection and predictive analytics" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <Layout>
        <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950">
          <Toaster 
            position="top-right"
            toastOptions={{
              style: {
                background: 'rgba(17, 24, 39, 0.8)',
                color: '#fff',
                backdropFilter: 'blur(16px)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
              },
            }}
          />
          
          {/* Hero Section */}
          <HeroSection />

          {/* Stats Dashboard */}
          <div className="px-6 py-8">
            <motion.div 
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 1.2 }}
            >
              <ModernStatsCard
                title="Active Anomalies"
                value={stats?.total_active || 0}
                icon={<ExclamationTriangleIcon className="w-6 h-6" />}
                gradient="from-rose-500 to-pink-500"
                trend={{ value: 12, isPositive: false }}
                loading={isLoading}
              />
              <ModernStatsCard
                title="Today's Total"
                value={stats?.total_today || 0}
                icon={<ChartBarIcon className="w-6 h-6" />}
                gradient="from-amber-500 to-orange-500"
                trend={{ value: 8, isPositive: true }}
                loading={isLoading}
              />
              <ModernStatsCard
                title="High Severity"
                value={stats?.severity_distribution?.high || 0}
                icon={<ClockIcon className="w-6 h-6" />}
                gradient="from-purple-500 to-indigo-500"
                loading={isLoading}
              />
              <ModernStatsCard
                title="Live Trains"
                value={247}
                icon={<TrainIcon className="w-6 h-6" />}
                gradient="from-emerald-500 to-teal-500"
                trend={{ value: 5, isPositive: true }}
                loading={isLoading}
              />
            </motion.div>

            {/* Connection Status */}
            <motion.div 
              className="mb-8"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, delay: 1.4 }}
            >
              <GlassCard className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <StatusIndicator 
                      status={isConnected ? 'online' : 'offline'} 
                      label={isConnected ? 'Real-time Data Connected' : 'Connection Lost'}
                    />
                    <div className="text-sm text-gray-400">
                      Last update: {new Date().toLocaleTimeString()}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <SignalIcon className="w-5 h-5 text-gray-400" />
                    <span className="text-sm text-gray-300">WebSocket</span>
                  </div>
                </div>
              </GlassCard>
            </motion.div>

            {/* Main Content Grid */}
            <motion.div 
              className="grid grid-cols-1 lg:grid-cols-3 gap-8"
              initial={{ opacity: 0, y: 40 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 1.6 }}
            >
              {/* Map Section */}
              <div className="lg:col-span-2">
                <GlassCard className="p-6 h-[600px]">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-white flex items-center gap-2">
                      <MapPinIcon className="w-6 h-6" />
                      Live Subway Map
                    </h2>
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
                      <span className="text-sm text-gray-400">Live</span>
                    </div>
                  </div>
                  
                  <div className="relative h-full rounded-xl overflow-hidden">
                    {mounted ? (
                      <EnhancedSubwayMap
                        anomalies={anomalies}
                        onStationClick={setSelectedStation}
                        selectedStation={selectedStation}
                        selectedLine={selectedLine}
                      />
                    ) : (
                      <LoadingSkeleton className="w-full h-full" />
                    )}
                    
                    {/* Modern Line Filter */}
                    <div className="absolute top-4 left-4">
                      <GlassCard className="p-4">
                        <ModernLineSelector
                          selectedLine={selectedLine}
                          onChange={setSelectedLine}
                          anomalyCounts={stats?.by_line}
                        />
                      </GlassCard>
                    </div>
                  </div>
                </GlassCard>
              </div>

              {/* Timeline Section */}
              <div className="space-y-6">
                <GlassCard className="p-6 h-[600px]">
                  <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                    <ChartBarIcon className="w-6 h-6" />
                    Anomaly Timeline
                  </h2>
                  <AnomalyTimeline
                    anomalies={anomalies}
                    timeRange={timeRange}
                    onTimeRangeChange={setTimeRange}
                    isLoading={isLoading}
                  />
                </GlassCard>
              </div>
            </motion.div>
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

function ModernLineSelector({ selectedLine, onChange, anomalyCounts = {} }: LineSelectorProps) {
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
    <div className="space-y-3">
      <h3 className="text-sm font-bold text-white uppercase tracking-wider">
        Subway Lines
      </h3>
      <div className="space-y-2">
        <motion.button
          onClick={() => onChange(null)}
          className={`w-full px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            selectedLine === null
              ? 'bg-gradient-to-r from-blue-500 to-cyan-500 text-white shadow-lg'
              : 'bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10'
          }`}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          All Lines
        </motion.button>
        
        <div className="grid grid-cols-2 gap-2">
          {lines.map(line => (
            <motion.button
              key={line.id}
              onClick={() => onChange(line.id)}
              className={`px-3 py-2 rounded-xl text-sm font-medium transition-all flex items-center gap-2 ${
                selectedLine === line.id
                  ? 'bg-white/20 text-white ring-2 ring-blue-400 shadow-lg'
                  : 'bg-white/5 text-gray-300 hover:bg-white/10 border border-white/10'
              }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <motion.span 
                className={`w-3 h-3 rounded-full ${line.color}`}
                animate={selectedLine === line.id ? { scale: [1, 1.2, 1] } : {}}
                transition={{ duration: 0.3 }}
              />
              <span className="flex-1 text-left">{line.label}</span>
              {anomalyCounts[line.id] && (
                <motion.span 
                  className="text-xs bg-red-500/20 text-red-400 px-2 py-1 rounded-full"
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  {anomalyCounts[line.id]}
                </motion.span>
              )}
            </motion.button>
          ))}
        </div>
      </div>

      {/* Floating Action Buttons */}
      <FloatingActionButton
        icon={<ArrowUpIcon className="w-6 h-6" />}
        onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
        tooltip="Back to top"
        position="bottom-right"
      />

      <FloatingActionButton
        icon={<PlusIcon className="w-6 h-6" />}
        onClick={() => showSuccess('Quick Action', 'Feature coming soon!')}
        tooltip="Quick actions"
        position="bottom-left"
        className="mr-20"
      />

      {/* Toast Container */}
      <Toaster 
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: 'transparent',
            boxShadow: 'none',
          },
        }}
      />
    </div>
  )
}