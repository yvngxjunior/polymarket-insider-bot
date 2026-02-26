import { usePositions } from '../hooks/useApi'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

export default function PositionsTable() {
  const { data, isLoading } = usePositions()

  if (isLoading) {
    return <div className="glass-card h-64 animate-pulse" />
  }

  if (!data || data.positions.length === 0) {
    return (
      <div className="glass-card text-center py-12">
        <p className="text-gray-500">No active positions</p>
      </div>
    )
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200/50">
          <thead>
            <tr className="text-left">
              <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                Market
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                Side
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                Entry
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                Current
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                P&L
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                TP/SL
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">
                Age
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200/30">
            {data.positions.map((position) => (
              <tr key={position.trade_id} className="hover:bg-white/30 transition-colors">
                <td className="px-4 py-3 text-sm font-medium text-gray-900 max-w-xs truncate">
                  {position.market_question}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      'badge',
                      position.side === 'BUY' ? 'badge-success' : 'badge-error'
                    )}
                  >
                    {position.side}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm font-['Roboto_Mono']">
                  {position.entry_price.toFixed(3)}
                </td>
                <td className="px-4 py-3 text-sm font-['Roboto_Mono']">
                  {position.current_price?.toFixed(3) || '---'}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={clsx(
                      "text-sm font-['Roboto_Mono'] font-medium",
                      (position.unrealized_pnl ?? 0) >= 0 ? 'profit-text' : 'loss-text'
                    )}
                  >
                    {position.unrealized_pnl !== null
                      ? `${position.unrealized_pnl >= 0 ? '+' : ''}$${position.unrealized_pnl.toFixed(2)}`
                      : '---'}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex gap-1">
                    {position.tp1_hit ? (
                      <span className="badge badge-success text-xs">TP1✓</span>
                    ) : (
                      <span className="badge badge-warning text-xs">TP1</span>
                    )}
                    <span className="badge badge-info text-xs">SL</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {formatDistanceToNow(new Date(position.opened_at), { addSuffix: true })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
