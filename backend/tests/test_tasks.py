from datetime import timedelta

import pytest

from app.core.time import utcnow
from tests.orgsetup import build_org, login, notifications


@pytest.fixture
def org(db, chair):
    return build_org(db, chair)


def _task(client, **extra):
    return client.post("/api/tasks", json={"title": "Design the poster", **extra})


def test_assign_work_submit_and_review(make_client, org):
    lead, member = login(make_client, org.ops_lead), login(make_client, org.ops_member)
    r = _task(lead, department_id=org.ops.id, assignee_ids=[org.ops_member.id], priority="high")
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["status"] == "assigned" and task["reviewer"]["id"] == org.ops_lead.id
    assert notifications(member, "task.assigned")[0]["payload"]["task_id"] == task["id"]

    tid = task["id"]
    assert member.get(f"/api/tasks/{tid}").json()["actions"] == ["comment", "start", "submit"]
    assert member.post(f"/api/tasks/{tid}/start").json()["status"] == "in_progress"
    r = member.post(f"/api/tasks/{tid}/submissions", json={"link_url": "https://drive.example/poster"})
    assert r.json()["status"] == "submitted"
    assert notifications(lead, "task.submitted")
    assert member.post(f"/api/tasks/{tid}/review", json={"outcome": "accepted"}).status_code == 403

    r = lead.post(f"/api/tasks/{tid}/review", json={"outcome": "changes_requested"})
    assert r.json()["error"]["code"] == "REMARKS_REQUIRED"
    r = lead.post(f"/api/tasks/{tid}/review", json={"outcome": "changes_requested", "remarks": "Bigger logo"})
    assert r.json()["status"] == "in_progress"
    assert notifications(member, "task.reviewed")[0]["payload"]["remarks"] == "Bigger logo"

    member.post(f"/api/tasks/{tid}/submissions", json={"note": "Logo enlarged", "link_url": "https://drive.example/v2"})
    r = lead.post(f"/api/tasks/{tid}/review", json={"outcome": "accepted"})
    done = r.json()
    assert done["status"] == "completed" and done["actions"] == ["comment", "reopen"]
    assert [s["review_outcome"] for s in done["submissions"]] == ["accepted", "changes_requested"]
    assert [h["to_status"] for h in done["history"]][:2] == ["completed", "submitted"]


def test_nobody_reviews_their_own_submission(make_client, org):
    lead = login(make_client, org.ops_lead)
    tid = _task(lead, department_id=org.ops.id, assignee_ids=[org.ops_lead.id]).json()["id"]
    lead.post(f"/api/tasks/{tid}/submissions", json={"note": "Done"})
    r = lead.post(f"/api/tasks/{tid}/review", json={"outcome": "accepted"})
    assert r.status_code == 403 and "your own submission" in r.json()["error"]["message"]


def test_dependencies_block_work_and_cycles_are_refused(make_client, org):
    lead, member = login(make_client, org.ops_lead), login(make_client, org.ops_member)
    first = _task(lead, department_id=org.ops.id).json()
    second = _task(lead, title="Print the poster", department_id=org.ops.id, depends_on=[first["id"]],
                   assignee_ids=[org.ops_member.id]).json()
    assert second["blocked"] is True
    r = member.post(f"/api/tasks/{second['id']}/start")
    assert r.status_code == 409 and r.json()["error"]["code"] == "BLOCKED"
    r = lead.put(f"/api/tasks/{first['id']}", json={"title": "Design the poster", "department_id": org.ops.id,
                                                    "depends_on": [second["id"]]})
    assert r.json()["error"]["code"] == "CYCLE"


def test_task_visibility_and_who_can_create(make_client, org):
    lead, member, tech = (login(make_client, u) for u in (org.ops_lead, org.ops_member, org.tech_member))
    tid = _task(lead, department_id=org.ops.id).json()["id"]
    assert member.get(f"/api/tasks/{tid}").status_code == 200           # Member role: tasks.view on Ops
    assert tech.get(f"/api/tasks/{tid}").status_code == 404
    assert _task(member, department_id=org.ops.id).status_code == 403   # members do not create department tasks
    assert _task(lead, department_id=org.tech.id).status_code == 403    # leads only in their department

    lead.put(f"/api/tasks/{tid}/assignees", json={"user_ids": [org.tech_member.id]})
    assert tech.get(f"/api/tasks/{tid}").status_code == 200              # assignees always see their task
    assert [t["id"] for t in tech.get("/api/tasks?view=mine").json()] == [tid]


def test_event_owner_runs_tasks_for_their_event(make_client, org):
    member = login(make_client, org.ops_member)
    ev = member.post("/api/events", json={"name": "Robo Race", "department_ids": [org.ops.id]}).json()
    r = _task(member, event_id=ev["id"], assignee_ids=[org.tech_member.id])
    assert r.status_code == 201, r.text
    assert r.json()["event"]["name"] == "Robo Race"
    assert member.get(f"/api/events/{ev['id']}").json()["open_tasks"] == 1


def test_comments_and_due_soon_reminders(db, make_client, org):
    lead, member = login(make_client, org.ops_lead), login(make_client, org.ops_member)
    soon = (utcnow() + timedelta(hours=5)).isoformat()
    tid = _task(lead, department_id=org.ops.id, due_at=soon, assignee_ids=[org.ops_member.id]).json()["id"]
    member.post(f"/api/tasks/{tid}/comments", json={"body": "Which size?"})
    assert notifications(lead, "task.comment")[0]["payload"]["excerpt"] == "Which size?"

    assert len(notifications(member, "task.due_soon")) == 1
    assert len(notifications(member, "task.due_soon")) == 1             # only once per task
    page = member.get("/api/notifications").json()
    assert page["unread"] >= 2
    assert member.post("/api/notifications/read", json={}).status_code == 204
    assert member.get("/api/notifications").json()["unread"] == 0
