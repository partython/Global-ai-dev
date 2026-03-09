# Partython.ai — Quarterly Security Audit Schedule

**Owner:** Partython (Vinhoth)
**Last Updated:** 2026-03-08
**Review Cadence:** Quarterly (Q1 Jan, Q2 Apr, Q3 Jul, Q4 Oct)

---

## Q1 (January) — Infrastructure & Access Review

| Task | Tool / Method | Owner |
|------|--------------|-------|
| Rotate all API keys & secrets | AWS Secrets Manager + `.env` | DevOps |
| Review IAM roles & permissions | AWS IAM Access Analyzer | DevOps |
| Audit Terraform drift | `terraform plan` against live infra | DevOps |
| SSL/TLS certificate expiry check | AWS Certificate Manager | DevOps |
| Review VPC security groups & NACLs | AWS Console / Terraform | DevOps |
| Database access audit (Neon Postgres) | Connection logs, RLS policy review | Backend |
| Dependency vulnerability scan | `pip audit`, `npm audit`, Snyk | Backend + Frontend |

## Q2 (April) — Application Security

| Task | Tool / Method | Owner |
|------|--------------|-------|
| OWASP Top 10 penetration test | OWASP ZAP / Burp Suite | Security |
| API endpoint authorization review | Manual + automated test suite | Backend |
| Prompt injection defense audit | Red-team LLM inputs | AI Team |
| XSS / CSRF testing on dashboard | Playwright E2E security tests | Frontend |
| Rate limiting validation | Load test all public endpoints | Backend |
| JWT token handling review | Check RS256 signing, expiry, refresh flow | Backend |
| Input validation audit | Review all user-facing endpoints | Backend |

## Q3 (July) — Data & Compliance

| Task | Tool / Method | Owner |
|------|--------------|-------|
| PII logging audit | Grep codebase for unmasked PII in logs | Backend |
| Data retention policy review | Check TTLs, auto-cleanup jobs | Backend |
| GDPR / data privacy compliance check | Manual review + legal counsel | Legal + Backend |
| Backup & disaster recovery drill | Restore from backup, measure RTO/RPO | DevOps |
| Multi-tenant data isolation test | Cross-tenant access attempt testing | Backend |
| Encryption audit (at-rest & in-transit) | AWS KMS, TLS config review | DevOps |
| Third-party vendor security review | Review SLAs for Neon, Vercel, Twilio, etc. | Business |

## Q4 (October) — Pre-Annual Review

| Task | Tool / Method | Owner |
|------|--------------|-------|
| Full security scan (SAST + DAST) | SonarQube + OWASP ZAP | Security |
| Incident response plan test | Tabletop exercise / fire drill | All |
| Security header audit | Mozilla Observatory, securityheaders.com | Frontend |
| WAF rule effectiveness review | AWS WAF logs analysis | DevOps |
| Social engineering awareness | Phishing simulation for team | HR + Security |
| Annual penetration test (external) | Engage third-party pen-test firm | Security |
| Security documentation update | Review all runbooks, audit this schedule | All |

---

## Continuous (Every Sprint)

These run automatically or as part of CI/CD:

- **Dependency scanning:** Snyk / `pip audit` / `npm audit` on every PR
- **SAST scanning:** SonarQube on every merge to main
- **Container image scanning:** Trivy on every Docker build
- **Secret detection:** git-secrets / truffleHog pre-commit hooks
- **Uptime monitoring:** Health checks every 60s (existing health_monitor service)
- **Error tracking:** Sentry alerts for unhandled exceptions

---

## Escalation & Reporting

- **Critical findings** (data breach, RCE, auth bypass): Fix within 24 hours, notify all stakeholders
- **High findings** (SQLi, XSS, privilege escalation): Fix within 7 days
- **Medium findings** (misconfig, info disclosure): Fix within 30 days
- **Low findings** (best practice gaps): Schedule for next sprint

All audit results are documented in `/docs/security/audit-reports/YYYY-QN-report.md`.

---

## Next Scheduled Audit

**Q2 2026 (April):** Application Security — OWASP Top 10 pen test, API auth review, prompt injection red-teaming.
