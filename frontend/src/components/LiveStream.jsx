import { useState, useEffect, useRef } from 'react'
import { formatDistanceToNow } from 'date-fns'

const LiveStream = () => {
  const [trades, setTrades] = useState([])
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8001'
    const ws = new WebSocket(`${wsUrl}/ws/trades`)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'trades_update' && data.trades) {
          setTrades(data.trades)
        }
      } catch (error) {
        console.error('[WS] Parse error:', error)
      }
    }

    ws.onerror = () => setIsConnected(false)
    ws.onclose = () => setIsConnected(false)

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    }
  }, [])

  return (
    <section className="border-sharp sticky top-8">
      {/* Header */}
      <div className="border-b border-ink p-8">
        <div className="flex items-center justify-between mb-4">
          <h4 className="font-display text-3xl text-ink">
            Live
          </h4>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 ${
              isConnected ? 'bg-brand animate-pulse-slow' : 'bg-muted'
            }`}></div>
            <span className="font-mono text-xs text-muted uppercase">
              {isConnected ? 'Connected' : 'Offline'}
            </span>
          </div>
        </div>
        <p className="font-mono text-xs text-muted">
          WebSocket Stream
        </p>
      </div>

      {/* Stream */}
      <div className="p-8">
        {trades.length > 0 ? (
          <div className="space-y-6">
            {trades.slice(0, 5).map((trade, idx) => (
              <div key={idx} className="border-b border-ink pb-6 last:border-0">
                {/* Side */}
                <div className="mb-3">
                  <span className={`font-mono text-xs uppercase tracking-widest ${
                    trade.side === 'BUY' ? 'text-brand' : 'text-ink'
                  }`}>
                    {trade.side}
                  </span>
                </div>

                {/* Amount */}
                <div className="mb-2">
                  <p className="font-display text-2xl text-ink">
                    ${trade.amount?.toFixed(0) || '0'}
                  </p>
                </div>

                {/* Meta */}
                <div className="flex items-center justify-between">
                  <p className="font-mono text-xs text-muted">
                    {trade.token_id?.slice(0, 8)}...
                  </p>
                  {trade.timestamp && (
                    <p className="font-mono text-xs text-muted">
                      {formatDistanceToNow(new Date(trade.timestamp), { addSuffix: true })}
                    </p>
                  )}
                </div>

                {/* PnL if exists */}
                {trade.pnl !== null && trade.pnl !== undefined && (
                  <div className="mt-3 pt-3 border-t border-ink">
                    <p className={`font-mono text-xs ${
                      trade.pnl >= 0 ? 'text-brand' : 'text-ink'
                    }`}>
                      P&L: {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="py-16 text-center">
            <p className="font-mono text-xs text-muted uppercase tracking-wide">
              {isConnected ? 'Awaiting trades...' : 'Connecting...'}
            </p>
          </div>
        )}
      </div>
    </section>
  )
}

export default LiveStream
