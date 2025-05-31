import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface StatusIndicatorProps {
  status: 'online' | 'offline' | 'connecting' | 'error';
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

export function StatusIndicator({
  status,
  label,
  size = 'md',
  showLabel = true,
  className = ''
}: StatusIndicatorProps) {
  const statusConfig = {
    online: {
      color: 'bg-emerald-500',
      label: label || 'Connected',
      pulse: true
    },
    offline: {
      color: 'bg-gray-500',
      label: label || 'Disconnected',
      pulse: false
    },
    connecting: {
      color: 'bg-amber-500',
      label: label || 'Connecting...',
      pulse: true
    },
    error: {
      color: 'bg-rose-500',
      label: label || 'Error',
      pulse: true
    }
  };

  const sizeConfig = {
    sm: 'w-2 h-2',
    md: 'w-3 h-3',
    lg: 'w-4 h-4'
  };

  const config = statusConfig[status];

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="relative">
        <motion.div
          className={cn(
            "rounded-full",
            sizeConfig[size],
            config.color
          )}
          animate={config.pulse ? {
            scale: [1, 1.2, 1],
            opacity: [1, 0.8, 1]
          } : {}}
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: "easeInOut"
          }}
        />
        {config.pulse && (
          <motion.div
            className={cn(
              "absolute inset-0 rounded-full",
              config.color,
              "opacity-30"
            )}
            animate={{
              scale: [1, 2, 1],
              opacity: [0.3, 0, 0.3]
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeInOut"
            }}
          />
        )}
      </div>
      {showLabel && (
        <span className="text-sm text-gray-300">
          {config.label}
        </span>
      )}
    </div>
  );
}