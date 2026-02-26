// Bot Settings Types
export interface BotSettings {
  // Core
  dry_run: boolean;
  scan_interval: number;
  initial_capital: number;

  // Risk Management
  max_positions: number;
  max_position_pct: number;
  max_price: number;
  min_price: number;
  daily_loss_limit_pct: number;
  drawdown_limit_pct: number;
  kelly_fraction: number;
  convergence_boost: number;

  // Filters
  min_win_rate: number;
  min_trades_count: number;
  min_source_bet_usdc: number;
  min_wallet_score: number;
  max_consecutive_losses: number;
  whale_threshold: number;

  // Features
  arb_enabled: boolean;
  arb_min_profit_pct: number;
  market_scan_enabled: boolean;
  market_scan_max_markets: number;
  llm_enabled: boolean;
  llm_min_confidence: number;

  // Advanced
  min_trade_usdc: number;
  kelly_fraction_sizer: number;
  log_level: string;
}

// Portfolio Types
export interface PortfolioStats {
  total_capital: number;
  peak_capital: number;
  daily_pnl: number;
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  open_positions: number;
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
}

// Position Types
export interface Position {
  id: number;
  market_question: string;
  token_id: string;
  side: string;
  amount_usdc: number;
  entry_price: number;
  current_price: number | null;
  pnl_usdc: number | null;
  pnl_pct: number | null;
  executed_at: string;
  age_hours: number;
  source_wallet: string;
}

// Trade History Types
export interface Trade {
  id: number;
  market_question: string;
  side: string;
  amount_usdc: number;
  price: number;
  pnl_usdc: number | null;
  pnl_pct: number | null;
  executed_at: string;
  closed_at: string | null;
  source_wallet: string;
  status: 'OPEN' | 'CLOSED' | 'SKIPPED';
}
