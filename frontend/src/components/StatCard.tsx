import clsx from 'clsx'

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number
  change?: number
  changeLabel?: string
  iconBgColor?: string
}

export default function StatCard({
  icon: Icon,
  label,
  value,
  change,
  changeLabel,
  iconBgColor = 'from-violet-500 to-indigo-500',
}: StatCardProps) {
  return (
    <div className="glass-card glass-card-hover">
      {/* Icon */}
      <div
        className={clsx(
          'w-12 h-12 rounded-xl flex items-center justify-center mb-4',
          'bg-gradient-to-br',
          iconBgColor
        )}
      >
        <Icon className="w-6 h-6 text-white" />
      </div>

      {/* Label */}
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
        {label}
      </div>

      {/* Value */}
      <div className="stat-value animate-count-up">{value}</div>

      {/* Change */}
      {change !== undefined && (
        <div className="mt-2 flex items-center gap-1">
          <span
            className={clsx(
              'text-sm font-medium',
              change >= 0 ? 'profit-text' : 'loss-text'
            )}
          >
            {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(2)}%
          </span>
          {changeLabel && (
            <span className="text-xs text-gray-500">{changeLabel}</span>
          )}
        </div>
      )}
    </div>
  )
}
