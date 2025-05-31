import { motion } from 'framer-motion';
import { 
  ExclamationTriangleIcon, 
  ClockIcon, 
  MapPinIcon,
  SignalIcon 
} from '@heroicons/react/24/outline';
import { GlassCard } from './GlassCard';
import { getSeverityColor } from '@/lib/utils';
import type { Anomaly } from '@/types';

interface AnomalyCardProps {
  anomaly: Anomaly;
  onClick?: () => void;
  index?: number;
}

export function AnomalyCard({ anomaly, onClick, index = 0 }: AnomalyCardProps) {
  const severityColors = {
    low: 'from-blue-500 to-cyan-500',
    medium: 'from-yellow-500 to-orange-500',
    high: 'from-orange-500 to-red-500',
    critical: 'from-red-500 to-pink-500'
  };

  const severityIcons = {
    low: <SignalIcon className="w-5 h-5" />,
    medium: <ClockIcon className="w-5 h-5" />,
    high: <ExclamationTriangleIcon className="w-5 h-5" />,
    critical: <ExclamationTriangleIcon className="w-5 h-5" />
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, delay: index * 0.1 }}
    >
      <GlassCard 
        className="p-4 hover:scale-[1.02] transition-transform cursor-pointer"
        onClick={onClick}
      >
        <div className="flex items-start gap-3">
          {/* Severity indicator */}
          <div className={`p-2 rounded-xl bg-gradient-to-br ${severityColors[anomaly.severity]} shadow-lg`}>
            <div className="text-white">
              {severityIcons[anomaly.severity]}
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-white truncate">
                {anomaly.type.replace('_', ' ').toUpperCase()}
              </h3>
              <span className={`text-xs px-2 py-1 rounded-full bg-gradient-to-r ${severityColors[anomaly.severity]} text-white font-medium`}>
                {anomaly.severity}
              </span>
            </div>

            <p className="text-sm text-gray-300 mb-3 line-clamp-2">
              {anomaly.description}
            </p>

            <div className="flex items-center gap-4 text-xs text-gray-400">
              <div className="flex items-center gap-1">
                <MapPinIcon className="w-4 h-4" />
                <span>{anomaly.station_name}</span>
              </div>
              <div className="flex items-center gap-1">
                <ClockIcon className="w-4 h-4" />
                <span>{new Date(anomaly.timestamp).toLocaleTimeString()}</span>
              </div>
            </div>

            {/* Confidence score */}
            <div className="mt-3">
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="text-gray-400">Confidence</span>
                <span className="text-white font-medium">{Math.round(anomaly.confidence * 100)}%</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-1.5">
                <motion.div
                  className={`h-1.5 rounded-full bg-gradient-to-r ${severityColors[anomaly.severity]}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${anomaly.confidence * 100}%` }}
                  transition={{ duration: 1, delay: 0.5 }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Animated border for critical anomalies */}
        {anomaly.severity === 'critical' && (
          <motion.div
            className="absolute inset-0 rounded-2xl border-2 border-red-500/50"
            animate={{
              opacity: [0.5, 1, 0.5],
              scale: [1, 1.02, 1]
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeInOut"
            }}
          />
        )}
      </GlassCard>
    </motion.div>
  );
}