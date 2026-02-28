import ScrollReveal from './ScrollReveal'

const WalletsPanel = ({ wallets }) => {
  const topWallets = wallets.slice(0, 12)
  const avgScore = wallets.length > 0 
    ? (wallets.reduce((sum, w) => sum + w.score, 0) / wallets.length * 100).toFixed(0)
    : '0'

  return (
    <ScrollReveal>
      <section className="border-sharp">
        {/* Header */}
        <div className="border-b border-ink p-12">
          <div className="flex items-end justify-between">
            <div>
              <h3 className="font-display text-5xl text-ink mb-2">
                Tracked Wallets
              </h3>
              <p className="font-mono text-sm text-muted">
                {wallets.length} traders monitored
              </p>
            </div>
            <div className="text-right">
              <p className="font-mono text-xs text-muted uppercase tracking-wide mb-1">
                Avg Score
              </p>
              <p className="font-display text-4xl text-brand">
                {avgScore}
              </p>
            </div>
          </div>
        </div>

        {/* Grid of Wallets */}
        <div className="p-12">
          {topWallets.length > 0 ? (
            <div className="grid grid-cols-3 gap-8">
              {topWallets.map((wallet, idx) => (
                <div 
                  key={idx} 
                  className="
                    border-sharp p-8 
                    transition-border hover-border-brand hover-border-thick hover-scale
                    animate-slide-in
                  "
                  style={{ animationDelay: `${idx * 0.05}s` }}
                >
                  {/* Address */}
                  <div className="mb-6">
                    <p className="font-mono text-xs text-ink">
                      {wallet.address.slice(0, 6)}...{wallet.address.slice(-4)}
                    </p>
                  </div>

                  {/* Score - BIG */}
                  <div className="mb-6">
                    <p className="font-display text-5xl text-brand">
                      {(wallet.score * 100).toFixed(0)}
                    </p>
                  </div>

                  {/* Stats Grid */}
                  <div className="grid grid-cols-2 gap-4 pt-6 border-t border-ink">
                    <div>
                      <p className="font-mono text-xs text-muted mb-1 uppercase tracking-wide">
                        Win Rate
                      </p>
                      <p className="font-mono text-sm text-ink">
                        {(wallet.win_rate * 100).toFixed(0)}%
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-xs text-muted mb-1 uppercase tracking-wide">
                        Trades
                      </p>
                      <p className="font-mono text-sm text-ink">
                        {wallet.total_trades}
                      </p>
                    </div>
                  </div>

                  {/* Whitelist Badge */}
                  {wallet.is_whitelisted && (
                    <div className="mt-4">
                      <span className="inline-block bg-brand text-paper px-3 py-1 font-mono text-xs uppercase tracking-wider">
                        Whitelisted
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="py-24 text-center">
              <p className="font-mono text-sm text-muted uppercase tracking-wide">
                No wallets tracked
              </p>
            </div>
          )}
        </div>
      </section>
    </ScrollReveal>
  )
}

export default WalletsPanel
