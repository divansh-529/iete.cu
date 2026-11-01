from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require, require_any, require_any_of
from app.core.db import get_db
from app.org import service
from app.org.models import Term
from app.org.schemas import (AssignIn, AssignmentOut, ChartNode, DepartmentDetailOut, DepartmentIn,
                             DepartmentOut, EndAssignmentIn, EndMembershipIn, MemberIn, MembershipOut,
                             NewMemberIn, NewMemberOut, PersonRef, PositionIn, PositionOut, ProfileIn, ProfileOut,
                             ReasonIn, SelfProfileIn, TermIn, TermOut, TransferIn, UserOrgOut)
from app.permissions.engine import department_scope, ensure, visible_department_ids
from app.users.models import User
from app.users.schemas import UserOut

router = APIRouter(prefix="/api", tags=["organisation"])


# ---------------------------------------------------------------- chart & people

@router.get("/org/chart", response_model=list[ChartNode])
def org_chart(user: User = Depends(require_any("org.view")), db: Session = Depends(get_db)):
    return service.chart(db, visible_department_ids(db, user, "org.view"))


@router.get("/org/people", response_model=list[PersonRef])
def org_people(q: str | None = None, limit: int = Query(20, ge=1, le=100),
               _: User = Depends(require_any_of("org.assign", "tasks.assign", "events.create", "events.edit")),
               db: Session = Depends(get_db)):
    """Minimal people search for pickers: staffing departments, event teams and task assignees.
    Returns names and emails only (does not require users.view)."""
    return [{"id": u.id, "full_name": u.full_name, "email": u.email} for u in service.people(db, q, limit)]


# ---------------------------------------------------------------- departments

@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(include_archived: bool = False, user: User = Depends(require_any("org.view")),
                     db: Session = Depends(get_db)):
    return service.department_summaries(db, visible_department_ids(db, user, "org.view"), include_archived)


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(body: DepartmentIn, actor: User = Depends(require_any("org.manage")),
                      db: Session = Depends(get_db)):
    dept = service.create_department(db, actor, body)
    return service.department_summaries(db, {dept.id}, True)[0]


@router.get("/departments/{dept_id}", response_model=DepartmentDetailOut)
def get_department(dept_id: int, user: User = Depends(require_any("org.view")),
                   db: Session = Depends(get_db)):
    dept = service.get_department(db, dept_id)
    ensure(db, user, "org.view", department_scope(db, dept.id))
    summary = service.department_summaries(db, {dept.id}, True)[0]
    positions = service.list_positions(db, None, dept.id, False, False)
    return {**summary, "created_at": dept.created_at,
            "positions": service.position_views(db, positions),
            "members": service.membership_views(db, service.department_members(db, dept.id))}


@router.put("/departments/{dept_id}", response_model=DepartmentOut)
def update_department(dept_id: int, body: DepartmentIn, actor: User = Depends(require_any("org.manage")),
                      db: Session = Depends(get_db)):
    service.update_department(db, actor, dept_id, body)
    return service.department_summaries(db, {dept_id}, True)[0]


@router.post("/departments/{dept_id}/archive", response_model=DepartmentOut)
def archive_department(dept_id: int, body: ReasonIn, actor: User = Depends(require_any("org.manage")),
                       db: Session = Depends(get_db)):
    service.set_department_status(db, actor, dept_id, True, body.reason)
    return service.department_summaries(db, {dept_id}, True)[0]


@router.post("/departments/{dept_id}/restore", response_model=DepartmentOut)
def restore_department(dept_id: int, body: ReasonIn, actor: User = Depends(require_any("org.manage")),
                       db: Session = Depends(get_db)):
    service.set_department_status(db, actor, dept_id, False, body.reason)
    return service.department_summaries(db, {dept_id}, True)[0]


@router.post("/departments/{dept_id}/members", response_model=MembershipOut, status_code=201)
def add_member(dept_id: int, body: MemberIn, actor: User = Depends(require_any("org.assign")),
               db: Session = Depends(get_db)):
    return service.membership_views(db, [service.add_member(db, actor, dept_id, body)])[0]


@router.post("/departments/{dept_id}/new-member", response_model=NewMemberOut, status_code=201)
def create_member(dept_id: int, body: NewMemberIn, actor: User = Depends(require_any("org.assign")),
                  db: Session = Depends(get_db)):
    user, invite_url, membership = service.create_member(db, actor, dept_id, body)
    return {"user": UserOut.model_validate(user), "invite_url": invite_url,
            "membership": service.membership_views(db, [membership])[0]}


@router.post("/department-memberships/{membership_id}/end", response_model=MembershipOut)
def end_membership(membership_id: int, body: EndMembershipIn,
                   actor: User = Depends(require_any("org.assign")), db: Session = Depends(get_db)):
    return service.membership_views(db, [service.end_membership(db, actor, membership_id, body.reason)])[0]


