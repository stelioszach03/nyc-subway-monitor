import { motion } from 'framer-motion';
import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
  onClick?: () => void;
}

export function GlassCard({ 
  children, 
  className = "", 
  hover = true, 
  glow = false,
  onClick 
}: GlassCardProps) {
  return (
    <motion.div
      className={cn(
        "backdrop-blur-xl bg-white/5 border border-white/10 rounded-2xl shadow-2xl",
        "transition-all duration-300",
        hover && "hover:bg-white/10 hover:border-white/20 hover:shadow-3xl",
        glow && "shadow-blue-500/20",
        onClick && "cursor-pointer",
        className
      )}
      whileHover={hover ? { 
        scale: 1.02,
        boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)"
      } : undefined}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      onClick={onClick}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      {children}
    </motion.div>
  );
}