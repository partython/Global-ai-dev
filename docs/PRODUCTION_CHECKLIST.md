# Partython.ai — Production Readiness Checklist (Global Launch)

> Last updated: March 9, 2026 (Phase 0 code complete)
> Status: PHASE 0 CODE COMPLETE — awaiting external registrations (DLT, Meta, Razorpay KYC)
> Target: Global SaaS platform — India first, then international

---

## 1. AUTHENTICATION & SIGNUP (CRITICAL — Currently Bot Vulnerable)

### 1.1 Signup Methods — Passwordless Only
- [x] **Google OAuth 2.0** ✅ `services/auth/main.py` — `/api/v1/auth/oauth/google` endpoint
  - Covers: Gmail users + Google Workspace custom domains (e.g., ceo@company.com on GSuite)
  - Scope: `openid email profile`
  - Verifies `email_verified: true` from Google's ID token before account creation
  - Auto-creates tenant + wallet on first login
  - ⚠️ NEEDS: Google Cloud Console OAuth 2.0 Client ID (production credentials)
- [ ] **Apple Sign-In** (Phase 2 — iOS app)
  - Required if distributing iOS app (App Store mandate)
  - Apple Developer account → Services → Sign In with Apple
  - Handle Apple's "Hide My Email" relay addresses
- [x] **Email OTP (Magic Code)** ✅ `services/auth/main.py` — `/api/v1/auth/otp/request` + `/api/v1/auth/otp/verify`
  - 6-digit OTP, 10-minute expiry, single-use
  - OTP stored hashed (SHA-256) — never plain text
  - Max 5 OTP requests per email per hour (Redis rate limiting)
  - Max 3 failed verification attempts per OTP
  - Auto-creates tenant + wallet on first login
  - ⚠️ NEEDS: MSG91 or SES configured for actual email delivery

### 1.2 Anti-Bot Protection
- [x] **Cloudflare Turnstile** ✅ Server-side verification in auth service + frontend invisible widget
  - Dev mode: auto-pass when key starts with "1x0000" (test keys configured)
  - ⚠️ NEEDS: Production Turnstile site key + secret from Cloudflare dashboard
- [x] **Rate limiting** ✅ Redis-backed in auth service
  - OTP request: max 5 per email per hour
  - Failed OTP verification: max 3 per OTP, then invalidate
- [x] **Disposable email blocklist** ✅ 16 domains blocked in auth service
  - TODO: Expand to full ~4000 domain list from GitHub repo
- [ ] **Device fingerprinting** (Phase 2)
  - FingerprintJS for browser fingerprint

### 1.3 Phone Number Verification — Mandatory Before Paid Features
- [x] **Indian mobile OTP** ✅ `services/auth/main.py` — `/api/v1/auth/phone/request-otp` + `/api/v1/auth/phone/verify`
  - MSG91 integration for OTP delivery (dev mode: logs to console)
  - Rate limited: 3 requests/user/hour
  - Store verified phone in users table
  - ⚠️ NEEDS: MSG91 production auth key + OTP template ID
- [ ] **International phone OTP** (Phase 2)
  - Provider: MSG91 (covers 190+ countries) or Twilio Verify
- [x] **Phone number uniqueness** ✅ Unique index on `users.phone_number` WHERE `phone_verified = true`

### 1.4 Session & Token Security
- [ ] Migrate from sessionStorage JWT to **httpOnly cookie sessions** (TODO: frontend migration)
  - ⚠️ Backend table `user_sessions` created in migration 013
- [x] Access token: 15-minute expiry ✅ (RS256 JWT)
- [x] Refresh token: 7-day expiry ✅ (with rotation)
- [ ] Force logout on email change (invalidate all sessions for that user)
- [ ] Concurrent session limit: max 5 active sessions per user
- [x] Session table ✅ `user_sessions` — user_id, token_hash, device_info, ip, created_at, last_used, expires_at (migration 013)

### 1.5 Business Verification (Before High-Value Features)
- [ ] Optional GST verification via GST API (validates business legitimacy)
- [ ] Optional PAN verification
- [ ] Verified businesses get: higher rate limits, priority support, branded sender IDs
- [ ] KYC document upload + storage (encrypted S3, access-controlled)

---

## 2. OTP INFRASTRUCTURE — DLT COMPLIANCE (INDIA REGULATORY)

### 2.1 Why This Matters
> TRAI mandates DLT registration for ALL A2P (Application-to-Person) SMS in India.
> Without DLT compliance, your OTPs and transactional SMS will be BLOCKED by telecom operators.
> This is a hard blocker — no DLT = no SMS delivery in India.

