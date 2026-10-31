from datetime import timedelta

from sqlalchemy import select, update

from app.auth.models import UserSession
from app.core.time import utcnow
from app.users.models import User
from tests.conftest import PASSWORD, make_user


def test_login_and_me(client, chair):
    r = client.login("chair@ietecu.in")
    assert r.status_code == 200
    assert r.json()["all_permissions"] is True
    assert client.get("/api/auth/me").json()["user"]["email"] == "chair@ietecu.in"


def test_email_is_case_insensitive(client, chair):
    assert client.login("CHAIR@IETECU.IN").status_code == 200


def test_wrong_password_and_unknown_email_look_the_same(client, chair):
    a = client.login("chair@ietecu.in", "wrong-password")
    b = client.login("nobody@ietecu.in", "wrong-password")
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["code"] == b.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_lockout_after_repeated_failures(client, db):
    make_user(db, "m@ietecu.in")
    for _ in range(5):
        assert client.login("m@ietecu.in", "nope-nope-nope").status_code == 401
    r = client.login("m@ietecu.in")  # correct password, but locked
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_suspended_user_cannot_log_in(client, db):
    make_user(db, "s@ietecu.in", status="suspended")
    r = client.login("s@ietecu.in")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_protected_route_requires_login(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/users").status_code == 401


def test_logout_invalidates_session(client, chair):
    client.login("chair@ietecu.in")
    session_cookie = client.cookies.get("iete_session")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("iete_session", session_cookie)  # replaying the old cookie must fail
    assert client.get("/api/auth/me").status_code == 401


def test_idle_session_expires(client, chair, db):
    client.login("chair@ietecu.in")
    db.execute(update(UserSession).values(last_seen_at=utcnow() - timedelta(hours=3)))
    db.commit()
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "SESSION_EXPIRED"


def test_csrf_header_required_for_state_changes(client, chair):
    client.login("chair@ietecu.in")
    from fastapi.testclient import TestClient
    r = TestClient.request(client, "POST", "/api/auth/logout")  # bypasses auto-header
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_FAILED"


def test_temp_password_forces_change_then_activates(client, db):
    make_user(db, "new@ietecu.in", status="invited", must_change=True)
    assert client.login("new@ietecu.in").status_code == 200
    r = client.get("/api/users")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    assert client.post("/api/auth/change-password", json={
        "current_password": PASSWORD, "new_password": PASSWORD}).status_code == 422
    assert client.post("/api/auth/change-password", json={
        "current_password": PASSWORD, "new_password": "short"}).status_code == 422
    r = client.post("/api/auth/change-password", json={
        "current_password": PASSWORD, "new_password": "a-brand-new-password"})
    assert r.status_code == 200
    user = db.scalar(select(User).where(User.email == "new@ietecu.in"))
    db.refresh(user)
    assert user.status == "active" and user.must_change_password is False


def test_password_change_signs_out_other_sessions(make_client, db):
    make_user(db, "m@ietecu.in")
    a, b = make_client(), make_client()
    a.login("m@ietecu.in")
    b.login("m@ietecu.in")
    a.post("/api/auth/change-password", json={"current_password": PASSWORD,
                                              "new_password": "another-good-password"})
    assert a.get("/api/auth/me").status_code == 200
    assert b.get("/api/auth/me").status_code == 401


def test_invite_link_flow(client, make_client, chair):
    client.login("chair@ietecu.in")
    r = client.post("/api/users", json={"email": "inv@ietecu.in", "full_name": "Invited Person",
                                        "credential": "invite"})
    assert r.status_code == 201
    token = r.json()["invite_url"].split("token=")[1]

    newcomer = make_client()
    assert newcomer.get(f"/api/auth/invite/{token}").json()["email"] == "inv@ietecu.in"
    r = newcomer.post("/api/auth/accept-invite", json={"token": token,
                                                       "new_password": "my-own-password"})
    assert r.status_code == 200
    assert r.json()["user"]["status"] == "active"
    assert newcomer.get("/api/auth/me").status_code == 200

    # Single use
    again = make_client().post("/api/auth/accept-invite", json={"token": token,
                                                                "new_password": "other-password"})
    assert again.status_code == 400
