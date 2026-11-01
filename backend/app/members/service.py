"""Recruitment with approval (Chairperson's requirement, 2026-11-01).

1. A recruiter (org.assign on the department: its Lead, or the Vice Chairperson / Secretary
   everywhere) proposes a candidate. Their account is created as 'proposed' and cannot sign in.
2. An approver (users.approve: the Chairperson, Vice Chairperson or Secretary) approves or rejects
   it. Nobody approves a member they proposed themselves, except the super admin.
3. On approval the account gets the forum's default first password, joins the department (and
   position), and the candidate is emailed. They must change the password at first sign-in.
"""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.config import settings
from app.core.errors import AppError, forbidden, not_found
from app.core.security import hash_password
from app.core.time import utcnow
from app.members.models import MemberProposal
from app.members.schemas import DecisionIn, ProposeMemberIn
from app.notifications.service import notify
from app.org import service as org
from app.org.models import Department, Position
from app.permissions import engine
from app.permissions.engine import can, department_scope, ensure, visible_department_ids
from app.users.models import User
from app.users.service import welcome_email


def propose(db: Session, actor: User, dept_id: int, body: ProposeMemberIn) -> MemberProposal:
    dept = org.get_department(db, dept_id)
    ensure(db, actor, "org.assign", department_scope(db, dept.id))
    if dept.status != "active":
        raise AppError(409, "INVALID_STATE", "This department is archived.")
    if body.position_id is not None:
        pos = org.get_position(db, body.position_id)
        if pos.department_id != dept.id or pos.status != "active":
            raise AppError(422, "VALIDATION_ERROR", f"Choose an active position in {dept.name}.")
        org.ensure_can_staff(db, actor, pos)

    user = db.scalar(select(User).where(User.email == body.email))
    if user is not None and user.status == "proposed":
        raise AppError(409, "ALREADY_PROPOSED", f"{user.full_name} is already waiting for approval.")
    if user is not None and user.status != "rejected":
        raise AppError(409, "EMAIL_TAKEN", "This person already has an account. Use “Add existing” instead.")
    if user is None:
        user = User(email=body.email, user_type="team", created_by=actor.id)
        db.add(user)
    # A previously rejected candidate can be proposed again; the old decision stays on record.
    user.full_name, user.status, user.must_change_password = body.full_name.strip(), "proposed", True
    db.flush()
    p = MemberProposal(user_id=user.id, department_id=dept.id, position_id=body.position_id,
                       note=(body.note or "").strip() or None, proposed_by=actor.id)
    db.add(p)
    db.flush()
    audit.record(db, actor.id, "member.propose", "user", user.id,
                 after={"proposal_id": p.id, "email": user.email, "department_id": dept.id,
                        "position_id": body.position_id})
    notify(db, engine.users_who_can(db, "users.approve", department_scope(db, dept.id), {actor.id}),
           "account.proposed", {"proposal_id": p.id, "name": user.full_name, "department": dept.name,
                                "by": actor.full_name}, actor.id)
    db.commit()
    return p


def _pending(db: Session, actor: User, proposal_id: int) -> MemberProposal:
    p = db.get(MemberProposal, proposal_id)
    if p is None:
        raise not_found("Proposal")
    ensure(db, actor, "users.approve", department_scope(db, p.department_id))
    if p.status != "pending":
        raise AppError(409, "INVALID_STATE", f"This proposal was already {p.status}.")
    if p.proposed_by == actor.id and not actor.is_super_admin:
        raise forbidden("You proposed this member, so someone else has to decide.")
    return p


def _decide(db: Session, actor: User, p: MemberProposal, status: str, remarks: str | None) -> None:
    p.status, p.decided_by, p.decided_at, p.decision_remarks = status, actor.id, utcnow(), remarks


def approve(db: Session, actor: User, proposal_id: int, body: DecisionIn) -> bool:
    """Activate the account and email the candidate. Returns whether the email was sent."""
    p = _pending(db, actor, proposal_id)
    user, dept = db.get(User, p.user_id), db.get(Department, p.department_id)
    if dept.status != "active":
        raise AppError(409, "INVALID_STATE", f"{dept.name} has been archived since this was proposed.")
    pos = db.get(Position, p.position_id) if p.position_id else None
    if pos is not None and pos.status != "active":
        raise AppError(409, "INVALID_STATE", f"The {pos.title} position has been archived. Reject and propose again.")
    user.password_hash = hash_password(settings.default_member_password)
    user.status, user.must_change_password, user.failed_login_count = "invited", True, 0
    org.place_member(db, actor, user, dept, pos)
    remarks = (body.remarks or "").strip() or None
    _decide(db, actor, p, "approved", remarks)
    audit.record(db, actor.id, "member.approve", "user", user.id,
                 after={"proposal_id": p.id, "department_id": dept.id, "remarks": remarks})
    notify(db, [p.proposed_by], "account.approved",
           {"proposal_id": p.id, "name": user.full_name, "department": dept.name, "by": actor.full_name}, actor.id)
    db.commit()
    return send_welcome(db, p)


