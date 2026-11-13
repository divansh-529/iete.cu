import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, ApiError, errorMessage } from "../../api/client";
import type { PersonRef, TrackerDetail, TrackerEvent } from "../../api/types";
import { Alert, Badge, Button, Card, cx, Field, formatDate, Input, PageHeader, Select, Spinner, Textarea } from "../../components/ui";
import { FormModal } from "../org/modals";
import { PersonPicker } from "../org/PersonPicker";
import { STEP_RECORDS, STEP_STATUS, TRACKER_STATUS } from "./status";

const today = () => new Date().toLocaleDateString("en-CA");   // yyyy-mm-dd in the viewer's time zone

export function TrackerDetailPage() {
  const id = Number(useParams().id);
  const doc = useQuery({ queryKey: ["tracker", "doc", id], queryFn: () => api<TrackerDetail>(`/tracker/${id}`) });
  const [modal, setModal] = useState<"assign" | "step" | "cancel" | "delete" | "handover" | "decline" | null>(null);
  if (doc.isLoading) return <Spinner />;
  if (doc.error || !doc.data) return <Alert>{errorMessage(doc.error)}</Alert>;
  const d = doc.data;
  return (
    <>
      <Link to="/app/tracker" className="text-sm text-brand-600 hover:underline">← Document tracker</Link>
      <PageHeader title={d.title}
                  subtitle={`${d.reference_no ? `${d.reference_no} · ` : ""}Added by ${d.created_by.full_name} on ${formatDate(d.created_at, false)}`}
                  actions={<Badge tone={TRACKER_STATUS[d.status][0]}>{TRACKER_STATUS[d.status][1]}</Badge>} />
      {d.handover && <HandoverBanner doc={d} onDecline={() => setModal("decline")} />}
      <Card className="mb-6">
        <Steps doc={d} />
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3 text-sm">
          <span className="text-slate-600">Carried by <span className="font-medium text-slate-900">{d.assigned_to.full_name}</span></span>
          <span className="flex flex-wrap gap-2">
            {d.can_hand_over && <Button onClick={() => setModal("handover")}>Hand over</Button>}
            {d.can_add_step && <Button variant="secondary" onClick={() => setModal("step")}>+ Add a signature</Button>}
            {d.can_manage && <Button variant="secondary" onClick={() => setModal("assign")}>Change who carries it</Button>}
            {d.can_manage && <Button variant="ghost" className="text-red-600" onClick={() => setModal("cancel")}>Cancel</Button>}
            {d.can_delete && <Button variant="ghost" className="text-red-700" onClick={() => setModal("delete")}>Delete</Button>}
          </span>
        </div>
        {d.description && <p className="mt-3 whitespace-pre-line text-sm text-slate-600">{d.description}</p>}
      </Card>
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3"><Card title="Timeline"><Timeline doc={d} /></Card></div>
        {d.can_record && d.current_step && <div className="lg:col-span-2"><RecordStep doc={d} /></div>}
      </div>
      {modal === "assign" && <Reassign id={d.id} onClose={() => setModal(null)} />}
      {modal === "step" && <AddStep id={d.id} onClose={() => setModal(null)} />}
      {modal === "cancel" && <CancelTracking id={d.id} onClose={() => setModal(null)} />}
      {modal === "delete" && <DeleteTracking id={d.id} onClose={() => setModal(null)} />}
      {modal === "handover" && <HandOver doc={d} onClose={() => setModal(null)} />}
      {modal === "decline" && <DeclineHandover id={d.id} onClose={() => setModal(null)} />}
    </>
  );
}

