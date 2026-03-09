#!/bin/bash
# ============================================================
# Priya Global — Dev Server Setup Script
# Run this on a fresh Ubuntu 22.04 EC2 instance (t3.xlarge)
#
# Usage:
#   chmod +x setup-dev-server.sh
#   sudo ./setup-dev-server.sh
# ============================================================

set -euo pipefail

DOMAIN="dev.partython.com"
REPO_URL="https://github.com/partython/Global-ai-dev.git"
APP_DIR="/opt/priya-global"

echo "=========================================="
echo "  Priya Global — Dev Server Setup"
echo "  Domain: $DOMAIN"
echo "=========================================="

# ─── 1. System Updates ───
echo "[1/8] Updating system packages..."
apt-get update -y
apt-get upgrade -y
apt-get install -y \
  apt-transport-https \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  git \
  unzip \
  htop \
  jq \
  certbot \
  python3-certbot-nginx \
  nginx \
  ufw

# ─── 2. Install Docker ───
echo "[2/8] Installing Docker..."
if ! command -v docker &> /dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
  usermod -aG docker ubuntu
fi

# Install Docker Compose plugin (v2)
if ! docker compose version &> /dev/null; then
  apt-get install -y docker-compose-plugin
fi

echo "Docker version: $(docker --version)"
echo "Docker Compose version: $(docker compose version)"

# ─── 3. Clone Repository ───
echo "[3/8] Cloning repository..."
if [ -d "$APP_DIR" ]; then
  echo "  Directory exists — pulling latest..."
  cd "$APP_DIR"
  git pull origin main
else
  git clone "$REPO_URL" "$APP_DIR"
  cd "$APP_DIR"
fi

# ─── 4. Generate JWT Keys ───
echo "[4/8] Generating JWT RS256 keypair..."
mkdir -p "$APP_DIR/config"
if [ ! -f "$APP_DIR/config/jwt-private.pem" ]; then
  openssl genrsa -out "$APP_DIR/config/jwt-private.pem" 2048
  openssl rsa -in "$APP_DIR/config/jwt-private.pem" -pubout -out "$APP_DIR/config/jwt-public.pem"
  chmod 600 "$APP_DIR/config/jwt-private.pem"
  chmod 644 "$APP_DIR/config/jwt-public.pem"
  echo "  New JWT keys generated."
else
  echo "  JWT keys already exist — skipping."
fi

# ─── 5. Create .env file ───
echo "[5/8] Creating .env configuration..."
if [ ! -f "$APP_DIR/.env" ]; then
  # Generate secure passwords
  PG_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32)
  GRAFANA_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
  FERNET_KEY=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")

  cat > "$APP_DIR/.env" << ENVEOF
# =====================================================
# Priya Global Platform — DEV SERVER
# Server: $DOMAIN
# Generated: $(date -u +%Y-%m-%d)
# =====================================================

ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO
PLATFORM_NAME="Priya AI"

# ─── PostgreSQL ───
PG_HOST=postgres
PG_PORT=5432
PG_DATABASE=priya_global
PG_USER=priya
PG_PASSWORD=${PG_PASS}
PG_POOL_MIN=2
PG_POOL_MAX=10
PG_SSL_MODE=disable
POSTGRES_PASSWORD=${PG_PASS}
DATABASE_URL=postgres://priya:${PG_PASS}@postgres:5432/priya_global

# ─── Redis ───
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=1
REDIS_SSL=false

# ─── JWT ───
JWT_SECRET_KEY_FILE=/app/config/jwt-private.pem
JWT_PUBLIC_KEY_FILE=/app/config/jwt-public.pem
JWT_ACCESS_EXPIRY=900
JWT_REFRESH_EXPIRY=604800
JWT_ISSUER=priya-global

# ─── Credential Encryption ───
CREDENTIALS_ENCRYPTION_KEY=${FERNET_KEY}

# ─── Grafana ───
GRAFANA_PASSWORD=${GRAFANA_PASS}

