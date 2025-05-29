import { useEffect, useState, ReactNode } from 'react'

interface HydrationFixProps {
  children: ReactNode
  fallback?: ReactNode
}

/**
 * Wrapper component to fix hydration mismatches
 * Prevents rendering on server and waits for client
 */
export function HydrationFix({ children, fallback = null }: HydrationFixProps) {
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setHydrated(true)
  }, [])

  return hydrated ? <>{children}</> : <>{fallback}</>
}

/**
 * Hook to detect if component has hydrated
 */
export function useHydrated() {
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    setHydrated(true)
  }, [])

  return hydrated
}