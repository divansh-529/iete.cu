from datetime import timedelta
from html import escape

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.auth.service import revoke_sessions
from app.core.config import settings
from app.core.errors import AppError, forbidden, not_found
from app.core.mail import send_mail
from app.core.security import hash_password, new_token, token_hash, validate_new_password
from app.core.time import utcnow
from app.users.models import InviteToken, User
from app.users.schemas import UserCreateIn, UserUpdateIn


def _snapshot(user: User) -> dict:
    return {"email": user.email, "full_name": user.full_name, "status": user.status,
            "must_change_password": user.must_change_password}


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.status == "deleted":
        raise not_found("User")
    return user


def _guard_target(actor: User, target: User, allow_self: bool = False) -> None:
    if target.is_super_admin and not actor.is_super_admin:
        raise forbidden("Only the Chairperson can change the Chairperson's account.")
    if not allow_self and target.id == actor.id:
        raise forbidden("You cannot perform this action on your own account.")
    if target.status in ("proposed", "rejected"):
        raise AppError(409, "INVALID_STATE", "This person was proposed by a lead. Approve or reject them on "
                                             "the Approvals page instead.")


def list_users(db: Session, q: str | None, status: str | None, user_type: str | None,
               offset: int, limit: int) -> tuple[list[User], int]:
    stmt = select(User).where(User.status != "deleted")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.full_name.ilike(like)))
    if status:
        stmt = stmt.where(User.status == status)
    if user_type:
        stmt = stmt.where(User.user_type == user_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(User.full_name).offset(offset).limit(limit)).all()
    return list(items), total or 0


def _issue_invite(db: Session, actor: User, user: User) -> str:
    token = new_token()
    db.add(InviteToken(user_id=user.id, token_hash=token_hash(token), created_by=actor.id,
                       expires_at=utcnow() + timedelta(hours=settings.invite_ttl_hours)))
    return f"{settings.frontend_base_url}/accept-invite?token={token}"


def welcome_email(user: User, department: str | None = None) -> bool:
    """Email a new member their sign-in details (the forum's default first password)."""
    login = f"{settings.frontend_base_url}/login"
    where = f" as a member of the {department} department" if department else ""
    text = (f"Hi {user.full_name},\n\n"
            f"Your account on the IETE Student Forum (Chandigarh University) portal is ready{where}.\n\n"
            f"Sign in at: {login}\n"
            f"Email: {user.email}\n"
            f"First-time password: {settings.default_member_password}\n\n"
            "You will be asked to choose your own password as soon as you sign in. Please do it straight "
            "away and don't share it with anyone.\n\n"
            "— IETE Student Forum, Chandigarh University")
    html = (f"<p>Hi {escape(user.full_name)},</p>"
            f"<p>Your account on the <strong>IETE Student Forum</strong> (Chandigarh University) portal is "
            f"ready{escape(where)}.</p>"
            f"<p><a href=\"{escape(login)}\">Sign in to the portal</a><br>Email: {escape(user.email)}<br>"
            f"First-time password: <code>{escape(settings.default_member_password)}</code></p>"
            "<p>You will be asked to choose your own password as soon as you sign in. Please do it "
            "straight away and don't share it with anyone.</p><p>— IETE Student Forum, Chandigarh University</p>")
    return send_mail(user.email, "Your IETE Student Forum portal account is ready", text, html)


def create_user(db: Session, actor: User, body: UserCreateIn) -> tuple[User, str | None, bool]:
    user, invite_url = add_user(db, actor, body)
    db.commit()
    emailed = body.credential == "default_password" and welcome_email(user)
    if emailed:
        audit.record(db, actor.id, "user.welcome_email", "user", user.id)
        db.commit()
    return user, invite_url, emailed


def add_user(db: Session, actor: User, body: UserCreateIn) -> tuple[User, str | None]:
    """Create the account without committing, so callers can add more in the same transaction."""
    user = User(email=body.email, full_name=body.full_name.strip(), user_type="team",
                status="invited", must_change_password=True, created_by=actor.id)
    if body.credential == "default_password":
        user.password_hash = hash_password(settings.default_member_password)
    elif body.credential == "temp_password":
        if not body.temp_password:
            raise AppError(422, "VALIDATION_ERROR", "A temporary password is required.")
        validate_new_password(body.temp_password, body.email)
        user.password_hash = hash_password(body.temp_password)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists.")
    invite_url = _issue_invite(db, actor, user) if body.credential == "invite" else None
    audit.record(db, actor.id, "user.create", "user", user.id,
                 after={**_snapshot(user), "credential": body.credential})
    return user, invite_url


def update_user(db: Session, actor: User, user_id: int, body: UserUpdateIn) -> User:
    user = get_user(db, user_id)
    _guard_target(actor, user, allow_self=True)
    before = _snapshot(user)
    if body.email is not None:
        user.email = body.email
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists.")
    audit.record(db, actor.id, "user.update", "user", user.id, before=before, after=_snapshot(user))
    db.commit()
    return user


def change_status(db: Session, actor: User, user_id: int, action: str, reason: str) -> User:
    user = get_user(db, user_id)
    _guard_target(actor, user)
    before = _snapshot(user)
    if action == "suspend":
        if user.status == "deactivated":
            raise AppError(409, "INVALID_STATE", "A deactivated account cannot be suspended.")
        user.status = "suspended"
    elif action == "deactivate":
        user.status = "deactivated"
    elif action == "reactivate":
        if user.status not in ("suspended", "deactivated"):
            raise AppError(409, "INVALID_STATE", "Only suspended or deactivated accounts can be reactivated.")
        user.status = "active" if user.password_hash and not user.must_change_password else "invited"
    if user.status in ("suspended", "deactivated"):
        revoke_sessions(db, user.id)
    audit.record(db, actor.id, f"user.{action}", "user", user.id, before=before,
                 after={**_snapshot(user), "reason": reason})
    db.commit()
    return user


