import { format } from 'date-fns'
import { useEffect, useState } from 'react'

export function Header() {
  const [currentTime, setCurrentTime] = useState<string>('')

  useEffect(() => {
    // Set initial time
    setCurrentTime(format(new Date(), 'MMM d, yyyy HH:mm:ss'))
    
    // Update time every second
    const interval = setInterval(() => {
      setCurrentTime(format(new Date(), 'MMM d, yyyy HH:mm:ss'))
    }, 1000)

    return () => clearInterval(interval)
  }, [])

  return (
    <header className="bg-gray-900 border-b border-gray-800 px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
            NYC Subway Monitor
          </h1>
          <span className="text-sm text-gray-500">
            Real-time Anomaly Detection
          </span>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="text-sm text-gray-400">
            {currentTime}
          </div>
          <button className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors">
            Export Report
          </button>
        </div>
      </div>
    </header>
  )
}