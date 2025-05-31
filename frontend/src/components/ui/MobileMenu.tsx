import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Bars3Icon, 
  XMarkIcon,
  HomeIcon,
  ChartBarIcon,
  MapIcon,
  Cog6ToothIcon,
  BellIcon
} from '@heroicons/react/24/outline';
import { GlassCard } from './GlassCard';

interface MobileMenuProps {
  isOpen: boolean;
  onToggle: () => void;
}

const menuItems = [
  { icon: HomeIcon, label: 'Dashboard', href: '/' },
  { icon: MapIcon, label: 'Live Map', href: '/map' },
  { icon: ChartBarIcon, label: 'Analytics', href: '/analytics' },
  { icon: BellIcon, label: 'Alerts', href: '/alerts' },
  { icon: Cog6ToothIcon, label: 'Settings', href: '/settings' },
];

export function MobileMenu({ isOpen, onToggle }: MobileMenuProps) {
  return (
    <>
      {/* Menu Button */}
      <motion.button
        className="md:hidden fixed top-4 left-4 z-50 p-3 rounded-xl bg-white/10 backdrop-blur-xl border border-white/20"
        onClick={onToggle}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
      >
        <motion.div
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.3 }}
        >
          {isOpen ? (
            <XMarkIcon className="w-6 h-6 text-white" />
          ) : (
            <Bars3Icon className="w-6 h-6 text-white" />
          )}
        </motion.div>
      </motion.button>

      {/* Overlay */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onToggle}
          />
        )}
      </AnimatePresence>

      {/* Menu Panel */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            className="fixed top-0 left-0 h-full w-80 z-50 md:hidden"
            initial={{ x: -320 }}
            animate={{ x: 0 }}
            exit={{ x: -320 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
          >
            <GlassCard className="h-full rounded-none rounded-r-2xl p-6">
              <div className="flex flex-col h-full">
                {/* Header */}
                <div className="mb-8 pt-16">
                  <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                    NYC Subway
                  </h2>
                  <p className="text-gray-400 text-sm">
                    Real-time Monitor
                  </p>
                </div>

                {/* Menu Items */}
                <nav className="flex-1">
                  <ul className="space-y-2">
                    {menuItems.map((item, index) => (
                      <motion.li
                        key={item.label}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.1 }}
                      >
                        <motion.a
                          href={item.href}
                          className="flex items-center gap-3 p-3 rounded-xl hover:bg-white/10 transition-all group"
                          whileHover={{ x: 5 }}
                          whileTap={{ scale: 0.95 }}
                        >
                          <div className="p-2 rounded-lg bg-gradient-to-br from-blue-500 to-purple-500 group-hover:from-purple-500 group-hover:to-pink-500 transition-all">
                            <item.icon className="w-5 h-5 text-white" />
                          </div>
                          <span className="text-white font-medium">
                            {item.label}
                          </span>
                        </motion.a>
                      </motion.li>
                    ))}
                  </ul>
                </nav>

                {/* Footer */}
                <div className="pt-6 border-t border-white/10">
                  <div className="text-xs text-gray-400 text-center">
                    Version 2.0.0
                  </div>
                </div>
              </div>
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

export function useMobileMenu() {
  const [isOpen, setIsOpen] = useState(false);

  const toggle = () => setIsOpen(!isOpen);
  const close = () => setIsOpen(false);
  const open = () => setIsOpen(true);

  return { isOpen, toggle, close, open };
}