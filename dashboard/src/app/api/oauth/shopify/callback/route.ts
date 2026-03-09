import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'

/**
 * Shopify OAuth Callback — Server-side token exchange
 *
 * TWO modes:
 * 1. GET  — Shopify redirects browser here. We pass params to the client-side page.
 * 2. POST — Client-side page sends { code, shop, hmac, auth_token } after verifying state.
 *
 * SECURITY:
 * - HMAC verified server-side with Shopify API Secret
 * - State verified client-side (sessionStorage, same as Google OAuth)
 * - API Secret never exposed to frontend
 */

const SHOPIFY_CLIENT_ID = process.env.SHOPIFY_CLIENT_ID || ''
const SHOPIFY_CLIENT_SECRET = process.env.SHOPIFY_CLIENT_SECRET || ''
const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'
const PUBLIC_APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'

// GET — Shopify redirects the browser here. Forward params to the client-side callback page.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)

  // Pass all Shopify params to our client-side callback page
  const params = new URLSearchParams()
  for (const [key, value] of searchParams.entries()) {
    params.set(key, value)
  }

  return NextResponse.redirect(`${PUBLIC_APP_URL}/oauth/shopify/callback?${params.toString()}`)
}

// POST — Client-side page calls this after verifying state in sessionStorage
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { code, shop, hmac, auth_token } = body

    if (!code || !shop) {
      return NextResponse.json({ message: 'Missing required parameters' }, { status: 400 })
    }

    if (!auth_token) {
      return NextResponse.json({ message: 'Authentication required' }, { status: 401 })
    }

    // Verify HMAC signature from Shopify
    // Shopify signs ALL query params except 'hmac' and 'signature' — we must include all of them
    if (hmac && SHOPIFY_CLIENT_SECRET) {
      const verifyParams: Record<string, string> = {}
      for (const [key, value] of Object.entries(body)) {
        // Skip non-Shopify params and the hmac/signature themselves
        if (key === 'hmac' || key === 'signature' || key === 'auth_token') continue
        if (typeof value === 'string') {
          verifyParams[key] = value
        }
      }

      const sortedParams = Object.keys(verifyParams)
        .sort()
        .map(k => `${k}=${verifyParams[k]}`)
        .join('&')

      const computed = crypto
        .createHmac('sha256', SHOPIFY_CLIENT_SECRET)
        .update(sortedParams)
        .digest('hex')

      if (computed !== hmac) {
        console.error('Shopify HMAC failed — computed:', computed, 'received:', hmac, 'input:', sortedParams)
        return NextResponse.json({ message: 'HMAC verification failed' }, { status: 403 })
      }
    }

    // Exchange authorization code for permanent access token
    const tokenResp = await fetch(`https://${shop}/admin/oauth/access_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client_id: SHOPIFY_CLIENT_ID,
        client_secret: SHOPIFY_CLIENT_SECRET,
        code: code,
      }),
    })

    const tokenData = await tokenResp.json()

    if (!tokenData.access_token) {
      console.error('Shopify token exchange failed:', tokenData)
      return NextResponse.json(
        { message: 'Token exchange failed', detail: tokenData },
        { status: 502 }
      )
    }

    // Get shop info for display
    let shopName = shop
    try {
      const shopResp = await fetch(`https://${shop}/admin/api/2024-01/shop.json`, {
        headers: { 'X-Shopify-Access-Token': tokenData.access_token },
      })
      const shopData = await shopResp.json()
      shopName = shopData.shop?.name || shop
    } catch {}

    // Register the shopify channel via gateway
    const registerResp = await fetch(`${GATEWAY_URL}/api/v1/channels/register`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${auth_token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: 'shopify',
        enabled: true,
        config: {
          shop_domain: shop,
          shop_name: shopName,
          access_token: tokenData.access_token,
          scope: tokenData.scope,
        },
        credentials_encrypted: true,
      }),
    })

    let registerResult = null
    try {
      registerResult = await registerResp.json()
    } catch {}

    console.log(`Shopify OAuth complete for shop: ${shop} (${shopName})`)

    return NextResponse.json({
      success: true,
      shop_domain: shop,
      shop_name: shopName,
      scope: tokenData.scope,
      channel_registered: registerResp.ok,
    })
  } catch (error) {
    console.error('Shopify OAuth callback error:', error)
    return NextResponse.json(
      { message: 'Server error during Shopify OAuth', detail: String(error) },
      { status: 500 }
    )
  }
}
