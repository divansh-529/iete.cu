from sqlalchemy import select

from app.auth.models import LoginAttempt
from app.core.config import Settings, settings
from tests.conftest import PASSWORD


def test_only_the_website_proxy_reaches_the_api(client, chair, db, monkeypatch):
    monkeypatch.setattr(settings, "proxy_secret", "s3cret-value")
    assert client.get("/api/health").status_code == 200                  # uptime checks still work
    assert client.get("/api/auth/me").status_code == 403                  # direct call to the backend
    assert client.get("/api/auth/me", headers={"x-proxy-secret": "wrong"}).status_code == 403

    proxy = {"x-proxy-secret": "s3cret-value", "x-real-client-ip": "203.0.113.7"}
    r = client.post("/api/auth/login", json={"email": "chair@ietecu.in", "password": PASSWORD}, headers=proxy)
    assert r.status_code == 200, r.text
    # The visitor's IP (not the proxy's) is what login rate limiting counts
    ips = {str(ip) for ip in db.scalars(select(LoginAttempt.ip)) if ip}
    assert ips == {"203.0.113.7"}


def test_forwarded_ip_ignored_without_secret(client, chair, db):
    client.post("/api/auth/login", json={"email": "chair@ietecu.in", "password": PASSWORD},
                headers={"x-real-client-ip": "203.0.113.7"})
    assert "203.0.113.7" not in {str(ip) for ip in db.scalars(select(LoginAttempt.ip)) if ip}


def test_pasted_proxy_secret_is_trimmed():
    assert Settings(proxy_secret=' "s3cret-value"\n').proxy_secret == "s3cret-value"


def test_hosted_postgres_url_uses_psycopg():
    url = Settings(database_url="postgresql://u:p@ep-x.neon.tech/iete?sslmode=require").database_url
    assert url == "postgresql+psycopg://u:p@ep-x.neon.tech/iete?sslmode=require"