# ─── AWS (copy from local .env) ───
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET=priya-global-media
SES_REGION=ap-south-1
SES_FROM_EMAIL=noreply@partython.com

# ─── AI/LLM Providers ───
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_AI_KEY=
PRIMARY_LLM=claude-3-5-sonnet-20241022
SECONDARY_LLM=gpt-4o
COST_LLM=gpt-4o-mini

# ─── Stripe ───
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=

# ─── Meta ───
META_APP_ID=
META_APP_SECRET=
META_CONFIG_ID=
META_REDIRECT_URI=https://${DOMAIN}/api/v1/whatsapp/embedded-signup/callback
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=
META_WEBHOOK_VERIFY_TOKEN=
NEXT_PUBLIC_META_APP_ID=
NEXT_PUBLIC_META_CONFIG_ID=

# ─── SMS/Voice ───
EXOTEL_SID=
EXOTEL_TOKEN=
EXOTEL_ACCOUNT_SID=
BANDWIDTH_ACCOUNT_ID=
BANDWIDTH_API_TOKEN=

# ─── Shopify OAuth ───
SHOPIFY_CLIENT_ID=
SHOPIFY_CLIENT_SECRET=

# ─── Webhook Verify Tokens ───
SOCIAL_WEBHOOK_TOKEN=$(openssl rand -hex 16)

# ─── Sentry ───
SENTRY_DSN=
SENTRY_ENABLED=false

# ─── Razorpay ───
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

# ─── Google OAuth ───
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# ─── Cloudflare Turnstile ───
TURNSTILE_SITE_KEY=1x00000000000000000000AA
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA

# ─── MSG91 ───
MSG91_AUTH_KEY=
MSG91_SENDER_ID=PARTAI
MSG91_OTP_TEMPLATE_ID=

# ─── Dashboard ───
DASHBOARD_URL=https://${DOMAIN}

# ─── Security ───
CORS_ORIGINS=https://${DOMAIN},http://${DOMAIN}
ENVEOF

  echo "  .env created with generated passwords."
  echo ""
  echo "  ================================================"
  echo "  IMPORTANT: Copy your API keys from local .env!"
  echo "  Edit: nano $APP_DIR/.env"
  echo "  ================================================"
  echo ""
else
  echo "  .env already exists — skipping."
fi

# ─── 6. Configure Nginx Reverse Proxy ───
echo "[6/8] Configuring Nginx reverse proxy..."
cat > /etc/nginx/sites-available/priya-global << 'NGINXEOF'
server {
    listen 80;
    server_name dev.partython.com;

    # Dashboard (Next.js)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    # API Gateway
    location /api/ {
        proxy_pass http://127.0.0.1:9000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
        client_max_body_size 50m;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:9000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }

    # Health check
    location /health {
        proxy_pass http://127.0.0.1:9000/health;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/priya-global /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ─── 7. Configure Firewall ───
echo "[7/8] Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp     # SSH
ufw allow 80/tcp     # HTTP
ufw allow 443/tcp    # HTTPS
ufw --force enable

# ─── 8. Create systemd service ───
echo "[8/8] Creating systemd service..."
cat > /etc/systemd/system/priya-global.service << SVCEOF
[Unit]
Description=Priya Global Platform
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable priya-global

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "  Next steps:"
echo ""
echo "  1. Edit .env with your API keys:"
echo "     sudo nano $APP_DIR/.env"
echo ""
echo "  2. Start the platform:"
echo "     cd $APP_DIR"
echo "     sudo docker compose up -d"
echo ""
echo "  3. Set up SSL (after DNS is pointed):"
echo "     sudo certbot --nginx -d $DOMAIN"
echo ""
echo "  4. Run database migration:"
echo "     sudo docker compose exec -T postgres psql -U priya -d priya_global < shared/migrations/001_foundation.sql"
echo ""
echo "  5. Check status:"
echo "     sudo docker compose ps"
echo "     curl http://localhost:9000/health"
echo ""
echo "=========================================="
