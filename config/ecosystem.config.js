/**
 * PM2 Ecosystem Configuration for Priya Global Platform
 *
 * CRITICAL: These services run on ports 9000-9027.
 * PSI AI runs on ports 5001-5009. ZERO OVERLAP.
 *
 * Both can run simultaneously on the same Mac Mini.
 *
 * Port Map:
 *   9000 — API Gateway
 *   9001 — Auth Service
 *   9002 — Tenant Service
 *   9003 — Channel Router
 *   9004 — AI Engine
 *   9010 — WhatsApp Channel
 *   9011 — Email Channel
 *   9012 — Voice Channel
 *   9013 — Social (Instagram + Facebook)
 *   9014 — WebChat Widget
 *   9015 — SMS Channel
 *   9016 — Telegram Channel
 *   9020 — Billing Service
 *   9021 — Analytics Service
 *   9022 — Marketing Manager AI
 *   9023 — E-Commerce Integrations
 *   9024 — Notification Service
 *   9025 — Plugin SDK
 *   9026 — Handoff Service
 *   9027 — Lead Scoring & Pipeline
 *   9028 — Conversation Intelligence
 *   9029 — Appointment Booking
 *   9030 — Knowledge Base v2
 *   9031 — Voice AI (STT/TTS/NLU)
 *   9032 — Video Chat
 *   9033 — RCS Messaging
 *   9034 — Automation Workflows
 *   9035 — Advanced Analytics
 *   9036 — AI Training & Fine-tuning
 *   9037 — Marketplace & App Store
 *   9038 — Compliance & GDPR
 *   9039 — Health Monitor & Service Mesh
 *   9040 — CDN & Asset Manager
 *   9041 — Deployment Manager
 *   9042 — Tenant Configuration Service
 *   9043 — Background Worker (Jobs & Queues)
 *   3000 — Next.js Dashboard/Website
 *
 * Total: 37 services (36 core + 1 worker) + 1 frontend = 38 processes
 */

module.exports = {
  apps: [
    // ─── Layer 0: API Gateway (single entry point) ───
    {
      name: "priya-gateway",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9000 --workers 2",
      cwd: "./services/gateway",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 1: Auth & Tenant ───
    {
      name: "priya-auth",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9001 --workers 2",
      cwd: "./services/auth",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-tenant",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9002 --workers 2",
      cwd: "./services/tenant",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 2: Channel Router ───
    {
      name: "priya-channel-router",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9003 --workers 2",
      cwd: "./services/channel_router",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 3: AI Engine ───
    {
      name: "priya-ai-engine",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9004 --workers 4",
      cwd: "./services/ai_engine",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 4: Channel Services ───
    {
      name: "priya-whatsapp",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9010 --workers 2",
      cwd: "./services/whatsapp",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-email",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9011 --workers 2",
      cwd: "./services/email",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-voice",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9012 --workers 2",
      cwd: "./services/voice",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-social",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9013 --workers 2",
      cwd: "./services/social",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-webchat",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9014 --workers 2",
      cwd: "./services/webchat",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-sms",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9015 --workers 2",
      cwd: "./services/sms",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-telegram",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9016 --workers 2",
      cwd: "./services/telegram",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 5: Business Services ───
    {
      name: "priya-billing",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9020 --workers 2",
      cwd: "./services/billing",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-analytics",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9021 --workers 2",
      cwd: "./services/analytics",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-marketing",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9022 --workers 2",
      cwd: "./services/marketing",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 6: Phase 3 Services ───
    {
      name: "priya-ecommerce",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9023 --workers 2",
      cwd: "./services/ecommerce",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-notifications",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9024 --workers 2",
      cwd: "./services/notification",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-plugins",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9025 --workers 2",
      cwd: "./services/plugins",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-handoff",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9026 --workers 2",
      cwd: "./services/handoff",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 7: Phase 4 Services ───
    {
      name: "priya-leads",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9027 --workers 2",
      cwd: "./services/leads",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-conversation-intel",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9028 --workers 2",
      cwd: "./services/conversation_intel",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-appointments",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9029 --workers 2",
      cwd: "./services/appointments",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-knowledge",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9030 --workers 4",
      cwd: "./services/knowledge",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 8: Phase 5 Services ───
    {
      name: "priya-voice-ai",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9031 --workers 2",
      cwd: "./services/voice_ai",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-video",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9032 --workers 2",
      cwd: "./services/video",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-rcs",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9033 --workers 2",
      cwd: "./services/rcs",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-workflows",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9034 --workers 2",
      cwd: "./services/workflows",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 9: Phase 6 & 7 Services ───
    {
      name: "priya-advanced-analytics",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9035 --workers 2",
      cwd: "./services/advanced_analytics",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-ai-training",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9036 --workers 2",
      cwd: "./services/ai_training",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-marketplace",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9037 --workers 2",
      cwd: "./services/marketplace",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-compliance",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9038 --workers 2",
      cwd: "./services/compliance",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 10: Phase 8 — Platform Operations ───
    {
      name: "priya-health-monitor",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9039 --workers 2",
      cwd: "./services/health_monitor",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-cdn-manager",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9040 --workers 2",
      cwd: "./services/cdn_manager",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },
    {
      name: "priya-deployment",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9041 --workers 2",
      cwd: "./services/deployment",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 10b: Tenant Configuration ───
    {
      name: "priya-tenant-config",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9042 --workers 3",
      cwd: "./services/tenant_config",
      interpreter: "none",
      env: { ENVIRONMENT: "production", LOG_LEVEL: "INFO" },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 10c: Background Worker (Jobs & Queues) ───
    {
      name: "priya-worker",
      script: "uvicorn",
      args: "main:app --host 0.0.0.0 --port 9043 --workers 1",
      cwd: "./services/worker",
      interpreter: "none",
      env: {
        ENVIRONMENT: "production",
        LOG_LEVEL: "INFO",
        WORKER_CONCURRENCY: "5",
        WORKER_QUEUES: "critical,high,normal,low",
      },
      max_restarts: 10,
      restart_delay: 3000,
    },

    // ─── Layer 11: Dashboard (Next.js) ───
    {
      name: "priya-dashboard",
      script: "npm",
      args: "start",
      cwd: "./dashboard",
      interpreter: "none",
      env: {
        NODE_ENV: "production",
        PORT: 3000,
        NEXT_PUBLIC_API_URL: "http://localhost:9000",
      },
      max_restarts: 10,
      restart_delay: 5000,
    },
  ],
};
