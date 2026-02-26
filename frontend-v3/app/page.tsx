import { fetchDashboard } from '@/lib/api'
import { LiveStatus } from '@/components/trading/LiveStatus'
import { TargetsTable } from '@/components/trading/TargetsTable'
import { OrderBook } from '@/components/trading/OrderBook'
import { AlertFeed } from '@/components/trading/AlertFeed'
import { EmergencyControls } from '@/components/trading/EmergencyControls'

export default async function Dashboard() {
  const data = await fetchDashboard()
  
  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold font-mono">⚡ PolyInsider Cockpit</h1>
        <EmergencyControls />
      </div>
      
      <LiveStatus data={data.liveStatus} />
      
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <section>
            <h2 className="text-xl font-bold mb-3">🎯 Copy Targets</h2>
            <div className="bg-gray-900 border border-gray-800 rounded overflow-hidden">
              <TargetsTable targets={data.targets} />
            </div>
          </section>
          
          <section>
            <h2 className="text-xl font-bold mb-3">📊 Active Positions</h2>
            <div className="bg-gray-900 border border-gray-800 rounded overflow-hidden">
              <OrderBook positions={data.positions} />
            </div>
          </section>
        </div>
        
        <div className="space-y-6">
          <AlertFeed alerts={data.alerts} />
        </div>
      </div>
    </div>
  )
}
