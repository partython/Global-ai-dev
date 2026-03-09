'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { Bell, Moon, Sun, Menu, X, Search } from 'lucide-react'
import { useAuth } from '@/stores/auth'
import { useAuthActions } from '@/lib/auth'

export const Header: React.FC<{ isDashboard?: boolean }> = ({ isDashboard = false }) => {
  const [isDarkMode, setIsDarkMode] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false)
  const user = useAuth((state) => state.user)
  const tenant = useAuth((state) => state.tenant)
  const { handleLogout } = useAuthActions()

  const toggleDarkMode = () => {
    setIsDarkMode(!isDarkMode)
    document.documentElement.classList.toggle('dark')
  }

  return (
    <>
      {/* Desktop Header */}
      <header className="sticky top-0 z-30 bg-white/80 dark:bg-neutral-950/80 backdrop-blur-xl border-b border-neutral-100 dark:border-neutral-800/50 hidden md:block">
        <div className="flex items-center justify-between px-6 h-16">
          {/* Search (dashboard only) */}
          {isDashboard ? (
            <div className="relative max-w-xs w-full">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
              <input
                type="text"
                placeholder="Search conversations, customers..."
                className="w-full pl-9 pr-4 py-2 text-sm bg-neutral-50 dark:bg-neutral-900 border border-neutral-200/50 dark:border-neutral-800 rounded-lg placeholder-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary-500/30 focus:border-primary-500 smooth"
              />
            </div>
          ) : (
            <div className="flex-1" />
          )}

          {/* Right Side */}
          <div className="flex items-center gap-2">
            <button
              onClick={toggleDarkMode}
              className="p-2.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-xl smooth text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
              aria-label="Toggle dark mode"
            >
              {isDarkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            {isDashboard && (
              <>
                <button className="relative p-2.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-xl smooth text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300">
                  <Bell size={18} />
                  <span className="absolute top-2 right-2 h-2 w-2 bg-primary-500 rounded-full ring-2 ring-white dark:ring-neutral-950" />
                </button>

                {/* Profile */}
                <div className="relative ml-1">
                  <button
                    onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
                    className="flex items-center gap-2.5 py-1.5 px-2.5 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-xl smooth"
                  >
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-white text-xs font-bold">
                      {user?.name?.split(' ').map(n => n[0]).join('') || 'U'}
                    </div>
                    <div className="hidden xl:block text-left">
                      <p className="text-sm font-semibold text-neutral-900 dark:text-white leading-tight">{user?.name || 'User'}</p>
                      <p className="text-[11px] text-neutral-400 leading-tight">{tenant?.name}</p>
                    </div>
                  </button>

                  {isProfileMenuOpen && (
                    <div className="absolute right-0 mt-2 w-52 bg-white dark:bg-neutral-900 rounded-xl shadow-xl border border-neutral-200/80 dark:border-neutral-800 overflow-hidden animate-fade-in">
                      <div className="p-4 border-b border-neutral-100 dark:border-neutral-800">
                        <p className="font-semibold text-sm text-neutral-900 dark:text-white">{user?.name}</p>
                        <p className="text-xs text-neutral-400 mt-0.5">{user?.email}</p>
                      </div>
                      <Link
                        href="/settings"
                        className="block px-4 py-2.5 text-sm text-neutral-600 dark:text-neutral-400 hover:bg-neutral-50 dark:hover:bg-neutral-800 no-underline smooth"
                        onClick={() => setIsProfileMenuOpen(false)}
                      >
                        Settings
                      </Link>
                      <button
                        onClick={() => {
                          handleLogout()
                          setIsProfileMenuOpen(false)
                        }}
                        className="w-full text-left px-4 py-2.5 text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 smooth"
                      >
                        Logout
                      </button>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Mobile Header */}
      <header className="sticky top-0 z-30 bg-white/80 dark:bg-neutral-950/80 backdrop-blur-xl border-b border-neutral-100 dark:border-neutral-800/50 md:hidden">
        <div className="flex items-center justify-between px-4 h-14">
          <Link href="/" className="flex items-center gap-2 no-underline">
            <div className="w-7 h-7 rounded-lg bg-primary-600 flex items-center justify-center text-white font-bold text-[10px]">P</div>
            <span className="font-bold text-sm text-neutral-900 dark:text-white">{tenant?.name || 'Partython.ai'}</span>
          </Link>
          <div className="flex items-center gap-1">
            <button onClick={toggleDarkMode} className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg">
              {isDarkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)} className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg">
              {isMobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
      </header>

      {/* Mobile Menu */}
      {isMobileMenuOpen && isDashboard && (
        <div className="md:hidden bg-white dark:bg-neutral-950 border-b border-neutral-100 dark:border-neutral-800/50 p-4 space-y-2">
          <Link href="/settings" className="block text-sm font-medium py-2 no-underline text-neutral-700 dark:text-neutral-300">Settings</Link>
          <button onClick={handleLogout} className="w-full text-left text-sm font-medium text-red-500 py-2">Logout</button>
        </div>
      )}
    </>
  )
}

export default Header
