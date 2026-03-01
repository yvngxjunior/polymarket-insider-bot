import { useState } from 'react'
import { X, Settings, Save } from 'lucide-react'

const SettingsSidebar = ({ isOpen, onClose, currentConfig, onSave }) => {
  const [config, setConfig] = useState(currentConfig || {
    dry_run: true,
    max_trade_amount: 100,
    min_win_rate: 0.60,
    min_wallet_score: 0.70,
    trailing_sl_enabled: true,
    trailing_sl_activation: 0.15,
    trailing_sl_distance: 0.05,
    wallet_discovery_enabled: true,
  })

  const handleChange = (key, value) => {
    setConfig({ ...config, [key]: value })
  }

  const handleSave = async () => {
    await onSave(config)
    onClose()
  }

  if (!isOpen) return null

  return (
    <>
      {/* Overlay */}
      <div 
        className="fixed inset-0 bg-ink/20 z-40 animate-fade-in-up"
        onClick={onClose}
      />

      {/* Sidebar */}
      <aside className="
        fixed right-0 top-0 h-screen w-[600px] bg-paper border-l border-sharp
        z-50 overflow-y-auto animate-slide-in
      ">
        {/* Header */}
        <div className="border-b border-ink p-12 flex items-center justify-between sticky top-0 bg-paper">
          <div className="flex items-center gap-4">
            <Settings className="text-brand" size={32} />
            <h2 className="font-display text-4xl text-ink">Settings</h2>
          </div>
          <button 
            onClick={onClose}
            className="p-3 border-sharp hover-border-brand transition-border"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-12 space-y-12">
          {/* Trading Section */}
          <section>
            <h3 className="font-display text-2xl text-ink mb-6 pb-3 border-b border-ink">
              Trading
            </h3>
            
            <div className="space-y-6">
              {/* Dry Run */}
              <div>
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input 
                    type="checkbox"
                    checked={config.dry_run}
                    onChange={(e) => handleChange('dry_run', e.target.checked)}
                    className="w-5 h-5 border-sharp"
                  />
                  <div>
                    <p className="font-mono text-sm text-ink group-hover:text-brand transition-sharp">
                      Dry Run Mode
                    </p>
                    <p className="font-mono text-xs text-muted">
                      Test without real trades
                    </p>
                  </div>
                </label>
              </div>

              {/* Max Trade Amount */}
              <div>
                <label className="block">
                  <p className="font-mono text-xs text-muted uppercase tracking-wide mb-2">
                    Max Trade Amount ($)
                  </p>
                  <input 
                    type="number"
                    value={config.max_trade_amount}
                    onChange={(e) => handleChange('max_trade_amount', parseFloat(e.target.value))}
                    className="w-full p-4 border-sharp font-mono text-ink focus:border-brand outline-none transition-border"
                  />
                </label>
              </div>

              {/* Min Win Rate */}
              <div>
                <label className="block">
                  <p className="font-mono text-xs text-muted uppercase tracking-wide mb-2">
                    Min Win Rate ({(config.min_win_rate * 100).toFixed(0)}%)
                  </p>
                  <input 
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={config.min_win_rate}
                    onChange={(e) => handleChange('min_win_rate', parseFloat(e.target.value))}
                    className="w-full"
                  />
                </label>
              </div>

              {/* Min Wallet Score */}
              <div>
                <label className="block">
                  <p className="font-mono text-xs text-muted uppercase tracking-wide mb-2">
                    Min Wallet Score ({(config.min_wallet_score * 100).toFixed(0)})
                  </p>
                  <input 
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={config.min_wallet_score}
                    onChange={(e) => handleChange('min_wallet_score', parseFloat(e.target.value))}
                    className="w-full"
                  />
                </label>
              </div>
            </div>
          </section>

          {/* Trailing Stop-Loss Section */}
          <section>
            <h3 className="font-display text-2xl text-ink mb-6 pb-3 border-b border-ink">
              Trailing Stop-Loss
            </h3>
            
            <div className="space-y-6">
              {/* Enable Trailing SL */}
              <div>
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input 
                    type="checkbox"
                    checked={config.trailing_sl_enabled}
                    onChange={(e) => handleChange('trailing_sl_enabled', e.target.checked)}
                    className="w-5 h-5 border-sharp"
                  />
                  <div>
                    <p className="font-mono text-sm text-ink group-hover:text-brand transition-sharp">
                      Enable Trailing SL
                    </p>
                    <p className="font-mono text-xs text-muted">
                      Auto lock profits at peak
                    </p>
                  </div>
                </label>
              </div>

              {config.trailing_sl_enabled && (
                <>
                  {/* Activation Threshold */}
                  <div>
                    <label className="block">
                      <p className="font-mono text-xs text-muted uppercase tracking-wide mb-2">
                        Activation Gain (+{(config.trailing_sl_activation * 100).toFixed(0)}%)
                      </p>
                      <input 
                        type="range"
                        min="0.05"
                        max="0.5"
                        step="0.05"
                        value={config.trailing_sl_activation}
                        onChange={(e) => handleChange('trailing_sl_activation', parseFloat(e.target.value))}
                        className="w-full"
                      />
                    </label>
                  </div>

                  {/* Trail Distance */}
                  <div>
                    <label className="block">
                      <p className="font-mono text-xs text-muted uppercase tracking-wide mb-2">
                        Trail Distance ({(config.trailing_sl_distance * 100).toFixed(0)}%)
                      </p>
                      <input 
                        type="range"
                        min="0.02"
                        max="0.2"
                        step="0.01"
                        value={config.trailing_sl_distance}
                        onChange={(e) => handleChange('trailing_sl_distance', parseFloat(e.target.value))}
                        className="w-full"
                      />
                    </label>
                  </div>
                </>
              )}
            </div>
          </section>

          {/* Wallet Discovery Section */}
          <section>
            <h3 className="font-display text-2xl text-ink mb-6 pb-3 border-b border-ink">
              Wallet Discovery
            </h3>
            
            <div className="space-y-6">
              {/* Enable Discovery */}
              <div>
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input 
                    type="checkbox"
                    checked={config.wallet_discovery_enabled}
                    onChange={(e) => handleChange('wallet_discovery_enabled', e.target.checked)}
                    className="w-5 h-5 border-sharp"
                  />
                  <div>
                    <p className="font-mono text-sm text-ink group-hover:text-brand transition-sharp">
                      Auto-Discovery
                    </p>
                    <p className="font-mono text-xs text-muted">
                      Find top traders every 24h
                    </p>
                  </div>
                </label>
              </div>
            </div>
          </section>
        </div>

        {/* Footer - Save Button */}
        <div className="border-t border-ink p-12 sticky bottom-0 bg-paper">
          <button 
            onClick={handleSave}
            className="w-full bg-brand text-paper py-4 px-8 font-mono text-sm uppercase tracking-wider hover:bg-ink transition-sharp flex items-center justify-center gap-3"
          >
            <Save size={18} />
            Save Configuration
          </button>
        </div>
      </aside>
    </>
  )
}

export default SettingsSidebar
