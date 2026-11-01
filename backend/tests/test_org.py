from sqlalchemy import select

from app.cli import DEFAULT_ROLES
from app.org.models import PositionAssignment
from app.users.models import User
from tests.conftest import grant, make_user
from tests.test_permissions import _grant


def _dept(client, name, parent_id=None):
    r = client.post("/api/departments", json={"name": name, "parent_id": parent_id})
    assert r.status_code == 201, r.text
    return r.json()


def _pos(client, title, department_id=None, **extra):
    r = client.post("/api/positions", json={"title": title, "department_id": department_id, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client, position_id, user_id, **extra):
    return client.post(f"/api/positions/{position_id}/assign", json={"user_id": user_id, **extra})


def test_department_and_position_lifecycle(client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    ops = _dept(client, "Operations")
    assert client.post("/api/departments", json={"name": "operations"}).status_code == 409

    lead = _pos(client, "Operations Lead", ops["id"], is_lead=True)
    r = _assign(client, lead["id"], member.id)
    assert r.status_code == 201

    detail = client.get(f"/api/departments/{ops['id']}").json()
    assert detail["member_count"] == 1                       # assignment auto-adds membership
    assert detail["leads"][0]["id"] == member.id
    assert detail["vacant_positions"] == 0

    # Cannot archive while people are in it
    assert client.post(f"/api/departments/{ops['id']}/archive",
                       json={"reason": "merge"}).status_code == 409


def test_position_capacity_and_duplicate_holder(client, chair, db):
    a, b = make_user(db, "a@ietecu.in"), make_user(db, "b@ietecu.in")
    client.login("chair@ietecu.in")
    pos = _pos(client, "Secretary")
    assert _assign(client, pos["id"], a.id).status_code == 201
    assert _assign(client, pos["id"], a.id).status_code == 409
    r = _assign(client, pos["id"], b.id)
    assert r.status_code == 409 and r.json()["error"]["code"] == "POSITION_FULL"


def test_reporting_line_cycle_rejected(client, chair):
    client.login("chair@ietecu.in")
    top = _pos(client, "Chairperson")
    mid = _pos(client, "Vice Chairperson", reports_to_position_id=top["id"])
    r = client.put(f"/api/positions/{top['id']}", json={"title": "Chairperson",
                                                         "reports_to_position_id": mid["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "CYCLE"


def test_position_grant_follows_the_holder(client, make_client, chair, db):
    """Access granted to a position moves with whoever holds it; history is kept."""
    old, new = make_user(db, "old@ietecu.in"), make_user(db, "new@ietecu.in")
    client.login("chair@ietecu.in")
    pos = _pos(client, "Secretary")
    assert _grant(client, pos["id"], "users.view", subject_type="position").status_code == 201
    assignment = _assign(client, pos["id"], old.id).json()

    old_client = make_client()
    old_client.login("old@ietecu.in")
    assert old_client.get("/api/users").status_code == 200

    r = client.post(f"/api/position-assignments/{assignment['id']}/end", json={"end_reason": "term_ended"})
    assert r.status_code == 200
    assert old_client.get("/api/users").status_code == 403    # access gone immediately

    _assign(client, pos["id"], new.id)
    new_client = make_client()
    new_client.login("new@ietecu.in")
    assert new_client.get("/api/users").status_code == 200

    history = client.get(f"/api/positions/{pos['id']}/history").json()
    assert [h["user"]["email"] for h in history] == ["new@ietecu.in", "old@ietecu.in"]
    assert history[1]["end_reason"] == "term_ended"


def test_department_grant_reaches_members(client, make_client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    dept = _dept(client, "Graphics")
    _grant(client, dept["id"], "users.view", subject_type="department")
    client.post(f"/api/departments/{dept['id']}/members", json={"user_id": member.id})
    member_client = make_client()
    member_client.login("m@ietecu.in")
    assert member_client.get("/api/users").status_code == 200


def test_sensitive_permission_cannot_go_to_position(client, chair):
    client.login("chair@ietecu.in")
    pos = _pos(client, "Treasurer")
    r = _grant(client, pos["id"], "finance.view", subject_type="position")
    assert r.status_code == 422 and r.json()["error"]["code"] == "SENSITIVE_NEEDS_PERSON"


def test_cannot_grant_to_own_position(client, chair, db):
    admin = make_user(db, "admin@ietecu.in")
    grant(db, admin, "permissions.manage", chair)
    grant(db, admin, "users.view", chair)
    client.login("chair@ietecu.in")
    pos = _pos(client, "Secretary")
    _assign(client, pos["id"], admin.id)

    admin_client = client.__class__(client.app)
    admin_client.login("admin@ietecu.in")
    r = _grant(admin_client, pos["id"], "users.view", subject_type="position")
    assert r.status_code == 403


def test_department_scoped_lead(client, make_client, chair, db):
    """A Lead with org.assign scoped to their department can staff it, but not other departments."""
    lead, member = make_user(db, "lead@ietecu.in"), make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    ops = _dept(client, "Operations")
    tech = _dept(client, "Technical")
    sub = _dept(client, "Ops Logistics", parent_id=ops["id"])
    lead_pos = _pos(client, "Operations Lead", ops["id"], is_lead=True)
    for code in ("org.view", "org.assign"):
        r = _grant(client, lead_pos["id"], code, subject_type="position",
                   scope_type="department", scope_id=ops["id"])
        assert r.status_code == 201, r.text
    _assign(client, lead_pos["id"], lead.id)

    lead_client = make_client()
    lead_client.login("lead@ietecu.in")
    assert lead_client.post(f"/api/departments/{ops['id']}/members", json={"user_id": member.id}).status_code == 201
    assert lead_client.post(f"/api/departments/{sub['id']}/members", json={"user_id": member.id}).status_code == 201
    assert lead_client.post(f"/api/departments/{tech['id']}/members", json={"user_id": member.id}).status_code == 403
    visible = {d["name"] for d in lead_client.get("/api/departments").json()}
    assert visible == {"Operations", "Ops Logistics"}
    assert lead_client.get(f"/api/departments/{tech['id']}").status_code == 403


def test_default_lead_role_can_add_members(client, make_client, chair, db):
    """The seeded Department Lead role, granted to a Lead position, lets its holder add team members."""
    lead, member = make_user(db, "lead@ietecu.in"), make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    ops = _dept(client, "Operations")
    tech = _dept(client, "Technical")
    role = client.post("/api/roles", json={"name": "Department Lead", "reason": "test",
                                           "permissions": DEFAULT_ROLES["Department Lead"][1]}).json()
    lead_pos = _pos(client, "Operations Lead", ops["id"], is_lead=True)
    r = _grant(client, lead_pos["id"], role_id=role["id"], subject_type="position",
               scope_type="department", scope_id=ops["id"])
    assert r.status_code == 201, r.text
    _assign(client, lead_pos["id"], lead.id)

    lead_client = make_client()
    lead_client.login("lead@ietecu.in")
    assert lead_client.get("/api/org/people").status_code == 200       # the add-member picker
    assert lead_client.post(f"/api/departments/{ops['id']}/members", json={"user_id": member.id}).status_code == 201
    assert lead_client.post(f"/api/departments/{tech['id']}/members", json={"user_id": member.id}).status_code == 403


def test_lead_cannot_make_another_lead(client, make_client, chair, db):
    """Leads staff their team with ordinary members only; lead and deputy seats are for admins."""
    lead, member, co_lead = (make_user(db, e) for e in ("lead@ietecu.in", "m@ietecu.in", "co@ietecu.in"))
    client.login("chair@ietecu.in")
    ops = _dept(client, "Operations")
    lead_pos = _pos(client, "Operations Lead", ops["id"], is_lead=True, max_holders=3)
    deputy = _pos(client, "Operations Deputy", ops["id"], is_deputy=True)
    crew = _pos(client, "Operations Crew", ops["id"], max_holders=5)
    _grant(client, lead_pos["id"], "org.assign", subject_type="position", scope_type="department", scope_id=ops["id"])
    _assign(client, lead_pos["id"], lead.id)
    co_assignment = _assign(client, lead_pos["id"], co_lead.id).json()

    lead_client = make_client()
    lead_client.login("lead@ietecu.in")
    new = {"full_name": "New Recruit"}
    for seat in (lead_pos, deputy):
        r = lead_client.post(f"/api/departments/{ops['id']}/member-proposals",
                             json={**new, "email": "x@ietecu.in", "position_id": seat["id"]})
        assert r.status_code == 403, r.text
        assert _assign(lead_client, seat["id"], member.id).status_code == 403
    assert db.scalar(select(User.id).where(User.email == "x@ietecu.in")) is None

    # A normal member is fine, but cannot then be promoted into a lead seat by the lead
    r = _assign(lead_client, crew["id"], member.id)
    assert r.status_code == 201
    r = lead_client.post(f"/api/position-assignments/{r.json()['id']}/transfer",
                         json={"to_position_id": lead_pos["id"], "reason": "promoted"})
    assert r.status_code == 403
    # Nor can a lead remove the other lead
    r = lead_client.post(f"/api/position-assignments/{co_assignment['id']}/end", json={"end_reason": "removed"})
    assert r.status_code == 403

    # An administrator still can
    assert _assign(client, deputy["id"], member.id).status_code == 201


def test_transfer_keeps_history(client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    ops = _dept(client, "Operations")
    member_pos = _pos(client, "Operations Coordinator", ops["id"], max_holders=10)
    lead_pos = _pos(client, "Operations Lead", ops["id"], is_lead=True)
    a = _assign(client, member_pos["id"], member.id).json()
    r = client.post(f"/api/position-assignments/{a['id']}/transfer",
                    json={"to_position_id": lead_pos["id"], "reason": "promoted"})
    assert r.status_code == 200 and r.json()["start_reason"] == "promoted"

    org = client.get(f"/api/users/{member.id}/org").json()
    assert [(p["position_title"], p["valid_to"] is None) for p in org["positions"]] == [
        ("Operations Lead", True), ("Operations Coordinator", False)]
    assert db.scalar(select(PositionAssignment.end_reason).where(PositionAssignment.id == a["id"])) == "promoted"


def test_remove_member_blocked_while_holding_position(client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    ops = _dept(client, "Operations")
    pos = _pos(client, "Operations Lead", ops["id"])
    _assign(client, pos["id"], member.id)
    membership = client.get(f"/api/departments/{ops['id']}").json()["members"][0]
    r = client.post(f"/api/department-memberships/{membership['id']}/end", json={"reason": "left"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "HOLDS_POSITION"


def test_chart_shows_vacancies(client, chair, db):
    client.login("chair@ietecu.in")
    top = _pos(client, "Chairperson")
    _pos(client, "Vice Chairperson", reports_to_position_id=top["id"])
    _assign(client, top["id"], chair.id)
    nodes = {n["title"]: n for n in client.get("/api/org/chart").json()}
    assert nodes["Chairperson"]["holders"][0]["id"] == chair.id
    assert nodes["Vice Chairperson"]["holders"] == []
    assert nodes["Vice Chairperson"]["reports_to_position_id"] == top["id"]


def test_profiles(client, make_client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    r = client.put(f"/api/users/{member.id}/profile",
                   json={"uid": "23BCS10001", "lifecycle_status": "probation", "year_of_study": 2})
    assert r.status_code == 200 and r.json()["lifecycle_status"] == "probation"

    member_client = make_client()
    member_client.login("m@ietecu.in")
    r = member_client.put("/api/me/profile", json={"phone": "9876543210"})
    assert r.status_code == 200 and r.json()["phone"] == "9876543210"
    assert r.json()["uid"] == "23BCS10001"
    # Members cannot change their own lifecycle status through the self-service route
    r = member_client.put("/api/me/profile", json={"lifecycle_status": "active"})
    assert r.status_code == 200 and r.json()["lifecycle_status"] == "probation"
    assert member_client.put(f"/api/users/{member.id}/profile", json={"uid": "X"}).status_code == 403


def test_terms_single_current(client, chair):
    client.login("chair@ietecu.in")
    a = client.post("/api/terms", json={"name": "2025-26", "starts_on": "2025-07-01",
                                        "ends_on": "2026-06-30", "is_current": True}).json()
    client.post("/api/terms", json={"name": "2026-27", "starts_on": "2026-07-01",
                                    "ends_on": "2027-06-30", "is_current": True})
    terms = {t["name"]: t["is_current"] for t in client.get("/api/terms").json()}
    assert terms == {"2025-26": False, "2026-27": True}
    assert a["is_current"] is True


def test_profile_must_be_completed_after_first_sign_in(client, chair):
    client.login("chair@ietecu.in")
    assert client.get("/api/auth/me").json()["profile_complete"] is False
    # Saving part of the form does not count, and blanks are stored as empty.
    r = client.put("/api/me/profile", json={"uid": "22BCS1", "phone": "  ", "branch": "CSE", "year_of_study": 3,
                                            "official_email": "a@cumail.in", "block": " c2 "})
    assert r.status_code == 200 and r.json()["phone"] is None and r.json()["block"] == "C2"
    assert client.get("/api/auth/me").json()["profile_complete"] is False
    # The IETE membership ID is optional.
    r = client.put("/api/me/profile", json={"phone": "9876543210"})
    assert r.status_code == 200 and r.json()["iete_membership_id"] is None
    assert client.get("/api/auth/me").json()["profile_complete"] is True
    r = client.put("/api/me/profile", json={"iete_membership_id": "ST-1234"})
    assert r.json()["iete_membership_id"] == "ST-1234"
    assert client.get("/api/auth/me").json()["profile_complete"] is True
    assert client.put("/api/me/profile", json={"official_email": "not-an-email"}).status_code == 422
    # Official email and block are required.
    assert client.put("/api/me/profile", json={"block": ""}).json()["block"] is None
    assert client.get("/api/auth/me").json()["profile_complete"] is False
