import { BotSettings, PortfolioStats, Position } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchApi<T>(endpoint: string, options?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new ApiError(response.status, `API Error: ${response.statusText}`);
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new Error(`Network error: ${error}`);
  }
}

// Settings API
export const settingsApi = {
  getSettings: () => fetchApi<BotSettings>('/api/settings'),
  updateSettings: (settings: BotSettings) =>
    fetchApi<BotSettings>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),
};

// Portfolio API
export const portfolioApi = {
  getStats: () => fetchApi<PortfolioStats>('/api/portfolio'),
  getPositions: () => fetchApi<Position[]>('/api/positions'),
};

// Health Check
export const healthApi = {
  check: () => fetchApi<{ status: string }>('/health'),
};
