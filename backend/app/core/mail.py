"""Outgoing email through Resend's HTTPS API (no extra dependency: the standard library is
enough). Free hosting plans block SMTP, so an HTTP API is the reliable option."""
import json
import logging
import urllib.error
import urllib.request

from app.core.config import settings

log = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


def mail_configured() -> bool:
    return bool(settings.resend_api_key)


def send_mail(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send one email. Returns False (never raises) when email is not set up or sending fails,
    so a mail problem can never undo the action that triggered it."""
    if not mail_configured():
        return False
    body = {"from": settings.mail_from, "to": [to], "subject": subject, "text": text}
    if html:
        body["html"] = html
    req = urllib.request.Request(RESEND_URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json",
        "User-Agent": "iete-portal/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("Email to %s failed: %s", to, e)
        return False
