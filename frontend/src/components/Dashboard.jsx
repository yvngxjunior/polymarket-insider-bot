import { useState, useEffect } from 'react'
import { Activity, TrendingUp, Wallet, AlertCircle } from 'lucide-react'
import StatsCard from './StatsCard'
import TrailingSLChart from './TrailingSLChart'
import PositionsTable from './PositionsTable'
import WalletsTable from './WalletsTable'
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
    const interval = setInterval(loadData, 5000) // Refresh every 5s
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-screen bg-slate-900 p-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-white mb-2 flex items-center gap-3">
          <Activity className="text-indigo-500" size={40} />
          PolyInsider Dashboard
        </h1>
        <p className="text-slate-400 text-lg">Real-time bot monitoring with Trailing SL</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatsCard
          title="Total Capital"
          value={`$${portfolio?.total_capital?.toFixed(2) || '0.00'}`}
          icon={<Wallet className="text-indigo-500" />}
          trend={portfolio?.return_pct}
        />
        <StatsCard
          title="Total PnL"
          value={`$${portfolio?.total_pnl?.toFixed(2) || '0.00'}`}
          icon={<TrendingUp className={portfolio?.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'} />}
          trend={portfolio?.return_pct}
          positive={portfolio?.total_pnl >= 0}
        />
        <StatsCard
          title="Trailing SL Active"
          value={stats?.trailing_sl?.tracked_positions || 0}
          icon={<Activity className="text-yellow-500" />}
          subtitle="positions tracked"
        />
        <StatsCard
          title="Auto-Discovered"
          value={stats?.wallet_discovery?.auto_discovered_wallets || 0}
          icon={<AlertCircle className="text-purple-500" />}
          subtitle="top traders"
        />
      </div>

      {/* Trailing SL Chart */}
      <div className="mb-8">
        <TrailingSLChart positions={trailingPositions} />
      </div>

      {/* Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <PositionsTable positions={trailingPositions} />
        <WalletsTable wallets={wallets.slice(0, 10)} />
      </div>
    </div>
  )
}

export default Dashboard
