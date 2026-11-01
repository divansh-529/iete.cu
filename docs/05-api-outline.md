# 05 — API Outline

All endpoints sit under `/api`, and the request and response bodies are JSON. **Perm** is the permission that `require()` checks, and **scope** is how the request's scope is derived. `public` means no session is needed. `self` means the caller can only act on their own records.

## Auth
| Method | Path | Perm | Notes |
|---|---|---|---|
| POST | `/auth/login` | public | Rate-limited. Sets the session and CSRF cookies. |
| POST | `/auth/logout` | session | Deletes the session row |
| GET | `/auth/me` | session | User, positions and effective permissions (UI hints only) |
| POST | `/auth/change-password` | session | Requires the current password, except for the forced first-time change (the person has just signed in with it). Clears `must_change_password` and moves `invited` to `active`. |
| POST | `/auth/accept-invite` | public (token) | Sets the first password from an invite link |

While `must_change_password` is true, every other endpoint returns `403 PASSWORD_CHANGE_REQUIRED`.

## Users & profiles
| Method | Path | Perm |
|---|---|---|
| GET | `/users` | `users.view` |
| POST | `/users` (with invite link or temporary password) | `users.create` |
| PATCH | `/users/{id}` | `users.edit` |
| POST | `/users/{id}/suspend` · `/reactivate` · `/deactivate` | `users.suspend` |
| POST | `/users/{id}/reset-password` (admin sets a new temporary password) | `users.reset_password` |
| GET/PATCH | `/users/{id}/profile` | `users.view`/`users.edit`, or self for limited fields |

## Org
| Method | Path | Perm (scope) |
|---|---|---|
| GET | `/org/chart` | `org.view` |
| CRUD | `/departments`, `/departments/{id}/archive` | `org.manage` |
| CRUD | `/positions` | `org.manage` (department) |
| POST | `/positions/{id}/assign` · `/positions/assignments/{id}/end` | `org.assign` (department) |
| POST | `/departments/{id}/members` · `DELETE …/{userId}` | `org.assign` (department) |
| GET | `/users/{id}/history` | `org.view` |

## Permissions
| Method | Path | Perm |
|---|---|---|
| GET | `/permissions` (catalogue) | `permissions.view` |
| CRUD | `/roles`, `/roles/{id}/permissions` | `roles.manage` |
| GET/POST | `/grants` | `permissions.view` / `permissions.manage` |
| POST | `/grants/{id}/revoke` | `permissions.manage` |
| GET | `/grants/effective?user_id=` | `permissions.view` |
| GET | `/permission-audit` | `audit.view` |

## Tasks
| Method | Path | Perm (scope) |
|---|---|---|
| GET | `/tasks?department=&event=&status=&assignee=` | `tasks.view` (row-filtered) |
| GET | `/tasks/mine` | self |
| POST/PATCH | `/tasks`, `/tasks/{id}` | `tasks.create` (dept/event) |
| POST | `/tasks/{id}/assign` | `tasks.assign` |
| POST | `/tasks/{id}/status` | assignee (own transitions) or `tasks.review` |
| POST | `/tasks/{id}/submissions` | assignee |
| POST | `/tasks/{id}/submissions/{sid}/review` | `tasks.review` + must be the reviewer |
| GET/POST | `/tasks/{id}/comments` | `tasks.view` |

## Events
| Method | Path | Perm (scope) |
|---|---|---|
| GET | `/events` | `events.view` (row-filtered) |
| POST | `/events` | `events.create` |
| PATCH | `/events/{id}` | `events.edit` (event) |
| POST | `/events/{id}/transition` `{to_status, remarks}` | `events.edit`. `events.approve` for approve/reject. |
| CRUD | `/events/{id}/team`, `/milestones`, `/checklist`, `/departments` | `events.edit` (event) |
| POST | `/events/{id}/archive` | `events.archive` |

