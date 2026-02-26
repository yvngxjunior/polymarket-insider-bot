'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { portfolioApi } from '@/lib/api';
import { Position } from '@/lib/types';
import { formatCurrency, formatRelativeTime, getPnLColor } from '@/lib/utils';

export default function PositionsPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchPositions = async () => {
    try {
      const data = await portfolioApi.getPositions();
      setPositions(data);
    } catch (error) {
      console.error('Failed to fetch positions', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mb-4 inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
          <p className="text-gray-400">Loading positions...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Open Positions</h1>
          <p className="mt-2 text-gray-400">{positions.length} active trades</p>
        </div>
        <button
          onClick={fetchPositions}
          className="rounded-md bg-gray-800 px-4 py-2 text-sm font-medium hover:bg-gray-700"
        >
          🔄 Refresh
        </button>
      </div>

      {positions.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-gray-400">No open positions</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-800 text-left text-sm text-gray-400">
                    <th className="p-4 font-medium">Market</th>
                    <th className="p-4 font-medium">Side</th>
                    <th className="p-4 font-medium">Amount</th>
                    <th className="p-4 font-medium">Entry</th>
                    <th className="p-4 font-medium">PnL</th>
                    <th className="p-4 font-medium">Age</th>
                    <th className="p-4 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos) => (
                    <tr
                      key={pos.id}
                      className="border-b border-gray-800/50 transition-colors hover:bg-gray-800/30"
                    >
                      <td className="p-4">
                        <p className="max-w-xs truncate font-medium">{pos.market_question}</p>
                        <p className="text-xs text-gray-500">{pos.token_id}</p>
                      </td>
                      <td className="p-4">
                        <span
                          className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${
                            pos.side === 'BUY'
                              ? 'bg-green-900/20 text-green-500'
                              : 'bg-red-900/20 text-red-500'
                          }`}
                        >
                          {pos.side}
                        </span>
                      </td>
                      <td className="p-4 font-mono text-sm">{formatCurrency(pos.amount_usdc)}</td>
                      <td className="p-4 font-mono text-sm">{pos.entry_price.toFixed(3)}</td>
                      <td className="p-4">
                        {pos.pnl_usdc !== null ? (
                          <div>
                            <p className={`font-mono text-sm font-semibold ${getPnLColor(pos.pnl_usdc)}`}>
                              {pos.pnl_usdc >= 0 ? '+' : ''}{formatCurrency(pos.pnl_usdc)}
                            </p>
                            {pos.pnl_pct !== null && (
                              <p className={`text-xs ${getPnLColor(pos.pnl_usdc)}`}>
                                ({pos.pnl_pct >= 0 ? '+' : ''}{(pos.pnl_pct * 100).toFixed(1)}%)
                              </p>
                            )}
                          </div>
                        ) : (
                          <span className="text-sm text-gray-500">-</span>
                        )}
                      </td>
                      <td className="p-4 text-sm text-gray-400">{formatRelativeTime(pos.age_hours)}</td>
                      <td className="p-4 font-mono text-xs text-gray-500">{pos.source_wallet}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
