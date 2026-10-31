"""Admin commands that must never be exposed over the web.

    python -m app.cli create-superadmin --email chair@example.com --name "Full Name"
    python -m app.cli seed-roles
    python -m app.cli seed-org
    python -m app.cli expire-grants
"""
import argparse
import getpass
import sys

from sqlalchemy import select

from app.audit import service as audit
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.security import hash_password, validate_new_password
from app.permissions.catalogue import sync_catalogue
from app.permissions.models import PermissionAudit, Role, RolePermission
from app.permissions.service import expire_grants
from app.users.models import User

# Starting roles from docs/02-permissions.md §8. Editable in the app afterwards.
DEFAULT_ROLES = {
    "Leadership": ("Vice Chair, Secretary, Joint Secretary", [
        "users.view", "org.view", "events.view", "events.create", "events.edit", "events.archive",
        "tasks.view", "tasks.create", "tasks.assign", "tasks.review", "tasks.export",
        "documents.view", "documents.upload", "documents.review", "points.view",
        "points.evaluate", "points.leaderboard.view", "reports.view"]),
    "Department Lead": ("Leads of each department", [
        "org.view", "org.assign", "events.view", "tasks.view", "tasks.create", "tasks.assign", "tasks.review",
        "documents.view", "documents.upload", "points.leaderboard.view"]),
    "Member": ("Ordinary department members", [
        "org.view", "events.view", "tasks.view", "documents.view", "points.leaderboard.view"]),
}


def create_superadmin(email: str, name: str, password: str | None) -> None:
    with SessionLocal() as db:
        sync_catalogue(db)
        if db.scalar(select(User).where(User.is_super_admin)):
            sys.exit("A super admin already exists. Transfer it from inside the app instead.")
        if db.scalar(select(User).where(User.email == email)):
            sys.exit(f"An account with email {email} already exists.")
        if password is None:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Repeat password: "):
                sys.exit("Passwords do not match.")
        try:
            validate_new_password(password, email)
        except AppError as e:
            sys.exit(e.message)
        user = User(email=email, full_name=name, user_type="team", status="active",
                    must_change_password=False, is_super_admin=True,
                    password_hash=hash_password(password))
        db.add(user)
        db.flush()
        audit.record(db, None, "user.create_superadmin", "user", user.id,
                     after={"email": email, "full_name": name})
        db.commit()
        print(f"Super admin created: {email} (id {user.id})")


def seed_roles() -> None:
    with SessionLocal() as db:
        sync_catalogue(db)
        for name, (description, codes) in DEFAULT_ROLES.items():
            if db.scalar(select(Role).where(Role.name == name)):
                print(f"Role exists, skipped: {name}")
                continue
            role = Role(name=name, description=description)
            db.add(role)
            db.flush()
            db.add_all(RolePermission(role_id=role.id, permission_code=c) for c in codes)
            db.add(PermissionAudit(action="role_create", subject_type="role", subject_id=role.id,
                                   role_id=role.id, reason="Default role seeded",
                                   new_value={"name": name, "permissions": sorted(codes)}))
            print(f"Role created: {name}")
        db.commit()


# Blueprint §4.1–4.2. Leads report to the Secretary by default (docs/07-open-decisions.md).
LEADERSHIP = ["Chairperson", "Vice Chairperson", "Secretary", "Joint Secretary"]
DEPARTMENTS = [
    ("Treasury", "Treasurer and authorised finance team", "Treasurer"),
    ("Membership", "Membership records and drives", "Membership Lead"),
    ("Management", "Event management", "Management Lead"),
    ("Operations", "Event operations and logistics", "Operations Lead"),
    ("Discipline", "Discipline and crowd management", "Discipline Lead"),
    ("Graphics", "Design and creatives", "Graphics Lead"),
    ("Technical", "Technical team", "Technical Lead"),
    ("PR", "Public relations", "PR Lead"),
    ("Anchoring", "Anchoring and hosting", "Anchoring Lead"),
]


