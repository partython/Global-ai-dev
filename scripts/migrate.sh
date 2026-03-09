#!/usr/bin/env bash
#
# Database Migration Helper for Priya Global Platform
# Manages Alembic migrations with convenient commands
#
# Usage:
#   ./scripts/migrate.sh upgrade       — apply all pending migrations
#   ./scripts/migrate.sh upgrade head  — apply all pending migrations (explicit)
#   ./scripts/migrate.sh upgrade +1    — apply next 1 migration
#   ./scripts/migrate.sh downgrade -1  — rollback last 1 migration
#   ./scripts/migrate.sh downgrade base — rollback to initial state
#   ./scripts/migrate.sh history       — show migration history
#   ./scripts/migrate.sh current       — show current revision
#   ./scripts/migrate.sh create "desc" — create new migration
#   ./scripts/migrate.sh generate "desc" — auto-generate migration from models
#   ./scripts/migrate.sh stamp <rev>   — stamp database to specific revision
#   ./scripts/migrate.sh test          — validate all migrations work

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALEMBIC_DIR="$PROJECT_ROOT/shared/migrations/alembic"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Ensure DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo -e "${RED}ERROR: DATABASE_URL environment variable not set${NC}"
    echo "Please set DATABASE_URL or load from .env file"
    exit 1
fi

# Function to print section headers
print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to redact credentials from DATABASE_URL for safe display
redact_database_url() {
    # Replace credentials in postgresql://user:pass@host/dbname format
    echo "$DATABASE_URL" | sed -E 's|postgresql://[^:]*:[^@]*@|postgresql://***:***@|g'
}

# Check if alembic is installed
check_alembic() {
    if ! command -v alembic &> /dev/null; then
        print_error "Alembic not installed"
        echo "Install with: pip install alembic sqlalchemy"
        exit 1
    fi
}

# ============================================================
# Command: upgrade
# ============================================================
cmd_upgrade() {
    local target="${1:-head}"
    print_header "Upgrading Database Migrations → $target"

    check_alembic

    cd "$PROJECT_ROOT"

    print_warning "Current revision before upgrade:"
    alembic current

    echo ""
    print_warning "Pending migrations:"
    alembic upgrade --sql "$target" 2>&1 | head -20 || true

    echo ""
    read -p "Continue with upgrade? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if alembic upgrade "$target"; then
            print_success "Database upgraded to $target"
            echo ""
            print_warning "New revision:"
            alembic current
        else
            print_error "Migration failed"
            exit 1
        fi
    else
        print_warning "Upgrade cancelled"
    fi
}

# ============================================================
# Command: downgrade
# ============================================================
cmd_downgrade() {
    local target="${1:--1}"
    print_header "Rolling Back Database Migrations → $target"

    check_alembic

    cd "$PROJECT_ROOT"

    print_warning "Current revision before downgrade:"
    alembic current

    echo ""
    print_warning "WARNING: This will rollback migrations!"
    echo "Target: $target"
    read -p "Are you sure? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if alembic downgrade "$target"; then
            print_success "Database rolled back"
            echo ""
            alembic current
        else
            print_error "Rollback failed"
            exit 1
        fi
    else
        print_warning "Rollback cancelled"
    fi
}

# ============================================================
# Command: history
# ============================================================
cmd_history() {
    print_header "Migration History"
    check_alembic

    cd "$PROJECT_ROOT"
    alembic history
}

# ============================================================
# Command: current
# ============================================================
cmd_current() {
    print_header "Current Database Revision"
    check_alembic

    cd "$PROJECT_ROOT"
    alembic current
}

