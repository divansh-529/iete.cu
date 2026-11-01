// Mirrors the Pydantic schemas in backend/app/*/schemas.py.

export type UserStatus = "proposed" | "rejected" | "invited" | "active" | "suspended" | "deactivated";

export interface User {
  id: number;
  email: string;
  full_name: string;
  user_type: string;
  status: UserStatus;
  must_change_password: boolean;
  is_super_admin: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface EffectivePermission {
  code: string;
  scope_type: string;
  scope_id: number | null;
}

export interface Me {
  user: User;
  permissions: EffectivePermission[];
  all_permissions: boolean;
}

export interface UserPage {
  items: User[];
  total: number;
}

export interface Permission {
  code: string;
  module: string;
  description: string;
  sensitive: boolean;
}

export interface Role {
  id: number;
  name: string;
  description: string | null;
  permissions: string[];
  active_grant_count: number;
}

export type SubjectType = "user" | "position" | "department";

export interface Grant {
  id: number;
  subject_type: SubjectType;
  subject_id: number;
  permission_code: string | null;
  role_id: number | null;
  role_name: string | null;
  scope_type: string;
  scope_id: number | null;
  scope_name: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  granted_by: number;
  granted_by_name: string | null;
  reason: string;
  created_at: string;
  active: boolean;
}

export interface EffectiveAccess {
  all_permissions: boolean;
  permissions: (EffectivePermission & { via_role: string | null; via_subject: string | null; grant_id: number })[];
}

// ---------------------------------------------------------------- organisation

export interface PersonRef {
  id: number;
  full_name: string;
  email: string;
}

export interface Department {
  id: number;
  name: string;
  description: string | null;
  parent_id: number | null;
  status: "active" | "archived";
  member_count: number;
  position_count: number;
  vacant_positions: number;
  leads: PersonRef[];
}

export interface Holder {
  assignment_id: number;
  user: PersonRef;
  valid_from: string;
}

export interface Position {
  id: number;
  title: string;
  description: string | null;
  department_id: number | null;
  department_name: string | null;
  reports_to_position_id: number | null;
  is_lead: boolean;
  is_deputy: boolean;
  max_holders: number;
  rank_order: number;
  status: "active" | "archived";
  holders: Holder[];
}

export interface Assignment {
  id: number;
  user: PersonRef;
  position_id: number;
  position_title: string;
  department_id: number | null;
  department_name: string | null;
  valid_from: string;
  valid_to: string | null;
  start_reason: string;
  end_reason: string | null;
  note: string | null;
}

export interface Membership {
  id: number;
  user: PersonRef;
  department_id: number;
  department_name: string;
  valid_from: string;
  valid_to: string | null;
  end_reason: string | null;
}

export interface DepartmentDetail extends Department {
  positions: Position[];
  members: Membership[];
  created_at: string;
}

export interface Profile {
  uid: string | null;
  phone: string | null;
  branch: string | null;
  year_of_study: number | null;
  joined_on: string | null;
  lifecycle_status: "onboarding" | "probation" | "active" | "alumni" | "removed";
  responsibilities: string | null;
}

export interface UserOrg {
  user: PersonRef;
  profile: Profile;
  positions: Assignment[];
  memberships: Membership[];
}

export interface ChartNode {
  position_id: number;
  title: string;
  department_id: number | null;
  department_name: string | null;
  reports_to_position_id: number | null;
  is_lead: boolean;
  is_deputy: boolean;
  max_holders: number;
  holders: PersonRef[];
}

export interface Term {
  id: number;
  name: string;
  starts_on: string;
  ends_on: string;
  is_current: boolean;
}

// ---------------------------------------------------------------- events

export type EventStatus = "draft" | "proposed" | "awaiting_approval" | "approved" | "open_for_registration"
  | "ongoing" | "completed" | "cancelled" | "archived";

export interface Ref {
  id: number;
  name: string;
}

export interface EventSummary {
  id: number;
  name: string;
  slug: string;
  category: string | null;
  status: EventStatus;
  venue: string | null;
  starts_at: string | null;
  ends_at: string | null;
  owner: PersonRef;
  departments: Ref[];
  team_size: number;
  open_tasks: number;
  created_at: string;
}

export interface StatusChange {
  from_status: string | null;
  to_status: string;
  changed_by: PersonRef;
  remarks: string | null;
  changed_at: string;
}

export interface AllowedTransition {
  to_status: EventStatus;
  label: string;
  needs_remarks: boolean;
  tone: "primary" | "secondary" | "danger";
}

export interface EventDetail extends EventSummary {
  description: string | null;
  capacity: number | null;
  budget_planned: string | null;
  is_public: boolean;
  team: { id: number; user: PersonRef; event_role: string; added_at: string }[];
  milestones: { id: number; title: string; due_at: string | null; done_at: string | null }[];
  checklist: { id: number; label: string; sort_order: number; done_at: string | null; done_by: PersonRef | null }[];
  history: StatusChange[];
  allowed_transitions: AllowedTransition[];
  can_edit: boolean;
  can_manage: boolean;
  can_add_tasks: boolean;
}

// ---------------------------------------------------------------- tasks

export type TaskStatus = "not_started" | "assigned" | "in_progress" | "submitted" | "under_review" | "completed" | "rejected";
export type TaskPriority = "low" | "medium" | "high" | "urgent";
export type TaskAction = "comment" | "edit" | "assign" | "start" | "submit" | "review" | "reopen";

export interface TaskSummary {
  id: number;
  title: string;
  priority: TaskPriority;
  status: TaskStatus;
  due_at: string | null;
  overdue: boolean;
  department: Ref | null;
  event: Ref | null;
  assignees: PersonRef[];
  reviewer: PersonRef | null;
  created_at: string;
  updated_at: string;
}

export interface TaskDetail extends TaskSummary {
  description: string | null;
  created_by: PersonRef;
  depends_on: { id: number; title: string; status: TaskStatus }[];
  blocked: boolean;
  submissions: {
    id: number; submitted_by: PersonRef; note: string | null; link_url: string | null; submitted_at: string;
    review_outcome: "accepted" | "changes_requested" | "rejected" | null; reviewed_by: PersonRef | null;
    review_remarks: string | null; reviewed_at: string | null;
  }[];
  comments: { id: number; author: PersonRef; body: string; created_at: string }[];
  history: StatusChange[];
  actions: TaskAction[];
}

// ---------------------------------------------------------------- recruitment

export interface MemberProposal {
  id: number;
  person: PersonRef;
  account_status: UserStatus;
  department: Ref;
  position: Ref | null;
  note: string | null;
  status: "pending" | "approved" | "rejected";
  proposed_by: PersonRef;
  created_at: string;
  decided_by: PersonRef | null;
  decided_at: string | null;
  decision_remarks: string | null;
  email_sent_at: string | null;
  can_decide: boolean;
}

export interface ProposalDecision {
  proposal: MemberProposal;
  email_sent: boolean | null;
  login_url: string;
  default_password: string;
}

// ---------------------------------------------------------------- score cards

export interface ScoreRound {
  id: number;
  title: string;
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
  cards: number;
  entries_given: number;
  entries_expected: number;
}

export interface ScoreSlot {
  slot: string;
  label: string;
  max_points: string;
  points: string | null;
  remarks: string | null;
  scored_by: PersonRef | null;
  given: boolean;
  editable: boolean;
}

export interface ScoreCard {
  card_id: number;
  person: PersonRef;
  category: string;
  category_label: string;
  department: Ref | null;
  slots: ScoreSlot[];
  total: string;
  max_total: string;
}

export interface ToScore {
  round: ScoreRound;
  cards: ScoreCard[];
  my_given: number;
  my_expected: number;
}

export interface PersonScores {
  person: PersonRef;
  cards: (ScoreCard & { round_id: number; round_title: string; closed_at: string | null })[];
  total: string;
  max_total: string;
}

export interface LeaderboardRow {
  person: PersonRef;
  category_label: string;
  department: string | null;
  rounds: number;
  total: string;
  max_total: string;
  latest: string;
}

// ---------------------------------------------------------------- notifications

export interface AppNotification {
  id: number;
  kind: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPage {
  items: AppNotification[];
  unread: number;
}

export interface AuditEvent {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

export interface PermissionAuditRow {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  subject_type: string | null;
  subject_id: number | null;
  subject_name: string | null;
  permission_code: string | null;
  role_id: number | null;
  scope_type: string | null;
  scope_id: number | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}
