'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import { Loader2, Save, RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react';

interface BotSettings {
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

export default function SettingsPage() {
  const [settings, setSettings] = useState<BotSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/settings');
      if (!response.ok) throw new Error('Failed to fetch settings');
      const data = await response.json();
      setSettings(data);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to load settings' });
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    if (!settings) return;
    setSaving(true);
    setMessage(null);
    
    try {
      const response = await fetch('http://localhost:8000/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      
      if (!response.ok) throw new Error('Failed to save settings');
      
      setMessage({ type: 'success', text: 'Settings saved successfully! Restart bot to apply.' });
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to save settings' });
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = <K extends keyof BotSettings>(key: K, value: BotSettings[K]) => {
    setSettings(prev => prev ? { ...prev, [key]: value } : null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="p-8">
        <Alert variant="destructive">
          <AlertTriangle className="w-4 h-4" />
          <AlertDescription>Failed to load settings. Check API connection.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Bot Settings</h1>
          <p className="text-muted-foreground mt-1">Configure all bot parameters</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchSettings} disabled={saving}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Reload
          </Button>
          <Button onClick={saveSettings} disabled={saving}>
            {saving ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Save className="w-4 h-4 mr-2" />
            )}
            Save Changes
          </Button>
        </div>
      </div>

      {/* Alert */}
      {message && (
        <Alert variant={message.type === 'error' ? 'destructive' : 'default'}>
          {message.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4" />
          ) : (
            <AlertTriangle className="w-4 h-4" />
          )}
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}

      {/* Core Settings */}
      <Card>
        <CardHeader>
          <CardTitle>Core Settings</CardTitle>
          <CardDescription>Basic bot operation parameters</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Dry Run */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="text-base font-medium">Dry Run Mode</Label>
              <p className="text-sm text-muted-foreground">
                Simulate trades without real execution
              </p>
            </div>
            <Switch
              checked={settings.dry_run}
              onCheckedChange={(checked) => updateSetting('dry_run', checked)}
            />
          </div>

          <Separator />

          {/* Scan Interval */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Scan Interval</Label>
              <span className="text-sm font-mono">{settings.scan_interval}s</span>
            </div>
            <p className="text-sm text-muted-foreground">Time between scans (1-60 seconds)</p>
            <Slider
              value={[settings.scan_interval]}
              onValueChange={([value]) => updateSetting('scan_interval', value)}
              min={1}
              max={60}
              step={1}
            />
          </div>

          <Separator />

          {/* Initial Capital */}
          <div className="space-y-2">
            <Label className="text-base font-medium">Initial Capital (USDC)</Label>
            <p className="text-sm text-muted-foreground">Starting capital for the bot</p>
            <Input
              type="number"
              value={settings.initial_capital}
              onChange={(e) => updateSetting('initial_capital', parseFloat(e.target.value))}
              min={1}
              step={10}
            />
          </div>
        </CardContent>
      </Card>

      {/* Risk Management */}
      <Card>
        <CardHeader>
          <CardTitle>Risk Management</CardTitle>
          <CardDescription>Position sizing and risk limits</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Max Positions */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Max Open Positions</Label>
              <span className="text-sm font-mono">{settings.max_positions}</span>
            </div>
            <p className="text-sm text-muted-foreground">Maximum concurrent positions (1-50)</p>
            <Slider
              value={[settings.max_positions]}
              onValueChange={([value]) => updateSetting('max_positions', value)}
              min={1}
              max={50}
              step={1}
            />
          </div>

          <Separator />

          {/* Max Position % */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Max Position Size</Label>
              <span className="text-sm font-mono">{(settings.max_position_pct * 100).toFixed(0)}%</span>
            </div>
            <p className="text-sm text-muted-foreground">Max % of capital per position (1-50%)</p>
            <Slider
              value={[settings.max_position_pct * 100]}
              onValueChange={([value]) => updateSetting('max_position_pct', value / 100)}
              min={1}
              max={50}
              step={1}
            />
          </div>

          <Separator />

          {/* Daily Loss Limit */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Daily Loss Limit</Label>
              <span className="text-sm font-mono">{(settings.daily_loss_limit_pct * 100).toFixed(0)}%</span>
            </div>
            <p className="text-sm text-muted-foreground">Max daily loss before pause (1-100%)</p>
            <Slider
              value={[settings.daily_loss_limit_pct * 100]}
              onValueChange={([value]) => updateSetting('daily_loss_limit_pct', value / 100)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          {/* Drawdown Limit */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Drawdown Limit</Label>
              <span className="text-sm font-mono">{(settings.drawdown_limit_pct * 100).toFixed(0)}%</span>
            </div>
            <p className="text-sm text-muted-foreground">Max drawdown from peak (1-100%)</p>
            <Slider
              value={[settings.drawdown_limit_pct * 100]}
              onValueChange={([value]) => updateSetting('drawdown_limit_pct', value / 100)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          {/* Kelly Fraction */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Kelly Fraction</Label>
              <span className="text-sm font-mono">{(settings.kelly_fraction * 100).toFixed(0)}%</span>
            </div>
            <p className="text-sm text-muted-foreground">Kelly sizing fraction (1-100%)</p>
            <Slider
              value={[settings.kelly_fraction * 100]}
              onValueChange={([value]) => updateSetting('kelly_fraction', value / 100)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          {/* Convergence Boost */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Convergence Boost</Label>
              <span className="text-sm font-mono">{settings.convergence_boost.toFixed(1)}x</span>
            </div>
            <p className="text-sm text-muted-foreground">Size multiplier when insiders converge (1-3x)</p>
            <Slider
              value={[settings.convergence_boost * 10]}
              onValueChange={([value]) => updateSetting('convergence_boost', value / 10)}
              min={10}
              max={30}
              step={1}
            />
          </div>

          <Separator />

          {/* Price Limits */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label className="text-base font-medium">Min Price</Label>
              <p className="text-sm text-muted-foreground">Don't buy below</p>
              <Input
                type="number"
                value={settings.min_price}
                onChange={(e) => updateSetting('min_price', parseFloat(e.target.value))}
                min={0.01}
                max={0.50}
                step={0.01}
              />
            </div>
            <div className="space-y-2">
              <Label className="text-base font-medium">Max Price</Label>
              <p className="text-sm text-muted-foreground">Don't buy above</p>
              <Input
                type="number"
                value={settings.max_price}
                onChange={(e) => updateSetting('max_price', parseFloat(e.target.value))}
                min={0.50}
                max={0.99}
                step={0.01}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Conviction Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Conviction Filters</CardTitle>
          <CardDescription>Insider quality thresholds</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Min Win Rate */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Min Win Rate</Label>
              <span className="text-sm font-mono">{(settings.min_win_rate * 100).toFixed(0)}%</span>
            </div>
            <p className="text-sm text-muted-foreground">Minimum wallet win rate to copy (0-100%)</p>
            <Slider
              value={[settings.min_win_rate * 100]}
              onValueChange={([value]) => updateSetting('min_win_rate', value / 100)}
              min={0}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          {/* Min Trades Count */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Min Trades Count</Label>
              <span className="text-sm font-mono">{settings.min_trades_count}</span>
            </div>
            <p className="text-sm text-muted-foreground">Minimum historical trades (1-100)</p>
            <Slider
              value={[settings.min_trades_count]}
              onValueChange={([value]) => updateSetting('min_trades_count', value)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          {/* Min Source Bet */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Min Source Bet</Label>
              <span className="text-sm font-mono">${settings.min_source_bet_usdc}</span>
            </div>
            <p className="text-sm text-muted-foreground">Minimum source trade size to copy ($1-$10,000)</p>
            <Slider
              value={[settings.min_source_bet_usdc]}
              onValueChange={([value]) => updateSetting('min_source_bet_usdc', value)}
              min={1}
              max={1000}
              step={10}
            />
          </div>

          <Separator />

          {/* Min Wallet Score */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Min Wallet Score</Label>
              <span className="text-sm font-mono">{(settings.min_wallet_score * 100).toFixed(0)}%</span>
            </div>
            <p className="text-sm text-muted-foreground">Minimum wallet quality score (0-100%)</p>
            <Slider
              value={[settings.min_wallet_score * 100]}
              onValueChange={([value]) => updateSetting('min_wallet_score', value / 100)}
              min={0}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          {/* Max Consecutive Losses */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Max Consecutive Losses</Label>
              <span className="text-sm font-mono">{settings.max_consecutive_losses}</span>
            </div>
            <p className="text-sm text-muted-foreground">Skip wallet after N losses (1-20)</p>
            <Slider
              value={[settings.max_consecutive_losses]}
              onValueChange={([value]) => updateSetting('max_consecutive_losses', value)}
              min={1}
              max={20}
              step={1}
            />
          </div>

          <Separator />

          {/* Whale Threshold */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Whale Threshold</Label>
              <span className="text-sm font-mono">${settings.whale_threshold}</span>
            </div>
            <p className="text-sm text-muted-foreground">Trade size for whale alerts ($50-$100,000)</p>
            <Slider
              value={[settings.whale_threshold]}
              onValueChange={([value]) => updateSetting('whale_threshold', value)}
              min={50}
              max={10000}
              step={50}
            />
          </div>
        </CardContent>
      </Card>

      {/* Features */}
      <Card>
        <CardHeader>
          <CardTitle>Advanced Features</CardTitle>
          <CardDescription>Enable/disable optional modules</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Arbitrage Scanner */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-base font-medium">Arbitrage Scanner</Label>
                <p className="text-sm text-muted-foreground">
                  Detect Polymarket vs Kalshi arbitrage opportunities
                </p>
              </div>
              <Switch
                checked={settings.arb_enabled}
                onCheckedChange={(checked) => updateSetting('arb_enabled', checked)}
              />
            </div>
            
            {settings.arb_enabled && (
              <div className="pl-4 space-y-2 border-l-2">
                <div className="flex justify-between">
                  <Label className="text-sm">Min Profit %</Label>
                  <span className="text-sm font-mono">{(settings.arb_min_profit_pct * 100).toFixed(1)}%</span>
                </div>
                <Slider
                  value={[settings.arb_min_profit_pct * 100]}
                  onValueChange={([value]) => updateSetting('arb_min_profit_pct', value / 100)}
                  min={1}
                  max={20}
                  step={0.1}
                />
              </div>
            )}
          </div>

          <Separator />

          {/* Market Scanner */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-base font-medium">Market Scanner</Label>
                <p className="text-sm text-muted-foreground">
                  Scan thousands of markets for opportunities
                </p>
              </div>
              <Switch
                checked={settings.market_scan_enabled}
                onCheckedChange={(checked) => updateSetting('market_scan_enabled', checked)}
              />
            </div>
            
            {settings.market_scan_enabled && (
              <div className="pl-4 space-y-2 border-l-2">
                <div className="flex justify-between">
                  <Label className="text-sm">Max Markets</Label>
                  <span className="text-sm font-mono">{settings.market_scan_max_markets.toLocaleString()}</span>
                </div>
                <Slider
                  value={[settings.market_scan_max_markets]}
                  onValueChange={([value]) => updateSetting('market_scan_max_markets', value)}
                  min={100}
                  max={20000}
                  step={100}
                />
              </div>
            )}
          </div>

          <Separator />

          {/* LLM Agent */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-base font-medium">AI Agent (GPT-4o-mini)</Label>
                <p className="text-sm text-muted-foreground">
                  AI-powered market analysis (requires OpenAI API key)
                </p>
              </div>
              <Switch
                checked={settings.llm_enabled}
                onCheckedChange={(checked) => updateSetting('llm_enabled', checked)}
              />
            </div>
            
            {settings.llm_enabled && (
              <div className="pl-4 space-y-2 border-l-2">
                <div className="flex justify-between">
                  <Label className="text-sm">Min Confidence</Label>
                  <span className="text-sm font-mono">{(settings.llm_min_confidence * 100).toFixed(0)}%</span>
                </div>
                <Slider
                  value={[settings.llm_min_confidence * 100]}
                  onValueChange={([value]) => updateSetting('llm_min_confidence', value / 100)}
                  min={50}
                  max={100}
                  step={1}
                />
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Advanced */}
      <Card>
        <CardHeader>
          <CardTitle>Advanced Settings</CardTitle>
          <CardDescription>Technical parameters (experts only)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Min Trade USDC */}
          <div className="space-y-2">
            <Label className="text-base font-medium">Min Trade Amount (USDC)</Label>
            <p className="text-sm text-muted-foreground">Trades below this are ignored</p>
            <Input
              type="number"
              value={settings.min_trade_usdc}
              onChange={(e) => updateSetting('min_trade_usdc', parseFloat(e.target.value))}
              min={0.5}
              step={0.5}
            />
          </div>

          <Separator />

          {/* Kelly Fraction Sizer */}
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base font-medium">Kelly Fraction (Position Sizer)</Label>
              <span className="text-sm font-mono">{(settings.kelly_fraction_sizer * 100).toFixed(0)}%</span>
            </div>
            <p className="text-sm text-muted-foreground">Separate Kelly for position sizing</p>
            <Slider
              value={[settings.kelly_fraction_sizer * 100]}
              onValueChange={([value]) => updateSetting('kelly_fraction_sizer', value / 100)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          {/* Log Level */}
          <div className="space-y-2">
            <Label className="text-base font-medium">Log Level</Label>
            <p className="text-sm text-muted-foreground">Logging verbosity</p>
            <select
              className="w-full px-3 py-2 border rounded-md"
              value={settings.log_level}
              onChange={(e) => updateSetting('log_level', e.target.value)}
            >
              <option value="DEBUG">DEBUG (Very Verbose)</option>
              <option value="INFO">INFO (Normal)</option>
              <option value="WARNING">WARNING (Quiet)</option>
              <option value="ERROR">ERROR (Errors Only)</option>
              <option value="CRITICAL">CRITICAL (Minimal)</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {/* Save Button (Bottom) */}
      <div className="flex justify-end">
        <Button onClick={saveSettings} disabled={saving} size="lg">
          {saving ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <Save className="w-4 h-4 mr-2" />
          )}
          Save All Changes
        </Button>
      </div>
    </div>
  );
}
