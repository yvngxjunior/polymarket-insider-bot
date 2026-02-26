import axios from 'axios'
import type {
  Portfolio,
  PositionsResponse,
  TradesResponse,
  WalletsResponse,
  HealthStatus,
} from '../types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 10000,
})

export const apiService = {
  // Health
  async getHealth(): Promise<HealthStatus> {
    const { data } = await api.get<HealthStatus>('/health')
    return data
  },

  // Portfolio
  async getPortfolio(): Promise<Portfolio> {
    const { data } = await api.get<Portfolio>('/api/portfolio')
    return data
  },

  // Positions
  async getPositions(): Promise<PositionsResponse> {
    const { data } = await api.get<PositionsResponse>('/api/positions')
    return data
  },

  // Trades
  async getTrades(
    page = 1,
    perPage = 50,
    status?: 'EXECUTED' | 'SKIPPED' | 'FAILED'
  ): Promise<TradesResponse> {
    const { data } = await api.get<TradesResponse>('/api/trades', {
      params: { page, per_page: perPage, status },
    })
    return data
  },

  // Wallets
  async getWallets(activeOnly = false): Promise<WalletsResponse> {
    const { data } = await api.get<WalletsResponse>('/api/wallets', {
      params: { active_only: activeOnly },
    })
    return data
  },
}

export default api
