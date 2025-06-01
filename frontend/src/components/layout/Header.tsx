import { format } from 'date-fns'
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { 
  DocumentArrowDownIcon, 
  Cog6ToothIcon,
  BellIcon,
  MapIcon
} from '@heroicons/react/24/outline'
import { GlassCard } from '../ui/GlassCard'
import { ThemeToggle } from '../ui/ThemeToggle'

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
    <motion.header 
      className="backdrop-blur-xl bg-gray-900/50 border-b border-white/10 px-6 py-4 sticky top-0 z-50"
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="flex items-center justify-between">
        <motion.div 
          className="flex items-center gap-4"
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <div className="flex items-center gap-3">
            <motion.div
              className="p-2 rounded-xl bg-gradient-to-br from-blue-500 to-purple-500 shadow-lg"
              whileHover={{ scale: 1.1, rotate: 5 }}
              transition={{ type: "spring", stiffness: 400, damping: 10 }}
            >
              <MapIcon className="w-6 h-6 text-white" />
            </motion.div>
            <div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
                NYC Subway Monitor
              </h1>
              <span className="text-sm text-gray-400 font-medium">
                Real-time Anomaly Detection System
              </span>
            </div>
          </div>
        </motion.div>
        
        <motion.div 
          className="flex items-center gap-4"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <GlassCard className="px-4 py-2">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
              <div className="text-sm text-gray-300 font-mono">
                {currentTime}
              </div>
            </div>
          </GlassCard>
          
          <div className="flex items-center gap-2">
            <motion.button 
              className="p-3 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-all relative"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <BellIcon className="w-5 h-5 text-gray-300" />
              <motion.div
                className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full"
                animate={{ scale: [1, 1.2, 1] }}
                transition={{ duration: 2, repeat: Infinity }}
              />
            </motion.button>
            
            <ThemeToggle />
            
            <motion.button 
              className="p-3 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition-all"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Cog6ToothIcon className="w-5 h-5 text-gray-300" />
            </motion.button>
            
            <motion.button 
              className="px-4 py-2 bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600 rounded-xl text-sm font-medium transition-all shadow-lg flex items-center gap-2"
              whileHover={{ scale: 1.05, boxShadow: "0 10px 25px rgba(59, 130, 246, 0.3)" }}
              whileTap={{ scale: 0.95 }}
            >
              <DocumentArrowDownIcon className="w-4 h-4" />
              Export Report
            </motion.button>
          </div>
        </motion.div>
      </div>
    </motion.header>
  )
}