### 2.2 DLT Entity Registration (One-Time, ~3-7 Days)
- [ ] **Choose DLT portal**: Jio DLT (https://trueconnect.jio.com) — recommended (free registration, fastest approval)
  - Alternatives: Airtel (https://www.airtel.in/business/commercial-communication), Vodafone-Idea, BSNL
  - You only need to register on ONE portal — it works across all operators
- [ ] **Register as "Enterprise"** (not Telemarketer — that's for agencies sending on behalf of others)
- [ ] **Documents needed**:
  - Company PAN card
  - GST registration certificate
  - Certificate of Incorporation / Partnership deed
  - Authorized signatory's Aadhaar + PAN
  - Company letterhead (for authorization letter)
  - Company email domain verification
- [ ] **Entity details to submit**:
  - Legal entity name: "Partython Inc" (or your registered company name)
  - Entity type: Private Limited / LLP / Proprietorship
  - Registered address
  - Authorized person details + mobile number (for OTP verification during registration)
- [ ] **Receive Entity ID** (format: `1XXXXXXXXXXXXXXXXX`) — save this, needed for all SMS sending
- [ ] **Estimated timeline**: Jio = 15 min to 72 hours; Airtel = 2-3 business days
- [ ] **Cost**: Jio = FREE as of 2026; Airtel = ₹590-1180 + GST one-time

### 2.3 Sender ID / Header Registration
- [ ] **Register platform headers** on DLT portal:
  - `PRIYAI` — for transactional messages (OTPs, alerts)
    - Will appear as: `XX-PRIYAI-T` on recipient's phone (TRAI May 2025 suffix rule)
  - `PRIYAM` — for service messages (if needed)
    - Will appear as: `XX-PRIYAM-S`
  - Header rules: exactly 6 alphabetic characters, no numbers/special chars
- [ ] **Header approval timeline**: 24-48 hours on Jio
- [ ] **Note**: The `-T`, `-P`, `-S`, `-G` suffixes are added AUTOMATICALLY by telecom operators based on template category. You do NOT add them yourself. This is per TRAI's Feb 2025 regulation effective May 6, 2025.

### 2.4 SMS Template Registration
- [ ] **Register ALL SMS templates** on DLT portal before they can be sent:

  **Platform OTP Templates (Transactional category):**
  - [ ] `Your Partython.ai verification code is {#var#}. Valid for 10 minutes. Do not share.`
  - [ ] `{#var#} is your OTP for Partython.ai login. Expires in 10 min. -PRIYAI`
  - [ ] `Use {#var#} to verify your phone number on Partython.ai. Do not share this code.`

  **Platform Notification Templates (Service/Transactional):**
  - [ ] `Your Partython.ai wallet balance is low (Rs.{#var#}). Top up to avoid service interruption.`
  - [ ] `Payment of Rs.{#var#} received. Your Partython.ai wallet balance is now Rs.{#var#}.`
  - [ ] `Your {#var#} channel has been disconnected. Log in to reconnect: {#var#}`
  - [ ] `New conversation from {#var#} on {#var#}. Reply in your Partython.ai dashboard.`

  **Template rules:**
  - Each `{#var#}` is a variable placeholder (up to 30 chars per variable)
  - Template must match EXACTLY when sending (no extra spaces, different punctuation)
  - Approval timeline: 24-48 hours
  - Each template gets a unique Template ID (format: `1XXXXXXXXXXXXXXXXX`)
  - Store Template IDs in your config/database — needed for every SMS API call

### 2.5 SMS Provider Setup (MSG91 Recommended)
- [ ] **Create MSG91 account** at https://msg91.com
  - Why MSG91 over Fast2SMS: better multi-tenant DLT management, webhook delivery reports, OTP widget, email+SMS+WhatsApp unified API
- [ ] **Link DLT Entity**: In MSG91 dashboard → Settings → DLT → Add Entity ID
- [ ] **Add Sender IDs**: Add your DLT-approved headers (PRIYAI, etc.)
- [ ] **Add Templates**: Import DLT-approved templates with Template IDs
- [ ] **Get API Key**: Dashboard → API → Copy authorization key
- [ ] **Configure OTP settings**:
  - OTP length: 6 digits
  - OTP expiry: 10 minutes (600 seconds)
  - Retry type: text → voice (if SMS fails, auto-retry as voice call)
  - Auto-detect OTP (Android SMS Retriever API hash)

### 2.6 MSG91 OTP API Integration
```
// Send OTP
POST https://control.msg91.com/api/v5/otp
Headers: { "authkey": "YOUR_MSG91_AUTH_KEY" }
Body: {
  "template_id": "YOUR_DLT_TEMPLATE_ID",
  "mobile": "91XXXXXXXXXX",
  "otp_length": 6,
  "otp_expiry": 10
}

// Verify OTP
POST https://control.msg91.com/api/v5/otp/verify
Body: { "mobile": "91XXXXXXXXXX", "otp": "123456" }

// Resend OTP
POST https://control.msg91.com/api/v5/otp/retry
Body: { "mobile": "91XXXXXXXXXX", "retrytype": "text" }
```

### 2.7 International OTP (For Global Users)
- [ ] **MSG91 international**: covers 190+ countries, ~$0.03-0.08/SMS
- [ ] **Alternative**: Twilio Verify ($0.05/verification, handles retries + voice fallback)
- [ ] **WhatsApp OTP channel**: cheaper for countries with high WhatsApp penetration
  - Use Meta's WhatsApp Cloud API authentication template (₹0.13/msg India, varies by country)
  - Fallback to SMS if user doesn't have WhatsApp
- [ ] **Email OTP as fallback**: free, works everywhere, slightly less secure than SMS

---

## 3. WALLET / CREDITS / PREPAID BILLING

### 3.1 Wallet Microservice
- [x] Create `wallet_service` microservice ✅ `services/wallet/main.py` (948 lines, port 9050)
- [ ] **Database tables**:
  ```
  wallets: tenant_id (PK), balance_paisa (BIGINT), currency (default 'INR'),
           last_topped_up, auto_topup_enabled, auto_topup_amount_paisa,
           auto_topup_threshold_paisa, created_at, updated_at

  wallet_transactions: id (UUID), tenant_id, type (topup/debit/refund/adjustment),
                       amount_paisa, running_balance_paisa, channel, action,
                       description, reference_id, metadata (JSONB), created_at

  pricing_rules: id, channel, action, cost_paisa, currency, effective_from,
                 effective_until, plan_tier, created_at
  ```
- [x] **All amounts stored in paisa** ✅ (integer, BIGINT CHECK >= 0)
- [x] **Atomic balance operations** ✅ `UPDATE wallet_accounts SET balance_paisa = balance_paisa - $1 WHERE tenant_id = $3 AND balance_paisa >= $1`
  - Single query, no race conditions, fails if insufficient balance
- [x] Row-level locking on wallet updates ✅ (atomic UPDATE with balance check)

### 3.2 Payment Integration
- [x] **Razorpay** ✅ Full integration in `services/wallet/main.py`
  - Create Razorpay Order → user pays → verify signature → credit wallet
  - Webhook handler with HMAC-SHA256 signature verification
  - Minimum top-up: ₹100 (configurable)
  - ⚠️ NEEDS: Production Razorpay API key + secret (KYC completion)
- [ ] **Stripe** for international users (credit cards, Apple Pay, Google Pay)
  - Stripe India is invite-only since May 2024 — apply early
  - Alternative: Razorpay International (supports 100+ currencies)
  - PaymentIntent flow → webhook confirms → credit wallet in user's currency
- [ ] **Multi-currency support**:
  - Store wallet in user's local currency (INR, USD, EUR, GBP, etc.)
  - Pricing table per currency per channel
  - Exchange rate updates daily (Open Exchange Rates API or similar)
- [ ] **GST handling**: 18% GST on platform services for Indian businesses
  - Invoice generation with GSTIN, SAC code (998314 — IT services)
  - Monthly/quarterly GST filing

### 3.3 Pricing (Actual 2026 Rates with Margin)

**WhatsApp (India — per-message pricing effective Jan 1, 2026):**
| Category | Meta Charges You | You Charge Tenant | Margin |
|---|---|---|---|
| Marketing | ₹0.88 | ₹1.20 | 36% |
| Utility | ₹0.13 | ₹0.25 | 92% |
| Authentication (OTP) | ₹0.13 | ₹0.25 | 92% |
| Service (24hr window) | FREE | FREE | — |

**SMS (India):**
| Type | Provider Cost | You Charge | Margin |
|---|---|---|---|
| Transactional (DLT) | ₹0.15-0.20 | ₹0.35 | ~85% |
| OTP via MSG91 | ₹0.20 | ₹0.35 | 75% |
| Quick SMS (no DLT) | ₹5.00 | ₹6.00 | 20% |

**Voice — WhatsApp Business Calling (Default):**
| Type | Provider Cost | You Charge | Margin |
|---|---|---|---|
| WhatsApp voice per min | TBD (check Meta pricing) | ₹2.00 | TBD |
| Note: No extra number cost — uses tenant's existing WhatsApp Business number |

**Voice — Traditional Numbers (Premium Add-On, Exotel):**
| Type | Provider Cost | You Charge | Margin |
|---|---|---|---|
| Exophone rental (2 per tenant) | ₹1,000-2,000/month | ₹3,000/month | ~60% |
| Inbound per min | ₹1.00-1.50 | ₹2.50 | ~80% |
| Outbound per min | ₹1.50-2.00 | ₹3.00 | ~60% |

**AI Bot:**
| Model | Your Cost | You Charge | Margin |
|---|---|---|---|
| GPT-4o mini | ~₹0.02/response | ₹0.15 | ~87% |
| GPT-4o | ~₹0.20/response | ₹0.50 | ~60% |
| Claude Sonnet | ~₹0.15/response | ₹0.40 | ~63% |

- [x] Store all pricing in wallet service config ✅ (CHANNEL_COSTS dict, `/api/v1/wallet/pricing` endpoint)
  - TODO: Move to `pricing_rules` DB table for admin dashboard editing
- [ ] Admin dashboard to update pricing without code deploy
- [ ] Per-tenant custom pricing for enterprise deals

### 3.4 Balance Controls
- [x] **Low balance warning** ✅ Auto-topup trigger in wallet debit flow
- [ ] **Critical balance** at ₹25: urgent notification, limited to essential messages only
- [ ] **Zero balance** → **pause all paid channels**: bot stops, outbound calls blocked, SMS blocked
- [x] **Auto top-up** ✅ `PUT /api/v1/wallet/auto-topup` — configurable threshold + amount
- [ ] Balance check **middleware in gateway**: reject outbound API calls if balance insufficient
- [x] **Refund mechanism** ✅ `POST /api/v1/wallet/adjust` — admin adjustment/refund endpoint

---

## 4. CHANNEL CONNECTIONS

### 4.1 Meta (WhatsApp + Instagram + Facebook)

#### Meta App Setup (One-Time, 1-2 Weeks)
- [x] Create Meta App at https://developers.facebook.com ✅
- [x] App type: "Business" ✅
- [x] Add products: WhatsApp, Instagram, Facebook Login ✅
- [x] **Business Verification** ✅ DONE
  - Documents: business registration, utility bill, domain verification (DNS TXT record)
  - COMPLETED — verified by Meta
- [ ] **App Review** (required for Embedded Signup at scale): ⚠️ SUBMIT NOW
  - Record 2 demo videos (screencast):
    1. Embedded Signup flow: user clicks Connect → Meta popup → authorizes → token received
    2. Message flow: send + receive WhatsApp/Instagram/Messenger message
  - Submit with descriptions of data usage
  - Timeline: 3-7 business days (can take longer if rejected)
- [ ] Enable **Advanced Access** for permissions:
  - `whatsapp_business_management` — manage WABAs
  - `whatsapp_business_messaging` — send/receive messages
  - `instagram_basic` — read Instagram profile
  - `instagram_manage_messages` — send/receive DMs
  - `pages_messaging` — Messenger
  - `pages_manage_metadata` — Page info
  - `pages_read_engagement` — Page insights
  - `business_management` — business assets
- [ ] Set App Mode to **Live** (not Development)

#### Embedded Signup Implementation (Replaces Current OAuth Redirect)
- [x] Load Meta JS SDK: `<script src="https://connect.facebook.net/en_US/sdk.js">` ✅ dashboard/channels/page.tsx
- [x] Initialize: `FB.init({ appId: META_APP_ID, version: 'v18.0' })` ✅ dashboard/channels/page.tsx
- [x] Trigger Embedded Signup: ✅ dashboard/channels/page.tsx — initiateMetaOAuth()
  ```javascript
  FB.login(function(response) {
    // response.authResponse.code → exchange for System User token
  }, {
    config_id: 'YOUR_CONFIG_ID',  // Created in Meta App Dashboard
    response_type: 'code',
    override_default_response_type: true,
    extras: {
      setup: { /* channel-specific config */ },
      featureType: '',
      sessionInfoVersion: 2,
    }
  });
  ```
- [x] Server-side: exchange code for System User token via Graph API ✅ services/whatsapp/main.py — /api/v1/embedded-signup
- [x] Long-lived token exchange (short → long-lived) ✅ services/whatsapp/main.py
- [x] Store token in `channel_connections` (WhatsApp + Facebook + Instagram) ✅
- [x] Register webhook: `POST /{waba_id}/subscribed_apps` ✅ auto in embedded-signup flow
- [x] Webhook endpoint: `/webhook/whatsapp` + `/webhook/social` ✅ gateway routes configured

#### WhatsApp Specific
- [x] Message template creation + submission flow ✅ services/whatsapp/main.py CRUD endpoints
- [x] Template approval status tracking ✅ stored in whatsapp_templates table
- [x] 24-hour messaging window enforcement ✅ services/whatsapp/main.py — send_message()
- [ ] Per-message billing → wallet deduction (utility ₹0.25, marketing ₹1.20) ⚠️ NEEDS gateway middleware
- [x] Media messages: images, docs, audio, video, location, contacts ✅
- [x] Interactive messages: buttons, lists ✅
- [x] Read receipts + delivery status webhooks ✅ handle_message_status()
- [x] Business profile setup (logo, description, address, website) ✅ phone-numbers/{id}/profile

#### Instagram + Facebook
- [x] Instagram Business Account linking via Embedded Signup ✅ auto-linked in embedded-signup flow
- [x] Story mention/reply handling ✅ services/social/main.py — INSTAGRAM_MESSAGE_TYPES
- [x] Facebook Page linking + Messenger configuration ✅ auto-linked in embedded-signup flow
- [ ] Persistent menu + Get Started button + Ice breakers ⚠️ NICE-TO-HAVE post-launch

### 4.2 Voice — WhatsApp Business Calling (Primary) + Traditional Numbers (Premium Add-On)

> **Strategy**: Use WhatsApp Business Calling as the default voice channel for all tenants (zero extra setup — rides on their existing WhatsApp Business connection). Traditional phone numbers (Exotel/SIP) offered as a premium add-on for tenants who specifically request dedicated landline/mobile numbers.

#### 4.2.1 WhatsApp Business Calling (Default for ALL tenants)

**How it works**: Tenant's WhatsApp Business number doubles as their voice channel. No extra numbers, no Exotel, no SIP trunks needed for MVP.

**Call Flow (Outbound — Sales):**
1. Lead enters system (website form, WhatsApp inquiry, Shopify order, etc.)
2. Priya AI sends a WhatsApp template message to the customer:
   *"Hi {name}, thanks for your interest in {product}. We'd love to give you a quick walkthrough. Reply YES to connect with our AI assistant."*
3. Customer replies → 24-hour conversation window opens
4. Priya AI initiates WhatsApp voice call via Meta Cloud API
5. Audio streams to LiveKit → Deepgram STT → Priya AI → ElevenLabs TTS → back to customer
6. Call completes → recording saved → wallet charged

**Call Flow (Inbound — Support):**
1. Customer sends WhatsApp message or calls the tenant's WhatsApp Business number
2. Meta webhook delivers to Partython → routes to tenant's Priya AI
3. If voice call: audio streams to LiveKit → AI conversation
4. If message: handled by existing WhatsApp text flow

**Implementation Checklist:**
- [x] **Meta Cloud API voice call support**: ✅ services/whatsapp/main.py — /api/v1/calling/initiate
  - Requires: Business Verification ✅ DONE
  - Requires: WhatsApp Business API access with voice call permissions
- [x] **Consent-first template endpoint**: ✅ /api/v1/calling/send-consent
  - Auto-grant when customer replies ✅ check_consent_grant() in webhook handler
  - Template must be approved by Meta ⚠️ MANUAL — submit via dashboard
- [x] **Initiate call API**: ✅ `POST /api/v1/calling/initiate` → Meta `POST /{phone_number_id}/calls`
  - Enforces 24h window + consent check before allowing call
- [x] **Call status webhooks**: ✅ handle_call_status() — tracks ringing/answered/completed/missed
- [x] **Call history endpoint**: ✅ `GET /api/v1/calling/history`
- [x] **DB migration**: ✅ migration 014 — whatsapp_calls + whatsapp_call_consents tables with RLS
- [ ] **Audio streaming to LiveKit**: Meta Cloud API → WebSocket audio stream → LiveKit room ⚠️ PHASE 2
  - Each call creates a LiveKit room tagged with `tenant_id` + `customer_phone`
  - Priya AI agent joins the room, processes audio in real time
- [ ] **Call recording**: capture audio from LiveKit room → store in tenant's S3 prefix ⚠️ PHASE 2
  - Announce recording at call start: "This call may be recorded for quality purposes"
  - DPDPA compliance: explicit consent before recording
- [ ] **Per-call billing**: on call end → calculate duration → deduct from tenant wallet
  - Meta charges: per-minute rate for WhatsApp voice calls (check current Meta pricing)
  - Partython charges: Meta cost + margin (update pricing_rules table)
- [ ] **Call status tracking**: ringing, connected, completed, missed, failed → update conversation UI
- [ ] **Human handoff during call**: if Priya AI detects escalation trigger → transfer to live agent
  - Agent receives notification in dashboard → joins LiveKit room → takes over call
- [ ] **Fallback**: if WhatsApp Calling API unavailable or customer prefers text → continue via WhatsApp messages

#### 4.2.2 Traditional Phone Numbers — Premium Add-On (Exotel)

> **For tenants who request dedicated landline/mobile numbers.** This is NOT part of MVP — offered as a paid add-on when tenants explicitly ask for it. Contact Partython team to set up.

**Why some tenants may want this:**
- They want a landline number for professional identity (e.g., +91-44-XXXXXXXX)
- They need to make cold outbound calls (not possible on WhatsApp)
- Their customers don't use WhatsApp
- They want separate sales and support numbers

**Exotel Setup (Chennai — Voice Stream only, no SIP available):**
- [ ] **Per tenant**: 2 Exophones required (Exotel limitation — 1 app per Exophone)
  - Exophone 1: **Voice Bot app** → handles inbound calls (customer calls in)
  - Exophone 2: **Stream Applet app** → handles outbound calls (Priya AI calls out)
  - Cost: ~₹1,000-2,000/month per tenant (2 numbers)
- [ ] **Exotel Bridge service** (already built): receives Exotel WebSocket voice stream → identifies tenant by Exophone → routes to tenant's AI agent room in LiveKit
- [ ] **Exophone Pool database**:
  ```sql
  CREATE TABLE exophone_pool (
    id UUID PRIMARY KEY,
    exophone VARCHAR(15) NOT NULL UNIQUE,         -- +914412345678
    exotel_number_sid VARCHAR(50),                 -- Exotel's internal ID
    tenant_id UUID REFERENCES tenants(id),        -- NULL = available
    direction VARCHAR(10) NOT NULL,                -- 'inbound' or 'outbound'
    app_type VARCHAR(20) NOT NULL,                 -- 'voice_bot' or 'stream_applet'
    region VARCHAR(50),                            -- mumbai, delhi, chennai, etc.
    number_type VARCHAR(20),                       -- landline, mobile, tollfree
    status VARCHAR(20) DEFAULT 'available',        -- available, assigned, suspended
    assigned_at TIMESTAMP,
    monthly_cost_paisa INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
  );
  ```
- [ ] **Assignment**: when premium tenant requests numbers → assign 2 Exophones (1 inbound + 1 outbound) → configure apps in Exotel dashboard
- [ ] **TRAI compliance for outbound**: DLT Telemarketer registration, 140-series for sales calls, DND/NCPR scrubbing, 10 AM–7 PM calling window, AI disclosure at call start
- [ ] **Per-minute billing**: Exotel webhook on call end → calculate duration → deduct from wallet
- [ ] **Call recording**: Exotel stores recordings → fetch via API → copy to tenant's S3 prefix

#### 4.2.3 Future — SIP Trunking (Phase 3, Scale)

> **When Exotel SIP becomes available in Chennai, or via Tata Tele SIP for direct LiveKit integration.**

- [ ] **Tata Tele SIP Trunking**: direct SIP → LiveKit SIP connector (`livekit-sip`), no bridge needed
  - Partython-owned numbers, shared channel pool
  - Best for: high-volume tenants, overflow capacity, cost optimization
  - Limitation: numbers belong to Partython, not per-tenant
- [ ] **Exotel vSIP**: when available in Chennai, replaces Voice Stream model
  - Per-tenant Exophone, bidirectional on single number (no 2-number limitation)
  - Direct SIP → LiveKit, eliminates Exotel Bridge service
- [ ] **LiveKit SIP connector setup**: configure `livekit-sip` with trunk credentials, inbound/outbound routing rules

### 4.3 SMS — DLT Compliant (See Section 2 for DLT Registration)

#### Platform SMS (OTPs, Notifications)
- [ ] Use MSG91 with your own DLT Entity ID + registered templates
- [ ] No per-tenant DLT setup needed for platform's own messages

#### Tenant SMS (Their Customers)
- [ ] **Phase 1 — MVP (No tenant DLT needed)**:
  - Use MSG91 OTP route for OTP-style messages (₹0.20/SMS)
  - Use Quick SMS / international route for custom messages (₹5/SMS, random sender)
  - Clear disclosure: "Messages sent from numeric sender ID until DLT setup"
- [ ] **Phase 2 — Managed DLT**:
  - Register Partython.ai as **Telemarketer** on DLT portals (in addition to Enterprise)
  - Build DLT onboarding flow in dashboard:
    1. Tenant uploads: company PAN, GST, authorization letter
    2. Your team submits to DLT portal on their behalf
    3. Once approved: tenant gets branded Sender ID + template approval
    4. Switch their messages to DLT route (₹0.15-0.25/SMS, branded)
  - Charge tenant ₹2,000-5,000 one-time setup fee for managed DLT registration
- [ ] **Delivery reports**: MSG91 webhook → update message status → dashboard
- [ ] **Per-SMS billing** → wallet deduction

### 4.4 Telegram
- [ ] Bot token validation via `GET /bot{token}/getMe`
- [ ] Auto-register webhook: `POST /bot{token}/setWebhook?url=https://api.partython.in/webhooks/telegram/{tenant_id}`
- [ ] Handle message types: text, photo, document, voice, video, location, contact
- [ ] Inline keyboard support for bot interactions
- [ ] No cost per message (Telegram is free) — only charge for AI bot response

### 4.5 Email (SMTP/IMAP)
- [ ] SMTP credential validation (TCP + TLS handshake test)
- [ ] Support: Gmail App Password, Outlook/365, Amazon SES, custom SMTP
- [ ] Inbound: IMAP polling (every 30s) or provider webhook (SES SNS, SendGrid Inbound Parse)
- [ ] Email threading: `In-Reply-To`, `References`, `Message-ID` headers
- [ ] Attachment handling: S3 upload, virus scan (ClamAV), size limit 25MB
- [ ] HTML email rendering in conversation view
- [ ] No per-message cost (uses tenant's own SMTP) — only charge for AI bot response

### 4.6 Shopify
- [ ] Shopify OAuth flow (already implemented ✅)
- [ ] HMAC-SHA256 verification on callbacks (already implemented ✅)
- [ ] Order status webhook → trigger WhatsApp notifications
- [ ] Customer data sync → CRM
- [ ] Abandoned cart recovery via WhatsApp/Email

### 4.7 WebChat
- [ ] Embeddable widget JS: `<script src="https://cdn.partython.in/widget.js" data-tenant="xxx">`
- [ ] Widget customization: colors, position (bottom-right/left), avatar, welcome message
- [ ] Auto-connect on tenant activation (no external auth needed)
- [ ] WebSocket-based real-time chat
- [ ] Visitor identification: cookie-based session, optional email collection
- [ ] No per-message cost — only charge for AI bot response

### 4.8 RCS (Phase 2 — Future)
- [ ] Google RCS Business Messaging agent registration
- [ ] API integration via Google's RBM API
- [ ] Fallback to SMS if RCS not supported on device
- [ ] Rich card + carousel support

---

## 5. AI / BOT ENGINE

- [ ] Per-tenant AI model selection (GPT-4o, GPT-4o-mini, Claude Sonnet, Gemini)
- [ ] Knowledge base ingestion: PDF, DOCX, website scraping, FAQ import
- [ ] Vector store per tenant (Pinecone/Qdrant/pgvector)
- [ ] Conversation context window management (last N messages + RAG retrieval)
- [ ] System prompt customization per tenant (brand voice, rules, escalation triggers)
- [ ] Human handoff detection: frustration signals, explicit "talk to human", complex queries
- [ ] Live agent routing: assign to available agent, notify via dashboard + push notification
- [ ] Per-response token tracking → wallet deduction (input + output tokens)
- [ ] Rate limiting: max AI calls per minute per tenant (prevent abuse)
- [ ] Content safety filter on AI responses (block harmful/inappropriate content)
- [ ] Multi-language support: detect language, respond in same language
- [ ] Canned responses / quick replies for common queries

---

## 6. NOTIFICATIONS & COMMUNICATIONS (Email + SMS + WhatsApp + Push)

> Every SaaS needs a reliable notification layer. Users expect instant confirmations, timely reminders,
> and clear alerts. This is NOT optional — it directly impacts revenue (dunning emails recover 72% of
> failed payments) and retention (74% of users expect welcome emails immediately).

### 6.1 Email Infrastructure Setup

#### Provider Selection
- [ ] **Amazon SES** (recommended for cost — $0.10 per 1,000 emails, free tier: 62,000/month on EC2)
  - Alternative: SendGrid (better deliverability dashboard, $19.95/mo for 50k emails)
  - Alternative: Postmark ($1.25 per 1,000 emails, best deliverability, SaaS-focused)
- [ ] **CRITICAL: Separate domains for transactional vs marketing**
  - Transactional: `mail.partython.in` (OTPs, receipts, alerts — high reputation)
  - Marketing: `updates.partython.in` (newsletters, announcements — isolated reputation)
  - If marketing gets spam complaints, it won't affect OTP delivery

#### Domain Authentication (Mandatory for Deliverability)
- [ ] **SPF record** on `partython.in`:
  ```
  v=spf1 include:amazonses.com include:_spf.google.com ~all
  ```
- [ ] **DKIM** — add CNAME records provided by SES (3 records for key rotation)
- [ ] **DMARC** policy:
  ```
  v=DMARC1; p=quarantine; sp=quarantine; rua=mailto:dmarc-reports@partython.in; pct=100
  ```
- [ ] **Custom MAIL FROM** domain: `bounce.partython.in` (instead of amazonses.com)
- [ ] **Verify domain** in SES console (DNS TXT record)
- [ ] **Request SES production access** (new accounts are in sandbox mode — can only send to verified emails)
  - Submit request with: use case, expected volume, bounce handling process
  - Approval: 24-48 hours

#### Email Template Engine
- [ ] Build or use template engine: **MJML** (responsive email framework) or **React Email**
- [ ] All emails must be:
  - Mobile responsive (60%+ opens are mobile)
  - Branded: Partython.ai logo, consistent colors, footer with address
  - Plain text fallback (for email clients that don't render HTML)
  - Unsubscribe link (CAN-SPAM + GDPR requirement, except purely transactional like OTPs)
- [ ] Store templates in database or S3 (not hardcoded) — admin can update without deploy
- [ ] Template variables: `{{tenant_name}}`, `{{amount}}`, `{{date}}`, `{{channel}}`, etc.

### 6.2 Notification Microservice (NEW — Must Build)

- [ ] Create `notification_service` microservice (Python FastAPI, port 9015)
- [ ] **Database tables**:
  ```sql
  notification_templates (
    id UUID PRIMARY KEY,
    name VARCHAR(100),          -- 'welcome_email', 'low_balance_sms', etc.
    channel VARCHAR(20),        -- 'email', 'sms', 'whatsapp', 'push'
    subject VARCHAR(500),       -- email subject (null for SMS/WhatsApp)
    body_html TEXT,             -- HTML body for email
    body_text TEXT,             -- plain text / SMS body
    dlt_template_id VARCHAR(30),-- DLT template ID (for SMS in India)
    msg91_template_id VARCHAR(30),
    whatsapp_template_name VARCHAR(100),
    variables JSONB,            -- list of variable names used
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP
  );

  notification_preferences (
    tenant_id UUID,
    user_id UUID,
    channel VARCHAR(20),
    category VARCHAR(50),       -- 'billing', 'channel_alerts', 'marketing', 'security'
    enabled BOOLEAN DEFAULT true,
    PRIMARY KEY (tenant_id, user_id, channel, category)
  );

  notification_log (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    user_id UUID,
    template_name VARCHAR(100),
    channel VARCHAR(20),        -- email/sms/whatsapp/push
    recipient VARCHAR(255),     -- email or phone
    status VARCHAR(20),         -- queued/sent/delivered/failed/bounced
    provider_message_id VARCHAR(100),
    metadata JSONB,
    sent_at TIMESTAMP,
    delivered_at TIMESTAMP,
    failed_reason TEXT
  );

  scheduled_notifications (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    template_name VARCHAR(100),
    channel VARCHAR(20),
    recipient VARCHAR(255),
    scheduled_for TIMESTAMP,
    status VARCHAR(20),         -- pending/sent/cancelled
    created_at TIMESTAMP
  );
  ```
- [ ] **Queue-based architecture**: notifications go into Redis queue → workers pick up → send via provider
  - Prevents API blocking on slow email sends
  - Retry failed sends: 3 attempts with exponential backoff (1min, 5min, 30min)
- [ ] **Multi-channel delivery**: same notification can go to email + SMS + WhatsApp + push
- [ ] **User preferences**: users can opt out of non-critical categories (marketing, tips) but NOT security/billing
- [ ] **Rate limiting**: max 10 emails/hour per user (prevent accidental notification storms)
- [ ] **Bounce/complaint handling**: SES SNS webhook → mark email as bounced → stop sending to that address

### 6.3 Complete Notification Catalog

#### A. ONBOARDING SEQUENCE (Triggered by signup)

| # | Timing | Channel | Notification | Purpose |
|---|--------|---------|-------------|---------|
| 1 | Immediate | Email | **Welcome Email** | Confirm signup, introduce platform, CTA: "Complete your setup" |
| 2 | Immediate | SMS | **Welcome SMS** | "Welcome to Partython.ai! Complete setup: {link}" |
| 3 | +1 hour | Email | **Phone Verification Reminder** | If phone not verified: "Verify your number to unlock channels" |
| 4 | +1 day | Email | **Connect First Channel** | Guide to connect WhatsApp/first channel, video tutorial link |
| 5 | +3 days | Email | **Top Up Wallet** | If wallet = ₹0: "Add credits to start messaging your customers" |
| 6 | +5 days | Email | **Tips & Best Practices** | AI bot setup tips, template message suggestions |
| 7 | +7 days | Email | **Check-in / Feedback** | "How's your experience? Need help?" — link to support |
| 8 | +14 days | Email | **Feature Highlight** | Showcase a feature they haven't used (analytics, team members) |

- [ ] Implement all 8 onboarding emails with HTML templates
- [ ] Track which emails user has received (don't resend)
- [ ] Skip emails that don't apply (e.g., skip #3 if phone already verified)
- [ ] Stop sequence if user unsubscribes from onboarding category

#### B. BILLING & WALLET NOTIFICATIONS (Critical — Directly Impacts Revenue)

| Trigger | Channel | Notification | DLT Template Needed? |
|---------|---------|-------------|---------------------|
| Top-up successful | Email + SMS | "Payment of ₹{amount} received. Wallet balance: ₹{balance}" | Yes — Service category |
| Top-up failed | Email + SMS | "Payment of ₹{amount} failed. Retry: {link}" | Yes — Service category |
| Balance < ₹100 | Email + SMS + WhatsApp | "Low balance alert: ₹{balance} remaining. Top up: {link}" | Yes — Service category |
| Balance < ₹25 | Email + SMS + WhatsApp + Push | "URGENT: ₹{balance} left. Channels will pause at ₹0. Top up now: {link}" | Yes — Service category |
| Balance = ₹0 (channels paused) | Email + SMS + WhatsApp | "Channels paused — wallet empty. Top up to resume: {link}" | Yes — Service category |
| Auto top-up triggered | Email | "Auto top-up of ₹{amount} processed. Balance: ₹{balance}" | Yes |
| Auto top-up failed | Email + SMS | "Auto top-up failed. Update payment method: {link}" | Yes |
| Monthly invoice ready | Email | "Your invoice for {month} is ready. Amount: ₹{amount}. View: {link}" | No (email only) |
| Subscription renewal (3 days before) | Email | "Your {plan} plan renews on {date} for ₹{amount}" | No |
| Subscription renewal failed | Email + SMS | "Plan renewal failed. Update payment: {link}. Service continues for 3 days." | Yes |

- [ ] Implement complete dunning sequence (graduated urgency):
  - Day 0: Friendly reminder ("Payment didn't go through, update your card")
  - Day 1: Second attempt + email ("We'll retry tomorrow")
  - Day 3: Urgent ("Service will be limited in 4 days")
  - Day 7: Final warning ("Last chance — account will be suspended tomorrow")
  - Day 8: Account suspended, final email with reactivation link
- [ ] Stop dunning sequence immediately when payment succeeds
- [ ] Track dunning state per tenant (which step they're on)

#### C. CHANNEL ALERTS

| Trigger | Channel | Notification |
|---------|---------|-------------|
| Channel connected successfully | Email + Push | "WhatsApp Business connected! Start messaging: {link}" |
| Channel disconnected (by user) | Email | "You've disconnected {channel}. Reconnect anytime: {link}" |
| Channel error (token expired, auth failed) | Email + SMS + Push | "Action needed: {channel} connection lost. Reconnect: {link}" |
| Meta token expiring (7 days before) | Email | "Your Meta authorization expires in 7 days. Re-authorize: {link}" |
| Exophone assigned | Email + SMS | "Your business number is {number}. Share with customers!" |
| DLT registration approved | Email | "SMS sender ID {header} approved! Start sending branded SMS." |
| Webhook delivery failed (3 consecutive) | Email | "Webhook to {url} failing. Check your endpoint." |
| High message volume alert | Email | "You sent {count} messages today — {percent}% of daily limit." |

#### D. CONVERSATION & AGENT ALERTS

| Trigger | Channel | Notification |
|---------|---------|-------------|
| New conversation (no agent) | Push + Email (if enabled) | "New {channel} message from {customer}. View: {link}" |
| Human handoff requested | Push + SMS | "Customer requesting human agent on {channel}. Respond: {link}" |
| Unresponded conversation (>30 min) | Push + Email | "Unresponded conversation with {customer} for {duration}." |
| CSAT score below threshold | Email (to admin) | "Customer satisfaction dropped to {score}%. Review: {link}" |
| Daily digest | Email (morning) | "Yesterday: {count} conversations, {resolved} resolved, avg response: {time}" |

#### E. SECURITY ALERTS (Cannot Be Disabled)

| Trigger | Channel | Notification |
|---------|---------|-------------|
| New login from unknown device | Email + SMS | "New login to your account from {device} in {location}. Not you? {link}" |
| Password/email changed | Email | "Your account email was changed. If this wasn't you, contact support." |
| API key created | Email | "New API key created: {key_name}. If this wasn't you, revoke: {link}" |
| Multiple failed login attempts | Email + SMS | "Multiple failed login attempts detected. Account temporarily locked." |
| Admin role granted | Email | "{user} has been granted admin access to your workspace." |

#### F. SYSTEM NOTIFICATIONS

| Trigger | Channel | Notification |
|---------|---------|-------------|
| Scheduled maintenance | Email + Dashboard banner | "Scheduled maintenance on {date} from {time}. Expected downtime: {duration}" |
| Incident / outage | Email + SMS + Dashboard | "Service disruption detected. We're working on it. Status: {link}" |
| Incident resolved | Email | "The issue affecting {service} has been resolved. Apologies for the inconvenience." |
| New feature announcement | Email (marketing) | "New: {feature}! Here's how it helps you: {link}" |
| Platform tips | Email (weekly/optional) | "Tip of the week: {tip}" |

### 6.4 DLT SMS Templates to Register (All Required for India SMS Delivery)

> Register these on your DLT portal (Jio/Airtel). Template variables shown as {#var#}.
> Category determines delivery rules: Transactional = 24/7 + DND; Service = 24/7 + DND;
> Promotional = 10AM-9PM, non-DND only.

**Category: Service (Implicit)**
```
Template 1 (OTP):
"Your Partython.ai verification code is {#var#}. Valid for 10 minutes. Do not share this code with anyone."

Template 2 (Welcome):
"Welcome to Partython.ai! Complete your setup at {#var#}. For help, contact support@partython.in"

Template 3 (Payment Success):
"Payment of Rs.{#var#} received successfully. Your Partython.ai wallet balance is Rs.{#var#}. Ref: {#var#}"

Template 4 (Payment Failed):
"Your payment of Rs.{#var#} on Partython.ai failed. Please retry at {#var#} or contact support."

Template 5 (Low Balance Warning):
"Alert: Your Partython.ai wallet balance is Rs.{#var#}. Top up now to avoid service interruption: {#var#}"

Template 6 (Critical Balance):
"URGENT: Your Partython.ai balance is Rs.{#var#}. Channels will pause at Rs.0. Top up immediately: {#var#}"

Template 7 (Channels Paused):
"Your Partython.ai channels are paused due to zero balance. Top up to resume: {#var#}"

Template 8 (Channel Error):
"Action required: Your {#var#} channel on Partython.ai needs reconnection. Fix now: {#var#}"

Template 9 (New Login Alert):
"New login to your Partython.ai account from {#var#}. If this wasn't you, secure your account: {#var#}"

Template 10 (Human Handoff):
"A customer on {#var#} is requesting a human agent. Respond now at {#var#}"

Template 11 (Number Assigned):
"Your Partython.ai business number is {#var#}. Share this with your customers for calls and SMS."

Template 12 (Auto Topup):
"Auto top-up of Rs.{#var#} processed on Partython.ai. New balance: Rs.{#var#}. Manage: {#var#}"

Template 13 (Subscription Renewal Failed):
"Your Partython.ai {#var#} plan renewal failed. Update payment method at {#var#} within 3 days."

Template 14 (Daily Digest):
"Partython.ai daily summary: {#var#} conversations, {#var#} resolved. Avg response: {#var#}. Details: {#var#}"
```

- [ ] Register ALL 14 templates on DLT portal
- [ ] Wait for approval (24-48 hours per template on Jio)
- [ ] Store approved Template IDs in `notification_templates` table
- [ ] Map each template to MSG91 API format

### 6.5 WhatsApp Notification Templates (Meta Approval Required)

> WhatsApp Business templates must be submitted via Meta Business Manager and approved.
> Use the "UTILITY" category for transactional, "MARKETING" for promotional.

- [ ] **Utility templates** (₹0.13/msg India, charged from wallet):
  - `welcome_message` — "Welcome to {{1}}! Your account is ready. Get started: {{2}}"
  - `payment_receipt` — "Payment of ₹{{1}} received. Balance: ₹{{2}}. Ref: {{3}}"
  - `low_balance_alert` — "Your {{1}} balance is ₹{{2}}. Top up to avoid service interruption: {{3}}"
  - `channel_error` — "Your {{1}} channel needs attention. Please reconnect: {{2}}"
  - `otp_message` — "{{1}} is your verification code for {{2}}. Valid for 10 minutes."
- [ ] **Marketing templates** (₹0.88/msg India — use sparingly):
  - `feature_announcement` — "New on {{1}}: {{2}}! See what's new: {{3}}"
  - `monthly_digest` — "Your {{1}} monthly report: {{2}} messages, {{3}} resolved. Full report: {{4}}"
- [ ] Submit templates via Meta Business Manager → WhatsApp Manager → Message Templates
- [ ] Approval timeline: 24-48 hours (can be instant for simple utility templates)
- [ ] Handle rejection: modify template and resubmit

### 6.6 Push Notifications (Browser + Mobile)

- [ ] **Browser push**: Firebase Cloud Messaging (FCM) — free
  - Service worker registration in Next.js dashboard
  - Permission prompt: show only after user takes first meaningful action (not on page load)
  - Store FCM token per user session in database
- [ ] **Mobile push** (Phase 2 — when mobile app launches):
  - FCM for Android
  - APNs for iOS (via Firebase)
- [ ] Push notification categories:
  - Urgent: new human handoff request, security alerts (always deliver)
  - Standard: new conversations, channel alerts (respect quiet hours)
  - Low: tips, announcements (batch deliver)
- [ ] **Quiet hours**: don't send non-urgent push between 10PM-8AM user's local time
- [ ] **Notification center** in dashboard: chronological list of all notifications with read/unread state

### 6.7 Notification Preferences Dashboard

- [ ] **Settings → Notifications page** in dashboard
- [ ] Per-category toggles:
  - Billing alerts: Email ✅ SMS ✅ WhatsApp ☐ Push ✅ — (email/SMS mandatory, can't disable)
  - Channel alerts: Email ✅ SMS ☐ WhatsApp ☐ Push ✅
  - Conversation alerts: Email ☐ SMS ☐ WhatsApp ☐ Push ✅
  - Security alerts: Email ✅ SMS ✅ — (ALWAYS ON, cannot disable)
  - Marketing/Tips: Email ☐ SMS ☐ WhatsApp ☐ Push ☐ — (all optional)
- [ ] **Team notification routing**: which team members get which alerts
  - Admin: all billing + security
  - Agents: conversation alerts only
  - Custom roles: configurable
- [ ] **Quiet hours** setting: suppress non-urgent notifications during specified hours
- [ ] **Daily digest option**: bundle non-urgent notifications into one morning email

---

## 7. SECURITY (PERMANENT DIRECTIVE: SECURITY FIRST)

### Application Security
- [ ] All credentials encrypted at rest: AES-256-GCM with PBKDF2 key derivation (100k iterations)
- [ ] PostgreSQL Row Level Security (RLS) on ALL tenant tables — enforced at DB level, not just app
- [ ] CSRF tokens on all state-changing endpoints (double-submit cookie pattern)
- [ ] Input validation: Pydantic models (Python), Zod schemas (TypeScript)
- [x] SQL injection: parameterized queries only (asyncpg + $1 placeholders) ✅
- [ ] XSS: Content Security Policy headers, React's built-in escaping
- [ ] CORS: strict origin whitelist (partython.in, localhost for dev)
- [ ] Rate limiting: Redis-backed, per-IP and per-tenant
- [ ] API key rotation: service-to-service JWT with 24hr expiry, auto-rotate
- [ ] Secrets: migrate from .env to AWS Secrets Manager (prod) / HashiCorp Vault (self-hosted)
- [x] Webhook signature verification: HMAC-SHA256 on all inbound webhooks (Meta, Exotel, Razorpay ✅, Shopify ✅)
- [ ] File upload scanning: ClamAV for virus/malware in attachments

### Infrastructure Security
- [ ] HTTPS everywhere: TLS 1.3, HSTS header (`max-age=31536000; includeSubDomains; preload`)
- [ ] AWS VPC: private subnets for databases, Redis, internal services
- [ ] Security groups: only ALB/gateway on port 443 exposed to internet
- [ ] Database: encryption at rest (RDS/Neon default), encryption in transit (SSL required)
- [ ] S3: bucket policy deny public access, server-side encryption (AES-256)
- [ ] Docker: run as non-root user, read-only filesystem, no privileged containers
- [ ] Docker image scanning: Trivy in CI pipeline, block deploy on HIGH/CRITICAL CVEs
- [ ] Dependency audit: `npm audit` + `pip-audit` + `safety check` in CI, weekly automated PRs
- [ ] WAF: AWS WAF or Cloudflare WAF on gateway (block common attacks, SQLi, XSS patterns)

### Compliance & Legal
- [ ] **Privacy Policy** page (covers all data collection, storage, sharing practices)
- [ ] **Terms of Service** page (liability, acceptable use, data ownership)
- [ ] **Data Processing Agreement (DPA)** template for enterprise tenants
- [ ] **Cookie Policy** page (if using cookies on marketing site)
- [ ] **DPDPA 2023 compliance** (India's Digital Personal Data Protection Act):
  - Consent collection before data processing
  - Data principal rights: access, correction, erasure
  - Data fiduciary obligations
  - Reasonable security safeguards
- [ ] **GDPR readiness** (for EU customers):
  - Standard Contractual Clauses (SCCs) for India → EU data transfers
  - Data export API (user requests all their data)
  - Data deletion API ("right to be forgotten")
  - Consent management (explicit opt-in for marketing)
  - Appoint EU representative if >250 employees or large-scale processing
  - Consider EU data residency option (AWS eu-west-1) for EU tenants
- [ ] **PCI DSS**: never store card data — Razorpay/Stripe handle PCI compliance
- [ ] **IT Act 2000 (India)**: reasonable security practices, data localization for sensitive data
- [ ] **TRAI compliance**: DLT registration (Section 2), no unsolicited commercial communication

### Monitoring & Incident Response
- [ ] Centralized logging: AWS CloudWatch or ELK stack (7-day hot, 90-day cold retention)
- [ ] Error tracking: Sentry (Python + Next.js SDKs)
- [ ] APM: Datadog or New Relic (request tracing, latency monitoring)
- [ ] Uptime monitoring: UptimeRobot or Pingdom (check every 1 min)
- [ ] Alerting: PagerDuty or Slack webhook for P0/P1 incidents
- [ ] Security audit logs: who accessed what tenant data, when, from where
- [ ] Automated backup verification: daily restore test to staging
- [ ] Incident response runbook: documented procedures for common failures
- [ ] War room process for P0 incidents

---

## 8. DATABASE & INFRASTRUCTURE

### Database
- [ ] Connection pooling: PgBouncer or Neon's built-in pooler (100 connections max)
- [ ] Read replica for analytics queries (separate from transactional)
- [ ] Automated daily backups: 30-day retention, cross-region replication
- [ ] Point-in-time recovery (PITR) enabled
- [x] Migration tool: Alembic with up/down migrations ✅ (012_wallet_passwordless migration created)
- [ ] Indexes: `tenant_id` (all tables), `(tenant_id, channel)`, `(conversation_id, tenant_id)`, `(created_at)` for time-range queries
- [ ] Partition `messages` table by `tenant_id` (or by month for very large tenants)
- [ ] Vacuum/analyze scheduled (autovacuum tuned for write-heavy workload)
- [ ] Query performance monitoring: `pg_stat_statements`, slow query log (>500ms)

### Redis
- [ ] Redis cluster (not single instance) for production
- [ ] Persistence: RDB + AOF for rate limit state
- [ ] Separate Redis databases: 0=cache, 1=rate-limits, 2=sessions, 3=pub-sub
- [ ] Memory limits + eviction policy: `allkeys-lru`
- [ ] Redis Sentinel or ElastiCache for high availability

### Docker / Deployment
- [ ] Multi-stage Docker builds: builder → production (50-70% smaller images)
- [x] Health check endpoints on ALL 45 services ✅ `GET /health` via Dockerfile.service HEALTHCHECK
- [ ] Graceful shutdown: handle SIGTERM, drain connections, finish in-flight requests
- [ ] Resource limits per container: CPU (0.5-2 cores), memory (256MB-2GB)
- [ ] Liveness + readiness probes (Kubernetes) or health checks (ECS)
- [ ] Auto-scaling: 2-10 replicas based on CPU >70% or request latency >500ms
- [ ] Blue-green deployment (zero downtime) or rolling update (max 25% unavailable)
- [ ] Rollback: one-command rollback to previous image tag

### CI/CD
- [ ] GitHub Actions: lint → test → security scan → build → push → deploy
- [ ] Branch strategy: `main` (production), `staging`, feature branches
- [ ] Staging environment: mirrors production (same infra, smaller scale)
- [ ] Integration tests gate: must pass before merge to staging
- [ ] Docker images tagged with git SHA + `latest` for branch
- [ ] Environment configs: `.env.dev`, `.env.staging`, `.env.prod` (never committed — Secrets Manager)
- [ ] Deploy approval: staging auto-deploy, production requires manual approval

---

## 9. DASHBOARD / FRONTEND

### Core Pages
- [ ] **Home**: overview stats, active conversations, channel health, wallet balance
- [ ] **Channels**: connect/disconnect/test (built ✅), manage settings, view stats
- [ ] **Conversations**: real-time inbox, agent assignment, message history, search
- [ ] **Contacts**: CRM-lite, customer profiles, channel history, tags, notes
- [ ] **Analytics**: message volume, response times, CSAT scores, channel breakdown
- [ ] **Bot Builder**: system prompt editor, knowledge base upload, test chat
- [ ] **Team**: invite members, roles (admin/agent/viewer), activity log
- [x] **Wallet** ✅ `dashboard/src/app/(dashboard)/wallet/page.tsx` — balance, Razorpay topup, transaction history
- [ ] **Settings**: company profile, API keys, webhooks, notification preferences, billing
- [ ] **Onboarding wizard**: first-time setup guide (verify phone → connect first channel → send test message)
- [x] **Login** ✅ `dashboard/src/app/(auth)/login/page.tsx` — Google Sign-In + Email OTP multi-step flow

### UX
- [ ] Mobile responsive (dashboard usable on phone for quick replies)
- [ ] Dark mode (partially done ✅)
- [ ] Real-time: WebSocket for new messages, typing indicators, agent presence
- [ ] Push notifications: browser + mobile (FCM/APNs)
- [ ] Toast notifications for async operations (already done ✅)
- [ ] Loading skeletons (already done ✅)
- [ ] Error boundaries: graceful error pages per route
- [ ] i18n: English (default), Hindi, Tamil, Telugu (Phase 2)

---

## 10. TESTING

- [ ] **Unit tests**: auth, wallet (balance operations, race conditions), channel_router, AI engine
- [ ] **Integration tests**: signup → OTP verify → connect channel → send message → billing
- [ ] **OAuth flow tests**: Meta Embedded Signup, Shopify OAuth, Google OAuth (mock providers)
- [ ] **Load testing**: k6 or Locust — 100 concurrent tenants, 1000 msgs/min, 50 concurrent calls
- [ ] **Billing accuracy tests**: simulate 10,000 transactions, verify wallet balance matches ledger sum
- [ ] **Security tests**: OWASP ZAP scan, dependency vulnerability scan, penetration test (external)
- [ ] **Chaos engineering**: kill random service, Redis failure, DB failover — verify recovery
- [ ] **E2E browser tests**: Playwright — signup, connect WhatsApp, send/receive, check wallet deduction

---

## 11. DOCUMENTATION

- [ ] API documentation: OpenAPI/Swagger auto-generated from FastAPI routes
- [ ] Channel Setup Guide (created ✅ — `docs/CHANNEL_SETUP.md`)
- [ ] Production Checklist (this document ✅)
- [ ] Deployment Guide: Docker Compose (local) + AWS ECS/EKS (production)
- [ ] Architecture diagram: all 45 services, data flows, external integrations
- [ ] Runbook: top 20 common issues with diagnosis + fix steps
- [ ] Developer onboarding: local setup in <30 minutes
- [ ] Tenant help center: Intercom/Crisp or self-hosted knowledge base
- [ ] API changelog: versioned, published on each release

---

## 12. GLOBAL LAUNCH REQUIREMENTS

### Domain & DNS
- [ ] `partython.in` — main domain (Vercel for Next.js frontend)
- [ ] `api.partython.in` — API gateway (AWS ALB / Cloudflare)
- [ ] `voice.partython.in` — WebSocket for Exotel Stream Applet
- [ ] `cdn.partython.in` — static assets, webchat widget JS
- [ ] `mail.partython.in` — email sending domain (SPF, DKIM, DMARC configured)
- [ ] SSL certificates: ACM (AWS) or Cloudflare automatic SSL

### Email Infrastructure
- [ ] Transactional email: Amazon SES or SendGrid
  - Verify `partython.in` domain
  - Configure SPF: `v=spf1 include:amazonses.com ~all`
  - Configure DKIM: add CNAME records from SES
  - Configure DMARC: `v=DMARC1; p=quarantine; rua=mailto:dmarc@partython.in`
- [ ] Email templates: signup OTP, wallet alerts, channel notifications, monthly invoice
- [ ] Unsubscribe link in all marketing/notification emails (CAN-SPAM + GDPR)

### Payment Processing
- [ ] Razorpay: production API keys, webhook endpoint registered
- [ ] Stripe (international): apply for invite, set up PaymentIntents
- [ ] GST invoicing: auto-generate with GSTIN, SAC code, HSN code
- [ ] Tax compliance: TDS on international payments, GST on domestic

### Third-Party Accounts (Production)
- [ ] Meta Developer App — Live mode, App Review passed
- [ ] Exotel production account — Exophone pool purchased
- [ ] MSG91 production account — DLT entity linked, templates approved
- [ ] Google Cloud — OAuth Client ID for Google Sign-In
- [ ] Apple Developer — Sign In with Apple service configured
- [ ] Razorpay production account — KYC completed
- [ ] Cloudflare — Turnstile site key, DNS management
- [ ] Sentry — error tracking projects created
- [ ] AWS account — VPC, ECS/EKS, RDS, S3, SES, Secrets Manager

### International Considerations
- [ ] WhatsApp pricing varies by country — maintain per-country pricing table
- [ ] International SMS rates vary widely — dynamic pricing lookup
- [ ] Data residency: India region (ap-south-1) primary, EU region (eu-west-1) optional for GDPR
- [ ] Multi-timezone support in dashboard (conversation timestamps, analytics)
- [ ] Multi-currency wallet display
- [ ] Right-to-left (RTL) language support (Arabic, Hebrew) — CSS `dir="rtl"` (Phase 3)

### Pre-Launch
- [ ] All monitoring dashboards configured and tested
- [ ] On-call rotation: 2 engineers minimum, PagerDuty escalation
- [ ] Load test passed: target throughput with <500ms P95 latency
- [ ] Security audit completed: no HIGH/CRITICAL findings open
- [ ] Beta program: 5-10 businesses, 2-week testing period
- [ ] Marketing site: features, pricing, documentation links
- [ ] Support channel: Intercom/Crisp chat widget on marketing site + dashboard

---

## PRIORITY ORDER FOR IMPLEMENTATION

### Phase 0 — Blockers (Must complete before ANY user touches production)
1. ~~Fix signup flow (Google OAuth + Email OTP + Turnstile)~~ ✅ CODE COMPLETE
2. DLT Entity registration on Jio portal (start NOW — takes 3-7 days) ⚠️ MANUAL — requires company docs
3. Register ALL 14 DLT SMS templates (24-48 hours approval each) ⚠️ MANUAL — after DLT entity approved
4. MSG91 account + OTP integration + DLT linking ⚠️ MANUAL — create account at msg91.com
5. Email infrastructure: SES domain verification + SPF/DKIM/DMARC ⚠️ MANUAL — AWS console + DNS
6. ~~Wallet microservice (balance check gates all paid actions)~~ ✅ CODE COMPLETE — `services/wallet/main.py`
7. ~~Razorpay integration for wallet top-ups~~ ✅ CODE COMPLETE — order + verify + webhook
8. Notification microservice with queue-based delivery ✅ CODE COMPLETE — `services/notification/main.py`
9. Welcome email + billing notification templates — TODO: HTML email templates

### Phase 1 — MVP Launch (First 10 beta tenants)
10. Meta Embedded Signup (WhatsApp + Instagram + Facebook)
11. WhatsApp Business Calling integration (consent template + Meta voice call API + LiveKit audio bridge)
12. Tenant SMS via MSG91 OTP route
13. Dashboard: Wallet page, Notifications preferences, Onboarding wizard
14. Complete onboarding email sequence (8 emails)
15. Dunning/payment failure sequence (5 emails over 8 days)
16. Channel alert notifications (connect/disconnect/error)
17. Push notifications (FCM browser push)
18. Basic analytics page

### Phase 2 — Growth (50+ tenants)
19. Stripe for international payments
20. Managed DLT for tenant branded SMS
21. Auto top-up + subscription plans
22. WhatsApp notification templates (Meta-approved utility messages)
23. Daily digest email for agents
24. Advanced analytics + CSAT
25. Telegram + Email channel polish
26. Notification center in dashboard (chronological log)
27. i18n (Hindi, Tamil, Telugu)
28. Traditional phone numbers as premium add-on (Exotel — 2 Exophones per tenant + bridge service)

### Phase 3 — Scale (200+ tenants)
29. Exotel vSIP migration (when available in Chennai — single number per tenant, no bridge needed)
30. Tata Tele SIP Trunking evaluation (direct LiveKit SIP, shared Partython numbers for overflow/cost optimization)
31. Mobile app (React Native) + APNs/FCM push
32. EU data residency option
33. RCS channel
34. White-label option for enterprise
35. Marketing email automation (feature announcements, tips)

---

## Section 7: Store Connections / Marketplace (E-Commerce)

### 7.1 Overview
The marketplace focuses on e-commerce store connectivity for MVP. Three platforms supported:

| Platform | Auth Type | Status | Notes |
|----------|-----------|--------|-------|
| Shopify | OAuth 2.0 | Built | HMAC signature verification, permanent access tokens |
| WooCommerce | WC REST Auth | Built | WooCommerce's own auth endpoint, consumer key/secret |
| Custom Store | API Key/Secret | Built | Generic REST API connector for self-hosted stores |

All other marketplace plugins (CRM, analytics, etc.) are deferred to Phase 2.

### 7.2 Shopify Integration

#### Shopify App Setup (Required Before Production)
1. Go to https://partners.shopify.com → Create a Partner account
2. Create a new App → "Custom App" or "Public App" depending on distribution
3. For our SaaS model, use "Public App" (allows any Shopify store to install)
4. Configure App URLs:
   - App URL: `https://www.partython.in/marketplace`
   - Allowed redirection URL: `https://www.partython.in/api/oauth/shopify/callback`
   - For dev: `http://localhost:3000/api/oauth/shopify/callback`
5. Request scopes: `read_customers,write_customers,read_orders,read_products,read_content`
6. Copy API Key → `SHOPIFY_CLIENT_ID` in `.env`
7. Copy API Secret → `SHOPIFY_CLIENT_SECRET` in `.env`

#### Shopify App Store Listing (Optional — for discoverability)
- Submit to Shopify App Store for public listing
- Requires passing Shopify's App Review process
- Mandatory: Privacy policy, GDPR compliance, data deletion webhook

#### Shopify Webhooks to Register
After OAuth, register these mandatory webhooks:
```
POST https://{shop}.myshopify.com/admin/api/2024-01/webhooks.json
```
- `orders/create` — New order placed
- `orders/updated` — Order status changed (shipped, delivered, cancelled)
- `orders/paid` — Payment confirmed
- `products/update` — Product details changed
- `products/delete` — Product removed
- `customers/create` — New customer registered
- `carts/create` — Cart created (for abandonment tracking)
- `carts/update` — Items added/removed from cart
- `app/uninstalled` — Mandatory: cleanup when store owner removes app

#### Shopify GDPR Compliance (Mandatory for App Store)
Shopify requires 3 GDPR endpoints:
1. `POST /webhook/ecommerce/shopify/customers/data_request` — Return customer data
2. `POST /webhook/ecommerce/shopify/customers/redact` — Delete customer data
3. `POST /webhook/ecommerce/shopify/shop/redact` — Delete all shop data (on app uninstall)

These endpoints must be configured in the Shopify Partner Dashboard under "App setup" → "GDPR mandatory webhooks".

### 7.3 WooCommerce Integration

#### How WooCommerce Auth Works
WooCommerce does NOT use standard OAuth2. It has its own REST API Authentication:
1. We redirect user to `{store_url}/wc-auth/v1/authorize?app_name=Partython.ai&scope=read_write&user_id={state}&callback_url={our_callback}&return_url={success_url}`
2. Store owner clicks "Approve" on their WordPress admin
3. WooCommerce POSTs `consumer_key` + `consumer_secret` to our callback URL
4. These keys are permanent (no expiry) until revoked by store owner

#### WooCommerce Requirements for Store Owners
- WordPress 5.0+ with WooCommerce 7.0+
- REST API must be enabled (Settings → WooCommerce → Advanced → REST API)
- WordPress REST API must not be blocked by security plugins (Wordfence, Sucuri, etc.)
- HTTPS strongly recommended (required for production)
- Permalink structure must NOT be "Plain" (must be "Post name" or custom)

#### WooCommerce Webhooks
After connection, register via WooCommerce REST API:
```
POST {store_url}/wp-json/wc/v3/webhooks
```
- `order.created` — New order
- `order.updated` — Order status change
- `product.updated` — Product change
- `product.deleted` — Product removed
- `customer.created` — New customer

Webhook signature verification: `X-WC-Webhook-Signature` header (HMAC-SHA256 with webhook secret)

### 7.4 Custom Store Integration

#### For Self-Hosted / Headless Commerce
Custom store connection uses API key authentication:
1. Tenant enters Store URL + API Key + API Secret
2. We validate connectivity by calling `GET {store_url}/products` (configurable)
3. Credentials encrypted with Fernet before DB storage
4. Webhooks: store owner configures their platform to POST events to `https://www.partython.in/webhook/ecommerce`

#### Expected API Endpoints (Documented for Store Owners)
We provide documentation so custom store developers can implement these endpoints:
```
GET  /products          — List products (pagination: ?page=1&per_page=50)
GET  /products/{id}     — Single product details
GET  /orders            — List orders (pagination + date filters)
GET  /orders/{id}       — Single order with line items
GET  /customers         — List customers
GET  /customers/{id}    — Single customer
POST /webhooks          — Register webhook callback URL
```

Authentication: `Authorization: Basic base64(api_key:api_secret)` or `X-API-Key: {api_key}`

#### Field Mapping Engine
Custom stores may have different field names. The ecommerce service includes a configurable field mapping engine:
```json
{
  "products": {
    "external_field": "item_name",
    "internal_field": "name",
    "data_type": "string"
  }
}
```
Tenants can configure mappings through the dashboard after connecting.

### 7.5 Data Sync Architecture

#### Sync Flow
1. **Initial Full Sync**: On connection, fetch all products, orders (last 90 days), and customers
2. **Incremental Sync**: Webhooks handle real-time updates; scheduled fallback every 6 hours
3. **Manual Sync**: Dashboard "Sync" button triggers immediate full sync
4. **Conflict Resolution**: External platform is source of truth; our data is read-only copy

#### Data Stored Locally
- Products: name, SKU, price, currency, inventory count, status, image URLs
- Orders: order ID, customer, total, status, items count, timestamps
- Customers: email, name (for conversation matching — no payment data stored)
- Abandoned Carts: cart ID, customer, value, items, abandonment timestamp

#### Rate Limiting
- Shopify: 2 requests/second per store (Shopify's limit)
- WooCommerce: Configurable per store (typically 25 req/sec for modern hosting)
- Custom: 60 requests/minute default, configurable per connection
- Sync endpoint: 5 calls/hour per tenant (prevent abuse)
- Test endpoint: 5 calls/minute per tenant

### 7.6 Security Checklist for Store Connections

- [ ] All API keys/secrets encrypted at rest (Fernet AES-256)
- [ ] Webhook signature verification for all platforms (HMAC-SHA256)
- [ ] SSRF protection on store URLs (block internal/private IPs)
- [ ] OAuth state parameter stored in httpOnly cookie (CSRF protection)
- [ ] No credentials returned in API responses (only masked versions)
- [ ] Tenant isolation via RLS on ecommerce_connections table
- [ ] Rate limiting on all sync/test endpoints
- [ ] HTTPS enforced for production store URLs
- [ ] Shopify HMAC verification on OAuth callback
- [ ] WooCommerce callback validates state parameter
- [ ] Credential rotation support (re-connect without data loss)
- [ ] Webhook replay protection (5-minute dedup window)
- [ ] Audit log for all connection/disconnection events

### 7.7 Database Schema (Already in 001_foundation.sql)

```sql
-- E-Commerce connections with tenant isolation
CREATE TABLE ecommerce_connections (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    platform        text NOT NULL CHECK (platform IN ('shopify', 'woocommerce', 'custom')),
    store_url       text NOT NULL,
    store_name      text,
    access_token    text,      -- encrypted
    api_key         text,      -- encrypted
    api_secret      text,      -- encrypted
    webhook_secret  text,      -- encrypted
    status          text NOT NULL DEFAULT 'active',
    last_sync_at    timestamptz,
    sync_errors     jsonb DEFAULT '[]',
    settings        jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, platform, store_url)
);

ALTER TABLE ecommerce_connections ENABLE ROW LEVEL SECURITY;
CREATE POLICY ecommerce_tenant_isolation ON ecommerce_connections
    USING (tenant_id = current_tenant_id() OR is_admin_connection());
```

### 7.8 Environment Variables

```bash
# .env — Store Connection Credentials
SHOPIFY_CLIENT_ID=               # From Shopify Partners Dashboard
SHOPIFY_CLIENT_SECRET=           # From Shopify Partners Dashboard

# WooCommerce: No global credentials needed
# Each store generates its own consumer_key/consumer_secret during auth
# These are stored per-tenant in encrypted ecommerce_connections table

# Custom Store: No global credentials needed
# Each tenant provides their own API key/secret during manual setup
```

### 7.9 Implementation Priority for Store Connections

#### Phase 0 — MVP Launch
1. Shopify Partner account + App creation
2. Configure OAuth redirect URIs (production + dev)
3. Set SHOPIFY_CLIENT_ID/SECRET in .env
4. Test Shopify OAuth flow end-to-end
5. Test WooCommerce auth flow with a local WordPress instance
6. Test Custom Store manual connection
7. Verify webhook signature verification for all platforms
8. Deploy ecommerce service in Docker compose
9. Verify RLS policies on ecommerce_connections table

#### Phase 1 — Post-Launch
10. Shopify App Store submission (for public listing)
11. Shopify GDPR mandatory webhooks
12. Cart abandonment tracking + alerts
13. Product recommendation in bot conversations
14. Automated order status updates via WhatsApp/SMS
15. Custom field mapping UI in dashboard

#### Phase 2 — Growth
16. Magento integration (re-enable from dormant code)
17. BigCommerce integration
18. Marketplace plugin ecosystem (CRM, analytics, payments plugins)
19. Developer portal for third-party plugin submissions