def send_welcome(db: Session, p: MemberProposal) -> bool:
    user, dept = db.get(User, p.user_id), db.get(Department, p.department_id)
    sent = welcome_email(user, dept.name)
    if sent:
        p.email_sent_at = utcnow()
        audit.record(db, None, "user.welcome_email", "user", user.id, after={"proposal_id": p.id})
        db.commit()
    return sent


def resend(db: Session, actor: User, proposal_id: int) -> bool:
    p = db.get(MemberProposal, proposal_id)
    if p is None:
        raise not_found("Proposal")
    ensure(db, actor, "users.approve", department_scope(db, p.department_id))
    user = db.get(User, p.user_id)
    if p.status != "approved" or user.status != "invited":
        raise AppError(409, "INVALID_STATE", "Only approved members who haven't signed in yet can be emailed again.")
    return send_welcome(db, p)


def reject(db: Session, actor: User, proposal_id: int, body: DecisionIn) -> None:
    p = _pending(db, actor, proposal_id)
    remarks = (body.remarks or "").strip()
    if len(remarks) < 3:
        raise AppError(422, "REMARKS_REQUIRED", "Give a short reason; the proposer will see it.")
    user = db.get(User, p.user_id)
    user.status = "rejected"
    _decide(db, actor, p, "rejected", remarks)
    audit.record(db, actor.id, "member.reject", "user", user.id, after={"proposal_id": p.id, "remarks": remarks})
    notify(db, [p.proposed_by], "account.rejected",
           {"proposal_id": p.id, "name": user.full_name, "remarks": remarks, "by": actor.full_name}, actor.id)
    db.commit()


def list_for(db: Session, user: User, status: str) -> list[MemberProposal]:
    """Approvers see proposals in departments they approve for; everyone sees their own."""
    stmt = select(MemberProposal)
    visible = visible_department_ids(db, user, "users.approve")
    if visible is not None:
        conditions = [MemberProposal.proposed_by == user.id]
        if visible:
            conditions.append(MemberProposal.department_id.in_(visible))
        stmt = stmt.where(or_(*conditions))
    if status == "pending":
        stmt = stmt.where(MemberProposal.status == "pending")
    elif status == "decided":
        stmt = stmt.where(MemberProposal.status != "pending")
    order = MemberProposal.created_at.asc() if status == "pending" else MemberProposal.decided_at.desc()
    return list(db.scalars(stmt.order_by(order, MemberProposal.id.desc()).limit(300)))


def views(db: Session, viewer: User, rows: list[MemberProposal]) -> list[dict]:
    people = org.people_by_id(db, [r.user_id for r in rows] + [r.proposed_by for r in rows]
                              + [r.decided_by for r in rows])
    depts = org.department_names(db, [r.department_id for r in rows])
    position_ids = {r.position_id for r in rows if r.position_id}
    positions = dict(db.execute(select(Position.id, Position.title)
                                .where(Position.id.in_(position_ids))).all()) if position_ids else {}
    statuses = dict(db.execute(select(User.id, User.status)
                               .where(User.id.in_({r.user_id for r in rows}))).all()) if rows else {}
    return [{
        "id": r.id, "person": people[r.user_id], "account_status": statuses[r.user_id],
        "department": {"id": r.department_id, "name": depts[r.department_id]},
        "position": {"id": r.position_id, "name": positions[r.position_id]} if r.position_id else None,
        "note": r.note, "status": r.status, "proposed_by": people[r.proposed_by], "created_at": r.created_at,
        "decided_by": people.get(r.decided_by), "decided_at": r.decided_at, "decision_remarks": r.decision_remarks,
        "email_sent_at": r.email_sent_at,
        "can_decide": r.status == "pending" and (r.proposed_by != viewer.id or viewer.is_super_admin)
                      and can(db, viewer, "users.approve", department_scope(db, r.department_id)),
    } for r in rows]
