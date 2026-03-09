// @ts-nocheck
'use client'

import React, { useState, useCallback } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowRight, Sparkles, Mail, ArrowLeft } from 'lucide-react'
import { useAuthStore } from '@/stores/auth'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:9000'

type Step = 'choose' | 'email' | 'otp' | 'profile'

export default function LoginPage() {
  const router = useRouter()
  const setAuth = useAuthStore((s) => s.setAuth)

  const [step, setStep] = useState<Step>('choose')
  const [email, setEmail] = useState('')
  const [otpCode, setOtpCode] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [businessName, setBusinessName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [isNewUser, setIsNewUser] = useState(false)

  // ─── Google Sign-In ───
  const handleGoogleLogin = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      // Load Google Sign-In SDK dynamically
      const googleClientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID
      if (!googleClientId) {
        // Fallback: server-side OAuth redirect flow
        // First check if the server has Google OAuth configured
        try {
          const checkRes = await fetch(`${API_URL}/api/v1/auth/oauth/google/redirect`, {
            method: 'GET',
            redirect: 'manual', // Don't auto-follow — we want the redirect URL
          })
          if (checkRes.status === 503) {
            setError('Google Sign-In is not configured yet. Please use Email OTP instead.')
            setLoading(false)
            return
          }
          // Server returned a redirect to Google — follow it
          window.location.href = `${API_URL}/api/v1/auth/oauth/google/redirect`
        } catch {
          setError('Google Sign-In is not available. Please use Email OTP instead.')
          setLoading(false)
        }
        return
      }

      // Use Google Identity Services
      // @ts-ignore - google.accounts loaded via script
      if (typeof google !== 'undefined' && google.accounts) {
        google.accounts.id.initialize({
          client_id: googleClientId,
          callback: async (response: any) => {
            try {
              const res = await fetch(`${API_URL}/api/v1/auth/oauth/google`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ credential: response.credential }),
              })
              const data = await res.json()
              if (!res.ok) throw new Error(data.detail || 'Google login failed')

              setAuth({
                user: data.user,
                tenant: data.user,
                token: data.access_token,
              })
              router.push('/dashboard')
            } catch (err: any) {
              setError(err.message)
              setLoading(false)
            }
          },
        })
        google.accounts.id.prompt()
      } else {
        setError('Google Sign-In not available. Please try Email OTP.')
      }
    } catch (err: any) {
      setError(err.message || 'Google sign-in failed')
    } finally {
      setLoading(false)
    }
  }, [router, setAuth])

  // ─── Request OTP ───
  const handleRequestOTP = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/api/v1/auth/otp/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Failed to send OTP')

      setStep('otp')
    } catch (err: any) {
      setError(err.message || 'Failed to send verification code')
    } finally {
      setLoading(false)
    }
  }

  // ─── Verify OTP ───
  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const body: any = { email, code: otpCode }
      if (isNewUser) {
        body.first_name = firstName
        body.last_name = lastName
        body.business_name = businessName
      }

      const res = await fetch(`${API_URL}/api/v1/auth/otp/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()

      if (!res.ok) {
        if (data.detail?.includes('first_name') || data.detail?.includes('business_name')) {
          // New user — need profile info
          setIsNewUser(true)
          setStep('profile')
          setLoading(false)
          return
        }
        throw new Error(data.detail || 'Verification failed')
      }

      setAuth({
        user: data.user,
        tenant: data.user,
        token: data.access_token,
      })
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.message || 'Invalid code')
    } finally {
      setLoading(false)
    }
  }

  // ─── Complete Profile (new users) ───
  const handleCompleteProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch(`${API_URL}/api/v1/auth/otp/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          code: otpCode,
          first_name: firstName,
          last_name: lastName,
          business_name: businessName,
          country: 'IN',
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Registration failed')

      setAuth({
        user: data.user,
        tenant: data.user,
        token: data.access_token,
      })
      router.push('/dashboard')
    } catch (err: any) {
      setError(err.message || 'Failed to create account')
    } finally {
      setLoading(false)
    }
  }

  // ─── Demo Login ───
  const handleDemoLogin = () => {
    setAuth({
      user: { id: 'demo-1', email: 'admin@partython.in', name: 'Demo Admin', role: 'admin' },
      tenant: { id: 'tenant-1', name: 'Partython.ai', plan: 'enterprise', status: 'active', createdAt: new Date(), updatedAt: new Date() },
      token: 'demo-token-xyz',
    })
    router.push('/dashboard')
  }

  return (
    <div className="min-h-screen flex">
      {/* Left — Brand panel */}
      <div className="hidden lg:flex lg:w-[45%] relative bg-neutral-900 overflow-hidden">
        <div className="absolute inset-0 dot-grid opacity-20" />
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[500px] h-[500px] bg-primary-600/20 rounded-full blur-3xl" />

        <div className="relative z-10 flex flex-col justify-between p-12 xl:p-16">
          <Link href="/" className="flex items-center gap-2.5 no-underline">
            <div className="w-9 h-9 rounded-xl bg-primary-600 flex items-center justify-center text-white font-bold text-sm">P</div>
            <span className="text-lg font-bold text-white tracking-tight">Partython.ai</span>
          </Link>

          <div>
            <h1 className="text-4xl xl:text-5xl font-bold text-white leading-tight">
              Your AI Sales Team,{' '}
              <span className="text-primary-400">Always On</span>
            </h1>
            <p className="mt-4 text-neutral-400 text-lg leading-relaxed max-w-md">
              Manage WhatsApp, Email, Voice, Instagram, Facebook, and Web Chat from a single dashboard.
            </p>
            <div className="mt-8 flex items-center gap-4">
              <div className="flex -space-x-2">
                {['AM', 'SK', 'VP', 'LC'].map((init, i) => (
                  <div key={i} className="w-8 h-8 rounded-full border-2 border-neutral-900 bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center text-[10px] font-bold text-white">
                    {init}
                  </div>
                ))}
              </div>
              <p className="text-sm text-neutral-400">
                <span className="text-white font-semibold">1,000+</span> sales teams trust Priya
              </p>
            </div>
          </div>

          <p className="text-xs text-neutral-600">&copy; 2026 Partython.ai Technologies</p>
        </div>
      </div>

      {/* Right — Auth form */}
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

          <AnimatePresence mode="wait">
            {/* ─── Step: Choose method ─── */}
            {step === 'choose' && (
              <motion.div key="choose" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <h2 className="text-2xl font-bold text-neutral-900 dark:text-white">Welcome</h2>
                <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1.5">Sign in or create your account</p>

                {error && (
                  <div className="mt-4 p-3 text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-200 dark:border-red-800/30">
                    {error}
                  </div>
                )}

                <div className="mt-8 space-y-3">
                  {/* Google Sign-In */}
                  <button
                    onClick={handleGoogleLogin}
                    disabled={loading}
                    className="w-full flex items-center justify-center gap-3 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white font-medium text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800 smooth disabled:opacity-50"
                  >
                    <svg viewBox="0 0 24 24" width="18" height="18">
                      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
                      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                    </svg>
                    Continue with Google
                  </button>

                  {/* Divider */}
                  <div className="relative my-4">
                    <div className="absolute inset-0 flex items-center">
                      <div className="w-full border-t border-neutral-200 dark:border-neutral-800" />
                    </div>
                    <div className="relative flex justify-center">
                      <span className="px-3 bg-white dark:bg-neutral-950 text-xs text-neutral-400">or</span>
                    </div>
                  </div>

                  {/* Email OTP */}
                  <button
                    onClick={() => setStep('email')}
                    className="w-full flex items-center justify-center gap-2 py-3 bg-primary-600 hover:bg-primary-700 text-white font-semibold text-sm rounded-xl smooth shadow-sm shadow-primary-600/25"
                  >
                    <Mail size={16} />
                    Continue with Email
                  </button>
                </div>

                {/* Demo */}
                <div className="relative my-6">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-neutral-200 dark:border-neutral-800" />
                  </div>
                  <div className="relative flex justify-center">
                    <span className="px-3 bg-white dark:bg-neutral-950 text-xs text-neutral-400">or</span>
                  </div>
                </div>

                <button
                  onClick={handleDemoLogin}
                  className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-primary-200 dark:border-primary-800/40 text-primary-600 dark:text-primary-400 font-semibold text-sm hover:bg-primary-50 dark:hover:bg-primary-950/30 smooth"
                >
                  <Sparkles size={16} />
                  Enter Demo Mode
                </button>
              </motion.div>
            )}

            {/* ─── Step: Enter Email ─── */}
            {step === 'email' && (
              <motion.div key="email" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <button onClick={() => { setStep('choose'); setError('') }} className="text-sm text-neutral-500 flex items-center gap-1 mb-6 hover:text-neutral-700">
                  <ArrowLeft size={14} /> Back
                </button>
                <h2 className="text-2xl font-bold text-neutral-900 dark:text-white">Enter your email</h2>
                <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1.5">{"We'll send you a 6-digit verification code"}</p>

                {error && (
                  <div className="mt-4 p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-200 dark:border-red-800/30">{error}</div>
                )}

                <form onSubmit={handleRequestOTP} className="mt-6 space-y-4">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 outline-none text-sm"
                    placeholder="you@company.com"
                    required
                    autoFocus
                  />
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full flex items-center justify-center gap-2 py-3 bg-primary-600 hover:bg-primary-700 text-white font-semibold text-sm rounded-xl smooth disabled:opacity-50"
                  >
                    {loading ? (
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <>Send Code <ArrowRight size={16} /></>
                    )}
                  </button>
                </form>
              </motion.div>
            )}

            {/* ─── Step: Enter OTP ─── */}
            {step === 'otp' && (
              <motion.div key="otp" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <button onClick={() => { setStep('email'); setError(''); setOtpCode('') }} className="text-sm text-neutral-500 flex items-center gap-1 mb-6 hover:text-neutral-700">
                  <ArrowLeft size={14} /> Back
                </button>
                <h2 className="text-2xl font-bold text-neutral-900 dark:text-white">Check your email</h2>
                <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1.5">
                  Enter the 6-digit code sent to <span className="font-medium text-neutral-700 dark:text-neutral-300">{email}</span>
                </p>

                {error && (
                  <div className="mt-4 p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-200 dark:border-red-800/30">{error}</div>
                )}

                <form onSubmit={handleVerifyOTP} className="mt-6 space-y-4">
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="\d{6}"
                    maxLength={6}
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    className="w-full px-4 py-4 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 outline-none text-2xl text-center tracking-[0.5em] font-mono"
                    placeholder="000000"
                    required
                    autoFocus
                  />
                  <button
                    type="submit"
                    disabled={loading || otpCode.length !== 6}
                    className="w-full flex items-center justify-center gap-2 py-3 bg-primary-600 hover:bg-primary-700 text-white font-semibold text-sm rounded-xl smooth disabled:opacity-50"
                  >
                    {loading ? (
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <>Verify & Sign In <ArrowRight size={16} /></>
                    )}
                  </button>
                </form>

                <button
                  onClick={handleRequestOTP}
                  className="w-full mt-3 text-sm text-primary-600 dark:text-primary-400 hover:underline"
                >
                  Resend code
                </button>
              </motion.div>
            )}

            {/* ─── Step: New User Profile ─── */}
            {step === 'profile' && (
              <motion.div key="profile" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <h2 className="text-2xl font-bold text-neutral-900 dark:text-white">Almost there!</h2>
                <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1.5">Tell us a bit about yourself to get started</p>

                {error && (
                  <div className="mt-4 p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-200 dark:border-red-800/30">{error}</div>
                )}

                <form onSubmit={handleCompleteProfile} className="mt-6 space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <input
                      type="text"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      className="px-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 outline-none text-sm"
                      placeholder="First name"
                      required
                      autoFocus
                    />
                    <input
                      type="text"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      className="px-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 outline-none text-sm"
                      placeholder="Last name"
                    />
                  </div>
                  <input
                    type="text"
                    value={businessName}
                    onChange={(e) => setBusinessName(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-white placeholder-neutral-400 outline-none text-sm"
                    placeholder="Business name"
                    required
                  />
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full flex items-center justify-center gap-2 py-3 bg-primary-600 hover:bg-primary-700 text-white font-semibold text-sm rounded-xl smooth disabled:opacity-50"
                  >
                    {loading ? (
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    ) : (
                      <>Create Account <ArrowRight size={16} /></>
                    )}
                  </button>
                </form>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </div>
  )
}
