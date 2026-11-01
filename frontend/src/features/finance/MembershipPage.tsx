import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { FinAccount, MembershipCategory, MembershipRecord, MembershipSummary, PersonRef, Ref } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, Empty, Field, formatDate, Input, Modal, PageHeader, Select, Spinner, Tabs } from "../../components/ui";
import { uploadForm } from "../documents/DocumentModal";
import { FormModal, ReasonModal } from "../org/modals";
import { PersonPicker } from "../org/PersonPicker";
import { MODE_LABELS, money } from "./TransactionModal";

const TABS = [["members", "Memberships"], ["categories", "Categories & fees"]] as const;
type Tab = (typeof TABS)[number][0];
const STATUS: Record<string, ["slate" | "blue" | "green" | "amber" | "red", string]> = {
  pending: ["amber", "Fee pending"], paid: ["green", "Paid"], waived: ["blue", "Waived"], refunded: ["slate", "Refunded"], cancelled: ["red", "Cancelled"],
};
const today = () => new Date().toISOString().slice(0, 10);

export function MembershipPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "categories" ? "categories" : "members";
  return (
    <>
      <PageHeader title="Membership" subtitle="Only the Joint Secretary, Secretary, Vice Chairperson, Chairperson and Treasurer can see this list." />
      <Tabs tabs={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />
      {tab === "members" ? <Members /> : <Categories />}
    </>
  );
}

function useRefresh() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["memberships"] });
    qc.invalidateQueries({ queryKey: ["finance"] });
  };
}

function Members() {
  const { me } = useAuth();
  const canRecord = !!me?.can_record_members;
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [adding, setAdding] = useState(false);
  const [addingPaid, setAddingPaid] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [paying, setPaying] = useState<MembershipRecord | null>(null);
  const [changing, setChanging] = useState<{ m: MembershipRecord; to: "waived" | "cancelled" } | null>(null);
  const refresh = useRefresh();
  const search = new URLSearchParams(Object.entries({ q: q.trim(), status }).filter(([, v]) => v));
  const rows = useQuery({ queryKey: ["memberships", "list", search.toString()], queryFn: () => api<MembershipRecord[]>(`/memberships?${search}`) });
  const summary = useQuery({ queryKey: ["memberships", "summary"], queryFn: () => api<MembershipSummary>("/memberships/summary") });
  return (
    <>
      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <Tile label="Paid" value={String(summary.data?.by_status.paid ?? 0)} />
        <Tile label="Fee pending" value={String(summary.data?.by_status.pending ?? 0)} />
        <Tile label="Fees recorded in Finance" value={money(summary.data?.fees_collected ?? 0)} />
      </div>
      <Card title="Memberships" actions={canRecord && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setUploading(true)}>Upload paid members</Button>
          <Button variant="secondary" onClick={() => setAddingPaid(true)}>+ Add paid member</Button>
          <Button variant="secondary" onClick={() => setAdding(true)}>+ New with fee due</Button>
        </div>
      )}>
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          <Field label="Search"><Input value={q} placeholder="Name, father name, number, University ID or email" onChange={(e) => setQ(e.target.value)} /></Field>
          <Field label="Status">
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              {Object.entries(STATUS).map(([k, [, label]]) => <option key={k} value={k}>{label}</option>)}
            </Select>
          </Field>
        </div>
        {rows.isLoading ? <Spinner /> : rows.error ? <Alert>{errorMessage(rows.error)}</Alert> : !rows.data?.length ? <Empty>No memberships found.</Empty> : (
          <ul className="divide-y divide-slate-100 text-sm">
            {rows.data.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                <span className="min-w-0 flex-1 basis-56">
                  <span className="font-medium text-slate-900">{m.holder_name}</span>
                  <span className="block text-xs text-slate-500">
                    {m.membership_no}
                    {m.father_name && ` · Father: ${m.father_name}`}
                    {m.course && ` · ${m.course}`}{m.study_year && ` · Year ${m.study_year}`}
                    {m.category && ` · ${m.category.name} · ${money(m.fee_amount)}`}
                    {m.holder_uid && ` · ${m.holder_uid}`}{m.holder_email && ` · ${m.holder_email}`}
                    {m.valid_to && ` · valid upto ${formatDate(m.valid_to, false)}`}
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-1">
                  <Badge tone={STATUS[m.status][0]}>{STATUS[m.status][1]}</Badge>
                  {m.status === "paid" && m.valid_to && m.valid_to < today() && <Badge tone="red">Expired</Badge>}
                  {canRecord && m.status === "pending" && <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => setPaying(m)}>Record payment</Button>}
                  {canRecord && m.status === "pending" && <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setChanging({ m, to: "waived" })}>Waive</Button>}
                  {canRecord && (m.status === "pending" || m.status === "waived") && <Button variant="ghost" className="px-2 py-1 text-xs text-red-600" onClick={() => setChanging({ m, to: "cancelled" })}>Cancel</Button>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {adding && <NewMembership onClose={() => setAdding(false)} />}
      {addingPaid && <AddPaidMember onClose={() => setAddingPaid(false)} />}
      {uploading && <UploadMembers onClose={() => setUploading(false)} />}
      {paying && <PayModal m={paying} onClose={() => setPaying(null)} />}
      {changing && (
        <ReasonModal title={`${changing.to === "waived" ? "Waive the fee for" : "Cancel"} ${changing.m.holder_name}`} submitLabel={changing.to === "waived" ? "Waive fee" : "Cancel membership"}
                     danger={changing.to === "cancelled"} onClose={() => setChanging(null)}
                     onSubmit={async (reason) => { await api(`/memberships/${changing.m.id}/${changing.to}`, { method: "POST", body: { reason } }); refresh(); }} />
      )}
    </>
  );
}

