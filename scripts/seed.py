#!/usr/bin/env python3
"""
Priya Global Platform — Database Seed Script
=============================================
Creates test tenants, users, customers, and sample data for local development.

Usage:
    python scripts/seed.py                  # Seed all data
    python scripts/seed.py --reset          # Drop & recreate tables, then seed
    python scripts/seed.py --users-only     # Seed only tenants + users

Passwords for all test users: Test@12345

SECURITY: This script is for LOCAL DEV ONLY. Never run in production.
"""

import asyncio
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from uuid import uuid4

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import asyncpg
    import bcrypt
except ImportError:
    print("ERROR: Missing dependencies. Run: pip install asyncpg bcrypt")
    sys.exit(1)


# ─── Configuration ───

DB_HOST = os.getenv("PG_HOST", "localhost")
DB_PORT = int(os.getenv("PG_PORT", "5432"))
DB_NAME = os.getenv("PG_DATABASE", "priya_global")
DB_USER = os.getenv("PG_USER", "priya")
DB_PASS = os.getenv("PG_PASSWORD") or os.getenv("POSTGRES_PASSWORD", "priya_local_dev_2026")

DEFAULT_PASSWORD = "Test@12345"

# ─── Color Output ───

GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log(emoji, msg):
    print(f"  {emoji} {msg}")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


# ─── Seed Data ───

TENANTS = [
    {
        "id": "a0000000-0000-0000-0000-000000000001",
        "name": "Balloons Unlimited Chennai",
        "slug": "balloons-unlimited",
        "plan": "enterprise",
        "status": "active",
        "business_name": "Balloons Unlimited",
        "business_email": "info@balloonsunlimitedchennai.com",
        "business_phone": "+914412345678",
        "business_url": "https://balloonsunlimitedchennai.com",
        "industry": "Party Supplies & Events",
        "country": "IN",
        "timezone": "Asia/Kolkata",
        "currency": "INR",
        "default_language": "en",
        "ai_personality": "friendly_sales",
        "ai_greeting": "Welcome to Balloons Unlimited! How can I help make your party special?",
        "brand_color": "#FF6B35",
        "max_conversations_month": 10000,
        "max_team_members": 25,
        "max_channels": 10,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000002",
        "name": "TechStart Solutions",
        "slug": "techstart-solutions",
        "plan": "growth",
        "status": "active",
        "business_name": "TechStart Solutions Pvt Ltd",
        "business_email": "hello@techstart.io",
        "business_phone": "+918012345678",
        "business_url": "https://techstart.io",
        "industry": "SaaS / Technology",
        "country": "IN",
        "timezone": "Asia/Kolkata",
        "currency": "INR",
        "default_language": "en",
        "ai_personality": "professional",
        "ai_greeting": "Hi there! I'm the TechStart assistant. How can I help?",
        "brand_color": "#3B82F6",
        "max_conversations_month": 5000,
        "max_team_members": 10,
        "max_channels": 5,
    },
    {
        "id": "a0000000-0000-0000-0000-000000000003",
        "name": "Fresh Bakes Mumbai",
        "slug": "fresh-bakes-mumbai",
        "plan": "starter",
        "status": "active",
        "business_name": "Fresh Bakes",
        "business_email": "orders@freshbakes.in",
        "business_phone": "+912212345678",
        "business_url": "https://freshbakes.in",
        "industry": "Food & Bakery",
        "country": "IN",
        "timezone": "Asia/Kolkata",
        "currency": "INR",
        "default_language": "en",
        "ai_personality": "friendly_sales",
        "ai_greeting": "Welcome to Fresh Bakes! What delicious treats can I help you with today?",
        "brand_color": "#F59E0B",
        "max_conversations_month": 1000,
        "max_team_members": 2,
        "max_channels": 3,
    },
]

