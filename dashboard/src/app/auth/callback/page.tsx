// @ts-nocheck
'use client'

import { Suspense, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuthStore } from '@/stores/auth'

function AuthCallbackHandler() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const setAuth = useAuthStore((s) => s.setAuth)

  useEffect(() => {
    const token = searchParams.get('token')
    const error = searchParams.get('error')

    if (error) {
      router.replace(`/login?error=${encodeURIComponent(error)}`)
      return
    }

    if (token) {
      try {
        const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))

        setAuth({
          user: {
            id: payload.sub || payload.user_id,
            email: payload.email || '',
            name: payload.name || `${payload.first_name || ''} ${payload.last_name || ''}`.trim(),
            role: payload.role || 'admin',
          },
          tenant: {
            id: payload.tenant_id || '',
            name: payload.tenant_name || '',
          },
          token,
        })

        router.replace('/dashboard')
      } catch {
        router.replace('/login?error=invalid_token')
      }
    } else {
      router.replace('/login?error=missing_token')
    }
  }, [searchParams, setAuth, router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-white dark:bg-neutral-950">
      <div className="text-center">
        <div className="w-8 h-8 border-2 border-primary-600/30 border-t-primary-600 rounded-full animate-spin mx-auto" />
        <p className="mt-4 text-sm text-neutral-500">Signing you in...</p>
      </div>
    </div>
  )
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-neutral-950">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-primary-600/30 border-t-primary-600 rounded-full animate-spin mx-auto" />
          <p className="mt-4 text-sm text-neutral-500">Loading...</p>
        </div>
      </div>
    }>
      <AuthCallbackHandler />
    </Suspense>
  )
}