def delete_user(db: Session, actor: User, user_id: int, reason: str, confirm_email: str) -> dict:
    """The Chairperson removes an account for good. The person can no longer sign in and loses their
    positions, departments, access and open work. The row stays as 'deleted' so past events, tasks and
    the audit log still name them, and their email and University ID can be used again."""
    from app.events.models import Event, EventTeamMember
    from app.members.models import MemberProposal
    from app.org.models import DepartmentMembership, MemberProfile, PositionAssignment
    from app.org.service import _close_assignment
    from app.permissions import engine
    from app.permissions.models import Grant, PermissionAudit
    from app.scores.models import ScoreCard, ScoreEntry, ScoreRound
    from app.tasks.models import Task, TaskAssignee

    if not actor.is_super_admin:
        raise forbidden("Only the Chairperson can delete an account.")
    user = get_user(db, user_id)
    if user.is_super_admin or user.id == actor.id:
        raise forbidden("The Chairperson's account can't be deleted.")
    if confirm_email.strip().lower() != user.email.lower():
        raise AppError(422, "CONFIRMATION_MISMATCH", f"Type the account's email, “{user.email}”, to confirm.")
    now, today = utcnow(), utcnow().date()
    before = _snapshot(user)

    assignments = db.scalars(select(PositionAssignment).where(PositionAssignment.user_id == user.id,
                                                              PositionAssignment.valid_to.is_(None))).all()
    for pa in assignments:
        _close_assignment(db, actor, pa, max(today, pa.valid_from), "removed", "Account deleted")
    memberships = db.scalars(select(DepartmentMembership).where(DepartmentMembership.user_id == user.id,
                                                                DepartmentMembership.valid_to.is_(None))).all()
    for m in memberships:
        m.valid_to, m.end_reason, m.ended_by = max(today, m.valid_from), "Account deleted", actor.id
    grants = db.scalars(select(Grant).where(Grant.revoked_at.is_(None), Grant.subject_type == "user",
                                            Grant.subject_id == user.id)).all()
    for g in grants:
        g.revoked_at, g.revoked_by = now, actor.id
        db.add(PermissionAudit(actor_id=actor.id, action="revoke", subject_type=g.subject_type,
                               subject_id=g.subject_id, permission_code=g.permission_code, role_id=g.role_id,
                               scope_type=g.scope_type, scope_id=g.scope_id, old_value={"grant_id": g.id},
                               reason=f"Account deleted: {reason}"))
    # Open work goes back to whoever runs it; finished work keeps their name.
    finished = ("completed", "rejected")
    unassigned = db.scalars(select(TaskAssignee).join(Task, Task.id == TaskAssignee.task_id).where(
        TaskAssignee.user_id == user.id, TaskAssignee.unassigned_at.is_(None), Task.status.not_in(finished))).all()
    for a in unassigned:
        a.unassigned_at = now
    for task in db.scalars(select(Task).where(Task.reviewer_id == user.id, Task.status.not_in(finished))):
        task.reviewer_id = None
    for t in db.scalars(select(EventTeamMember).where(EventTeamMember.user_id == user.id,
                                                      EventTeamMember.removed_at.is_(None))):
        t.removed_at, t.removed_by = now, actor.id
    for p in db.scalars(select(MemberProposal).where(MemberProposal.user_id == user.id, MemberProposal.status == "pending")):
        p.status, p.decided_by, p.decided_at, p.decision_remarks = "rejected", actor.id, now, "Account deleted"
    # A round still being scored no longer expects a card for them.
    open_cards = list(db.scalars(select(ScoreCard.id).join(ScoreRound, ScoreRound.id == ScoreCard.round_id).where(
        ScoreCard.user_id == user.id, ScoreRound.status == "open")))
    if open_cards:
        db.execute(delete(ScoreEntry).where(ScoreEntry.card_id.in_(open_cards)))
        db.execute(delete(ScoreCard).where(ScoreCard.id.in_(open_cards)))
    profile = db.get(MemberProfile, user.id)
    uid = profile.uid if profile else None
    if profile:
        profile.uid = None

    revoke_sessions(db, user.id)
    user.status = "deleted"
    summary = {"positions_ended": len(assignments), "memberships_ended": len(memberships), "grants_revoked": len(grants),
               "tasks_unassigned": len(unassigned),
               "events_still_owned": db.scalar(select(func.count()).select_from(Event).where(
                   Event.owner_id == user.id, Event.status.not_in(("completed", "cancelled", "archived")))) or 0}
    audit.record(db, actor.id, "user.delete", "user", user.id, before={**before, "uid": uid},
                 after={"status": "deleted", "reason": reason, **summary})
    engine.clear_cache(db)
    db.commit()
    return summary


def reset_password(db: Session, actor: User, user_id: int, temp_password: str) -> User:
    user = get_user(db, user_id)
    _guard_target(actor, user)
    validate_new_password(temp_password, user.email)
    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    revoke_sessions(db, user.id)
    audit.record(db, actor.id, "user.reset_password", "user", user.id)  # password never logged
    db.commit()
    return user


def reissue_invite(db: Session, actor: User, user_id: int) -> str:
    user = get_user(db, user_id)
    _guard_target(actor, user)
    if user.status != "invited":
        raise AppError(409, "INVALID_STATE", "Invites can only be issued to accounts that are still invited.")
    url = _issue_invite(db, actor, user)
    audit.record(db, actor.id, "user.invite_issued", "user", user.id)
    db.commit()
    return url
