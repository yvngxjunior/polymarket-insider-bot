import { Link, useLocation } from 'react-router-dom'
import {
  HomeIcon,
  ChartBarIcon,
  ClockIcon,
  UserGroupIcon,
  Cog6ToothIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline'
import clsx from 'clsx'

interface SidebarProps {
  open: boolean
  onToggle: () => void
}

const navigation = [
  { name: 'Dashboard', href: '/', icon: HomeIcon, group: 'main' },
  { name: 'Positions', href: '/positions', icon: ChartBarIcon, group: 'trading' },
  { name: 'Trade History', href: '/trades', icon: ClockIcon, group: 'trading' },
  { name: 'Wallets', href: '/wallets', icon: UserGroupIcon, group: 'intelligence' },
  { name: 'Settings', href: '/settings', icon: Cog6ToothIcon, group: 'system' },
]

export default function Sidebar({ open, onToggle }: SidebarProps) {
  const location = useLocation()

  return (
    <div
      className={clsx(
        'bg-white/70 backdrop-blur-md border-r border-white/30 shadow-glass',
        'flex flex-col transition-all duration-300 ease-in-out',
        open ? 'w-64' : 'w-20'
      )}
    >
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-white/20">
        {open && (
          <div className="font-bold text-lg bg-gradient-to-r from-violet-600 to-indigo-600 bg-clip-text text-transparent">
            PolyInsider
          </div>
        )}
        <button
          onClick={onToggle}
          className="p-2 rounded-lg hover:bg-white/50 transition-colors"
        >
          {open ? (
            <ChevronLeftIcon className="w-5 h-5 text-gray-600" />
          ) : (
            <ChevronRightIcon className="w-5 h-5 text-gray-600" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-6 space-y-1">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href
          return (
            <Link
              key={item.name}
              to={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-xl',
                'transition-all duration-200',
                isActive
                  ? 'bg-gradient-to-r from-violet-500 to-indigo-500 text-white shadow-lg'
                  : 'text-gray-700 hover:bg-white/50'
              )}
            >
              <item.icon className={clsx('w-5 h-5', open ? '' : 'mx-auto')} />
              {open && (
                <span className="text-sm font-medium">{item.name}</span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      {open && (
        <div className="px-4 py-4 border-t border-white/20">
          <div className="text-xs text-gray-500 text-center">
            v3.1.0 • PolyInsider Bot
          </div>
        </div>
      )}
    </div>
  )
}
