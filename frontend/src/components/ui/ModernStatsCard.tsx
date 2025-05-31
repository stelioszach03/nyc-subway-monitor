import { motion } from 'framer-motion';
import { ReactNode } from 'react';
import { GlassCard } from './GlassCard';
import { AnimatedCounter } from './AnimatedCounter';
import { cn } from '@/lib/utils';

interface ModernStatsCardProps {
  title: string;
  value: number;
  icon: ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  suffix?: string;
  prefix?: string;
  className?: string;
  gradient?: string;
  loading?: boolean;
}

export function ModernStatsCard({
  title,
  value,
  icon,
  trend,
  suffix = '',
  prefix = '',
  className = '',
  gradient = 'from-blue-500 to-cyan-500',
  loading = false
}: ModernStatsCardProps) {
  return (
    <GlassCard className={cn("p-6 relative overflow-hidden", className)}>
      {/* Gradient background */}
      <div className={cn(
        "absolute inset-0 bg-gradient-to-br opacity-10",
        gradient
      )} />
      
      {/* Content */}
      <div className="relative z-10">
        <div className="flex items-center justify-between mb-4">
          <div className={cn(
            "p-3 rounded-xl bg-gradient-to-br",
            gradient,
            "shadow-lg"
          )}>
            <div className="text-white text-xl">
              {icon}
            </div>
          </div>
          
          {trend && (
            <motion.div
              className={cn(
                "flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium",
                trend.isPositive 
                  ? "bg-emerald-500/20 text-emerald-400" 
                  : "bg-rose-500/20 text-rose-400"
              )}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.5 }}
            >
              <span>{trend.isPositive ? '↗' : '↘'}</span>
              <span>{Math.abs(trend.value)}%</span>
            </motion.div>
          )}
        </div>
        
        <div className="space-y-2">
          <h3 className="text-gray-400 text-sm font-medium uppercase tracking-wider">
            {title}
          </h3>
          
          <div className="text-3xl font-bold text-white">
            {loading ? (
              <div className="h-8 w-24 bg-gray-700 rounded animate-pulse" />
            ) : (
              <AnimatedCounter
                value={value}
                prefix={prefix}
                suffix={suffix}
                duration={2}
              />
            )}
          </div>
        </div>
      </div>
      
      {/* Animated border */}
      <motion.div
        className="absolute inset-0 rounded-2xl border-2 border-transparent"
        style={{
          background: `linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent) border-box`,
          WebkitMask: 'linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0)',
          WebkitMaskComposite: 'exclude'
        }}
        animate={{
          background: [
            'linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent)',
            'linear-gradient(225deg, transparent, rgba(255,255,255,0.1), transparent)',
            'linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent)'
          ]
        }}
        transition={{
          duration: 3,
          repeat: Infinity,
          ease: "linear"
        }}
      />
    </GlassCard>
  );
}