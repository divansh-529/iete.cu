from datetime import timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.time import utcnow
from app.permissions.models import Grant, PermissionAudit
from tests.conftest import grant, make_user


def _grant(client, subject_id, code=None, role_id=None, subject_type="user", **extra):
    body = {"subject_type": subject_type, "subject_id": subject_id, "reason": "testing", **extra}
    if code:
        body["permission_code"] = code
    if role_id:
        body["role_id"] = role_id
    return client.post("/api/grants", json=body)


def test_grant_gives_access_and_revoke_removes_it(client, make_client, chair, db):
    member = make_user(db, "m@ietecu.in")
    member_client = make_client()
    member_client.login("m@ietecu.in")
    assert member_client.get("/api/users").status_code == 403

    client.login("chair@ietecu.in")
    r = _grant(client, member.id, "users.view")
    assert r.status_code == 201
    assert member_client.get("/api/users").status_code == 200

    r = client.post(f"/api/grants/{r.json()['id']}/revoke", json={"reason": "No longer needed"})
    assert r.status_code == 200 and r.json()["active"] is False
    assert member_client.get("/api/users").status_code == 403

    actions = db.scalars(select(PermissionAudit.action).order_by(PermissionAudit.id)).all()
    assert actions == ["grant", "revoke"]


def test_cannot_grant_to_self(client, chair, db):
    admin = make_user(db, "admin@ietecu.in")
    grant(db, admin, "permissions.manage", chair)
    client.login("admin@ietecu.in")
    r = _grant(client, admin.id, "users.view")
    assert r.status_code == 403


def test_delegation_ceiling(client, chair, db):
    admin = make_user(db, "admin@ietecu.in")
    member = make_user(db, "m@ietecu.in")
    grant(db, admin, "permissions.manage", chair)
    grant(db, admin, "users.view", chair)
    client.login("admin@ietecu.in")
    assert _grant(client, member.id, "users.view").status_code == 201        # holds it
    assert _grant(client, member.id, "finance.view").status_code == 403      # does not


def test_sensitive_permission_rejected_in_role(client, chair):
    client.login("chair@ietecu.in")
    r = client.post("/api/roles", json={"name": "Treasury", "permissions": ["finance.view"],
                                        "reason": "test"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SENSITIVE_IN_ROLE"


def test_sensitive_permission_blocked_in_db_too(db):
    db.execute(text("INSERT INTO roles (name) VALUES ('Sneaky')"))
    with pytest.raises(DBAPIError):
        db.execute(text("INSERT INTO role_permissions VALUES "
                        "((SELECT id FROM roles WHERE name='Sneaky'), 'finance.view')"))
    db.rollback()


def test_role_grant_gives_its_permissions(client, make_client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    role = client.post("/api/roles", json={"name": "Viewer", "permissions": ["users.view"],
                                           "reason": "test"}).json()
    assert _grant(client, member.id, role_id=role["id"]).status_code == 201

    member_client = make_client()
    member_client.login("m@ietecu.in")
    assert member_client.get("/api/users").status_code == 200
    me = member_client.get("/api/auth/me").json()
    assert {"code": "users.view", "scope_type": "global", "scope_id": None} in me["permissions"]

    # Editing the role changes access for everyone who holds it
    client.put(f"/api/roles/{role['id']}", json={"name": "Viewer", "permissions": ["org.view"],
                                                 "reason": "narrow"})
    assert member_client.get("/api/users").status_code == 403


def test_expired_grant_is_ignored(client, make_client, chair, db):
    member = make_user(db, "m@ietecu.in")
    g = grant(db, member, "users.view", chair)
    g.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    member_client = make_client()
    member_client.login("m@ietecu.in")
    assert member_client.get("/api/users").status_code == 403


def test_expire_job_writes_audit(chair, db):
    from app.permissions.service import expire_grants
    member = make_user(db, "m@ietecu.in")
    g = grant(db, member, "users.view", chair)
    g.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()
    assert expire_grants(db) == 1
    assert db.scalar(select(PermissionAudit.action)) == "expire"
    assert db.get(Grant, g.id).revoked_at is not None


def test_duplicate_grant_rejected(client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    assert _grant(client, member.id, "users.view").status_code == 201
    assert _grant(client, member.id, "users.view").status_code == 409


def test_scoped_grants_not_available_yet(client, chair, db):
    member = make_user(db, "m@ietecu.in")
    client.login("chair@ietecu.in")
    r = _grant(client, member.id, "tasks.view", scope_type="event", scope_id=1)
    assert r.status_code == 422


def test_audit_log_is_append_only(db):
    db.execute(text("INSERT INTO audit_events (action, entity_type) VALUES ('x', 'y')"))
    db.commit()
    with pytest.raises(DBAPIError):
        db.execute(text("DELETE FROM audit_events"))
    db.rollback()
