'use client'
import { LiveStatus as Status } from '@/lib/types'
import { Badge } from '../ui/Badge'

export function LiveStatus({ data }: { data: Status }) {
  const rpcStatus = data.rpcLatency < 100 ? 'success' : data.rpcLatency < 300 ? 'warning' : 'error'
  const gasStatus = data.gasPrice < 80 ? 'success' : data.gasPrice < 120 ? 'warning' : 'error'
  
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 p-4 bg-gray-900 border border-gray-800 rounded">
      <Metric label="Bot Status" value={data.botActive ? '🟢 ACTIVE' : '🔴 STOPPED'} />
      <Metric label="Total PnL" value={`$${data.totalPnL.toFixed(2)}`} valueClass={data.totalPnL >= 0 ? 'text-green-400' : 'text-red-400'} />
      <Metric label="Daily PnL" value={`$${data.dailyPnL.toFixed(2)}`} valueClass={data.dailyPnL >= 0 ? 'text-green-400' : 'text-red-400'} />
      <Metric label="RPC Latency" value={`${data.rpcLatency}ms`} badge={<Badge variant={rpcStatus}>{rpcStatus.toUpperCase()}</Badge>} />
      <Metric label="Gas Price" value={`${data.gasPrice} gwei`} badge={<Badge variant={gasStatus}>{gasStatus.toUpperCase()}</Badge>} />
      <Metric label="Balance" value={`$${data.walletBalance.toFixed(2)}`} />
      <Metric label="Last Trade" value={`${Math.floor((Date.now()/1000 - data.lastTradeTimestamp)/60)}min ago`} />
    </div>
  )
}

function Metric({ label, value, valueClass = 'text-white', badge }: any) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500 font-mono uppercase">{label}</span>
      <span className={`text-lg font-bold font-mono ${valueClass}`}>{value}</span>
      {badge && <div className="mt-1">{badge}</div>}
    </div>
  )
}
