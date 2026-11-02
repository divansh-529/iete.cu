# 02 — Permissions Model

Blueprint §5 makes this a core requirement: **a designation alone never grants broad access**. The Chairperson and authorised admins grant permissions explicitly, by user, role, position or department, and can scope each grant to part of the system.

## 1. Building blocks

| Concept | What it is | Example |
|---|---|---|
| **Permission** | A fixed action code defined in code and seeded into the DB | `events.create`, `finance.expense.approve` |
| **Sensitive flag** | Marks permissions that must be granted explicitly to a user and can never arrive through a role, position or department | `finance.*`, `users.*`, `permissions.manage`, `points.approve` |
| **Role** | A named bundle of permissions that admins can edit | "Department Lead (standard)", "Event Coordinator" |
| **Subject** | The holder of a grant | a user, a role, a position (e.g. "Secretary") or a department |
| **Scope** | Where the grant applies | `global`, `department:7`, `event:42`, `folder:310`, `finance_account:2`, `record:task:991` |
| **Grant** | Subject + (permission or role) + scope + optional expiry | "Ops Lead position → role *Dept Lead* → scope department:Operations" |
| **Super Admin** | A boolean on the Chairperson's user that bypasses checks. Every action is still audited. | — |

Positions belong to the org structure ([03-data-model.md](03-data-model.md) §2). Granting to a **position** means that whoever holds the position gets the access, and loses it automatically when they are moved off it. This reflects how a student forum works, where the role persists across terms and the people change.

## 2. Permission catalogue (initial)

`S` marks a sensitive permission.

| Module | Permission codes |
|---|---|
| Users | `users.create` S, `users.edit` S, `users.suspend` S, `users.reset_password` S, `users.approve` |
| Permissions | `permissions.view` S, `permissions.manage` S, `roles.manage` S |
| Org | `org.view`, `org.manage` (departments, positions), `org.assign` (move or assign members) |
| Tasks | `tasks.view`, `tasks.create`, `tasks.assign`, `tasks.review`, `tasks.export` |
| Events | `events.view`, `events.create`, `events.edit`, `events.review`, `events.approve` S, `events.archive` |
| Documents | `documents.view`, `documents.upload`, `documents.review`, `documents.delete` S, `documents.manage_folders` |
| Points | `points.view`, `points.evaluate`, `points.approve` S, `points.adjust` S, `points.leaderboard.view` |
| Finance | `finance.view` S, `finance.income.record` S, `finance.expense.submit`, `finance.expense.verify` S, `finance.expense.approve` S, `finance.accounts.manage` S, `finance.reconcile` S, `finance.export` S |
| Membership | `membership.view` S, `membership.record` S, `membership.export` S |
| Participants | `registrations.view`, `registrations.review`, `registrations.export` S, `attendance.record`, `attendance.correct`, `certificates.upload` |
| Comms | `announcements.publish`, `meetings.manage`, `campaigns.manage` |
| Reports | `reports.view`, `reports.export` |
| Audit | `audit.view` S |
| Settings | `settings.manage` S |

