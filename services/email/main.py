"""
Email Channel Service - Priya Global Multi-Tenant AI Sales Platform

Handles inbound email reception via AWS SES → SNS → HTTP notification.
Processes outbound email sending with full multi-tenant support.
Manages email templates, domain verification, bounces, complaints.

FastAPI service running on port 9011.
AWS SES for cost efficiency at scale (SendGrid alternative).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from email import message_from_bytes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.header import decode_header
from enum import Enum
from typing import Optional, Dict, List, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator, EmailStr
import asyncpg
import httpx
import aioboto3
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.core.config import config
from shared.core.database import db, generate_uuid, utc_now
from shared.core.security import mask_pii, sanitize_input, sanitize_email
from shared.middleware.auth import get_auth, AuthContext, require_role
from shared.observability.tracing import init_tracing, TracingMiddleware, shutdown_tracing
from shared.observability.sentry import init_sentry
from shared.middleware.sentry import SentryTenantMiddleware
from shared.events.event_bus import EventBus, EventType
from shared.middleware.cors import get_cors_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Constants & Configuration
# ============================================================================

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB
BLOCKED_EXTENSIONS = {".exe", ".bat", ".sh", ".ps1", ".com", ".dll", ".msi"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
    "image/gif",
    "text/plain",
    "text/csv",
}

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
BOUNCE_SUPPRESSION_HOURS = 24

# ============================================================================
# Pydantic Models
# ============================================================================

class EmailAttachment(BaseModel):
    """Email attachment metadata"""
    filename: str
    mime_type: str
    s3_key: str
    size_bytes: int
    s3_url: str


class EmailTemplate(BaseModel):
    """Email template for bulk/marketing emails"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    name: str
    subject: str
    html_body: str
    text_body: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @validator("name")
    def validate_name(cls, v):
        if not v or len(v) < 1 or len(v) > 200:
            raise ValueError("Template name must be 1-200 characters")
        return sanitize_input(v)


class VerifiedDomain(BaseModel):
    """Verified email domain for tenant"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    domain: str
    verification_token: str
    verified: bool = False
    dkim_verified: bool = False
    spf_verified: bool = False
    dmarc_record: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    verified_at: Optional[datetime] = None


class SendEmailRequest(BaseModel):
    """Request to send an email"""
    to: EmailStr
    subject: str
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    reply_to: Optional[EmailStr] = None
    cc: Optional[List[EmailStr]] = Field(default_factory=list)
    bcc: Optional[List[EmailStr]] = Field(default_factory=list)
    template_id: Optional[str] = None
    template_variables: Optional[Dict[str, str]] = Field(default_factory=dict)
    is_marketing: bool = False

    @validator("subject")
    def validate_subject(cls, v):
        if not v or len(v) > 998:
            raise ValueError("Subject required, max 998 chars")
        return sanitize_input(v)


class BouncedEmail(BaseModel):
    """Suppressed email address (bounce/complaint)"""
    email: str
    bounce_type: str  # permanent or transient
    complaint: bool = False
    suppressed_at: datetime = Field(default_factory=utc_now)
    suppressed_until: Optional[datetime] = None


class EmailAnalytics(BaseModel):
    """Email analytics for tenant"""
    period_start: datetime
    period_end: datetime
    total_sent: int = 0
    total_delivered: int = 0
    total_bounced: int = 0
    total_complained: int = 0
    total_opened: int = 0
    total_clicked: int = 0
    bounce_rate: float = 0.0
    complaint_rate: float = 0.0
    open_rate: float = 0.0
    click_rate: float = 0.0


class SNSMessage(BaseModel):
    """SNS notification wrapper"""
    Type: str
    MessageId: str
    Message: str
    Timestamp: str
    SignatureVersion: str
    Signature: str
    SigningCertUrl: str
    UnsubscribeURL: Optional[str] = None


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Email Channel Service",
    description="Multi-tenant email channel for Priya Global",
    version="1.0.0",
)
# Initialize Sentry error tracking

# Initialize event bus
event_bus = EventBus(service_name="email")
init_sentry(service_name="email", service_port=9011)

# Initialize OpenTelemetry distributed tracing
init_tracing(app, service_name="email")
app.add_middleware(TracingMiddleware)

# Sentry tenant context middleware
app.add_middleware(SentryTenantMiddleware)


# Global AWS clients (lazy initialized)
_ses_client = None
_s3_client = None


async def get_ses_client():
    """Get or create SES boto3 client (async)"""
    global _ses_client
    if _ses_client is None:
        session = aioboto3.Session()
        _ses_client = session.client(
            "ses",
            region_name=config.aws.ses_region,
            aws_access_key_id=config.aws.access_key,
            aws_secret_access_key=config.aws.secret_key,
        )
    return _ses_client


async def get_s3_client():
    """Get or create S3 boto3 client (async)"""
    global _s3_client
    if _s3_client is None:
        session = aioboto3.Session()
        _s3_client = session.client(
            "s3",
            region_name=config.aws.s3_region,
            aws_access_key_id=config.aws.access_key,
            aws_secret_access_key=config.aws.secret_key,
        )
    return _s3_client


# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize database pool and log startup"""
    await db.initialize()
    await event_bus.startup()
    logger.info("Email service started on port %d", config.ports.email)