USERS = [
    # ── Tenant 1: Balloons Unlimited ──
    {
        "id": "b0000000-0000-0000-0000-000000000001",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "email": "partython@balloonsunlimited.com",
        "name": "Partython (Owner)",
        "role": "owner",
        "email_verified": True,
    },
    {
        "id": "b0000000-0000-0000-0000-000000000002",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "email": "admin@balloonsunlimited.com",
        "name": "Priya Admin",
        "role": "admin",
        "email_verified": True,
    },
    {
        "id": "b0000000-0000-0000-0000-000000000003",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "email": "agent1@balloonsunlimited.com",
        "name": "Ramesh Kumar",
        "role": "agent",
        "email_verified": True,
    },
    {
        "id": "b0000000-0000-0000-0000-000000000004",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "email": "agent2@balloonsunlimited.com",
        "name": "Lakshmi Devi",
        "role": "agent",
        "email_verified": True,
    },
    {
        "id": "b0000000-0000-0000-0000-000000000005",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "email": "viewer@balloonsunlimited.com",
        "name": "Suresh Viewer",
        "role": "viewer",
        "email_verified": False,
    },
    # ── Tenant 2: TechStart ──
    {
        "id": "b0000000-0000-0000-0000-000000000006",
        "tenant_id": "a0000000-0000-0000-0000-000000000002",
        "email": "ceo@techstart.io",
        "name": "Arun Mehta",
        "role": "owner",
        "email_verified": True,
    },
    {
        "id": "b0000000-0000-0000-0000-000000000007",
        "tenant_id": "a0000000-0000-0000-0000-000000000002",
        "email": "support@techstart.io",
        "name": "Divya Support",
        "role": "agent",
        "email_verified": True,
    },
    {
        "id": "b0000000-0000-0000-0000-000000000008",
        "tenant_id": "a0000000-0000-0000-0000-000000000002",
        "email": "dev@techstart.io",
        "name": "Karthik Dev",
        "role": "developer",
        "email_verified": True,
    },
    # ── Tenant 3: Fresh Bakes ──
    {
        "id": "b0000000-0000-0000-0000-000000000009",
        "tenant_id": "a0000000-0000-0000-0000-000000000003",
        "email": "owner@freshbakes.in",
        "name": "Meera Patel",
        "role": "owner",
        "email_verified": True,
    },
    {
        "id": "b0000000-0000-0000-0000-000000000010",
        "tenant_id": "a0000000-0000-0000-0000-000000000003",
        "email": "orders@freshbakes.in",
        "name": "Anita Orders",
        "role": "agent",
        "email_verified": True,
    },
]

CUSTOMERS = [
    # ── Customers for Tenant 1: Balloons Unlimited ──
    {
        "id": "c0000000-0000-0000-0000-000000000001",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "name": "Rajesh Birthday Party",
        "email": "rajesh@gmail.com",
        "phone": "+919876543210",
        "whatsapp_id": "919876543210",
        "country": "IN",
        "city": "Chennai",
        "language": "en",
        "tags": ["vip", "repeat-customer", "birthday"],
        "lead_score": 85,
        "lead_stage": "won",
        "lifetime_value": 45000.00,
        "total_orders": 12,
        "first_channel": "whatsapp",
    },
    {
        "id": "c0000000-0000-0000-0000-000000000002",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "name": "Sunita Wedding Planner",
        "email": "sunita.events@yahoo.com",
        "phone": "+919887654321",
        "whatsapp_id": "919887654321",
        "country": "IN",
        "city": "Chennai",
        "language": "ta",
        "tags": ["wedding", "bulk-orders", "b2b"],
        "lead_score": 92,
        "lead_stage": "won",
        "lifetime_value": 125000.00,
        "total_orders": 8,
        "first_channel": "whatsapp",
    },
    {
        "id": "c0000000-0000-0000-0000-000000000003",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "name": "Corporate Events Ltd",
        "email": "events@corpevents.in",
        "phone": "+914423456789",
        "country": "IN",
        "city": "Chennai",
        "language": "en",
        "tags": ["corporate", "b2b", "monthly"],
        "lead_score": 78,
        "lead_stage": "negotiation",
        "lifetime_value": 85000.00,
        "total_orders": 5,
        "first_channel": "email",
    },
    {
        "id": "c0000000-0000-0000-0000-000000000004",
        "tenant_id": "a0000000-0000-0000-0000-000000000001",
        "name": "New Lead - Priya",
        "phone": "+919111222333",
        "whatsapp_id": "919111222333",
        "country": "IN",
        "city": "Chennai",
        "language": "en",
        "tags": ["new"],
        "lead_score": 25,
        "lead_stage": "new",
        "lifetime_value": 0,
        "total_orders": 0,
        "first_channel": "whatsapp",
    },
    # ── Customers for Tenant 2: TechStart ──
    {
        "id": "c0000000-0000-0000-0000-000000000005",
        "tenant_id": "a0000000-0000-0000-0000-000000000002",
        "name": "Acme Corp",
        "email": "procurement@acme.com",
        "phone": "+918011223344",
        "country": "IN",
        "city": "Bangalore",
        "language": "en",
        "tags": ["enterprise", "trial"],
        "lead_score": 70,
        "lead_stage": "proposal",
        "lifetime_value": 500000.00,
        "total_orders": 1,
        "first_channel": "webchat",
    },
    # ── Customers for Tenant 3: Fresh Bakes ──
    {
        "id": "c0000000-0000-0000-0000-000000000006",
        "tenant_id": "a0000000-0000-0000-0000-000000000003",
        "name": "Asha Iyer",
        "email": "asha.iyer@gmail.com",
        "phone": "+912299887766",
        "whatsapp_id": "912299887766",
        "country": "IN",
        "city": "Mumbai",
        "language": "hi",
        "tags": ["cake-lover", "weekly"],
        "lead_score": 60,
        "lead_stage": "won",
        "lifetime_value": 12000.00,
        "total_orders": 24,
        "first_channel": "instagram",
    },
]


