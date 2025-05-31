import { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { Header } from './Header'
import { ParticleBackground } from '../ui/ParticleBackground'
import { MobileMenu, useMobileMenu } from '../ui/MobileMenu'

interface LayoutProps {
  children: ReactNode
}

export function Layout({ children }: LayoutProps) {
  const mobileMenu = useMobileMenu()

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 relative overflow-hidden">
      <ParticleBackground />
      <div className="relative z-10">
        <Header />
        <motion.main
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5 }}
        >
          {children}
        </motion.main>
      </div>
      
      {/* Mobile Menu */}
      <MobileMenu 
        isOpen={mobileMenu.isOpen} 
        onToggle={mobileMenu.toggle} 
      />
    </div>
  )
}