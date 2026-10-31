from sqlalchemy import select

from app.audit.models import AuditEvent
from tests.conftest import PASSWORD, grant, make_user


def test_admin_creates_user_with_temp_password(client, make_client, chair, db):
    client.login("chair@ietecu.in")
    r = client.post("/api/users", json={"email": "ops@ietecu.in", "full_name": "Ops Lead",
                                        "credential": "temp_password",
                                        "temp_password": "temporary-pass-1"})
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["status"] == "invited" and body["invite_url"] is None

    newcomer = make_client()
    assert newcomer.login("ops@ietecu.in", "temporary-pass-1").json()["user"]["must_change_password"]

    actions = db.scalars(select(AuditEvent.action)).all()
    assert "user.create" in actions


def test_duplicate_email_rejected(client, chair):
    client.login("chair@ietecu.in")
    body = {"email": "x@ietecu.in", "full_name": "X Person", "credential": "invite"}
    assert client.post("/api/users", json=body).status_code == 201
    r = client.post("/api/users", json={**body, "email": "X@IETECU.IN"})
    assert r.status_code == 409


def test_member_without_permission_is_forbidden(client, db):
    make_user(db, "m@ietecu.in")
    client.login("m@ietecu.in")
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", json={"email": "a@ietecu.in", "full_name": "Aa",
                                           "credential": "invite"}).status_code == 403


def test_granted_view_permission_allows_listing_only(client, chair, db):
    sec = make_user(db, "sec@ietecu.in")
    grant(db, sec, "users.view", chair)
    client.login("sec@ietecu.in")
    assert client.get("/api/users").status_code == 200
    assert client.post("/api/users", json={"email": "a@ietecu.in", "full_name": "Aa",
                                           "credential": "invite"}).status_code == 403


def test_suspend_ends_sessions_immediately(client, make_client, chair, db):
    member = make_user(db, "m@ietecu.in")
    member_client = make_client()
    member_client.login("m@ietecu.in")
    client.login("chair@ietecu.in")
    r = client.post(f"/api/users/{member.id}/suspend", json={"reason": "Inactive for a month"})
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    assert member_client.get("/api/auth/me").status_code == 401

    r = client.post(f"/api/users/{member.id}/reactivate", json={"reason": "Back"})
    assert r.json()["status"] == "active"


def test_admin_reset_password(client, make_client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    r = client.post(f"/api/users/{member.id}/reset-password",
                    json={"temp_password": "fresh-temp-pass"})
    assert r.status_code == 200 and r.json()["must_change_password"] is True
    assert make_client().login("m@ietecu.in", PASSWORD).status_code == 401
    assert make_client().login("m@ietecu.in", "fresh-temp-pass").status_code == 200
    # The password itself never appears in the audit log
    rows = db.scalars(select(AuditEvent).where(AuditEvent.action == "user.reset_password")).all()
    assert rows and all("fresh-temp-pass" not in str(r.after) for r in rows)


def test_admin_cannot_touch_chairperson_or_self(client, chair, db):
    admin = make_user(db, "admin@ietecu.in")
    grant(db, admin, "users.suspend", chair)
    grant(db, admin, "users.reset_password", chair)
    client.login("admin@ietecu.in")
    assert client.post(f"/api/users/{chair.id}/suspend", json={"reason": "coup"}).status_code == 403
    assert client.post(f"/api/users/{admin.id}/suspend", json={"reason": "self"}).status_code == 403
    assert client.post(f"/api/users/{chair.id}/reset-password",
                       json={"temp_password": "takeover-password"}).status_code == 403
