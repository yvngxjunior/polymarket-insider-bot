'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { portfolioApi } from '@/lib/api';
import { PortfolioStats } from '@/lib/types';
import { formatCurrency, formatPercentage, getPnLColor } from '@/lib/utils';

export default function DashboardPage() {
  const [stats, setStats] = useState<PortfolioStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, []);

  const fetchStats = async () => {
    try {
      const data = await portfolioApi.getStats();
      setStats(data);
      setError(null);
    } catch (err) {
      setError('Failed to load portfolio data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mb-4 inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
          <p className="text-gray-400">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="rounded-lg border border-red-800 bg-red-900/20 p-6">
        <h3 className="text-lg font-semibold text-red-100">Error</h3>
        <p className="mt-2 text-sm text-red-200">{error || 'Failed to load data'}</p>
      </div>
    );
  }

  const statCards = [
    {
      title: 'Total Capital',
      value: formatCurrency(stats.total_capital),
      change: stats.total_pnl,
      icon: '💰',
    },
    {
      title: 'Total PnL',
      value: formatCurrency(stats.total_pnl),
      percentage: ((stats.total_pnl / stats.peak_capital) * 100).toFixed(2) + '%',
      icon: '📈',
      color: getPnLColor(stats.total_pnl),
    },
    {
      title: 'Daily PnL',
      value: formatCurrency(stats.daily_pnl),
      icon: '📅',
      color: getPnLColor(stats.daily_pnl),
    },
    {
      title: 'Win Rate',
      value: formatPercentage(stats.win_rate, 1),
      subtitle: `${stats.winning_trades}W / ${stats.losing_trades}L`,
      icon: '🎯',
    },
    {
      title: 'Total Trades',
      value: stats.total_trades.toString(),
      subtitle: `${stats.open_positions} open`,
      icon: '🔄',
    },
    {
      title: 'Avg Win / Loss',
      value: `${formatCurrency(stats.avg_win)} / ${formatCurrency(Math.abs(stats.avg_loss))}`,
      icon: '⚖️',
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="mt-2 text-gray-400">Real-time portfolio overview</p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {statCards.map((stat, index) => (
          <Card key={index} className="transition-transform hover:scale-105">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium text-gray-400">
                  {stat.title}
                </CardTitle>
                <span className="text-2xl">{stat.icon}</span>
              </div>
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${stat.color || ''}`}>
                {stat.value}
              </div>
              {stat.subtitle && (
                <p className="mt-1 text-sm text-gray-500">{stat.subtitle}</p>
              )}
              {stat.percentage && (
                <p className={`mt-1 text-sm font-medium ${stat.color}`}>
                  {stat.change && stat.change > 0 ? '+' : ''}{stat.percentage}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Performance Summary */}
      <Card>
        <CardHeader>
          <CardTitle>Performance Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Peak Capital</span>
              <span className="font-mono font-semibold">{formatCurrency(stats.peak_capital)}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Largest Win</span>
              <span className="font-mono font-semibold text-green-500">
                +{formatCurrency(stats.largest_win)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Largest Loss</span>
              <span className="font-mono font-semibold text-red-500">
                {formatCurrency(stats.largest_loss)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-400">Open Positions</span>
              <span className="font-mono font-semibold">{stats.open_positions}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
