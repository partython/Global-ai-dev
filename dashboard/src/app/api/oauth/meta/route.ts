import { NextRequest, NextResponse } from 'next/server'
import crypto from 'crypto'

/**
 * Meta OAuth Initiation
 * POST /api/oauth/meta — Generate OAuth URL for Facebook Login
 *
 * Handles WhatsApp Business, Instagram, and Facebook Messenger
 * through a single Meta App with multiple products.
 *
 * SECURITY:
 * - State parameter stored in httpOnly cookie (CSRF protection)
 * - State expires in 10 minutes
 * - Meta App Secret never exposed to frontend
 */

const META_APP_ID = process.env.META_APP_ID
const META_GRAPH_VERSION = 'v18.0'

// Scopes needed for all three Meta channels
const META_SCOPES = [
  // WhatsApp Business
  'whatsapp_business_management',
  'whatsapp_business_messaging',
  // Instagram
  'instagram_basic',
  'instagram_manage_messages',
  // Facebook Pages / Messenger
  'pages_manage_metadata',
  'pages_messaging',
  'pages_read_engagement',
].join(',')

export async function POST(request: NextRequest) {
  try {
    if (!META_APP_ID) {
      return NextResponse.json(
        {
          message: 'Meta App not configured. Set META_APP_ID in environment variables.',
          setup_required: true,
        },
        { status: 503 }
      )
    }

    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    // Generate CSRF state parameter
    const state = crypto.randomUUID()

    // Determine redirect URI based on environment
    const origin = process.env.NEXT_PUBLIC_APP_URL
      || process.env.NEXTAUTH_URL
      || (request.headers.get('origin') ?? 'http://localhost:3000')
    const redirectUri = `${origin}/api/oauth/meta/callback`

    // Build Facebook Login OAuth URL
    const params = new URLSearchParams({
      client_id: META_APP_ID,
      redirect_uri: redirectUri,
      state: state,
      scope: META_SCOPES,
      response_type: 'code',
    })

    const authUrl = `https://www.facebook.com/${META_GRAPH_VERSION}/dialog/oauth?${params.toString()}`

    // Store state in httpOnly cookie (10min expiry) for CSRF verification
    const response = NextResponse.json({
      auth_url: authUrl,
      provider: 'meta',
    })

    response.cookies.set('oauth_state', state, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 600, // 10 minutes
      path: '/api/oauth',
    })

    // Also store the auth token so callback can use it
    const token = auth.replace('Bearer ', '')
    response.cookies.set('oauth_token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 600,
      path: '/api/oauth',
    })

    console.log('Meta OAuth initiated, redirecting to Facebook Login')
    return response
  } catch (error) {
    console.error('Meta OAuth initiation error:', error)
    return NextResponse.json(
      { message: 'Failed to initiate Meta OAuth' },
      { status: 500 }
    )
  }
}
