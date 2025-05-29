import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import { StationMarker } from './StationMarker'

// Set Mapbox token
mapboxgl.accessToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || ''

interface Anomaly {
  id?: number
  station_id?: string
  line?: string
  anomaly_type: string
  severity: number
  detected_at: string
  model_name: string
  model_version: string
  features?: Record<string, number>
  metadata?: Record<string, any>
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
  const markersRef = useRef<mapboxgl.Marker[]>([])

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current || map.current) return

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: [-73.98, 40.75], // NYC center
      zoom: 11,
      pitch: 30,
    })

    map.current.on('load', () => {
      setMapLoaded(true)
      
      // Add subway lines layer (if you have the data)
      // map.current?.addSource('subway-lines', {
      //   type: 'geojson',
      //   data: '/data/subway-lines.geojson',
      // })

      // map.current?.addLayer({
      //   id: 'subway-lines',
      //   type: 'line',
      //   source: 'subway-lines',
      //   paint: {
      //     'line-color': '#4a5568',
      //     'line-width': 2,
      //     'line-opacity': 0.6,
      //   },
      // })
    })

    // Cleanup
    return () => {
      map.current?.remove()
      map.current = null
    }
  }, [])

  // Add station markers for anomalies
  useEffect(() => {
    if (!map.current || !mapLoaded) return

    // Remove existing markers
    markersRef.current.forEach(marker => marker.remove())
    markersRef.current = []

    // Group anomalies by station
    const anomaliesByStation = anomalies.reduce<Record<string, Anomaly[]>>((acc, anomaly) => {
      if (!anomaly.station_id) return acc
      
      if (!acc[anomaly.station_id]) {
        acc[anomaly.station_id] = []
      }
      acc[anomaly.station_id].push(anomaly)
      return acc
    }, {})

    // Add markers
    Object.entries(anomaliesByStation).forEach(([stationId, stationAnomalies]) => {
      // Calculate severity (max of all anomalies at station)
      const maxSeverity = Math.max(...stationAnomalies.map(a => a.severity))
      
      // Create custom marker element
      const el = document.createElement('div')
      el.className = 'station-marker'
      el.innerHTML = StationMarker({ 
        severity: maxSeverity, 
        count: stationAnomalies.length,
        isSelected: stationId === selectedStation,
      })

      // For demo purposes, place markers at random positions around NYC
      // In production, you'd use actual station coordinates
      const lat = 40.65 + Math.random() * 0.2
      const lng = -74.05 + Math.random() * 0.2

      // Add marker to map
      const marker = new mapboxgl.Marker(el)
        .setLngLat([lng, lat])
        .addTo(map.current!)

      // Add popup
      const popup = new mapboxgl.Popup({ offset: 25 })
        .setHTML(`
          <div class="p-2">
            <h3 class="font-bold text-sm mb-1">Station ${stationId}</h3>
            <p class="text-xs text-gray-300">${stationAnomalies.length} anomalies</p>
            <p class="text-xs text-gray-300">Max severity: ${(maxSeverity * 100).toFixed(0)}%</p>
          </div>
        `)

      marker.setPopup(popup)

      // Click handler
      el.addEventListener('click', () => {
        onStationClick?.(stationId)
      })

      markersRef.current.push(marker)
    })
  }, [anomalies, mapLoaded, selectedStation, onStationClick])

  // Handle selected station
  useEffect(() => {
    if (!map.current || !selectedStation) return

    // Find the marker for the selected station and open its popup
    const stationAnomaly = anomalies.find(a => a.station_id === selectedStation)
    if (stationAnomaly) {
      // In production, you'd get actual coordinates
      const lat = 40.65 + Math.random() * 0.2
      const lng = -74.05 + Math.random() * 0.2
      
      map.current.flyTo({
        center: [lng, lat],
        zoom: 13,
        duration: 1000,
      })
    }
  }, [selectedStation, anomalies])

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