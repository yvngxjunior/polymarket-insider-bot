import { useState, useEffect } from 'react'
import { Settings } from 'lucide-react'
import MetricsGrid from './MetricsGrid'
import TrailingSLPanel from './TrailingSLPanel'
import WalletsPanel from './WalletsPanel'
import LiveStream from './LiveStream'
import SettingsSidebar from './SettingsSidebar'
import { fetchAPI } from '../utils/api'

const Dashboard = ({ stats }) => {
  const [portfolio, setPortfolio] = useState(null)
  const [trailingPositions, setTrailingPositions] = useState([])
  const [wallets, setWallets] = useState([])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [config, setConfig] = useState(null)

  useEffect(() => {
    const loadData = async () => {
      try {
        const [portfolioData, trailingData, walletsData, settingsData, trailingConfig] = await Promise.all([
          fetchAPI('/portfolio'),
          fetchAPI('/features/trailing-sl/status'),
          fetchAPI('/wallets'),
          fetchAPI('/settings'),
          fetchAPI('/features/trailing-sl/config'),
        ])
        
        setPortfolio(portfolioData)
        setTrailingPositions(trailingData.positions || [])
        setWallets(walletsData.active_wallets || [])
        
        // Merge settings into config
        setConfig({
          dry_run: settingsData.dry_run || false,
          max_trade_amount: settingsData.max_trade_amount || 100,
          min_win_rate: settingsData.min_win_rate || 0.60,
          min_wallet_score: 0.70,
          trailing_sl_enabled: true,
          trailing_sl_activation: trailingConfig.activation_gain_pct || 0.15,
          trailing_sl_distance: trailingConfig.trail_distance_pct || 0.05,
          wallet_discovery_enabled: true,
        })
      } catch (error) {
        console.error('Failed to load dashboard data:', error)
      }
    }

    loadData()
    const interval = setInterval(loadData, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleSaveConfig = async (newConfig) => {
    try {
      // Update bot settings (dry_run, max_trade_amount, etc.)
      await fetchAPI('/settings', {
        method: 'POST',
        body: JSON.stringify({
          dry_run: newConfig.dry_run,
          max_trade_amount: newConfig.max_trade_amount,
          min_win_rate: newConfig.min_win_rate,
        }),
      })
      
      // Update trailing SL config
      await fetchAPI('/features/trailing-sl/config', {
        method: 'POST',
        body: JSON.stringify({
          activation_gain_pct: newConfig.trailing_sl_activation,
          trail_distance_pct: newConfig.trailing_sl_distance,
          min_locked_profit_pct: 0.10, // default
        }),
      })
      
      console.log('Configuration saved:', newConfig)
      // Update local config state
      setConfig(newConfig)
      
      // TODO: Add success toast notification
    } catch (error) {
      console.error('Failed to save config:', error)
      // TODO: Add error toast notification
    }
  }

  return (
    <div className="min-h-screen bg-paper px-8 py-16">
      {/* Header - Asymmetric */}
      <header className="mb-40 animate-fade-in-up">
        <div className="border-b border-ink pb-8 flex items-end justify-between">
          <div>
            <h1 className="font-display text-display text-ink mb-2">
              PolyInsider
            </h1>
            <p className="font-mono text-sm text-muted tracking-wide uppercase">
              Real-time Trading Intelligence
            </p>
          </div>
          
          {/* Settings Button */}
          <button
            onClick={() => setSettingsOpen(true)}
            className="
              flex items-center gap-3 px-6 py-4 border-sharp 
              hover-border-brand transition-border
              font-mono text-sm uppercase tracking-wider
            "
          >
            <Settings size={18} />
            Settings
          </button>
        </div>

        {/* Dry Run Banner */}
        {config?.dry_run && (
          <div className="mt-6 p-4 border-brand bg-brand/5 animate-pulse">
            <p className="font-mono text-sm text-brand uppercase tracking-wider text-center">
              🧪 DRY RUN MODE ACTIVE — No real trades executed
            </p>
          </div>
        )}
      </header>

      {/* Metrics - Grid System */}
      <MetricsGrid 
        portfolio={portfolio} 
        stats={stats} 
      />

      {/* Asymmetric Two-Column */}
      <div className="grid grid-cols-12 gap-16 mb-40">
        {/* 70% - Trailing SL */}
        <div className="col-span-7 animate-fade-in-up stagger-3">
          <TrailingSLPanel positions={trailingPositions} />
        </div>

        {/* 30% - Live Stream */}
        <div className="col-span-5 animate-fade-in-up stagger-4">
          <LiveStream />
        </div>
      </div>

      {/* Full Width - Wallets */}
      <div className="animate-fade-in-up stagger-5">
        <WalletsPanel wallets={wallets} />
      </div>

      {/* Footer */}
      <footer className="mt-40 pt-16 border-t border-ink">
        <div className="flex justify-between items-center">
          <p className="font-mono text-xs text-muted uppercase tracking-wider">
            v3.2.0 — Trading Bot
          </p>
          <p className="font-mono text-xs text-muted">
            Last update: {new Date().toLocaleTimeString()}
          </p>
        </div>
      </footer>

      {/* Settings Sidebar */}
      <SettingsSidebar 
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        currentConfig={config}
        onSave={handleSaveConfig}
      />
    </div>
  )
}

export default Dashboard
