'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { ArrowRight, Sparkles, Eye, EyeOff, CheckCircle } from 'lucide-react'
import { useAuthStore } from '@/stores/auth'
import { registerUser } from '@/lib/auth'

export default function RegisterPage() {
  const router = useRouter()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [form, setForm] = useState({ businessName: '', name: '', email: '', password: '' })
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const update = (field: string, value: string) => setForm((f) => ({ ...f, [field]: value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const response = await registerUser({
        businessName: form.businessName,
        fullName: form.name,
        email: form.email,
        password: form.password,
      })
      setAuth({
        user: response.user,
        tenant: response.tenant,
        token: response.token,
      })
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleDemoLogin = () => {
    setAuth({
      user: { id: 'demo-1', email: 'admin@currentglobal.com', name: 'Demo Admin', role: 'admin' },
      tenant: { id: 'tenant-1', name: 'Partython.ai', plan: 'enterprise', status: 'active', createdAt: new Date(), updatedAt: new Date() },
      token: 'demo-token-xyz',
    })
    router.push('/dashboard')
  }

  const benefits = [
    '30-day free trial, no credit card',
    'All 6 channels included',
    'AI trained on your business in 5 min',
    'Cancel anytime, export your data',
  ]

  return (
    <div className="min-h-screen flex">
      {/* Left — Brand panel */}
      <div className="hidden lg:flex lg:w-[45%] relative bg-neutral-900 overflow-hidden">
        <div className="absolute inset-0 dot-grid opacity-20" />
        <div className="absolute bottom-1/4 left-1/3 w-[500px] h-[500px] bg-accent-600/15 rounded-full blur-3xl" />

        <div className="relative z-10 flex flex-col justify-between p-12 xl:p-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 no-underline">
            <div className="w-9 h-9 rounded-xl bg-primary-600 flex items-center justify-center text-white font-bold text-sm">P</div>
            <span className="text-lg font-bold text-white tracking-tight">Partython.ai</span>
          </Link>

          {/* Value props */}
          <div>
            <h1 className="text-4xl xl:text-5xl font-bold text-white leading-tight">
              Start selling with{' '}
              <span className="text-accent-400">AI today</span>
            </h1>
            <p className="mt-4 text-neutral-400 text-lg leading-relaxed max-w-md">
              Set up your AI-powered sales team in under 5 minutes. No engineering required.
            </p>

            <div className="mt-8 space-y-3">
              {benefits.map((b) => (
                <div key={b} className="flex items-center gap-3">
                  <CheckCircle size={16} className="text-green-400 flex-shrink-0" />
                  <span className="text-sm text-neutral-300">{b}</span>
                </div>
              ))}
            </div>
          </div>

          <p className="text-xs text-neutral-600">&copy; 2026 Partython.ai Technologies</p>
        </div>
      </div>

      {/* Right — Register form */}
      <div className="flex-1 flex items-center justify-center p-6 md:p-12 bg-white dark:bg-neutral-950">
        <motion.div
          className="w-full max-w-[400px]"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          {/* Mobile logo */}
          <div className="lg:hidden mb-8">
            <Link href="/" className="flex items-center gap-2.5 no-underline">
              <div className="w-9 h-9 rounded-xl bg-primary-600 flex items-center justify-center text-white font-bold text-sm">P</div>
              <span className="text-lg font-bold text-neutral-900 dark:text-white tracking-tight">Partython.ai</span>
            </Link>
          </div>

          <h2 className="text-2xl font-bold text-neutral-900 dark:text-white">Create your account</h2>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1.5">Start your 30-day free trial</p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-3 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-200 dark:border-red-800/30"
              >
                {error}
              </motion.div>
            )}

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">Business Name</label>
              <input
                type="text"
                value={form.businessName}
                onChange={(e) => update('businessName', e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 input-ring outline-none smooth text-sm"
                placeholder="Your Company"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">Full Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => update('name', e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 input-ring outline-none smooth text-sm"
                placeholder="John Doe"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">Work Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => update('email', e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 input-ring outline-none smooth text-sm"
                placeholder="you@company.com"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => update('password', e.target.value)}
                  className="w-full px-4 py-3 pr-11 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 input-ring outline-none smooth text-sm"
                  placeholder="Min 8 characters"
                  required
                  minLength={8}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 py-3 bg-primary-600 hover:bg-primary-700 text-white font-semibold text-sm rounded-xl smooth shadow-sm shadow-primary-600/25 disabled:opacity-50 disabled:cursor-not-allowed mt-2"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  Create Account
                  <ArrowRight size={16} />
                </>
              )}
            </button>

            <p className="text-[11px] text-neutral-400 dark:text-neutral-500 text-center">
              By creating an account, you agree to our{' '}
              <a href="#" className="underline no-underline hover:text-neutral-600">Terms of Service</a>{' '}
              and{' '}
              <a href="#" className="underline no-underline hover:text-neutral-600">Privacy Policy</a>
            </p>
          </form>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-neutral-200 dark:border-neutral-800" />
            </div>
            <div className="relative flex justify-center">
              <span className="px-3 bg-white dark:bg-neutral-950 text-xs text-neutral-400">or</span>
            </div>
          </div>

          {/* Demo mode */}
          <button
            onClick={handleDemoLogin}
            className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-primary-200 dark:border-primary-800/40 text-primary-600 dark:text-primary-400 font-semibold text-sm hover:bg-primary-50 dark:hover:bg-primary-950/30 smooth"
          >
            <Sparkles size={16} />
            Try Demo Mode
          </button>

          <p className="text-center text-sm text-neutral-500 dark:text-neutral-400 mt-8">
            Already have an account?{' '}
            <Link href="/login" className="text-primary-600 dark:text-primary-400 font-semibold no-underline hover:text-primary-700">
              Sign in
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  )
}
