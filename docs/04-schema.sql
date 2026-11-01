-- =====================================================================
-- IETE Student Forum ERP — PostgreSQL schema DRAFT (PostgreSQL 15+)
-- Design reference only. Production schema will be built via Alembic
-- migrations, phase by phase (see 06-roadmap.md).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS citext;

-- ---------------------------------------------------------------------
-- Shared: append-only guard
-- ---------------------------------------------------------------------
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% on % is not allowed (append-only table)', TG_OP, TG_TABLE_NAME;
END $$;

-- =====================================================================
-- 1. IDENTITY & ACCESS
-- =====================================================================
CREATE TABLE users (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email                 citext NOT NULL UNIQUE,
  full_name             text   NOT NULL,
  password_hash         text,                       -- null until invite accepted
  user_type             text   NOT NULL CHECK (user_type IN ('team','participant')),
  status                text   NOT NULL DEFAULT 'invited'
                        CHECK (status IN ('invited','active','suspended','deactivated')),
  must_change_password  boolean NOT NULL DEFAULT true,
  is_super_admin        boolean NOT NULL DEFAULT false,
  failed_login_count    int     NOT NULL DEFAULT 0,
  locked_until          timestamptz,
  last_login_at         timestamptz,
  created_by            bigint REFERENCES users(id),
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);
-- At most one super admin
CREATE UNIQUE INDEX one_super_admin ON users ((true)) WHERE is_super_admin;

CREATE TABLE invite_tokens (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id),
  token_hash  bytea  NOT NULL UNIQUE,
  expires_at  timestamptz NOT NULL,
  used_at     timestamptz,
  created_by  bigint NOT NULL REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id      bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash   bytea  NOT NULL UNIQUE,
  created_at   timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  ip           inet,
  user_agent   text
);
CREATE INDEX ON sessions (user_id);

