import { usePortfolio } from '../hooks/useApi'
import StatCard from './StatCard'
import {
  BanknotesIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline'

export default function PortfolioOverview() {
  const { data: portfolio, isLoading } = usePortfolio()

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="glass-card h-40 animate-pulse" />
        ))}
      </div>
    )
  }

  if (!portfolio) return null

  const profitLossChange =
    portfolio.total_capital > 0
      ? (portfolio.daily_pnl / portfolio.total_capital) * 100
      : 0

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {/* Total Capital */}
      <StatCard
        icon={BanknotesIcon}
        label="Total Capital"
        value={`$${portfolio.total_capital.toFixed(2)}`}
        iconBgColor="from-green-500 to-emerald-500"
      />

      {/* Daily P&L */}
      <StatCard
        icon={portfolio.daily_pnl >= 0 ? ArrowTrendingUpIcon : ArrowTrendingDownIcon}
        label="Daily P&L"
        value={`${portfolio.daily_pnl >= 0 ? '+' : ''}$${portfolio.daily_pnl.toFixed(2)}`}
        change={profitLossChange}
        changeLabel="vs capital"
        iconBgColor={
          portfolio.daily_pnl >= 0
            ? 'from-green-500 to-emerald-500'
            : 'from-red-500 to-rose-500'
        }
      />

      {/* Drawdown */}
      <StatCard
        icon={ArrowTrendingDownIcon}
        label="Drawdown"
        value={`${(portfolio.drawdown_pct * 100).toFixed(2)}%`}
        iconBgColor="from-orange-500 to-amber-500"
      />

      {/* Open Positions */}
      <StatCard
        icon={ChartBarIcon}
        label="Open Positions"
        value={portfolio.open_positions_count}
        iconBgColor="from-blue-500 to-cyan-500"
      />
    </div>
  )
}
