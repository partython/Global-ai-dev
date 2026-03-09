import { NextRequest, NextResponse } from 'next/server'

/**
 * E-Commerce Store Connection Test
 * POST /api/ecommerce/test — Test a store connection
 *
 * Tests connectivity by calling the store's API with provided credentials.
 * Rate limited to 5 req/min per tenant.
 */

const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'

export async function POST(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()

    const { connection_id } = body
    if (!connection_id) {
      return NextResponse.json(
        { message: 'connection_id is required' },
        { status: 400 }
      )
    }

    const resp = await fetch(`${GATEWAY_URL}/api/v1/ecommerce/connections/${connection_id}/test`, {
      method: 'POST',
      headers: {
        'Authorization': auth,
        'Content-Type': 'application/json',
      },
    })

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Test store connection error:', error)
    return NextResponse.json(
      { status: 'failed', message: 'Connection test failed' },
      { status: 500 }
    )
  }
}