# ---------------------------------------------------------------- positions

@router.get("/positions", response_model=list[PositionOut])
def list_positions(department_id: int | None = None, leadership: bool = False,
                   include_archived: bool = False, user: User = Depends(require_any("org.view")),
                   db: Session = Depends(get_db)):
    visible = visible_department_ids(db, user, "org.view")
    positions = service.list_positions(db, visible, department_id, leadership, include_archived)
    return service.position_views(db, positions)


@router.post("/positions", response_model=PositionOut, status_code=201)
def create_position(body: PositionIn, actor: User = Depends(require_any("org.manage")),
                    db: Session = Depends(get_db)):
    return service.position_views(db, [service.create_position(db, actor, body)])[0]


@router.get("/positions/{position_id}", response_model=PositionOut)
def get_position(position_id: int, user: User = Depends(require_any("org.view")),
                 db: Session = Depends(get_db)):
    pos = service.get_position(db, position_id)
    ensure(db, user, "org.view", department_scope(db, pos.department_id))
    return service.position_views(db, [pos])[0]


@router.get("/positions/{position_id}/history", response_model=list[AssignmentOut])
def position_history(position_id: int, user: User = Depends(require_any("org.view")),
                     db: Session = Depends(get_db)):
    pos = service.get_position(db, position_id)
    ensure(db, user, "org.view", department_scope(db, pos.department_id))
    return service.assignment_views(db, service.position_history(db, position_id))


@router.put("/positions/{position_id}", response_model=PositionOut)
def update_position(position_id: int, body: PositionIn, actor: User = Depends(require_any("org.manage")),
                    db: Session = Depends(get_db)):
    return service.position_views(db, [service.update_position(db, actor, position_id, body)])[0]


@router.post("/positions/{position_id}/archive", response_model=PositionOut)
def archive_position(position_id: int, body: ReasonIn, actor: User = Depends(require_any("org.manage")),
                     db: Session = Depends(get_db)):
    return service.position_views(db, [service.set_position_status(db, actor, position_id, True, body.reason)])[0]


@router.post("/positions/{position_id}/restore", response_model=PositionOut)
def restore_position(position_id: int, body: ReasonIn, actor: User = Depends(require_any("org.manage")),
                     db: Session = Depends(get_db)):
    return service.position_views(db, [service.set_position_status(db, actor, position_id, False, body.reason)])[0]


@router.post("/positions/{position_id}/assign", response_model=AssignmentOut, status_code=201)
def assign(position_id: int, body: AssignIn, actor: User = Depends(require_any("org.assign")),
           db: Session = Depends(get_db)):
    return service.assignment_views(db, [service.assign(db, actor, position_id, body)])[0]


@router.post("/position-assignments/{assignment_id}/end", response_model=AssignmentOut)
def end_assignment(assignment_id: int, body: EndAssignmentIn,
                   actor: User = Depends(require_any("org.assign")), db: Session = Depends(get_db)):
    return service.assignment_views(db, [service.end_assignment(db, actor, assignment_id, body)])[0]


@router.post("/position-assignments/{assignment_id}/transfer", response_model=AssignmentOut)
def transfer(assignment_id: int, body: TransferIn, actor: User = Depends(require_any("org.assign")),
             db: Session = Depends(get_db)):
    return service.assignment_views(db, [service.transfer(db, actor, assignment_id, body)])[0]


# ---------------------------------------------------------------- people

@router.get("/users/{user_id}/org", response_model=UserOrgOut)
def user_org(user_id: int, _: User = Depends(require_any("org.view")), db: Session = Depends(get_db)):
    return service.user_org(db, user_id)


@router.put("/users/{user_id}/profile", response_model=ProfileOut)
def update_profile(user_id: int, body: ProfileIn, actor: User = Depends(require("users.edit")),
                   db: Session = Depends(get_db)):
    return service.update_profile(db, actor, user_id, body)


@router.get("/me/org", response_model=UserOrgOut)
def my_org(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return service.user_org(db, user.id)


@router.put("/me/profile", response_model=ProfileOut)
def update_my_profile(body: SelfProfileIn, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    return service.update_profile(db, user, user.id, body)


# ---------------------------------------------------------------- terms

@router.get("/terms", response_model=list[TermOut])
def list_terms(_: User = Depends(require_any("org.view")), db: Session = Depends(get_db)):
    return db.scalars(select(Term).order_by(Term.starts_on.desc())).all()


@router.post("/terms", response_model=TermOut, status_code=201)
def create_term(body: TermIn, actor: User = Depends(require("org.manage")), db: Session = Depends(get_db)):
    return service.save_term(db, actor, body)


@router.put("/terms/{term_id}", response_model=TermOut)
def update_term(term_id: int, body: TermIn, actor: User = Depends(require("org.manage")),
                db: Session = Depends(get_db)):
    return service.save_term(db, actor, body, term_id)
