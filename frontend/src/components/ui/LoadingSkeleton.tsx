import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface LoadingSkeletonProps {
  className?: string;
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
  lines?: number;
}

export function LoadingSkeleton({
  className = '',
  variant = 'rectangular',
  width,
  height,
  lines = 1
}: LoadingSkeletonProps) {
  const baseClasses = "bg-gradient-to-r from-gray-800 via-gray-700 to-gray-800 bg-[length:200%_100%]";
  
  const variants = {
    text: "h-4 rounded",
    circular: "rounded-full",
    rectangular: "rounded-lg"
  };

  const shimmerAnimation = {
    backgroundPosition: ['200% 0', '-200% 0'],
  };

  if (variant === 'text' && lines > 1) {
    return (
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, index) => (
          <motion.div
            key={index}
            className={cn(baseClasses, variants.text, className)}
            style={{ 
              width: index === lines - 1 ? '75%' : '100%',
              height: height || '1rem'
            }}
            animate={shimmerAnimation}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "linear",
              delay: index * 0.1
            }}
          />
        ))}
      </div>
    );
  }

  return (
    <motion.div
      className={cn(baseClasses, variants[variant], className)}
      style={{ width, height }}
      animate={shimmerAnimation}
      transition={{
        duration: 2,
        repeat: Infinity,
        ease: "linear"
      }}
    />
  );
}