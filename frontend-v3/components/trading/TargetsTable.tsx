'use client'
import { Target } from '@/lib/types'
import { toggleTarget } from '@/lib/api'
import { useState } from 'react'

export function TargetsTable({ targets: initialTargets }: { targets: Target[] }) {
  const [targets, setTargets] = useState(initialTargets)
  
  const handleToggle = async (address: string) => {
    const target = targets.find(t => t.address === address)!
    await toggleTarget(address, !target.isActive)
    setTargets(prev => prev.map(t => t.address === address ? {...t, isActive: !t.isActive} : t))
  }
  
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm font-mono">
        <thead className="bg-gray-900 border-b border-gray-800">
          <tr className="text-left text-gray-500">
            <th className="p-3">Wallet</th>
            <th className="p-3">Winrate</th>
            <th className="p-3">ROI 7d</th>
            <th className="p-3">Vol 24h</th>
            <th className="p-3">Avg Size</th>
            <th className="p-3">Last Trade</th>
            <th className="p-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {targets.map(t => (
            <tr key={t.address} className="border-b border-gray-800 hover:bg-gray-900/50">
              <td className="p-3">
                <div className="flex items-center gap-2">
                  <span className="text-blue-400">{t.name || `${t.address.slice(0,6)}...${t.address.slice(-4)}`}</span>
                  {t.riskAlert && <span className="text-red-400">⚠️</span>}
                </div>
              </td>
              <td className="p-3">{t.winrate.toFixed(1)}%</td>
              <td className={`p-3 ${t.roi7d >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {t.roi7d >= 0 ? '+' : ''}{t.roi7d.toFixed(1)}%
              </td>
              <td className="p-3">${t.volume24h.toLocaleString()}</td>
              <td className="p-3">${t.avgPositionSize}</td>
              <td className="p-3">{Math.floor(t.lastTradeAge/60)}min</td>
              <td className="p-3">
                <button 
                  onClick={() => handleToggle(t.address)}
                  className={`px-3 py-1 rounded font-bold ${t.isActive ? 'bg-green-500/20 text-green-400' : 'bg-gray-700 text-gray-400'}`}
                >
                  {t.isActive ? 'ON' : 'OFF'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
