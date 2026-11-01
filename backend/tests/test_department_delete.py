"""The Chairperson can delete any department outright, even while it is in use."""
import pytest
from sqlalchemy import select

from app.org.models import Department, Position
from app.permissions.models import Grant
from tests.conftest import grant
from tests.orgsetup import build_org, login


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


def _delete(client, dept, confirm=None, reason="Merged into Treasury"):
    return client.post(f"/api/departments/{dept.id}/delete",
                       json={"reason": reason, "confirm_name": confirm if confirm is not None else dept.name})


def test_chairperson_deletes_a_department_in_use(db, make_client, org):
    chair, lead = login(make_client, org.chair), login(make_client, org.ops_lead)
    sub = Department(name="Ops Logistics", parent_id=org.ops.id)
    db.add(sub)
    db.commit()
    lead.post(f"/api/departments/{org.ops.id}/member-proposals", json={"email": "r@gmail.com", "full_name": "R Recruit"})

    assert _delete(chair, org.ops, confirm="Operationz").json()["error"]["code"] == "CONFIRMATION_MISMATCH"
    r = _delete(chair, org.ops)
    assert r.status_code == 200, r.text
    assert r.json() == {"members_removed": 2, "positions_closed": 1, "grants_revoked": 2,
                        "proposals_declined": 1, "subdepartments_moved": 1}

    # Gone from every list and lookup, and the name is free again
    assert "Operations" not in {d["name"] for d in chair.get("/api/departments?include_archived=true").json()}
    assert chair.get(f"/api/departments/{org.ops.id}").status_code == 404
    assert chair.post(f"/api/departments/{org.ops.id}/restore", json={"reason": "undo"}).status_code == 404
    assert chair.post("/api/departments", json={"name": "Operations"}).status_code == 201

    # The lead lost the access the department gave them, but their history still names it
    assert lead.get(f"/api/departments/{org.tech.id}").status_code == 403
    assert lead.post(f"/api/departments/{org.tech.id}/member-proposals",
                     json={"email": "x@gmail.com", "full_name": "X"}).status_code == 403
    history = chair.get(f"/api/users/{org.ops_lead.id}/org").json()
    assert [(m["department_name"], m["valid_to"] is not None) for m in history["memberships"]] == [("Operations", True)]
    assert history["positions"][0]["end_reason"] == "removed"

    db.expire_all()
    assert db.get(Department, sub.id).parent_id is None                                   # moved up a level
    assert db.scalar(select(Position.status).where(Position.department_id == org.ops.id)) == "archived"
    assert not db.scalars(select(Grant).where(Grant.scope_id == org.ops.id, Grant.revoked_at.is_(None))).all()


def test_only_the_chairperson_can_delete(db, make_client, org, chair):
    grant(db, org.vc, "org.manage", chair)          # even with org.manage everywhere
    vc = login(make_client, org.vc)
    r = _delete(vc, org.tech)
    assert r.status_code == 403 and "Only the Chairperson" in r.json()["error"]["message"]
    assert login(make_client, org.ops_lead).post(f"/api/departments/{org.ops.id}/delete",
                                                 json={"reason": "x" * 5, "confirm_name": "Operations"}).status_code == 403
