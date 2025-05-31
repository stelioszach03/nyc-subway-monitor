import { motion } from 'framer-motion';
import toast from 'react-hot-toast';
import { 
  CheckCircleIcon, 
  ExclamationTriangleIcon, 
  InformationCircleIcon,
  XCircleIcon 
} from '@heroicons/react/24/outline';

interface NotificationToastProps {
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  duration?: number;
}

const toastConfig = {
  success: {
    icon: CheckCircleIcon,
    gradient: 'from-emerald-500 to-teal-500',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/20'
  },
  error: {
    icon: XCircleIcon,
    gradient: 'from-red-500 to-rose-500',
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/20'
  },
  warning: {
    icon: ExclamationTriangleIcon,
    gradient: 'from-amber-500 to-orange-500',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/20'
  },
  info: {
    icon: InformationCircleIcon,
    gradient: 'from-blue-500 to-cyan-500',
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/20'
  }
};

export function showNotification({ type, title, message, duration = 4000 }: NotificationToastProps) {
  const config = toastConfig[type];
  const Icon = config.icon;

  toast.custom(
    (t) => (
      <motion.div
        className={`max-w-md w-full backdrop-blur-xl bg-gray-900/90 border ${config.borderColor} rounded-2xl shadow-2xl p-4`}
        initial={{ opacity: 0, y: 50, scale: 0.3 }}
        animate={{ 
          opacity: t.visible ? 1 : 0,
          y: t.visible ? 0 : 50,
          scale: t.visible ? 1 : 0.3
        }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
      >
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-xl bg-gradient-to-br ${config.gradient} shadow-lg`}>
            <Icon className="w-5 h-5 text-white" />
          </div>
          
          <div className="flex-1 min-w-0">
            <h3 className="text-white font-semibold text-sm mb-1">
              {title}
            </h3>
            <p className="text-gray-300 text-sm leading-relaxed">
              {message}
            </p>
          </div>
          
          <button
            onClick={() => toast.dismiss(t.id)}
            className="text-gray-400 hover:text-white transition-colors p-1"
          >
            <XCircleIcon className="w-4 h-4" />
          </button>
        </div>

        {/* Progress bar */}
        <motion.div
          className={`mt-3 h-1 bg-gradient-to-r ${config.gradient} rounded-full`}
          initial={{ width: "100%" }}
          animate={{ width: "0%" }}
          transition={{ duration: duration / 1000, ease: "linear" }}
        />
      </motion.div>
    ),
    { duration }
  );
}

// Convenience functions
export const showSuccess = (title: string, message: string) => 
  showNotification({ type: 'success', title, message });

export const showError = (title: string, message: string) => 
  showNotification({ type: 'error', title, message });

export const showWarning = (title: string, message: string) => 
  showNotification({ type: 'warning', title, message });

export const showInfo = (title: string, message: string) => 
  showNotification({ type: 'info', title, message });