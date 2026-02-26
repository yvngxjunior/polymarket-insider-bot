import { useState } from 'react'
import { useWallets } from '../hooks/useApi'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

export default function Wallets() {
  const [activeOnly, setActiveOnly] = useState(false)
  const { data, isLoading } = useWallets(activeOnly)

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-10 w-64 bg-gray-200 animate-pulse rounded-lg" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="glass-card h-64 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Tracked Wallets</h1>
          <p className="text-gray-500 mt-1">
            {data?.active_count || 0} active &bull; {data?.total_count || 0} total
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
        {data?.wallets.map((wallet) => {
          // Nom affiché : username Polymarket > label DB > adresse courte
          const displayName =
            wallet.polymarket_display_name ||
            wallet.polymarket_username ||
            wallet.label ||
            null

          const shortAddress = `${wallet.address.slice(0, 6)}...${wallet.address.slice(-4)}`
          const profileUrl = wallet.polymarket_url

          return (
            <div key={wallet.address} className="glass-card glass-card-hover">
              {/* Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  {/* Avatar Polymarket ou initiales */}
                  {wallet.polymarket_pfp ? (
                    <img
                      src={wallet.polymarket_pfp}
                      alt={displayName || shortAddress}
                      className="w-10 h-10 rounded-full object-cover border-2 border-white shadow-sm"
                      onError={(e) => {
                        // Fallback si image cassée
                        ;(e.target as HTMLImageElement).style.display = 'none'
                      }}
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-400 to-indigo-400 flex items-center justify-center text-white font-bold text-sm shadow-sm">
                      {displayName
                        ? displayName.slice(0, 2).toUpperCase()
                        : wallet.address.slice(2, 4).toUpperCase()}
                    </div>
                  )}

                  <div>
                    {/* Nom + lien Polymarket */}
                    {displayName ? (
                      <a
                        href={profileUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-semibold text-gray-900 hover:text-violet-600 transition-colors flex items-center gap-1"
                      >
                        {displayName}
                        <svg className="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                    ) : (
                      // Pas de profil Polymarket → lien direct quand même
                      <a
                        href={profileUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm font-semibold text-gray-700 hover:text-violet-600 transition-colors"
                      >
                        Unnamed Trader
                      </a>
                    )}

                    {/* Adresse courte */}
                    <a
                      href={`https://polygonscan.com/address/${wallet.address}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-['Roboto_Mono'] text-gray-400 hover:text-gray-600 transition-colors"
                    >
                      {shortAddress}
                    </a>
                  </div>
                </div>

                {/* Badges Active / Whale */}
                <div className="flex flex-col gap-1 items-end">
                  {wallet.is_active && <span className="badge badge-success">Active</span>}
                  {wallet.is_whale && <span className="badge badge-info">Whale</span>}
                </div>
              </div>

              {/* Score */}
              <div className="mb-4">
                <div className="flex items-end justify-between mb-1">
                  <div className="text-xs text-gray-500">Wallet Score</div>
                  <div className="text-xs text-gray-400">{wallet.score.toFixed(1)} / 100</div>
                </div>
                <div className="flex items-end gap-2 mb-2">
                  <div className="text-2xl font-bold">{wallet.score.toFixed(1)}</div>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-gradient-to-r from-violet-500 to-indigo-500 h-2 rounded-full transition-all"
                    style={{ width: `${Math.min(wallet.score, 100)}%` }}
                  />
                </div>
              </div>

              {/* Stats grid */}
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
              <div className="text-xs text-gray-400 border-t border-gray-200/50 pt-3 flex items-center justify-between">
                <span>
                  Last activity:{' '}
                  {wallet.last_activity
                    ? formatDistanceToNow(new Date(wallet.last_activity), { addSuffix: true })
                    : 'Unknown'}
                </span>
                {/* Lien Polymarket */}
                <a
                  href={profileUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-violet-500 hover:text-violet-700 text-xs font-medium flex items-center gap-1"
                >
                  View on Polymarket
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </a>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