const TEMPLATE = "Name,Father Name,Membership No,Course,Year,Membership Valid Upto\nAsha Rao,Ravi Rao,IETE-101,BE CSE,2,31/03/2027\n";

function downloadTemplate() {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
  link.download = "paid-members-template.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

/** The Treasurer's list of paid members. Nothing is saved unless every row is right. */
function UploadMembers({ onClose }: { onClose: () => void }) {
  const refresh = useRefresh();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ created: number; updated: number } | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setDone(await api<{ created: number; updated: number }>("/memberships/upload", { method: "POST", body: uploadForm(file) }));
      refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Upload paid members" open onClose={onClose}>
      {done ? (
        <div className="space-y-4">
          <Alert tone="green">{done.created} member(s) added and {done.updated} updated.</Alert>
          <div className="flex justify-end"><Button onClick={onClose}>Done</Button></div>
        </div>
      ) : (
        <div className="space-y-4 text-sm">
          {error && <Alert>{error}</Alert>}
          <p className="text-slate-600">Upload an Excel (.xlsx) or CSV file. The first row must have these headings:</p>
          <p className="rounded-lg bg-slate-50 px-3 py-2 font-medium text-slate-800">Name · Father Name · Membership No · Course · Year · Membership Valid Upto</p>
          <ul className="list-disc space-y-1 pl-5 text-slate-600">
            <li>Write dates day first, like 31/03/2027.</li>
            <li>If a Membership No already exists, that person's details are updated.</li>
            <li>If any row has a problem, nothing is saved and you'll see which rows to fix.</li>
          </ul>
          <button type="button" onClick={downloadTemplate} className="font-medium text-brand-700 hover:underline">Download a sample file</button>
          <Field label="File">
            <Input type="file" accept=".xlsx,.csv" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setError(null); }} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button disabled={!file || busy} onClick={upload}>{busy ? "Uploading…" : "Upload"}</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function AddPaidMember({ onClose }: { onClose: () => void }) {
  const refresh = useRefresh();
  const [name, setName] = useState("");
  const [father, setFather] = useState("");
  const [number, setNumber] = useState("");
  const [course, setCourse] = useState("");
  const [year, setYear] = useState("");
  const [valid, setValid] = useState("");
  return (
    <FormModal title="Add paid member" submitLabel="Add" onClose={onClose}
               onSubmit={async () => {
                 await api("/memberships/paid", { method: "POST", body: { holder_name: name, father_name: father, membership_no: number, course, study_year: year, valid_to: valid } });
                 refresh();
               }}>
      <Field label="Name"><Input required minLength={2} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
      <Field label="Father name"><Input required minLength={2} maxLength={120} value={father} onChange={(e) => setFather(e.target.value)} /></Field>
      <Field label="Membership no"><Input required maxLength={40} value={number} onChange={(e) => setNumber(e.target.value)} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Course"><Input required maxLength={80} value={course} onChange={(e) => setCourse(e.target.value)} /></Field>
        <Field label="Year"><Input required maxLength={20} value={year} onChange={(e) => setYear(e.target.value)} /></Field>
      </div>
      <Field label="Membership valid upto"><Input type="date" required value={valid} onChange={(e) => setValid(e.target.value)} /></Field>
    </FormModal>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm shadow-slate-900/[0.03]">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 font-display text-2xl font-semibold text-slate-900 tabular-nums">{value}</div>
    </div>
  );
}

function NewMembership({ onClose }: { onClose: () => void }) {
  const refresh = useRefresh();
  const categories = useQuery({ queryKey: ["memberships", "categories"], queryFn: () => api<MembershipCategory[]>("/membership/categories") });
  const usable = categories.data?.filter((c) => c.active) ?? [];
  const [team, setTeam] = useState(true);
  const [person, setPerson] = useState<PersonRef | null>(null);
  const [name, setName] = useState("");
  const [uid, setUid] = useState("");
  const [email, setEmail] = useState("");
  const [category, setCategory] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  return (
    <FormModal title="New membership" submitLabel="Create" onClose={onClose}
               onSubmit={async () => {
                 if (team && !person) throw new Error("Choose a person");
                 const chosen = category || usable[0]?.id;
                 if (!chosen) throw new Error("Add a category first");
                 await api("/memberships", { method: "POST", body: {
                   user_id: team ? person!.id : null, holder_name: team ? null : name, holder_uid: team ? null : uid || null,
                   holder_email: team ? null : email || null, category_id: Number(chosen), valid_from: from || null, valid_to: to || null } });
                 refresh();
               }}>
      {!usable.length && !categories.isLoading && <Alert tone="amber">Add a category on the Categories & fees tab first.</Alert>}
      <Field label="Category">
        <Select value={category} onChange={(e) => setCategory(e.target.value)}>
          {usable.map((c) => <option key={c.id} value={c.id}>{c.name} ({money(c.fee)})</option>)}
        </Select>
      </Field>
      <div className="flex gap-5 text-sm">
        <label className="flex items-center gap-2"><input type="radio" checked={team} onChange={() => setTeam(true)} /> Team member</label>
        <label className="flex items-center gap-2"><input type="radio" checked={!team} onChange={() => setTeam(false)} /> Someone else</label>
      </div>
      {team ? <Field group label="Person"><PersonPicker value={person} onChange={setPerson} /></Field> : (
        <>
          <Field label="Name"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="University ID"><Input value={uid} onChange={(e) => setUid(e.target.value)} /></Field>
            <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          </div>
        </>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Valid from" hint="Optional."><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="Valid to" hint="Optional."><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      </div>
    </FormModal>
  );
}

function PayModal({ m, onClose }: { m: MembershipRecord; onClose: () => void }) {
  const refresh = useRefresh();
  const { can } = useAuth();
  // People who only record memberships don't see balances, so they use the plain list of account names.
  const accounts = useQuery({ queryKey: ["finance", "pay-accounts"],
                              queryFn: () => can("finance.view") ? api<FinAccount[]>("/finance/accounts").then((a) => a.filter((x) => x.active) as Ref[]) : api<Ref[]>("/membership/account-names") });
  const [account, setAccount] = useState("");
  const [date, setDate] = useState(today());
  const [mode, setMode] = useState("upi");
  const [reference, setReference] = useState("");
  return (
    <FormModal title={`Record ${money(m.fee_amount)} from ${m.holder_name}`} submitLabel="Record payment" onClose={onClose}
               onSubmit={async () => {
                 const chosen = account || accounts.data?.[0]?.id;
                 if (!chosen) throw new Error("Add a finance account first");
                 await api(`/memberships/${m.id}/pay`, { method: "POST", body: { account_id: Number(chosen), paid_on: date, payment_mode: mode, payment_reference: reference || null } });
                 refresh();
               }}>
      <Field label="Paid into">
        <Select value={account} onChange={(e) => setAccount(e.target.value)}>
          {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Date"><Input type="date" required max={today()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        <Field label="Paid by">
          <Select value={mode} onChange={(e) => setMode(e.target.value)}>
            {Object.entries(MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Reference" hint="Optional. For example, the UPI reference."><Input value={reference} onChange={(e) => setReference(e.target.value)} /></Field>
    </FormModal>
  );
}

function Categories() {
  const { me } = useAuth();
  const refresh = useRefresh();
  const list = useQuery({ queryKey: ["memberships", "categories"], queryFn: () => api<MembershipCategory[]>("/membership/categories") });
  const [editing, setEditing] = useState<MembershipCategory | "new" | null>(null);
  const [name, setName] = useState("");
  const [fee, setFee] = useState("");
  const [active, setActive] = useState(true);
  const edit = (c: MembershipCategory | "new") => {
    setEditing(c);
    setName(c === "new" ? "" : c.name);
    setFee(c === "new" ? "" : c.fee);
    setActive(c === "new" ? true : c.active);
  };
  return (
    <Card title="Categories & fees" actions={me?.can_record_members && <Button onClick={() => edit("new")}>+ New category</Button>}>
      <p className="mb-3 text-xs text-slate-500">Changing a fee only affects new memberships.</p>
      {list.isLoading ? <Spinner /> : !list.data?.length ? <Empty>No categories yet. For example: Student Member.</Empty> : (
        <ul className="divide-y divide-slate-100 text-sm">
          {list.data.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-2 py-2.5">
              <span><span className="font-medium">{c.name}</span> <span className="text-slate-500">{money(c.fee)}</span> {!c.active && <Badge tone="red">Closed</Badge>}</span>
              {me?.can_record_members && <Button variant="ghost" onClick={() => edit(c)}>Edit</Button>}
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <FormModal title={editing === "new" ? "New category" : `Edit ${editing.name}`} submitLabel="Save" onClose={() => setEditing(null)}
                   onSubmit={async () => {
                     await api(editing === "new" ? "/membership/categories" : `/membership/categories/${editing.id}`,
                               { method: editing === "new" ? "POST" : "PUT", body: { name, fee, active } });
                     refresh();
                   }}>
          <Field label="Name"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
          <Field label="Fee (₹)"><Input type="number" min="0" step="0.01" required value={fee} onChange={(e) => setFee(e.target.value)} /></Field>
          {editing !== "new" && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Open for new memberships</label>}
        </FormModal>
      )}
    </Card>
  );
}
