import { Wallet, Star } from 'lucide-react'

const WalletsTable = ({ wallets }) => {
  return (
    <div className="card">
      <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
        <Wallet className="text-purple-500" />
        Top Tracked Wallets
      </h2>
      
      {wallets && wallets.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left py-3 px-2 text-slate-400 font-medium">Address</th>
                <th className="text-right py-3 px-2 text-slate-400 font-medium">Score</th>
                <th className="text-right py-3 px-2 text-slate-400 font-medium">Win Rate</th>
                <th className="text-right py-3 px-2 text-slate-400 font-medium">Trades</th>
              </tr>
            </thead>
            <tbody>
              {wallets.map((wallet, idx) => (
                <tr key={idx} className="border-b border-slate-800 hover:bg-slate-800/50 transition">
                  <td className="py-3 px-2 text-slate-300 font-mono text-xs flex items-center gap-2">
                    {wallet.is_whitelisted && <Star size={12} className="text-yellow-500" />}
                    {wallet.address.slice(0, 6)}...{wallet.address.slice(-4)}
                  </td>
                  <td className="text-right py-3 px-2">
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-16 bg-slate-700 rounded-full h-2 overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-indigo-500 to-purple-500"
                          style={{ width: `${wallet.score * 100}%` }}
                        ></div>
                      </div>
                      <span className="text-slate-300 font-semibold w-10">
                        {(wallet.score * 100).toFixed(0)}
                      </span>
                    </div>
                  </td>
                  <td className="text-right py-3 px-2 text-green-400 font-semibold">
                    {(wallet.win_rate * 100).toFixed(1)}%
                  </td>
                  <td className="text-right py-3 px-2 text-slate-300">
                    {wallet.total_trades}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-center py-8 text-slate-400">
          <p>No wallets tracked</p>
        </div>
      )}
    </div>
  )
}

export default WalletsTable
