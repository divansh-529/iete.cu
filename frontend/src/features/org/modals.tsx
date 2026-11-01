import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { api, errorMessage } from "../../api/client";
import type { Department, Holder, PersonRef, Position } from "../../api/types";
import { Alert, Button, Field, Input, Modal, Select } from "../../components/ui";
import { PersonPicker } from "./PersonPicker";

const today = () => new Date().toISOString().slice(0, 10);

/** Refresh everything that shows org structure after a change. */
export function useOrgRefresh() {
  const qc = useQueryClient();
  return () => {
    for (const key of ["departments", "department", "positions", "position", "position-history", "chart",
                       "user-org", "effective", "me", "audit"]) {
      qc.invalidateQueries({ queryKey: [key] });
    }
  };
}

export function FormModal({ title, onClose, onSubmit, submitLabel, danger, children }: {
  title: string; onClose: () => void; onSubmit: () => Promise<unknown>; submitLabel: string;
  danger?: boolean; children: ReactNode;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await onSubmit();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={title} open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {children}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={danger ? "danger" : "primary"} disabled={busy}>{submitLabel}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function ReasonModal({ title, label = "Reason (recorded in the audit log)", submitLabel, danger, warning, onSubmit, onClose }: {
  title: string; label?: string; submitLabel: string; danger?: boolean; warning?: string;
  onSubmit: (reason: string) => Promise<unknown>; onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  return (
    <FormModal title={title} onClose={onClose} submitLabel={submitLabel} danger={danger} onSubmit={() => onSubmit(reason)}>
      {warning && <Alert tone="amber">{warning}</Alert>}
      <Field label={label}>
        <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
      </Field>
    </FormModal>
  );
}

export function DepartmentFormModal({ dept, onClose }: { dept?: Department; onClose: () => void }) {
  const refresh = useOrgRefresh();
  const all = useQuery({ queryKey: ["departments", false], queryFn: () => api<Department[]>("/departments") });
  const [name, setName] = useState(dept?.name ?? "");
  const [description, setDescription] = useState(dept?.description ?? "");
  const [parent, setParent] = useState(dept?.parent_id ? String(dept.parent_id) : "");
  return (
    <FormModal title={dept ? `Edit ${dept.name}` : "New department"} onClose={onClose}
               submitLabel={dept ? "Save" : "Create department"}
               onSubmit={async () => {
                 const body = { name, description: description || null, parent_id: parent ? Number(parent) : null };
                 await api(dept ? `/departments/${dept.id}` : "/departments", { method: dept ? "PUT" : "POST", body });
                 refresh();
               }}>
      <Field label="Name"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
      <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      <Field label="Part of" hint="Optional: make this a sub-team of another department.">
        <Select value={parent} onChange={(e) => setParent(e.target.value)}>
          <option value="">— Top level —</option>
          {all.data?.filter((d) => d.id !== dept?.id).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
      </Field>
    </FormModal>
  );
}

export function PositionFormModal({ position, departmentId, onClose }: {
  position?: Position; departmentId?: number | null; onClose: () => void;
}) {
  const refresh = useOrgRefresh();
  const depts = useQuery({ queryKey: ["departments", false], queryFn: () => api<Department[]>("/departments") });
  const positions = useQuery({ queryKey: ["positions", "all"], queryFn: () => api<Position[]>("/positions") });
  const [title, setTitle] = useState(position?.title ?? "");
  const [description, setDescription] = useState(position?.description ?? "");
  const [dept, setDept] = useState(String(position?.department_id ?? departmentId ?? ""));
  const [reportsTo, setReportsTo] = useState(String(position?.reports_to_position_id ?? ""));
  const [isLead, setIsLead] = useState(position?.is_lead ?? false);
  const [isDeputy, setIsDeputy] = useState(position?.is_deputy ?? false);
  const [maxHolders, setMaxHolders] = useState(String(position?.max_holders ?? 1));
  const [rank, setRank] = useState(String(position?.rank_order ?? 100));

  return (
    <FormModal title={position ? `Edit ${position.title}` : "New position"} onClose={onClose}
               submitLabel={position ? "Save" : "Create position"}
               onSubmit={async () => {
                 const body = {
                   title, description: description || null, department_id: dept ? Number(dept) : null,
                   reports_to_position_id: reportsTo ? Number(reportsTo) : null, is_lead: isLead,
                   is_deputy: isDeputy, is_category: position?.is_category ?? false, max_holders: Number(maxHolders),
                   rank_order: Number(rank),
                 };
                 await api(position ? `/positions/${position.id}` : "/positions", { method: position ? "PUT" : "POST", body });
                 refresh();
               }}>
      <Field label="Title"><Input required minLength={2} value={title} onChange={(e) => setTitle(e.target.value)} autoFocus /></Field>
      <Field label="Department" hint="Leave empty for leadership positions (Chairperson, Secretary…).">
        <Select value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">— Leadership (no department) —</option>
          {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
      </Field>
      <Field label="Reports to">
        <Select value={reportsTo} onChange={(e) => setReportsTo(e.target.value)}>
          <option value="">— Nobody (top of the chart) —</option>
          {positions.data?.filter((p) => p.id !== position?.id).map((p) => (
            <option key={p.id} value={p.id}>{p.title}{p.department_name ? ` (${p.department_name})` : ""}</option>
          ))}
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="How many people can hold it">
          <Input type="number" min={1} max={100} required value={maxHolders} onChange={(e) => setMaxHolders(e.target.value)} />
        </Field>
        <Field label="Sort order" hint="Lower shows first.">
          <Input type="number" min={0} required value={rank} onChange={(e) => setRank(e.target.value)} />
        </Field>
      </div>
      <div className="flex gap-5 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" checked={isLead} onChange={(e) => setIsLead(e.target.checked)} /> Lead</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={isDeputy} onChange={(e) => setIsDeputy(e.target.checked)} /> Deputy</label>
      </div>
      <Field label="Description / responsibilities"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
    </FormModal>
  );
}

/** Chairperson's shortcut from the reporting lines: a lead or a category, placed under a chosen box. */
export function AddToChartModal({ parent, onClose }: { parent?: { id: number; title: string }; onClose: () => void }) {
  const refresh = useOrgRefresh();
  const depts = useQuery({ queryKey: ["departments", false], queryFn: () => api<Department[]>("/departments") });
  const positions = useQuery({ queryKey: ["positions", "all"], queryFn: () => api<Position[]>("/positions") });
  const [kind, setKind] = useState<"lead" | "category">("lead");
  const [title, setTitle] = useState("");
  const [dept, setDept] = useState("");
  const [reportsTo, setReportsTo] = useState(parent ? String(parent.id) : "");
  return (
    <FormModal title={parent ? `Add under ${parent.title}` : "Add to reporting lines"} submitLabel="Add" onClose={onClose}
               onSubmit={async () => {
                 await api("/positions", {
                   method: "POST",
                   body: { title, department_id: dept ? Number(dept) : null, reports_to_position_id: reportsTo ? Number(reportsTo) : null,
                           is_lead: kind === "lead", is_category: kind === "category" },
                 });
                 refresh();
               }}>
      <Field label="Type" hint={kind === "lead" ? "A person can be assigned to it. In a department, they get that department's Lead access."
                                                : "A heading that groups positions. Nobody is assigned to it."}>
        <Select value={kind} onChange={(e) => setKind(e.target.value as "lead" | "category")}>
          <option value="lead">Lead</option>
          <option value="category">Category</option>
        </Select>
      </Field>
      <Field label="Title"><Input required minLength={2} maxLength={80} value={title} onChange={(e) => setTitle(e.target.value)} autoFocus /></Field>
      <Field label="Department">
        <Select value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">— No department —</option>
          {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
      </Field>
      <Field label="Reports to">
        <Select value={reportsTo} onChange={(e) => setReportsTo(e.target.value)}>
          <option value="">— Nobody (top of the chart) —</option>
          {positions.data?.map((p) => (
            <option key={p.id} value={p.id}>{p.title}{p.department_name ? ` (${p.department_name})` : ""}</option>
          ))}
        </Select>
      </Field>
    </FormModal>
  );
}

/** Chairperson only: remove a box from the reporting lines, even while someone holds it. */
export function DeletePositionModal({ position, onClose, onDeleted }: {
  position: { id: number; title: string; holderCount: number }; onClose: () => void; onDeleted?: () => void;
}) {
  const refresh = useOrgRefresh();
  const [confirm, setConfirm] = useState("");
  const [reason, setReason] = useState("");
  return (
    <FormModal title={`Delete ${position.title}`} submitLabel="Delete permanently" danger onClose={onClose}
               onSubmit={async () => {
                 await api(`/positions/${position.id}/delete`, { method: "POST", body: { reason, confirm_title: confirm } });
                 refresh();
                 onDeleted?.();
               }}>
      <Alert tone="amber">
        <p className="font-medium">This happens straight away and can't be undone:</p>
        <ul className="mt-1 list-disc pl-5">
          {position.holderCount > 0 && <li>{position.holderCount} person(s) lose this position and the access it gives.</li>}
          <li>Anyone reporting to it will report one level up.</li>
        </ul>
        <p className="mt-2">People's history and the audit log will still show it.</p>
      </Alert>
      <Field label="Reason (recorded in the audit log)">
        <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
      </Field>
      <Field label={`Type “${position.title}” to confirm`}>
        <Input required value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
      </Field>
    </FormModal>
  );
}

export function AssignModal({ position, onClose }: { position: Position; onClose: () => void }) {
  const refresh = useOrgRefresh();
  const [person, setPerson] = useState<PersonRef | null>(null);
  const [from, setFrom] = useState(today());
  const [reason, setReason] = useState("appointed");
  const [note, setNote] = useState("");
  return (
    <FormModal title={`Assign someone as ${position.title}`} onClose={onClose} submitLabel="Assign"
               onSubmit={async () => {
                 if (!person) throw new Error("Choose a person");
                 await api(`/positions/${position.id}/assign`, {
                   method: "POST", body: { user_id: person.id, valid_from: from, start_reason: reason, note: note || null },
                 });
                 refresh();
               }}>
      <Field group label="Person"><PersonPicker value={person} onChange={setPerson} exclude={position.holders.map((h) => h.user.id)} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Starting"><Input type="date" required value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="Reason">
          <Select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="appointed">Appointed</option>
            <option value="promoted">Promoted</option>
            <option value="transferred">Transferred</option>
            <option value="reinstated">Reinstated</option>
          </Select>
        </Field>
      </div>
      <Field label="Note (optional)"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      {position.department_id && (
        <p className="text-xs text-slate-500">They will also be added to the {position.department_name} department if not already a member.</p>
      )}
    </FormModal>
  );
}

export function EndAssignmentModal({ holder, positionTitle, onClose }: {
  holder: Holder; positionTitle: string; onClose: () => void;
}) {
  const refresh = useOrgRefresh();
  const [to, setTo] = useState(today());
  const [reason, setReason] = useState("term_ended");
  const [note, setNote] = useState("");
  return (
    <FormModal title={`End ${holder.user.full_name} as ${positionTitle}`} onClose={onClose} submitLabel="End assignment" danger
               onSubmit={async () => {
                 await api(`/position-assignments/${holder.assignment_id}/end`, {
                   method: "POST", body: { end_reason: reason, valid_to: to, note: note || null },
                 });
                 refresh();
               }}>
      <Alert tone="amber">Any access granted to this position stops for them immediately. The record stays in their history.</Alert>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Last day"><Input type="date" required value={to} min={holder.valid_from} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label="Reason">
          <Select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="term_ended">Term ended</option>
            <option value="resigned">Resigned</option>
            <option value="removed">Removed</option>
            <option value="transferred">Transferred</option>
            <option value="promoted">Promoted</option>
          </Select>
        </Field>
      </div>
      <Field label="Note (optional)"><Input value={note} onChange={(e) => setNote(e.target.value)} /></Field>
    </FormModal>
  );
}

export function TransferModal({ holder, position, canManage, onClose }:
  { holder: Holder; position: Position; canManage: boolean; onClose: () => void }) {
  const refresh = useOrgRefresh();
  const positions = useQuery({ queryKey: ["positions", "all"], queryFn: () => api<Position[]>("/positions") });
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("promoted");
  const [effective, setEffective] = useState(today());
  return (
    <FormModal title={`Move ${holder.user.full_name}`} onClose={onClose} submitLabel="Move"
               onSubmit={async () => {
                 await api(`/position-assignments/${holder.assignment_id}/transfer`, {
                   method: "POST", body: { to_position_id: Number(target), reason, effective },
                 });
                 refresh();
               }}>
      <p className="text-sm text-slate-600">Ends their time as <strong>{position.title}</strong> and starts the new position on the same day.</p>
      <Field label="New position">
        <Select required value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Choose…</option>
          {positions.data?.filter((p) => p.id !== position.id && (canManage || !(p.is_lead || p.is_deputy))).map((p) => (
            <option key={p.id} value={p.id} disabled={p.holders.length >= p.max_holders}>
              {p.title}{p.department_name ? ` (${p.department_name})` : ""}{p.holders.length >= p.max_holders ? " — full" : ""}
            </option>
          ))}
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Type">
          <Select value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="promoted">Promotion</option>
            <option value="transferred">Transfer</option>
          </Select>
        </Field>
        <Field label="Effective"><Input type="date" required value={effective} min={holder.valid_from} onChange={(e) => setEffective(e.target.value)} /></Field>
      </div>
    </FormModal>
  );
}

export function AddMemberModal({ dept, existing, onClose }: { dept: Department; existing: number[]; onClose: () => void }) {
  const refresh = useOrgRefresh();
  const [person, setPerson] = useState<PersonRef | null>(null);
  const [from, setFrom] = useState(today());
  return (
    <FormModal title={`Add member to ${dept.name}`} onClose={onClose} submitLabel="Add member"
               onSubmit={async () => {
                 if (!person) throw new Error("Choose a person");
                 await api(`/departments/${dept.id}/members`, { method: "POST", body: { user_id: person.id, valid_from: from } });
                 refresh();
               }}>
      <Field group label="Person"><PersonPicker value={person} onChange={setPerson} exclude={existing} /></Field>
      <Field label="Joined on"><Input type="date" required value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
    </FormModal>
  );
}
