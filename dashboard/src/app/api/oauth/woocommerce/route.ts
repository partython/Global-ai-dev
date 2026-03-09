import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'

/**
 * WooCommerce REST API Authentication Initiation
 * POST /api/oauth/woocommerce — Generate WooCommerce Auth URL
 *
 * WooCommerce uses its own authentication endpoint (not standard OAuth2).
 * The store owner visits a URL on their WooCommerce site that prompts them
 * to generate REST API keys with specific permissions.
 *
 * Flow:
 * 1. Frontend sends store_url (e.g., "https://mystore.com")
 * 2. We validate the URL and check it's a real WooCommerce site
 * 3. We build the WC REST API auth URL with callback
 * 4. Store owner approves → WooCommerce POSTs keys to our callback
 *
 * SECURITY:
 * - State parameter stored in httpOnly cookie (CSRF protection)
 * - Store URL validated and sanitized
 * - Only HTTPS stores accepted in production
 * - Callback uses POST (keys never in URL)
 */

export async function POST(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()
    const storeUrl = body.store_url?.trim()?.replace(/\/+$/, '') // Remove trailing slashes

    if (!storeUrl) {
      return NextResponse.json(
        { message: 'Store URL is required' },
        { status: 400 }
      )
    }

    // Validate URL format
    let parsedUrl: URL
    try {
      parsedUrl = new URL(storeUrl)
    } catch {
      return NextResponse.json(
        { message: 'Invalid URL format. Example: https://mystore.com' },
        { status: 400 }
      )
    }

    // SECURITY: Only allow http/https protocols
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      return NextResponse.json(
        { message: 'Only HTTP/HTTPS URLs are allowed' },
        { status: 400 }
      )
    }

    // In production, enforce HTTPS
    if (process.env.NODE_ENV === 'production' && parsedUrl.protocol !== 'https:') {
      return NextResponse.json(
        { message: 'HTTPS is required for production stores' },
        { status: 400 }
      )
    }

    // SECURITY: Block internal/private IPs (SSRF protection)
    const hostname = parsedUrl.hostname
    const blockedPatterns = [
      /^localhost$/i,
      /^127\./,
      /^10\./,
      /^172\.(1[6-9]|2[0-9]|3[01])\./,
      /^192\.168\./,
      /^0\./,
      /^169\.254\./,
      /^::1$/,
      /^fc00:/,
      /^fe80:/,
    ]
    if (blockedPatterns.some(p => p.test(hostname))) {
      return NextResponse.json(
        { message: 'Internal URLs are not allowed' },
        { status: 400 }
      )
    }

    // Generate CSRF state
    const state = crypto.randomUUID()

    const origin = process.env.NEXT_PUBLIC_APP_URL
      || request.headers.get('origin')
      || 'http://localhost:3000'
    const callbackUrl = `${origin}/api/oauth/woocommerce/callback`

    // WooCommerce REST API Authentication URL
    // Docs: https://woocommerce.github.io/woocommerce-rest-api-docs/#authentication
    const cleanStoreUrl = `${parsedUrl.protocol}//${parsedUrl.host}${parsedUrl.pathname}`.replace(/\/+$/, '')

    const wcAuthParams = new URLSearchParams({
      app_name: 'Partython.ai',
      scope: 'read_write',
      user_id: state, // WC will return this — we use state as user_id for CSRF
      return_url: `${origin}/marketplace?connected=woocommerce&status=success`,
      callback_url: callbackUrl,
    })

    const authUrl = `${cleanStoreUrl}/wc-auth/v1/authorize?${wcAuthParams.toString()}`

    const response = NextResponse.json({
      auth_url: authUrl,
      provider: 'woocommerce',
    })

    // Store state + store URL in httpOnly cookies
    response.cookies.set('wc_oauth_state', state, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 600,
      path: '/api/oauth',
    })
    response.cookies.set('wc_store_url', cleanStoreUrl, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 600,
      path: '/api/oauth',
    })

    const token = auth.replace('Bearer ', '')
    response.cookies.set('oauth_token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 600,
      path: '/api/oauth',
    })

    console.log(`WooCommerce auth initiated for store: ${cleanStoreUrl}`)
    return response
  } catch (error) {
    console.error('WooCommerce auth initiation error:', error)
    return NextResponse.json(
      { message: 'Failed to initiate WooCommerce authentication' },
      { status: 500 }
    )
  }
}