/** AD ✓ → ED (here now) → PVC → VC */
function Steps({ doc }: { doc: TrackerDetail }) {
  const current = doc.steps.find((s) => s.status !== "signed");
  return (
    <ol className="flex flex-wrap items-center gap-y-3">
      {doc.steps.map((s, i) => {
        const here = doc.status === "in_progress" && s.id === current?.id;
        return (
          <li key={s.id} className="flex items-center">
            {i > 0 && <span className={cx("mx-2 h-0.5 w-6 sm:w-10", s.status === "signed" ? "bg-emerald-400" : "bg-slate-200")} />}
            <span className="flex flex-col items-center gap-1">
              <span className={cx("flex h-9 min-w-9 items-center justify-center rounded-full px-2 text-sm font-semibold ring-2",
                s.status === "signed" ? "bg-emerald-500 text-white ring-emerald-500"
                  : s.status === "rejected" ? "bg-red-500 text-white ring-red-500"
                  : here ? "bg-white text-brand-700 ring-brand-500" : "bg-white text-slate-400 ring-slate-200")}>
                {s.status === "signed" ? "✓" : i + 1}
              </span>
              <span className={cx("text-xs font-medium", here ? "text-brand-700" : "text-slate-600")}>{s.authority}</span>
              {here && <Badge tone={STEP_STATUS[s.status][0]}>{s.status === "pending" ? "Here now" : STEP_STATUS[s.status][1]}</Badge>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function describe(e: TrackerEvent): string {
  switch (e.kind) {
    case "created": return `Started tracking and gave it to ${e.assigned_to?.full_name}. Signatures: ${e.note}`;
    case "assigned": return `Gave it to ${e.assigned_to?.full_name} to carry`;
    case "step_added": return `Added a signature: ${e.note}`;
    case "completed": return "All signatures done ✓";
    case "cancelled": return "Cancelled tracking";
    case "handover_requested": return `Asked ${e.assigned_to?.full_name} to take it over`;
    case "handover_accepted": return `${e.assigned_to?.full_name} accepted it and carries it now`;
    case "handover_declined": return `${e.assigned_to?.full_name} couldn't take it`;
    case "handover_withdrawn": return `Withdrew the handover to ${e.assigned_to?.full_name}`;
    case "submitted": return `Submitted at ${e.step}`;
    case "returned": return `${e.step} returned it with changes`;
    case "signed": return `Signed by ${e.step} ✓`;
    case "rejected": return `${e.step} rejected it`;
    default: return e.kind;
  }
}

function Timeline({ doc }: { doc: TrackerDetail }) {
  const [error, setError] = useState<string | null>(null);
  async function open(updateId: number) {
    const tab = window.open("", "_blank");   // opened first, or the browser blocks it as a pop-up
    try {
      const { url } = await api<{ url: string }>(`/tracker/${doc.id}/updates/${updateId}/file`);
      if (tab) tab.location.href = url;
      else window.location.href = url;
    } catch (err) {
      tab?.close();
      setError(errorMessage(err));
    }
  }
  const dot = (kind: string) => ({ signed: "bg-emerald-500", completed: "bg-emerald-500", rejected: "bg-red-500", returned: "bg-amber-500",
                                   cancelled: "bg-slate-400", submitted: "bg-brand-500" } as Record<string, string>)[kind] ?? "bg-slate-300";
  return (
    <>
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      <ol className="relative space-y-5 border-l border-slate-200 pl-5">
        {[...doc.timeline].reverse().map((e) => (
          <li key={e.id} className="relative">
            <span className={cx("absolute -left-[1.6rem] top-1 h-3 w-3 rounded-full ring-4 ring-white", dot(e.kind))} />
            <div className="text-sm font-medium text-slate-900">{describe(e)}</div>
            <div className="text-xs text-slate-500">
              {e.happened_on ? `On ${formatDate(e.happened_on, false)} · ` : ""}recorded by {e.by.full_name}, {formatDate(e.at)}
            </div>
            {e.note && e.kind !== "created" && e.kind !== "step_added" && <p className="mt-1 text-sm text-slate-600">“{e.note}”</p>}
            {e.file_name && <button onClick={() => open(e.id)} className="mt-1 text-xs font-medium text-brand-600 hover:underline">📎 {e.file_name}</button>}
          </li>
        ))}
      </ol>
    </>
  );
}

function RecordStep({ doc }: { doc: TrackerDetail }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState("submitted");
  const [on, setOn] = useState(today());
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const needsNote = status === "returned" || status === "rejected";
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("status", status);
    form.append("happened_on", on);
    if (note.trim()) form.append("note", note.trim());
    if (file) form.append("file", file);
    try {
      await api(`/tracker/${doc.id}/updates`, { method: "POST", body: form });
      qc.invalidateQueries({ queryKey: ["tracker"] });
      setNote("");
      setFile(null);
      setFileKey((k) => k + 1);
      setStatus("submitted");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card title={`Update at ${doc.current_step}`}>
      <form onSubmit={save} className="space-y-3">
        {error && <Alert>{error}</Alert>}
        <Field label="What happened?">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STEP_RECORDS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </Select>
        </Field>
        <Field label="Date"><Input type="date" required max={today()} value={on} onChange={(e) => setOn(e.target.value)} /></Field>
        <Field label={needsNote ? "What did the office say?" : "Note (optional)"}>
          <Textarea required={needsNote} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <Field label="Photo or scan (optional)" hint="JPG, PNG or PDF">
          <Input key={fileKey} type="file" accept=".jpg,.jpeg,.png,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        {status === "rejected" && <Alert tone="amber">Rejected closes this document. Start a new one if it will be sent again.</Alert>}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Saving…" : "Save update"}</Button>
      </form>
    </Card>
  );
}

function Reassign({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [person, setPerson] = useState<PersonRef | null>(null);
  return (
    <FormModal title="Change who carries it" submitLabel="Save" onClose={onClose}
               onSubmit={async () => {
                 if (!person) throw new ApiError(422, "PERSON_REQUIRED", "Choose someone.");
                 await api(`/tracker/${id}/assignee`, { method: "PUT", body: { user_id: person.id } });
                 qc.invalidateQueries({ queryKey: ["tracker"] });
               }}>
      <Field group label="Person"><PersonPicker value={person} onChange={setPerson} /></Field>
    </FormModal>
  );
}

function AddStep({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [authority, setAuthority] = useState("");
  return (
    <FormModal title="Add a signature" submitLabel="Add" onClose={onClose}
               onSubmit={async () => {
                 await api(`/tracker/${id}/steps`, { method: "POST", body: { authority } });
                 qc.invalidateQueries({ queryKey: ["tracker"] });
               }}>
      <Field label="Office" hint="Added at the end, after the others"><Input required maxLength={60} value={authority} placeholder="Dean"
                                                                              onChange={(e) => setAuthority(e.target.value)} autoFocus /></Field>
    </FormModal>
  );
}

function CancelTracking({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  return (
    <FormModal title="Cancel tracking" submitLabel="Cancel tracking" danger onClose={onClose}
               onSubmit={async () => {
                 await api(`/tracker/${id}/cancel`, { method: "POST", body: { reason } });
                 qc.invalidateQueries({ queryKey: ["tracker"] });
               }}>
      <Field label="Why?"><Input required minLength={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></Field>
    </FormModal>
  );
}

function DeleteTracking({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [reason, setReason] = useState("");
  return (
    <FormModal title="Delete this document" submitLabel="Delete" danger onClose={onClose}
               onSubmit={async () => {
                 await api(`/tracker/${id}/delete`, { method: "POST", body: { reason } });
                 qc.invalidateQueries({ queryKey: ["tracker"] });
                 navigate("/app/tracker");
               }}>
      <Alert tone="amber">It disappears from the tracker for everyone. The audit log keeps a record of the deletion.</Alert>
      <Field label="Reason"><Input required minLength={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></Field>
    </FormModal>
  );
}

/** A handover waiting to be accepted. The person it's offered to accepts or declines here. */
function HandoverBanner({ doc, onDecline }: { doc: TrackerDetail; onDecline: () => void }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const h = doc.handover!;
  async function run(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      await api(`/tracker/${doc.id}/${path}`, { method: "POST", body });
      qc.invalidateQueries({ queryKey: ["tracker"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mb-6 rounded-xl border border-violet-200 bg-violet-50 px-5 py-4 text-sm">
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      <p className="font-medium text-violet-900">
        {doc.can_answer_handover ? `${doc.assigned_to.full_name} wants to hand this document to you.`
          : `Waiting for ${h.to.full_name} to accept the handover from ${doc.assigned_to.full_name}.`}
      </p>
      {h.note && <p className="mt-1 text-violet-800">“{h.note}”</p>}
      <p className="mt-1 text-xs text-violet-700">Asked {formatDate(h.at)}. Until it's accepted, {doc.assigned_to.full_name} still carries it.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {doc.can_answer_handover && <Button disabled={busy} onClick={() => run("handover/answer", { accept: true })}>Accept and carry it</Button>}
        {doc.can_answer_handover && <Button variant="secondary" disabled={busy} onClick={onDecline}>Decline</Button>}
        {doc.can_withdraw_handover && <Button variant="secondary" disabled={busy} onClick={() => run("handover/withdraw")}>Withdraw handover</Button>}
      </div>
    </div>
  );
}

function HandOver({ doc, onClose }: { doc: TrackerDetail; onClose: () => void }) {
  const qc = useQueryClient();
  const [person, setPerson] = useState<PersonRef | null>(null);
  const [note, setNote] = useState("");
  return (
    <FormModal title="Hand over for the next signatures" submitLabel="Ask them to take it" onClose={onClose}
               onSubmit={async () => {
                 if (!person) throw new ApiError(422, "PERSON_REQUIRED", "Choose who will take it.");
                 await api(`/tracker/${doc.id}/handover`, { method: "POST", body: { user_id: person.id, note: note || null } });
                 qc.invalidateQueries({ queryKey: ["tracker"] });
               }}>
      <Field group label="Hand it to"><PersonPicker value={person} onChange={setPerson} exclude={[doc.assigned_to.id]} /></Field>
      <Field label="Note (optional)"><Textarea maxLength={500} value={note} placeholder={doc.current_step ? `Please take it to ${doc.current_step}` : ""}
                                               onChange={(e) => setNote(e.target.value)} /></Field>
      <p className="text-xs text-slate-500">They must accept before it becomes theirs. Until then you still carry it.</p>
    </FormModal>
  );
}

function DeclineHandover({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [reason, setReason] = useState("");
  return (
    <FormModal title="Decline the handover" submitLabel="Decline" onClose={onClose}
               onSubmit={async () => {
                 await api(`/tracker/${id}/handover/answer`, { method: "POST", body: { accept: false, reason } });
                 qc.invalidateQueries({ queryKey: ["tracker"] });
                 navigate("/app/tracker");
               }}>
      <Field label="Why can't you take it?"><Input required minLength={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></Field>
    </FormModal>
  );
}
