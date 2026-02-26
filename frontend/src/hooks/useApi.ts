import { useQuery } from '@tanstack/react-query'
import { apiService } from '../services/api'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiService.getHealth(),
    refetchInterval: 10000, // Check health every 10s
  })
}

export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: () => apiService.getPortfolio(),
  })
}

export function usePositions() {
  return useQuery({
    queryKey: ['positions'],
    queryFn: () => apiService.getPositions(),
  })
}

export function useTrades(
  page = 1,
  perPage = 50,
  status?: 'EXECUTED' | 'SKIPPED' | 'FAILED'
) {
  return useQuery({
    queryKey: ['trades', page, perPage, status],
    queryFn: () => apiService.getTrades(page, perPage, status),
  })
}

export function useWallets(activeOnly = false) {
  return useQuery({
    queryKey: ['wallets', activeOnly],
    queryFn: () => apiService.getWallets(activeOnly),
  })
}
