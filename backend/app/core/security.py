import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import AppError

_hasher = PasswordHasher()  # Argon2id with library defaults

# Verified against when the user does not exist, so response time does not reveal valid emails.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def validate_new_password(password: str, email: str | None = None) -> None:
    if len(password) < settings.min_password_length:
        raise AppError(422, "WEAK_PASSWORD",
                       f"Password must be at least {settings.min_password_length} characters.")
    if email and password.lower() == email.lower():
        raise AppError(422, "WEAK_PASSWORD", "Password must not be the same as the email address.")
