#!/bin/bash
# Wire EventBus into all remaining Priya Global services
# This script adds EventBus import, initialization, and startup/shutdown wiring

SERVICES_DIR="/sessions/wizardly-eloquent-darwin/mnt/Ai/priya-global/services"

# List of all services to wire (auth is already done)
SERVICES=(
    "ai_engine"
    "ai_training"
    "analytics"
    "appointments"
    "billing"
    "channel_router"
    "compliance"
    "conversation_intel"
    "deployment"
    "ecommerce"
    "email"
    "handoff"
    "health_monitor"
    "knowledge"
    "leads"
    "marketing"
    "marketplace"
    "notification"
    "plugins"
    "rcs"
    "sms"
    "social"
    "telegram"
    "tenant"
    "tenant_config"
    "video"
    "voice"
    "voice_ai"
    "webchat"
    "whatsapp"
    "workflows"
    "gateway"
    "channel-router"
    "advanced_analytics"
    "media"
    "cdn_manager"
)

echo "========================================"
echo "EventBus Wiring Script"
echo "========================================"
echo ""

# Counter for stats
total=0
success=0
skipped=0
failed=0

for service in "${SERVICES[@]}"; do
    service_dir="$SERVICES_DIR/$service"
    main_py="$service_dir/main.py"

    total=$((total + 1))

    # Skip if main.py doesn't exist or is empty
    if [ ! -f "$main_py" ]; then
        echo "⊘ $service: main.py not found"
        skipped=$((skipped + 1))
        continue
    fi

    # Check if already wired
    if grep -q "from shared.events.event_bus import EventBus" "$main_py"; then
        echo "✓ $service: already wired"
        success=$((success + 1))
        continue
    fi

    # Check if service has startup/shutdown events (required for wiring)
    if ! grep -q "@app.on_event.*startup\|@app.on_event.*shutdown" "$main_py"; then
        echo "✗ $service: no startup/shutdown events found"
        failed=$((failed + 1))
        continue
    fi

    echo "→ $service: wiring EventBus..."

    # Use Python to do the wiring
    python3 << 'EOF' "$service" "$main_py"
import sys
import re

service_name = sys.argv[1]
main_py_path = sys.argv[2]

with open(main_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add import (look for other shared imports and add after them)
if "from shared.events.event_bus import EventBus" not in content:
    # Find a good place to add the import (after other shared imports)
    import_pattern = r"(from shared\.middleware\.sentry import SentryTenantMiddleware\n)"
    if re.search(import_pattern, content):
        content = re.sub(
            import_pattern,
            r"\1from shared.events.event_bus import EventBus, EventType\n",
            content
        )

# 2. Add event_bus initialization (after middleware setup, before lifecycle)
if "event_bus = EventBus" not in content:
    # Find where to add it (before lifecycle events section)
    lifecycle_pattern = r"\n# ─── Lifecycle Events ───"
    if re.search(lifecycle_pattern, content):
        content = re.sub(
            lifecycle_pattern,
            f"\n# Initialize event bus\nevent_bus = EventBus(service_name=\"{service_name}\")\n\n# ─── Lifecycle Events ───",
            content
        )

# 3. Wire startup event
if "await event_bus.startup()" not in content:
    # Pattern for startup event
    startup_pattern = r"(@app\.on_event\(\"startup\"\)\s+async def \w+\([^)]*\):\s+\"\"\"[^\"]*?\"\"\"\s+)"
    match = re.search(startup_pattern, content, re.DOTALL)
    if match:
        # Find the first actual code line after docstring
        docstring_end = match.end()
        # Look for the first non-comment, non-whitespace line
        code_start = content.find("await", docstring_end)
        if code_start != -1 and code_start < docstring_end + 500:
            # Insert event_bus startup before first await
            content = content[:code_start] + "await event_bus.startup()\n    " + content[code_start:]

# 4. Wire shutdown event
if "await event_bus.shutdown()" not in content:
    shutdown_pattern = r"(@app\.on_event\(\"shutdown\"\)\s+async def \w+\([^)]*\):\s+\"\"\"[^\"]*?\"\"\"\s+)"
    match = re.search(shutdown_pattern, content, re.DOTALL)
    if match:
        docstring_end = match.end()
        code_start = content.find("await", docstring_end)
        if code_start != -1 and code_start < docstring_end + 500:
            content = content[:code_start] + "await event_bus.shutdown()\n    " + content[code_start:]

# Write back
with open(main_py_path, 'w', encoding='utf-8') as f:
    f.write(content)

EOF

    if [ $? -eq 0 ]; then
        echo "✓ $service: wired successfully"
        success=$((success + 1))
    else
        echo "✗ $service: wiring failed"
        failed=$((failed + 1))
    fi
done

echo ""
echo "========================================"
echo "Summary:"
echo "  Total:   $total"
echo "  Success: $success"
echo "  Skipped: $skipped"
echo "  Failed:  $failed"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Review modified files for correctness"
echo "2. Add event publishing to key endpoints in each service"
echo "3. Test with docker-compose up kafka"
echo "4. Run integration tests"
echo ""
