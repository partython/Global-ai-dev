import { NextRequest, NextResponse } from 'next/server'

/**
 * E-Commerce Store Connections API
 * GET  /api/ecommerce/stores — List connected stores
 * POST /api/ecommerce/stores — Connect a new store (manual/API key flow)
 * DELETE /api/ecommerce/stores — Disconnect a store
 *
 * Proxies to the ecommerce microservice via gateway.
 */

const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'

export async function GET(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const resp = await fetch(`${GATEWAY_URL}/api/v1/ecommerce/connections`, {
      method: 'GET',
      headers: {
        'Authorization': auth,
        'Content-Type': 'application/json',
      },
    })

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Fetch stores error:', error)
    return NextResponse.json({ connections: [] }, { status: 200 })
  }
}

export async function POST(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()

    // Validate required fields
    const { platform, store_url } = body
    if (!platform || !store_url) {
      return NextResponse.json(
        { message: 'platform and store_url are required' },
        { status: 400 }
      )
    }

    // Validate platform
    const allowedPlatforms = ['shopify', 'woocommerce', 'custom']
    if (!allowedPlatforms.includes(platform)) {
      return NextResponse.json(
        { message: `Invalid platform. Allowed: ${allowedPlatforms.join(', ')}` },
        { status: 400 }
      )
    }

    const resp = await fetch(`${GATEWAY_URL}/api/v1/ecommerce/connect`, {
      method: 'POST',
      headers: {
        'Authorization': auth,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Connect store error:', error)
    return NextResponse.json(
      { message: 'Failed to connect store' },
      { status: 500 }
    )
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const { searchParams } = new URL(request.url)
    const connectionId = searchParams.get('id')

    if (!connectionId) {
      return NextResponse.json(
        { message: 'Connection ID is required' },
        { status: 400 }
      )
    }

    const resp = await fetch(`${GATEWAY_URL}/api/v1/ecommerce/connections/${connectionId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': auth,
        'Content-Type': 'application/json',
      },
    })

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Disconnect store error:', error)
    return NextResponse.json(
      { message: 'Failed to disconnect store' },
      { status: 500 }
    )
  }
}
