import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'

/**
 * Shopify OAuth Initiation
 * POST /api/oauth/shopify — Generate Shopify Admin OAuth URL
 *
 * Returns { auth_url, state } — client stores state in sessionStorage
 * before redirecting (no httpOnly cookies needed).
 *
 * SECURITY:
 * - State generated server-side with crypto.randomUUID()
 * - HMAC verified on callback
 * - Shopify API Secret never exposed to frontend
 */

const SHOPIFY_CLIENT_ID = process.env.SHOPIFY_CLIENT_ID || ''
const SHOPIFY_SCOPES = [
  // Customers
  'read_customers',
  'write_customers',
  // Orders (includes fulfillments, refunds)
  'read_orders',
  'write_orders',
  'read_draft_orders',
  'write_draft_orders',
  // Products & Inventory
  'read_products',
  'write_products',
  'read_inventory',
  'read_locations',
  // Fulfillment
  'read_fulfillments',
  // Marketing & Analytics
  'read_analytics',
  'read_marketing_events',
  'read_price_rules',
  'read_discounts',
  // Checkouts (abandoned carts)
  'read_checkouts',
  // Content
  'read_content',
  // Webhooks
  'read_webhooks',
  'write_webhooks',
].join(',')

export async function POST(request: NextRequest) {
  try {
    if (!SHOPIFY_CLIENT_ID) {
      return NextResponse.json(
        { message: 'Shopify App not configured. Set SHOPIFY_CLIENT_ID in environment.' },
        { status: 503 }
      )
    }

    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()
    const shopDomain = body.shop_domain?.trim()?.toLowerCase()

    if (!shopDomain || !shopDomain.includes('.myshopify.com')) {
      return NextResponse.json(
        { message: 'Invalid Shopify domain. Must be in format: yourstore.myshopify.com' },
        { status: 400 }
      )
    }

    // SECURITY: Validate shop domain format (prevent open redirect)
    if (!/^[a-z0-9-]+\.myshopify\.com$/.test(shopDomain)) {
      return NextResponse.json(
        { message: 'Invalid shop domain format' },
        { status: 400 }
      )
    }

    const state = crypto.randomUUID()

    // Always use public URL for redirect_uri — Docker containers resolve request.url to internal hostnames
    const publicUrl = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'
    const redirectUri = `${publicUrl}/api/oauth/shopify/callback`

    const params = new URLSearchParams({
      client_id: SHOPIFY_CLIENT_ID,
      scope: SHOPIFY_SCOPES,
      redirect_uri: redirectUri,
      state: state,
      'grant_options[]': 'per-user',
    })

    const authUrl = `https://${shopDomain}/admin/oauth/authorize?${params.toString()}`

    // Return state + shop_domain — client stores them in sessionStorage
    // No cookies needed (they were unreliable across the OAuth redirect flow)
    console.log(`Shopify OAuth initiated for shop: ${shopDomain}`)
    return NextResponse.json({
      auth_url: authUrl,
      state: state,
      shop_domain: shopDomain,
      provider: 'shopify',
    })
  } catch (error) {
    console.error('Shopify OAuth initiation error:', error)
    return NextResponse.json(
      { message: 'Failed to initiate Shopify OAuth' },
      { status: 500 }
    )
  }
}
