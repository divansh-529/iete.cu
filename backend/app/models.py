"""Imports every model module so Base.metadata is complete (used by Alembic and tests)."""
from app.audit.models import AuditEvent  # noqa: F401
from app.auth.models import LoginAttempt, UserSession  # noqa: F401
from app.events.models import (Event, EventChecklistItem, EventDepartment, EventMilestone,  # noqa: F401
                               EventStatusHistory, EventTeamMember)
from app.notifications.models import Notification  # noqa: F401
from app.org.models import (Department, DepartmentMembership, MemberProfile, Position,  # noqa: F401
                            PositionAssignment, Term)
from app.permissions.models import Grant, Permission, PermissionAudit, Role, RolePermission  # noqa: F401
from app.settings.models import Setting  # noqa: F401
from app.tasks.models import (Task, TaskAssignee, TaskComment, TaskDependency,  # noqa: F401
                              TaskStatusHistory, TaskSubmission)
from app.users.models import InviteToken, User  # noqa: F401
