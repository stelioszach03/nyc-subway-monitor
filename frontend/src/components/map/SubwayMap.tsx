import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'
import { StationMarker } from './StationMarker'

// Set Mapbox token
mapboxgl.accessToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || ''

interface SubwayMapProps {
  anomalies: any[]
  onStationClick?: (stationId: string | null) => void
  selectedStation?: string | null
}

export function SubwayMap({ anomalies, onStationClick, selectedStation }: SubwayMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<mapboxgl.Map | null>(null)
  const [mapLoaded, setMapLoaded] = useState(false)

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
      
      // Add subway lines layer
      map.current?.addSource('subway-lines', {
        type: 'geojson',
        data: '/data/subway-lines.geojson', // Would need this data file
      })

      map.current?.addLayer({
        id: 'subway-lines',
        type: 'line',
        source: 'subway-lines',
        paint: {
          'line-color': '#4a5568',
          'line-width': 2,
          'line-opacity': 0.6,
        },
      })
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

    // Group anomalies by station
    const anomaliesByStation = anomalies.reduce((acc, anomaly) => {
      if (!anomaly.station_id) return acc
      
      if (!acc[anomaly.station_id]) {
        acc[anomaly.station_id] = []
      }
      acc[anomaly.station_id].push(anomaly)
      return acc
    }, {} as Record<string, any[]>)

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

      // Add marker to map
      const marker = new mapboxgl.Marker(el)
        .setLngLat([-73.98, 40.75]) // Would need actual station coordinates
        .addTo(map.current!)

      // Click handler
      el.addEventListener('click', () => {
        onStationClick?.(stationId)
      })
    })
  }, [anomalies, mapLoaded, selectedStation, onStationClick])

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