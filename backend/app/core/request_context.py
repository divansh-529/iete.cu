import ipaddress
import secrets
from contextvars import ContextVar

from starlette.requests import Request

from app.core.config import settings

# Set per request by middleware; read by the audit writer.
client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)

PROXY_SECRET_HEADER = "x-proxy-secret"
PROXY_CLIENT_IP_HEADER = "x-real-client-ip"


def from_trusted_proxy(request: Request) -> bool:
    sent = request.headers.get(PROXY_SECRET_HEADER)
    return bool(settings.proxy_secret and sent and secrets.compare_digest(sent, settings.proxy_secret))


def request_ip(request: Request) -> str | None:
    """The client address if it is a valid IP (stored in INET columns), else None.

    Behind the hosting proxies every request comes from the proxy's address, so the visitor's
    IP is taken from the header our own proxy sets, and only when it proves it is our proxy."""
    if from_trusted_proxy(request):
        host = request.headers.get(PROXY_CLIENT_IP_HEADER)
    else:
        host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None
