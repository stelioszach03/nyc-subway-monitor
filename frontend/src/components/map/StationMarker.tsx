interface StationMarkerProps {
  severity: number
  count: number
  isSelected?: boolean
}

export function StationMarker({ severity, count, isSelected }: StationMarkerProps) {
  // Determine color based on severity
  const getColor = () => {
    if (severity > 0.7) return '#ef4444' // red
    if (severity > 0.4) return '#f59e0b' // amber
    return '#eab308' // yellow
  }

  const color = getColor()
  const size = 20 + (severity * 20) // Dynamic size based on severity

  return `
    <div class="relative cursor-pointer ${isSelected ? 'z-50' : 'z-10'}">
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
        class="relative rounded-full border-2 ${isSelected ? 'border-white' : 'border-gray-800'} shadow-lg"
        style="
          width: ${size}px;
          height: ${size}px;
          background-color: ${color};
          box-shadow: 0 0 10px ${color};
        "
      >
        <span class="absolute inset-0 flex items-center justify-center text-xs font-bold text-white">
          ${count}
        </span>
      </div>
    </div>
  `
}