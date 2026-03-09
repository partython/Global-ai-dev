#!/usr/bin/env python3
"""
Wire EventBus into all Priya Global services.
"""

import re
import sys
from pathlib import Path

SERVICES_DIR = Path("/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services")

# All services (auth already done manually)
SERVICES = [
    "ai_engine", "ai_training", "analytics", "appointments", "billing",
    "channel_router", "compliance", "conversation_intel", "deployment",
    "ecommerce", "email", "handoff", "health_monitor", "knowledge",
    "leads", "marketing", "marketplace", "notification", "plugins",
    "rcs", "sms", "social", "telegram", "tenant", "tenant_config",
    "video", "voice", "voice_ai", "webchat", "whatsapp", "workflows",
    "gateway", "advanced_analytics", "media", "cdn_manager"
]

def wire_service(service_name: str) -> tuple[bool, str]:
    """Wire a single service. Returns (success, message)"""
    main_py = SERVICES_DIR / service_name / "main.py"

    if not main_py.exists():
        return False, f"main.py not found"

    try:
        with open(main_py, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content

        # Check if already wired
        if "from shared.events.event_bus import EventBus" in content:
            return True, "already wired"

        # Step 1: Add import after other shared imports
        if "from shared.middleware.sentry import SentryTenantMiddleware" in content:
            content = content.replace(
                "from shared.middleware.sentry import SentryTenantMiddleware",
                "from shared.middleware.sentry import SentryTenantMiddleware\nfrom shared.events.event_bus import EventBus, EventType"
            )

        # Step 2: Add event_bus initialization before lifecycle section
        lifecycle_match = re.search(r"\n# ─── Lifecycle Events ───", content)
        if lifecycle_match:
            insert_pos = lifecycle_match.start()
            event_bus_init = f"\n# Initialize event bus\nevent_bus = EventBus(service_name=\"{service_name}\")\n"
            content = content[:insert_pos] + event_bus_init + content[insert_pos:]

        # Step 3: Wire startup/shutdown
        # Pattern for startup event
        startup_pattern = r"(@app\.on_event\(['\"]startup['\"]\)\s*async def \w+\([^)]*\):\s*(?:\"\"\"[^\"]*?\"\"\"\s*)?)"
        startup_match = re.search(startup_pattern, content, re.DOTALL)
        if startup_match and "await event_bus.startup()" not in content:
            # Find where to insert (after docstring, before first statement)
            after_sig = startup_match.end()
            # Find the first await or other statement
            first_stmt = re.search(r"\n\s+(await|logger|[a-z_])", content[after_sig:])
            if first_stmt:
                insert_at = after_sig + first_stmt.start() + 1
                indent = "    "
                content = (content[:insert_at] +
                          f"\n{indent}await event_bus.startup()" +
                          content[insert_at:])

        # Pattern for shutdown event
        shutdown_pattern = r"(@app\.on_event\(['\"]shutdown['\"]\)\s*async def \w+\([^)]*\):\s*(?:\"\"\"[^\"]*?\"\"\"\s*)?)"
        shutdown_match = re.search(shutdown_pattern, content, re.DOTALL)
        if shutdown_match and "await event_bus.shutdown()" not in content:
            # Find where to insert (after docstring, before first statement)
            after_sig = shutdown_match.end()
            # Find the first await or other statement
            first_stmt = re.search(r"\n\s+(await|logger|[a-z_])", content[after_sig:])
            if first_stmt:
                insert_at = after_sig + first_stmt.start() + 1
                indent = "    "
                content = (content[:insert_at] +
                          f"\n{indent}await event_bus.shutdown()" +
                          content[insert_at:])

        # Only write if content changed
        if content != original:
            with open(main_py, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, "wired"
        else:
            return False, "no changes made"

    except Exception as e:
        return False, str(e)


def main():
    print("\n" + "="*60)
    print("WIRING EVENTBUS INTO PRIYA GLOBAL SERVICES")
    print("="*60 + "\n")

    success_count = 0
    already_wired = 0
    failed_count = 0

    for service in sorted(SERVICES):
        success, message = wire_service(service)

        if success and message == "already wired":
            print(f"  ✓ {service:25} {message}")
            already_wired += 1
        elif success and message == "wired":
            print(f"  ✓ {service:25} {message}")
            success_count += 1
        else:
            print(f"  ✗ {service:25} {message}")
            failed_count += 1

    print("\n" + "="*60)
    print(f"SUMMARY:")
    print(f"  Newly Wired:  {success_count}")
    print(f"  Already Done: {already_wired}")
    print(f"  Failed:       {failed_count}")
    print(f"  Total:        {len(SERVICES)}")
    print("="*60 + "\n")

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
