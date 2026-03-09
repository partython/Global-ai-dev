# Meta Platform Setup — Priya Global Go-Live Guide

**Goal**: Get WhatsApp Business API + Instagram DMs + Facebook Messenger + WhatsApp Business Calling live.

---

## Timeline Overview

| Step | Time | Blocking? |
|------|------|-----------|
| 1. Create Meta Developer App | 10 min | No |
| 2. Create Meta Business Account | 15 min | No |
| 3. Configure Embedded Signup | 20 min | No |
| 4. Add WhatsApp Product | 10 min | No |
| 5. Add Instagram Product | 10 min | No |
| 6. Add Facebook Messenger Product | 10 min | No |
| 7. Business Verification | ~~2-5 business days~~ | ✅ **DONE** |
| 8. App Review (Advanced Access) | 3-7 business days | **YES — SUBMIT NOW** |
| 9. WhatsApp Business Calling Opt-in | 1-2 days | **YES** |

**Total**: Code is ready NOW. External approvals take 5-12 business days.

---

## Step 1: Create Meta Developer App (10 min)

1. Go to https://developers.facebook.com/apps
2. Click **"Create App"**
3. Select **"Business"** as app type
4. App name: `Priya Global` (or your brand)
5. App contact email: `partythoninc@gmail.com`
6. Business Account: Select existing or create new
7. Click **Create App**

**After creation, note down:**
- App ID → put in `.env` as `META_APP_ID` and `NEXT_PUBLIC_META_APP_ID`
- App Secret → put in `.env` as `META_APP_SECRET`

---

## Step 2: Create/Verify Meta Business Account (15 min)

1. Go to https://business.facebook.com/settings
2. If no business account exists, create one:
   - Business name: `Partython Inc` (or your registered business name)
   - Your name, business email, business address
3. Go to **Business Settings → Security Center**
4. Click **"Start Verification"**
5. Upload documents:
   - Business registration certificate / GST certificate (India)
   - Utility bill or bank statement showing business address
   - PAN card of the business entity

**Business Verification typically takes 2-5 business days.**

---

## Step 3: Configure Embedded Signup (20 min)

This is what lets your tenants (customers) connect their own WhatsApp/Instagram/Facebook accounts through your dashboard.

### 3a. In your Meta App, go to **WhatsApp → Embedded Signup**

1. Click **"Create configuration"**
2. Configuration name: `Priya Global Onboarding`
3. Permissions requested:
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
   - `business_management`