@app.on_event("shutdown")
async def shutdown():
    """Cleanup database pool"""
    await db.close()
    shutdown_tracing()
    await event_bus.shutdown()
    logger.info("Email service shutdown")


# ============================================================================
# Helper Functions
# ============================================================================

async def extract_tenant_from_recipient(recipient_email: str) -> Optional[str]:
    """
    Map recipient email domain to tenant_id.
    Query verified_domains table for tenant ownership.
    Example: support@company.com → tenant_id
    """
    try:
        domain = recipient_email.split("@")[1].lower()
        async with db.admin_connection() as conn:
            row = await conn.fetchrow(
                "SELECT tenant_id FROM verified_domains WHERE domain = $1 AND verified = true",
                domain,
            )
            return row["tenant_id"] if row else None
    except Exception as e:
        logger.error("Error extracting tenant from recipient: %s: %s", mask_pii(recipient_email), e)
        return None


async def validate_attachment(filename: str, mime_type: str, size_bytes: int) -> bool:
    """Validate attachment for security"""
    # Check extension
    ext = "." + (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
    if ext in BLOCKED_EXTENSIONS:
        logger.warning("Blocked attachment extension: %s", ext)
        return False

    # Check size
    if size_bytes > MAX_ATTACHMENT_SIZE:
        logger.warning("Attachment too large: %s bytes", size_bytes)
        return False

    # Check MIME type (if available)
    if mime_type and mime_type not in ALLOWED_MIME_TYPES:
        logger.warning("Disallowed MIME type: %s", mime_type)
        return False

    return True


async def upload_attachment_to_s3(tenant_id: str, filename: str, data: bytes) -> Optional[str]:
    """Upload attachment to S3 and return signed URL"""
    try:
        s3 = await get_s3_client()
        key = f"email-attachments/{tenant_id}/{uuid4()}/{filename}"

        async with s3 as s3_sync:
            await s3_sync.put_object(
                Bucket=config.aws.s3_bucket,
                Key=key,
                Body=data,
                ContentDisposition=f'attachment; filename="{filename}"',
            )

        # Generate presigned URL (7 days)
        url = f"https://{config.aws.s3_bucket}.s3.{config.aws.s3_region}.amazonaws.com/{key}"
        logger.info("Uploaded attachment to S3: %s", key)
        return url
    except Exception as e:
        logger.error("Failed to upload attachment: %s", e)
        return None


async def is_email_suppressed(tenant_id: str, email: str) -> bool:
    """Check if email is in suppression list (bounced/complained) for this tenant"""
    try:
        async with db.tenant_connection(tenant_id) as conn:
            # CHANNEL-ROUTING-FIX: Add tenant_id filter to prevent cross-tenant suppression list leakage
            row = await conn.fetchrow(
                """SELECT suppressed_until FROM bounced_emails
                   WHERE tenant_id = $1 AND email = $2 AND (complaint = true OR suppressed_until IS NULL OR suppressed_until > NOW())""",
                tenant_id,
                email.lower(),
            )
            return row is not None
    except Exception as e:
        logger.error("Error checking suppression list: %s", e)
        return False


def render_template(template_html: str, variables: Dict[str, str]) -> str:
    """Simple Jinja2-style variable substitution {{var}}"""
    rendered = template_html
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered


async def build_email_mime(
    from_email: str,
    to: str,
    subject: str,
    html_body: Optional[str],
    text_body: Optional[str],
    cc: Optional[List[str]],
    bcc: Optional[List[str]],
    reply_to: Optional[str],
    attachments: Optional[List[EmailAttachment]],
    is_marketing: bool,
    unsubscribe_url: Optional[str],
) -> str:
    """Build MIME multipart email with all headers"""
    msg = MIMEMultipart("alternative")

    msg["From"] = from_email
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = reply_to

    # CAN-SPAM compliance
    if is_marketing and unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"

    # Add text body
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))

    # Add HTML body
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Add attachments
    if attachments:
        for att in attachments:
            try:
                part = MIMEBase("application", "octet-stream")
                # In production, fetch from S3 and add here
                part.add_header("Content-Disposition", f'attachment; filename="{att.filename}"')
                msg.attach(part)
            except Exception as e:
                logger.error("Failed to add attachment: %s", e)

    return msg.as_string()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def send_via_ses(
    from_email: str,
    to: str,
    cc: List[str],
    bcc: List[str],
    raw_message: str,
) -> Optional[str]:
    """
    Send email via AWS SES using send_raw_email.
    Returns message_id on success, None on failure.
    """
    try:
        ses = await get_ses_client()

        async with ses as ses_sync:
            response = await ses_sync.send_raw_email(
                RawMessage={"Data": raw_message},
                Source=from_email,
                Destinations=[to] + cc + bcc,
            )

        message_id = response.get("MessageId")
        logger.info("Email sent via SES: %s", message_id)
        return message_id
    except Exception as e:
        logger.error("Failed to send email via SES: %s", e)
        raise


