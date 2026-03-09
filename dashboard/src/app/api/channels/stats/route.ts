import { NextRequest, NextResponse } from 'next/server'

/**
 * Channel Stats API
 * GET /api/channels/stats — Aggregated message stats per channel
 */

const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'

export async function GET(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const resp = await fetch(`${GATEWAY_URL}/api/v1/channels/stats`, {
      method: 'GET',
      headers: {
        'Authorization': auth,
        'Content-Type': 'application/json',
      },
    })

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Channel stats error:', error)
    // Graceful fallback — empty stats
    return NextResponse.json({ stats: [] }, { status: 200 })
  }
}
