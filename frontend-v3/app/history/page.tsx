'use client';

import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/Card';

export default function HistoryPage() {
  const [filter, setFilter] = useState<'all' | 'wins' | 'losses'>('all');

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Trade History</h1>
          <p className="mt-2 text-gray-400">All closed trades</p>
        </div>

        <div className="flex gap-2">
          {(['all', 'wins', 'losses'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-md px-4 py-2 text-sm font-medium capitalize transition-colors ${
                filter === f
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-gray-400">🚧 Trade history coming soon!</p>
          <p className="mt-2 text-sm text-gray-500">
            This page will show all your closed trades with detailed analytics.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