# ============================================================================
# Inbound Email Processing
# ============================================================================

@app.post("/webhook/ses")
async def receive_email(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Receive emails from AWS SES via SNS notification.
    Handles:
    1. SNS subscription confirmation
    2. Email reception
    3. Parse and extract components
    4. Route to channel router
    """
    try:
        body = await request.json()

        # Handle SNS subscription confirmation
        if body.get("Type") == "SubscriptionConfirmation":
            async with httpx.AsyncClient() as client:
                await client.get(body["SubscribeURL"])
                logger.info("SNS subscription confirmed")
            return JSONResponse({"status": "ok"})

        # Process email notification
        if body.get("Type") != "Notification":
            return JSONResponse({"error": "Invalid message type"}, status_code=400)

        message = json.loads(body.get("Message", "{}"))
        receipt = message.get("receipt", {})
        mail_obj = message.get("mail", {})

        # Extract basic fields
        from_address = mail_obj.get("source", "")
        to_addresses = receipt.get("recipients", [])
        subject = mail_obj.get("commonHeaders", {}).get("subject", "[No Subject]")

        # Extract headers for threading
        headers = mail_obj.get("commonHeaders", {})
        in_reply_to = headers.get("in-reply-to")
        references = headers.get("references")

        # Extract tenant from recipient domain
        if not to_addresses:
            logger.error("Email received with no recipients")
            return JSONResponse({"error": "No recipients"}, status_code=400)

        tenant_id = await extract_tenant_from_recipient(to_addresses[0])
        if not tenant_id:
            logger.warning("Could not map recipient domain to tenant: %s", to_addresses[0])
            return JSONResponse({"error": "Unknown tenant domain"}, status_code=400)

        # Process email in background
        background_tasks.add_task(
            process_inbound_email,
            tenant_id=tenant_id,
            from_address=from_address,
            to_addresses=to_addresses,
            subject=subject,
            in_reply_to=in_reply_to,
            references=references,
            mail_object=mail_obj,
        )

        return JSONResponse({"status": "received"})

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error in email webhook: %s", e)
        return JSONResponse({"error": "Failed to process webhook"}, status_code=500)


async def process_inbound_email(
    tenant_id: str,
    from_address: str,
    to_addresses: List[str],
    subject: str,
    in_reply_to: Optional[str],
    references: Optional[str],
    mail_object: Dict[str, Any],
):
    """
    Background task: Process inbound email and route to Channel Router.
    Extracts body (HTML + text), attachments, detects threading.
    """
    try:
        from_clean = sanitize_email(from_address)
        if not from_clean:
            logger.error("Invalid from address: %s", mask_pii(from_address))
            return

        # Parse email body from mail_object (SES format)
        html_body = None
        text_body = None
        attachments: List[EmailAttachment] = []

        # In production, fetch full email from S3 (SES stores it there for large emails)
        # For now, extract from message object
        if "html" in mail_object:
            html_body = mail_object["html"]
        if "text" in mail_object:
            text_body = mail_object["text"]

        # Thread detection
        thread_id = None
        if in_reply_to:
            thread_id = in_reply_to
        elif references:
            thread_id = references.split()[-1]  # Last reference ID

        # Build normalized ChannelMessage
        message_data = {
            "message_id": str(uuid4()),
            "tenant_id": tenant_id,
            "channel": "email",
            "direction": "inbound",
            "sender_id": from_clean,
            "recipient_id": to_addresses[0],
            "message_type": "text",
            "content": {
                "text": text_body or html_body or "[Empty email]",
                "media_type": "email",
            },
            "metadata": {
                "subject": subject,
                "attachments": [att.dict() for att in attachments],
            },
            "context": {
                "thread_id": thread_id,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Forward to Channel Router
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "http://localhost:9003/api/v1/messages/inbound",
                json=message_data,
                headers={"X-Service-Auth": "internal"},
            )
            if response.status_code != 200:
                logger.error("Channel Router rejected message: %s", response.text)

        logger.info("Processed inbound email from %s to %s", mask_pii(from_clean), to_addresses[0])

    except Exception as e:
        logger.error("Error processing inbound email: %s", e)


# ============================================================================
# System Email Sending (Internal — no auth required)
# ============================================================================

# System sender for OTP, password reset, system notifications
SYSTEM_FROM_EMAIL = os.getenv("SES_FROM_EMAIL", "noreply@partython.ai")

# Built-in OTP email template
OTP_EMAIL_HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8f9fa; padding: 40px 0;">
  <div style="max-width: 480px; margin: 0 auto; background: white; border-radius: 12px; padding: 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
    <div style="text-align: center; margin-bottom: 32px;">
      <h1 style="color: #1a1a2e; font-size: 24px; margin: 0;">Priya AI</h1>
    </div>
    <p style="color: #333; font-size: 16px; line-height: 1.5;">Your login code is:</p>
    <div style="text-align: center; margin: 24px 0;">
      <span style="font-size: 36px; font-weight: 700; letter-spacing: 8px; color: #1a1a2e; background: #f0f0f5; padding: 16px 32px; border-radius: 8px; display: inline-block;">{{otp_code}}</span>
    </div>
    <p style="color: #666; font-size: 14px; line-height: 1.5;">This code expires in <strong>{{expires_minutes}} minutes</strong>.</p>
    <p style="color: #666; font-size: 14px; line-height: 1.5;">If you didn't request this code, you can safely ignore this email.</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
    <p style="color: #999; font-size: 12px; text-align: center;">Priya AI by Partython Inc. — Secure, passwordless login.</p>
  </div>
</body>
</html>
"""

# System template registry (built-in templates that don't need DB)
SYSTEM_TEMPLATES = {
    "otp_login": {
        "subject": "Your Priya AI Login Code",
        "html": OTP_EMAIL_HTML,
        "text": "Your login code is: {{otp_code}}. It expires in {{expires_minutes}} minutes.",
    },
    "welcome": {
        "subject": "Welcome to Priya AI",
        "html": "<p>Welcome to Priya AI! Your account is ready.</p>",
        "text": "Welcome to Priya AI! Your account is ready.",
    },
}


class SystemEmailRequest(BaseModel):
    """Internal system email request — no auth required."""
    to: str
    subject: Optional[str] = None
    template: Optional[str] = None
    variables: Optional[Dict[str, str]] = {}
    html_body: Optional[str] = None
    text_body: Optional[str] = None


@app.post("/api/v1/email/send-system")
async def send_system_email(req: SystemEmailRequest, request: Request):
    """
    Send system emails (OTP, welcome, password reset, etc).
    Internal-only — no tenant auth required.
    Accepts template name + variables, or raw body.

    Called by auth service for OTP delivery.
    """
    # Security: only allow internal service calls
    forwarded = request.headers.get("x-forwarded-for", "")
    host = request.client.host if request.client else ""
    # In Docker, internal calls come from container network (172.x.x.x)
    # In local dev, they come from localhost/127.0.0.1
    is_internal = (
        host.startswith("172.") or
        host.startswith("10.") or
        host in ("127.0.0.1", "localhost", "::1") or
        "internal" in request.headers.get("x-service-auth", "")
    )

    if not is_internal:
        logger.warning("Rejected external system email request from %s", host)
        raise HTTPException(status_code=403, detail="Internal access only")

    try:
        # Resolve template
        html_body = req.html_body
        text_body = req.text_body
        subject = req.subject

        if req.template and req.template in SYSTEM_TEMPLATES:
            tpl = SYSTEM_TEMPLATES[req.template]
            if not subject:
                subject = tpl["subject"]
            html_body = render_template(tpl["html"], req.variables or {})
            text_body = render_template(tpl["text"], req.variables or {})
        elif req.template:
            # Unknown template — use subject/body from request or fallback
            if not html_body and not text_body:
                logger.warning("Unknown system template: %s", req.template)
                raise HTTPException(status_code=400, detail=f"Unknown template: {req.template}")

        if not subject:
            subject = "Priya AI Notification"

        if not html_body and not text_body:
            raise HTTPException(status_code=400, detail="Email body or valid template required")

        # Build and send
        raw_message = await build_email_mime(
            from_email=SYSTEM_FROM_EMAIL,
            to=req.to,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            cc=[],
            bcc=[],
            reply_to=SYSTEM_FROM_EMAIL,
            attachments=None,
            is_marketing=False,
            unsubscribe_url=None,
        )

        message_id = await send_via_ses(
            from_email=SYSTEM_FROM_EMAIL,
            to=req.to,
            cc=[],
            bcc=[],
            raw_message=raw_message,
        )

        if not message_id:
            raise HTTPException(status_code=500, detail="Failed to send system email")

        logger.info("System email sent: %s → %s (template=%s)", message_id, mask_pii(req.to), req.template)
        return JSONResponse({
            "message_id": message_id,
            "status": "sent",
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error("System email error: %s", str(e))
        raise HTTPException(status_code=500, detail="Failed to send system email")


# ============================================================================
# Outbound Email Sending (Tenant — auth required)
# ============================================================================

@app.post("/api/v1/send")
async def send_email(
    request: SendEmailRequest,
    auth: AuthContext = Depends(get_auth),
):
    """
    Send email to recipient.
    Receives from Channel Router or API clients.
    Applies tenant branding, handles templates, tracks via SES.
    """
    try:
        tenant_id = auth.tenant_id

        # Check suppression list
        if await is_email_suppressed(tenant_id, request.to):
            logger.warning("Email suppressed (bounced/complained): %s", mask_pii(request.to))
            return JSONResponse(
                {"error": "Email address is suppressed"},
                status_code=400,
            )

        # Resolve sending domain
        async with db.tenant_connection(tenant_id) as conn:
            domain_row = await conn.fetchrow(
                "SELECT domain FROM verified_domains WHERE tenant_id = $1 AND verified = true LIMIT 1",
                tenant_id,
            )

        if not domain_row:
            return JSONResponse(
                {"error": "No verified sending domain for tenant"},
                status_code=400,
            )

        from_email = f"noreply@{domain_row['domain']}"

        # Resolve template if provided
        html_body = request.html_body
        text_body = request.text_body

        if request.template_id:
            async with db.tenant_connection(tenant_id) as conn:
                template = await conn.fetchrow(
                    "SELECT html_body, text_body FROM email_templates WHERE id = $1",
                    request.template_id,
                )

            if not template:
                return JSONResponse({"error": "Template not found"}, status_code=404)

            # Render template with variables
            html_body = render_template(template["html_body"], request.template_variables)
            text_body = render_template(template.get("text_body", ""), request.template_variables)

        if not html_body and not text_body:
            return JSONResponse({"error": "Email body required"}, status_code=400)

        # Build MIME message
        reply_to = request.reply_to or from_email
        unsubscribe_url = f"https://app.priyaai.com/unsubscribe/{tenant_id}?email={request.to}" if request.is_marketing else None

        raw_message = await build_email_mime(
            from_email=from_email,
            to=request.to,
            subject=request.subject,
            html_body=html_body,
            text_body=text_body,
            cc=request.cc or [],
            bcc=request.bcc or [],
            reply_to=reply_to,
            attachments=None,
            is_marketing=request.is_marketing,
            unsubscribe_url=unsubscribe_url,
        )

        # Send via SES
        message_id = await send_via_ses(
            from_email=from_email,
            to=request.to,
            cc=request.cc or [],
            bcc=request.bcc or [],
            raw_message=raw_message,
        )

        if not message_id:
            return JSONResponse({"error": "Failed to send email"}, status_code=500)

        # Log send event
        async with db.tenant_connection(tenant_id) as conn:
            await conn.execute(
                """INSERT INTO email_events (tenant_id, message_id, recipient, event_type, timestamp)
                   VALUES ($1, $2, $3, $4, $5)""",
                tenant_id, message_id, request.to, "send", utc_now(),
            )

        logger.info("Email sent: %s to %s", message_id, mask_pii(request.to))
        return JSONResponse({
            "message_id": message_id,
            "status": "sent",
            "timestamp": utc_now().isoformat(),
        })

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error sending email: %s", e)
        return JSONResponse({"error": "Failed to send email"}, status_code=500)


# ============================================================================
# Email Templates CRUD
# ============================================================================

@app.get("/api/v1/templates")
async def list_templates(
    auth: AuthContext = Depends(get_auth),
):
    """List email templates for tenant"""
    try:
        async with db.tenant_connection(auth.tenant_id) as conn:
            templates = await conn.fetch(
                "SELECT id, name, subject, created_at FROM email_templates WHERE tenant_id = $1 ORDER BY created_at DESC",
                auth.tenant_id,
            )

        return JSONResponse({
            "templates": [dict(t) for t in templates],
        })
    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error listing templates: %s", e)
        return JSONResponse({"error": "Failed to list templates"}, status_code=500)


@app.post("/api/v1/templates")
async def create_template(
    template: EmailTemplate,
    auth: AuthContext = Depends(get_auth),
):
    """Create new email template"""
    try:
        template.tenant_id = auth.tenant_id

        async with db.tenant_connection(auth.tenant_id) as conn:
            await conn.execute(
                """INSERT INTO email_templates (id, tenant_id, name, subject, html_body, text_body, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                template.id, auth.tenant_id, template.name, template.subject,
                template.html_body, template.text_body, utc_now(), utc_now(),
            )

        logger.info("Template created: %s", template.id)
        return JSONResponse({
            "id": template.id,
            "status": "created",
        }, status_code=201)

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error creating template: %s", e)
        return JSONResponse({"error": "Failed to create template"}, status_code=500)


@app.put("/api/v1/templates/{template_id}")
async def update_template(
    template_id: str,
    template: EmailTemplate,
    auth: AuthContext = Depends(get_auth),
):
    """Update email template"""
    try:
        async with db.tenant_connection(auth.tenant_id) as conn:
            await conn.execute(
                """UPDATE email_templates SET name = $1, subject = $2, html_body = $3,
                   text_body = $4, updated_at = $5 WHERE id = $6 AND tenant_id = $7""",
                template.name, template.subject, template.html_body, template.text_body,
                utc_now(), template_id, auth.tenant_id,
            )

        logger.info("Template updated: %s", template_id)
        return JSONResponse({"status": "updated"})

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error updating template: %s", e)
        return JSONResponse({"error": "Failed to update template"}, status_code=500)


@app.delete("/api/v1/templates/{template_id}")
async def delete_template(
    template_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Delete email template"""
    try:
        async with db.tenant_connection(auth.tenant_id) as conn:
            await conn.execute(
                "DELETE FROM email_templates WHERE id = $1 AND tenant_id = $2",
                template_id, auth.tenant_id,
            )

        logger.info("Template deleted: %s", template_id)
        return JSONResponse({"status": "deleted"})

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error deleting template: %s", e)
        return JSONResponse({"error": "Failed to delete template"}, status_code=500)


# ============================================================================
# Domain Management
# ============================================================================

@app.get("/api/v1/domains")
async def list_domains(
    auth: AuthContext = Depends(get_auth),
):
    """List verified domains for tenant"""
    try:
        async with db.tenant_connection(auth.tenant_id) as conn:
            domains = await conn.fetch(
                """SELECT id, domain, verified, dkim_verified, spf_verified, created_at, verified_at
                   FROM verified_domains WHERE tenant_id = $1 ORDER BY created_at DESC""",
                auth.tenant_id,
            )

        return JSONResponse({
            "domains": [dict(d) for d in domains],
        })
    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error listing domains: %s", e)
        return JSONResponse({"error": "Failed to list domains"}, status_code=500)


@app.post("/api/v1/domains/verify")
async def initiate_domain_verification(
    domain: str,
    auth: AuthContext = Depends(get_auth),
):
    """Initiate domain verification (return DNS records to add)"""
    try:
        domain_lower = domain.lower().strip()

        # Check if already verified
        async with db.tenant_connection(auth.tenant_id) as conn:
            existing = await conn.fetchrow(
                "SELECT id FROM verified_domains WHERE domain = $1 AND tenant_id = $2",
                domain_lower, auth.tenant_id,
            )

        if existing:
            return JSONResponse({"error": "Domain already exists"}, status_code=400)

        # Generate verification token
        verification_token = f"v1_{uuid4()}"
        domain_id = str(uuid4())

        async with db.tenant_connection(auth.tenant_id) as conn:
            await conn.execute(
                """INSERT INTO verified_domains (id, tenant_id, domain, verification_token, created_at)
                   VALUES ($1, $2, $3, $4, $5)""",
                domain_id, auth.tenant_id, domain_lower, verification_token, utc_now(),
            )

        # Return DNS records to add
        return JSONResponse({
            "domain_id": domain_id,
            "domain": domain_lower,
            "verification_token": verification_token,
            "dns_records": [
                {
                    "type": "TXT",
                    "name": f"_priya-verification.{domain_lower}",
                    "value": verification_token,
                    "description": "Domain ownership verification",
                },
                {
                    "type": "MX",
                    "name": domain_lower,
                    "value": "10 inbound-smtp.ap-south-1.amazonaws.com",
                    "description": "AWS SES inbound MX record",
                },
                {
                    "type": "TXT",
                    "name": f"_dmarc.{domain_lower}",
                    "value": 'v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain_lower}',
                    "description": "DMARC policy",
                },
            ],
            "status": "verification_initiated",
        }, status_code=201)

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error initiating domain verification: %s", e)
        return JSONResponse({"error": "Failed to initiate domain verification"}, status_code=500)


@app.get("/api/v1/domains/{domain_id}/status")
async def check_domain_status(
    domain_id: str,
    auth: AuthContext = Depends(get_auth),
):
    """Check domain verification status"""
    try:
        async with db.tenant_connection(auth.tenant_id) as conn:
            domain = await conn.fetchrow(
                "SELECT domain, verified, dkim_verified, spf_verified FROM verified_domains WHERE id = $1",
                domain_id,
            )

        if not domain:
            return JSONResponse({"error": "Domain not found"}, status_code=404)

        return JSONResponse({
            "domain": domain["domain"],
            "verified": domain["verified"],
            "dkim_verified": domain["dkim_verified"],
            "spf_verified": domain["spf_verified"],
        })

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error checking domain status: %s", e)
        return JSONResponse({"error": "Failed to check domain status"}, status_code=500)


# ============================================================================
# Bounce & Complaint Handling
# ============================================================================

@app.post("/webhook/ses/notifications")
async def handle_ses_notifications(request: Request):
    """
    Handle SES bounce/complaint notifications from SNS.
    Updates suppression list, prevents future sends.
    """
    try:
        body = await request.json()

        # Verify SNS subscription
        if body.get("Type") == "SubscriptionConfirmation":
            async with httpx.AsyncClient() as client:
                await client.get(body["SubscribeURL"])
            return JSONResponse({"status": "ok"})

        if body.get("Type") != "Notification":
            return JSONResponse({"error": "Invalid type"}, status_code=400)

        message = json.loads(body.get("Message", "{}"))
        event_type = message.get("eventType")

        if event_type == "Bounce":
            await handle_bounce(message)
        elif event_type == "Complaint":
            await handle_complaint(message)

        return JSONResponse({"status": "processed"})

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error handling SES notification: %s", e)
        return JSONResponse({"error": "Failed to process notification"}, status_code=500)


async def handle_bounce(message: Dict[str, Any]):
    """Process SES bounce notification"""
    try:
        bounce = message.get("bounce", {})
        bounce_type = bounce.get("bounceType", "permanent")
        bounced_recipients = bounce.get("bouncedRecipients", [])

        for recipient in bounced_recipients:
            email = recipient.get("emailAddress", "").lower()
            if not email:
                continue

            # CHANNEL-ROUTING-FIX: Resolve tenant from bounce message metadata
            # SES bounce notifications may include Message-ID → tenant mapping
            tenant_id = message.get("tenant_id")
            if not tenant_id:
                logger.warning("Bounce notification missing tenant_id for %s", mask_pii(email))
                continue

            logger.info("Processing bounce for %s: %s (tenant=%s)", mask_pii(email), bounce_type, tenant_id)

            # Suppress email for 24 hours if transient, permanently if hard bounce
            suppressed_until = None
            if bounce_type == "transient":
                suppressed_until = datetime.now(timezone.utc) + \
                    __import__("datetime").timedelta(hours=BOUNCE_SUPPRESSION_HOURS)

            # CHANNEL-ROUTING-FIX: Store in tenant-specific suppression list
            async with db.tenant_connection(tenant_id) as conn:
                await conn.execute(
                    """INSERT INTO bounced_emails (id, tenant_id, email, bounce_type, suppressed_at, suppressed_until)
                       VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (tenant_id, email) DO UPDATE SET suppressed_until = $6""",
                    str(uuid4()), tenant_id, email, bounce_type, utc_now(), suppressed_until,
                )

    except Exception as e:
        logger.error("Error handling bounce: %s", e)


async def handle_complaint(message: Dict[str, Any]):
    """Process SES complaint notification"""
    try:
        complaint = message.get("complaint", {})
        complained_recipients = complaint.get("complainedRecipients", [])

        for recipient in complained_recipients:
            email = recipient.get("emailAddress", "").lower()
            if not email:
                continue

            # CHANNEL-ROUTING-FIX: Resolve tenant from complaint message metadata
            tenant_id = message.get("tenant_id")
            if not tenant_id:
                logger.warning("Complaint notification missing tenant_id for %s", mask_pii(email))
                continue

            logger.warning("Complaint for %s (tenant=%s)", mask_pii(email), tenant_id)

            # CHANNEL-ROUTING-FIX: Permanently suppress and flag as complaint in tenant-specific list
            async with db.tenant_connection(tenant_id) as conn:
                await conn.execute(
                    """INSERT INTO bounced_emails (id, tenant_id, email, bounce_type, complaint, suppressed_at)
                       VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (tenant_id, email) DO UPDATE SET complaint = true""",
                    str(uuid4()), tenant_id, email, "complaint", True, utc_now(),
                )

    except Exception as e:
        logger.error("Error handling complaint: %s", e)


# ============================================================================
# Email Analytics
# ============================================================================

@app.get("/api/v1/analytics")
async def get_analytics(
    days: int = Query(7, ge=1, le=90),
    auth: AuthContext = Depends(get_auth),
):
    """Get email analytics for tenant (open rate, click rate, bounce rate, etc.)"""
    try:
        start_date = (datetime.now(timezone.utc) -
                      __import__("datetime").timedelta(days=days))

        async with db.tenant_connection(auth.tenant_id) as conn:
            stats = await conn.fetchrow(
                """SELECT
                   COUNT(*) FILTER (WHERE event_type = 'send') as total_sent,
                   COUNT(*) FILTER (WHERE event_type = 'delivery') as total_delivered,
                   COUNT(*) FILTER (WHERE event_type = 'bounce') as total_bounced,
                   COUNT(*) FILTER (WHERE event_type = 'complaint') as total_complained,
                   COUNT(*) FILTER (WHERE event_type = 'open') as total_opened,
                   COUNT(*) FILTER (WHERE event_type = 'click') as total_clicked
                   FROM email_events WHERE tenant_id = $1 AND timestamp >= $2""",
                auth.tenant_id, start_date,
            )

        stats_dict = dict(stats) if stats else {}
        total_sent = stats_dict.get("total_sent", 0) or 0

        return JSONResponse({
            "period_start": start_date.isoformat(),
            "period_end": datetime.now(timezone.utc).isoformat(),
            "total_sent": total_sent,
            "total_delivered": stats_dict.get("total_delivered", 0) or 0,
            "total_bounced": stats_dict.get("total_bounced", 0) or 0,
            "total_complained": stats_dict.get("total_complained", 0) or 0,
            "total_opened": stats_dict.get("total_opened", 0) or 0,
            "total_clicked": stats_dict.get("total_clicked", 0) or 0,
            "bounce_rate": (stats_dict.get("total_bounced", 0) or 0) / total_sent * 100 if total_sent > 0 else 0,
            "complaint_rate": (stats_dict.get("total_complained", 0) or 0) / total_sent * 100 if total_sent > 0 else 0,
            "open_rate": (stats_dict.get("total_opened", 0) or 0) / total_sent * 100 if total_sent > 0 else 0,
            "click_rate": (stats_dict.get("total_clicked", 0) or 0) / total_sent * 100 if total_sent > 0 else 0,
        })

    except Exception as e:
        # HIGH FIX: Do not expose exception details to client
        logger.error("Error getting analytics: %s", e)
        return JSONResponse({"error": "Failed to retrieve analytics"}, status_code=500)


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Service health check"""
    return JSONResponse({
        "status": "healthy",
        "service": "email",
        "port": config.ports.email,
    })


if __name__ == "__main__":
    import uvicorn


    uvicorn.run(app, host="0.0.0.0", port=config.ports.email, log_level="info")
