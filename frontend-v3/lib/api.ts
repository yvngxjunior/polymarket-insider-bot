import { DashboardData, RiskSettings } from './types'

const API_URL = 'http://localhost:8000/api';

export async function fetchDashboard(): Promise<DashboardData> {
  const res = await fetch(`${API_URL}/dashboard`, { cache: 'no-store' });
  if (!res.ok) throw new Error('API fetch failed');
  return res.json();
}

export async function toggleTarget(address: string, active: boolean) {
  await fetch(`${API_URL}/targets/${address}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ isActive: active })
  });
}

export async function cashOutPosition(positionId: string) {
  await fetch(`${API_URL}/positions/${positionId}/cashout`, { method: 'POST' });
}

export async function emergencyStopAll() {
  await fetch(`${API_URL}/emergency/stop-all`, { method: 'POST' });
}

export async function updateRiskSettings(settings: Partial<RiskSettings>) {
  await fetch(`${API_URL}/settings/risk`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  });
}
