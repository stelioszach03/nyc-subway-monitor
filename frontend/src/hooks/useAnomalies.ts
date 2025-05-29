import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'

interface UseAnomaliesOptions {
  line?: string | null
  station?: string | null
  startDate?: Date
  endDate?: Date
  page?: number
  pageSize?: number
}

export function useAnomalies(options: UseAnomaliesOptions = {}) {
  const {
    line,
    station,
    startDate,
    endDate,
    page = 1,
    pageSize = 100,
  } = options

  // Fetch anomalies
  const anomaliesQuery = useQuery({
    queryKey: ['anomalies', { line, station, startDate, endDate, page, pageSize }],
    queryFn: async () => {
      return apiClient.get('/api/v1/anomalies', {
        line: line || undefined,
        station_id: station || undefined,
        start_date: startDate?.toISOString(),
        end_date: endDate?.toISOString(),
        page,
        page_size: pageSize,
      })
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  })

  // Fetch stats
  const statsQuery = useQuery({
    queryKey: ['anomaly-stats'],
    queryFn: async () => {
      return apiClient.get('/api/v1/anomalies/stats', {
        hours: 24,
      })
    },
    refetchInterval: 60000, // Refetch every minute
  })

  return {
    anomalies: anomaliesQuery.data?.anomalies || [],
    total: anomaliesQuery.data?.total || 0,
    stats: statsQuery.data,
    isLoading: anomaliesQuery.isLoading || statsQuery.isLoading,
    error: anomaliesQuery.error || statsQuery.error,
    refetch: () => {
      anomaliesQuery.refetch()
      statsQuery.refetch()
    },
  }
}