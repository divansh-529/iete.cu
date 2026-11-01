import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { User, UserPage } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Button, Card, Empty, Field, formatDate, Input, Modal, PageHeader, Select, Spinner,
  StatusBadge } from "../../components/ui";
import { SignInDetails } from "../members/SignInDetails";
import { CopyBox } from "./CopyBox";

export function UsersPage() {
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);

  const params = new URLSearchParams({ limit: "200" });
  if (q) params.set("q", q);
  if (status) params.set("status", status);
  const { data, isLoading, error } = useQuery({
    queryKey: ["users", q, status],
    queryFn: () => api<UserPage>(`/users?${params}`),
  });

  return (
    <>
      <PageHeader title="Team accounts" subtitle="Every member has their own account. Leads propose recruits; the Chairperson, Vice Chair or Secretary approve them."
                  actions={can("users.create") && <Button onClick={() => setCreating(true)}>+ New account</Button>} />
      <Card>
        <div className="mb-4 flex flex-wrap gap-2">
          <Input placeholder="Search name or email…" value={q} onChange={(e) => setQ(e.target.value)}
                 className="max-w-xs" />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40">
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="invited">Invited</option>
            <option value="proposed">Waiting for approval</option>
            <option value="rejected">Not approved</option>
            <option value="suspended">Suspended</option>
            <option value="deactivated">Deactivated</option>
          </Select>
        </div>
        {error && <Alert>{errorMessage(error)}</Alert>}
        {isLoading ? <Spinner /> : !data?.items.length ? <Empty>No accounts match.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="py-2 pr-4 font-medium">Name</th>
                  <th className="py-2 pr-4 font-medium">Email</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium">Last login</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50">
                    <td className="py-2.5 pr-4">
                      <Link to={`/app/users/${u.id}`} className="font-medium text-brand-700 hover:underline">
                        {u.full_name}
                      </Link>
                      {u.is_super_admin && <span className="ml-2 text-xs text-slate-500">(Chairperson)</span>}
                    </td>
                    <td className="py-2.5 pr-4 text-slate-600">{u.email}</td>
                    <td className="py-2.5 pr-4"><StatusBadge status={u.status} /></td>
                    <td className="py-2.5 pr-4 text-slate-500">{formatDate(u.last_login_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-xs text-slate-500">{data.total} account(s)</p>
          </div>
        )}
      </Card>
      <CreateUserModal open={creating} onClose={() => setCreating(false)} />
    </>
  );
}

/** The Chairperson (users.create) adds an account directly. It starts on the forum's default
 *  first password and the person is emailed their sign-in details. Recruits proposed by leads go
 *  through the Approvals page instead (features/members). */
function CreateUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [credential, setCredential] = useState<"default_password" | "invite" | "temp_password">("default_password");
  const [tempPassword, setTempPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<{ user: User; invite_url: string | null; email_sent: boolean;
    default_password: string | null; login_url: string | null } | null>(null);

  function close() {
    setEmail(""); setName(""); setTempPassword(""); setError(null); setCreated(null);
    onClose();
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setCreated(await api("/users", { method: "POST", body: {
        email, full_name: name, credential, temp_password: credential === "temp_password" ? tempPassword : null } }));
      qc.invalidateQueries({ queryKey: ["users"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="New team account" open={open} onClose={close}>
      {created ? (
        <div className="space-y-4">
          <Alert tone="green">Account created for {created.user.full_name}.</Alert>
          {created.invite_url ? (
            <>
              <p className="text-sm text-slate-600">Share this invite link privately. It works once and expires in 72 hours. It will not be shown again.</p>
              <CopyBox value={created.invite_url} />
            </>
          ) : created.default_password ? (
            <SignInDetails email={created.user.email} emailed={created.email_sent} password={created.default_password}
                           loginUrl={created.login_url ?? ""} />
          ) : (
            <p className="text-sm text-slate-600">Give them the temporary password privately. They will be asked to choose their own password at first sign-in.</p>
          )}
          <div className="flex justify-end gap-2">
            <Link to={`/app/users/${created.user.id}`} onClick={close}><Button variant="secondary">Open account &amp; grant access</Button></Link>
            <Button onClick={close}>Done</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <Alert>{error}</Alert>}
          <Field label="Full name"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
          <Field label="Email (Gmail)"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium text-slate-700">First sign-in</legend>
            {([["default_password", "Default first password", "the forum's standard; they're emailed and must change it"],
               ["invite", "One-time invite link", "you share the link; they set their own password"],
               ["temp_password", "A temporary password of your choice", "they must change it at first sign-in"]] as const).map(([key, label, note]) => (
              <label key={key} className="flex items-start gap-2 text-sm">
                <input type="radio" className="mt-0.5" checked={credential === key} onChange={() => setCredential(key)} />
                <span>{label} <span className="text-slate-500">({note})</span></span>
              </label>
            ))}
          </fieldset>
          {credential === "temp_password" && (
            <Field label="Temporary password" hint="At least 10 characters. Share it privately.">
              <Input type="text" required minLength={10} value={tempPassword} autoComplete="off" onChange={(e) => setTempPassword(e.target.value)} />
            </Field>
          )}
          <p className="text-xs text-slate-500">New accounts have no access until you grant permissions or add them to a department.</p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={close}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create account"}</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}