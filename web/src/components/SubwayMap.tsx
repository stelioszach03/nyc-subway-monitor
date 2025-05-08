import { useRef, useEffect, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { useSubwayData } from '../contexts/SubwayDataContext';
import { Train } from '../types/subway';
import { Feature, Geometry, GeoJsonProperties } from 'geojson';

// Set Mapbox token
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || '';

// NYC subway line colors
const ROUTE_COLORS: Record<string, string> = {
  '1': '#ff3c1f',
  '2': '#ff3c1f',
  '3': '#ff3c1f',
  '4': '#00933c',
  '5': '#00933c',
  '6': '#00933c',
  '7': '#b933ad',
  'A': '#0039a6',
  'C': '#0039a6',
  'E': '#0039a6',
  'B': '#ff6319',
  'D': '#ff6319',
  'F': '#ff6319',
  'M': '#ff6319',
  'G': '#6cbe45',
  'J': '#996633',
  'Z': '#996633',
  'L': '#a7a9ac',
  'N': '#fccc0a',
  'Q': '#fccc0a',
  'R': '#fccc0a',
  'W': '#fccc0a',
  'S': '#808183',
  'SI': '#0039a6'
};

const SubwayMap = () => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const { trains, delays } = useSubwayData();

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current) return;

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/light-v11',
      center: [-73.977, 40.705], // NYC coordinates
      zoom: 12
    });

    map.current.on('load', () => {
      // Add subway line layers (can be loaded from GeoJSON)
      // For simplicity, we'll focus on train positions in this example
      
      // Add a source for train positions
      map.current?.addSource('trains', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: []
        }
      });

      // Add train symbols layer
      map.current?.addLayer({
        id: 'trains-layer',
        type: 'circle',
        source: 'trains',
        paint: {
          'circle-radius': 6,
          'circle-color': ['get', 'color'],
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff'
        }
      });

      // Add train labels
      map.current?.addLayer({
        id: 'train-labels',
        type: 'symbol',
        source: 'trains',
        layout: {
          'text-field': ['get', 'route_id'],
          'text-size': 12,
          'text-offset': [0, -1.5],
          'text-anchor': 'center'
        },
        paint: {
          'text-color': '#000000',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1
        }
      });

      setMapLoaded(true);
    });

    return () => {
      map.current?.remove();
    };
  }, []);

  // Update train positions
  useEffect(() => {
    if (!mapLoaded || !map.current || !trains.length) return;

    // Convert trains to GeoJSON
    const features: Feature<Geometry, GeoJsonProperties>[] = trains.map((train: Train) => ({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [train.longitude, train.latitude]
      },
      properties: {
        id: train.trip_id,
        route_id: train.route_id,
        delay: train.delay || 0,
        color: ROUTE_COLORS[train.route_id] || '#888888',
        status: train.current_status
      }
    }));

    // Update the GeoJSON source
    const source = map.current.getSource('trains') as mapboxgl.GeoJSONSource;
    source.setData({
      type: 'FeatureCollection',
      features
    });
  }, [trains, mapLoaded]);

  // Update delay overlays
  useEffect(() => {
    if (!mapLoaded || !map.current || !delays.length) return;

    // This would involve fetching subway line geometries and updating them
    // with delay information. For simplicity, we're skipping this part.
    // In a real app, you would:
    // 1. Load subway line GeoJSON data
    // 2. Join with delay data
    // 3. Update line colors based on delays
  }, [delays, mapLoaded]);

  return (
    <div className="h-full w-full rounded-lg border border-gray-200">
      <div ref={mapContainer} className="h-full w-full" />
    </div>
  );
};

export default SubwayMap;
