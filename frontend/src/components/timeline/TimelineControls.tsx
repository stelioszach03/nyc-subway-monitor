import { format } from 'date-fns'

interface TimelineControlsProps {
  timeRange: [Date, Date]
  onTimeRangeChange: (range: [Date, Date]) => void
}

export function TimelineControls({ timeRange, onTimeRangeChange }: TimelineControlsProps) {
  const presets = [
    { label: '1H', hours: 1 },
    { label: '6H', hours: 6 },
    { label: '24H', hours: 24 },
    { label: '7D', hours: 168 },
  ]

  const handlePresetClick = (hours: number) => {
    const end = new Date()
    const start = new Date(end.getTime() - hours * 60 * 60 * 1000)
    onTimeRangeChange([start, end])
  }

  return (
    <div className="flex items-center justify-between">
      <div className="flex gap-2">
        {presets.map(preset => (
          <button
            key={preset.label}
            onClick={() => handlePresetClick(preset.hours)}
            className="px-3 py-1 bg-gray-800 hover:bg-gray-700 rounded text-sm transition-colors"
          >
            {preset.label}
          </button>
        ))}
      </div>
      
      <div className="text-sm text-gray-400">
        {format(timeRange[0], 'MMM d, HH:mm')} - {format(timeRange[1], 'HH:mm')}
      </div>
    </div>
  )
}