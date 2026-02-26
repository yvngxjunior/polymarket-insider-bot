'use client'
import { emergencyStopAll } from '@/lib/api'
import { useState } from 'react'

export function EmergencyControls() {
  const [confirming, setConfirming] = useState(false)
  
  const handlePanicStop = async () => {
    if (!confirming) {
      setConfirming(true)
      setTimeout(() => setConfirming(false), 3000)
      return
    }
    await emergencyStopAll()
    alert('🚨 All trading stopped!')
    window.location.reload()
  }
  
  return (
    <div className="flex gap-4">
      <button 
        onClick={handlePanicStop}
        className={`px-6 py-3 rounded font-bold transition ${
          confirming 
            ? 'bg-red-600 animate-pulse' 
            : 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
        }`}
      >
        {confirming ? '⚠️ CLICK AGAIN TO CONFIRM' : '🔴 EMERGENCY STOP'}
      </button>
    </div>
  )
}
