import { useState, useEffect, useRef } from 'react'
import { Activity, TrendingUp, TrendingDown, Clock } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

const LiveTradesStream = () => {
  const [trades, setTrades] = useState([])
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    // WebSocket connection
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8001'
    const ws = new WebSocket(`${wsUrl}/ws/trades`)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[WS] Connected to live trades stream')
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'trades_update' && data.trades) {
          setTrades(data.trades)
        }
      } catch (error) {
        console.error('[WS] Failed to parse message:', error)
      }
    }

    ws.onerror = (error) => {
      console.error('[WS] Connection error:', error)
      setIsConnected(false)
    }

    ws.onclose = () => {
      console.log('[WS] Connection closed')
      setIsConnected(false)
    }

    // Cleanup on unmount
    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    }
  }, [])

  return (
    <div className="card">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="text-blue-500" />
          Live Trades Stream
        </h2>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
          }`}></div>
          <span className="text-sm text-slate-400">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {trades.length > 0 ? (
        <div className="space-y-3">
          {trades.map((trade, idx) => (
            <div 
              key={idx} 
              className="bg-slate-800/50 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  {trade.side === 'BUY' ? (
                    <TrendingUp className="text-green-500" size={18} />
                  ) : (
                    <TrendingDown className="text-red-500" size={18} />
                  )}
                  <span className={`font-semibold ${
                    trade.side === 'BUY' ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {trade.side}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-xs text-slate-500">
                  <Clock size={12} />
                  {trade.timestamp && formatDistanceToNow(new Date(trade.timestamp), { addSuffix: true })}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-slate-500 text-xs mb-1">Token ID</p>
                  <p className="text-slate-300 font-mono text-xs">{trade.token_id}</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs mb-1">Amount</p>
                  <p className="text-white font-semibold">${trade.amount?.toFixed(2) || '0.00'}</p>
                </div>
              </div>

              {trade.pnl !== null && trade.pnl !== undefined && (
                <div className="mt-3 pt-3 border-t border-slate-700">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-slate-500">PnL</span>
                    <span className={`font-semibold ${
                      trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-slate-400">
          <Activity className="mx-auto mb-3 text-slate-600" size={48} />
          <p>Waiting for trades...</p>
          <p className="text-sm text-slate-500 mt-1">
            {isConnected ? 'Listening for new trades' : 'Connecting to stream...'}
          </p>
        </div>
      )}
    </div>
  )
}

export default LiveTradesStream
