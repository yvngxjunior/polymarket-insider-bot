import { useState } from 'react'
import { useTrades } from '../hooks/useApi'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

type TradeStatus = 'EXECUTED' | 'SKIPPED' | 'FAILED' | undefined

export default function TradeHistory() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<TradeStatus>(undefined)
  const perPage = 25

  const { data, isLoading } = useTrades(page, perPage, status)

  if (isLoading) {
    return <div className="glass-card h-96 animate-pulse" />
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Trade History</h1>
          <p className="text-gray-500 mt-1">
            {data?.total_count || 0} total trades
          </p>
        </div>

        {/* Status Filter */}
        <div className="flex gap-2">
          <button
            onClick={() => setStatus(undefined)}
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium transition-all',
              status === undefined
                ? 'bg-gradient-to-r from-violet-500 to-indigo-500 text-white shadow-lg'
                : 'bg-white/50 text-gray-700 hover:bg-white/70'
            )}
          >
            All
          </button>
          <button
            onClick={() => setStatus('EXECUTED')}
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium transition-all',
              status === 'EXECUTED'
                ? 'bg-gradient-to-r from-green-500 to-emerald-500 text-white shadow-lg'
                : 'bg-white/50 text-gray-700 hover:bg-white/70'
            )}
          >
            Executed
          </button>
          <button
            onClick={() => setStatus('SKIPPED')}
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium transition-all',
              status === 'SKIPPED'
                ? 'bg-gradient-to-r from-yellow-500 to-amber-500 text-white shadow-lg'
                : 'bg-white/50 text-gray-700 hover:bg-white/70'
            )}
          >
            Skipped
          </button>
          <button
            onClick={() => setStatus('FAILED')}
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium transition-all',
              status === 'FAILED'
                ? 'bg-gradient-to-r from-red-500 to-rose-500 text-white shadow-lg'
                : 'bg-white/50 text-gray-700 hover:bg-white/70'
            )}
          >
            Failed
          </button>
        </div>
      </div>

      {/* Trades Table */}
      <div className="glass-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200/50">
            <thead>
              <tr className="text-left">
                <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">Date</th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">Market</th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">Side</th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">Amount</th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">Price</th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">P&L</th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">TX</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200/30">
              {data?.trades.map((trade) => (
                <tr key={trade.id} className="hover:bg-white/30 transition-colors">
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {formatDistanceToNow(new Date(trade.created_at), { addSuffix: true })}
                  </td>
                  <td className="px-4 py-3 text-sm font-medium text-gray-900 max-w-xs truncate">
                    {trade.market_question || 'Unknown'}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        'badge',
                        trade.side === 'BUY' ? 'badge-success' : 'badge-error'
                      )}
                    >
                      {trade.side}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm font-['Roboto_Mono']">
                    ${trade.amount_usdc.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-sm font-['Roboto_Mono']">
                    {trade.price.toFixed(3)}
                  </td>
                  <td className="px-4 py-3">
                    {trade.pnl_usdc !== null ? (
                      <span
                        className={clsx(
                          "text-sm font-['Roboto_Mono'] font-medium",
                          trade.pnl_usdc >= 0 ? 'profit-text' : 'loss-text'
                        )}
                      >
                        {trade.pnl_usdc >= 0 ? '+' : ''}${trade.pnl_usdc.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-sm text-gray-400">---</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={clsx(
                        'badge',
                        trade.status === 'EXECUTED'
                          ? 'badge-success'
                          : trade.status === 'SKIPPED'
                          ? 'badge-warning'
                          : 'badge-error'
                      )}
                    >
                      {trade.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {trade.tx_hash ? (
                      <a
                        href={`https://polygonscan.com/tx/${trade.tx_hash}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-500 hover:text-blue-600 text-sm"
                      >
                        View
                      </a>
                    ) : (
                      <span className="text-sm text-gray-400">---</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {data && data.total_count > perPage && (
          <div className="px-4 py-3 border-t border-gray-200/50 flex items-center justify-between">
            <div className="text-sm text-gray-500">
              Showing {(page - 1) * perPage + 1} to {Math.min(page * perPage, data.total_count)} of{' '}
              {data.total_count} results
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 rounded-lg bg-white/50 hover:bg-white/70 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page * perPage >= data.total_count}
                className="px-3 py-1 rounded-lg bg-white/50 hover:bg-white/70 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
