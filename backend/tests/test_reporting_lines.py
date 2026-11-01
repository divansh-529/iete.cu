"""The Chairperson adds and deletes leads and categories in the reporting lines."""
import pytest
from sqlalchemy import select

from app.org.models import Position
from app.permissions.models import Grant
from tests.conftest import make_user
from tests.orgsetup import build_org, login


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


def _delete(client, position_id, title, reason="Restructure"):
    return client.post(f"/api/positions/{position_id}/delete", json={"reason": reason, "confirm_title": title})


def _chart(client):
    return {n["title"]: n for n in client.get("/api/org/chart").json()}


def test_category_groups_positions_and_cannot_be_held(make_client, org, db):
    chair = login(make_client, org.chair)
    r = chair.post("/api/positions", json={"title": "Core Team", "is_category": True})
    assert r.status_code == 201, r.text
    category = r.json()
    assert category["is_category"] is True
    r = chair.post(f"/api/positions/{category['id']}/assign", json={"user_id": org.ops_member.id})
    assert r.json()["error"]["code"] == "IS_CATEGORY"
    r = chair.post("/api/positions", json={"title": "Bad", "is_category": True, "is_lead": True})
    assert r.json()["error"]["code"] == "INVALID_CATEGORY"

    r = chair.post("/api/positions", json={"title": "Web Lead", "is_lead": True, "department_id": org.tech.id,
                                           "reports_to_position_id": category["id"]})
    assert r.status_code == 201, r.text
    chart = _chart(chair)
    assert chart["Core Team"]["is_category"] is True
    assert chart["Web Lead"]["reports_to_position_id"] == category["id"]


def test_a_new_lead_gets_lead_access_in_that_department(make_client, org, db):
    chair = login(make_client, org.chair)
    lead = chair.post("/api/positions", json={"title": "Web Lead", "is_lead": True, "department_id": org.tech.id}).json()
    person = make_user(db, "newlead@ietecu.in")
    r = chair.post(f"/api/positions/{lead['id']}/assign", json={"user_id": person.id})
    assert r.status_code == 201, r.text
    client = login(make_client, person)
    assert client.get(f"/api/departments/{org.tech.id}").status_code == 200
    # Deleting the lead ends that access at once.
    assert _delete(chair, lead["id"], "Web Lead").status_code == 200
    assert client.post(f"/api/departments/{org.tech.id}/member-proposals",
                       json={"email": "x@gmail.com", "full_name": "X"}).status_code == 403


def test_chairperson_deletes_a_held_lead(make_client, org, db):
    chair, lead = login(make_client, org.chair), login(make_client, org.ops_lead)
    position = chair.get("/api/positions", params={"department_id": org.ops.id}).json()[0]
    below = chair.post("/api/positions", json={"title": "Ops Helper", "department_id": org.ops.id,
                                               "reports_to_position_id": position["id"]}).json()

    assert _delete(chair, position["id"], "Wrong title").json()["error"]["code"] == "CONFIRMATION_MISMATCH"
    r = _delete(chair, position["id"], position["title"])
    assert r.status_code == 200, r.text
    assert r.json() == {"holders_removed": 1, "grants_revoked": 1, "reports_moved": 1}

    # Gone everywhere, including archived lists and lookups.
    assert position["title"] not in _chart(chair)
    assert chair.get(f"/api/positions/{position['id']}").status_code == 404
    assert position["id"] not in {p["id"] for p in chair.get("/api/positions", params={"include_archived": True}).json()}
    assert chair.post(f"/api/positions/{position['id']}/restore", json={"reason": "undo"}).status_code == 404
    # Whoever reported to it moves one level up, and history still names it.
    assert _chart(chair)["Ops Helper"]["reports_to_position_id"] == position["reports_to_position_id"]
    history = chair.get(f"/api/users/{org.ops_lead.id}/org").json()["positions"]
    assert history[0]["position_title"] == position["title"] and history[0]["end_reason"] == "removed"
    db.expire_all()
    assert not db.scalars(select(Grant).where(Grant.subject_type == "position", Grant.subject_id == position["id"],
                                              Grant.revoked_at.is_(None))).all()
    assert lead.post(f"/api/departments/{org.ops.id}/member-proposals",
                     json={"email": "y@gmail.com", "full_name": "Y"}).status_code == 403

    # Deleting the department later does not bring the position back.
    r = chair.post(f"/api/departments/{org.ops.id}/delete", json={"reason": "Merged", "confirm_name": "Operations"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Position, position["id"]).status == "deleted"


def test_only_the_chairperson_can_delete(make_client, org, db):
    chair, vc = login(make_client, org.chair), login(make_client, org.vc)
    category = chair.post("/api/positions", json={"title": "Core Team", "is_category": True}).json()
    assert _delete(vc, category["id"], "Core Team").status_code == 403
    assert login(make_client, org.ops_member).post(
        f"/api/positions/{category['id']}/delete", json={"reason": "Nope", "confirm_title": "Core Team"}).status_code == 403
    assert _delete(chair, category["id"], "Core Team").json()["holders_removed"] == 0


def test_chairpersons_own_position_is_protected(make_client, org, db, chair):
    client = login(make_client, org.chair)
    own = client.post("/api/positions", json={"title": "Chairperson", "is_lead": True}).json()
    assert client.post(f"/api/positions/{own['id']}/assign", json={"user_id": chair.id}).status_code == 201
    assert _delete(client, own["id"], "Chairperson").json()["error"]["code"] == "POSITION_PROTECTED"
