import PortfolioOverview from '../components/PortfolioOverview'
import PositionsTable from '../components/PositionsTable'

export default function Dashboard() {
  return (
    <div className="space-y-6">
      {/* Page Title */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Real-time portfolio & position tracking</p>
      </div>

      {/* Portfolio Overview */}
      <section>
        <PortfolioOverview />
      </section>

      {/* Active Positions */}
      <section>
        <div className="mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Active Positions</h2>
          <p className="text-sm text-gray-500 mt-1">Currently open trades with TP/SL tracking</p>
        </div>
        <PositionsTable />
      </section>
    </div>
  )
}
