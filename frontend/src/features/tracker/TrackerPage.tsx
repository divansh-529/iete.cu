import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, ApiError, errorMessage } from "../../api/client";
import type { PersonRef, TrackerAccess, TrackerDetail, TrackerSummary } from "../../api/types";
import { Alert, Badge, Button, Card, cx, Empty, Field, formatDate, Input, PageHeader, Select, Spinner, Tabs,
  Textarea } from "../../components/ui";
import { FormModal } from "../org/modals";
import { PersonPicker } from "../org/PersonPicker";
import { TRACKER_STATUS } from "./status";

// Offices a document usually goes to. Any other can be typed in.
const OFFICES = ["HOD", "AD", "ED", "Dean", "Director", "Registrar", "PVC", "VC"];

/** Paper documents carried from office to office for signatures, with a timeline for each. */
export function TrackerPage() {
  const [params, setParams] = useSearchParams();
  const [adding, setAdding] = useState(false);
  const [status, setStatus] = useState("");
  const access = useQuery({ queryKey: ["tracker", "access"], queryFn: () => api<TrackerAccess>("/tracker/access") });
  const tabs = access.data?.sees_all ? ([["mine", "Mine"], ["all", "All documents"]] as const) : ([["mine", "Mine"]] as const);
  const view = params.get("tab") === "all" && access.data?.sees_all ? "all" : "mine";
  const rows = useQuery({ queryKey: ["tracker", "list", view, status],
                          queryFn: () => api<TrackerSummary[]>(`/tracker?view=${view}${status ? `&status=${status}` : ""}`) });
  return (
    <>
      <PageHeader title="Document tracker"
                  subtitle="Track a paper document as it goes from office to office for signatures, such as AD → ED → PVC → VC."
                  actions={<Button onClick={() => setAdding(true)}>+ Track a document</Button>} />
      {tabs.length > 1 && <Tabs tabs={tabs} value={view} onChange={(t) => setParams({ tab: t })} />}
      <Card title={view === "all" ? "All documents" : "Documents I carry or added"}
            actions={<Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40">
              <option value="">Any status</option>
              {Object.entries(TRACKER_STATUS).map(([k, [, label]]) => <option key={k} value={k}>{label}</option>)}
            </Select>}>
        {rows.isLoading ? <Spinner /> : rows.error ? <Alert>{errorMessage(rows.error)}</Alert> : !rows.data?.length ? (
          <Empty>No documents yet. Use “Track a document” to add one.</Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {rows.data.map((d) => (
              <li key={d.id}>
                <Link to={`/app/tracker/${d.id}`} className="flex flex-wrap items-center justify-between gap-3 py-3 hover:bg-slate-50">
                  <span className="min-w-0 flex-1 basis-64">
                    <span className="font-medium text-slate-900">{d.title}</span>
                    <span className="block text-xs text-slate-500">
                      {d.reference_no && `${d.reference_no} · `}Carried by {d.assigned_to.full_name} · updated {formatDate(d.last_update_at, false)}
                    </span>
                  </span>
                  <span className="flex items-center gap-3">
                    <Progress signed={d.steps_signed} total={d.steps_total} />
                    {d.current_step ? <Badge tone="amber">At {d.current_step}</Badge>
                      : <Badge tone={TRACKER_STATUS[d.status][0]}>{TRACKER_STATUS[d.status][1]}</Badge>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {adding && <NewTracker onClose={() => setAdding(false)} />}
    </>
  );
}

function Progress({ signed, total }: { signed: number; total: number }) {
  return (
    <span className="flex items-center gap-2 text-xs text-slate-500">
      <span className="flex gap-0.5">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={cx("h-2 w-4 rounded-full", i < signed ? "bg-emerald-500" : "bg-slate-200")} />
        ))}
      </span>
      {signed}/{total} signed
    </span>
  );
}

function NewTracker({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [reference, setReference] = useState("");
  const [description, setDescription] = useState("");
  const [person, setPerson] = useState<PersonRef | null>(null);
  const [steps, setSteps] = useState<string[]>(["AD", "ED", "PVC", "VC"]);
  const [custom, setCustom] = useState("");
  const add = (s: string) => { if (s.trim()) setSteps([...steps, s.trim()]); };
  const move = (i: number, by: number) => {
    const next = [...steps];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    setSteps(next);
  };
  return (
    <FormModal title="Track a document" submitLabel="Start tracking" onClose={onClose}
               onSubmit={async () => {
                 if (!person) throw new ApiError(422, "PERSON_REQUIRED", "Choose who will carry the document.");
                 const doc = await api<TrackerDetail>("/tracker", { method: "POST", body: {
                   title, reference_no: reference || null, description: description || null, assigned_to: person.id, steps } });
                 qc.invalidateQueries({ queryKey: ["tracker"] });
                 navigate(`/app/tracker/${doc.id}`);
               }}>
      <Field label="What is the document?"><Input required minLength={3} maxLength={200} value={title} placeholder="Venue permission for Tech Fest"
                                                  onChange={(e) => setTitle(e.target.value)} autoFocus /></Field>
      <Field label="Reference or letter no. (optional)"><Input maxLength={80} value={reference} onChange={(e) => setReference(e.target.value)} /></Field>
      <Field label="Details (optional)"><Textarea maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      <Field group label="Who will carry it?"><PersonPicker value={person} onChange={setPerson} autoFocus={false} /></Field>
      <Field group label="Signatures needed, in order">
        <ol className="space-y-1.5">
          {steps.map((s, i) => (
            <li key={`${s}-${i}`} className="flex items-center gap-2 rounded-md border border-slate-200 px-3 py-1.5 text-sm">
              <span className="w-5 text-slate-400">{i + 1}.</span>
              <span className="flex-1 font-medium">{s}</span>
              <button type="button" disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move ${s} up`} className="px-1 text-slate-500 disabled:opacity-30">↑</button>
              <button type="button" disabled={i === steps.length - 1} onClick={() => move(i, 1)} aria-label={`Move ${s} down`} className="px-1 text-slate-500 disabled:opacity-30">↓</button>
              <button type="button" onClick={() => setSteps(steps.filter((_, j) => j !== i))} aria-label={`Remove ${s}`} className="px-1 text-red-600">✕</button>
            </li>
          ))}
        </ol>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {OFFICES.map((o) => (
            <button key={o} type="button" onClick={() => add(o)}
                    className="rounded-full border border-slate-300 px-2.5 py-0.5 text-xs font-medium text-slate-600 hover:border-brand-400 hover:text-brand-700">+ {o}</button>
          ))}
        </div>
        <div className="mt-2 flex gap-2">
          <Input placeholder="Another office…" maxLength={60} value={custom} onChange={(e) => setCustom(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(custom); setCustom(""); } }} />
          <Button type="button" variant="secondary" onClick={() => { add(custom); setCustom(""); }}>Add</Button>
        </div>
      </Field>
      {!steps.length && <Alert tone="amber">Add at least one signature.</Alert>}
    </FormModal>
  );
}
