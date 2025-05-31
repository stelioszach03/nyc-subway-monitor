import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api'
import type { AnomalyListResponse, AnomalyStats } from '@/types'

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
  const anomaliesQuery = useQuery<AnomalyListResponse>({
    queryKey: ['anomalies', { line, station, startDate, endDate, page, pageSize }],
    queryFn: async () => {
      const response = await apiClient.get<AnomalyListResponse>('/anomalies', {
        params: {
          line: line || undefined,
          station_id: station || undefined,
          start_date: startDate?.toISOString(),
          end_date: endDate?.toISOString(),
          page,
          page_size: pageSize,
        }
      })
      return response.data
    },
    refetchInterval: 30000, // Refetch every 30 seconds
  })

  // Fetch stats
  const statsQuery = useQuery<AnomalyStats>({
    queryKey: ['anomaly-stats'],
    queryFn: async () => {
      const response = await apiClient.get<AnomalyStats>('/anomalies/stats', {
        params: {
          hours: 24,
        }
      })
      return response.data
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