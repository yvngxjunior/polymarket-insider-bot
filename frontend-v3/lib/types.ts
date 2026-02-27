export interface LiveStatus {
  botActive: boolean;
  totalPnL: number;
  dailyPnL: number;
  rpcLatency: number;
  gasPrice: number;
  walletBalance: number;
  lastTradeTimestamp: number;
}

export interface Target {
  address: string;
  name: string;
  winrate: number;
  roi7d: number;
  volume24h: number;
  avgPositionSize: number;
  lastTradeAge: number;
  isActive: boolean;
  riskAlert: boolean;
}

export interface Position {
  id: string;
  market: string;
  side: 'YES' | 'NO';
  entryPrice: number;
  currentPrice: number;
  pnl: number;
  probability: number;
  ageSeconds: number;
  slippage: number;
  canCashOut: boolean;
}

export interface RiskSettings {
  positionSizing: { mode: 'fixed' | 'percentage'; amount: number };
  maxSlippage: number;
  gasLimit: number;
  stopLoss: { enabled: boolean; dailyLimit: number; perTrade: number };
}

export interface Alert {
  timestamp: number;
  level: 'success' | 'warning' | 'error';
  message: string;
}

export interface DashboardData {
  liveStatus: LiveStatus;
  targets: Target[];
  positions: Position[];
  riskSettings: RiskSettings;
  alerts: Alert[];
}
