# Row Level Security (RLS) Documentation Index

## Quick Navigation

### For First-Time Setup (5 minutes)
1. Start: [`RLS_QUICK_START.md`](RLS_QUICK_START.md) - Setup and quick reference
2. Then: Copy examples from [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md)

### For Deep Understanding (30 minutes)
1. Read: [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md) - Complete technical guide
2. Review: [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md) - Real-world patterns

### For Troubleshooting
1. Quick fixes: [`RLS_QUICK_START.md`](RLS_QUICK_START.md#troubleshooting)
2. Detailed guide: [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#troubleshooting)

## Document Descriptions

### RLS_QUICK_START.md (7.5 KB)
**Audience**: Developers doing initial setup

**Contents**:
- File overview (what was created)
- 5-step installation process
- Common code patterns (5 examples)
- Security checklist
- Verification procedures
- Troubleshooting quick fixes
- Next steps

**Read time**: 5-10 minutes

**Key sections**:
- Installation Steps
- Common Patterns
- Verifying RLS is Working
- Troubleshooting

### RLS_IMPLEMENTATION.md (15 KB)
**Audience**: Technical leads, security reviewers

**Contents**:
- Complete architecture explanation
- Security model details
- RLS policy structure
- Usage in Python and FastAPI
- Admin operations
- Request flow walkthrough
- Security guarantees & limitations
- Detailed troubleshooting
- Performance considerations
- Maintenance procedures
- Best practices

**Read time**: 20-30 minutes

**Key sections**:
- Architecture
- Tables with RLS
- Usage in Python Code
- Usage in FastAPI Routes
- Troubleshooting
- Limitations & Edge Cases
- Security Best Practices

### RLS_INTEGRATION_EXAMPLES.md (16 KB)
**Audience**: Developers implementing features

**Contents**:
- 9 real-world code examples:
  1. Conversation service (before/after)
  2. Customer CRUD operations
  3. Message/conversation threads
  4. Multi-tenant analytics
  5. Bulk operations
  6. Error handling
  7. Middleware usage
  8. Complex JOINs
  9. Testing with RLS
- Best practices summary

**Read time**: 10-15 minutes (or copy-paste specific examples)

**Key sections**:
- Example 1: Conversation Service
- Example 2: Customer Service
- Example 3: Message/Conversation Thread
- Example 4: Multi-Tenant Analytics
- Example 5: Bulk Operations
- Example 6: Error Handling
- Example 7: Middleware Usage
- Example 8: Complex Queries with JOINs
- Example 9: Testing with RLS

## File Locations

### Code Files
```
shared/migrations/alembic/versions/011_row_level_security.py    (Migration)
shared/core/rls.py                                               (Helper module)
shared/tests/test_rls.py                                        (Test suite)
```

### Documentation Files
```
docs/RLS_INDEX.md                        (This file)
docs/RLS_QUICK_START.md                  (Setup guide)
docs/RLS_IMPLEMENTATION.md               (Technical reference)
docs/RLS_INTEGRATION_EXAMPLES.md         (Code examples)
```

## Common Scenarios

### I want to...

#### Add RLS to my new route
→ See: [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md#example-2-customer-service)

#### Understand how RLS works
→ See: [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#architecture)

#### Set up RLS for the first time
→ See: [`RLS_QUICK_START.md`](RLS_QUICK_START.md#installation-steps)

#### Debug an RLS error
→ See: [`RLS_QUICK_START.md`](RLS_QUICK_START.md#troubleshooting) or [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#troubleshooting)

#### Copy a working example
→ See: [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md)

#### Verify RLS is working
→ See: [`RLS_QUICK_START.md`](RLS_QUICK_START.md#verifying-rls-is-working)

#### Understand security guarantees
→ See: [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#security-guarantees)

#### Test my RLS implementation
→ See: [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md#example-9-testing-with-rls)

## Topic Index

### Setup & Installation
- [`RLS_QUICK_START.md`](RLS_QUICK_START.md#installation-steps) - Installation Steps
- [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#maintenance) - Initial Setup

### Usage Patterns
- [`RLS_QUICK_START.md`](RLS_QUICK_START.md#common-patterns) - Common Patterns
- [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md) - Full Examples

### Security
- [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#security-guarantees) - Security Guarantees
- [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#security-best-practices) - Best Practices
- [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md#example-6-error-handling-with-rls) - Error Handling

### Troubleshooting
- [`RLS_QUICK_START.md`](RLS_QUICK_START.md#troubleshooting) - Quick Fixes
- [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#troubleshooting) - Detailed Guide

### Administration
- [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#admin-operations) - Admin Operations
- [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#maintenance) - Maintenance

### Performance
- [`RLS_IMPLEMENTATION.md`](RLS_IMPLEMENTATION.md#performance-considerations) - Performance Guide
- [`RLS_QUICK_START.md`](RLS_QUICK_START.md#performance-notes) - Performance Notes

### Testing
- [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md#example-9-testing-with-rls) - Testing Examples
- [`RLS_QUICK_START.md`](RLS_QUICK_START.md#testing) - Test Running

## Reading Paths

### Path 1: "I want to implement RLS" (30 minutes)
1. Read: [`RLS_QUICK_START.md`](RLS_QUICK_START.md) (5 min)
2. Read: [`RLS_IMPLEMENTATION.md - Architecture`](RLS_IMPLEMENTATION.md#architecture) (5 min)
3. Copy: Examples from [`RLS_INTEGRATION_EXAMPLES.md - Example 2`](RLS_INTEGRATION_EXAMPLES.md#example-2-customer-service) (5 min)
4. Test: Run `pytest shared/tests/test_rls.py` (5 min)
5. Deploy: Follow [`RLS_QUICK_START.md - Deployment Checklist`](RLS_QUICK_START.md#deployment-checklist) (5 min)

### Path 2: "I need to understand the security" (20 minutes)
1. Read: [`RLS_IMPLEMENTATION.md - Security Model`](RLS_IMPLEMENTATION.md#security-model) (5 min)
2. Read: [`RLS_IMPLEMENTATION.md - Security Guarantees`](RLS_IMPLEMENTATION.md#security-guarantees) (5 min)
3. Read: [`RLS_IMPLEMENTATION.md - Security Best Practices`](RLS_IMPLEMENTATION.md#security-best-practices) (5 min)
4. Review: [`RLS_INTEGRATION_EXAMPLES.md - Best Practices`](RLS_INTEGRATION_EXAMPLES.md#best-practices-summary) (5 min)

### Path 3: "I'm troubleshooting an issue" (10 minutes)
1. Check: [`RLS_QUICK_START.md - Troubleshooting`](RLS_QUICK_START.md#troubleshooting) (2 min)
2. Deep dive: [`RLS_IMPLEMENTATION.md - Troubleshooting`](RLS_IMPLEMENTATION.md#troubleshooting) (5 min)
3. Run: Debug queries from documentation (3 min)

### Path 4: "I need code examples" (5-15 minutes)
- Go directly to: [`RLS_INTEGRATION_EXAMPLES.md`](RLS_INTEGRATION_EXAMPLES.md)
- Find relevant example
- Copy and modify for your use case

## Testing Commands

All RLS test suite:
```bash
pytest shared/tests/test_rls.py -v
```

Specific test class:
```bash
pytest shared/tests/test_rls.py::TestRLSPolicies -v
```

Verify RLS in database:
```sql
-- Check RLS enabled
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public';

-- Check policies
SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public';

-- Verify service role
SELECT rolname, bypassrls FROM pg_roles WHERE rolname = 'priya_service_role';
```

## Key Concepts

### tenant_id
Identifies which tenant owns a row. Always set from request context, never from user input.

### app.current_tenant_id
PostgreSQL setting that RLS policies check. Set automatically by `db.tenant_connection()`.

### RLS Policy
Database-level rule that filters rows. Four types per table: SELECT, INSERT, UPDATE, DELETE.

### priya_service_role
Backend service role that can bypass RLS. Used for system operations only.

### require_tenant_context()
Python function that extracts and validates tenant_id from request. Use in all routes.

## Related Code

### Database Module
- File: `shared/core/database.py`
- Already supports RLS via `tenant_connection()`
- No changes needed

### Authentication
- Should set `X-Tenant-ID` header
- Or populate `request.state.user.tenant_id`
- Middleware extracts automatically

### Models/Schemas
- All should include `tenant_id` field
- Should use `uuid.uuid4()` for IDs
- Validate tenant_id is valid UUID

## Additional Resources

PostgreSQL Documentation:
- [Row Level Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [CREATE POLICY](https://www.postgresql.org/docs/current/sql-createpolicy.html)
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html)

Priya Global Docs:
- [Database Setup](../ALEMBIC_SETUP.md)
- [Security Audit](../SECURITY_AUDIT_REPORT.md)

## Support

For questions:
1. Check relevant section in this index
2. Read the linked documentation file
3. Search the troubleshooting section
4. Review the code examples
5. Run the test suite to verify setup

## Summary

Priya Global's RLS implementation provides three complementary documents:

1. **Quick Start** - Setup in 5 minutes
2. **Implementation** - Understanding in detail
3. **Examples** - Copy-paste code patterns

Start with Quick Start, then explore other documents as needed.
