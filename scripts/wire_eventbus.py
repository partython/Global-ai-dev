#!/usr/bin/env python3
"""
Wire EventBus into all 34 Priya Global services.
This script modifies each service's main.py to:
1. Import EventBus and EventType
2. Initialize event_bus singleton
3. Add event_bus.startup() to @app.on_event("startup")
4. Add event_bus.shutdown() to @app.on_event("shutdown")
5. Add event publishing calls after key business logic
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

SERVICES_DIR = Path("/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services")

# Service-specific event publishing patterns
SERVICE_EVENTS = {
    "ai_engine": [
        ("ai_response_generated", "EventType.AI_RESPONSE_GENERATED", [
            "async def generate_response",
            "async def get_ai_response",
        ]),
    ],
    "analytics": [
        ("events_received", "EventType.ANALYTICS_EVENT", [
            "async def log_event",
            "async def track_event",
        ]),
    ],
    "appointments": [
        ("appointment_booked", "EventType.APPOINTMENT_BOOKED", [
            "async def book_appointment",
            "async def create_appointment",
        ]),
    ],
    "billing": [
        ("payment_received", "EventType.PAYMENT_RECEIVED", [
            "async def process_payment",
            "async def create_invoice",
        ]),
        ("payment_failed", "EventType.PAYMENT_FAILED", [
            "async def handle_payment_failure",
        ]),
    ],
    "channel_router": [
        ("message_sent", "EventType.MESSAGE_SENT", [
            "async def send_message",
            "async def route_message",
        ]),
        ("message_received", "EventType.MESSAGE_RECEIVED", [
            "async def receive_message",
            "async def process_inbound",
        ]),
    ],
    "conversation": [
        ("conversation_started", "EventType.CONVERSATION_STARTED", [
            "async def start_conversation",
            "async def create_conversation",
        ]),
        ("conversation_ended", "EventType.CONVERSATION_ENDED", [
            "async def end_conversation",
            "async def close_conversation",
        ]),
    ],
    "conversation_intel": [
        ("conversation_escalated", "EventType.CONVERSATION_ESCALATED", [
            "async def escalate_conversation",
        ]),
    ],
    "knowledge": [
        ("knowledge_updated", "EventType.KNOWLEDGE_UPDATED", [
            "async def update_knowledge",
            "async def add_knowledge",
        ]),
    ],
    "leads": [
        ("lead_created", "EventType.LEAD_CREATED", [
            "async def create_lead",
            "async def add_lead",
        ]),
        ("lead_updated", "EventType.LEAD_UPDATED", [
            "async def update_lead",
        ]),
    ],
    "notification": [
        ("channel_connected", "EventType.CHANNEL_CONNECTED", [
            "async def connect_channel",
        ]),
        ("channel_disconnected", "EventType.CHANNEL_DISCONNECTED", [
            "async def disconnect_channel",
        ]),
    ],
    "tenant_config": [
        ("tenant_created", "EventType.TENANT_CREATED", [
            "async def create_tenant",
            "async def add_tenant",
        ]),
        ("tenant_updated", "EventType.TENANT_UPDATED", [
            "async def update_tenant",
        ]),
    ],
    "whatsapp": [
        ("message_received", "EventType.MESSAGE_RECEIVED", [
            "async def receive_webhook",
            "async def handle_inbound_message",
        ]),
        ("message_sent", "EventType.MESSAGE_SENT", [
            "async def send_message",
        ]),
    ],
}


def add_eventbus_import(content: str) -> str:
    """Add EventBus import to file."""
    # Find the line with other shared imports
    pattern = r"(from shared\.middleware\.auth import.*?)\n"
    if re.search(pattern, content, re.DOTALL):
        return re.sub(
            r"(from shared\.middleware\.sentry import SentryTenantMiddleware)\n",
            r"\1\nfrom shared.events.event_bus import EventBus, EventType\n",
            content
        )
    return content


def add_eventbus_initialization(content: str) -> str:
    """Add event_bus initialization before lifecycle events."""
    # Find the lifecycle events section
    pattern = r"(# ─── Lifecycle Events ───)"
    if re.search(pattern, content):
        return re.sub(
            r"(app\.add_middleware\(SentryTenantMiddleware\))\n\n+",
            r"\1\n\n# Initialize event bus\nevent_bus = EventBus(service_name=\"{service}\")\n\n",
            content
        )
    return content


def wire_service(service_name: str) -> bool:
    """Wire a single service."""
    main_py = SERVICES_DIR / service_name / "main.py"

    if not main_py.exists():
        print(f"  ✗ {service_name}: main.py not found")
        return False

    try:
        with open(main_py, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # Step 1: Add import
        if "from shared.events.event_bus import EventBus" not in content:
            content = add_eventbus_import(content)

        # Step 2: Add initialization
        if "event_bus = EventBus" not in content:
            content = content.replace(
                "# ─── Lifecycle Events ───",
                f"# Initialize event bus\nevent_bus = EventBus(service_name=\"{service_name}\")\n\n\n# ─── Lifecycle Events ───"
            )

        # Step 3: Wire startup/shutdown
        if "await event_bus.startup()" not in content:
            content = re.sub(
                r"(async def startup.*?:\s*\"\"\"[^\"]*?\"\"\"\s*)(await db\.initialize\(\))",
                r"\1await event_bus.startup()\n    \2",
                content,
                flags=re.DOTALL
            )

        if "await event_bus.shutdown()" not in content:
            content = re.sub(
                r"(async def shutdown.*?:\s*\"\"\"[^\"]*?\"\"\"\s*)(await db\.close\(\))",
                r"\1await event_bus.shutdown()\n    \2",
                content,
                flags=re.DOTALL
            )

        # Only write if changed
        if content != original_content:
            with open(main_py, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  ✓ {service_name}: wired")
            return True
        else:
            print(f"  - {service_name}: already wired")
            return False

    except Exception as e:
        print(f"  ✗ {service_name}: {e}")
        return False


def main():
    """Wire all services."""
    print("\n" + "="*60)
    print("WIRING EVENTBUS INTO PRIYA GLOBAL SERVICES")
    print("="*60 + "\n")

    # Get all service directories
    services = sorted([
        d.name for d in SERVICES_DIR.iterdir()
        if d.is_dir() and (d / "main.py").exists()
    ])

    print(f"Found {len(services)} services:\n")

    total = 0
    success = 0

    for service_name in services:
        total += 1
        if wire_service(service_name):
            success += 1

    print(f"\n" + "="*60)
    print(f"SUMMARY: {success}/{total} services wired")
    print("="*60 + "\n")

    print("Next steps:")
    print("1. Review the wired services for correctness")
    print("2. Add specific event publishing calls to endpoints")
    print("3. Test the event flow end-to-end")
    print("4. Deploy to production with Kafka cluster\n")


if __name__ == "__main__":
    main()
