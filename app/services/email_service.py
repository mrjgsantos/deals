from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(*, to_email: str, reset_url: str) -> None:
    """Send a password reset email via Resend API.

    If RESEND_API_KEY is not configured, logs the URL and skips sending
    (useful for local development).
    """
    if not settings.resend_api_key:
        logger.warning("email_service_no_api_key skipping email to=%s reset_url=%s", to_email, reset_url)
        return

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2>Reset your password</h2>
      <p>Click the link below to choose a new password. The link expires in 1 hour.</p>
      <p><a href="{reset_url}" style="background:#111;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block">Reset password</a></p>
      <p style="color:#888;font-size:13px">If you didn't request this, you can ignore this email.</p>
    </div>
    """

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": [to_email],
                "subject": "Reset your Deals password",
                "html": html,
            },
            timeout=10,
        )
        response.raise_for_status()
        logger.info("email_service_sent to=%s", to_email)
    except Exception:
        logger.exception("email_service_send_failed to=%s", to_email)
        raise
