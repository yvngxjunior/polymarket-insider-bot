'use client'
import { Position } from '@/lib/types'
import { cashOutPosition } from '@/lib/api'

export function OrderBook({ positions }: { positions: Position[] }) {
  const handleCashOut = async (id: string) => {
    if (!confirm('Confirm cash out this position?')) return
    await cashOutPosition(id)
    window.location.reload()
  }
  
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm font-mono">
        <thead className="bg-gray-900 border-b border-gray-800">
          <tr className="text-left text-gray-500">
            <th className="p-3">Market</th>
            <th className="p-3">Side</th>
            <th className="p-3">Entry</th>
            <th className="p-3">Current</th>
            <th className="p-3">P/L</th>
            <th className="p-3">Prob</th>
            <th className="p-3">Age</th>
            <th className="p-3">Actions</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(p => {
            const pnlClass = p.pnl >= 0 ? 'text-green-400' : 'text-red-400'
            const bgClass = p.pnl < -20 ? 'bg-red-500/10' : ''
            return (
              <tr key={p.id} className={`border-b border-gray-800 hover:bg-gray-900/50 ${bgClass}`}>
                <td className="p-3 max-w-xs truncate">{p.market}</td>
                <td className="p-3">
                  <span className={p.side === 'YES' ? 'text-green-400' : 'text-red-400'}>{p.side}</span>
                </td>
                <td className="p-3">${p.entryPrice.toFixed(2)}</td>
                <td className="p-3">${p.currentPrice.toFixed(2)}</td>
                <td className={`p-3 font-bold ${pnlClass}`}>
                  {p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(2)}
                </td>
                <td className="p-3">{(p.probability * 100).toFixed(0)}%</td>
                <td className="p-3">{Math.floor(p.ageSeconds/3600)}h</td>
                <td className="p-3">
                  <button 
                    onClick={() => handleCashOut(p.id)}
                    disabled={!p.canCashOut}
                    className="px-3 py-1 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 disabled:opacity-50"
                  >
                    {p.pnl < -20 ? '🚨 PANIC' : 'Cash Out'}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
