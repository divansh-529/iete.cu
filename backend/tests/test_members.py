"""Recruitment with approval: a lead proposes, the Chairperson / Vice Chair / Secretary decide."""
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.org.models import DepartmentMembership, Position
from app.users.models import User
from tests.orgsetup import build_org, login, notifications

DEFAULT = settings.default_member_password


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


def _propose(client, dept_id, email="recruit@gmail.com", **extra):
    return client.post(f"/api/departments/{dept_id}/member-proposals",
                       json={"email": email, "full_name": "Riya Recruit", **extra})


def test_lead_proposes_and_an_approver_activates(db, make_client, org):
    lead, vc, secretary = (login(make_client, u) for u in (org.ops_lead, org.vc, org.secretary))
    crew = Position(title="Operations Crew", department_id=org.ops.id, max_holders=5)
    db.add(crew)
    db.commit()

    r = _propose(lead, org.ops.id, position_id=crew.id, note="Strong at logistics")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "pending" and p["account_status"] == "proposed" and p["can_decide"] is False

    # Waiting accounts cannot sign in
    r = make_client().login("recruit@gmail.com", DEFAULT)
    assert r.status_code == 401        # no password yet
    # Every approver is told; the lead cannot decide
    for c in (vc, secretary):
        assert notifications(c, "account.proposed")[0]["payload"]["name"] == "Riya Recruit"
    assert lead.post(f"/api/member-proposals/{p['id']}/approve", json={}).status_code == 403

    r = secretary.post(f"/api/member-proposals/{p['id']}/approve", json={"remarks": "Welcome"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["proposal"]["status"] == "approved" and body["proposal"]["decided_by"]["id"] == org.secretary.id
    assert body["email_sent"] is False and body["default_password"] == DEFAULT     # email not set up in tests
    assert notifications(lead, "account.approved")[0]["payload"]["name"] == "Riya Recruit"

    recruit = db.scalar(select(User).where(User.email == "recruit@gmail.com"))
    assert recruit.status == "invited" and recruit.must_change_password
    assert db.scalar(select(DepartmentMembership.id).where(DepartmentMembership.user_id == recruit.id,
                                                           DepartmentMembership.department_id == org.ops.id))

    # First sign-in uses the default password and must change it, and not to the default again
    newbie = make_client()
    assert newbie.login("recruit@gmail.com", DEFAULT).status_code == 200
    assert newbie.get("/api/events").json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    r = newbie.post("/api/auth/change-password", json={"current_password": DEFAULT, "new_password": DEFAULT + "x"})
    assert r.status_code == 200, r.text


def test_new_password_cannot_be_the_default(make_client, client, chair):
    client.login("chair@ietecu.in")
    client.post("/api/users", json={"email": "direct@gmail.com", "full_name": "Direct Add"})
    c = make_client()
    assert c.login("direct@gmail.com", DEFAULT).status_code == 200      # admin-created: default password
    r = c.post("/api/auth/change-password", json={"current_password": DEFAULT, "new_password": "CU@12345678"})
    assert r.status_code == 422


def test_recruiting_is_limited_to_own_department(make_client, org, db):
    lead, vc = login(make_client, org.ops_lead), login(make_client, org.vc)
    tech_pos = Position(title="Technical Crew", department_id=org.tech.id)
    db.add(tech_pos)
    db.commit()
    assert _propose(lead, org.tech.id).status_code == 403
    assert _propose(lead, org.ops.id, position_id=tech_pos.id).status_code == 422
    assert _propose(lead, org.ops.id, email=org.ops_member.email).json()["error"]["code"] == "EMAIL_TAKEN"
    assert _propose(vc, org.tech.id, email="vcpick@gmail.com").status_code == 201    # VC recruits anywhere
    member = login(make_client, org.ops_member)
    assert _propose(member, org.ops.id).status_code == 403                           # members don't recruit


def test_no_one_approves_their_own_proposal(make_client, org):
    vc, secretary, chair = (login(make_client, u) for u in (org.vc, org.secretary, org.chair))
    p = _propose(vc, org.ops.id).json()
    r = vc.post(f"/api/member-proposals/{p['id']}/approve", json={})
    assert r.status_code == 403 and "someone else" in r.json()["error"]["message"]
    assert [x["can_decide"] for x in secretary.get("/api/member-proposals").json()] == [True]
    assert chair.post(f"/api/member-proposals/{p['id']}/approve", json={}).status_code == 200


def test_rejection_needs_a_reason_and_can_be_proposed_again(make_client, org, db):
    lead, chair = login(make_client, org.ops_lead), login(make_client, org.chair)
    p = _propose(lead, org.ops.id).json()
    assert chair.post(f"/api/member-proposals/{p['id']}/reject", json={}).json()["error"]["code"] == "REMARKS_REQUIRED"
    r = chair.post(f"/api/member-proposals/{p['id']}/reject", json={"remarks": "Apply next semester"})
    assert r.json()["proposal"]["status"] == "rejected"
    assert notifications(lead, "account.rejected")[0]["payload"]["remarks"] == "Apply next semester"
    assert make_client().login("recruit@gmail.com", DEFAULT).status_code == 401
    assert chair.post(f"/api/member-proposals/{p['id']}/approve", json={}).status_code == 409   # already decided

    again = _propose(lead, org.ops.id)
    assert again.status_code == 201
    history = chair.get("/api/member-proposals?status=all").json()
    assert sorted(x["status"] for x in history) == ["pending", "rejected"]


def test_full_position_at_approval_changes_nothing(make_client, org, db):
    lead, chair = login(make_client, org.ops_lead), login(make_client, org.chair)
    seat = Position(title="Operations Coordinator", department_id=org.ops.id, max_holders=1)
    db.add(seat)
    db.commit()
    first = _propose(lead, org.ops.id, email="a@gmail.com", position_id=seat.id).json()
    second = _propose(lead, org.ops.id, email="b@gmail.com", position_id=seat.id).json()
    assert chair.post(f"/api/member-proposals/{first['id']}/approve", json={}).status_code == 200
    r = chair.post(f"/api/member-proposals/{second['id']}/approve", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "POSITION_FULL"
    pending = chair.get("/api/member-proposals").json()
    assert [(x["id"], x["account_status"]) for x in pending] == [(second["id"], "proposed")]


def test_welcome_email_is_sent_when_configured(make_client, org, monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr("app.users.service.send_mail", lambda to, subject, text, html=None: sent.append((to, text)) or True)
    lead, chair = login(make_client, org.ops_lead), login(make_client, org.chair)
    p = _propose(lead, org.ops.id).json()
    body = chair.post(f"/api/member-proposals/{p['id']}/approve", json={}).json()
    assert body["email_sent"] is True and body["proposal"]["email_sent_at"]
    (to, text), = sent
    assert to == "recruit@gmail.com" and DEFAULT in text and "Operations" in text


def test_first_change_needs_no_current_password_but_later_ones_do(make_client, client, chair):
    client.login("chair@ietecu.in")
    client.post("/api/users", json={"email": "fresh@gmail.com", "full_name": "Fresh Member"})
    c = make_client()
    c.login("fresh@gmail.com", DEFAULT)
    r = c.post("/api/auth/change-password", json={"new_password": "my-own-password-1"})
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is False
    # From now on, changing it again needs the current password
    assert c.post("/api/auth/change-password", json={"new_password": "another-password-2"}).status_code == 400
    assert c.post("/api/auth/change-password", json={"current_password": "my-own-password-1",
                                                     "new_password": "another-password-2"}).status_code == 200