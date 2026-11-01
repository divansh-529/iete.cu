"""A small organisation with the real default roles and grants (app.cli.apply_default_grants):
Chairperson (super admin), a Vice Chair holding Leadership, an Operations Lead, an Operations
member, and a Technical member."""
from dataclasses import dataclass

from app.cli import DEFAULT_ROLES, apply_default_grants
from app.org.models import Department, DepartmentMembership, Position, PositionAssignment
from app.permissions.models import Role, RolePermission
from tests.conftest import make_user


@dataclass
class Org:
    chair: object
    vc: object
    ops_lead: object
    ops_member: object
    tech_member: object
    ops: Department
    tech: Department


def build_org(db, chair) -> Org:
    for name, (description, codes) in DEFAULT_ROLES.items():
        role = Role(name=name, description=description)
        db.add(role)
        db.flush()
        db.add_all(RolePermission(role_id=role.id, permission_code=c) for c in codes)
    ops, tech = Department(name="Operations"), Department(name="Technical")
    db.add_all([ops, tech])
    db.flush()
    vc_pos = Position(title="Vice Chairperson", is_lead=True)
    ops_lead_pos = Position(title="Operations Lead", department_id=ops.id, is_lead=True)
    db.add_all([vc_pos, ops_lead_pos])
    db.flush()
    vc, lead = make_user(db, "vc@ietecu.in"), make_user(db, "opslead@ietecu.in")
    member, tech_member = make_user(db, "opsmember@ietecu.in"), make_user(db, "techmember@ietecu.in")
    from datetime import date
    for user, pos in ((vc, vc_pos), (lead, ops_lead_pos)):
        db.add(PositionAssignment(user_id=user.id, position_id=pos.id, valid_from=date.today(),
                                  start_reason="appointed", assigned_by=chair.id))
    for user, dept in ((lead, ops), (member, ops), (tech_member, tech)):
        db.add(DepartmentMembership(user_id=user.id, department_id=dept.id, valid_from=date.today(),
                                    assigned_by=chair.id))
    apply_default_grants(db, chair)
    db.commit()
    return Org(chair, vc, lead, member, tech_member, ops, tech)


def login(make_client, user):
    c = make_client()
    r = c.login(user.email)
    assert r.status_code == 200, r.text
    return c


def notifications(client, kind=None):
    items = client.get("/api/notifications").json()["items"]
    return [n for n in items if kind is None or n["kind"] == kind]
