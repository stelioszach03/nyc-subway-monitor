// process-stations.mjs - Convert stops.txt to GeoJSON with proper station data
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// Get current directory
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// MTA line colors for reference
const LINE_COLORS = {
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

// Default station colors by area/borough - used as fallback when route info isn't available
const AREA_COLORS = {
  'Manhattan': '#1E88E5',
  'Brooklyn': '#43A047',
  'Bronx': '#FB8C00',
  'Queens': '#8E24AA',
  'Staten Island': '#F4511E'
};

const stopsFile = path.join(__dirname, 'stops.txt');
const outputFile = path.join(__dirname, 'public', 'subway-stations.geojson');

// Create public directory if it doesn't exist
if (!fs.existsSync(path.join(__dirname, 'public'))) {
  fs.mkdirSync(path.join(__dirname, 'public'), { recursive: true });
}

// Read the stops.txt file
console.log(`Reading stops data from ${stopsFile}`);
const content = fs.readFileSync(stopsFile, 'utf8');
const lines = content.split('\n');

// Parse the header to get column indices
const headers = lines[0].split(',');
const getColumnIndex = (name) => headers.indexOf(name);

const stopIdIndex = getColumnIndex('stop_id');
const stopNameIndex = getColumnIndex('stop_name');
const stopLatIndex = getColumnIndex('stop_lat');
const stopLonIndex = getColumnIndex('stop_lon');
const locationTypeIndex = getColumnIndex('location_type');
const parentStationIndex = getColumnIndex('parent_station');

// Helper function to parse a CSV line properly (handles quotes)
function parseCSVLine(line) {
  const result = [];
  let inQuotes = false;
  let currentValue = '';
  
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      result.push(currentValue);
      currentValue = '';
    } else {
      currentValue += char;
    }
  }
  
  // Don't forget the last value
  result.push(currentValue);
  return result;
}

// Extract borough from station name if possible
function getBorough(name) {
  if (name.includes('- Manhattan')) return 'Manhattan';
  if (name.includes('- Brooklyn')) return 'Brooklyn';
  if (name.includes('- Bronx')) return 'Bronx';
  if (name.includes('- Queens')) return 'Queens';
  if (name.includes('- Staten Island')) return 'Staten Island';
  
  // Fallbacks based on common patterns
  if (name.includes('Manhattan')) return 'Manhattan';
  if (name.includes('Bklyn') || name.includes('Brooklyn')) return 'Brooklyn';
  if (name.includes('Bronx')) return 'Bronx';
  if (name.includes('Queens')) return 'Queens';
  if (name.includes('Staten Island')) return 'Staten Island';
  
  return 'Manhattan'; // Default fallback
}

// Assign a color based on station ID and name patterns
function assignStationColor(stopId, name) {
  // Try to extract route info from the stop_id
  const routeMatch = stopId.match(/^[A-Z0-9]+/);
  if (routeMatch && LINE_COLORS[routeMatch[0]]) {
    return LINE_COLORS[routeMatch[0]];
  }
  
  // Look for route indicators in the name
  for (const [route, color] of Object.entries(LINE_COLORS)) {
    if (name.includes(`(${route})`) || name.includes(`(${route} `) || 
        name.includes(`${route} Line`) || name.includes(`${route}-`)) {
      return color;
    }
  }
  
  // Use borough-based colors as fallback
  const borough = getBorough(name);
  return AREA_COLORS[borough] || '#808183';
}

// Create GeoJSON features
const features = [];
const parentStations = new Set();

// First pass: collect parent stations
for (let i = 1; i < lines.length; i++) {
  const line = lines[i].trim();
  if (!line) continue;
  
  const parts = parseCSVLine(line);
  
  // We're only interested in location_type 1 (parent stations)
  if (locationTypeIndex >= 0 && parts[locationTypeIndex] === '1') {
    parentStations.add(parts[stopIdIndex]);
  }
}

console.log(`Found ${parentStations.size} parent stations`);

// Second pass: process stations
for (let i = 1; i < lines.length; i++) {
  const line = lines[i].trim();
  if (!line) continue;
  
  const parts = parseCSVLine(line);
  
  // Skip if invalid row
  if (parts.length <= Math.max(stopIdIndex, stopNameIndex, stopLatIndex, stopLonIndex)) {
    continue;
  }
  
  // We only want parent stations (location_type = 1)
  // If location_type field exists and is not 1, skip
  if (locationTypeIndex >= 0 && parts[locationTypeIndex] !== '1') {
    // But also include entries that refer to parent stations
    if (parentStationIndex >= 0 && parts[parentStationIndex] && 
        parentStations.has(parts[parentStationIndex])) {
      continue; // Skip child entries of parent stations
    }
    
    // If it's not a parent and doesn't have a parent, it might be a standalone station
    if (locationTypeIndex >= 0 && parts[locationTypeIndex] !== '0') {
      continue; // Skip non-stations (like entrances)
    }
  }
  
  // Skip if missing required coordinates
  if (!parts[stopLatIndex] || !parts[stopLonIndex] || 
      isNaN(parseFloat(parts[stopLatIndex])) || isNaN(parseFloat(parts[stopLonIndex]))) {
    continue;
  }
  
  // Clean up station name
  let stationName = parts[stopNameIndex].replace(/"/g, '').trim();
  
  // Remove redundant suffixes
  stationName = stationName
    .replace(/ - Manhattan$/, '')
    .replace(/ - Brooklyn$/, '')
    .replace(/ - Queens$/, '')
    .replace(/ - Bronx$/, '')
    .replace(/ - Staten Island$/, '')
    .replace(/ Station$/, '');
  
  const stopId = parts[stopIdIndex].replace(/"/g, '').trim();
  const color = assignStationColor(stopId, stationName);
  
  try {
    features.push({
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: [parseFloat(parts[stopLonIndex]), parseFloat(parts[stopLatIndex])]
      },
      properties: {
        stop_id: stopId,
        station_name: stationName,
        color: color
      }
    });
  } catch (e) {
    console.error(`Error processing line ${i}:`, e);
  }
}

// Create GeoJSON object
const geojson = {
  type: 'FeatureCollection',
  features: features
};

// Write to file
fs.writeFileSync(outputFile, JSON.stringify(geojson, null, 2));
console.log(`✅ Generated GeoJSON with ${features.length} stations at: ${outputFile}`);
