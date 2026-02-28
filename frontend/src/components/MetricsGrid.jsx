import { useEffect, useState } from 'react'

const MetricsGrid = ({ portfolio, stats }) => {
  const [prevValues, setPrevValues] = useState({})
  const [updatedIndices, setUpdatedIndices] = useState(new Set())

  const metrics = [
    {
      label: 'Capital',
      value: `$${portfolio?.total_capital?.toFixed(0) || '0'}`,
      sublabel: portfolio?.return_pct ? `${portfolio.return_pct >= 0 ? '+' : ''}${portfolio.return_pct.toFixed(1)}%` : null,
    },
    {
      label: 'P&L',
      value: `${portfolio?.total_pnl >= 0 ? '+' : ''}$${portfolio?.total_pnl?.toFixed(0) || '0'}`,
      sublabel: null,
      accent: portfolio?.total_pnl >= 0,
    },
    {
      label: 'Trailing',
      value: `${stats?.trailing_sl?.tracked_positions || 0}`,
      sublabel: 'Active Positions',
    },
    {
      label: 'Discovery',
      value: `${stats?.wallet_discovery?.auto_discovered_wallets || 0}`,
      sublabel: 'Top Traders',
    },
  ]

  // Detect value changes
  useEffect(() => {
    const newUpdated = new Set()
    metrics.forEach((metric, idx) => {
      if (prevValues[idx] !== undefined && prevValues[idx] !== metric.value) {
        newUpdated.add(idx)
      }
    })
    
    if (newUpdated.size > 0) {
      setUpdatedIndices(newUpdated)
      setTimeout(() => setUpdatedIndices(new Set()), 300)
    }

    const newPrevValues = {}
    metrics.forEach((metric, idx) => {
      newPrevValues[idx] = metric.value
    })
    setPrevValues(newPrevValues)
  }, [portfolio, stats])

  return (
    <section className="mb-40">
      <div className="grid grid-cols-4 gap-16">
        {metrics.map((metric, idx) => (
          <div 
            key={idx} 
            className={`
              border-sharp p-12 
              transition-border hover-border-thick hover-border-brand hover-lift
              animate-fade-in-up stagger-${idx + 1}
            `}
          >
            {/* Label */}
            <div className="mb-8">
              <p className="font-mono text-xs text-muted uppercase tracking-widest">
                {metric.label}
              </p>
            </div>

            {/* Value - MASSIVE with animation */}
            <div className="mb-4">
              <h2 className={`
                font-display text-6xl leading-none
                ${metric.accent ? 'text-brand' : 'text-ink'}
                ${updatedIndices.has(idx) ? 'animate-number-tick' : ''}
              `}>
                {metric.value}
              </h2>
            </div>

            {/* Sublabel */}
            {metric.sublabel && (
              <p className="font-mono text-xs text-muted">
                {metric.sublabel}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}

export default MetricsGrid
