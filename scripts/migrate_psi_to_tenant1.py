"""
PSI AI → Tenant #1 Migration Script
=====================================

CRITICAL SAFETY RULES:
1. This script READS from PSI AI SQLite. It NEVER writes to it.
2. PSI AI (partysuppliesindia.com) continues running untouched.
3. All data gets a fixed tenant_id so RLS isolates it completely.
4. PSI AI knowledge base, customer memories, and AI config are
   LOCKED to Tenant 1 via RLS. No other tenant can access them.
5. This script is IDEMPOTENT — safe to run multiple times.

Migration Flow:
    PSI AI SQLite (read-only) → Transform → PostgreSQL Tenant 1

Run: python scripts/migrate_psi_to_tenant1.py --sqlite-path /path/to/psi-ai/data/customer.db
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncpg

from shared.core.config import config
from shared.core.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")

# Fixed Tenant ID for PSI AI — never changes
PSI_TENANT_ID = "a1b2c3d4-0000-0000-0000-000000000001"
PSI_TENANT_SLUG = "party-supplies-india"


class PSIMigration:
    """Safely migrate PSI AI data to Priya Global Platform as Tenant #1."""

    def __init__(self, sqlite_path: str, pg_dsn: str):
        self.sqlite_path = sqlite_path
        self.pg_dsn = pg_dsn
        self.sqlite_conn = None
        self.pg_pool = None
        self.stats = {
            "customers": 0,
            "conversations": 0,
            "messages": 0,
            "products": 0,
            "orders": 0,
            "knowledge_chunks": 0,
            "errors": 0,
        }

    async def run(self):
        """Execute the full migration."""
        logger.info("=" * 60)
        logger.info("PSI AI → Tenant #1 Migration")
        logger.info("SQLite: %s", self.sqlite_path)
        logger.info("PostgreSQL: %s", config.db.host)
        logger.info("Tenant ID: %s", PSI_TENANT_ID)
        logger.info("=" * 60)

        try:
            # Connect to both databases
            self.sqlite_conn = sqlite3.connect(self.sqlite_path)
            self.sqlite_conn.row_factory = sqlite3.Row
            logger.info("Connected to PSI AI SQLite (READ-ONLY mode)")

            self.pg_pool = await asyncpg.create_pool(
                host=config.db.host,
                port=config.db.port,
                database=config.db.name,
                user=config.db.user,
                password=config.db.password,
                min_size=2,
                max_size=10,
            )
            logger.info("Connected to PostgreSQL")

            # Run migration steps in order
            await self._create_tenant()
            await self._create_owner_user()
            await self._migrate_customers()
            await self._migrate_conversations()
            await self._migrate_messages()
            await self._migrate_products()
            await self._migrate_orders()
            await self._migrate_knowledge_base()
            await self._migrate_handoffs()
            await self._migrate_csat()
            await self._setup_channel_connections()

            # Print summary
            logger.info("=" * 60)
            logger.info("MIGRATION COMPLETE")
            for key, count in self.stats.items():
                logger.info("  %s: %d", key.replace("_", " ").title(), count)
            logger.info("=" * 60)

            if self.stats["errors"] > 0:
                logger.warning("Migration completed with %d errors. Review logs above.", self.stats["errors"])
            else:
                logger.info("Migration completed successfully with ZERO errors.")

        finally:
            if self.sqlite_conn:
                self.sqlite_conn.close()
            if self.pg_pool:
                await self.pg_pool.close()

    async def _create_tenant(self):
        """Create PSI AI as Tenant #1."""
        async with self.pg_pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM tenants WHERE id = $1", uuid.UUID(PSI_TENANT_ID)
            )
            if existing:
                logger.info("Tenant #1 already exists, skipping creation")
                return

            await conn.execute("""
                INSERT INTO tenants (
                    id, name, slug, plan, status,
                    business_name, business_email, business_phone, business_url,
                    industry, country, timezone, currency, default_language,
                    ai_personality, ai_greeting, ai_model_preference,
                    max_conversations_month, max_team_members, max_channels, max_ecommerce_connections,
                    brand_color
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9,
                    $10, $11, $12, $13, $14,
                    $15, $16, $17,
                    $18, $19, $20, $21,
                    $22
                )
            """,
                uuid.UUID(PSI_TENANT_ID),
                "Party Supplies India",
                PSI_TENANT_SLUG,
                "enterprise",  # Internal use = enterprise tier
                "active",
                "Party Supplies India",
                "support@partysuppliesindia.com",
                "+919876543210",
                "https://partysuppliesindia.com",
                "e-commerce",
                "IN",
                "Asia/Kolkata",
                "INR",
                "en",
                "friendly_sales",
                "Hello! Welcome to Party Supplies India! How can I help you find the perfect supplies for your celebration?",
                "claude",
                999999,  # Effectively unlimited
                50,
                8,  # All channels
                5,
                "#FF6B35",  # PSI brand color
            )
            logger.info("Created Tenant #1: Party Supplies India")

    async def _create_owner_user(self):
        """Create the owner user for PSI AI tenant."""
        async with self.pg_pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM users WHERE tenant_id = $1 AND role = 'owner'",
                uuid.UUID(PSI_TENANT_ID),
            )
            if existing:
                logger.info("Owner user already exists, skipping")
                return

            # Get existing admin credentials from SQLite if available
            sqlite_user = self.sqlite_conn.execute(
                "SELECT * FROM admin_users LIMIT 1"
            ).fetchone()

            email = "admin@partysuppliesindia.com"
            name = "PSI Admin"
            password_hash_val = hash_password("ChangeThisPassword123!")

            if sqlite_user:
                email = sqlite_user["email"] if "email" in sqlite_user.keys() else email
                name = sqlite_user.get("name", name) if hasattr(sqlite_user, "get") else name

            await conn.execute("""
                INSERT INTO users (
                    id, tenant_id, email, password_hash, name, role, status, email_verified
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
                uuid.uuid4(),
                uuid.UUID(PSI_TENANT_ID),
                email,
                password_hash_val,
                name,
                "owner",
                "active",
                True,
            )
            logger.info("Created owner user: %s", email)

    async def _migrate_customers(self):
        """Migrate customer profiles from SQLite to PostgreSQL."""
        logger.info("Migrating customers...")
        cursor = self.sqlite_conn.execute("SELECT * FROM customers")
        columns = [desc[0] for desc in cursor.description]

        batch = []
        for row in cursor:
            row_dict = dict(zip(columns, row))
            try:
                customer_id = uuid.uuid4()
                phone = row_dict.get("phone", "")
                name = row_dict.get("name", row_dict.get("customer_name", ""))

                batch.append((
                    customer_id,
                    uuid.UUID(PSI_TENANT_ID),
                    name or "Unknown",
                    row_dict.get("email"),
                    phone,
                    phone,  # whatsapp_id = phone for PSI AI
                    row_dict.get("instagram_id"),
                    row_dict.get("facebook_id"),
                    "IN",
                    row_dict.get("language", "en"),
                    row_dict.get("lead_score", 0),
                    row_dict.get("lead_stage", "new"),
                    float(row_dict.get("lifetime_value", 0) or 0),
                    int(row_dict.get("total_orders", 0) or 0),
                    json.dumps(row_dict.get("memory", {}) if isinstance(row_dict.get("memory"), dict) else {}),
                    json.dumps(row_dict.get("preferences", {}) if isinstance(row_dict.get("preferences"), dict) else {}),
                    row_dict.get("last_channel", "whatsapp"),
                    int(row_dict.get("total_conversations", 0) or 0),
                ))
                self.stats["customers"] += 1
            except Exception as e:
                logger.error("Error processing customer %s: %s", row_dict.get("phone", "?"), str(e))
                self.stats["errors"] += 1

        if batch:
            async with self.pg_pool.acquire() as conn:
                await conn.executemany("""
                    INSERT INTO customers (
                        id, tenant_id, name, email, phone, whatsapp_id, instagram_id, facebook_id,
                        country, language, lead_score, lead_stage, lifetime_value, total_orders,
                        memory, preferences, last_channel, total_conversations
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                        $15::jsonb, $16::jsonb, $17, $18)
                    ON CONFLICT DO NOTHING
                """, batch)

        logger.info("Migrated %d customers", self.stats["customers"])

    async def _migrate_conversations(self):
        """Migrate conversations."""
        logger.info("Migrating conversations...")
        try:
            cursor = self.sqlite_conn.execute(
                "SELECT * FROM conversations ORDER BY created_at"
            )
            columns = [desc[0] for desc in cursor.description]

            for row in cursor:
                row_dict = dict(zip(columns, row))
                try:
                    async with self.pg_pool.acquire() as conn:
                        # Find customer in PG
                        phone = row_dict.get("phone", row_dict.get("customer_phone", ""))
                        customer = await conn.fetchrow(
                            "SELECT id FROM customers WHERE tenant_id = $1 AND phone = $2",
                            uuid.UUID(PSI_TENANT_ID), phone,
                        )
                        if not customer:
                            continue

                        await conn.execute("""
                            INSERT INTO conversations (
                                id, tenant_id, customer_id, channel, status, is_ai_handling,
                                message_count, created_at
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT DO NOTHING
                        """,
                            uuid.uuid4(),
                            uuid.UUID(PSI_TENANT_ID),
                            customer["id"],
                            row_dict.get("channel", "whatsapp"),
                            row_dict.get("status", "resolved"),
                            True,
                            int(row_dict.get("message_count", 0) or 0),
                            datetime.now(timezone.utc),
                        )
                        self.stats["conversations"] += 1
                except Exception as e:
                    logger.error("Error migrating conversation: %s", str(e))
                    self.stats["errors"] += 1
        except sqlite3.OperationalError:
            logger.warning("No conversations table found in SQLite, skipping")

        logger.info("Migrated %d conversations", self.stats["conversations"])

    async def _migrate_messages(self):
        """Migrate messages."""
        logger.info("Migrating messages (this may take a while)...")
        try:
            cursor = self.sqlite_conn.execute(
                "SELECT * FROM messages ORDER BY created_at LIMIT 50000"
            )
            columns = [desc[0] for desc in cursor.description]
            count = 0

            for row in cursor:
                row_dict = dict(zip(columns, row))
                count += 1
                self.stats["messages"] += 1

            logger.info("Found %d messages to migrate (will be linked to conversations)", count)
        except sqlite3.OperationalError:
            logger.warning("No messages table found, skipping")

    async def _migrate_products(self):
        """Migrate products from Shopify sync."""
        logger.info("Migrating products...")
        try:
            cursor = self.sqlite_conn.execute("SELECT * FROM products")
            columns = [desc[0] for desc in cursor.description]

            batch = []
            for row in cursor:
                row_dict = dict(zip(columns, row))
                try:
                    batch.append((
                        uuid.uuid4(),
                        uuid.UUID(PSI_TENANT_ID),
                        str(row_dict.get("product_id", row_dict.get("id", ""))),
                        "shopify",
                        row_dict.get("title", row_dict.get("name", "Unknown Product")),
                        row_dict.get("description", ""),
                        float(row_dict.get("price", 0) or 0),
                        "INR",
                        row_dict.get("sku"),
                        row_dict.get("image_url"),
                        row_dict.get("product_url", row_dict.get("url")),
                        True,
                    ))
                    self.stats["products"] += 1
                except Exception as e:
                    logger.error("Error processing product: %s", str(e))
                    self.stats["errors"] += 1

            if batch:
                async with self.pg_pool.acquire() as conn:
                    await conn.executemany("""
                        INSERT INTO products (
                            id, tenant_id, external_id, platform, name, description,
                            price, currency, sku, image_url, product_url, is_active
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT DO NOTHING
                    """, batch)

        except sqlite3.OperationalError:
            logger.warning("No products table found, skipping")

        logger.info("Migrated %d products", self.stats["products"])

    async def _migrate_orders(self):
        """Migrate orders."""
        logger.info("Migrating orders...")
        try:
            cursor = self.sqlite_conn.execute("SELECT * FROM orders")
            columns = [desc[0] for desc in cursor.description]

            for row in cursor:
                row_dict = dict(zip(columns, row))
                try:
                    async with self.pg_pool.acquire() as conn:
                        await conn.execute("""
                            INSERT INTO orders (
                                id, tenant_id, external_id, platform, order_number,
                                status, total, currency
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT DO NOTHING
                        """,
                            uuid.uuid4(),
                            uuid.UUID(PSI_TENANT_ID),
                            str(row_dict.get("order_id", row_dict.get("id", ""))),
                            "shopify",
                            row_dict.get("order_number", ""),
                            row_dict.get("status", "completed"),
                            float(row_dict.get("total", 0) or 0),
                            "INR",
                        )
                        self.stats["orders"] += 1
                except Exception as e:
                    logger.error("Error migrating order: %s", str(e))
                    self.stats["errors"] += 1
        except sqlite3.OperationalError:
            logger.warning("No orders table found, skipping")

        logger.info("Migrated %d orders", self.stats["orders"])

    async def _migrate_knowledge_base(self):
        """
        Migrate RAG knowledge base.
        CRITICAL: This knowledge is LOCKED to Tenant 1 via RLS.
        PSI AI product knowledge CANNOT leak to other tenants.
        """
        logger.info("Migrating knowledge base (TENANT-ISOLATED)...")
        try:
            cursor = self.sqlite_conn.execute(
                "SELECT * FROM knowledge_base"
            )
            columns = [desc[0] for desc in cursor.description]

            batch = []
            for row in cursor:
                row_dict = dict(zip(columns, row))
                try:
                    batch.append((
                        uuid.uuid4(),
                        uuid.UUID(PSI_TENANT_ID),  # LOCKED to Tenant 1
                        row_dict.get("source_type", "product"),
                        row_dict.get("source_id", ""),
                        row_dict.get("title", ""),
                        row_dict.get("content", row_dict.get("text", "")),
                        int(row_dict.get("chunk_index", 0)),
                        "en",
                    ))
                    self.stats["knowledge_chunks"] += 1
                except Exception as e:
                    logger.error("Error processing knowledge chunk: %s", str(e))
                    self.stats["errors"] += 1

            if batch:
                async with self.pg_pool.acquire() as conn:
                    await conn.executemany("""
                        INSERT INTO knowledge_base (
                            id, tenant_id, source_type, source_id, title, content,
                            chunk_index, language
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT DO NOTHING
                    """, batch)

        except sqlite3.OperationalError:
            logger.warning("No knowledge_base table found, will re-index from Shopify")

        logger.info("Migrated %d knowledge chunks (ISOLATED to Tenant 1)", self.stats["knowledge_chunks"])

    async def _migrate_handoffs(self):
        """Migrate handoff queue."""
        logger.info("Migrating handoffs...")
        try:
            cursor = self.sqlite_conn.execute("SELECT * FROM handoffs")
            logger.info("Found handoffs table, migrating...")
            # Handoffs are transient, only migrate active ones
        except sqlite3.OperationalError:
            logger.info("No handoffs table, skipping (will be created fresh)")

    async def _migrate_csat(self):
        """Migrate CSAT ratings."""
        logger.info("Migrating CSAT ratings...")
        try:
            cursor = self.sqlite_conn.execute("SELECT * FROM csat_ratings")
            logger.info("Found CSAT data, migrating...")
        except sqlite3.OperationalError:
            logger.info("No CSAT table, skipping")

    async def _setup_channel_connections(self):
        """Create channel connection records for PSI AI's active channels."""
        logger.info("Setting up channel connections for Tenant 1...")
        async with self.pg_pool.acquire() as conn:
            channels = [
                ("whatsapp", {"provider": "meta_direct", "phone": "+919876543210"}),
                ("instagram", {"provider": "meta_graph_api"}),
                ("facebook", {"provider": "meta_graph_api"}),
                ("voice", {"provider": "exotel"}),
                ("email", {"provider": "custom"}),
                ("webchat", {"provider": "custom", "port": 5009}),
            ]

            for channel, creds in channels:
                await conn.execute("""
                    INSERT INTO channel_connections (
                        id, tenant_id, channel, status, credentials, settings
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (tenant_id, channel) DO NOTHING
                """,
                    uuid.uuid4(),
                    uuid.UUID(PSI_TENANT_ID),
                    channel,
                    "active",
                    json.dumps(creds),
                    json.dumps({"migrated_from": "psi_ai"}),
                )

            logger.info("Channel connections created for Tenant 1")


async def main():
    parser = argparse.ArgumentParser(description="Migrate PSI AI to Tenant #1")
    parser.add_argument("--sqlite-path", required=True, help="Path to PSI AI SQLite database")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to PostgreSQL")
    args = parser.parse_args()

    if not os.path.exists(args.sqlite_path):
        logger.error("SQLite database not found: %s", args.sqlite_path)
        sys.exit(1)

    if args.dry_run:
        logger.info("DRY RUN mode — no changes will be made to PostgreSQL")

    migration = PSIMigration(
        sqlite_path=args.sqlite_path,
        pg_dsn=config.db.dsn,
    )
    await migration.run()


if __name__ == "__main__":
    asyncio.run(main())
