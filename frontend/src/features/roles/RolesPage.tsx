import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../../api/client";
import type { Permission, Role } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Spinner } from "../../components/ui";

export function RolesPage() {
  const { can } = useAuth();
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => api<Role[]>("/roles") });
  const [editing, setEditing] = useState<Role | "new" | null>(null);

  return (
    <>
      <PageHeader title="Roles"
                  subtitle="A role is a bundle of everyday permissions. Holding a designation never grants a role automatically."
                  actions={can("roles.manage") && <Button onClick={() => setEditing("new")}>+ New role</Button>} />
      {roles.isLoading ? <Spinner /> : roles.error ? <Alert>{errorMessage(roles.error)}</Alert>
        : !roles.data?.length ? <Card><Empty>No roles yet.</Empty></Card> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {roles.data.map((r) => (
            <Card key={r.id} title={r.name}
                  actions={can("roles.manage") && <Button variant="ghost" onClick={() => setEditing(r)}>Edit</Button>}>
              {r.description && <p className="mb-3 text-sm text-slate-600">{r.description}</p>}
              <p className="mb-2 text-xs text-slate-500">
                {r.permissions.length} permissions · held by {r.active_grant_count} {r.active_grant_count === 1 ? "person" : "people"}
              </p>
              <div className="flex flex-wrap gap-1">
                {r.permissions.map((p) => <Badge key={p}>{p}</Badge>)}
              </div>
            </Card>
          ))}
        </div>
      )}
      {editing && <RoleModal role={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function RoleModal({ role, onClose }: { role: Role | null; onClose: () => void }) {
  const qc = useQueryClient();
  const perms = useQuery({ queryKey: ["permissions"], queryFn: () => api<Permission[]>("/permissions") });
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [selected, setSelected] = useState<Set<string>>(new Set(role?.permissions ?? []));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const modules = new Map<string, Permission[]>();
  perms.data?.filter((p) => !p.sensitive).forEach((p) => modules.set(p.module, [...(modules.get(p.module) ?? []), p]));

  function toggle(code: string) {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(code)) n.delete(code); else n.add(code);
      return n;
    });
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const body = { name, description: description || null, permissions: [...selected], reason };
      if (role) await api(`/roles/${role.id}`, { method: "PUT", body });
      else await api("/roles", { method: "POST", body });
      qc.invalidateQueries({ queryKey: ["roles"] });
      qc.invalidateQueries({ queryKey: ["effective"] });
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function remove() {
    setError(null);
    try {
      await api(`/roles/${role!.id}?reason=${encodeURIComponent(reason || "Role removed")}`, { method: "DELETE" });
      qc.invalidateQueries({ queryKey: ["roles"] });
      onClose();
    } catch (err) {
      setError(errorMessage(err));
      setConfirmDelete(false);
    }
  }

  return (
    <Modal title={role ? `Edit role: ${role.name}` : "New role"} open onClose={onClose}>
      <form onSubmit={save} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {role && role.active_grant_count > 0 && (
          <Alert tone="amber">Changes apply immediately to the {role.active_grant_count} people who hold this role.</Alert>
        )}
        <Field label="Name"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <div>
          <span className="mb-1 block text-sm font-medium text-slate-700">Permissions</span>
          <p className="mb-2 text-xs text-slate-500">Sensitive permissions (finance, accounts, approvals) are not listed. Grant them to individuals.</p>
          <div className="max-h-72 space-y-3 overflow-y-auto rounded-md border border-slate-200 p-3">
            {[...modules.entries()].map(([module, list]) => (
              <div key={module}>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{module}</div>
                {list.map((p) => (
                  <label key={p.code} className="flex items-start gap-2 py-0.5 text-sm">
                    <input type="checkbox" className="mt-1" checked={selected.has(p.code)} onChange={() => toggle(p.code)} />
                    <span><code className="text-xs">{p.code}</code> <span className="text-slate-500">{p.description}</span></span>
                  </label>
                ))}
              </div>
            ))}
          </div>
        </div>
        <Field label="Reason for this change (recorded in the audit log)">
          <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <div className="flex flex-wrap justify-between gap-2">
          <div>
            {role && (confirmDelete
              ? <Button type="button" variant="danger" onClick={remove}>Confirm delete</Button>
              : <Button type="button" variant="ghost" className="text-red-600" onClick={() => setConfirmDelete(true)}>Delete role</Button>)}
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit">Save</Button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