CREATE TABLE login_attempts (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email       citext,
  ip          inet,
  success     boolean NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON login_attempts (ip, created_at);
CREATE INDEX ON login_attempts (email, created_at);

CREATE TABLE permissions (
  code        text PRIMARY KEY,                    -- e.g. 'finance.expense.approve'
  module      text NOT NULL,
  description text NOT NULL,
  sensitive   boolean NOT NULL DEFAULT false
);

CREATE TABLE roles (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        text NOT NULL UNIQUE,
  description text,
  created_by  bigint REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE role_permissions (
  role_id         bigint NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_code text   NOT NULL REFERENCES permissions(code),
  PRIMARY KEY (role_id, permission_code)
);
-- Sensitive permissions may not be bundled into roles
CREATE FUNCTION role_perm_not_sensitive() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (SELECT sensitive FROM permissions WHERE code = NEW.permission_code) THEN
    RAISE EXCEPTION 'Sensitive permission % cannot be added to a role', NEW.permission_code;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_role_perm_not_sensitive BEFORE INSERT OR UPDATE ON role_permissions
  FOR EACH ROW EXECUTE FUNCTION role_perm_not_sensitive();

CREATE TABLE grants (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  subject_type    text   NOT NULL CHECK (subject_type IN ('user','role','position','department')),
  subject_id      bigint NOT NULL,
  permission_code text   REFERENCES permissions(code),
  role_id         bigint REFERENCES roles(id),
  scope_type      text   NOT NULL DEFAULT 'global'
                  CHECK (scope_type IN ('global','department','event','folder','finance_account','record')),
  scope_id        bigint,
  scope_record_type text,                           -- only when scope_type = 'record'
  expires_at      timestamptz,
  revoked_at      timestamptz,
  revoked_by      bigint REFERENCES users(id),
  granted_by      bigint NOT NULL REFERENCES users(id),
  reason          text   NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK ((permission_code IS NULL) <> (role_id IS NULL)),
  CHECK ((scope_type = 'global') = (scope_id IS NULL))
);
CREATE INDEX ON grants (subject_type, subject_id) WHERE revoked_at IS NULL;

CREATE TABLE permission_audit (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id        bigint REFERENCES users(id),     -- null = system (expiry job)
  action          text   NOT NULL CHECK (action IN ('grant','revoke','modify','expire',
                                                    'role_create','role_update','role_delete')),
  subject_type    text,
  subject_id      bigint,
  permission_code text,
  role_id         bigint,
  scope_type      text,
  scope_id        bigint,
  old_value       jsonb,
  new_value       jsonb,
  reason          text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_permission_audit_ro BEFORE UPDATE OR DELETE ON permission_audit
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- =====================================================================
-- 2. ORGANISATION
-- =====================================================================
CREATE TABLE terms (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       text NOT NULL UNIQUE,                 -- '2026-27'
  starts_on  date NOT NULL,
  ends_on    date NOT NULL,
  is_current boolean NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX one_current_term ON terms ((true)) WHERE is_current;

CREATE TABLE departments (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        text NOT NULL UNIQUE,
  description text,
  parent_id   bigint REFERENCES departments(id),
  status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  created_by  bigint REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE positions (
  id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title                  text NOT NULL,
  department_id          bigint REFERENCES departments(id),   -- null = leadership/org-level
  reports_to_position_id bigint REFERENCES positions(id),
  is_lead                boolean NOT NULL DEFAULT false,
  is_deputy              boolean NOT NULL DEFAULT false,
  max_holders            int NOT NULL DEFAULT 1 CHECK (max_holders > 0),
  rank_order             int NOT NULL DEFAULT 100,
  status                 text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
  created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE position_assignments (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id),
  position_id bigint NOT NULL REFERENCES positions(id),
  valid_from  date   NOT NULL,
  valid_to    date,                                -- null = current
  start_reason text  NOT NULL CHECK (start_reason IN ('appointed','promoted','transferred','reinstated')),
  end_reason   text  CHECK (end_reason IN ('promoted','transferred','resigned','removed','term_ended')),
  assigned_by bigint NOT NULL REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE INDEX ON position_assignments (user_id) WHERE valid_to IS NULL;
CREATE INDEX ON position_assignments (position_id) WHERE valid_to IS NULL;

CREATE TABLE department_memberships (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id       bigint NOT NULL REFERENCES users(id),
  department_id bigint NOT NULL REFERENCES departments(id),
  valid_from    date NOT NULL,
  valid_to      date,
  assigned_by   bigint NOT NULL REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE UNIQUE INDEX one_open_membership ON department_memberships (user_id, department_id)
  WHERE valid_to IS NULL;

CREATE TABLE member_profiles (
  user_id          bigint PRIMARY KEY REFERENCES users(id),
  uid              text UNIQUE,                    -- university ID
  iete_membership_id text,                         -- optional: only paid IETE members
  phone            text,
  branch           text,
  year_of_study    smallint,
  joined_on        date,
  lifecycle_status text NOT NULL DEFAULT 'onboarding'
                   CHECK (lifecycle_status IN ('onboarding','probation','active','alumni','removed')),
  responsibilities text,
  updated_at       timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 3. EVENTS
-- =====================================================================
CREATE TABLE events (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name               text NOT NULL,
  slug               text NOT NULL UNIQUE,
  category           text,
  description        text,
  venue              text,
  starts_at          timestamptz,
  ends_at            timestamptz,
  reg_opens_at       timestamptz,
  reg_closes_at      timestamptz,
  capacity           int CHECK (capacity IS NULL OR capacity > 0),
  allow_teams        boolean NOT NULL DEFAULT false,
  team_size_min      smallint,
  team_size_max      smallint,
  eligibility        text,
  is_public          boolean NOT NULL DEFAULT false,
  status             text NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft','proposed','awaiting_approval','approved',
                                       'open_for_registration','ongoing','completed',
                                       'cancelled','archived')),
  budget_planned     numeric(12,2),
  owner_id           bigint NOT NULL REFERENCES users(id),
  term_id            bigint REFERENCES terms(id),
  created_by         bigint NOT NULL REFERENCES users(id),
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE event_departments (
  event_id      bigint NOT NULL REFERENCES events(id),
  department_id bigint NOT NULL REFERENCES departments(id),
  PRIMARY KEY (event_id, department_id)
);

CREATE TABLE event_team (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id   bigint NOT NULL REFERENCES events(id),
  user_id    bigint NOT NULL REFERENCES users(id),
  event_role text   NOT NULL,                      -- 'coordinator','volunteer',...
  added_by   bigint NOT NULL REFERENCES users(id),
  added_at   timestamptz NOT NULL DEFAULT now(),
  removed_at timestamptz
);

CREATE TABLE event_milestones (
  id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id  bigint NOT NULL REFERENCES events(id),
  title     text NOT NULL,
  due_at    timestamptz,
  done_at   timestamptz
);

CREATE TABLE event_checklist_items (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id   bigint NOT NULL REFERENCES events(id),
  label      text NOT NULL,
  sort_order int  NOT NULL DEFAULT 0,
  done_by    bigint REFERENCES users(id),
  done_at    timestamptz
);

CREATE TABLE event_status_history (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id    bigint NOT NULL REFERENCES events(id),
  from_status text,
  to_status   text NOT NULL,
  changed_by  bigint NOT NULL REFERENCES users(id),
  remarks     text,
  changed_at  timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 4. WORK / TASKS
-- =====================================================================
CREATE TABLE tasks (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title         text NOT NULL,
  description   text,
  priority      text NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high','urgent')),
  status        text NOT NULL DEFAULT 'not_started'
                CHECK (status IN ('not_started','assigned','in_progress','submitted',
                                  'under_review','completed','rejected')),
                -- 'overdue' is derived: due_at < now() AND status NOT IN ('completed')
  due_at        timestamptz,
  department_id bigint REFERENCES departments(id),
  event_id      bigint REFERENCES events(id),
  reviewer_id   bigint REFERENCES users(id),
  created_by    bigint NOT NULL REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON tasks (department_id);
CREATE INDEX ON tasks (event_id);

CREATE TABLE task_assignees (
  task_id     bigint NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  user_id     bigint NOT NULL REFERENCES users(id),
  assigned_by bigint NOT NULL REFERENCES users(id),
  assigned_at timestamptz NOT NULL DEFAULT now(),
  unassigned_at timestamptz,
  PRIMARY KEY (task_id, user_id, assigned_at)
);

CREATE TABLE task_dependencies (
  task_id            bigint NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  depends_on_task_id bigint NOT NULL REFERENCES tasks(id),
  PRIMARY KEY (task_id, depends_on_task_id),
  CHECK (task_id <> depends_on_task_id)
);

CREATE TABLE task_comments (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id    bigint NOT NULL REFERENCES tasks(id),
  author_id  bigint NOT NULL REFERENCES users(id),
  body       text   NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE task_status_history (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id     bigint NOT NULL REFERENCES tasks(id),
  from_status text,
  to_status   text NOT NULL,
  changed_by  bigint NOT NULL REFERENCES users(id),
  remarks     text,
  changed_at  timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 5. DOCUMENTS (manual upload only)
-- =====================================================================
CREATE TABLE folder_templates (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       text NOT NULL,                        -- '01 Proposal' ...
  sort_order int  NOT NULL,
  active     boolean NOT NULL DEFAULT true
);

CREATE TABLE folders (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       text NOT NULL,
  parent_id  bigint REFERENCES folders(id),
  event_id   bigint REFERENCES events(id),
  sort_order int  NOT NULL DEFAULT 0,
  created_by bigint REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE documents (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  folder_id          bigint NOT NULL REFERENCES folders(id),
  title              text   NOT NULL,
  category           text,
  description        text,
  status             text   NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft','submitted','pending_approval','approved',
                                       'rejected','final','archived')),
  approval_reference text,
  current_version_id bigint,                        -- FK added below
  created_by         bigint NOT NULL REFERENCES users(id),
  created_at         timestamptz NOT NULL DEFAULT now(),
  deleted_at         timestamptz,
  deleted_by         bigint REFERENCES users(id)
);

CREATE TABLE document_versions (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id       bigint NOT NULL REFERENCES documents(id),
  version_no        int    NOT NULL,
  storage_key       text   NOT NULL UNIQUE,
  original_filename text   NOT NULL,
  mime_type         text   NOT NULL,
  size_bytes        bigint NOT NULL CHECK (size_bytes > 0),
  sha256            bytea  NOT NULL,
  uploaded_by       bigint NOT NULL REFERENCES users(id),
  uploaded_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, version_no)
);
ALTER TABLE documents ADD CONSTRAINT documents_current_version_fk
  FOREIGN KEY (current_version_id) REFERENCES document_versions(id);
CREATE TRIGGER trg_document_versions_ro BEFORE UPDATE OR DELETE ON document_versions
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE TABLE document_reviews (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  document_id bigint NOT NULL REFERENCES documents(id),
  from_status text,
  to_status   text NOT NULL,
  remarks     text,
  reviewer_id bigint NOT NULL REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Generic attachment storage for tasks, finance, campaigns, certificates
CREATE TABLE files (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  storage_key       text   NOT NULL UNIQUE,
  original_filename text   NOT NULL,
  mime_type         text   NOT NULL,
  size_bytes        bigint NOT NULL CHECK (size_bytes > 0),
  sha256            bytea  NOT NULL,
  uploaded_by       bigint REFERENCES users(id),
  uploaded_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE task_submissions (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id      bigint NOT NULL REFERENCES tasks(id),
  submitted_by bigint NOT NULL REFERENCES users(id),
  note         text,
  link_url     text,
  file_id      bigint REFERENCES files(id),
  review_outcome text CHECK (review_outcome IN ('accepted','rejected','changes_requested')),
  reviewed_by  bigint REFERENCES users(id),
  review_remarks text,
  submitted_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at  timestamptz
);

-- =====================================================================
-- 6. PERFORMANCE / POINTS
-- =====================================================================
CREATE TABLE evaluator_map (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  term_id            bigint REFERENCES terms(id),
  evaluator_type     text   NOT NULL CHECK (evaluator_type IN ('user','position')),
  evaluator_id       bigint NOT NULL,
  evaluatee_type     text   NOT NULL CHECK (evaluatee_type IN ('user','position','department')),
  evaluatee_id       bigint NOT NULL,
  created_by         bigint NOT NULL REFERENCES users(id),
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evaluations (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id     bigint NOT NULL REFERENCES events(id),
  evaluatee_id bigint NOT NULL REFERENCES users(id),
  max_points   numeric(6,2) NOT NULL CHECK (max_points > 0),
  combine_mode text NOT NULL DEFAULT 'sum' CHECK (combine_mode IN ('sum','average','separate')),
  status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open','submitted','decided')),
  opened_by    bigint NOT NULL REFERENCES users(id),
  opened_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (event_id, evaluatee_id)
);

CREATE TABLE point_submissions (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  evaluation_id bigint NOT NULL REFERENCES evaluations(id),
  evaluator_id  bigint NOT NULL REFERENCES users(id),
  score         numeric(6,2) NOT NULL CHECK (score >= 0),
  max_score     numeric(6,2) NOT NULL CHECK (max_score > 0),
  remarks       text   NOT NULL,
  evidence_file_id bigint REFERENCES files(id),
  supersedes_id bigint REFERENCES point_submissions(id),  -- revision after 'returned'
  submitted_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (score <= max_score)
);
CREATE TRIGGER trg_point_submissions_ro BEFORE UPDATE OR DELETE ON point_submissions
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE TABLE point_decisions (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  evaluation_id bigint NOT NULL REFERENCES evaluations(id),
  outcome       text   NOT NULL CHECK (outcome IN ('approved','adjusted','rejected','returned')),
  submitted_total numeric(6,2),
  final_score   numeric(6,2),
  reason        text,
  decided_by    bigint NOT NULL REFERENCES users(id),
  decided_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (outcome NOT IN ('approved','adjusted') OR final_score IS NOT NULL),
  CHECK (outcome <> 'adjusted' OR reason IS NOT NULL)
);
CREATE TRIGGER trg_point_decisions_ro BEFORE UPDATE OR DELETE ON point_decisions
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE TABLE points_ledger (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id       bigint NOT NULL REFERENCES users(id),
  event_id      bigint REFERENCES events(id),
  term_id       bigint REFERENCES terms(id),
  points        numeric(6,2) NOT NULL,              -- negative allowed for corrections
  entry_type    text NOT NULL CHECK (entry_type IN ('award','adjustment')),
  decision_id   bigint REFERENCES point_decisions(id),
  adjusts_id    bigint REFERENCES points_ledger(id),
  old_score     numeric(6,2),
  new_score     numeric(6,2),
  reason        text,
  authorised_by bigint NOT NULL REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (entry_type <> 'award' OR decision_id IS NOT NULL),
  CHECK (entry_type <> 'adjustment' OR (adjusts_id IS NOT NULL AND reason IS NOT NULL))
);
CREATE INDEX ON points_ledger (user_id);
CREATE TRIGGER trg_points_ledger_ro BEFORE UPDATE OR DELETE ON points_ledger
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- =====================================================================
-- 7. MEMBERSHIP
-- =====================================================================
CREATE TABLE membership_categories (
  id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name   text NOT NULL UNIQUE,
  fee    numeric(12,2) NOT NULL CHECK (fee >= 0),
  active boolean NOT NULL DEFAULT true
);

CREATE TABLE memberships (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  membership_no  text   NOT NULL UNIQUE,            -- 'MEM-0153'
  user_id        bigint REFERENCES users(id),
  holder_name    text   NOT NULL,
  holder_uid     text,
  holder_email   citext,
  category_id    bigint NOT NULL REFERENCES membership_categories(id),
  fee_amount     numeric(12,2) NOT NULL CHECK (fee_amount >= 0),
  status         text NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','paid','waived','refunded','cancelled')),
  valid_from     date,
  valid_to       date,
  recorded_by    bigint NOT NULL REFERENCES users(id),
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 8. FINANCE
-- =====================================================================
CREATE TABLE fin_accounts (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name            text NOT NULL UNIQUE,
  description     text,
  opening_balance numeric(12,2) NOT NULL DEFAULT 0,
  opening_date    date NOT NULL,
  active          boolean NOT NULL DEFAULT true,
  created_by      bigint NOT NULL REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sponsors (
  id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name    text NOT NULL,
  contact text,
  notes   text
);

CREATE TABLE fin_transactions (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code              text NOT NULL UNIQUE,           -- 'INC-2026-0012', 'EXP-2026-0042'
  txn_type          text NOT NULL CHECK (txn_type IN ('income','expense','transfer_in',
                                                     'transfer_out','adjustment_credit',
                                                     'adjustment_debit','reversal')),
  account_id        bigint NOT NULL REFERENCES fin_accounts(id),
  amount            numeric(12,2) NOT NULL CHECK (amount > 0),
  txn_date          date   NOT NULL,
  counterparty      text,                           -- source (income) / paid-to (expense)
  purpose           text   NOT NULL,
  category          text,
  payment_mode      text CHECK (payment_mode IN ('cash','upi','bank_transfer','cheque','card','other')),
  payment_reference text,
  event_id          bigint REFERENCES events(id),
  department_id     bigint REFERENCES departments(id),
  membership_id     bigint REFERENCES memberships(id),
  sponsor_id        bigint REFERENCES sponsors(id),
  transfer_group_id uuid,
  reverses_id       bigint REFERENCES fin_transactions(id),
  status            text NOT NULL DEFAULT 'submitted'
                    CHECK (status IN ('submitted','verified','approved','posted',
                                      'rejected','reimbursed')),
  submitted_by      bigint NOT NULL REFERENCES users(id),
  submitted_at      timestamptz NOT NULL DEFAULT now(),
  verified_by       bigint REFERENCES users(id),
  verified_at       timestamptz,
  approved_by       bigint REFERENCES users(id),
  approved_at       timestamptz,
  posted_at         timestamptz,
  rejection_reason  text,
  CHECK (verified_by IS NULL OR verified_by <> submitted_by),
  CHECK (approved_by IS NULL OR approved_by <> submitted_by),
  CHECK ((txn_type IN ('transfer_in','transfer_out')) = (transfer_group_id IS NOT NULL)),
  CHECK ((txn_type = 'reversal') = (reverses_id IS NOT NULL))
);
CREATE INDEX ON fin_transactions (account_id, status);
CREATE INDEX ON fin_transactions (event_id);

-- Posted transactions are immutable; only status 'reimbursed' may follow 'posted'.
CREATE FUNCTION fin_txn_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Finance transactions cannot be deleted; record a reversal';
  END IF;
  IF OLD.status = 'posted' THEN
    IF NEW.status = 'reimbursed'
       AND (to_jsonb(NEW) - 'status') = (to_jsonb(OLD) - 'status') THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Posted transaction % is immutable; record a reversal', OLD.code;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_fin_txn_guard BEFORE UPDATE OR DELETE ON fin_transactions
  FOR EACH ROW EXECUTE FUNCTION fin_txn_guard();

CREATE TABLE fin_attachments (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  transaction_id bigint NOT NULL REFERENCES fin_transactions(id),
  file_id        bigint NOT NULL REFERENCES files(id),
  kind           text NOT NULL CHECK (kind IN ('bill','invoice','receipt','proof','other')),
  added_by       bigint NOT NULL REFERENCES users(id),
  added_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE fin_reconciliations (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  account_id        bigint NOT NULL REFERENCES fin_accounts(id),
  period_end        date   NOT NULL,
  statement_balance numeric(12,2) NOT NULL,
  book_balance      numeric(12,2) NOT NULL,
  difference        numeric(12,2) GENERATED ALWAYS AS (statement_balance - book_balance) STORED,
  statement_file_id bigint REFERENCES files(id),
  notes             text,
  reconciled_by     bigint NOT NULL REFERENCES users(id),
  reconciled_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (account_id, period_end)
);

-- Book balance is derived, never stored.
CREATE VIEW fin_account_balances AS
SELECT a.id AS account_id,
       a.name,
       a.opening_balance,
       COALESCE(SUM(CASE WHEN t.txn_type IN ('income','transfer_in','adjustment_credit')
                         THEN t.amount END), 0) AS total_credits,
       COALESCE(SUM(CASE WHEN t.txn_type IN ('expense','transfer_out','adjustment_debit')
                         THEN t.amount END), 0) AS total_debits,
       a.opening_balance
         + COALESCE(SUM(CASE WHEN t.txn_type IN ('income','transfer_in','adjustment_credit')
                             THEN t.amount END), 0)
         - COALESCE(SUM(CASE WHEN t.txn_type IN ('expense','transfer_out','adjustment_debit')
                             THEN t.amount END), 0) AS book_balance
FROM fin_accounts a
LEFT JOIN fin_transactions t
  ON t.account_id = a.id AND t.status IN ('posted','reimbursed')
GROUP BY a.id;
-- NOTE: 'reversal' rows are expanded in the service layer into an opposite-direction
-- adjustment_credit/debit, so the view only needs the directional types above.

-- =====================================================================
-- 9. PARTICIPANTS, ATTENDANCE, CERTIFICATES
-- =====================================================================
CREATE TABLE registration_forms (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id     bigint NOT NULL UNIQUE REFERENCES events(id),
  fields       jsonb  NOT NULL,                     -- [{key,label,type,required,options}]
  consent_text text   NOT NULL,
  requires_account boolean NOT NULL DEFAULT true,
  requires_approval boolean NOT NULL DEFAULT false,
  waitlist_enabled  boolean NOT NULL DEFAULT false,
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE registrations (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  reg_code         text   NOT NULL UNIQUE,          -- shown to participant, used in QR
  event_id         bigint NOT NULL REFERENCES events(id),
  participant_id   bigint REFERENCES users(id),
  full_name        text   NOT NULL,
  email            citext NOT NULL,
  uid              text,
  phone            text,
  institution      text,
  team_name        text,
  answers          jsonb  NOT NULL DEFAULT '{}',
  consent_given_at timestamptz NOT NULL,
  status           text NOT NULL DEFAULT 'submitted'
                   CHECK (status IN ('submitted','approved','rejected','waitlisted','cancelled')),
  reviewed_by      bigint REFERENCES users(id),
  reviewed_at      timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX reg_unique_email ON registrations (event_id, email) WHERE status <> 'cancelled';
CREATE UNIQUE INDEX reg_unique_uid   ON registrations (event_id, uid)   WHERE uid IS NOT NULL AND status <> 'cancelled';

CREATE TABLE registration_team_members (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  registration_id bigint NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
  full_name       text NOT NULL,
  email           citext,
  uid             text
);

CREATE TABLE attendance (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id        bigint NOT NULL REFERENCES events(id),
  registration_id bigint REFERENCES registrations(id),
  team_member_id  bigint REFERENCES registration_team_members(id),
  user_id         bigint REFERENCES users(id),          -- for team-member (staff) attendance
  present         boolean NOT NULL DEFAULT true,
  method          text NOT NULL CHECK (method IN ('manual','qr')),
  recorded_by     bigint NOT NULL REFERENCES users(id),
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(registration_id, team_member_id, user_id) = 1)
);

CREATE TABLE attendance_corrections (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  attendance_id bigint NOT NULL REFERENCES attendance(id),
  old_present   boolean NOT NULL,
  new_present   boolean NOT NULL,
  reason        text NOT NULL,
  corrected_by  bigint NOT NULL REFERENCES users(id),
  corrected_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE certificates (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  registration_id bigint NOT NULL REFERENCES registrations(id),
  file_id         bigint NOT NULL REFERENCES files(id),
  released        boolean NOT NULL DEFAULT false,
  uploaded_by     bigint NOT NULL REFERENCES users(id),
  uploaded_at     timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 10. COMMUNICATION
-- =====================================================================
CREATE TABLE announcements (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title        text NOT NULL,
  body         text NOT NULL,
  audience     text NOT NULL CHECK (audience IN ('all_team','department','event','participants')),
  audience_id  bigint,
  published_by bigint NOT NULL REFERENCES users(id),
  published_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE meetings (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title           text NOT NULL,
  scheduled_at    timestamptz NOT NULL,
  location        text,
  agenda          text,
  minutes_document_id bigint REFERENCES documents(id),
  department_id   bigint REFERENCES departments(id),
  event_id        bigint REFERENCES events(id),
  created_by      bigint NOT NULL REFERENCES users(id)
);

CREATE TABLE campaigns (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       text NOT NULL,
  event_id   bigint REFERENCES events(id),
  created_by bigint NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE campaign_posts (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  campaign_id   bigint NOT NULL REFERENCES campaigns(id),
  platform      text NOT NULL CHECK (platform IN ('instagram','linkedin','whatsapp','email','other')),
  planned_for   timestamptz,
  status        text NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned','scheduled','published','completed')),
  assignee_id   bigint REFERENCES users(id),
  creative_file_id bigint REFERENCES files(id),
  post_url      text,
  proof_file_id bigint REFERENCES files(id)
);

CREATE TABLE notifications (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES users(id),
  kind       text   NOT NULL,                       -- 'task.assigned','expense.pending',...
  payload    jsonb  NOT NULL,
  read_at    timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON notifications (user_id) WHERE read_at IS NULL;

-- =====================================================================
-- 11. GOVERNANCE
-- =====================================================================
CREATE TABLE audit_events (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id    bigint REFERENCES users(id),
  action      text   NOT NULL,                      -- 'user.create','doc.delete','fin.post',...
  entity_type text   NOT NULL,
  entity_id   bigint,
  before      jsonb,
  after       jsonb,
  ip          inet,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON audit_events (entity_type, entity_id);
CREATE INDEX ON audit_events (actor_id, created_at);
CREATE TRIGGER trg_audit_events_ro BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE TABLE settings (
  key        text PRIMARY KEY,
  value      jsonb NOT NULL,
  updated_by bigint REFERENCES users(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE exports_log (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id),
  export_type text   NOT NULL,
  filters     jsonb,
  row_count   int,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- SEED: default event folder templates (blueprint §8.2)
-- =====================================================================
INSERT INTO folder_templates (name, sort_order) VALUES
  ('01 Proposal', 1), ('02 Permissions & Approvals', 2), ('03 Venue & Logistics', 3),
  ('04 Notices & Communications', 4), ('05 Duty Leave & Attendance', 5),
  ('06 Sponsorship & Budget', 6), ('07 Event Execution', 7),
  ('08 Post-Event Records', 8), ('09 Final Report & Archive', 9);
