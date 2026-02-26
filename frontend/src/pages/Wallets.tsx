import { useState } from 'react'
import { useWallets } from '../hooks/useApi'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

export default function Wallets() {
  const [activeOnly, setActiveOnly] = useState(false)
  const { data, isLoading } = useWallets(activeOnly)

  if (isLoading) {
    return <div className="glass-card h-96 animate-pulse" />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Tracked Wallets</h1>
          <p className="text-gray-500 mt-1">
            {data?.active_count || 0} active • {data?.total_count || 0} total
          </p>
        </div>

        {/* Active Filter */}
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(e) => setActiveOnly(e.target.checked)}
            className="rounded border-gray-300 text-violet-600 focus:ring-violet-500"
          />
          <span className="text-sm font-medium text-gray-700">Active only</span>
        </label>
      </div>

      {/* Wallets Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {data?.wallets.map((wallet) => (
          <div key={wallet.address} className="glass-card glass-card-hover">
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="text-xs text-gray-500 mb-1">
                  {wallet.label || 'Unnamed Wallet'}
                </div>
                <div className="text-xs font-['Roboto_Mono'] text-gray-400">
                  {wallet.address.slice(0, 6)}...{wallet.address.slice(-4)}
                </div>
              </div>
              <div className="flex gap-1">
                {wallet.is_active && <span className="badge badge-success">Active</span>}
                {wallet.is_whale && <span className="badge badge-info">Whale</span>}
              </div>
            </div>

            {/* Score */}
            <div className="mb-4">
              <div className="text-xs text-gray-500 mb-1">Wallet Score</div>
              <div className="flex items-end gap-2">
                <div className="text-2xl font-bold">{wallet.score.toFixed(1)}</div>
                <div className="text-sm text-gray-500">/ 100</div>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                <div
                  className="bg-gradient-to-r from-violet-500 to-indigo-500 h-2 rounded-full transition-all"
                  style={{ width: `${wallet.score}%` }}
                />
              </div>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <div className="text-xs text-gray-500">Win Rate</div>
                <div className="text-lg font-['Roboto_Mono'] font-bold profit-text">
                  {(wallet.win_rate * 100).toFixed(1)}%
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Total Profit</div>
                <div className="text-lg font-['Roboto_Mono'] font-bold profit-text">
                  ${wallet.total_profit_usd.toFixed(0)}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Total Trades</div>
                <div className="text-lg font-['Roboto_Mono'] font-bold">
                  {wallet.total_trades}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Streak</div>
                <div
                  className={clsx(
                    "text-lg font-['Roboto_Mono'] font-bold",
                    wallet.consecutive_losses > 0 ? 'loss-text' : 'profit-text'
                  )}
                >
                  {wallet.consecutive_losses > 0 ? `-${wallet.consecutive_losses}` : '✓'}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="text-xs text-gray-400 border-t border-gray-200/50 pt-3">
              Last activity: {formatDistanceToNow(new Date(wallet.last_activity), { addSuffix: true })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
