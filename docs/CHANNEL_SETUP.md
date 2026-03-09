# Channel Setup Guide — Partython.ai

## Overview

Partython.ai supports 10 communication channels. Each channel uses one of three authentication methods:

| Channel | Auth Type | Provider |
|---------|-----------|----------|
| WhatsApp Business | OAuth | Meta Business Suite |
| Instagram DM | OAuth | Meta Business Suite |
| Facebook Messenger | OAuth | Meta Business Suite |
| Shopify | OAuth | Shopify Partners |
| Email (SMTP) | Manual | Gmail/Outlook/Custom SMTP |
| Telegram Bot | Manual | @BotFather |
| SMS | Manual | Exotel |
| Voice / Phone | Manual | Exotel |
| Web Chat | Auto | Self-hosted (no setup) |
| RCS Messaging | Manual | Google RBM |

---

## 1. Meta (WhatsApp + Instagram + Facebook)

All three Meta channels are connected through a single Meta App with multiple products.

### Step 1: Create a Meta App

1. Go to [Meta for Developers](https://developers.facebook.com)
2. Click **My Apps** → **Create App**
3. Select **Business** type
4. Enter app name: `Partython AI Platform`
5. Link your Business Manager account

### Step 2: Add Products to the App

In your App Dashboard, click **Add Product** and add:

- **Facebook Login** (for OAuth)
- **WhatsApp** (for Business API)
- **Instagram** (for Messaging)

### Step 3: Configure Facebook Login

1. Go to **Facebook Login** → **Settings**
2. Add **Valid OAuth Redirect URIs**:
   - Production: `https://www.partython.in/api/oauth/meta/callback`
   - Local dev: `http://localhost:3000/api/oauth/meta/callback`
3. Enable **Client OAuth Login** and **Web OAuth Login**

### Step 4: Get App Credentials

1. Go to **Settings** → **Basic**
2. Copy **App ID** → set as `META_APP_ID` in `.env`
3. Copy **App Secret** → set as `META_APP_SECRET` in `.env`

### Step 5: WhatsApp Business Setup

1. In the app, go to **WhatsApp** → **API Setup**
2. Create or select a WhatsApp Business Account
3. Add a phone number (verify via SMS/call)
4. Copy your **Business Account ID** → set as `WHATSAPP_BUSINESS_ACCOUNT_ID`
5. Set webhook verify token → set as `META_WEBHOOK_VERIFY_TOKEN`

### Step 6: Webhook Configuration

1. Go to **WhatsApp** → **Configuration**
2. Set **Callback URL**: `https://api.partython.in/webhook/whatsapp`
3. Set **Verify Token**: same as `META_WEBHOOK_VERIFY_TOKEN`
4. Subscribe to: `messages`, `message_deliveries`, `message_reads`

5. Go to **Instagram** → **Webhooks**
6. Set **Callback URL**: `https://api.partython.in/webhook/social`
7. Subscribe to: `messages`, `messaging_postbacks`

### Step 7: App Review (Production)

Before going live, submit for **App Review** with these permissions:
- `whatsapp_business_management`
- `whatsapp_business_messaging`
- `instagram_basic`
- `instagram_manage_messages`
- `pages_manage_metadata`
- `pages_messaging`
- `pages_read_engagement`

### Local Dev: Webhook Testing with ngrok

```bash
ngrok http 9000
# Copy the https URL, e.g., https://abc123.ngrok.io
# Set as webhook URL in Meta Dashboard:
# https://abc123.ngrok.io/webhook/whatsapp
```

---

## 2. Shopify

### Step 1: Create a Shopify App

1. Go to [Shopify Partners](https://partners.shopify.com)
2. Click **Apps** → **Create app**
3. Choose **Custom app** or **Public app**
4. Set app name: `Partython AI`

### Step 2: Configure OAuth

1. In **App setup** → **URLs**:
   - **App URL**: `https://www.partython.in`
   - **Allowed redirection URL(s)**:
     - `https://www.partython.in/api/oauth/shopify/callback`
     - `http://localhost:3000/api/oauth/shopify/callback` (dev)

2. Under **API access scopes**, select:
   - `read_customers`, `write_customers`
   - `read_orders`
   - `read_products`
   - `read_content`

### Step 3: Get Credentials

1. Copy **API key** → set as `SHOPIFY_CLIENT_ID` in `.env`
2. Copy **API secret key** → set as `SHOPIFY_CLIENT_SECRET` in `.env`

---

## 3. Telegram Bot

### Step 1: Create a Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., `Partython Support`)
4. Choose a username (must end in `bot`, e.g., `partython_support_bot`)
5. Copy the **bot token** (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Connect in Dashboard

1. Go to **Channels** in the Partython dashboard
2. Click **Connect** on Telegram Bot
3. Paste the bot token
4. Click **Test Connection** → should show bot username
5. Click **Save & Connect**

---

## 4. Email (SMTP)

### Gmail with App Password

1. Enable 2-Step Verification on your Google Account
2. Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
3. Generate a new app password for "Mail"
4. In the dashboard, enter:
   - SMTP Server: `smtp.gmail.com`
   - SMTP Port: `587`
   - Email: your Gmail address
   - Password: the app password (not your Gmail password)

### Outlook / Microsoft 365

1. Go to Azure Portal → App registrations → New registration
2. Set redirect URI: `https://www.partython.in/api/oauth/microsoft/callback`
3. Add API permissions: `SMTP.Send`, `IMAP.AccessAsUser.All`
4. Get Client ID and Client Secret

### Custom SMTP

Enter your SMTP server details directly:
- Server hostname
- Port (usually 587 for TLS, 465 for SSL)
- Username
- Password

---

## 5. SMS (Exotel)

### Step 1: Get Exotel Credentials

1. Log in to [Exotel Dashboard](https://my.exotel.com)
2. Go to **API Settings** → **API Credentials**
3. Copy:
   - **Account SID**
   - **API Key**
   - **API Token**

### Step 2: Connect in Dashboard

1. Go to **Channels** → Click **Connect** on SMS
2. Enter your Exotel SID, Token, and Sender ID
3. Click **Test Connection**
4. Click **Save & Connect**

---

## 6. Voice / Phone (Exotel)

Same Exotel credentials as SMS, plus a **Caller ID / Virtual Number**:

1. In Exotel Dashboard, go to **Phone Numbers**
2. Purchase or use an existing virtual number
3. Enter the number as Caller ID in the dashboard

---

## 7. Web Chat

No external setup needed. WebChat is self-hosted.

1. Go to **Channels** → Click **Enable** on Web Chat
2. Copy the embed code from the Manage page
3. Add it to your website's HTML

---

## 8. RCS Messaging (Google RBM)

### Step 1: Register as RCS Agent

1. Go to [Google Business Communications](https://business.google.com/rcs)
2. Create an RBM agent
3. Get verified by Google

### Step 2: Create Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project and enable the RBM API
3. Create a Service Account with RBM access
4. Download the JSON key file
5. Enter the API key and Project ID in the dashboard

---

## Environment Variables Summary

```bash
# Meta (WhatsApp + Instagram + Facebook)
META_APP_ID=your_meta_app_id
META_APP_SECRET=your_meta_app_secret
WHATSAPP_BUSINESS_ACCOUNT_ID=your_waba_id
META_WEBHOOK_VERIFY_TOKEN=your_verify_token
SOCIAL_WEBHOOK_TOKEN=your_social_verify_token

# Shopify
SHOPIFY_CLIENT_ID=your_shopify_client_id
SHOPIFY_CLIENT_SECRET=your_shopify_client_secret

# Exotel (SMS + Voice)
EXOTEL_SID=your_exotel_sid
EXOTEL_TOKEN=your_exotel_token
EXOTEL_ACCOUNT_SID=your_exotel_account_sid

# Credential Encryption (already configured)
CREDENTIALS_ENCRYPTION_KEY=your_fernet_key
```

---

## Security Notes

- All credentials are encrypted with AES-256 before database storage
- OAuth tokens are exchanged server-side (secrets never exposed to browser)
- CSRF protection via httpOnly cookies on all OAuth flows
- Webhook signatures verified (HMAC-SHA256) for Meta and Shopify
- Tenant isolation via PostgreSQL Row Level Security (RLS)
- Test connection endpoints are rate-limited (5 req/min per tenant)
