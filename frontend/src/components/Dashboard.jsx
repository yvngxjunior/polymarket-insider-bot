import { useState, useEffect } from 'react'
import MetricsGrid from './MetricsGrid'
import TrailingSLPanel from './TrailingSLPanel'
import WalletsPanel from './WalletsPanel'
import LiveStream from './LiveStream'
import { fetchAPI } from '../utils/api'

const Dashboard = ({ stats }) => {
  const [portfolio, setPortfolio] = useState(null)
  const [trailingPositions, setTrailingPositions] = useState([])
  const [wallets, setWallets] = useState([])

  useEffect(() => {
    const loadData = async () => {
      try {
        const [portfolioData, trailingData, walletsData] = await Promise.all([
          fetchAPI('/portfolio'),
          fetchAPI('/features/trailing-sl/status'),
          fetchAPI('/wallets'),
        ])
        
        setPortfolio(portfolioData)
        setTrailingPositions(trailingData.positions || [])
        setWallets(walletsData.active_wallets || [])
      } catch (error) {
        console.error('Failed to load dashboard data:', error)
      }
    }

    loadData()
    const interval = setInterval(loadData, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-screen bg-paper px-8 py-16">
      {/* Header - Asymmetric */}
      <header className="mb-40 animate-fade-in-up">
        <div className="border-b border-ink pb-8">
          <h1 className="font-display text-display text-ink mb-2">
            PolyInsider
          </h1>
          <p className="font-mono text-sm text-muted tracking-wide uppercase">
            Real-time Trading Intelligence
          </p>
        </div>
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
    </div>
  )
}

export default Dashboard
