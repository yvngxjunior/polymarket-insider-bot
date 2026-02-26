export function Badge({ variant, children }: { variant: 'success'|'warning'|'error'; children: React.ReactNode }) {
  const colors = {
    success: 'bg-green-500/20 text-green-400 border-green-500',
    warning: 'bg-yellow-500/20 text-yellow-400 border-yellow-500',
    error: 'bg-red-500/20 text-red-400 border-red-500'
  }
  return <span className={`px-2 py-1 rounded text-xs font-mono border ${colors[variant]}`}>{children}</span>
}
