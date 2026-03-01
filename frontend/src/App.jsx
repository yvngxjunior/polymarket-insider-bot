import { useState, useEffect } from 'react'
import Dashboard from './components/Dashboard'
import { fetchAPI } from './utils/api'
import './App.css'

function App() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await fetchAPI('/features/status')
        setStats(data)
      } catch (error) {
        console.error('Failed to load stats:', error)
      } finally {
        setLoading(false)
      }
    }

    loadStats()
    const interval = setInterval(loadStats, 10000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center">
        <div className="font-display text-6xl text-ink">Loading...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-paper">
      <Dashboard stats={stats} />
    </div>
  )
}

export default App
