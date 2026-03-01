'use client'

import { useEffect, useState } from 'react'
import { RefreshCw, Play, Database, AlertCircle, Activity, TrendingUp } from 'lucide-react'

type HealthData = {
  wallet_refresher: string
  executor: string
  db: string
  dry_run: boolean
  timestamp: string
}

type Signal = {
  id: number
  whale_address: string
  signal_type: string
  outcome_price: number
  market_name?: string
  created_at: string
}

type Whale = {
  address: string
  whale_score: number
  conviction_score: number
  total_pnl: number
  total_volume: number
}

type LogEntry = {
  timestamp: string
  level: string
  message: string
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [signals, setSignals] = useState<Signal[]>([])
  const [whales, setWhales] = useState<Whale[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<string>('')

  const fetchData = async () => {
    setIsRefreshing(true)
    try {
      // Health check
      const healthRes = await fetch('http://localhost:8000/health')
      if (healthRes.ok) {
        const healthData = await healthRes.json()
        setHealth(healthData)
      }

      // Trade signals
      const signalsRes = await fetch('http://localhost:8000/api/signals?limit=20')
      if (signalsRes.ok) {
        const signalsData = await signalsRes.json()
        setSignals(signalsData)
      }

      // Top whales
      const whalesRes = await fetch('http://localhost:8000/api/whales')
      if (whalesRes.ok) {
        const whalesData = await whalesRes.json()
        setWhales(whalesData)
      }

      // Logs
      const logsRes = await fetch('http://localhost:8000/api/logs?service=wallet-refresher&tail=100')
      if (logsRes.ok) {
        const logsData = await logsRes.json()
        setLogs(logsData)
      }

      setLastUpdate(new Date().toLocaleTimeString('fr-FR'))
    } catch (error) {
      console.error('Fetch error:', error)
    } finally {
      setIsRefreshing(false)
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 15000) // Refresh every 15s
    return () => clearInterval(interval)
  }, [])

  const getStatusColor = (status: string) => {
    if (status === 'running') return 'bg-emerald-500/20 text-emerald-400'
    if (status === 'stopped') return 'bg-red-500/20 text-red-400'
    return 'bg-orange-500/20 text-orange-400'
  }

  const getScoreColor = (score: number) => {
    if (score >= 0.80) return 'text-emerald-400'
    if (score >= 0.70) return 'text-yellow-400'
    return 'text-red-400'
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950/30 to-slate-950 text-white">
      <div className="max-w-[1800px] mx-auto p-8">
        {/* HEADER */}
        <header className="mb-12">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 bg-gradient-to-br from-purple-500 to-pink-500 rounded-2xl flex items-center justify-center">
                <Activity className="w-8 h-8" />
              </div>
              <div>
                <h1 className="text-6xl font-black bg-gradient-to-r from-purple-400 via-pink-400 to-purple-400 bg-clip-text text-transparent">
                  PolyInsider v3.2
                </h1>
                <p className="text-slate-400 text-lg mt-1">Live Whale Copy-Trading • 5€ Starter Mode</p>
              </div>
            </div>
            <button 
              onClick={fetchData}
              disabled={isRefreshing}
              className="flex items-center gap-3 px-8 py-4 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 rounded-xl font-bold text-lg transition-all shadow-lg shadow-purple-500/20"
            >
              <RefreshCw className={`w-6 h-6 ${isRefreshing ? 'animate-spin' : ''}`} />
              {isRefreshing ? 'Refreshing...' : 'Refresh Now'}
            </button>
          </div>
          {lastUpdate && (
            <p className="text-slate-500 text-sm">Dernière mise à jour: {lastUpdate}</p>
          )}
        </header>

        {/* STATUS GRID */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
          <div className="bg-white/5 backdrop-blur-xl border border-white/10 p-8 rounded-2xl">
            <div className="flex items-center gap-3 mb-4">
              <Play className="w-8 h-8 text-purple-400" />
              <h3 className="font-bold text-xl">Wallet Refresher</h3>
            </div>
            <p className={`text-4xl font-black mb-2 ${health?.wallet_refresher === 'running' ? 'text-emerald-400' : 'text-orange-400'}`}>
              {health?.wallet_refresher || 'unknown'}
            </p>
            <p className="text-sm text-slate-400">Scraping whale exits</p>
          </div>

          <div className="bg-white/5 backdrop-blur-xl border border-white/10 p-8 rounded-2xl">
            <div className="flex items-center gap-3 mb-4">
              <Database className="w-8 h-8 text-blue-400" />
              <h3 className="font-bold text-xl">Executor</h3>
            </div>
            <p className={`text-4xl font-black mb-2 ${health?.executor === 'running' ? 'text-emerald-400' : 'text-orange-400'}`}>
              {health?.executor || 'unknown'}
            </p>
            <p className="text-sm text-slate-400">
              Mode: <span className={`font-bold ${health?.dry_run ? 'text-yellow-400' : 'text-emerald-400'}`}>
                {health?.dry_run ? 'DRY-RUN' : 'LIVE'}
              </span>
            </p>
          </div>

          <div className="bg-white/5 backdrop-blur-xl border border-white/10 p-8 rounded-2xl">
            <div className="flex items-center gap-3 mb-4">
              <TrendingUp className="w-8 h-8 text-emerald-400" />
              <h3 className="font-bold text-xl">Signals (24h)</h3>
            </div>
            <p className="text-4xl font-black mb-2 text-emerald-400">
              {signals.length}
            </p>
            <p className="text-sm text-slate-400">Trade opportunities detected</p>
          </div>

          <div className="bg-white/5 backdrop-blur-xl border border-white/10 p-8 rounded-2xl">
            <div className="flex items-center gap-3 mb-4">
              <Activity className="w-8 h-8 text-pink-400" />
              <h3 className="font-bold text-xl">Whales Tracked</h3>
            </div>
            <p className="text-4xl font-black mb-2 text-pink-400">
              {whales.length}
            </p>
            <p className="text-sm text-slate-400">Top performers monitored</p>
          </div>
        </div>

        {/* MAIN CONTENT GRID */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
          {/* TOP WHALES */}
          <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-8">
            <h3 className="font-bold text-3xl mb-6 flex items-center gap-3">
              🐋 Top 12 Whales
            </h3>
            <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
              {whales.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                  <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>Aucun whale tracké pour le moment</p>
                  <p className="text-xs mt-2">Lance wallet_refresher pour détecter</p>
                </div>
              ) : (
                whales.map((whale, i) => (
                  <div key={whale.address} className="flex items-center justify-between p-5 bg-white/5 rounded-xl hover:bg-white/10 transition-all border border-white/5">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-2xl font-black text-slate-600">#{i+1}</span>
                        <div className="font-mono text-sm text-slate-300">
                          {whale.address.slice(0,6)}...{whale.address.slice(-4)}
                        </div>
                      </div>
                      <div className="flex gap-4 text-xs text-slate-500">
                        <span>PnL: <span className="text-white font-bold">${whale.total_pnl?.toLocaleString()}</span></span>
                        <span>Vol: <span className="text-white font-bold">${whale.total_volume?.toLocaleString()}</span></span>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`text-3xl font-black ${getScoreColor(whale.whale_score)}`}>
                        {(whale.whale_score * 100).toFixed(0)}%
                      </div>
                      <div className={`text-xs font-bold mt-1 px-3 py-1 rounded-full ${getScoreColor(whale.conviction_score || 0)} bg-white/5`}>
                        Conv: {((whale.conviction_score || 0) * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* TRADE SIGNALS */}
          <div className="bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl p-8">
            <h3 className="font-bold text-3xl mb-6 flex items-center gap-3">
              📊 Trade Signals (Derniers 20)
            </h3>
            <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2">
              {signals.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                  <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>Aucun signal détecté</p>
                  <p className="text-xs mt-2">Les signals apparaîtront quand les whales tradent</p>
                </div>
              ) : (
                signals.map(signal => (
                  <div key={signal.id} className="flex items-center justify-between p-4 bg-white/5 rounded-xl hover:bg-white/10 transition-all border border-white/5">
                    <div className="flex-1">
                      <div className="font-mono text-sm text-slate-300 mb-1">
                        {signal.whale_address}
                      </div>
                      {signal.market_name && (
                        <div className="text-xs text-slate-500 truncate max-w-md">
                          {signal.market_name}
                        </div>
                      )}
                      <div className="text-xs text-slate-600 mt-1">
                        {new Date(signal.created_at).toLocaleString('fr-FR')}
                      </div>
                    </div>
                    <div className="text-right ml-4">
                      <div className={`font-bold px-4 py-2 rounded-lg text-sm ${signal.signal_type === 'SELL' ? 'bg-red-500/20 text-red-300' : signal.signal_type === 'BUY' ? 'bg-green-500/20 text-green-300' : 'bg-blue-500/20 text-blue-300'}`}>
                        {signal.signal_type}
                      </div>
                      <div className="text-xs text-slate-400 mt-1">
                        @ {signal.outcome_price.toFixed(2)}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* LOGS TERMINAL */}
        <div className="bg-black/40 border border-white/10 rounded-2xl p-8">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-8 h-8 text-orange-400" />
              <h3 className="font-bold text-3xl">Live Logs (Wallet Refresher)</h3>
            </div>
            <div className="flex gap-2">
              <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></div>
              <div className="w-3 h-3 bg-yellow-500 rounded-full animate-pulse" style={{animationDelay: '0.2s'}}></div>
              <div className="w-3 h-3 bg-emerald-500 rounded-full animate-pulse" style={{animationDelay: '0.4s'}}></div>
            </div>
          </div>
          <div className="bg-black/70 border border-emerald-500/20 rounded-xl p-6 h-96 overflow-y-auto font-mono text-xs">
            {logs.length === 0 ? (
              <div className="flex items-center justify-center h-full text-slate-600">
                <div className="text-center">
                  <AlertCircle className="w-12 h-12 mx-auto mb-3 opacity-30" />
                  <p>Waiting for logs...</p>
                  <p className="text-xs mt-2">Vérifie que wallet_refresher tourne</p>
                </div>
              </div>
            ) : (
              logs.slice(-50).map((log, i) => (
                <div 
                  key={i} 
                  className={`py-1 ${
                    log.level === 'ERROR' ? 'text-red-400' : 
                    log.level === 'WARNING' ? 'text-yellow-400' : 
                    log.level === 'INFO' ? 'text-emerald-400' : 
                    'text-slate-400'
                  }`}
                >
                  <span className="text-slate-600">[{log.timestamp}]</span>
                  <span className="mx-2 font-bold">{log.level}</span>
                  <span>{log.message}</span>
                </div>
              ))
            )}
          </div>
          <div className="mt-4 text-xs text-slate-500 text-center">
            Affiche les 50 dernières lignes • Auto-refresh toutes les 15s
          </div>
        </div>

        {/* FOOTER */}
        <footer className="mt-12 text-center text-slate-600 text-sm">
          <p>PolyInsider Bot v3.2 • Mode 5€ • DRY-RUN enabled</p>
          <p className="mt-2">Backend API: <a href="http://localhost:8000/docs" className="text-purple-400 hover:underline" target="_blank">http://localhost:8000/docs</a></p>
        </footer>
      </div>
    </div>
  )
}
