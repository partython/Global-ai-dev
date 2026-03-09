import { NextRequest, NextResponse } from 'next/server'

/**
 * Channel Management API Routes
 * Proxies requests to the gateway → channel_router service
 *
 * GET  /api/channels         → List all tenant channels
 * POST /api/channels         → Register/connect a channel with credentials
 * DELETE /api/channels       → Disconnect a channel
 */

const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'

function getAuthHeader(request: NextRequest): string | null {
  return request.headers.get('authorization')
}

// GET — List all channels for the authenticated tenant
export async function GET(request: NextRequest) {
  try {
    const auth = getAuthHeader(request)
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const resp = await fetch(`${GATEWAY_URL}/api/v1/channels`, {
      method: 'GET',
      headers: {
        'Authorization': auth,
        'Content-Type': 'application/json',
      },
    })

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('List channels error:', error)
    return NextResponse.json(
      { message: 'Failed to fetch channels' },
      { status: 500 }
    )
  }
}

// POST — Register/connect a new channel
export async function POST(request: NextRequest) {
  try {
    const auth = getAuthHeader(request)
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()

    // Validate required fields
    if (!body.channel) {
      return NextResponse.json(
        { message: 'Channel type is required' },
        { status: 400 }
      )
    }

    // SECURITY: Never log credential values
    console.log(`Registering channel: ${body.channel}`)

    const resp = await fetch(`${GATEWAY_URL}/api/v1/channels/register`, {
      method: 'POST',
      headers: {
        'Authorization': auth,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: body.channel,
        enabled: true,
        config: body.credentials || {},
        credentials_encrypted: true,
      }),
    })

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Register channel error:', error)
    return NextResponse.json(
      { message: 'Failed to register channel' },
      { status: 500 }
    )
  }
}

// DELETE — Disconnect a channel
export async function DELETE(request: NextRequest) {
  try {
    const auth = getAuthHeader(request)
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const { searchParams } = new URL(request.url)
    const channel = searchParams.get('channel')

    if (!channel) {
      return NextResponse.json(
        { message: 'Channel parameter is required' },
        { status: 400 }
      )
    }

    console.log(`Disconnecting channel: ${channel}`)

    const resp = await fetch(
      `${GATEWAY_URL}/api/v1/channels/${encodeURIComponent(channel)}/disconnect`,
      {
        method: 'POST',
        headers: {
          'Authorization': auth,
          'Content-Type': 'application/json',
        },
      }
    )

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Disconnect channel error:', error)
    return NextResponse.json(
      { message: 'Failed to disconnect channel' },
      { status: 500 }
    )
  }
}
