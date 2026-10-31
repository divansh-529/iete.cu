"""The fixed list of permission codes. Synced into the `permissions` table at startup.

Sensitive permissions can only be granted directly to a user (never via a role,
position or department). See docs/02-permissions.md.
"""
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class PermissionDef:
    code: str
    description: str
    sensitive: bool = False

    @property
    def module(self) -> str:
        return self.code.split(".", 1)[0]


S = True
_DEFS = [
    # Users
    PermissionDef("users.view", "View team accounts"),
    PermissionDef("users.create", "Create team accounts", S),
    PermissionDef("users.edit", "Edit team account details", S),
    PermissionDef("users.suspend", "Suspend, reactivate or deactivate accounts", S),
    PermissionDef("users.reset_password", "Set a new temporary password for a user", S),
    # Permissions
    PermissionDef("permissions.view", "View roles, grants and effective access", S),
    PermissionDef("permissions.manage", "Grant and revoke permissions", S),
    PermissionDef("roles.manage", "Create and edit roles", S),
    # Org
    PermissionDef("org.view", "View departments, positions and the org chart"),
    PermissionDef("org.manage", "Create and edit departments and positions"),
    PermissionDef("org.assign", "Assign members to positions and departments"),
    # Tasks
    PermissionDef("tasks.view", "View tasks"),
    PermissionDef("tasks.create", "Create and edit tasks"),
    PermissionDef("tasks.assign", "Assign tasks"),
    PermissionDef("tasks.review", "Review task submissions"),
    PermissionDef("tasks.export", "Export task lists"),
    # Events
    PermissionDef("events.view", "View events"),
    PermissionDef("events.create", "Create events"),
    PermissionDef("events.edit", "Edit events and their workspace"),
    PermissionDef("events.approve", "Approve or reject event proposals", S),
    PermissionDef("events.archive", "Archive events"),
    # Documents
    PermissionDef("documents.view", "View and download documents"),
    PermissionDef("documents.upload", "Upload documents and new versions"),
    PermissionDef("documents.review", "Change document review status"),
    PermissionDef("documents.delete", "Delete documents (soft delete)", S),
    PermissionDef("documents.manage_folders", "Create and edit folders"),
    # Points
    PermissionDef("points.view", "View points history"),
    PermissionDef("points.evaluate", "Submit point evaluations"),
    PermissionDef("points.approve", "Approve, adjust, reject or return evaluations", S),
    PermissionDef("points.adjust", "Correct approved points", S),
    PermissionDef("points.leaderboard.view", "View leaderboards"),
    # Finance
    PermissionDef("finance.view", "View finance records and balances", S),
    PermissionDef("finance.income.record", "Record income", S),
    PermissionDef("finance.expense.submit", "Submit expenses"),
    PermissionDef("finance.expense.verify", "Verify submitted expenses", S),
    PermissionDef("finance.expense.approve", "Approve expenses and reversals", S),
    PermissionDef("finance.accounts.manage", "Manage accounts and transfers", S),
    PermissionDef("finance.reconcile", "Record bank reconciliations", S),
    PermissionDef("finance.export", "Export finance data", S),
    # Membership
    PermissionDef("membership.view", "View membership records", S),
    PermissionDef("membership.record", "Record memberships and payments", S),
    PermissionDef("membership.export", "Export membership data", S),
    # Participants
    PermissionDef("registrations.view", "View event registrations"),
    PermissionDef("registrations.review", "Approve or reject registrations"),
    PermissionDef("registrations.export", "Export participant data", S),
    PermissionDef("attendance.record", "Record attendance"),
    PermissionDef("attendance.correct", "Correct attendance records"),
    PermissionDef("certificates.upload", "Upload certificates"),
    # Comms
    PermissionDef("announcements.publish", "Publish announcements"),
    PermissionDef("meetings.manage", "Manage meetings and minutes"),
    PermissionDef("campaigns.manage", "Manage promotion campaigns"),
    # Reports, audit, settings
    PermissionDef("reports.view", "View reports and dashboards"),
    PermissionDef("reports.export", "Export reports"),
    PermissionDef("audit.view", "View the audit log", S),
    PermissionDef("settings.manage", "Change system settings", S),
]

CATALOGUE: dict[str, PermissionDef] = {p.code: p for p in _DEFS}


def sync_catalogue(db: Session) -> None:
    from app.permissions.models import Permission

    rows = [{"code": p.code, "module": p.module, "description": p.description,
             "sensitive": p.sensitive} for p in _DEFS]
    stmt = insert(Permission).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Permission.code],
        set_={"module": stmt.excluded.module, "description": stmt.excluded.description,
              "sensitive": stmt.excluded.sensitive},
    )
    db.execute(stmt)
    db.commit()
