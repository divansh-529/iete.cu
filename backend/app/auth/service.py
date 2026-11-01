from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.auth.models import LoginAttempt, UserSession
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import (hash_password, needs_rehash, new_token, token_hash,
                               validate_new_password, verify_password)
from app.core.time import utcnow
from app.users.models import InviteToken, User


def create_session(db: Session, user: User, ip: str | None, user_agent: str | None) -> str:
    token = new_token()
    db.add(UserSession(user_id=user.id, token_hash=token_hash(token), ip=ip,
                       user_agent=(user_agent or "")[:300],
                       expires_at=utcnow() + timedelta(days=settings.session_absolute_days)))
    return token


def revoke_sessions(db: Session, user_id: int, keep_session_id: int | None = None) -> None:
    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    if keep_session_id is not None:
        stmt = stmt.where(UserSession.id != keep_session_id)
    db.execute(stmt)


def login(db: Session, email: str, password: str, ip: str | None,
          user_agent: str | None) -> tuple[User, str]:
    now = utcnow()
    window_start = now - timedelta(minutes=settings.login_ip_window_minutes)
    ip_failures = db.scalar(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.ip == ip, LoginAttempt.success.is_(False),
        LoginAttempt.created_at > window_start)) if ip else 0
    if ip_failures >= settings.login_ip_max_failures:
        raise AppError(429, "TOO_MANY_ATTEMPTS", "Too many failed logins. Try again later.")

    user = db.scalar(select(User).where(User.email == email, User.status != "deleted"))
    if user and user.locked_until and user.locked_until > now:
        db.add(LoginAttempt(email=email, ip=ip, success=False))
        db.commit()
        minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise AppError(429, "ACCOUNT_LOCKED",
                       f"Too many failed attempts. Try again in {minutes} minute(s).")

    ok = verify_password(user.password_hash if user else None, password)
    if not ok or user is None:
        db.add(LoginAttempt(email=email, ip=ip, success=False))
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_count = 0
                audit.record(db, None, "auth.lockout", "user", user.id)
        db.commit()
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")

    if user.status not in ("active", "invited"):
        db.add(LoginAttempt(email=email, ip=ip, success=False))
        db.commit()
        message = {"proposed": "This account is waiting for approval. You'll get an email when it's ready.",
                   "rejected": "This account was not approved. Contact your department lead."
                   }.get(user.status, f"This account is {user.status}. Contact an administrator.")
        raise AppError(403, "ACCOUNT_DISABLED", message)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.add(LoginAttempt(email=email, ip=ip, success=True))
    token = create_session(db, user, ip, user_agent)
    audit.record(db, user.id, "auth.login", "user", user.id)
    db.commit()
    return user, token


def logout(db: Session, sess: UserSession) -> None:
    audit.record(db, sess.user_id, "auth.logout", "user", sess.user_id)
    db.delete(sess)
    db.commit()


def change_password(db: Session, user: User, sess: UserSession, current: str | None, new: str) -> None:
    """Right after signing in with a first-time password (must_change_password), the person has
    just proved it, so it isn't asked again. A later, voluntary change still needs the current
    password, so someone at an unattended signed-in device can't take the account over."""
    if not user.must_change_password and not verify_password(user.password_hash, current or ""):
        raise AppError(400, "WRONG_PASSWORD", "Current password is incorrect.")
    if verify_password(user.password_hash, new):
        raise AppError(422, "WEAK_PASSWORD", "New password must be different from the current one.")
    validate_new_password(new, user.email)
    user.password_hash = hash_password(new)
    user.must_change_password = False
    if user.status == "invited":
        user.status = "active"
    revoke_sessions(db, user.id, keep_session_id=sess.id)
    audit.record(db, user.id, "auth.password_change", "user", user.id)
    db.commit()


def _valid_invite(db: Session, token: str) -> tuple[InviteToken, User]:
    invite = db.scalar(select(InviteToken).where(InviteToken.token_hash == token_hash(token)))
    if invite is None or invite.used_at is not None or invite.expires_at <= utcnow():
        raise AppError(400, "INVALID_INVITE", "This invite link is invalid or has expired.")
    user = db.get(User, invite.user_id)
    if user is None or user.status != "invited":
        raise AppError(400, "INVALID_INVITE", "This invite link is invalid or has expired.")
    return invite, user


def invite_info(db: Session, token: str) -> User:
    return _valid_invite(db, token)[1]


def accept_invite(db: Session, token: str, new_password: str, ip: str | None,
                  user_agent: str | None) -> tuple[User, str]:
    invite, user = _valid_invite(db, token)
    validate_new_password(new_password, user.email)
    now = utcnow()
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.status = "active"
    user.last_login_at = now
    # Any other outstanding invites for this user are now void.
    for other in db.scalars(select(InviteToken).where(InviteToken.user_id == user.id,
                                                      InviteToken.used_at.is_(None))):
        other.used_at = now
    session_token = create_session(db, user, ip, user_agent)
    audit.record(db, user.id, "auth.invite_accepted", "user", user.id)
    db.commit()
    return user, session_token
