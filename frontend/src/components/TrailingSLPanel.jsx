import ScrollReveal from './ScrollReveal'

const TrailingSLPanel = ({ positions }) => {
  return (
    <ScrollReveal>
      <section className="border-sharp">
        {/* Header */}
        <div className="border-b border-ink p-12">
          <h3 className="font-display text-5xl text-ink mb-2">
            Trailing Stop-Loss
          </h3>
          <p className="font-mono text-sm text-muted">
            {positions.length} position{positions.length !== 1 ? 's' : ''} tracked
          </p>
        </div>

        {/* Content */}
        <div className="p-12">
          {positions.length > 0 ? (
            <div className="space-y-8">
              {positions.map((pos, idx) => (
                <div 
                  key={idx} 
                  className="border-b border-ink pb-8 last:border-0 transition-sharp hover-lift"
                >
                  <div className="grid grid-cols-4 gap-8">
                    {/* Position ID */}
                    <div>
                      <p className="font-mono text-xs text-muted mb-2 uppercase tracking-wide">
                        Position
                      </p>
                      <p className="font-mono text-sm text-ink">
                        {pos.position_id.slice(0, 8)}...
                      </p>
                    </div>

                    {/* Entry */}
                    <div>
                      <p className="font-mono text-xs text-muted mb-2 uppercase tracking-wide">
                        Entry
                      </p>
                      <p className="font-display text-2xl text-ink">
                        {pos.entry_price.toFixed(4)}
                      </p>
                    </div>

                    {/* Peak */}
                    <div>
                      <p className="font-mono text-xs text-muted mb-2 uppercase tracking-wide">
                        Peak
                      </p>
                      <p className="font-display text-2xl text-brand">
                        {pos.peak_price.toFixed(4)}
                      </p>
                    </div>

                    {/* Gain */}
                    <div className="text-right">
                      <p className="font-mono text-xs text-muted mb-2 uppercase tracking-wide">
                        Gain
                      </p>
                      <p className={`font-display text-2xl ${
                        pos.peak_gain_pct >= 0 ? 'text-brand' : 'text-ink'
                      }`}>
                        {pos.peak_gain_pct >= 0 ? '+' : ''}{pos.peak_gain_pct.toFixed(1)}%
                      </p>
                    </div>
                  </div>

                  {/* Status */}
                  <div className="mt-6">
                    <span className={`
                      inline-block px-4 py-2 font-mono text-xs uppercase tracking-wider
                      transition-sharp
                      ${
                        pos.trailing_active 
                          ? 'bg-brand text-paper' 
                          : 'border-sharp text-ink hover-border-brand'
                      }
                    `}>
                      {pos.trailing_active ? 'Active' : 'Watching'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-24 text-center">
              <p className="font-mono text-sm text-muted uppercase tracking-wide">
                No active positions
              </p>
              <p className="font-mono text-xs text-muted mt-2">
                Positions appear at +15% gain
              </p>
            </div>
          )}
        </div>
      </section>
    </ScrollReveal>
  )
}

export default TrailingSLPanel
