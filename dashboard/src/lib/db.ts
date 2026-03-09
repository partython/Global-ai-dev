import { neon } from '@neondatabase/serverless'

// ── Database Connection ──
// Production (Vercel): Uses Neon serverless driver (HTTP) with NEON_DATABASE_URL
// Local dev (Docker): Uses 'pg' package with standard postgres:// DATABASE_URL

type QueryResult = Record<string, any>[]
type SQLTag = (strings: TemplateStringsArray, ...values: any[]) => Promise<QueryResult>

let _query: SQLTag | null = null

function getSQL(): SQLTag {
  if (_query) return _query

  const neonUrl = process.env.NEON_DATABASE_URL || process.env.POSTGRES_URL
  const localUrl = process.env.DATABASE_URL

  const isNeon = neonUrl && (neonUrl.includes('neon.tech') || neonUrl.includes('neon://'))

  if (isNeon && neonUrl) {
    // Production: Neon HTTP driver
    const sql = neon(neonUrl)
    _query = sql as unknown as SQLTag
  } else {
    // Local dev: standard node-postgres (pg) driver
    const databaseUrl = localUrl || neonUrl
    if (!databaseUrl) {
      throw new Error('DATABASE_URL environment variable is required')
    }

    const { Pool } = require('pg')
    const pool = new Pool({ connectionString: databaseUrl })

    _query = async (strings: TemplateStringsArray, ...values: any[]): Promise<QueryResult> => {
      // Convert tagged template literal to parameterized query
      let query = ''
      for (let i = 0; i < strings.length; i++) {
        query += strings[i]
        if (i < values.length) {
          query += `$${i + 1}`
        }
      }
      const result = await pool.query(query, values)
      return result.rows
    }
  }

  return _query!
}

// ── Slug Generator ──

function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .substring(0, 60)
}

function randomHex(n: number): string {
  const chars = '0123456789abcdef'
  let result = ''
  for (let i = 0; i < n; i++) {
    result += chars[Math.floor(Math.random() * chars.length)]
  }
  return result
}

// ── Query Helpers ──
// These match the actual schema from 001_foundation.sql

export async function createTenant(name: string, plan: string = 'starter') {
  const sql = getSQL()

  // Generate unique slug
  let slug = generateSlug(name)
  const existing = await sql`SELECT id FROM tenants WHERE slug = ${slug} LIMIT 1`
  if (existing.length > 0) {
    slug = `${slug}-${randomHex(6)}`
  }

  const result = await sql`
    INSERT INTO tenants (name, slug, plan, status, country, timezone, currency)
    VALUES (${name}, ${slug}, ${plan}, 'active', 'IN', 'Asia/Kolkata', 'INR')
    RETURNING id, name, slug, plan, status, created_at, updated_at
  `
  return result[0]
}

export async function createUser(
  email: string,
  passwordHash: string,
  name: string,
  tenantId: string,
  role: string = 'owner'
) {
  const sql = getSQL()
  const result = await sql`
    INSERT INTO users (email, password_hash, name, role, tenant_id, status, email_verified)
    VALUES (${email}, ${passwordHash}, ${name}, ${role}, ${tenantId}, 'active', false)
    RETURNING id, email, name, role, tenant_id
  `
  return result[0]
}

export async function findUserByEmail(email: string) {
  const sql = getSQL()
  const result = await sql`
    SELECT u.id, u.email, u.password_hash, u.name, u.role, u.tenant_id,
           t.name as tenant_name, t.plan, t.status as tenant_status,
           t.created_at as tenant_created_at, t.updated_at as tenant_updated_at
    FROM users u
    JOIN tenants t ON u.tenant_id = t.id
    WHERE u.email = ${email}
    LIMIT 1
  `
  return result[0] || null
}

export async function findUserById(userId: string) {
  const sql = getSQL()
  const result = await sql`
    SELECT u.id, u.email, u.name, u.role, u.tenant_id,
           t.name as tenant_name, t.plan, t.status as tenant_status,
           t.created_at as tenant_created_at, t.updated_at as tenant_updated_at
    FROM users u
    JOIN tenants t ON u.tenant_id = t.id
    WHERE u.id = ${userId}::uuid
    LIMIT 1
  `
  return result[0] || null
}

export async function emailExists(email: string): Promise<boolean> {
  const sql = getSQL()
  const result = await sql`
    SELECT 1 FROM users WHERE email = ${email} LIMIT 1
  `
  return result.length > 0
}
