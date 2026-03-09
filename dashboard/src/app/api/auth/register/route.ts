import { NextRequest, NextResponse } from 'next/server'
import bcrypt from 'bcryptjs'
import { SignJWT } from 'jose'
import { createTenant, createUser, emailExists } from '@/lib/db'

const JWT_SECRET = new TextEncoder().encode(
  process.env.JWT_SECRET || 'fallback-dev-secret-change-in-production'
)

// SECURITY: Input validation
function validateInput(body: any): string | null {
  if (!body.businessName || typeof body.businessName !== 'string' || body.businessName.trim().length < 2) {
    return 'Business name must be at least 2 characters'
  }
  if (!body.fullName || typeof body.fullName !== 'string' || body.fullName.trim().length < 2) {
    return 'Full name must be at least 2 characters'
  }
  if (!body.email || typeof body.email !== 'string') {
    return 'Valid email is required'
  }
  // RFC 5322 simplified email check
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  if (!emailRegex.test(body.email)) {
    return 'Invalid email format'
  }
  if (!body.password || typeof body.password !== 'string' || body.password.length < 8) {
    return 'Password must be at least 8 characters'
  }
  if (body.password.length > 128) {
    return 'Password too long'
  }
  return null
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    // Validate input
    const validationError = validateInput(body)
    if (validationError) {
      return NextResponse.json({ message: validationError }, { status: 400 })
    }

    const email = body.email.toLowerCase().trim()
    const businessName = body.businessName.trim()
    const fullName = body.fullName.trim()

    // Check if email already registered
    const exists = await emailExists(email)
    if (exists) {
      return NextResponse.json(
        { message: 'An account with this email already exists' },
        { status: 409 }
      )
    }

    // SECURITY: Hash password with bcrypt, cost factor 12
    const passwordHash = await bcrypt.hash(body.password, 12)

    // Create tenant first, then user
    const tenant = await createTenant(businessName)
    const user = await createUser(email, passwordHash, fullName, tenant.id)

    // Sign JWT (7-day expiry)
    const token = await new SignJWT({
      userId: user.id,
      tenantId: tenant.id,
      email: user.email,
      role: user.role,
    })
      .setProtectedHeader({ alg: 'HS256' })
      .setIssuedAt()
      .setExpirationTime('7d')
      .sign(JWT_SECRET)

    return NextResponse.json({
      token,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        role: user.role,
      },
      tenant: {
        id: tenant.id,
        name: tenant.name,
        plan: tenant.plan,
        status: tenant.status,
        createdAt: tenant.created_at,
        updatedAt: tenant.updated_at,
      },
    })
  } catch (error: any) {
    console.error('Registration error:', error)
    // SECURITY: Don't leak internal error details
    return NextResponse.json(
      { message: 'Registration failed. Please try again.' },
      { status: 500 }
    )
  }
}
