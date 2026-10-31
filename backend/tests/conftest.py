import os

os.environ.setdefault("IETE_DATABASE_URL",
                      "postgresql+psycopg://iete:iete_dev_password@localhost:5433/iete_test")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.auth.deps import CSRF_COOKIE  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.permissions.catalogue import sync_catalogue  # noqa: E402
from app.permissions.models import Grant  # noqa: E402
from app.users.models import User  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def _migrate():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location",
                        os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _clean_db():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        # TRUNCATE bypasses the row-level append-only triggers, which is what tests need.
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        sync_catalogue(db)
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_user(db, email: str, *, super_admin: bool = False, status: str = "active",
              must_change: bool = False, password: str | None = PASSWORD) -> User:
    user = User(email=email, full_name=email.split("@")[0].title(), user_type="team",
                status=status, must_change_password=must_change, is_super_admin=super_admin,
                password_hash=hash_password(password) if password else None)
    db.add(user)
    db.commit()
    return user


def grant(db, user: User, code: str, by: User) -> Grant:
    g = Grant(subject_type="user", subject_id=user.id, permission_code=code,
              granted_by=by.id, reason="test setup")
    db.add(g)
    db.commit()
    return g


class Client(TestClient):
    """TestClient that sends the CSRF header automatically after login."""

    def request(self, method, url, **kwargs):
        token = self.cookies.get(CSRF_COOKIE)
        if token:
            kwargs["headers"] = {**(kwargs.get("headers") or {}), "x-csrf-token": token}
        return super().request(method, url, **kwargs)

    def login(self, email: str, password: str = PASSWORD):
        return self.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture
def client():
    return Client(app)


@pytest.fixture
def make_client():
    return lambda: Client(app)


@pytest.fixture
def chair(db):
    return make_user(db, "chair@ietecu.in", super_admin=True)
