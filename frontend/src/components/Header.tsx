import { useHealth, usePortfolio } from '../hooks/useApi'
import { ArrowPathIcon } from '@heroicons/react/24/outline'
import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'

export default function Header() {
  const queryClient = useQueryClient()
  const { data: health } = useHealth()
  const { data: portfolio } = usePortfolio()

  const handleRefresh = () => {
    queryClient.invalidateQueries()
  }

  return (
    <header className="h-16 bg-white/70 backdrop-blur-md border-b border-white/30 shadow-glass sticky top-0 z-10">
      <div className="h-full px-6 flex items-center justify-between">
        {/* Left: Portfolio Summary */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">Capital:</span>
            <span className="font-['Roboto_Mono'] text-lg font-bold">
              ${portfolio?.total_capital.toFixed(2) || '---'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">Daily P&L:</span>
            <span
              className={clsx(
                "font-['Roboto_Mono'] text-lg font-bold",
                (portfolio?.daily_pnl ?? 0) >= 0 ? 'text-profit' : 'text-loss'
              )}
            >
              {(portfolio?.daily_pnl ?? 0) >= 0 ? '+' : ''}
              ${portfolio?.daily_pnl.toFixed(2) || '0.00'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">Positions:</span>
            <span className="font-['Roboto_Mono'] text-lg font-bold">
              {portfolio?.open_positions_count || 0}
            </span>
          </div>
        </div>

        {/* Right: Status + Refresh */}
        <div className="flex items-center gap-4">
          {/* API Status */}
          <div className="flex items-center gap-2">
            <div
              className={clsx(
                'w-2 h-2 rounded-full',
                health?.status === 'ok'
                  ? 'bg-green-500 animate-pulse'
                  : 'bg-red-500'
              )}
            />
            <span className="text-sm text-gray-600">
              {health?.status === 'ok' ? 'API Online' : 'API Offline'}
            </span>
          </div>

          {/* Refresh Button */}
          <button
            onClick={handleRefresh}
            className="p-2 rounded-lg hover:bg-white/50 transition-colors group"
            title="Refresh all data"
          >
            <ArrowPathIcon className="w-5 h-5 text-gray-600 group-hover:rotate-180 transition-transform duration-500" />
          </button>
        </div>
      </div>
    </header>
  )
}
