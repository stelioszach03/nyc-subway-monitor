import { motion } from 'framer-motion';
import { ReactNode } from 'react';

interface FloatingActionButtonProps {
  icon: ReactNode;
  onClick: () => void;
  className?: string;
  tooltip?: string;
  position?: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left';
}

export function FloatingActionButton({
  icon,
  onClick,
  className = '',
  tooltip,
  position = 'bottom-right'
}: FloatingActionButtonProps) {
  const positionClasses = {
    'bottom-right': 'bottom-6 right-6',
    'bottom-left': 'bottom-6 left-6',
    'top-right': 'top-6 right-6',
    'top-left': 'top-6 left-6'
  };

  return (
    <motion.button
      className={`fixed ${positionClasses[position]} z-50 p-4 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full shadow-2xl hover:shadow-blue-500/25 transition-all group ${className}`}
      onClick={onClick}
      whileHover={{ 
        scale: 1.1,
        boxShadow: "0 20px 40px rgba(59, 130, 246, 0.4)"
      }}
      whileTap={{ scale: 0.9 }}
      initial={{ scale: 0, rotate: -180 }}
      animate={{ scale: 1, rotate: 0 }}
      transition={{ 
        type: "spring", 
        stiffness: 260, 
        damping: 20,
        delay: 1
      }}
    >
      <motion.div
        className="text-white text-xl"
        whileHover={{ rotate: 15 }}
        transition={{ type: "spring", stiffness: 400, damping: 10 }}
      >
        {icon}
      </motion.div>

      {/* Tooltip */}
      {tooltip && (
        <motion.div
          className="absolute bottom-full mb-2 left-1/2 transform -translate-x-1/2 px-3 py-2 bg-gray-900 text-white text-sm rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity"
          initial={{ opacity: 0, y: 10 }}
          whileHover={{ opacity: 1, y: 0 }}
        >
          {tooltip}
          <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900" />
        </motion.div>
      )}

      {/* Ripple effect */}
      <motion.div
        className="absolute inset-0 rounded-full bg-white/20"
        initial={{ scale: 0, opacity: 0.5 }}
        animate={{ scale: [0, 1.5], opacity: [0.5, 0] }}
        transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
      />
    </motion.button>
  );
}