def seed_org() -> None:
    from datetime import date

    from app.org.models import Department, Position, PositionAssignment
    from app.permissions.models import Grant

    with SessionLocal() as db:
        if db.scalar(select(Position).limit(1)):
            sys.exit("Positions already exist; seed-org only runs on an empty organisation.")
        chair = db.scalar(select(User).where(User.is_super_admin))
        lead_role = db.scalar(select(Role).where(Role.name == "Department Lead"))
        previous = None
        positions = {}
        for rank, title in enumerate(LEADERSHIP, start=1):
            pos = Position(title=title, rank_order=rank * 10, is_lead=True,
                           reports_to_position_id=previous)
            db.add(pos)
            db.flush()
            positions[title] = pos
            previous = pos.id
        for name, description, lead_title in DEPARTMENTS:
            dept = Department(name=name, description=description)
            db.add(dept)
            db.flush()
            lead = Position(title=lead_title, department_id=dept.id, is_lead=True, rank_order=100,
                            reports_to_position_id=positions["Secretary"].id)
            db.add(lead)
            db.flush()
            # Whoever holds the Lead position can run their own department (e.g. add members to it).
            if chair and lead_role:
                g = Grant(subject_type="position", subject_id=lead.id, role_id=lead_role.id,
                          scope_type="department", scope_id=dept.id, granted_by=chair.id,
                          reason="Default Department Lead access")
                db.add(g)
                db.flush()
                db.add(PermissionAudit(actor_id=None, action="grant", subject_type="position",
                                       subject_id=lead.id, role_id=lead_role.id, scope_type="department",
                                       scope_id=dept.id, reason=g.reason,
                                       new_value={"grant_id": g.id, "role_id": lead_role.id}))
        if not (chair and lead_role):
            print("Lead positions were not given the Department Lead role: run create-superadmin and "
                  "seed-roles first, or grant it from the app.")
        if chair:
            db.add(PositionAssignment(user_id=chair.id, position_id=positions["Chairperson"].id,
                                      valid_from=date.today(), start_reason="appointed",
                                      assigned_by=chair.id))
        audit.record(db, None, "org.seed", "organisation", None,
                     after={"leadership": LEADERSHIP, "departments": [d[0] for d in DEPARTMENTS]})
        db.commit()
        print(f"Created {len(LEADERSHIP)} leadership positions and {len(DEPARTMENTS)} departments.")


def db_check() -> None:
    """Startup check: says which database we are about to use (password masked) and why it fails."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    try:
        url = make_url(settings.database_url)
    except Exception:
        sys.exit("DB CHECK FAILED: IETE_DATABASE_URL is not a valid postgresql:// address. "
                 "Paste only the URL: no quotes, no variable name, no spaces.")
    pw = url.password or ""
    print(f"DB CHECK: user={url.username} host={url.host} database={url.database} "
          f"password={len(pw)} chars ({pw[:4]}…) query={dict(url.query)}")
    try:
        with create_engine(url).connect() as conn:
            conn.execute(text("select 1"))
    except Exception as e:
        reason = str(getattr(e, "orig", e))
        if "password authentication failed" in reason:
            sys.exit("DB CHECK FAILED: wrong database password for this user. Copy the connection "
                     "string again from Neon (Connect, pooling off) and paste it unchanged.")
        sys.exit(f"DB CHECK FAILED: {reason.splitlines()[0] if reason else type(e).__name__}")
    print("DB CHECK: connected OK")
    secret = settings.proxy_secret
    print(f"PROXY SECRET: {len(secret)} chars ({secret[:4]}…{secret[-2:]})" if secret else
          "PROXY SECRET: not set (the API accepts direct requests)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("create-superadmin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--password", help="omit to be prompted (recommended)")
    sub.add_parser("seed-roles")
    sub.add_parser("seed-org")
    sub.add_parser("expire-grants")
    sub.add_parser("db-check")
    args = parser.parse_args()

    if args.command == "create-superadmin":
        create_superadmin(args.email, args.name, args.password)
    elif args.command == "seed-roles":
        seed_roles()
    elif args.command == "seed-org":
        seed_org()
    elif args.command == "db-check":
        db_check()
    elif args.command == "expire-grants":
        with SessionLocal() as db:
            print(f"Expired grants marked: {expire_grants(db)}")


if __name__ == "__main__":
    main()
