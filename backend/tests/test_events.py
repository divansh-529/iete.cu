import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.orgsetup import build_org, login, notifications

START = "2026-12-05T10:00:00+05:30"


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


def _event(client, **extra):
    body = {"name": "Tech Fest 2026", "department_ids": [], **extra}
    return client.post("/api/events", json=body)


def _move(client, event_id, to, remarks=None):
    return client.post(f"/api/events/{event_id}/transition", json={"to_status": to, "remarks": remarks})


def test_two_step_approval_chain(make_client, org):
    member, vc, chair = (login(make_client, u) for u in (org.ops_member, org.vc, org.chair))

    r = _event(member, department_ids=[org.ops.id])
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["status"] == "draft" and ev["owner"]["id"] == org.ops_member.id
    assert [t["to_status"] for t in ev["allowed_transitions"]] == ["proposed", "cancelled"]

    assert _move(member, ev["id"], "proposed").json()["error"]["code"] == "INCOMPLETE"   # no date yet
    r = member.put(f"/api/events/{ev['id']}", json={"name": "Tech Fest 2026", "starts_at": START,
                                                    "venue": "Main Hall", "department_ids": [org.ops.id]})
    assert r.status_code == 200, r.text
    assert _move(member, ev["id"], "proposed").json()["status"] == "proposed"

    # Leadership is told and can forward; the owner cannot forward their own proposal
    assert notifications(vc, "event.needs_review")[0]["payload"]["event_id"] == ev["id"]
    assert _move(member, ev["id"], "awaiting_approval").status_code == 403
    assert member.put(f"/api/events/{ev['id']}", json={"name": "Renamed", "department_ids": [org.ops.id]}).status_code == 403
    assert _move(vc, ev["id"], "awaiting_approval").json()["status"] == "awaiting_approval"

    # Only the Chairperson approves
    assert _move(vc, ev["id"], "approved").status_code == 403
    assert notifications(chair, "event.needs_approval")[0]["payload"]["event_id"] == ev["id"]
    r = _move(chair, ev["id"], "approved")
    assert r.json()["status"] == "approved"
    assert [h["to_status"] for h in r.json()["history"]] == ["approved", "awaiting_approval", "proposed", "draft"]
    assert {n["payload"]["to_status"] for n in notifications(member, "event.status")} == {"awaiting_approval", "approved"}


def test_send_back_needs_a_reason_and_reopens_the_draft(make_client, org):
    member, vc = login(make_client, org.ops_member), login(make_client, org.vc)
    ev = _event(member, department_ids=[org.ops.id], starts_at=START).json()
    _move(member, ev["id"], "proposed")
    assert _move(vc, ev["id"], "draft").json()["error"]["code"] == "REMARKS_REQUIRED"
    r = _move(vc, ev["id"], "draft", "Please add a budget")
    assert r.json()["status"] == "draft"
    detail = member.get(f"/api/events/{ev['id']}").json()
    assert detail["can_edit"] is True and detail["history"][0]["remarks"] == "Please add a budget"


def test_nobody_approves_their_own_event(make_client, org):
    vc = login(make_client, org.vc)
    ev = _event(vc, starts_at=START).json()                      # Leadership may create org-wide events
    _move(vc, ev["id"], "proposed")
    r = _move(vc, ev["id"], "awaiting_approval")
    assert r.status_code == 403 and "you own" in r.json()["error"]["message"]


def test_members_create_events_only_for_their_department(make_client, org):
    member = login(make_client, org.ops_member)
    assert _event(member, department_ids=[org.tech.id]).status_code == 403
    assert _event(member).json()["error"]["code"] == "DEPARTMENT_REQUIRED"


def test_event_visibility_follows_department_and_team(make_client, org):
    member, tech, lead = (login(make_client, u) for u in (org.ops_member, org.tech_member, org.ops_lead))
    ev = _event(member, department_ids=[org.ops.id]).json()

    assert tech.get(f"/api/events/{ev['id']}").status_code == 404
    assert [e["id"] for e in tech.get("/api/events").json()] == []
    assert lead.get(f"/api/events/{ev['id']}").status_code == 200        # same department

    r = member.post(f"/api/events/{ev['id']}/team", json={"user_id": org.tech_member.id, "event_role": "Volunteer"})
    assert r.status_code == 201 and r.json()["team"][0]["event_role"] == "volunteer"
    assert tech.get(f"/api/events/{ev['id']}").status_code == 200
    assert [e["id"] for e in tech.get("/api/events?view=mine").json()] == [ev["id"]]
    assert notifications(tech, "event.team_added")[0]["payload"]["event_id"] == ev["id"]
    assert tech.post(f"/api/events/{ev['id']}/checklist", json={"label": "Book hall"}).status_code == 403


def test_workspace_checklist_and_milestones(make_client, org):
    member = login(make_client, org.ops_member)
    ev = _event(member, department_ids=[org.ops.id]).json()
    r = member.post(f"/api/events/{ev['id']}/checklist", json={"label": "Book hall"})
    item = r.json()["checklist"][0]
    r = member.put(f"/api/events/{ev['id']}/checklist/{item['id']}", json={"label": "Book hall", "done": True})
    assert r.json()["checklist"][0]["done_by"]["id"] == org.ops_member.id
    r = member.post(f"/api/events/{ev['id']}/milestones", json={"title": "Posters out", "due_at": START})
    assert r.json()["milestones"][0]["title"] == "Posters out"


def test_status_history_is_append_only(db, make_client, org):
    member = login(make_client, org.ops_member)
    _event(member, department_ids=[org.ops.id])
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE event_status_history SET remarks = 'x'"))
    db.rollback()
