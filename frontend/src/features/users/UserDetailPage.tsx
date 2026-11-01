import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { User, UserOrg } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, Field, formatDate, Input, Modal, PageHeader, Spinner,
  StatusBadge } from "../../components/ui";
import { AuditList } from "../audit/AuditPage";
import { OrgHistoryCard, ProfileCard } from "../org/PersonOrg";
import { GrantsCard } from "../permissions/GrantsCard";
import { CopyBox } from "./CopyBox";

export function UserDetailPage() {
  const id = Number(useParams().id);
  const { can, me } = useAuth();
  const account = useQuery({
    queryKey: ["user", id],
    queryFn: () => api<User>(`/users/${id}`),
    enabled: can("users.view"),
  });
  const org = useQuery({
    queryKey: ["user-org", id],
    queryFn: () => api<UserOrg>(`/users/${id}/org`),
    enabled: can("org.view"),
  });

  if (account.isLoading || org.isLoading) return <Spinner />;
  const user = account.data;
  const person = user ?? org.data?.user;
  if (!person) return <Alert>{errorMessage(account.error ?? org.error)}</Alert>;
  const isSelf = me?.user.id === person.id;

  return (
    <>
      {can("users.view")
        ? <Link to="/app/users" className="text-sm text-brand-600 hover:underline">← Team accounts</Link>
        : <Link to="/app/org" className="text-sm text-brand-600 hover:underline">← Organisation</Link>}
      <PageHeader title={person.full_name} subtitle={person.email} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {org.data && <OrgHistoryCard org={org.data} />}
          {user && can("permissions.view") && (
            user.is_super_admin
              ? <Card title="Access"><p className="text-sm text-slate-600">The Chairperson has every permission.</p></Card>
              : <GrantsCard subjectType="user" subjectId={user.id} subjectName={user.full_name}
                            canManage={can("permissions.manage") && !isSelf} showEffective />
          )}
          {can("audit.view") && (
            <Card title="Recent activity on this account">
              <AuditList filters={{ entity_type: "user", entity_id: String(person.id) }} compact />
            </Card>
          )}
        </div>
        <div className="space-y-6">
          {user && <AccountCard user={user} isSelf={isSelf} />}
          {org.data && <ProfileCard userId={person.id} profile={org.data.profile} editable={can("users.edit")} />}
        </div>
      </div>
    </>
  );
}

function AccountCard({ user, isSelf }: { user: User; isSelf: boolean }) {
  const { can, me } = useAuth();
  const qc = useQueryClient();
  const [action, setAction] = useState<null | "suspend" | "reactivate" | "deactivate" | "reset" | "invite" | "delete">(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const protectedTarget = isSelf || (user.is_super_admin && !me?.all_permissions);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["user", user.id] });
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["audit"] });
  };

  async function reissueInvite() {
    const r = await api<{ invite_url: string }>(`/users/${user.id}/invite`, { method: "POST" });
    setInviteUrl(r.invite_url);
    refresh();
  }

  return (
    <Card title="Account">
      <dl className="space-y-3 text-sm">
        <Row label="Status"><StatusBadge status={user.status} /></Row>
        {user.is_super_admin && <Row label="Role"><Badge tone="blue">Chairperson (super admin)</Badge></Row>}
        <Row label="Must change password">{user.must_change_password ? "Yes" : "No"}</Row>
        <Row label="Last sign-in">{formatDate(user.last_login_at)}</Row>
        <Row label="Created">{formatDate(user.created_at)}</Row>
      </dl>
      {!protectedTarget && (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
          {can("users.reset_password") && (
            <Button variant="secondary" onClick={() => setAction("reset")}>Reset password</Button>
          )}
          {can("users.create") && user.status === "invited" && (
            <Button variant="secondary" onClick={reissueInvite}>New invite link</Button>
          )}
          {can("users.suspend") && (user.status === "active" || user.status === "invited") && (
            <Button variant="secondary" onClick={() => setAction("suspend")}>Suspend</Button>
          )}
          {can("users.suspend") && (user.status === "suspended" || user.status === "deactivated") && (
            <Button variant="secondary" onClick={() => setAction("reactivate")}>Reactivate</Button>
          )}
          {can("users.suspend") && user.status !== "deactivated" && (
            <Button variant="danger" onClick={() => setAction("deactivate")}>Deactivate</Button>
          )}
          {me?.user.is_super_admin && (
            <Button variant="danger" onClick={() => setAction("delete")}>Delete account</Button>
          )}
        </div>
      )}
      {inviteUrl && (
        <div className="mt-4 space-y-2">
          <p className="text-xs text-slate-600">New one-time invite link (shown once):</p>
          <CopyBox value={inviteUrl} />
        </div>
      )}
      {(action === "suspend" || action === "reactivate" || action === "deactivate") && (
        <StatusModal user={user} action={action} onClose={() => setAction(null)} onDone={refresh} />
      )}
      {action === "delete" && <DeleteAccountModal user={user} onClose={() => setAction(null)} />}
      {action === "reset" && <ResetPasswordModal user={user} onClose={() => setAction(null)} onDone={refresh} />}
    </Card>
  );
}

/** Chairperson only. */
function DeleteAccountModal({ user, onClose }: { user: User; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/users/${user.id}/delete`, { method: "POST", body: { reason, confirm_email: confirm } });
      qc.invalidateQueries();
      navigate("/app/users", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Modal title={`Delete ${user.full_name}`} open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Alert tone="amber">
          <p className="font-medium">This happens straight away and can't be undone:</p>
          <ul className="mt-1 list-disc pl-5">
            <li>They are signed out and can't sign in again.</li>
            <li>They lose their positions, departments, access and open tasks.</li>
            <li>Their scores leave the standings.</li>
          </ul>
          <p className="mt-2">Past events, tasks and the audit log still show their name. Events they run still list them as owner, and you can keep managing those events.</p>
        </Alert>
        <Field label="Reason (recorded in the audit log)">
          <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </Field>
        <Field label={`Type “${user.email}” to confirm`}>
          <Input required value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="danger" disabled={busy}>{busy ? "Deleting…" : "Delete permanently"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right text-slate-800">{children}</dd>
    </div>
  );
}

function StatusModal({ user, action, onClose, onDone }:
  { user: User; action: "suspend" | "reactivate" | "deactivate"; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const label = { suspend: "Suspend", reactivate: "Reactivate", deactivate: "Deactivate" }[action];

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api(`/users/${user.id}/${action}`, { method: "POST", body: { reason } });
      onDone();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal title={`${label} ${user.full_name}`} open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {action !== "reactivate" && (
          <Alert tone="amber">They will be signed out immediately and cannot sign in until reactivated.</Alert>
        )}
        <Field label="Reason (recorded in the audit log)">
          <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={action === "reactivate" ? "primary" : "danger"}>{label}</Button>
        </div>
      </form>
    </Modal>
  );
}

function ResetPasswordModal({ user, onClose, onDone }: { user: User; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api(`/users/${user.id}/reset-password`, { method: "POST", body: { temp_password: password } });
      setDone(true);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal title={`Reset password for ${user.full_name}`} open onClose={onClose}>
      {done ? (
        <div className="space-y-4">
          <Alert tone="green">Temporary password set. Share it privately. They must change it at next sign-in.</Alert>
          <div className="flex justify-end"><Button onClick={onClose}>Done</Button></div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <Alert>{error}</Alert>}
          <Field label="New temporary password" hint="At least 10 characters. All their sessions will be signed out.">
            <Input type="text" required minLength={10} autoComplete="off" value={password}
                   onChange={(e) => setPassword(e.target.value)} autoFocus />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit">Set temporary password</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
