import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../../api/client";
import type { DepartmentDetail } from "../../api/types";
import { Alert, Button, Field, Input, Modal, Select, Textarea } from "../../components/ui";

/** A recruiter proposes a new member for a department. The account stays "waiting for
 *  approval" until the Chairperson, Vice Chair or Secretary approves it. */
export function ProposeMemberModal({ department, canManage, onClose }: {
  department: DepartmentDetail; canManage: boolean; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [positionId, setPositionId] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  // Leads recruit ordinary members only; lead and deputy seats are for administrators.
  const openPositions = department.positions.filter((p) =>
    p.holders.length < p.max_holders && (canManage || !(p.is_lead || p.is_deputy)));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/departments/${department.id}/member-proposals`, { method: "POST", body: {
        full_name: name, email, position_id: positionId ? Number(positionId) : null, note: note || null } });
      qc.invalidateQueries({ queryKey: ["proposals"] });
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={sent ? "Sent for approval" : `Propose a new member · ${department.name}`} open onClose={onClose}>
      {sent ? (
        <div className="space-y-4">
          <Alert tone="green">
            <strong>{name}</strong> has been proposed for {department.name}. The Chairperson, Vice Chairperson or Secretary
            will review it. Once approved, {email} gets an email with their sign-in details.
          </Alert>
          <p className="text-sm text-slate-600">You can follow it on the <strong>Recruitment</strong> page.</p>
          <div className="flex justify-end"><Button onClick={onClose}>Done</Button></div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          {error && <Alert>{error}</Alert>}
          <Field label="Full name"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
          <Field label="Gmail address" hint="Their sign-in details are emailed here once the account is approved.">
            <Input type="email" required placeholder="name@gmail.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Position (optional)" hint="Only positions with a free seat are listed.">
            <Select value={positionId} onChange={(e) => setPositionId(e.target.value)}>
              <option value="">Member only, no position</option>
              {openPositions.map((p) => (
                <option key={p.id} value={p.id}>{p.title}{p.is_lead ? " (lead)" : p.is_deputy ? " (deputy)" : ""}</option>
              ))}
            </Select>
          </Field>
          <Field label="Note for the approvers (optional)">
            <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Interviewed on 3 Nov, strong at anchoring" />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Sending…" : "Send for approval"}</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
