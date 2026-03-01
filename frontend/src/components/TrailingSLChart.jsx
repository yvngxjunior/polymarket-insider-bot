import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts'
import { Activity } from 'lucide-react'

const TrailingSLChart = ({ positions }) => {
  if (!positions || positions.length === 0) {
    return (
      <div className="card">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
          <Activity className="text-yellow-500" />
          Trailing Stop-Loss Tracker
        </h2>
        <div className="text-center py-12 text-slate-400">
          <p>No active trailing positions yet</p>
          <p className="text-sm mt-2">Positions will appear here once they reach +15% gain</p>
        </div>
      </div>
    )
  }

  // Prépare les données pour le chart
  const chartData = positions.map((pos, idx) => ({
    position: `Pos ${idx + 1}`,
    entry: pos.entry_price,
    peak: pos.peak_price,
    gain_pct: pos.peak_gain_pct,
  }))

  return (
    <div className="card">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-2">
          <Activity className="text-yellow-500" />
          Trailing Stop-Loss Tracker
        </h2>
        <p className="text-slate-400 text-sm">
          {positions.length} position{positions.length > 1 ? 's' : ''} with active trailing stop-loss
        </p>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis 
            dataKey="position" 
            stroke="#94a3b8"
            style={{ fontSize: '12px' }}
          />
          <YAxis 
            stroke="#94a3b8"
            style={{ fontSize: '12px' }}
            domain={['dataMin - 0.05', 'dataMax + 0.05']}
          />
          <Tooltip 
            contentStyle={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '0.5rem',
              color: '#f1f5f9',
            }}
            formatter={(value, name) => {
              if (name === 'gain_pct') return [`${value.toFixed(2)}%`, 'Gain']
              return [value.toFixed(4), name === 'entry' ? 'Entry' : 'Peak']
            }}
          />
          <Legend 
            wrapperStyle={{ color: '#94a3b8', fontSize: '12px' }}
          />
          <ReferenceLine 
            y={0.15} 
            stroke="#f59e0b" 
            strokeDasharray="3 3" 
            label={{ value: '+15% Activation', fill: '#f59e0b', fontSize: 10 }}
          />
          <Line 
            type="monotone" 
            dataKey="entry" 
            stroke="#6366f1" 
            strokeWidth={2}
            dot={{ fill: '#6366f1', r: 4 }}
            name="Entry Price"
          />
          <Line 
            type="monotone" 
            dataKey="peak" 
            stroke="#10b981" 
            strokeWidth={2}
            dot={{ fill: '#10b981', r: 4 }}
            name="Peak Price"
          />
        </LineChart>
      </ResponsiveContainer>

      {/* Legend explicatif */}
      <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-indigo-500"></div>
          <span className="text-slate-300">Entry Price - Position opening</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-green-500"></div>
          <span className="text-slate-300">Peak Price - Highest reached</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
          <span className="text-slate-300">Trailing activates @ +15%</span>
        </div>
      </div>
    </div>
  )
}

export default TrailingSLChart
