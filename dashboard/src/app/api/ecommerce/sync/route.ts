import { NextRequest, NextResponse } from 'next/server'

/**
 * E-Commerce Store Data Sync
 * POST /api/ecommerce/sync — Trigger product/order sync for a connected store
 *
 * Initiates a background sync job for products, orders, or customers.
 */

const GATEWAY_URL = process.env.GATEWAY_INTERNAL_URL || 'http://gateway:9000'

export async function POST(request: NextRequest) {
  try {
    const auth = request.headers.get('authorization')
    if (!auth) {
      return NextResponse.json({ message: 'Unauthorized' }, { status: 401 })
    }

    const body = await request.json()

    const { connection_id, sync_type } = body
    if (!connection_id) {
      return NextResponse.json(
        { message: 'connection_id is required' },
        { status: 400 }
      )
    }

    const validSyncTypes = ['products', 'orders', 'customers', 'all']
    if (sync_type && !validSyncTypes.includes(sync_type)) {
      return NextResponse.json(
        { message: `Invalid sync_type. Allowed: ${validSyncTypes.join(', ')}` },
        { status: 400 }
      )
    }

    const resp = await fetch(`${GATEWAY_URL}/api/v1/ecommerce/sync`, {
      method: 'POST',
      headers: {
        'Authorization': auth,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        platform_id: connection_id,
        full_sync: sync_type === 'all',
        sync_type: sync_type || 'all',
      }),
    })

    const data = await resp.json()
    return NextResponse.json(data, { status: resp.status })
  } catch (error) {
    console.error('Sync store error:', error)
    return NextResponse.json(
      { message: 'Failed to trigger sync' },
      { status: 500 }
    )
  }
}
