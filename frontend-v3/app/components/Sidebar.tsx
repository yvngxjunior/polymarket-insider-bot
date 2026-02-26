'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navigation = [
  { name: 'Dashboard', href: '/', icon: '📊' },
  { name: 'Settings', href: '/settings', icon: '⚙️' },
  { name: 'Positions', href: '/positions', icon: '📈' },
  { name: 'History', href: '/history', icon: '📜' },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex w-64 flex-col border-r border-gray-800 bg-gray-900">
      {/* Logo */}
      <div className="flex h-16 items-center border-b border-gray-800 px-6">
        <h1 className="text-xl font-bold text-primary-500">PolyInsider</h1>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`
                group flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors
                ${isActive
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }
              `}
            >
              <span className="mr-3 text-lg">{item.icon}</span>
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-gray-800 p-4">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>v3.0.0</span>
          <div className="flex items-center">
            <div className="mr-2 h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            API Online
          </div>
        </div>
      </div>
    </div>
  );
}
