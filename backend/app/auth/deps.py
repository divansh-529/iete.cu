from collections.abc import Callable
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import UserSession
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import AppError, forbidden
from app.core.security import token_hash
from app.core.time import utcnow
from app.permissions.engine import GLOBAL, Scope, can, has_any
from app.users.models import User

SESSION_COOKIE = "iete_session"
CSRF_COOKIE = "iete_csrf"


def _unauthenticated(code: str = "NOT_AUTHENTICATED") -> AppError:
    return AppError(401, code, "Please log in.")


def load_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _unauthenticated()
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token)))
    now = utcnow()
    if sess is None:
        raise _unauthenticated()
    idle_limit = sess.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if sess.expires_at <= now or idle_limit <= now:
        db.delete(sess)
        db.commit()
        raise _unauthenticated("SESSION_EXPIRED")
    if (now - sess.last_seen_at).total_seconds() > 60:   # avoid a write on every request
        sess.last_seen_at = now
        db.commit()
    return sess


def current_user_any(sess: UserSession = Depends(load_session),
                     db: Session = Depends(get_db)) -> User:
    """Logged-in user, including one who still has to change their password."""
    user = db.get(User, sess.user_id)
    if user is None or user.status not in ("active", "invited"):
        raise _unauthenticated()
    return user


def current_user(user: User = Depends(current_user_any)) -> User:
    if user.must_change_password:
        raise AppError(403, "PASSWORD_CHANGE_REQUIRED", "You must change your password first.")
    return user


def require(permission: str, scope: Callable[[Request], Scope] | None = None):
    """Route dependency: 403 unless the user holds `permission` at the request's scope."""

    def dependency(request: Request, user: User = Depends(current_user),
                   db: Session = Depends(get_db)) -> User:
        if not can(db, user, permission, scope(request) if scope else GLOBAL):
            raise forbidden()
        return user

    dependency.required_permission = permission  # type: ignore[attr-defined]
    return dependency


def require_any(permission: str):
    """Route dependency: 403 unless the user holds `permission` at *some* scope.
    The service must then call `engine.ensure()` with the exact scope of the record."""

    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if not has_any(db, user, permission):
            raise forbidden()
        return user

    dependency.required_permission = permission  # type: ignore[attr-defined]
    return dependency
