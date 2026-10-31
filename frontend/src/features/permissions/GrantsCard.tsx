import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../../api/client";
import type { Department, EffectiveAccess, Grant, Permission, Role, SubjectType } from "../../api/types";
import { Alert, Badge, Button, Card, Empty, Field, formatDate, Input, Modal, Select, Spinner } from "../../components/ui";

const SUBJECT_HINT: Record<SubjectType, string> = {
  user: "This person can sign in but cannot see or do anything until access is granted.",
  position: "Whoever holds this position gets this access, and loses it when they leave the position.",
  department: "Every current member of this department gets this access.",
};

/** Grants held by a person, position or department. */
export function GrantsCard({ subjectType, subjectId, subjectName, canManage, showEffective = false }: {
  subjectType: SubjectType; subjectId: number; subjectName: string; canManage: boolean; showEffective?: boolean;
}) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [revoking, setRevoking] = useState<Grant | null>(null);

  const grants = useQuery({
    queryKey: ["grants", subjectType, subjectId, showInactive],
    queryFn: () => api<Grant[]>(`/grants?subject_type=${subjectType}&subject_id=${subjectId}&include_inactive=${showInactive}`),
  });
  const effective = useQuery({
    queryKey: ["effective", subjectId],
    queryFn: () => api<EffectiveAccess>(`/grants/effective?user_id=${subjectId}`),
    enabled: showEffective && subjectType === "user",
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["grants", subjectType, subjectId] });
    qc.invalidateQueries({ queryKey: ["effective"] });
  };

  return (
    <Card title="Access granted" actions={canManage && <Button onClick={() => setAdding(true)}>+ Grant access</Button>}>
      <label className="mb-3 flex items-center gap-2 text-xs text-slate-600">
        <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />
        Show revoked and expired grants
      </label>
      {grants.isLoading ? <Spinner /> : grants.error ? <Alert>{errorMessage(grants.error)}</Alert>
        : !grants.data?.length ? (
          <Empty>
            No access granted directly.{" "}
            {effective.data?.permissions.length
              ? "Everything this person can do comes from their position or departments (see below)."
              : SUBJECT_HINT[subjectType]}
          </Empty>
        ) : (
        <ul className="divide-y divide-slate-100">
          {grants.data.map((g) => (
            <li key={g.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  {g.role_name ? <Badge tone="blue">Role: {g.role_name}</Badge>
                    : <code className="text-sm font-medium text-slate-800">{g.permission_code}</code>}
                  <Badge>{g.scope_type === "global" ? "Everywhere" : `${g.scope_name ?? g.scope_type} only`}</Badge>
                  {!g.active && <Badge tone="red">{g.revoked_at ? "Revoked" : "Expired"}</Badge>}
                  {g.active && g.expires_at && <Badge tone="amber">Expires {formatDate(g.expires_at, false)}</Badge>}
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  “{g.reason}” · by {g.granted_by_name ?? "system"} on {formatDate(g.created_at)}
                </p>
              </div>
              {canManage && g.active && (
                <Button variant="ghost" className="text-red-600" onClick={() => setRevoking(g)}>Revoke</Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {effective.data && effective.data.permissions.length > 0 && <EffectiveList access={effective.data} />}
      {adding && <AddGrantModal subjectType={subjectType} subjectId={subjectId} subjectName={subjectName}
                                onClose={() => setAdding(false)} onDone={refresh} />}
      {revoking && <RevokeModal grant={revoking} onClose={() => setRevoking(null)} onDone={refresh} />}
    </Card>
  );
}

function EffectiveList({ access }: { access: EffectiveAccess }) {
  const byCode = new Map<string, string[]>();
  for (const p of access.permissions) {
    const source = [p.via_role && `role ${p.via_role}`, p.via_subject].filter(Boolean).join(", ") || "direct";
    const where = p.scope_type === "global" ? "" : ` (${p.scope_type} #${p.scope_id})`;
    byCode.set(p.code, [...(byCode.get(p.code) ?? []), source + where]);
  }
  return (
    <details className="mt-4 rounded-md bg-slate-50 p-3 text-sm">
      <summary className="cursor-pointer font-medium text-slate-700">
        Everything this person can do ({byCode.size} permissions, including through positions and departments)
      </summary>
      <ul className="mt-2 space-y-1">
        {[...byCode.entries()].sort().map(([code, sources]) => (
          <li key={code} className="text-xs">
            <code>{code}</code> <span className="text-slate-500">via {[...new Set(sources)].join("; ")}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function AddGrantModal({ subjectType, subjectId, subjectName, onClose, onDone }: {
  subjectType: SubjectType; subjectId: number; subjectName: string; onClose: () => void; onDone: () => void;
}) {
  const [kind, setKind] = useState<"role" | "permission">("role");
  const [roleId, setRoleId] = useState("");
  const [code, setCode] = useState("");
  const [scope, setScope] = useState("global");
  const [expires, setExpires] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles") });
  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api<Permission[]>("/permissions") });
  const depts = useQuery({ queryKey: ["departments", false], queryFn: () => api<Department[]>("/departments") });

  const modules = new Map<string, Permission[]>();
  perms.data
    ?.filter((p) => subjectType === "user" || !p.sensitive)
    .forEach((p) => modules.set(p.module, [...(modules.get(p.module) ?? []), p]));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/grants", {
        method: "POST",
        body: {
          subject_type: subjectType,
          subject_id: subjectId,
          role_id: kind === "role" ? Number(roleId) : null,
          permission_code: kind === "permission" ? code : null,
          scope_type: scope === "global" ? "global" : "department",
          scope_id: scope === "global" ? null : Number(scope),
          expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null,
          reason,
        },
      });
      onDone();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal title={`Grant access to ${subjectName}`} open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <p className="text-xs text-slate-500">{SUBJECT_HINT[subjectType]}</p>
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" checked={kind === "role"} onChange={() => setKind("role")} /> A role
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={kind === "permission"} onChange={() => setKind("permission")} /> A single permission
          </label>
        </div>
        {kind === "role" ? (
          <Field label="Role">
            <Select required value={roleId} onChange={(e) => setRoleId(e.target.value)}>
              <option value="">Choose a role…</option>
              {roles.data?.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.permissions.length} permissions)</option>)}
            </Select>
          </Field>
        ) : (
          <Field label="Permission"
                 hint={subjectType === "user"
                   ? "⚠ marks sensitive permissions (finance, accounts, approvals)."
                   : "Sensitive permissions are hidden: they can only be granted to a named person."}>
            <Select required value={code} onChange={(e) => setCode(e.target.value)}>
              <option value="">Choose a permission…</option>
              {[...modules.entries()].map(([module, list]) => (
                <optgroup key={module} label={module}>
                  {list.map((p) => (
                    <option key={p.code} value={p.code}>{p.code}: {p.description}{p.sensitive ? " ⚠" : ""}</option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </Field>
        )}
        <Field label="Applies to" hint="Limit to one department (and its sub-departments) or allow everywhere.">
          <Select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="global">Everywhere</option>
            {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name} department only</option>)}
          </Select>
        </Field>
        <Field label="Expires on (optional)">
          <Input type="date" value={expires} onChange={(e) => setExpires(e.target.value)}
                 min={new Date().toISOString().slice(0, 10)} />
        </Field>
        <Field label="Reason (recorded in the audit log)">
          <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit">Grant</Button>
        </div>
      </form>
    </Modal>
  );
}

function RevokeModal({ grant, onClose, onDone }: { grant: Grant; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api(`/grants/${grant.id}/revoke`, { method: "POST", body: { reason } });
      onDone();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal title={`Revoke ${grant.role_name ? `role “${grant.role_name}”` : grant.permission_code}`} open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field label="Reason (recorded in the audit log)">
          <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="danger">Revoke</Button>
        </div>
      </form>
    </Modal>
  );
}
