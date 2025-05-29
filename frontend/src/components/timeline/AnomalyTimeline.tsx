import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import { format } from 'date-fns'
import { TimelineControls } from './TimelineControls'

interface AnomalyTimelineProps {
  anomalies: any[]
  timeRange: [Date, Date]
  onTimeRangeChange: (range: [Date, Date]) => void
  isLoading?: boolean
}

export function AnomalyTimeline({ 
  anomalies, 
  timeRange, 
  onTimeRangeChange,
  isLoading 
}: AnomalyTimelineProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || anomalies.length === 0) return

    // Clear previous chart
    d3.select(svgRef.current).selectAll('*').remove()

    // Dimensions
    const margin = { top: 20, right: 20, bottom: 40, left: 50 }
    const width = containerRef.current.clientWidth - margin.left - margin.right
    const height = 200 - margin.top - margin.bottom

    // Create SVG
    const svg = d3.select(svgRef.current)
      .attr('width', width + margin.left + margin.right)
      .attr('height', height + margin.top + margin.bottom)

    const g = svg.append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    // Scales
    const xScale = d3.scaleTime()
      .domain(timeRange)
      .range([0, width])

    const yScale = d3.scaleLinear()
      .domain([0, d3.max(anomalies, d => d.severity) || 1])
      .range([height, 0])

    // Color scale for severity
    const colorScale = d3.scaleSequential(d3.interpolateOrRd)
      .domain([0, 1])

    // X-axis
    g.append('g')
      .attr('transform', `translate(0,${height})`)
      .call(d3.axisBottom(xScale)
        .ticks(6)
        .tickFormat(d => format(d as Date, 'HH:mm'))
      )
      .attr('class', 'text-gray-400')

    // Y-axis
    g.append('g')
      .call(d3.axisLeft(yScale)
        .ticks(5)
        .tickFormat(d => `${(d as number * 100).toFixed(0)}%`)
      )
      .attr('class', 'text-gray-400')

    // Add anomaly circles
    g.selectAll('.anomaly')
      .data(anomalies)
      .enter()
      .append('circle')
      .attr('class', 'anomaly cursor-pointer hover:stroke-white hover:stroke-2')
      .attr('cx', d => xScale(new Date(d.detected_at)))
      .attr('cy', d => yScale(d.severity))
      .attr('r', 4)
      .attr('fill', d => colorScale(d.severity))
      .attr('opacity', 0.8)
      .on('mouseover', function(event, d) {
        // Show tooltip
        const tooltip = d3.select('body').append('div')
          .attr('class', 'tooltip bg-gray-900 text-white p-2 rounded shadow-lg text-sm')
          .style('position', 'absolute')
          .style('opacity', 0)

        tooltip.transition()
          .duration(200)
          .style('opacity', .9)

        tooltip.html(`
          <div class="font-bold">${d.anomaly_type}</div>
          <div>Severity: ${(d.severity * 100).toFixed(1)}%</div>
          <div>Station: ${d.station_id || 'Unknown'}</div>
          <div>Time: ${format(new Date(d.detected_at), 'HH:mm:ss')}</div>
        `)
          .style('left', (event.pageX + 10) + 'px')
          .style('top', (event.pageY - 28) + 'px')
      })
      .on('mouseout', function() {
        d3.selectAll('.tooltip').remove()
      })

    // Add brush for time selection
    const brush = d3.brushX()
      .extent([[0, 0], [width, height]])
      .on('end', (event) => {
        if (event.selection) {
          const [x0, x1] = event.selection
          const newRange: [Date, Date] = [
            xScale.invert(x0),
            xScale.invert(x1)
          ]
          onTimeRangeChange(newRange)
        }
      })

    g.append('g')
      .attr('class', 'brush')
      .call(brush)

  }, [anomalies, timeRange, onTimeRangeChange])

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-3 border-b border-gray-800">
        <h2 className="text-lg font-semibold mb-2">Anomaly Timeline</h2>
        <TimelineControls
          timeRange={timeRange}
          onTimeRangeChange={onTimeRangeChange}
        />
      </div>
      
      <div ref={containerRef} className="flex-1 p-4">
        {isLoading ? (
          <div className="h-full flex items-center justify-center">
            <div className="animate-pulse text-gray-500">Loading timeline...</div>
          </div>
        ) : anomalies.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-gray-500">No anomalies in selected range</div>
          </div>
        ) : (
          <svg ref={svgRef} className="w-full h-full" />
        )}
      </div>
    </div>
  )
}