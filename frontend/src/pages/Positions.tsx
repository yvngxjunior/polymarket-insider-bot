import PositionsTable from '../components/PositionsTable'
import { usePositions } from '../hooks/useApi'

export default function Positions() {
  const { data } = usePositions()

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Active Positions</h1>
        <p className="text-gray-500 mt-1">
          {data?.total_count || 0} open position{data?.total_count !== 1 ? 's' : ''} •{' '}
          ${data?.total_capital_deployed.toFixed(2) || '0.00'} deployed
        </p>
      </div>

      {/* Positions Table */}
      <PositionsTable />
    </div>
  )
}
