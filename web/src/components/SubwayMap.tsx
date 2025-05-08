import { useRef, useEffect, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { useSubwayData } from '../contexts/SubwayDataContext';
import { Train } from '../types/subway';
import { Feature, Geometry, GeoJsonProperties } from 'geojson';
import { ROUTE_COLORS } from '../types/subway';

// Set Mapbox token
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || 'pk.eyJ1Ijoic3RlbGlvc3phY2gwMDMiLCJhIjoiY205bmNqanJuMGpyZzJqc2VibG91aHh6MSJ9._RaxW8Cprc33mxaUfsMEnw';
mapboxgl.accessToken = MAPBOX_TOKEN;

// NYC Subway Stations GeoJSON URL
const SUBWAY_STATIONS_URL = 'https://raw.githubusercontent.com/kevin-brown/nyc-open-geojson/master/transportation/subway-stations.geojson';

// MTA official line colors
const MTA_LINE_COLORS: Record<string, string> = {
  '1': '#EE352E', '2': '#EE352E', '3': '#EE352E',
  '4': '#00933C', '5': '#00933C', '6': '#00933C',
  '7': '#B933AD',
  'A': '#2850AD', 'C': '#2850AD', 'E': '#2850AD',
  'B': '#FF6319', 'D': '#FF6319', 'F': '#FF6319', 'M': '#FF6319',
  'G': '#6CBE45',
  'J': '#996633', 'Z': '#996633',
  'L': '#A7A9AC',
  'N': '#FCCC0A', 'Q': '#FCCC0A', 'R': '#FCCC0A', 'W': '#FCCC0A',
  'S': '#808183', 'SIR': '#00A1DE'
};

interface SubwayMapProps {
  selectedRoute: string | null;
}

// Helper function to extract station names and routes from description
const processStationDescription = (description: string) => {
  const name = description.match(/\*\s*NAME:\s*([^\n]+)/i)?.[1]?.trim();
  const routesStr = description.match(/\*\s*LINE:\s*([^\n]+)/i)?.[1] ?? '';
  const routes = routesStr
    .replace(/ Express/gi, '')
    .split(/[-\s]+/)
    .filter(Boolean);

  return {
    station_name: name ?? 'Unknown',
    routes,
    primary_route: routes[0] ?? ''
  };
};

const SubwayMap = ({ selectedRoute }: SubwayMapProps) => {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapStyle, setMapStyle] = useState<string>('light-v11');
  const [showControls, setShowControls] = useState(false);
  const [showStations, setShowStations] = useState(true);
  const { trains, delays } = useSubwayData();
  const [selectedTrain, setSelectedTrain] = useState<Train | null>(null);
  const popup = useRef<mapboxgl.Popup | null>(null);

  // Filter trains based on the selected route
  const filteredTrains = selectedRoute
    ? trains.filter(train => train.route_id === selectedRoute)
    : trains;

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current) return;

    try {
      // Create map instance
      map.current = new mapboxgl.Map({
        container: mapContainer.current,
        style: `mapbox://styles/mapbox/${mapStyle}`,
        center: [-73.985, 40.745], // NYC midtown coordinates
        zoom: 12,
        attributionControl: false
      });

      // Add navigation controls
      map.current.addControl(new mapboxgl.NavigationControl(), 'top-right');
      
      // Add attribution control
      map.current.addControl(new mapboxgl.AttributionControl({
        compact: true
      }));

      // Add geolocation control
      map.current.addControl(
        new mapboxgl.GeolocateControl({
          positionOptions: {
            enableHighAccuracy: true
          },
          trackUserLocation: true,
          showUserHeading: true
        }),
        'top-right'
      );

      // Initialize popup but don't add it to the map yet
      popup.current = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
        maxWidth: '300px',
        className: 'subway-popup'
      });

      map.current.on('load', async () => {
        console.log('Map loaded successfully');
        
        // Add a source for train positions
        map.current?.addSource('trains', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: []
          }
        });

        // Fetch and process subway stations
        try {
          const response = await fetch(SUBWAY_STATIONS_URL);
          const data = await response.json();
          
          // Process each feature to extract station name and routes
          data.features.forEach((feature: any) => {
            const description = feature.properties.description || '';
            const { station_name, routes, primary_route } = processStationDescription(description);
            
            // Add parsed data back to the feature
            feature.properties.station_name = station_name;
            feature.properties.routes = routes;
            feature.properties.primary_route = primary_route;
            
            // Set the color based on primary route
            feature.properties.color = 
              MTA_LINE_COLORS[primary_route] || 
              (primary_route ? ROUTE_COLORS[primary_route] : '#808183'); // Fallback to our colors or gray
          });

          // Add subway stations source
          map.current?.addSource('subway-stations', {
            type: 'geojson',
            data: data
          });

          // Add subway stations layer
          map.current?.addLayer({
            id: 'subway-stations-layer',
            type: 'circle',
            source: 'subway-stations',
            paint: {
              'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                10, 2,
                14, 4,
                16, 6
              ],
              'circle-color': ['get', 'color'],
              'circle-opacity': 0.8,
              'circle-stroke-width': 1.5,
              'circle-stroke-color': '#ffffff',
              'circle-stroke-opacity': 0.9,
            },
            layout: {
              'visibility': showStations ? 'visible' : 'none'
            }
          });

          // Add subway station labels
          map.current?.addLayer({
            id: 'subway-stations-labels',
            type: 'symbol',
            source: 'subway-stations',
            minzoom: 13, // Only show labels when zoomed in
            layout: {
              'text-field': ['get', 'station_name'],
              'text-size': 10,
              'text-offset': [0, 1],
              'text-anchor': 'top',
              'text-allow-overlap': false,
              'text-ignore-placement': false,
              'visibility': showStations ? 'visible' : 'none'
            },
            paint: {
              'text-color': '#000000',
              'text-halo-color': '#ffffff',
              'text-halo-width': 1.5
            }
          });

          console.log('Subway stations loaded');
        } catch (error) {
          console.error('Error loading subway stations:', error);
        }

        // Add train symbols layer
        map.current?.addLayer({
          id: 'trains-layer',
          type: 'circle',
          source: 'trains',
          paint: {
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              10, 3,
              14, 6,
              16, 8
            ],
            'circle-color': ['get', 'color'],
            'circle-stroke-width': 2,
            'circle-stroke-color': '#ffffff',
            'circle-stroke-opacity': 0.8,
          }
        });

        // Add train labels
        map.current?.addLayer({
          id: 'train-labels',
          type: 'symbol',
          source: 'trains',
          layout: {
            'text-field': ['get', 'route_id'],
            'text-size': 10,
            'text-offset': [0, 0],
            'text-anchor': 'center',
            'text-allow-overlap': false,
            'text-ignore-placement': false,
          },
          paint: {
            'text-color': [
              'case',
              ['in', ['get', 'route_id'], ['literal', ['N', 'Q', 'R', 'W']]],
              '#000000',
              '#ffffff'
            ],
            'text-halo-color': [
              'case',
              ['in', ['get', 'route_id'], ['literal', ['N', 'Q', 'R', 'W']]],
              '#ffffff',
              '#000000'
            ],
            'text-halo-width': 0.5
          }
        });

        // Add click event for trains
        map.current?.on('click', 'trains-layer', (e) => {
          if (e.features && e.features.length > 0) {
            const feature = e.features[0];
            const props = feature.properties;
            
            if (props) {
              const train = trains.find(t => 
                t.trip_id === props.id && 
                t.route_id === props.route_id
              );
              
              if (train) {
                setSelectedTrain(train);
              }
            }
          }
        });

        // Add click event for subway stations
        map.current?.on('click', 'subway-stations-layer', (e) => {
          if (e.features && e.features.length > 0) {
            const feature = e.features[0];
            const props = feature.properties;
            const coordinates = (feature.geometry as any).coordinates.slice();
            
            if (props && coordinates) {
              const routesList = props.routes ? props.routes.join(', ') : 'None';
              
              // Create popup for station
              new mapboxgl.Popup()
                .setLngLat(coordinates)
                .setHTML(`
                  <div class="p-2">
                    <h3 class="font-bold text-base">${props.station_name}</h3>
                    <p class="text-sm text-gray-600 mt-1">Lines: ${routesList}</p>
                  </div>
                `)
                .addTo(map.current!);
            }
          }
        });

        // Change cursor on hover for both trains and stations
        map.current?.on('mouseenter', 'trains-layer', () => {
          if (map.current) {
            map.current.getCanvas().style.cursor = 'pointer';
          }
        });

        map.current?.on('mouseenter', 'subway-stations-layer', () => {
          if (map.current) {
            map.current.getCanvas().style.cursor = 'pointer';
          }
        });

        map.current?.on('mouseleave', 'trains-layer', () => {
          if (map.current) {
            map.current.getCanvas().style.cursor = '';
          }
        });

        map.current?.on('mouseleave', 'subway-stations-layer', () => {
          if (map.current) {
            map.current.getCanvas().style.cursor = '';
          }
        });

        setMapLoaded(true);
      });

      map.current.on('error', (e) => {
        console.error('Mapbox error:', e);
      });
    } catch (err) {
      console.error('Error initializing map:', err);
    }

    return () => {
      if (popup.current) popup.current.remove();
      map.current?.remove();
    };
  }, [mapStyle]);

  // Update train positions
  useEffect(() => {
    if (!mapLoaded || !map.current || !filteredTrains.length) return;

    try {
      // Convert trains to GeoJSON
      const features: Feature<Geometry, GeoJsonProperties>[] = filteredTrains.map((train: Train) => ({
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [train.longitude, train.latitude]
        },
        properties: {
          id: train.trip_id,
          route_id: train.route_id,
          delay: train.delay || 0,
          color: MTA_LINE_COLORS[train.route_id] || ROUTE_COLORS[train.route_id] || '#888888',
          status: train.current_status,
          direction: train.direction_id === 0 ? 'Northbound' : 'Southbound',
          vehicle_id: train.vehicle_id
        }
      }));

      // Update the GeoJSON source
      const source = map.current.getSource('trains') as mapboxgl.GeoJSONSource;
      source.setData({
        type: 'FeatureCollection',
        features
      });
      
      // If a train was selected, ensure popup is still shown even after data update
      if (selectedTrain) {
        const train = filteredTrains.find(t => 
          t.trip_id === selectedTrain.trip_id && 
          t.route_id === selectedTrain.route_id
        );
        
        if (train) {
          setSelectedTrain(train);
        } else {
          setSelectedTrain(null);
          if (popup.current) popup.current.remove();
        }
      }
    } catch (err) {
      console.error('Error updating train positions:', err);
    }
  }, [filteredTrains, mapLoaded, selectedTrain, trains]);

  // Handle train selection for popup
  useEffect(() => {
    if (!mapLoaded || !map.current || !popup.current) return;
    
    if (selectedTrain) {
      try {
        // Format delay text
        let delayText = 'On time';
        let delayClass = 'text-green-600';
        
        if (selectedTrain.delay) {
          if (selectedTrain.delay > 300) {
            delayText = `${Math.floor(selectedTrain.delay / 60)} min ${selectedTrain.delay % 60} sec delay`;
            delayClass = 'text-red-600 font-bold';
          } else if (selectedTrain.delay > 60) {
            delayText = `${Math.floor(selectedTrain.delay / 60)} min ${selectedTrain.delay % 60} sec delay`;
            delayClass = 'text-yellow-600 font-semibold';
          } else if (selectedTrain.delay > 0) {
            delayText = `${selectedTrain.delay} sec delay`;
            delayClass = 'text-yellow-600';
          }
        }

        // Format status text
        let statusText = selectedTrain.current_status || 'Unknown';
        if (statusText === 'STOPPED_AT') statusText = 'Stopped at station';
        if (statusText === 'IN_TRANSIT_TO') statusText = 'In transit';
        if (statusText === 'INCOMING_AT') statusText = 'Arriving at station';
        
        // Create popup HTML
        const popupContent = `
          <div class="p-1">
            <div class="flex items-center mb-2">
              <div class="flex h-6 w-6 items-center justify-center rounded-full text-white text-xs font-bold mr-2" 
                   style="background-color: ${MTA_LINE_COLORS[selectedTrain.route_id] || ROUTE_COLORS[selectedTrain.route_id] || '#888888'}">
                ${selectedTrain.route_id}
              </div>
              <div class="font-medium">${selectedTrain.route_id} Train</div>
            </div>
            <div class="grid grid-cols-2 gap-y-1 text-xs">
              <div class="text-gray-600">Status:</div>
              <div class="font-medium">${statusText}</div>
              <div class="text-gray-600">Direction:</div>
              <div class="font-medium">${selectedTrain.direction_id === 0 ? 'Northbound' : 'Southbound'}</div>
              <div class="text-gray-600">Delay:</div>
              <div class="${delayClass}">${delayText}</div>
              <div class="text-gray-600">Vehicle ID:</div>
              <div class="font-mono text-gray-800">${selectedTrain.vehicle_id}</div>
            </div>
          </div>
        `;

        // Show popup
        popup.current
          .setLngLat([selectedTrain.longitude, selectedTrain.latitude])
          .setHTML(popupContent)
          .addTo(map.current);
      } catch (err) {
        console.error('Error showing popup:', err);
      }
    } else {
      // Remove popup if no train is selected
      popup.current.remove();
    }
  }, [selectedTrain, mapLoaded]);

  // Update station visibility when toggled
  useEffect(() => {
    if (!mapLoaded || !map.current) return;
    
    map.current.setLayoutProperty(
      'subway-stations-layer',
      'visibility',
      showStations ? 'visible' : 'none'
    );
    
    map.current.setLayoutProperty(
      'subway-stations-labels',
      'visibility',
      showStations ? 'visible' : 'none'
    );
  }, [showStations, mapLoaded]);

  // Toggle map style
  const toggleMapStyle = () => {
    setMapStyle(prevStyle => 
      prevStyle === 'light-v11' ? 'dark-v11' : 'light-v11'
    );
  };

  // Reset map view to NYC
  const resetMapView = () => {
    map.current?.flyTo({
      center: [-73.985, 40.745],
      zoom: 12,
      essential: true
    });
  };

  // Toggle stations visibility
  const toggleStations = () => {
    setShowStations(prev => !prev);
  };

  // Show a placeholder if map fails to load
  if (!MAPBOX_TOKEN || MAPBOX_TOKEN.length < 20) {
    return (
      <div className="relative flex h-full w-full items-center justify-center bg-gray-100">
        <div className="text-center p-4">
          <div className="text-red-600 mb-2">Error: Missing or invalid Mapbox token</div>
          <div className="text-sm text-gray-600">Please check your environment variables</div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <div ref={mapContainer} className="h-full w-full" />
      
      {/* Map controls overlay */}
      <div className="absolute bottom-5 right-5 z-10 flex flex-col space-y-2">
        <button
          onClick={() => setShowControls(!showControls)}
          className="rounded-lg bg-white p-2 shadow-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Toggle map controls"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </button>
        
        {showControls && (
          <>
            <button
              onClick={toggleMapStyle}
              className="rounded-lg bg-white p-2 shadow-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label={mapStyle === 'light-v11' ? 'Switch to dark mode' : 'Switch to light mode'}
            >
              {mapStyle === 'light-v11' ? (
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              )}
            </button>
            
            <button
              onClick={toggleStations}
              className="rounded-lg bg-white p-2 shadow-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label={showStations ? 'Hide stations' : 'Show stations'}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>
            
            <button
              onClick={resetMapView}
              className="rounded-lg bg-white p-2 shadow-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="Reset map view"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </button>
            
            <button
              onClick={() => setSelectedTrain(null)}
              className={`rounded-lg bg-white p-2 shadow-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 ${!selectedTrain ? 'opacity-50 cursor-not-allowed' : ''}`}
              disabled={!selectedTrain}
              aria-label="Close popup"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </>
        )}
      </div>
      
      {/* Legend overlay */}
      <div className="absolute bottom-5 left-5 z-10 bg-white bg-opacity-90 p-3 rounded-lg shadow-md max-w-xs">
        <div className="text-xs font-medium text-gray-700 mb-2">Map Legend</div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(MTA_LINE_COLORS).filter(([key]) => 
            // Filter out duplicate colors - only get one line per color family
            key === '1' || key === '4' || key === '7' || key === 'A' || 
            key === 'B' || key === 'G' || key === 'J' || key === 'L' || 
            key === 'N' || key === 'S' || key === 'SIR'
          ).map(([key, color]) => (
            <div key={key} className="flex items-center" title={`${key} Line`}>
              <div className="h-4 w-4 rounded-full mr-1" style={{ backgroundColor: color, border: '1px solid white' }}></div>
              <span className="text-xs text-gray-700">{key}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 text-xs text-gray-500">
          Showing {filteredTrains.length} active trains
        </div>
      </div>
      
      {/* Map attribution overlay */}
      <div className="absolute bottom-2 left-2 z-10 text-xs text-gray-600">
        <span>Data: MTA GTFS-RT feeds</span>
      </div>
      
      {/* Loading state */}
      {!mapLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-white bg-opacity-80">
          <div className="flex flex-col items-center">
            <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-600 border-t-transparent"></div>
            <p className="mt-3 text-sm font-medium text-gray-700">Loading map...</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default SubwayMap;