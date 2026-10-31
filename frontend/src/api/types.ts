// Mirrors the Pydantic schemas in backend/app/*/schemas.py.

export type UserStatus = "invited" | "active" | "suspended" | "deactivated";

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