**Recruiting with approval** (Chairperson's requirement, 2026-11-01). `users.create` stays sensitive and lets the Chairperson add accounts directly. Everyone else recruits through proposals:

1. A holder of `org.assign` on a department (its Lead; the Vice Chairperson and Secretary everywhere) proposes a candidate with `POST /departments/{id}/member-proposals`. The account is created as `proposed` and cannot sign in.
2. A holder of `users.approve` (the Chairperson; the Vice Chairperson and Secretary by default, through their positions) approves or rejects it. Nobody decides on a member they proposed themselves, except the super admin. Rejection needs a reason, and a rejected candidate can be proposed again later.
3. On approval the account gets the forum's default first password (`IETE_DEFAULT_MEMBER_PASSWORD`, `CU@12345678` by default), joins the department and the chosen position, and the candidate is emailed their sign-in details. They must change the password at first sign-in, and cannot choose the default one.

`users.approve` is deliberately not sensitive, so that it can sit on the Vice Chairperson and Secretary positions and pass to whoever holds them. Every proposal and decision is kept (`member_proposals`) and audited.

**Leads staff members, not leads.** Filling, ending or transferring into or out of a lead or deputy position needs `org.manage` at that scope as well as `org.assign`. A department lead (who has `org.assign` only) can therefore recruit and place ordinary members, but cannot appoint, promote someone into, or remove a lead or deputy.

`finance.expense.submit` is deliberately **not** sensitive. Anyone allowed to spend must be able to record the spend (blueprint §10.4).

## 3. Scope matching

A grant at scope **G** covers a request at scope **R** when:

```
G.type == 'global'                                     → covers everything
G == R                                                 → exact match
G.type == 'department' and R belongs to that department → e.g. a task or event owned by the dept
G.type == 'event' and R belongs to that event           → e.g. the event's folders, tasks, registrations
G.type == 'folder' and R is the folder or a descendant
```

`belongs to` is resolved by the service layer with a small function per resource type, such as `task → department_id, event_id`.

## 4. The check algorithm

```python
def can(user, perm: str, scope: Scope) -> bool:
    if user.status != "active":            return False
    if user.is_super_admin:                return True
    p = catalogue[perm]
    grants = active_grants_for(user)       # cached per request
    for g in grants:
        if g.expires_at and g.expires_at <= now(): continue
        if p.sensitive and g.subject_type != "user": continue  # sensitive ⇒ direct grant only
        if not (g.permission == perm or (g.role and perm in role_perms[g.role])): continue
        if covers(g.scope, scope): return True
    return False                            # deny by default
```

`active_grants_for(user)` returns the union of:
1. Grants where `subject = user`.
2. Grants where `subject = position P`, for every **current** position assignment of the user.
3. Grants where `subject = department D`, for every department the user is currently a member of.
4. Grants where `subject = role R`, for roles assigned directly to the user (role assignment is itself a user grant of the role).

The user's grants are loaded once per request with a single SQL query (UNION ALL over the four sources) and memoised.

## 5. Row filtering for lists

`can()` answers questions about a single item. List endpoints build a filter from the same grants instead:

```python
def visible_scope_ids(user, perm, scope_type) -> AllOrIds
# returns ALL if any matching global grant, else the set of department/event ids
```

The query then adds `WHERE department_id = ANY(:ids) OR event_id = ANY(:ids2)`. The same grant data drives both paths, so the two can never disagree.

## 6. Anti-escalation rules (enforced in `permissions/service.py`)

1. **No self-grants.** A user cannot create, edit or revoke a grant where the subject is themselves, a position they hold, or a department they belong to.
2. **Delegation ceiling.** A non-super-admin with `permissions.manage` can only grant permissions they themselves hold, at a scope no wider than their own.
3. **Sensitive permissions are granted to users only.** The API rejects any attempt to put a sensitive permission into a role, or to grant one to a position or department.
4. **Approval chain.** Workflow services check *who* is acting as well as *whether* they hold the permission. For example, the person who submitted an expense cannot verify or approve the same expense, even when they hold those permissions.
5. **Super Admin can only be transferred** by the current Super Admin, through a confirm-twice flow. The transfer is audited.

## 7. Permission audit (blueprint §5.3)

Every create, update or revoke of a grant, role, or role-permission membership writes a `permission_audit` row inside the same transaction:

| Field | Meaning |
|---|---|
| `actor_id` | Who made the change |
| `subject_type`, `subject_id` | Whose access changed |
| `permission_code` / `role_id` | What changed |
| `scope_type`, `scope_id` | Where it applies |
| `action` | `grant` / `revoke` / `modify` / `expire` |
| `old_value`, `new_value` | JSONB snapshots |
| `reason` | Required free-text field |
| `created_at` | Timestamp |

A nightly job marks expired grants with an `expire` audit row, so the history shows exactly when access ended.

## 8. Illustrative default setup (matches blueprint §5.2; all editable)

| Grant | Subject | Scope |
|---|---|---|
| Super Admin flag | Chairperson user | — |
| Role "Leadership" (`org.view`, `events.*` except approve, including `events.review`, `tasks.*`, `documents.view/upload/review`, `points.evaluate`, `reports.view`) | Positions: Vice Chair, Secretary, Joint Secretary | global |
| `org.assign`, `users.approve` (recruit anywhere, approve new accounts) | Positions: Vice Chair, Secretary (equal powers) | global |
| Role "Department Lead" (`org.view`, `org.assign`, `tasks.*`, `events.view/create/edit`, `documents.view/upload`) | Each Lead position | that position's department |
| Role "Member" (`tasks.view`, `events.view`, `events.create`, `documents.view`) | Each department | that department |

`python -m app.cli seed-org` applies these grants on a new install; `python -m app.cli sync-defaults` adds any that are missing on an existing one (it never removes anything).

**Events and tasks also follow involvement.** An event's owner runs its workspace and its tasks; its team can see it. A task's assignees, reviewer and creator can always see it. Approval chain rules: the event owner cannot forward or approve their own proposal, and a reviewer cannot review their own task submission.
| `finance.view`, `finance.income.record`, `finance.expense.verify`, `membership.*` | Treasurer **user** (sensitive, so a direct grant) | global |
| `finance.view`, `finance.expense.approve` | Vice Chair **user** (if configured) | global |
| `points.evaluate` | VC and Secretary positions | per the evaluator map |