async def create_tables(conn):
    """Create core tables using the dashboard-compatible schema (simplified for local dev)."""
    log("📦", "Creating core tables...")

    # Extensions
    await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    await conn.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # Tenants
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name TEXT NOT NULL,
            slug TEXT UNIQUE,
            plan TEXT NOT NULL DEFAULT 'starter',
            status TEXT NOT NULL DEFAULT 'active',
            business_name TEXT,
            business_email TEXT,
            business_phone TEXT,
            business_url TEXT,
            industry TEXT,
            country TEXT NOT NULL DEFAULT 'IN',
            timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
            currency TEXT NOT NULL DEFAULT 'INR',
            default_language TEXT NOT NULL DEFAULT 'en',
            ai_personality TEXT DEFAULT 'friendly_sales',
            ai_greeting TEXT DEFAULT 'Hello! How can I help you today?',
            ai_system_prompt TEXT,
            ai_model_preference TEXT DEFAULT 'auto',
            logo_url TEXT,
            brand_color TEXT DEFAULT '#3B82F6',
            favicon_url TEXT,
            max_conversations_month INTEGER NOT NULL DEFAULT 1000,
            max_team_members INTEGER NOT NULL DEFAULT 2,
            max_channels INTEGER NOT NULL DEFAULT 3,
            max_ecommerce_connections INTEGER NOT NULL DEFAULT 1,
            conversations_this_month INTEGER NOT NULL DEFAULT 0,
            billing_period_start TIMESTAMPTZ,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            trial_ends_at TIMESTAMPTZ,
            settings JSONB NOT NULL DEFAULT '{}',
            feature_flags JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ
        )
    """)

    # Users
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            password_hash TEXT,
            name TEXT NOT NULL,
            avatar_url TEXT,
            role TEXT NOT NULL DEFAULT 'agent',
            status TEXT NOT NULL DEFAULT 'active',
            email_verified BOOLEAN NOT NULL DEFAULT false,
            totp_secret TEXT,
            totp_enabled BOOLEAN NOT NULL DEFAULT false,
            last_login_at TIMESTAMPTZ,
            last_login_ip INET,
            failed_login_count INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMPTZ,
            google_id TEXT,
            apple_id TEXT,
            microsoft_id TEXT,
            preferred_language TEXT DEFAULT 'en',
            notification_prefs JSONB NOT NULL DEFAULT '{"email": true, "push": true, "sound": true}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(tenant_id, email)
        )
    """)

    # Customers
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name TEXT,
            email TEXT,
            phone TEXT,
            avatar_url TEXT,
            whatsapp_id TEXT,
            instagram_id TEXT,
            facebook_id TEXT,
            telegram_id TEXT,
            webchat_session TEXT,
            country TEXT,
            city TEXT,
            language TEXT DEFAULT 'en',
            timezone TEXT,
            tags TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
            lead_score INTEGER NOT NULL DEFAULT 0,
            lead_stage TEXT DEFAULT 'new',
            lifetime_value NUMERIC(12,2) NOT NULL DEFAULT 0,
            total_orders INTEGER NOT NULL DEFAULT 0,
            first_channel TEXT,
            memory JSONB NOT NULL DEFAULT '{}',
            preferences JSONB NOT NULL DEFAULT '{}',
            family_info JSONB NOT NULL DEFAULT '{}',
            last_message_at TIMESTAMPTZ,
            last_channel TEXT,
            total_conversations INTEGER NOT NULL DEFAULT 0,
            sentiment_avg FLOAT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMPTZ
        )
    """)

    # Indexes
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug) WHERE deleted_at IS NULL")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_tenant ON customers(tenant_id)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email) WHERE email IS NOT NULL")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone) WHERE phone IS NOT NULL")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_whatsapp ON customers(whatsapp_id) WHERE whatsapp_id IS NOT NULL")

    log("✅", "Core tables created")


async def seed_tenants(conn):
    log("🏢", "Seeding tenants...")
    now = datetime.now(timezone.utc)

    for t in TENANTS:
        await conn.execute("""
            INSERT INTO tenants (
                id, name, slug, plan, status,
                business_name, business_email, business_phone, business_url,
                industry, country, timezone, currency, default_language,
                ai_personality, ai_greeting, brand_color,
                max_conversations_month, max_team_members, max_channels,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12, $13, $14,
                $15, $16, $17,
                $18, $19, $20,
                $21, $22
            ) ON CONFLICT (id) DO NOTHING
        """,
            t["id"], t["name"], t["slug"], t["plan"], t["status"],
            t["business_name"], t["business_email"], t["business_phone"], t["business_url"],
            t["industry"], t["country"], t["timezone"], t["currency"], t["default_language"],
            t["ai_personality"], t["ai_greeting"], t["brand_color"],
            t["max_conversations_month"], t["max_team_members"], t["max_channels"],
            now, now,
        )
    log("✅", f"Seeded {len(TENANTS)} tenants")


async def seed_users(conn):
    log("👤", "Seeding users...")
    now = datetime.now(timezone.utc)
    pwd_hash = hash_password(DEFAULT_PASSWORD)

    for u in USERS:
        await conn.execute("""
            INSERT INTO users (
                id, tenant_id, email, password_hash, name,
                role, status, email_verified,
                preferred_language, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, 'active', $7,
                'en', $8, $9
            ) ON CONFLICT (tenant_id, email) DO NOTHING
        """,
            u["id"], u["tenant_id"], u["email"], pwd_hash, u["name"],
            u["role"], u["email_verified"],
            now, now,
        )
    log("✅", f"Seeded {len(USERS)} users")


async def seed_customers(conn):
    log("🛒", "Seeding customers...")
    now = datetime.now(timezone.utc)

    for c in CUSTOMERS:
        await conn.execute("""
            INSERT INTO customers (
                id, tenant_id, name, email, phone,
                whatsapp_id, country, city, language,
                tags, lead_score, lead_stage,
                lifetime_value, total_orders, first_channel,
                last_message_at, total_conversations,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12,
                $13, $14, $15,
                $16, $17,
                $18, $19
            ) ON CONFLICT (id) DO NOTHING
        """,
            c["id"], c["tenant_id"], c.get("name"), c.get("email"), c.get("phone"),
            c.get("whatsapp_id"), c.get("country"), c.get("city"), c.get("language", "en"),
            c.get("tags", []), c.get("lead_score", 0), c.get("lead_stage", "new"),
            c.get("lifetime_value", 0), c.get("total_orders", 0), c.get("first_channel"),
            now - timedelta(hours=2), c.get("total_orders", 0),
            now - timedelta(days=30), now,
        )
    log("✅", f"Seeded {len(CUSTOMERS)} customers")


async def reset_tables(conn):
    log("⚠️ ", f"{RED}Dropping existing tables...{RESET}")
    await conn.execute("DROP TABLE IF EXISTS customers CASCADE")
    await conn.execute("DROP TABLE IF EXISTS users CASCADE")
    await conn.execute("DROP TABLE IF EXISTS tenants CASCADE")
    log("✅", "Tables dropped")


async def main():
    parser = argparse.ArgumentParser(description="Seed Priya Global local dev database")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables before seeding")
    parser.add_argument("--users-only", action="store_true", help="Only seed tenants and users")
    args = parser.parse_args()

    print(f"\n{BOLD}{'━' * 55}{RESET}")
    print(f"  {BOLD}Priya Global — Database Seed{RESET}")
    print(f"{'━' * 55}\n")

    dsn = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    log("🔌", f"Connecting to {CYAN}{DB_HOST}:{DB_PORT}/{DB_NAME}{RESET}...")

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as e:
        log("❌", f"{RED}Connection failed: {e}{RESET}")
        log("💡", "Make sure PostgreSQL is running: ./scripts/dev-boot.sh")
        sys.exit(1)

    log("✅", f"Connected as {CYAN}{DB_USER}{RESET}")

    try:
        if args.reset:
            await reset_tables(conn)

        await create_tables(conn)
        await seed_tenants(conn)
        await seed_users(conn)

        if not args.users_only:
            await seed_customers(conn)

        # Summary
        tenant_count = await conn.fetchval("SELECT COUNT(*) FROM tenants")
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        customer_count = await conn.fetchval("SELECT COUNT(*) FROM customers")

        print(f"\n{BOLD}{'━' * 55}{RESET}")
        print(f"  {GREEN}✅ Seed Complete!{RESET}")
        print(f"{'━' * 55}")
        print(f"  Tenants:    {CYAN}{tenant_count}{RESET}")
        print(f"  Users:      {CYAN}{user_count}{RESET}")
        print(f"  Customers:  {CYAN}{customer_count}{RESET}")
        print(f"{'━' * 55}")
        print(f"\n  {BOLD}Test Login Credentials:{RESET}")
        print(f"  {'─' * 50}")
        for u in USERS:
            role_color = {
                "owner": f"{RED}{BOLD}",
                "admin": YELLOW,
                "agent": GREEN,
                "developer": CYAN,
                "viewer": "",
            }.get(u["role"], "")
            print(f"  {u['email']:<42} {role_color}{u['role']:<10}{RESET}")
        print(f"  {'─' * 50}")
        print(f"  Password for all: {BOLD}{DEFAULT_PASSWORD}{RESET}")
        print()

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
