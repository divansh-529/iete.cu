import secrets

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth import service
from app.auth.deps import (CSRF_COOKIE, SESSION_COOKIE, current_user_any, load_session)
from app.auth.models import UserSession
from app.auth.schemas import (AcceptInviteIn, ChangePasswordIn, EffectivePermission, InviteInfoOut,
                              LoginIn, MeOut)
from app.core.config import settings
from app.core.db import get_db
from app.core.request_context import request_ip
from app.org.service import profile_complete
from app.permissions.catalogue import CATALOGUE
from app.permissions.engine import effective_grants
from app.users.models import User
from app.users.schemas import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_auth_cookies(response: Response, session_token: str) -> None:
    max_age = settings.session_absolute_days * 86400
    response.set_cookie(SESSION_COOKIE, session_token, max_age=max_age, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(24), max_age=max_age, httponly=False,
                        secure=settings.cookie_secure, samesite="lax", path="/")


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def build_me(db: Session, user: User) -> MeOut:
    if user.is_super_admin:
        perms: list[EffectivePermission] = []
    else:
        seen = set()
        perms = []
        for g in effective_grants(db, user):
            if CATALOGUE[g.permission].sensitive and not g.direct:
                continue
            key = (g.permission, g.scope_type, g.scope_id)
            if key not in seen:
                seen.add(key)
                perms.append(EffectivePermission(code=g.permission, scope_type=g.scope_type,
                                                 scope_id=g.scope_id))
    return MeOut(user=UserOut.model_validate(user), permissions=perms,
                 all_permissions=user.is_super_admin, profile_complete=profile_complete(db, user))


def _client(request: Request) -> tuple[str | None, str | None]:
    return request_ip(request), request.headers.get("user-agent")


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user, token = service.login(db, body.email, body.password, *_client(request))
    _set_auth_cookies(response, token)
    return build_me(db, user)


@router.post("/logout", status_code=204)
def logout(response: Response, sess: UserSession = Depends(load_session),
           db: Session = Depends(get_db)):
    service.logout(db, sess)
    _clear_auth_cookies(response)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user_any), db: Session = Depends(get_db)):
    return build_me(db, user)


@router.post("/change-password", response_model=MeOut)
def change_password(body: ChangePasswordIn, user: User = Depends(current_user_any),
                    sess: UserSession = Depends(load_session), db: Session = Depends(get_db)):
    service.change_password(db, user, sess, body.current_password, body.new_password)
    return build_me(db, user)


@router.get("/invite/{token}", response_model=InviteInfoOut)
def invite_info(token: str, db: Session = Depends(get_db)):
    user = service.invite_info(db, token)
    return InviteInfoOut(email=user.email, full_name=user.full_name)


@router.post("/accept-invite", response_model=MeOut)
def accept_invite(body: AcceptInviteIn, request: Request, response: Response,
                  db: Session = Depends(get_db)):
    user, token = service.accept_invite(db, body.token, body.new_password, *_client(request))
    _set_auth_cookies(response, token)
    return build_me(db, user)
