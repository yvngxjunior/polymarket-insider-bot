'use client'
import { Alert } from '@/lib/types'
import { useEffect, useRef } from 'react'

export function AlertFeed({ alerts }: { alerts: Alert[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [alerts])
  
  return (
    <div className="bg-black border border-gray-800 rounded p-4 font-mono text-sm">
      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-gray-800">
        <span className="text-green-400">●</span>
        <span className="text-gray-400">System Logs (Live)</span>
      </div>
      <div ref={containerRef} className="space-y-1 max-h-64 overflow-y-auto">
        {alerts.slice(-20).map((alert, i) => {
          const icon = alert.level === 'success' ? '🟢' : alert.level === 'warning' ? '⚠️' : '🔴'
          const color = alert.level === 'success' ? 'text-green-400' : alert.level === 'warning' ? 'text-yellow-400' : 'text-red-400'
          const time = new Date(alert.timestamp * 1000).toLocaleTimeString('en-US', {hour12: false})
          
          return (
            <div key={i} className="flex gap-3">
              <span className="text-gray-600">[{time}]</span>
              <span>{icon}</span>
              <span className={color}>{alert.message}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
