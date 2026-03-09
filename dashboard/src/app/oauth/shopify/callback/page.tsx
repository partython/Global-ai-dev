// @ts-nocheck
'use client'

import { Suspense, useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useAuth } from '@/stores/auth'

/**
 * Shopify OAuth Callback Page (Client-Side)
 *
 * Flow:
 * 1. Shopify redirects to /api/oauth/shopify/callback (GET)
 * 2. Server redirects to this page with Shopify params in URL
 * 3. This page verifies state against sessionStorage
 * 4. Calls POST /api/oauth/shopify/callback with code + auth token
 * 5. Redirects to /channels on success
 */

function ShopifyCallbackHandler() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const token = useAuth((state) => state.token)
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing')
  const [message, setMessage] = useState('Connecting your Shopify store...')

  useEffect(() => {
    handleCallback()
  }, [])

  const handleCallback = async () => {
    try {
      const code = searchParams.get('code')
      const state = searchParams.get('state')
      const shop = searchParams.get('shop')
      const hmac = searchParams.get('hmac')
      const timestamp = searchParams.get('timestamp')

      if (!code || !shop) {
        setStatus('error')
        setMessage('Missing parameters from Shopify. Please try again.')
        setTimeout(() => router.push('/channels?connected=shopify&status=error&reason=missing_params'), 2000)
        return
      }

      // Verify state against what we stored in sessionStorage
      const storedState = sessionStorage.getItem('shopify_oauth_state')
      const storedShop = sessionStorage.getItem('shopify_oauth_shop')

      if (!storedState || storedState !== state) {
        console.warn('Shopify state mismatch — stored:', storedState, 'received:', state)
        // If HMAC is present, we can still proceed (Shopify's own verification)
        if (!hmac) {
          setStatus('error')
          setMessage('Security verification failed. Please try again.')
          setTimeout(() => router.push('/channels?connected=shopify&status=error&reason=state_mismatch'), 2000)
          return
        }
        console.log('Proceeding with HMAC verification despite state mismatch')
      }

      if (storedShop && storedShop !== shop) {
        setStatus('error')
        setMessage('Shop domain mismatch. Please try again.')
        setTimeout(() => router.push('/channels?connected=shopify&status=error&reason=shop_mismatch'), 2000)
        return
      }

      if (!token) {
        setStatus('error')
        setMessage('Your session has expired. Please log in again.')
        setTimeout(() => router.push('/login'), 2000)
        return
      }

      setMessage('Exchanging authorization code...')

      // Collect ALL search params (Shopify signs all of them for HMAC)
      const allParams: Record<string, string> = {}
      searchParams.forEach((value, key) => {
        allParams[key] = value
      })

      // Call our server-side API to exchange code for access token
      const resp = await fetch('/api/oauth/shopify/callback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...allParams,
          auth_token: token,
        }),
      })

      const data = await resp.json()

      if (resp.ok && data.success) {
        // Clean up sessionStorage
        sessionStorage.removeItem('shopify_oauth_state')
        sessionStorage.removeItem('shopify_oauth_shop')

        setStatus('success')
        setMessage(`Connected ${data.shop_name || shop}!`)
        setTimeout(() => router.push('/channels?connected=shopify&status=success&channels=shopify'), 1500)
      } else {
        setStatus('error')
        setMessage(data.message || 'Failed to connect Shopify store')
        setTimeout(() => router.push(`/channels?connected=shopify&status=error&reason=${encodeURIComponent(data.message || 'unknown')}`), 2500)
      }
    } catch (error) {
      console.error('Shopify callback error:', error)
      setStatus('error')
      setMessage('An unexpected error occurred. Please try again.')
      setTimeout(() => router.push('/channels?connected=shopify&status=error&reason=server_error'), 2000)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-950">
      <div className="text-center p-8 max-w-md">
        {status === 'processing' && (
          <>
            <div className="w-12 h-12 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Connecting Shopify
            </h2>
            <p className="text-gray-600 dark:text-gray-400">{message}</p>
          </>
        )}
        {status === 'success' && (
          <>
            <div className="w-12 h-12 bg-emerald-500 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Success!
            </h2>
            <p className="text-gray-600 dark:text-gray-400">{message}</p>
          </>
        )}
        {status === 'error' && (
          <>
            <div className="w-12 h-12 bg-red-500 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
              Connection Failed
            </h2>
            <p className="text-gray-600 dark:text-gray-400">{message}</p>
          </>
        )}
      </div>
    </div>
  )
}

export default function ShopifyCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-950">
          <div className="w-12 h-12 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin" />
        </div>
      }
    >
      <ShopifyCallbackHandler />
    </Suspense>
  )
}
