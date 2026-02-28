import { TrendingUp, TrendingDown } from 'lucide-react'

const StatsCard = ({ title, value, icon, trend, subtitle, positive = true }) => {
  return (
    <div className="card">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-slate-400 text-sm mb-1">{title}</p>
          <h3 className="text-3xl font-bold text-white">{value}</h3>
          {subtitle && <p className="text-slate-500 text-xs mt-1">{subtitle}</p>}
        </div>
        <div className="p-3 bg-slate-800 rounded-lg">
          {icon}
        </div>
      </div>
      
      {trend !== undefined && trend !== null && (
        <div className={`flex items-center gap-1 text-sm ${
          positive ? 'text-green-500' : 'text-red-500'
        }`}>
          {positive ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
          <span>{Math.abs(trend).toFixed(2)}%</span>
          <span className="text-slate-500">vs initial</span>
        </div>
      )}
    </div>
  )
}

export default StatsCard