4. Solution: **"Tech Provider"** (you're providing the platform to other businesses)
5. Callback URL: `https://partython.in/api/v1/whatsapp/embedded-signup/callback`

**Note the Config ID** → put in `.env` as `META_CONFIG_ID` and `NEXT_PUBLIC_META_CONFIG_ID`

### 3b. Configure OAuth Settings

1. Go to **App Settings → Basic**
2. Set **Valid OAuth Redirect URIs**:
   ```
   https://partython.in/api/v1/whatsapp/embedded-signup/callback
   https://localhost:3000/channels
   ```
3. Set **Deauthorize Callback URL**: `https://partython.in/webhook/meta-deauth`
4. Set **Data Deletion Request URL**: `https://partython.in/webhook/meta-data-delete`

---

## Step 4: Add WhatsApp Product (10 min)

1. In your Meta App, click **"Add Product"** → **WhatsApp**
2. Go to **WhatsApp → Getting Started**
3. Note your **Phone Number ID** and **WhatsApp Business Account ID**
4. Go to **WhatsApp → Configuration**:
   - Webhook URL: `https://partython.in/webhook/whatsapp`
   - Verify Token: `priya_wa_verify_2026` (matches your `.env`)
   - Subscribe to: `messages`, `message_deliveries`, `message_reads`, `messaging_handovers`

### Test Phone Number (for development)
Meta provides a test phone number. Use this for testing before business verification is complete.

---

## Step 5: Add Instagram Product (10 min)

1. Click **"Add Product"** → **Instagram**
2. Go to **Instagram → Basic Display** (or Messenger API for Instagram)
3. Configure:
   - Webhook URL: `https://partython.in/webhook/social`
   - Subscribe to: `messages`, `messaging_postbacks`, `messaging_referrals`

### Required Permissions (request in App Review):
- `instagram_basic`
- `instagram_manage_messages`
- `pages_manage_metadata`

---

## Step 6: Add Facebook Messenger Product (10 min)

1. Click **"Add Product"** → **Messenger**
2. Go to **Messenger → Settings**
3. Configure webhooks:
   - Webhook URL: `https://partython.in/webhook/social`
   - Verify Token: `priya_social_verify_2026`
   - Subscribe to: `messages`, `messaging_postbacks`, `messaging_referrals`, `messaging_handovers`

---

## Step 7: Business Verification (2-5 business days)

**This is the main blocker.** You cannot go live without Business Verification.

### Documents needed (India):
- GST Registration Certificate
- Business PAN Card
- Company registration (CIN) document
- Business bank statement (last 3 months)
- Domain verification (add DNS TXT record)

### Domain Verification:
1. Go to Business Settings → Brand Safety → Domains
2. Add `partython.in`
3. Add the DNS TXT record Meta provides to your domain's DNS settings
4. Wait for verification (usually minutes)

### Tips for faster verification:
- Ensure business name matches exactly across all documents
- Use a business email on the same domain (e.g., `support@partython.in`)
- Have a live website at `partython.in` with business info, privacy policy, terms of service
- Respond to any Meta requests within 24 hours

---

## Step 8: App Review — Advanced Access (3-7 business days)

After Business Verification, request Advanced Access for these permissions:

### WhatsApp Permissions:
- `whatsapp_business_management` — Manage WABA settings
- `whatsapp_business_messaging` — Send/receive messages

### Instagram Permissions:
- `instagram_basic` — Read profile info
- `instagram_manage_messages` — Send/receive DMs

### Facebook Permissions:
- `pages_messaging` — Send/receive Messenger messages
- `pages_manage_metadata` — Subscribe to page webhooks
- `business_management` — Manage business assets

### How to submit for App Review:
1. Go to App Review → Permissions and Features
2. For each permission, click **"Request Advanced Access"**
3. Provide:
   - Detailed use case description
   - Step-by-step screencast showing how your app uses each permission
   - Privacy Policy URL: `https://partython.in/privacy`
   - Terms of Service URL: `https://partython.in/terms`

### Screencast tips:
- Show the dashboard login → channels page → "Connect WhatsApp" flow
- Show a test conversation flowing through
- Show the tenant onboarding flow (Embedded Signup)
- Keep it under 5 minutes per permission

---

## Step 9: WhatsApp Business Calling (1-2 days)

WhatsApp Business Calling is a newer feature. After Business Verification:

1. Go to WhatsApp → Configuration in your Meta App
2. Enable **"WhatsApp Business Calling"** (if available in your region)
3. Or contact Meta support to enable calling for your WABA

### Consent Template (must be approved by Meta):
Create a template named `voice_call_consent`:
```
Category: UTILITY
Language: en

Body: Hi {{1}}, {{2}} from {{3}} would like to call you to discuss your inquiry.
Please reply to this message to allow us to call you.

Example: Hi John, Sarah from Acme Corp would like to call you...
```

Submit this template through the dashboard or Meta Business Manager.

### Call Flow:
1. Agent sends consent template → customer sees it in WhatsApp
2. Customer replies with any message → consent auto-granted (our backend handles this)
3. Agent clicks "Call" in dashboard → WhatsApp call rings on customer's phone
4. Audio streams through Meta → our platform for AI processing

---

## Environment Variables Checklist

After completing the Meta setup, fill in these values in `.env`:

```bash
# From Step 1
META_APP_ID=your_app_id_here
META_APP_SECRET=your_app_secret_here
NEXT_PUBLIC_META_APP_ID=your_app_id_here

# From Step 3
META_CONFIG_ID=your_config_id_here
NEXT_PUBLIC_META_CONFIG_ID=your_config_id_here

# From Step 4 (test number - will be overridden per-tenant via Embedded Signup)
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=your_waba_id
WHATSAPP_ACCESS_TOKEN=your_access_token
```

---

## Quick Test Checklist

After Meta setup is complete:

- [ ] Meta Developer App created with WhatsApp + Instagram + Messenger products
- [ ] Business Verification approved
- [ ] App Review approved for all required permissions
- [ ] Webhook URLs configured and verified
- [ ] DNS domain verification complete
- [ ] Consent template approved by Meta
- [ ] Test: Send WhatsApp message via test number
- [ ] Test: Receive webhook at `/webhook/whatsapp`
- [ ] Test: Instagram DM flows through `/webhook/social`
- [ ] Test: Facebook Messenger flows through `/webhook/social`
- [ ] Test: Embedded Signup connects tenant in dashboard
- [ ] Test: Voice call consent → call initiation works

---

## Parallel Tasks (Do While Waiting for Verification)

While waiting for Meta Business Verification (2-5 days):

1. **Google OAuth** (10 min): https://console.cloud.google.com/apis/credentials
   - Create OAuth 2.0 Client ID
   - Authorized redirect: `https://partython.in/api/v1/auth/oauth/google/callback`

2. **Cloudflare Turnstile** (5 min): https://dash.cloudflare.com/turnstile
   - Create widget for `partython.in`
   - Get Site Key + Secret Key

3. **Razorpay** (same day if docs ready): https://dashboard.razorpay.com
   - KYC with business PAN + GST
   - Enable test mode keys immediately
   - Production keys after KYC (1-2 days)

4. **MSG91** (for phone OTP): https://msg91.com
   - Sign up, get Auth Key
   - DLT registration (if sending SMS to Indian numbers)

5. **Deploy to production**: Get the platform running on `partython.in`
   - Docker Compose or Kubernetes
   - Nginx reverse proxy with SSL
   - PostgreSQL, Redis, Kafka in production config

---

## Support & Troubleshooting

- Meta Business Help: https://www.facebook.com/business/help
- WhatsApp Business API Support: https://business.facebook.com/direct-support
- Meta Developer Community: https://developers.facebook.com/community
- WhatsApp Business Platform changelog: https://developers.facebook.com/docs/whatsapp/changelog

If Business Verification is taking longer than 5 days, contact Meta support directly through the Business Help Center.