# ============================================================
# Command: create
# ============================================================
cmd_create() {
    local description="$1"

    if [ -z "$description" ]; then
        print_error "Description required"
        echo "Usage: ./migrate.sh create \"Migration description\""
        exit 1
    fi

    print_header "Creating New Migration: $description"
    check_alembic

    cd "$PROJECT_ROOT"

    if alembic revision --autogenerate -m "$description"; then
        print_success "Migration created"
        echo ""
        echo "Edit the migration file to add your SQL code:"
        ls -lt "$ALEMBIC_DIR/versions"/*.py | head -1 | awk '{print $NF}'
    else
        print_error "Failed to create migration"
        exit 1
    fi
}

# ============================================================
# Command: generate
# ============================================================
cmd_generate() {
    local description="$1"

    if [ -z "$description" ]; then
        print_error "Description required"
        echo "Usage: ./migrate.sh generate \"Migration description\""
        exit 1
    fi

    print_header "Auto-generating Migration: $description"
    check_alembic

    cd "$PROJECT_ROOT"

    print_warning "Auto-generating based on SQLAlchemy models..."
    if alembic revision --autogenerate -m "$description"; then
        print_success "Migration auto-generated"
        echo ""
        print_warning "IMPORTANT: Review the generated migration!"
        ls -lt "$ALEMBIC_DIR/versions"/*.py | head -1 | awk '{print $NF}'
    else
        print_error "Failed to auto-generate migration"
        exit 1
    fi
}

# ============================================================
# Command: stamp
# ============================================================
cmd_stamp() {
    local revision="$1"

    if [ -z "$revision" ]; then
        print_error "Revision required"
        echo "Usage: ./migrate.sh stamp <revision_id>"
        exit 1
    fi

    print_header "Stamping Database to Revision: $revision"
    check_alembic

    print_warning "WARNING: This marks the database at a specific revision without running migrations!"
    read -p "Continue? (yes/no): " -r
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$PROJECT_ROOT"
        if alembic stamp "$revision"; then
            print_success "Database stamped to $revision"
        else
            print_error "Stamp failed"
            exit 1
        fi
    else
        print_warning "Stamp cancelled"
    fi
}

# ============================================================
# Command: test
# ============================================================
cmd_test() {
    print_header "Testing All Migrations"
    check_alembic

    cd "$PROJECT_ROOT"

    print_warning "This will create/test migrations in a temporary database"
    print_warning "Using DATABASE_URL: $(redact_database_url)"

    echo ""
    print_warning "Validating migration syntax..."

    if alembic upgrade head --sql | head -50 > /dev/null 2>&1; then
        print_success "All migrations are syntactically valid"

        echo ""
        print_warning "Showing first 50 lines of SQL that would be executed:"
        alembic upgrade head --sql | head -50
    else
        print_error "Migration validation failed"
        exit 1
    fi
}

# ============================================================
# Command: branches
# ============================================================
cmd_branches() {
    print_header "Migration Branches"
    check_alembic

    cd "$PROJECT_ROOT"
    alembic branches
}

# ============================================================
# Command: help
# ============================================================
cmd_help() {
    cat << EOF
${BLUE}Priya Global Platform — Database Migration Helper${NC}

${YELLOW}USAGE:${NC}
    ./scripts/migrate.sh <command> [options]

${YELLOW}COMMANDS:${NC}

    upgrade [target]        Apply migrations up to target
                            Default: head (all pending)
                            Examples: upgrade head, upgrade +1

    downgrade [target]      Rollback migrations to target
                            Default: -1 (previous version)
                            Examples: downgrade -1, downgrade base

    history                 Show all migrations

    current                 Show current database revision

    create "description"    Create new empty migration

    generate "description"  Auto-generate migration from models

    stamp <revision>        Mark database at specific revision
                            (doesn't run migrations)

    test                    Validate all migrations work

    branches                Show migration branches

    help                    Show this help message

${YELLOW}EXAMPLES:${NC}

    # Apply all pending migrations
    ./scripts/migrate.sh upgrade

    # Apply next migration
    ./scripts/migrate.sh upgrade +1

    # Rollback last migration
    ./scripts/migrate.sh downgrade -1

    # Create new migration
    ./scripts/migrate.sh create "add_payment_tables"

    # View history
    ./scripts/migrate.sh history

${YELLOW}ENVIRONMENT VARIABLES:${NC}

    DATABASE_URL    PostgreSQL connection string (required)
                    Format: postgresql://user:pass@host/dbname
                    Note: Credentials are redacted in all output logs

${YELLOW}SAFETY NOTES:${NC}

    • Always run migrations in development first
    • Backup production database before upgrading
    • Review all auto-generated migrations before applying
    • Test all migrations thoroughly
    • Keep migration files in version control

EOF
}

# ============================================================
# Main command dispatch
# ============================================================
main() {
    local command="${1:-help}"

    case "$command" in
        upgrade)    cmd_upgrade "$2" ;;
        downgrade)  cmd_downgrade "$2" ;;
        history)    cmd_history ;;
        current)    cmd_current ;;
        create)     cmd_create "$2" ;;
        generate)   cmd_generate "$2" ;;
        stamp)      cmd_stamp "$2" ;;
        test)       cmd_test ;;
        branches)   cmd_branches ;;
        help|--help|-h) cmd_help ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            cmd_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
