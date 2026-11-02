"""Only the Chairperson can delete an account."""
import pytest
from sqlalchemy import select

from app.audit.models import AuditEvent
from app.permissions.models import Grant
from app.tasks.models import TaskAssignee
from app.users.models import User
from tests.conftest import PASSWORD, grant
from tests.orgsetup import build_org, login


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


def _delete(client, user, confirm=None):
    return client.post(f"/api/users/{user.id}/delete",
                       json={"reason": "Left the forum", "confirm_email": confirm if confirm is not None else user.email})


def test_only_the_chairperson_can_delete(make_client, org, db, chair):
    client = login(make_client, org.chair)
    # Not leads, not leadership, not even someone granted the suspend permission.
    assert _delete(login(make_client, org.ops_lead), org.ops_member).status_code == 403
    assert _delete(login(make_client, org.vc), org.ops_member).status_code == 403
    grant(db, org.vc, "users.suspend", by=chair)
    assert _delete(login(make_client, org.vc), org.ops_member).status_code == 403
    assert _delete(client, chair).status_code == 403
    assert _delete(client, org.ops_member, confirm="wrong@ietecu.in").json()["error"]["code"] == "CONFIRMATION_MISMATCH"
    db.expire_all()
    assert db.get(User, org.ops_member.id).status == "active"


def test_deleting_removes_access_and_open_work_but_keeps_history(make_client, org, db):
    chair, lead = login(make_client, org.chair), login(make_client, org.ops_lead)
    event = lead.post("/api/events", json={"name": "Tech Fest", "department_ids": [org.ops.id]}).json()
    task = chair.post("/api/tasks", json={"title": "Posters", "department_id": org.ops.id,
                                          "assignee_ids": [org.ops_lead.id]})
    assert task.status_code == 201, task.text

    r = _delete(chair, org.ops_lead)
    assert r.status_code == 200, r.text
    assert r.json() == {"positions_ended": 1, "memberships_ended": 1, "grants_revoked": 0, "tasks_unassigned": 1,
                        "events_still_owned": 1}

    # Signed out at once and can't sign in again.
    assert lead.get("/api/auth/me").status_code == 401
    assert make_client().post("/api/auth/login", json={"email": org.ops_lead.email, "password": PASSWORD}).status_code == 401
    # Gone from accounts and the people picker.
    assert org.ops_lead.id not in {u["id"] for u in chair.get("/api/users").json()["items"]}
    assert chair.get(f"/api/users/{org.ops_lead.id}").status_code == 404
    assert org.ops_lead.id not in {p["id"] for p in chair.get("/api/org/people").json()}
    # History still names them.
    history = chair.get(f"/api/users/{org.ops_lead.id}/org").json()["positions"]
    assert history[0]["end_reason"] == "removed"
    assert chair.get(f"/api/events/{event['id']}").json()["owner"]["id"] == org.ops_lead.id
    db.expire_all()
    assert db.query(AuditEvent).filter_by(action="user.delete", entity_id=org.ops_lead.id).count() == 1
    assert not db.scalars(select(TaskAssignee).where(TaskAssignee.user_id == org.ops_lead.id,
                                                     TaskAssignee.unassigned_at.is_(None))).all()


def test_direct_grants_end_and_email_and_uid_can_be_reused(make_client, org, db, chair):
    client = login(make_client, org.chair)
    grant(db, org.ops_member, "org.view", by=chair)
    assert client.put(f"/api/users/{org.ops_member.id}/profile", json={"uid": "25BCS1"}).status_code == 200
    assert _delete(client, org.ops_member).json()["grants_revoked"] == 1
    db.expire_all()
    assert not db.scalars(select(Grant).where(Grant.subject_type == "user", Grant.subject_id == org.ops_member.id,
                                              Grant.revoked_at.is_(None))).all()

    r = client.post("/api/users", json={"email": org.ops_member.email, "full_name": "Back Again", "credential": "default_password"})
    assert r.status_code == 201, r.text
    new_id = r.json()["user"]["id"]
    assert new_id != org.ops_member.id
    assert client.put(f"/api/users/{new_id}/profile", json={"uid": "25BCS1"}).status_code == 200
    # Two live accounts still can't share an email.
    r = client.post("/api/users", json={"email": org.ops_member.email, "full_name": "Twin", "credential": "default_password"})
    assert r.json()["error"]["code"] == "EMAIL_TAKEN"


def test_not_approved_recruit_can_be_deleted_and_proposed_again(make_client, org):
    chair, lead = login(make_client, org.chair), login(make_client, org.ops_lead)
    body = {"email": "recruit@gmail.com", "full_name": "New Recruit"}
    assert lead.post(f"/api/departments/{org.ops.id}/member-proposals", json=body).status_code == 201
    recruit = chair.get("/api/users", params={"q": "recruit@gmail.com"}).json()["items"][0]
    r = chair.post(f"/api/users/{recruit['id']}/delete", json={"reason": "Duplicate", "confirm_email": recruit["email"]})
    assert r.status_code == 200, r.text
    assert chair.get("/api/users", params={"q": "recruit@gmail.com"}).json()["total"] == 0
    assert lead.post(f"/api/departments/{org.ops.id}/member-proposals", json=body).status_code == 201


def test_scores_drop_out_of_open_and_published_rounds(make_client, org):
    chair, vc = login(make_client, org.chair), login(make_client, org.vc)
    rnd = chair.post("/api/scores/rounds", json={"title": "October"}).json()
    assert chair.post(f"/api/scores/rounds/{rnd['id']}/close").status_code == 200
    assert org.ops_member.id in {b["person"]["id"] for b in chair.get("/api/scores/leaderboard").json()}
    open_round = chair.post("/api/scores/rounds", json={"title": "November"}).json()
    assert _delete(chair, org.ops_member).status_code == 200
    assert org.ops_member.id not in {b["person"]["id"] for b in chair.get("/api/scores/leaderboard").json()}
    assert chair.get(f"/api/scores/people/{org.ops_member.id}").status_code == 404
    current = next(r for r in chair.get("/api/scores/rounds").json() if r["id"] == open_round["id"])
    assert current["cards"] == open_round["cards"] - 1
