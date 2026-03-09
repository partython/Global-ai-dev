import { NextRequest, NextResponse } from 'next/server'

/**
 * Channel Test Connection API
 * POST /api/channels/test — Test credentials against the provider API
 */

const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'

export async function POST(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()

    if (!body.channel) {
      return NextResponse.json(
        { message: 'Channel type is required' },
        { status: 400 }
      )
    }

    // SECURITY: Never log credential values, only channel type
    console.log(`Testing connection for channel: ${body.channel}`)

    const resp = await fetch(
      `${GATEWAY_URL}/api/v1/channels/${encodeURIComponent(body.channel)}/test`,
      {
        method: 'POST',
        headers: {
          'Authorization': auth,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          credentials: body.credentials || null,
        }),
      }
    )

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Test channel error:', error)
    return NextResponse.json(
      { status: 'failed', message: 'Connection test failed' },
      { status: 500 }
    )
  }
}
