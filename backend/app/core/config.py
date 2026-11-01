from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="IETE_", extra="ignore")

    database_url: str = "postgresql+psycopg://iete:iete_dev_password@localhost:5433/iete"

    # Production sits behind the website's /api proxy (frontend/functions). When set, the API only
    # answers requests carrying this secret, and trusts the visitor IP that the proxy forwards.
    proxy_secret: str = ""

    # Sessions
    session_idle_minutes: int = 120
    session_absolute_days: int = 7
    cookie_secure: bool = False  # must be True in production (HTTPS)

    # Login protection
    login_max_failures: int = 5          # consecutive failures before lockout
    login_lockout_minutes: int = 15
    login_ip_max_failures: int = 30      # per IP within the window below
    login_ip_window_minutes: int = 15

    # Accounts
    invite_ttl_hours: int = 72
    min_password_length: int = 10
    frontend_base_url: str = "http://localhost:5173"
    # Every new account starts with this password and must change it at first sign-in
    # (Chairperson's requirement). Override with IETE_DEFAULT_MEMBER_PASSWORD.
    default_member_password: str = "CU@12345678"

    # Email (Resend, https://resend.com: an HTTPS API, since free hosts block SMTP). Without a
    # key, emails are skipped and the portal shows the sign-in details to share by hand.
    resend_api_key: str = ""
    mail_from: str = "IETE Student Forum <noreply@isfcu.online>"

    # File storage over the S3 API (any S3-compatible provider). Without these,
    # uploads answer with a clear "not set up yet" message and everything else keeps working.
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_region: str = "auto"

    @field_validator("proxy_secret")
    @classmethod
    def _strip_secret(cls, value: str) -> str:
        """Quotes and spaces copied along with the value are not part of the secret."""
        return value.strip().strip("'\"").strip()

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, url: str) -> str:
        """Hosted Postgres providers hand out postgres:// or postgresql:// URLs; use psycopg 3.
        Quotes and spaces copied along with the value from an .env file are dropped."""
        url = url.strip().strip("'\"").strip()
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


settings = Settings()