## Documents
| Method | Path | Perm (scope) |
|---|---|---|
| GET | `/folders?event=` · `/folders/{id}` | `documents.view` (folder) |
| CRUD | `/folders` | `documents.manage_folders` |
| POST | `/documents/upload-url` returns a presigned PUT URL | `documents.upload` (folder) |
| POST | `/documents` (commit metadata after upload) | `documents.upload` |
| POST | `/documents/{id}/versions` | `documents.upload` |
| POST | `/documents/{id}/review` | `documents.review` |
| GET | `/documents/{id}/download` returns a presigned GET URL | `documents.view` |
| DELETE | `/documents/{id}` (soft delete) | `documents.delete` |
| GET | `/documents/search?q=&category=&status=&event=` | `documents.view` (row-filtered) |

## Points
| Method | Path | Perm |
|---|---|---|
| CRUD | `/evaluator-map` | `points.approve` |
| POST | `/events/{id}/evaluations/open` | `points.approve` or `events.edit` |
| GET | `/evaluations?mine=1` | `points.evaluate` (only the evaluatees in the caller's evaluator map) |
| POST | `/evaluations/{id}/submissions` | `points.evaluate` + evaluator map match |
| POST | `/evaluations/{id}/decision` `{outcome, final_score, reason}` | `points.approve` |
| POST | `/points-ledger/{id}/adjust` | `points.adjust` |
| GET | `/leaderboard?scope=overall|department|event&period=month|semester|year|term` | `points.leaderboard.view` |
| GET | `/points/users/{id}` | `points.view`, or self |

## Finance & membership
| Method | Path | Perm |
|---|---|---|
| CRUD | `/finance/accounts` | `finance.accounts.manage` |
| GET | `/finance/accounts/balances` | `finance.view` |
| GET | `/finance/transactions?account=&event=&status=&from=&to=` | `finance.view` |
| POST | `/finance/income` | `finance.income.record` |
| POST | `/finance/expenses` | `finance.expense.submit` |
| POST | `/finance/expenses/{id}/verify` · `/approve` · `/reject` | `finance.expense.verify` / `.approve` (≠ submitter) |
| POST | `/finance/transfers` | `finance.accounts.manage` |
| POST | `/finance/transactions/{id}/reverse` | `finance.expense.approve` + reason (≠ original submitter) |
| CRUD | `/finance/reconciliations` | `finance.reconcile` |
| GET | `/finance/export` | `finance.export` |
| CRUD | `/membership/categories` | `membership.record` |
| GET/POST/PATCH | `/memberships` | `membership.view` / `membership.record` |
| GET | `/memberships/summary` | `membership.view` |

## Participants (public + participant area)
| Method | Path | Perm |
|---|---|---|
| GET | `/public/events` · `/public/events/{slug}` | public |
| POST | `/public/participants/signup` | public, only if enabled in settings |
| POST | `/public/events/{slug}/register` | public or participant session, depending on the form setting |
| GET | `/me/registrations` · `/me/certificates` | self (participant) |
| GET | `/events/{id}/registrations` | `registrations.view` (event) |
| POST | `/registrations/{id}/review` | `registrations.review` |
| GET | `/events/{id}/registrations/export` | `registrations.export` |
| CRUD | `/events/{id}/registration-form` | `events.edit` |

## Attendance & certificates
| Method | Path | Perm |
|---|---|---|
| POST | `/events/{id}/attendance` (manual, bulk) | `attendance.record` |
| POST | `/events/{id}/attendance/scan` `{reg_code}` | `attendance.record` |
| POST | `/attendance/{id}/correct` | `attendance.correct` |
| POST | `/registrations/{id}/certificate` | `certificates.upload` |

## Comms
| Method | Path | Perm |
|---|---|---|
| CRUD | `/announcements` | `announcements.publish` |
| CRUD | `/meetings` | `meetings.manage` |
| CRUD | `/campaigns`, `/campaigns/{id}/posts` | `campaigns.manage` |
| GET | `/notifications` · POST `/notifications/read` | self |

## Reports, audit, settings
| Method | Path | Perm |
|---|---|---|
| GET | `/reports/dashboard` (Chairperson overview; each widget checks its own permission) | `reports.view` |
| GET | `/reports/{org|tasks|events|performance|finance|documents}` | `reports.view` + module permission |
| GET | `/reports/{name}/export` | `reports.export` |
| GET | `/audit?entity=&actor=&from=` | `audit.view` |
| GET/PUT | `/settings/{key}` | `settings.manage` |
