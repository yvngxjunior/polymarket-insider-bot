import { TrendingUp, TrendingDown, Activity } from 'lucide-react'

const PositionsTable = ({ positions }) => {
  return (
    <div className="card">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
        <Activity className="text-green-500" />
        Active Trailing Positions
      </h2>
      
      {positions && positions.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left py-3 px-2 text-slate-400 font-medium">Position</th>
                <th className="text-right py-3 px-2 text-slate-400 font-medium">Entry</th>
                <th className="text-right py-3 px-2 text-slate-400 font-medium">Peak</th>
                <th className="text-right py-3 px-2 text-slate-400 font-medium">Gain</th>
                <th className="text-center py-3 px-2 text-slate-400 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos, idx) => (
                <tr key={idx} className="border-b border-slate-800 hover:bg-slate-800/50 transition">
                  <td className="py-3 px-2 text-slate-300 font-mono text-xs">
                    {pos.position_id.slice(0, 12)}...
                  </td>
                  <td className="text-right py-3 px-2 text-slate-300">
                    {pos.entry_price.toFixed(4)}
                  </td>
                  <td className="text-right py-3 px-2 text-green-400 font-semibold">
                    {pos.peak_price.toFixed(4)}
                  </td>
                  <td className="text-right py-3 px-2">
                    <span className={`font-semibold ${
                      pos.peak_gain_pct >= 0 ? 'text-green-500' : 'text-red-500'
                    }`}>
                      {pos.peak_gain_pct >= 0 ? '+' : ''}{pos.peak_gain_pct.toFixed(2)}%
                    </span>
                  </td>
                  <td className="text-center py-3 px-2">
                    {pos.trailing_active ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded-full text-xs">
                        <TrendingUp size={12} />
                        Trailing
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-slate-700 text-slate-400 rounded-full text-xs">
                        <Activity size={12} />
                        Watching
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-8 text-slate-400">
          <p>No active positions</p>
        </div>
      )}
    </div>
  )
}

export default PositionsTable
