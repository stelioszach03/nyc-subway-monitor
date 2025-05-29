import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import type { Anomaly } from '@/types'

// Set Mapbox token
if (process.env.NEXT_PUBLIC_MAPBOX_TOKEN) {
  mapboxgl.accessToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN
}

interface SubwayMapProps {
  anomalies: Anomaly[]
  onStationClick?: (stationId: string | null) => void
  selectedStation?: string | null
}

export function SubwayMap({ anomalies, onStationClick, selectedStation }: SubwayMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<mapboxgl.Map | null>(null)
  const [mapLoaded, setMapLoaded] = useState(false)
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
        pitch: 30,
      })

      map.current.on('load', () => {
        setMapLoaded(true)
      })

      // Add navigation controls
      map.current.addControl(new mapboxgl.NavigationControl(), 'top-right')

      // Cleanup
      return () => {
        map.current?.remove()
        map.current = null
      }
    } catch (error) {
      console.error('Failed to initialize map:', error)
    }
  }, [])

  // Update markers
  useEffect(() => {
    if (!map.current || !mapLoaded) return

    // Remove old markers
    Object.values(markersRef.current).forEach(marker => marker.remove())
    markersRef.current = {}

    // Group anomalies by station
    const anomaliesByStation = anomalies.reduce<Record<string, Anomaly[]>>((acc, anomaly) => {
      if (!anomaly.station_id) return acc
      
      if (!acc[anomaly.station_id]) {
        acc[anomaly.station_id] = []
      }
      acc[anomaly.station_id].push(anomaly)
      return acc
    }, {})

    // Add markers for each station
    Object.entries(anomaliesByStation).forEach(([stationId, stationAnomalies]) => {
      // Calculate severity
      const maxSeverity = Math.max(...stationAnomalies.map(a => a.severity))
      
      // Create marker element
      const el = document.createElement('div')
      el.className = 'station-marker'
      
      // Determine color based on severity
      const color = maxSeverity > 0.7 ? '#ef4444' : maxSeverity > 0.4 ? '#f59e0b' : '#eab308'
      const size = 20 + (maxSeverity * 20)
      
      el.innerHTML = `
        <div class="relative cursor-pointer">
          <div 
            class="absolute rounded-full animate-ping"
            style="
              width: ${size * 2}px;
              height: ${size * 2}px;
              background-color: ${color};
              opacity: 0.3;
              top: -${size}px;
              left: -${size}px;
            "
          ></div>
          <div 
            class="relative rounded-full border-2 ${stationId === selectedStation ? 'border-white' : 'border-gray-800'} shadow-lg"
            style="
              width: ${size}px;
              height: ${size}px;
              background-color: ${color};
              box-shadow: 0 0 10px ${color};
            "
          >
            <span class="absolute inset-0 flex items-center justify-center text-xs font-bold text-white">
              ${stationAnomalies.length}
            </span>
          </div>
        </div>
      `

      // For demo, use random coordinates around NYC
      // In production, you'd use actual station coordinates
      const lat = 40.65 + Math.random() * 0.2
      const lng = -74.05 + Math.random() * 0.2

      // Create marker
      const marker = new mapboxgl.Marker(el)
        .setLngLat([lng, lat])
        .addTo(map.current!)

      // Add popup
      const popupContent = `
        <div class="p-2">
          <h3 class="font-bold text-sm mb-1">Station ${stationId}</h3>
          <p class="text-xs text-gray-300">${stationAnomalies.length} anomalies</p>
          <p class="text-xs text-gray-300">Max severity: ${(maxSeverity * 100).toFixed(0)}%</p>
          <div class="mt-2">
            ${stationAnomalies.map(a => `
              <div class="text-xs">
                <span class="text-gray-400">${a.anomaly_type}:</span> 
                <span class="${a.severity > 0.7 ? 'text-red-400' : a.severity > 0.4 ? 'text-yellow-400' : 'text-green-400'}">
                  ${(a.severity * 100).toFixed(0)}%
                </span>
              </div>
            `).join('')}
          </div>
        </div>
      `

      const popup = new mapboxgl.Popup({ offset: 25 })
        .setHTML(popupContent)

      marker.setPopup(popup)

      // Click handler
      el.addEventListener('click', () => {
        onStationClick?.(stationId)
      })

      markersRef.current[stationId] = marker
    })
  }, [anomalies, mapLoaded, selectedStation, onStationClick])

  // Handle selected station
  useEffect(() => {
    if (!map.current || !selectedStation || !markersRef.current[selectedStation]) return

    const marker = markersRef.current[selectedStation]
    const lngLat = marker.getLngLat()
    
    map.current.flyTo({
      center: [lngLat.lng, lngLat.lat],
      zoom: 13,
      duration: 1000,
    })

    // Open popup
    marker.togglePopup()
  }, [selectedStation])

  return (
    <div ref={mapContainer} className="w-full h-full">
      {!mapLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900">
          <div className="text-gray-500">Loading map...</div>
        </div>
      )}
    </div>
  )
}
