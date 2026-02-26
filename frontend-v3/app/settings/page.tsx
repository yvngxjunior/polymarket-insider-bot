'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card';
import { Switch } from '@/components/ui/Switch';
import { Slider } from '@/components/ui/Slider';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { Alert, AlertDescription } from '@/components/ui/Alert';
import { Separator } from '@/components/ui/Separator';
import { Label } from '@/components/ui/Label';
import { settingsApi } from '@/lib/api';
import { BotSettings } from '@/lib/types';

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
      const data = await settingsApi.getSettings();
      setSettings(data);
      setMessage(null);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to load settings. Check API connection.' });
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    if (!settings) return;
    setSaving(true);
    setMessage(null);

    try {
      await settingsApi.updateSettings(settings);
      setMessage({ type: 'success', text: '✅ Settings saved! Restart bot to apply changes.' });
    } catch (error) {
      setMessage({ type: 'error', text: '❌ Failed to save settings. Check API connection.' });
    } finally {
      setSaving(false);
    }
  };

  const updateSetting = <K extends keyof BotSettings>(key: K, value: BotSettings[K]) => {
    setSettings((prev) => (prev ? { ...prev, [key]: value } : null));
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mb-4 inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
          <p className="text-gray-400">Loading settings...</p>
        </div>
      </div>
    );
  }

  if (!settings) {
    return (
      <Alert variant="error">
        <AlertDescription>❌ Failed to load settings. Check that backend API is running on http://localhost:8000</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6 pb-16">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Settings</h1>
          <p className="mt-2 text-gray-400">Configure all bot parameters</p>
        </div>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={fetchSettings} disabled={saving}>
            🔄 Reload
          </Button>
          <Button onClick={saveSettings} loading={saving}>
            💾 Save Changes
          </Button>
        </div>
      </div>

      {/* Alert */}
      {message && (
        <Alert variant={message.type === 'error' ? 'error' : 'success'}>
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}

      {/* Core Settings */}
      <Card>
        <CardHeader>
          <CardTitle>⚙️ Core Settings</CardTitle>
          <CardDescription>Basic bot operation parameters</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base">Dry Run Mode</Label>
              <p className="text-sm text-gray-500">Simulate trades without real execution</p>
            </div>
            <Switch checked={settings.dry_run} onCheckedChange={(v) => updateSetting('dry_run', v)} />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Scan Interval</Label>
              <span className="font-mono text-sm text-primary-500">{settings.scan_interval}s</span>
            </div>
            <p className="text-sm text-gray-500">Time between scans (1-60 seconds)</p>
            <Slider
              value={[settings.scan_interval]}
              onValueChange={([v]) => updateSetting('scan_interval', v)}
              min={1}
              max={60}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <Label className="text-base">Initial Capital (USDC)</Label>
            <p className="text-sm text-gray-500">Starting capital for simulation</p>
            <Input
              type="number"
              value={settings.initial_capital}
              onChange={(e) => updateSetting('initial_capital', parseFloat(e.target.value))}
            />
          </div>
        </CardContent>
      </Card>

      {/* Risk Management */}
      <Card>
        <CardHeader>
          <CardTitle>🛡️ Risk Management</CardTitle>
          <CardDescription>Position sizing and risk limits</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Max Open Positions</Label>
              <span className="font-mono text-sm text-primary-500">{settings.max_positions}</span>
            </div>
            <p className="text-sm text-gray-500">Maximum concurrent positions (1-50)</p>
            <Slider
              value={[settings.max_positions]}
              onValueChange={([v]) => updateSetting('max_positions', v)}
              min={1}
              max={50}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Max Position Size</Label>
              <span className="font-mono text-sm text-primary-500">
                {(settings.max_position_pct * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-500">Max % of capital per position (1-50%)</p>
            <Slider
              value={[settings.max_position_pct * 100]}
              onValueChange={([v]) => updateSetting('max_position_pct', v / 100)}
              min={1}
              max={50}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Daily Loss Limit</Label>
              <span className="font-mono text-sm text-primary-500">
                {(settings.daily_loss_limit_pct * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-500">Max daily loss before pause (1-100%)</p>
            <Slider
              value={[settings.daily_loss_limit_pct * 100]}
              onValueChange={([v]) => updateSetting('daily_loss_limit_pct', v / 100)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Drawdown Limit</Label>
              <span className="font-mono text-sm text-primary-500">
                {(settings.drawdown_limit_pct * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-500">Max drawdown from peak (1-100%)</p>
            <Slider
              value={[settings.drawdown_limit_pct * 100]}
              onValueChange={([v]) => updateSetting('drawdown_limit_pct', v / 100)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Kelly Fraction</Label>
              <span className="font-mono text-sm text-primary-500">
                {(settings.kelly_fraction * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-500">Kelly sizing fraction (1-100%)</p>
            <Slider
              value={[settings.kelly_fraction * 100]}
              onValueChange={([v]) => updateSetting('kelly_fraction', v / 100)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Convergence Boost</Label>
              <span className="font-mono text-sm text-primary-500">{settings.convergence_boost.toFixed(1)}x</span>
            </div>
            <p className="text-sm text-gray-500">Size multiplier when insiders converge (1-3x)</p>
            <Slider
              value={[settings.convergence_boost * 10]}
              onValueChange={([v]) => updateSetting('convergence_boost', v / 10)}
              min={10}
              max={30}
              step={1}
            />
          </div>

          <Separator />

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Min Price</Label>
              <p className="text-xs text-gray-500">Don't buy below</p>
              <Input
                type="number"
                value={settings.min_price}
                onChange={(e) => updateSetting('min_price', parseFloat(e.target.value))}
                step={0.01}
              />
            </div>
            <div className="space-y-2">
              <Label>Max Price</Label>
              <p className="text-xs text-gray-500">Don't buy above</p>
              <Input
                type="number"
                value={settings.max_price}
                onChange={(e) => updateSetting('max_price', parseFloat(e.target.value))}
                step={0.01}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Conviction Filters */}
      <Card>
        <CardHeader>
          <CardTitle>🎯 Conviction Filters</CardTitle>
          <CardDescription>Insider quality thresholds</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Min Win Rate</Label>
              <span className="font-mono text-sm text-primary-500">
                {(settings.min_win_rate * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-500">Minimum wallet win rate (0-100%)</p>
            <Slider
              value={[settings.min_win_rate * 100]}
              onValueChange={([v]) => updateSetting('min_win_rate', v / 100)}
              min={0}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Min Trades Count</Label>
              <span className="font-mono text-sm text-primary-500">{settings.min_trades_count}</span>
            </div>
            <p className="text-sm text-gray-500">Minimum historical trades (1-100)</p>
            <Slider
              value={[settings.min_trades_count]}
              onValueChange={([v]) => updateSetting('min_trades_count', v)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Min Source Bet</Label>
              <span className="font-mono text-sm text-primary-500">${settings.min_source_bet_usdc}</span>
            </div>
            <p className="text-sm text-gray-500">Minimum source trade size ($1-$10,000)</p>
            <Slider
              value={[settings.min_source_bet_usdc]}
              onValueChange={([v]) => updateSetting('min_source_bet_usdc', v)}
              min={1}
              max={1000}
              step={10}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Min Wallet Score</Label>
              <span className="font-mono text-sm text-primary-500">
                {(settings.min_wallet_score * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-500">Minimum wallet quality score (0-100%)</p>
            <Slider
              value={[settings.min_wallet_score * 100]}
              onValueChange={([v]) => updateSetting('min_wallet_score', v / 100)}
              min={0}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Max Consecutive Losses</Label>
              <span className="font-mono text-sm text-primary-500">{settings.max_consecutive_losses}</span>
            </div>
            <p className="text-sm text-gray-500">Skip wallet after N losses (1-20)</p>
            <Slider
              value={[settings.max_consecutive_losses]}
              onValueChange={([v]) => updateSetting('max_consecutive_losses', v)}
              min={1}
              max={20}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Whale Threshold</Label>
              <span className="font-mono text-sm text-primary-500">${settings.whale_threshold}</span>
            </div>
            <p className="text-sm text-gray-500">Trade size for whale alerts ($50-$100,000)</p>
            <Slider
              value={[settings.whale_threshold]}
              onValueChange={([v]) => updateSetting('whale_threshold', v)}
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
          <CardTitle>🚀 Advanced Features</CardTitle>
          <CardDescription>Enable/disable optional modules</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Arbitrage */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-base">Arbitrage Scanner</Label>
                <p className="text-sm text-gray-500">Polymarket vs Kalshi arbitrage</p>
              </div>
              <Switch
                checked={settings.arb_enabled}
                onCheckedChange={(v) => updateSetting('arb_enabled', v)}
              />
            </div>
            {settings.arb_enabled && (
              <div className="ml-4 space-y-2 border-l-2 border-primary-600 pl-4">
                <div className="flex justify-between">
                  <Label className="text-sm">Min Profit %</Label>
                  <span className="font-mono text-sm text-primary-500">
                    {(settings.arb_min_profit_pct * 100).toFixed(1)}%
                  </span>
                </div>
                <Slider
                  value={[settings.arb_min_profit_pct * 100]}
                  onValueChange={([v]) => updateSetting('arb_min_profit_pct', v / 100)}
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
              <div>
                <Label className="text-base">Market Scanner</Label>
                <p className="text-sm text-gray-500">Scan thousands of markets</p>
              </div>
              <Switch
                checked={settings.market_scan_enabled}
                onCheckedChange={(v) => updateSetting('market_scan_enabled', v)}
              />
            </div>
            {settings.market_scan_enabled && (
              <div className="ml-4 space-y-2 border-l-2 border-primary-600 pl-4">
                <div className="flex justify-between">
                  <Label className="text-sm">Max Markets</Label>
                  <span className="font-mono text-sm text-primary-500">
                    {settings.market_scan_max_markets.toLocaleString()}
                  </span>
                </div>
                <Slider
                  value={[settings.market_scan_max_markets]}
                  onValueChange={([v]) => updateSetting('market_scan_max_markets', v)}
                  min={100}
                  max={20000}
                  step={100}
                />
              </div>
            )}
          </div>

          <Separator />

          {/* AI Agent */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-base">AI Agent (GPT-4o-mini)</Label>
                <p className="text-sm text-gray-500">AI-powered market analysis</p>
              </div>
              <Switch
                checked={settings.llm_enabled}
                onCheckedChange={(v) => updateSetting('llm_enabled', v)}
              />
            </div>
            {settings.llm_enabled && (
              <div className="ml-4 space-y-2 border-l-2 border-primary-600 pl-4">
                <div className="flex justify-between">
                  <Label className="text-sm">Min Confidence</Label>
                  <span className="font-mono text-sm text-primary-500">
                    {(settings.llm_min_confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <Slider
                  value={[settings.llm_min_confidence * 100]}
                  onValueChange={([v]) => updateSetting('llm_min_confidence', v / 100)}
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
          <CardTitle>🔧 Advanced Settings</CardTitle>
          <CardDescription>Technical parameters (experts only)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label className="text-base">Min Trade Amount (USDC)</Label>
            <p className="text-sm text-gray-500">Trades below this are ignored</p>
            <Input
              type="number"
              value={settings.min_trade_usdc}
              onChange={(e) => updateSetting('min_trade_usdc', parseFloat(e.target.value))}
              step={0.5}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label className="text-base">Kelly Fraction (Position Sizer)</Label>
              <span className="font-mono text-sm text-primary-500">
                {(settings.kelly_fraction_sizer * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-gray-500">Separate Kelly for position sizing</p>
            <Slider
              value={[settings.kelly_fraction_sizer * 100]}
              onValueChange={([v]) => updateSetting('kelly_fraction_sizer', v / 100)}
              min={1}
              max={100}
              step={1}
            />
          </div>

          <Separator />

          <div className="space-y-2">
            <Label className="text-base">Log Level</Label>
            <p className="text-sm text-gray-500">Logging verbosity</p>
            <select
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-white focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500"
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
        <Button onClick={saveSettings} loading={saving} size="lg">
          💾 Save All Changes
        </Button>
      </div>
    </div>
  );
}
