import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { 
  MapPinIcon, 
  ExclamationTriangleIcon,
  EyeIcon,
  Cog6ToothIcon
} from '@heroicons/react/24/outline'
import { GlassCard } from '../ui/GlassCard'
import { StatusIndicator } from '../ui/StatusIndicator'
import type { Anomaly } from '@/types'

// Set Mapbox token
if (process.env.NEXT_PUBLIC_MAPBOX_TOKEN) {
  mapboxgl.accessToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN
}

interface EnhancedSubwayMapProps {
  anomalies: Anomaly[]
  onStationClick?: (stationId: string | null) => void
  selectedStation?: string | null
  selectedLine?: string | null
}

export function EnhancedSubwayMap({ 
  anomalies, 
  onStationClick, 
  selectedStation,
  selectedLine 
}: EnhancedSubwayMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<mapboxgl.Map | null>(null)
  const [mapLoaded, setMapLoaded] = useState(false)
  const [is3D, setIs3D] = useState(true)
  const [showHeatmap, setShowHeatmap] = useState(false)
  const markersRef = useRef<{ [key: string]: mapboxgl.Marker }>({})

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current || map.current) return

    try {
      map.current = new mapboxgl.Map({
        container: mapContainer.current,
        style: 'mapbox://styles/mapbox/dark-v11',
        center: [-73.98, 40.75], // NYC center
        zoom: 11,
        pitch: is3D ? 45 : 0,
        bearing: is3D ? -17.6 : 0,
        antialias: true,
      })

      map.current.on('load', () => {
        setMapLoaded(true)
        
        // Add 3D buildings layer
        if (is3D) {
          map.current?.addLayer({
            id: '3d-buildings',
            source: 'composite',
            'source-layer': 'building',
            filter: ['==', 'extrude', 'true'],
            type: 'fill-extrusion',
            minzoom: 15,
            paint: {
              'fill-extrusion-color': '#aaa',
              'fill-extrusion-height': [
                'interpolate',
                ['linear'],
                ['zoom'],
                15,
                0,
                15.05,
                ['get', 'height']
              ],
              'fill-extrusion-base': [
                'interpolate',
                ['linear'],
                ['zoom'],
                15,
                0,
                15.05,
                ['get', 'min_height']
              ],
              'fill-extrusion-opacity': 0.6
            }
          })
        }
      })

      // Add navigation controls
      map.current.addControl(new mapboxgl.NavigationControl(), 'top-right')

      // Add geolocate control
      map.current.addControl(
        new mapboxgl.GeolocateControl({
          positionOptions: {
            enableHighAccuracy: true
          },
          trackUserLocation: true,
          showUserHeading: true
        }),
        'top-right'
      )

    } catch (error) {
      console.error('Failed to initialize map:', error)
    }

    return () => {
      map.current?.remove()
      map.current = null
    }
  }, [is3D])

  // Update anomaly markers
  useEffect(() => {
    if (!map.current || !mapLoaded) return

    // Clear existing markers
    Object.values(markersRef.current).forEach(marker => marker.remove())
    markersRef.current = {}

    // Add new markers for anomalies
    anomalies.forEach(anomaly => {
      if (!anomaly.latitude || !anomaly.longitude) return

      const severity = anomaly.severity || 'low'
      const color = {
        low: '#3B82F6',
        medium: '#F59E0B', 
        high: '#EF4444',
        critical: '#DC2626'
      }[severity] || '#6B7280'

      // Create custom marker element
      const el = document.createElement('div')
      el.className = 'anomaly-marker'
      el.style.cssText = `
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: ${color};
        border: 2px solid white;
        box-shadow: 0 0 20px ${color}50;
        cursor: pointer;
        animation: pulse 2s infinite;
      `

      // Add click handler
      el.addEventListener('click', () => {
        onStationClick?.(anomaly.station_id || null)
      })

      // Create marker
      const marker = new mapboxgl.Marker(el)
        .setLngLat([anomaly.longitude, anomaly.latitude])
        .addTo(map.current!)

      // Add popup
      const popup = new mapboxgl.Popup({ offset: 25 })
        .setHTML(`
          <div class="bg-gray-900 text-white p-3 rounded-lg">
            <h3 class="font-bold text-sm mb-1">${anomaly.type}</h3>
            <p class="text-xs text-gray-300 mb-1">Station: ${anomaly.station_name}</p>
            <p class="text-xs text-gray-300">Severity: ${severity}</p>
          </div>
        `)

      marker.setPopup(popup)
      markersRef.current[anomaly.id] = marker
    })
  }, [anomalies, mapLoaded, onStationClick])

  // Toggle 3D view
  const toggle3D = () => {
    if (!map.current) return
    
    setIs3D(!is3D)
    map.current.easeTo({
      pitch: !is3D ? 45 : 0,
      bearing: !is3D ? -17.6 : 0,
      duration: 1000
    })
  }

  // Toggle heatmap
  const toggleHeatmap = () => {
    setShowHeatmap(!showHeatmap)
    // Implementation for heatmap would go here
  }

  return (
    <div className="relative w-full h-full rounded-2xl overflow-hidden">
      {/* Map Container */}
      <div ref={mapContainer} className="w-full h-full" />

      {/* Map Controls */}
      <motion.div
        className="absolute top-4 left-4 z-10 space-y-2"
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.5 }}
      >
        <GlassCard className="p-3">
          <div className="flex items-center gap-2 mb-2">
            <MapPinIcon className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium text-white">Map Controls</span>
          </div>
          
          <div className="space-y-2">
            <motion.button
              className={`w-full px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                is3D 
                  ? 'bg-blue-500 text-white' 
                  : 'bg-white/10 text-gray-300 hover:bg-white/20'
              }`}
              onClick={toggle3D}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <EyeIcon className="w-3 h-3 inline mr-1" />
              3D View
            </motion.button>
            
            <motion.button
              className={`w-full px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                showHeatmap 
                  ? 'bg-orange-500 text-white' 
                  : 'bg-white/10 text-gray-300 hover:bg-white/20'
              }`}
              onClick={toggleHeatmap}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Cog6ToothIcon className="w-3 h-3 inline mr-1" />
              Heatmap
            </motion.button>
          </div>
        </GlassCard>
      </motion.div>

      {/* Legend */}
      <motion.div
        className="absolute bottom-4 left-4 z-10"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.7 }}
      >
        <GlassCard className="p-3">
          <div className="flex items-center gap-2 mb-2">
            <ExclamationTriangleIcon className="w-4 h-4 text-yellow-400" />
            <span className="text-sm font-medium text-white">Anomaly Severity</span>
          </div>
          
          <div className="space-y-1">
            {[
              { level: 'Low', color: '#3B82F6' },
              { level: 'Medium', color: '#F59E0B' },
              { level: 'High', color: '#EF4444' },
              { level: 'Critical', color: '#DC2626' }
            ].map(({ level, color }) => (
              <div key={level} className="flex items-center gap-2">
                <div 
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: color, boxShadow: `0 0 10px ${color}50` }}
                />
                <span className="text-xs text-gray-300">{level}</span>
              </div>
            ))}
          </div>
        </GlassCard>
      </motion.div>

      {/* Status Indicator */}
      <motion.div
        className="absolute top-4 right-4 z-10"
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.3 }}
      >
        <GlassCard className="p-3">
          <div className="flex items-center gap-2">
            <StatusIndicator 
              status={mapLoaded ? 'operational' : 'loading'} 
              size="sm" 
            />
            <span className="text-sm text-white">
              {mapLoaded ? 'Map Loaded' : 'Loading...'}
            </span>
          </div>
        </GlassCard>
      </motion.div>

      {/* Loading Overlay */}
      <AnimatePresence>
        {!mapLoaded && (
          <motion.div
            className="absolute inset-0 bg-gray-900/80 backdrop-blur-sm flex items-center justify-center z-20"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="text-center">
              <motion.div
                className="w-16 h-16 border-4 border-blue-500/30 border-t-blue-500 rounded-full mx-auto mb-4"
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              />
              <h3 className="text-lg font-medium text-white mb-2">
                Loading NYC Subway Map
              </h3>
              <p className="text-gray-400 text-sm">
                Initializing 3D visualization...
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Custom CSS for markers */}
      <style jsx>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.2); opacity: 0.8; }
        }
        
        .anomaly-marker:hover {
          transform: scale(1.3) !important;
          z-index: 1000;
        }
      `}</style>
    </div>
  )
}