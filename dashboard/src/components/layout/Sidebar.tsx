'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import clsx from 'clsx'
import {
  Home,
  MessageSquare,
  Users,
  Share2,
  Brain,
  BarChart3,
  UserPlus,
  Star,
  Settings,
  ChevronLeft,
  ChevronRight,
  LogOut,
  CreditCard,
  TrendingUp,
  UsersRound,
  Megaphone,
  Workflow,
  Store,
  Code2,
} from 'lucide-react'
import { useAuth } from '@/stores/auth'
import { useAuthActions } from '@/lib/auth'

const menuItems = [
  { icon: Home, label: 'Dashboard', href: '/dashboard', id: 'dashboard' },
  { icon: MessageSquare, label: 'Conversations', href: '/conversations', id: 'conversations' },
  { icon: Users, label: 'Customers', href: '/customers', id: 'customers' },
  { icon: Share2, label: 'Channels', href: '/channels', id: 'channels' },
  { icon: Brain, label: 'Knowledge Base', href: '/knowledge-base', id: 'knowledge' },
  { icon: TrendingUp, label: 'Analytics', href: '/analytics', id: 'analytics' },
  { icon: BarChart3, label: 'Funnels', href: '/funnels', id: 'funnels' },
  { icon: Megaphone, label: 'Campaigns', href: '/campaigns', id: 'campaigns' },
  { icon: Workflow, label: 'Workflows', href: '/workflows', id: 'workflows' },
  { icon: UserPlus, label: 'Handoffs', href: '/handoffs', id: 'handoffs' },
  { icon: Star, label: 'CSAT', href: '/csat', id: 'csat' },
  { icon: UsersRound, label: 'Team', href: '/team', id: 'team' },
  { icon: CreditCard, label: 'Billing', href: '/billing', id: 'billing' },
  { icon: Store, label: 'Marketplace', href: '/marketplace', id: 'marketplace' },
  { icon: Code2, label: 'API Keys', href: '/api-keys', id: 'api-keys' },
  { icon: Settings, label: 'Settings', href: '/settings', id: 'settings' },
]

export const Sidebar: React.FC = () => {
  const [isCollapsed, setIsCollapsed] = useState(false)
  const pathname = usePathname()
  const tenant = useAuth((state) => state.tenant)
  const { handleLogout } = useAuthActions()

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className={clsx(
        'hidden md:flex flex-col fixed left-0 top-0 h-screen bg-white dark:bg-neutral-950 border-r border-neutral-100 dark:border-neutral-800/50 smooth z-40',
        isCollapsed ? 'w-[72px]' : 'w-60'
      )}>
        {/* Logo area */}
        <div className="flex items-center justify-between px-4 h-16 border-b border-neutral-100 dark:border-neutral-800/50">
          {!isCollapsed && (
            <Link href="/dashboard" className="flex items-center gap-2.5 no-underline">
              <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center text-white font-bold text-xs">
                P
              </div>
              <div className="overflow-hidden">
                <p className="text-sm font-bold text-neutral-900 dark:text-white truncate tracking-tight">
                  {tenant?.name || 'Partython.ai'}
                </p>
              </div>
            </Link>
          )}
          {isCollapsed && (
            <div className="w-8 h-8 rounded-lg bg-primary-600 flex items-center justify-center text-white font-bold text-xs mx-auto">
              P
            </div>
          )}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={clsx(
              'p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg smooth text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300',
              isCollapsed && 'mx-auto mt-2'
            )}
            aria-label="Toggle sidebar"
          >
            {isCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {/* Menu Items */}
        <nav className="flex-1 overflow-y-auto py-3 px-2.5 space-y-0.5">
          {menuItems.map((item) => {
            const Icon = item.icon
            const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`)
            return (
              <Link
                key={item.id}
                href={item.href}
                className={clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium smooth group no-underline',
                  isActive
                    ? 'bg-primary-50 dark:bg-primary-950/40 text-primary-600 dark:text-primary-400'
                    : 'text-neutral-500 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 hover:text-neutral-900 dark:hover:text-white'
                )}
                title={isCollapsed ? item.label : undefined}
              >
                <Icon size={18} className={clsx('flex-shrink-0', isActive && 'text-primary-600 dark:text-primary-400')} />
                {!isCollapsed && <span>{item.label}</span>}
              </Link>
            )
          })}
        </nav>

        {/* Logout */}
        <div className="p-3 border-t border-neutral-100 dark:border-neutral-800/50">
          <button
            onClick={handleLogout}
            className={clsx(
              'flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-[13px] font-medium text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 smooth',
              isCollapsed && 'justify-center'
            )}
          >
            <LogOut size={18} />
            {!isCollapsed && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* Spacer for content push */}
      <div className={clsx('hidden md:block flex-shrink-0', isCollapsed ? 'w-[72px]' : 'w-60')} />
    </>
  )
}

export default Sidebar
