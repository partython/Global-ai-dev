import { NextRequest, NextResponse } from 'next/server'

/**
 * Meta OAuth Callback
 * GET /api/oauth/meta/callback — Facebook redirects here after user authorizes
 *
 * Flow:
 * 1. Verify state parameter matches cookie (CSRF protection)
 * 2. Exchange authorization code for short-lived user access token
 * 3. Exchange short-lived token for long-lived token (60 days)
 * 4. Fetch connected pages, WhatsApp accounts, Instagram accounts
 * 5. Register each connected channel via gateway → channel_router
 * 6. Redirect to /channels with success status
 *
 * SECURITY:
 * - State verified against httpOnly cookie
 * - Meta App Secret used server-side only (never exposed)
 * - Credentials stored encrypted via channel_router
 * - No tokens in URL parameters after initial exchange
 */

const META_APP_ID = process.env.META_APP_ID || ''
const META_APP_SECRET = process.env.META_APP_SECRET || ''
const META_GRAPH_VERSION = 'v18.0'
const GRAPH_API = `https://graph.facebook.com/${META_GRAPH_VERSION}`
const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const error = searchParams.get('error')
    const errorReason = searchParams.get('error_reason')

    // Handle user denial
    if (error) {
      console.warn(`Meta OAuth denied: ${error} - ${errorReason}`)
      return NextResponse.redirect(
        new URL(`/channels?connected=meta&status=denied&reason=${encodeURIComponent(errorReason || error)}`, request.url)
      )
    }

    if (!code || !state) {
      return NextResponse.redirect(
        new URL('/channels?connected=meta&status=error&reason=missing_params', request.url)
      )
    }

    // SECURITY: Verify state matches the httpOnly cookie (CSRF protection)
    const storedState = request.cookies.get('oauth_state')?.value
    if (!storedState || storedState !== state) {
      console.error('OAuth state mismatch — possible CSRF attack')
      return NextResponse.redirect(
        new URL('/channels?connected=meta&status=error&reason=state_mismatch', request.url)
      )
    }

    // Retrieve the auth token from cookie
    const authToken = request.cookies.get('oauth_token')?.value
    if (!authToken) {
      return NextResponse.redirect(
        new URL('/channels?connected=meta&status=error&reason=session_expired', request.url)
      )
    }

    // Determine redirect URI (must match exactly what was sent in initiation)
    const origin = process.env.NEXT_PUBLIC_APP_URL
      || process.env.NEXTAUTH_URL
      || new URL(request.url).origin
    const redirectUri = `${origin}/api/oauth/meta/callback`

    // Step 1: Exchange code for short-lived user access token
    const tokenParams = new URLSearchParams({
      client_id: META_APP_ID,
      redirect_uri: redirectUri,
      client_secret: META_APP_SECRET,
      code: code,
    })

    const tokenResp = await fetch(
      `${GRAPH_API}/oauth/access_token?${tokenParams.toString()}`
    )
    const tokenData = await tokenResp.json()

    if (tokenData.error) {
      console.error('Meta token exchange failed:', tokenData.error.message)
      return NextResponse.redirect(
        new URL(`/channels?connected=meta&status=error&reason=token_exchange_failed`, request.url)
      )
    }

    const shortLivedToken = tokenData.access_token

    // Step 2: Exchange for long-lived token (60 days)
    const longLivedParams = new URLSearchParams({
      grant_type: 'fb_exchange_token',
      client_id: META_APP_ID,
      client_secret: META_APP_SECRET,
      fb_exchange_token: shortLivedToken,
    })

    const longLivedResp = await fetch(
      `${GRAPH_API}/oauth/access_token?${longLivedParams.toString()}`
    )
    const longLivedData = await longLivedResp.json()
    const longLivedToken = longLivedData.access_token || shortLivedToken

    // Step 3: Fetch connected assets (pages, WhatsApp, Instagram)
    const connectedChannels: string[] = []

    // 3a: Get Facebook Pages (for Messenger + Instagram)
    const pagesResp = await fetch(
      `${GRAPH_API}/me/accounts?fields=id,name,access_token,instagram_business_account&access_token=${longLivedToken}`
    )
    const pagesData = await pagesResp.json()
    const pages = pagesData.data || []

    for (const page of pages) {
      // Register Facebook Messenger channel
      await registerChannel(authToken, 'facebook', {
        page_id: page.id,
        page_name: page.name,
        access_token: page.access_token, // Page-specific long-lived token
      })
      connectedChannels.push('facebook')

      // If page has Instagram Business Account, register it too
      if (page.instagram_business_account) {
        const igId = page.instagram_business_account.id

        // Get Instagram account details
        const igResp = await fetch(
          `${GRAPH_API}/${igId}?fields=id,name,username&access_token=${page.access_token}`
        )
        const igData = await igResp.json()

        await registerChannel(authToken, 'instagram', {
          ig_account_id: igId,
          account_name: igData.username || igData.name || 'Instagram',
          access_token: page.access_token,
          page_id: page.id, // Needed for API calls
        })
        connectedChannels.push('instagram')
      }
    }

    // 3b: Get WhatsApp Business Account (if WABA is linked to the Meta App)
    try {
      const wabaResp = await fetch(
        `${GRAPH_API}/me?fields=id,name&access_token=${longLivedToken}`
      )
      const wabaData = await wabaResp.json()

      // Try to get WhatsApp phone numbers if Business Account exists
      const businessId = process.env.WHATSAPP_BUSINESS_ACCOUNT_ID
      if (businessId) {
        const phonesResp = await fetch(
          `${GRAPH_API}/${businessId}/phone_numbers?access_token=${longLivedToken}`
        )
        const phonesData = await phonesResp.json()
        const phones = phonesData.data || []

        if (phones.length > 0) {
          const phone = phones[0] // Primary phone number
          await registerChannel(authToken, 'whatsapp', {
            phone_number_id: phone.id,
            display_phone_number: phone.display_phone_number,
            business_account_id: businessId,
            access_token: longLivedToken,
            quality_rating: phone.quality_rating || 'UNKNOWN',
            account_name: wabaData.name || 'WhatsApp Business',
          })
          connectedChannels.push('whatsapp')
        }
      }
    } catch (e) {
      // WhatsApp may not be set up yet — that's OK
      console.log('WhatsApp Business Account not found or not linked:', e)
    }

    // Clear OAuth cookies
    const response = NextResponse.redirect(
      new URL(
        `/channels?connected=meta&status=success&channels=${connectedChannels.join(',')}`,
        request.url
      )
    )
    response.cookies.delete('oauth_state')
    response.cookies.delete('oauth_token')

    console.log(`Meta OAuth complete. Connected channels: ${connectedChannels.join(', ')}`)
    return response
  } catch (error) {
    console.error('Meta OAuth callback error:', error)
    return NextResponse.redirect(
      new URL('/channels?connected=meta&status=error&reason=server_error', request.url)
    )
  }
}

/**
 * Register a channel via the gateway → channel_router
 * Credentials are encrypted by the channel_router before DB storage
 */
async function registerChannel(
  authToken: string,
  channel: string,
  config: Record<string, string>
): Promise<void> {
  try {
    const resp = await fetch(`${GATEWAY_URL}/api/v1/channels/register`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${authToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: channel,
        enabled: true,
        config: config,
        credentials_encrypted: true,
      }),
    })

    if (!resp.ok) {
      const error = await resp.text()
      console.error(`Failed to register ${channel}:`, error)
    } else {
      // SECURITY: Never log credential values
      console.log(`Successfully registered ${channel} channel`)
    }
  } catch (error) {
    console.error(`Error registering ${channel}:`, error)
  }
}
