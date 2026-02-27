'use client'
import { LiveStatus as Status } from '@/lib/types'
import { Badge } from '../ui/Badge'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useEffect, useState } from 'react'

export function LiveStatus({ data: initialData }: { data: Status }) {
  const [data, setData] = useState(initialData)
  const { data: wsData, isConnected } = useWebSocket('ws://localhost:8000/ws/dashboard')
  
  useEffect(() => {
    if (wsData && wsData.liveStatus) {
      setData(wsData.liveStatus)
    }
  }, [wsData])
  
  const rpcStatus = data.rpcLatency < 100 ? 'success' : data.rpcLatency < 300 ? 'warning' : 'error'
  const gasStatus = data.gasPrice < 80 ? 'success' : data.gasPrice < 120 ? 'warning' : 'error'
  
  return (
    <div className="relative">
      {/* WebSocket Status Indicator */}
      <div className="absolute -top-2 -right-2 flex items-center gap-2 text-xs">
        <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
        <span className="text-gray-500">{isConnected ? 'Live' : 'Offline'}</span>
      </div>
      
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 p-4 bg-gray-900 border border-gray-800 rounded">
        <Metric label="Bot Status" value={data.botActive ? '🟢 ACTIVE' : '🔴 STOPPED'} />
        <Metric 
          label="Total PnL" 
          value={`$${data.totalPnL.toFixed(2)}`} 
          valueClass={data.totalPnL >= 0 ? 'text-green-400' : 'text-red-400'}
          animate={true}
        />
        <Metric 
          label="Daily PnL" 
          value={`$${data.dailyPnL.toFixed(2)}`} 
          valueClass={data.dailyPnL >= 0 ? 'text-green-400' : 'text-red-400'}
          animate={true}
        />
        <Metric 
          label="RPC Latency" 
          value={`${data.rpcLatency}ms`} 
          badge={<Badge variant={rpcStatus}>{rpcStatus.toUpperCase()}</Badge>}
          animate={true}
        />
        <Metric 
          label="Gas Price" 
          value={`${data.gasPrice} gwei`} 
          badge={<Badge variant={gasStatus}>{gasStatus.toUpperCase()}</Badge>}
          animate={true}
        />
        <Metric label="Balance" value={`$${data.walletBalance.toFixed(2)}`} animate={true} />
        <Metric label="Last Trade" value={`${Math.floor((Date.now()/1000 - data.lastTradeTimestamp)/60)}min ago`} />
      </div>
    </div>
  )
}

function Metric({ label, value, valueClass = 'text-white', badge, animate = false }: any) {
  const [flash, setFlash] = useState(false)
  
  useEffect(() => {
    if (animate) {
      setFlash(true)
      const timer = setTimeout(() => setFlash(false), 300)
      return () => clearTimeout(timer)
    }
  }, [value, animate])
  
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500 font-mono uppercase">{label}</span>
      <span 
        className={`text-lg font-bold font-mono ${valueClass} transition-all ${
          flash ? 'scale-110 text-blue-400' : ''
        }`}
      >
        {value}
      </span>
      {badge && <div className="mt-1">{badge}</div>}
    </div>
  )
}
