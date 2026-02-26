export interface Portfolio {
  total_capital: number
  peak_capital: number
  daily_pnl: number
  drawdown_pct: number
  open_positions_count: number
  daily_reset_date: string
}

export interface Position {
  trade_id: number
  token_id: string
  market_question: string
  side: 'BUY' | 'SELL'
  entry_price: number
  current_price: number | null
  amount_usdc: number
  unrealized_pnl: number | null
  tp1_hit: boolean
  tp2_price: number
  sl_price: number
  opened_at: string
}

export interface PositionsResponse {
  positions: Position[]
  total_count: number
  total_capital_deployed: number
}

export interface Trade {
  id: number
  source_wallet: string
  market_question: string | null
  token_id: string
  side: 'BUY' | 'SELL'
  amount_usdc: number
  price: number
  pnl_usdc: number | null
  status: 'EXECUTED' | 'SKIPPED' | 'FAILED'
  skip_reason: string | null
  tx_hash: string | null
  created_at: string
  executed_at: string | null
}

export interface TradesResponse {
  trades: Trade[]
  total_count: number
  page: number
  per_page: number
}

export interface Wallet {
  address: string
  label: string | null
  score: number
  win_rate: number
  total_trades: number
  total_profit_usd: number
  is_active: boolean
  is_whale: boolean
  consecutive_losses: number
  entry_timing_score: number
  first_seen: string
  last_activity: string
}

export interface WalletsResponse {
  wallets: Wallet[]
  total_count: number
  active_count: number
}

export interface HealthStatus {
  status: 'ok' | 'error'
  service: string
  version: string
}
