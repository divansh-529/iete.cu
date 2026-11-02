"""Admin commands that must never be exposed over the web.

    python -m app.cli create-superadmin --email chair@example.com --name "Full Name"
    python -m app.cli seed-roles
    python -m app.cli seed-org
    python -m app.cli sync-defaults    # existing installs: add new default permissions and grants
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
        "org.view", "events.view", "events.create", "events.edit", "events.review",
        "events.archive",
        "tasks.view", "tasks.create", "tasks.assign", "tasks.review", "tasks.export",
        "documents.view", "documents.upload", "documents.review", "finance.expense.submit", "points.view",
        "points.evaluate", "points.leaderboard.view", "reports.view"]),
    "Department Lead": ("Leads of each department", [
        "org.view", "org.assign", "events.view", "events.create", "events.edit", "tasks.view",
        "tasks.create", "tasks.assign", "tasks.review", "documents.view", "documents.upload",
        "finance.expense.submit", "points.leaderboard.view"]),
    # Every core team member can propose events for their department; approval decides.
    "Member": ("Ordinary department members", [
        "org.view", "events.view", "events.create", "tasks.view", "documents.view",
        "points.leaderboard.view"]),
}


def create_superadmin(email: str, name: str, password: str | None) -> None:
    with SessionLocal() as db:
        sync_catalogue(db)
        if db.scalar(select(User).where(User.is_super_admin)):
            sys.exit("A super admin already exists. Transfer it from inside the app instead.")
        if db.scalar(select(User).where(User.email == email, User.status != "deleted")):
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


# Blueprint §4.1–4.2, as confirmed by the Chairperson: the Vice Chairperson and Secretary are
# equals who both report to the Chairperson; the Joint Secretary and the department Leads report
# to the Secretary.
LEADERSHIP = ["Chairperson", "Vice Chairperson", "Secretary", "Joint Secretary"]
LEADERSHIP_REPORTS_TO = {"Vice Chairperson": "Chairperson", "Secretary": "Chairperson",
                         "Joint Secretary": "Secretary"}
LEADERSHIP_RANK = {"Chairperson": 10, "Vice Chairperson": 20, "Secretary": 20, "Joint Secretary": 30}
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

    with SessionLocal() as db:
        if db.scalar(select(Position).limit(1)):
            sys.exit("Positions already exist; seed-org only runs on an empty organisation.")
        chair = db.scalar(select(User).where(User.is_super_admin))
        positions = {}
        for title in LEADERSHIP:
            boss = LEADERSHIP_REPORTS_TO.get(title)
            pos = Position(title=title, rank_order=LEADERSHIP_RANK[title], is_lead=True,
                           reports_to_position_id=positions[boss].id if boss else None)
            db.add(pos)
            db.flush()
            positions[title] = pos
        for name, description, lead_title in DEPARTMENTS:
            dept = Department(name=name, description=description)
            db.add(dept)
            db.flush()
            db.add(Position(title=lead_title, department_id=dept.id, is_lead=True, rank_order=100,
                            reports_to_position_id=positions["Secretary"].id))
        db.flush()
        if chair:
            db.add(PositionAssignment(user_id=chair.id, position_id=positions["Chairperson"].id,
                                      valid_from=date.today(), start_reason="appointed",
                                      assigned_by=chair.id))
            granted = apply_default_grants(db, chair)
        else:
            granted = 0
            print("Default access was not granted: run create-superadmin and seed-roles first, "
                  "then sync-defaults.")
        audit.record(db, None, "org.seed", "organisation", None,
                     after={"leadership": LEADERSHIP, "departments": [d[0] for d in DEPARTMENTS]})
        db.commit()
        print(f"Created {len(LEADERSHIP)} leadership positions and {len(DEPARTMENTS)} departments; "
              f"{granted} default grant(s).")


# docs/02-permissions.md §8: which positions and departments get which default access.
LEADERSHIP_ROLE_POSITIONS = ("Vice Chairperson", "Secretary", "Joint Secretary")
# The Vice Chairperson and Secretary recruit for any department and approve new accounts.
RECRUITER_POSITIONS = ("Vice Chairperson", "Secretary")
RECRUITER_PERMISSIONS = ("org.assign", "users.approve")


def _grant_once(db, chair: User, subject_type: str, subject_id: int, scope_type: str, scope_id: int | None,
                role: Role | None = None, permission: str | None = None) -> bool:
    """Grant a role or a single permission unless an identical active grant exists.
    Returns True if one was added."""
    from app.permissions.engine import active_grant_filter
    from app.permissions.models import Grant

    role_id = role.id if role else None
    exists = db.scalar(select(Grant.id).where(
        Grant.subject_type == subject_type, Grant.subject_id == subject_id,
        Grant.role_id.is_not_distinct_from(role_id), Grant.permission_code.is_not_distinct_from(permission),
        Grant.scope_type == scope_type, Grant.scope_id.is_not_distinct_from(scope_id),
        *active_grant_filter()))
    if exists:
        return False
    g = Grant(subject_type=subject_type, subject_id=subject_id, role_id=role_id, permission_code=permission,
              scope_type=scope_type, scope_id=scope_id, granted_by=chair.id,
              reason=f"Default {role.name if role else permission} access")
    db.add(g)
    db.flush()
    db.add(PermissionAudit(actor_id=None, action="grant", subject_type=subject_type, subject_id=subject_id,
                           role_id=role_id, permission_code=permission, scope_type=scope_type, scope_id=scope_id,
                           reason=g.reason, new_value={"grant_id": g.id, "role_id": role_id, "permission": permission}))
    return True


def apply_default_grants(db, chair: User) -> int:
    """Leadership positions get Leadership (everywhere), and the Vice Chairperson and Secretary
    also recruit and approve accounts everywhere. Each department's Lead position gets Department
    Lead and each department gets Member, both on that department only."""
    from app.org.models import Department, Position

    roles = {r.name: r for r in db.scalars(select(Role).where(Role.name.in_(DEFAULT_ROLES)))}
    added = 0
    positions = db.scalars(select(Position).where(Position.status == "active")).all()
    for p in positions:
        if p.department_id is None and p.title in LEADERSHIP_ROLE_POSITIONS and "Leadership" in roles:
            added += _grant_once(db, chair, "position", p.id, "global", None, role=roles["Leadership"])
        if p.department_id is None and p.title in RECRUITER_POSITIONS:
            for code in RECRUITER_PERMISSIONS:
                added += _grant_once(db, chair, "position", p.id, "global", None, permission=code)
        if p.department_id is not None and p.is_lead and "Department Lead" in roles:
            added += _grant_once(db, chair, "position", p.id, "department", p.department_id,
                                 role=roles["Department Lead"])
    if "Member" in roles:
        for d in db.scalars(select(Department).where(Department.status == "active")):
            added += _grant_once(db, chair, "department", d.id, "department", d.id, role=roles["Member"])
    return added


def sync_defaults() -> None:
    """Bring an existing installation up to the current defaults. Only ever adds: missing
    permissions on the default roles, and missing default grants. Never removes anything."""
    from app.permissions import engine

    with SessionLocal() as db:
        sync_catalogue(db)
        for name, (description, codes) in DEFAULT_ROLES.items():
            role = db.scalar(select(Role).where(Role.name == name))
            if role is None:
                role = Role(name=name, description=description)
                db.add(role)
                db.flush()
                missing = codes
            else:
                have = set(db.scalars(select(RolePermission.permission_code).where(RolePermission.role_id == role.id)))
                missing = [c for c in codes if c not in have]
            if missing:
                db.add_all(RolePermission(role_id=role.id, permission_code=c) for c in missing)
                db.add(PermissionAudit(action="role_update", subject_type="role", subject_id=role.id,
                                       role_id=role.id, reason="Default permissions added by sync-defaults",
                                       new_value={"added": sorted(missing)}))
                print(f"{name}: added {', '.join(sorted(missing))}")
        chair = db.scalar(select(User).where(User.is_super_admin))
        if chair is None:
            sys.exit("No super admin yet: run create-superadmin first.")
        print(f"Default grants added: {apply_default_grants(db, chair)}")
        engine.clear_cache(db)
        db.commit()


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
    sub.add_parser("sync-defaults")
    args = parser.parse_args()

    if args.command == "create-superadmin":
        create_superadmin(args.email, args.name, args.password)
    elif args.command == "seed-roles":
        seed_roles()
    elif args.command == "seed-org":
        seed_org()
    elif args.command == "db-check":
        db_check()
    elif args.command == "sync-defaults":
        sync_defaults()
    elif args.command == "expire-grants":
        with SessionLocal() as db:
            print(f"Expired grants marked: {expire_grants(db)}")


if __name__ == "__main__":
    main()
