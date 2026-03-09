import { NextRequest, NextResponse } from 'next/server'

/**
 * WooCommerce REST API Authentication Callback
 * POST /api/oauth/woocommerce/callback — WooCommerce POSTs API keys here
 *
 * After the store owner approves access, WooCommerce sends a POST request
 * to this endpoint with the generated API keys.
 *
 * WooCommerce callback payload:
 * {
 *   "key_id": 1,
 *   "user_id": "<our_state_parameter>",
 *   "consumer_key": "ck_xxxxxxxx",
 *   "consumer_secret": "cs_xxxxxxxx",
 *   "key_permissions": "read_write"
 * }
 *
 * SECURITY:
 * - Verifies user_id matches our stored state (CSRF protection)
 * - Keys stored encrypted via gateway
 * - Consumer secret never exposed to frontend
 * - Only accepts POST method (keys not in URL)
 */

const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    const {
      key_id,
      user_id,
      consumer_key,
      consumer_secret,
      key_permissions,
    } = body

    // Validate required fields
    if (!consumer_key || !consumer_secret || !user_id) {
      console.error('WooCommerce callback missing required fields')
      return NextResponse.json(
        { message: 'Missing required fields' },
        { status: 400 }
      )
    }

    // Verify state (user_id is our CSRF state parameter)
    const storedState = request.cookies.get('wc_oauth_state')?.value
    const storedStoreUrl = request.cookies.get('wc_store_url')?.value
    const authToken = request.cookies.get('oauth_token')?.value

    // Note: WooCommerce POSTs from the store server, so cookies may not
    // be present (server-to-server). We handle both cases:
    // 1. With cookies (same browser session) — full CSRF verification
    // 2. Without cookies (server POST) — store keys temporarily, verify on return_url

    if (storedState && storedState !== user_id) {
      console.error('WooCommerce callback state mismatch')
      return NextResponse.json(
        { message: 'State verification failed' },
        { status: 403 }
      )
    }

    // If we have the auth token (cookie present), register immediately
    if (authToken && storedStoreUrl) {
      // Verify the WooCommerce store is reachable with these keys
      let storeName = storedStoreUrl
      try {
        const verifyResp = await fetch(
          `${storedStoreUrl}/wp-json/wc/v3/system_status`,
          {
            headers: {
              'Authorization': `Basic ${Buffer.from(`${consumer_key}:${consumer_secret}`).toString('base64')}`,
            },
          }
        )
        if (verifyResp.ok) {
          const sysStatus = await verifyResp.json()
          storeName = sysStatus.environment?.site_title || storedStoreUrl
        }
      } catch {
        // Non-fatal — store URL is still valid from OAuth flow
      }

      // Register the WooCommerce connection via gateway
      const registerResp = await fetch(`${GATEWAY_URL}/api/v1/ecommerce/connect`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          platform: 'woocommerce',
          store_url: storedStoreUrl,
          api_key: consumer_key,
          api_secret: consumer_secret,
          metadata: {
            store_name: storeName,
            key_id: key_id,
            key_permissions: key_permissions,
          },
        }),
      })

      if (!registerResp.ok) {
        console.error('Failed to register WooCommerce via gateway:', registerResp.status)
      }

      // Clear cookies
      const response = NextResponse.json({
        success: true,
        message: 'WooCommerce store connected successfully',
      })
      response.cookies.delete('wc_oauth_state')
      response.cookies.delete('wc_store_url')
      response.cookies.delete('oauth_token')

      console.log(`WooCommerce connected: ${storedStoreUrl}`)
      return response
    }

    // Server-to-server case: Store keys temporarily in a secure session store
    // The return_url will trigger a verification on the frontend
    // We use a temporary storage approach via gateway
    try {
      const tempStoreResp = await fetch(`${GATEWAY_URL}/api/v1/ecommerce/pending`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state: user_id,
          consumer_key,
          consumer_secret,
          key_id,
          key_permissions,
          expires_in: 600, // 10 minutes
        }),
      })

      if (!tempStoreResp.ok) {
        console.error('Failed to store pending WooCommerce keys')
      }
    } catch (err) {
      console.error('Gateway pending store error:', err)
    }

    console.log(`WooCommerce callback received for state: ${user_id} (server-to-server)`)
    return NextResponse.json({
      success: true,
      message: 'Keys received, pending user verification',
    })
  } catch (error) {
    console.error('WooCommerce callback error:', error)
    return NextResponse.json(
      { message: 'Failed to process WooCommerce callback' },
      { status: 500 }
    )
  }
}
