import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { Appeal, Transaction, TransactionDetail } from "../../api/types";
import { Alert, Badge, Button, Empty, Field, formatDate, Input, Modal, Spinner } from "../../components/ui";
import { fileSize, uploadForm, ACCEPT } from "../documents/DocumentModal";
import { FormModal, ReasonModal } from "../org/modals";

export const money = (n: string | number) =>
  `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const STATUS: Record<string, [string, "slate" | "blue" | "green" | "amber" | "red"]> = {
  submitted: ["Waiting to verify", "amber"], verified: ["Waiting to approve", "blue"], posted: ["Posted", "green"], rejected: ["Rejected", "red"], appealed: ["Under appeal", "amber"],
};
export const TYPE_LABELS: Record<string, string> = {
  income: "Income", expense: "Expense", transfer_in: "Transfer in", transfer_out: "Transfer out", reversal: "Reversal",
};
export const MODE_LABELS: Record<string, string> = {
  cash: "Cash", upi: "UPI", bank_transfer: "Bank transfer", cheque: "Cheque", card: "Card", other: "Other",
};

export function TransactionStatus({ t }: { t: Transaction }) {
  if (t.reversed_by_code) return <Badge tone="slate">Reversed</Badge>;
  const [label, tone] = t.for_chairperson && t.status !== "appealed" ? ["Waiting for Chairperson", "amber"] as const : STATUS[t.status] ?? [t.status, "slate"];
  return <Badge tone={tone}>{label}</Badge>;
}

export function TransactionList({ rows, onOpen, empty }: { rows: Transaction[]; onOpen: (id: number) => void; empty: string }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <ul className="divide-y divide-slate-100 text-sm">
      {rows.map((t) => (
        <li key={t.id}>
          <button onClick={() => onOpen(t.id)} className="flex w-full flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5 text-left hover:bg-slate-50">
            <span className="min-w-0 flex-1 basis-56">
              <span className="block truncate font-medium text-slate-900">{t.purpose}</span>
              <span className="block text-xs text-slate-500">
                {t.code} · {TYPE_LABELS[t.txn_type]} · {t.account.name} · {formatDate(t.txn_date, false)}{t.counterparty && ` · ${t.counterparty}`}
              </span>
            </span>
            <span className="flex items-center gap-3">
              <TransactionStatus t={t} />
              <span className={`font-semibold tabular-nums ${t.is_credit ? "text-emerald-700" : "text-slate-900"}`}>
                {t.is_credit ? "+" : "−"}{money(t.amount)}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function TransactionModal({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const tx = useQuery({ queryKey: ["transaction", id], queryFn: () => api<TransactionDetail>(`/finance/transactions/${id}`) });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState<"reject" | "reverse" | "appeal" | null>(null);
  const [comment, setComment] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  async function act(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      const updated = await api<TransactionDetail>(path, { method: "POST", body });
      qc.setQueryData(["transaction", id], updated);
      qc.invalidateQueries({ queryKey: ["finance"] });
      qc.invalidateQueries({ queryKey: ["memberships"] });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function open(attachmentId: number, inline: boolean) {
    const tab = window.open("", "_blank");
    try {
      const { url } = await api<{ url: string }>(`/finance/transactions/${id}/attachments/${attachmentId}/download?inline=${inline}`);
      if (tab) tab.location.href = url;
      else window.location.href = url;
    } catch (err) {
      tab?.close();
      setError(errorMessage(err));
    }
  }

  if (!tx.data) {
    return <Modal title="Transaction" open onClose={onClose}>{tx.error ? <Alert>{errorMessage(tx.error)}</Alert> : <Spinner />}</Modal>;
  }
  const t = tx.data;
  const base = `/finance/expenses/${id}`;

  return (
    <Modal title={t.code} open onClose={onClose}>
      <div className="space-y-5 text-sm">
        {error && <Alert>{error}</Alert>}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TransactionStatus t={t} />
          <span className={`font-display text-2xl font-semibold tabular-nums ${t.is_credit ? "text-emerald-700" : "text-slate-900"}`}>
            {t.is_credit ? "+" : "−"}{money(t.amount)}
          </span>
        </div>
        <p className="whitespace-pre-line text-slate-800">{t.purpose}</p>
        {t.status === "rejected" && t.rejection_reason && <Alert>Rejected: “{t.rejection_reason}”</Alert>}
        {t.for_chairperson && t.status !== "appealed"
          ? <Alert tone="amber">The Chairperson has to approve this before it counts in a balance.</Alert>
          : t.needs_chairperson && <Alert tone="amber">This is above ₹5,000, so the Chairperson has to approve it.</Alert>}
        <dl className="space-y-1.5">
          <Row label="Type">{TYPE_LABELS[t.txn_type]}</Row>
          <Row label="Account">{t.account.name}</Row>
          <Row label="Date">{formatDate(t.txn_date, false)}</Row>
          {t.counterparty && <Row label={t.is_credit ? "From" : "Paid to"}>{t.counterparty}</Row>}
          {t.category && <Row label="Category">{t.category}</Row>}
          {t.payment_mode && <Row label="Payment">{MODE_LABELS[t.payment_mode]}{t.payment_reference && ` · ${t.payment_reference}`}</Row>}
          {t.event && <Row label="Event"><Link to={`/app/events/${t.event.id}`} className="text-brand-700 hover:underline">{t.event.name}</Link></Row>}
          {t.department && <Row label="Department">{t.department.name}</Row>}
          <Row label={t.txn_type === "expense" ? "Submitted by" : "Recorded by"}>{t.submitted_by.full_name} · {formatDate(t.submitted_at)}</Row>
          {t.verified_by && <Row label="Verified by">{t.verified_by.full_name} · {formatDate(t.verified_at)}</Row>}
          {t.approved_by && <Row label="Approved by">{t.approved_by.full_name} · {formatDate(t.approved_at)}</Row>}
          {t.reverses_code && <Row label="Reverses">{t.reverses_code}</Row>}
          {t.reversed_by_code && <Row label="Reversed by">{t.reversed_by_code}</Row>}
        </dl>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Bills and proofs</h3>
          {t.attachments.length ? (
            <ul className="divide-y divide-slate-100">
              {t.attachments.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-slate-800">{a.original_filename}</span>
                    <span className="text-xs text-slate-500">{a.kind} · {fileSize(a.size_bytes)} · {a.added_by.full_name}</span>
                  </span>
                  <button onClick={() => open(a.id, true)} className="shrink-0 text-brand-700 hover:underline">Open</button>
                </li>
              ))}
            </ul>
          ) : <p className="text-slate-500">None attached.</p>}
          {t.can_attach && (
            <>
              <Button variant="secondary" className="mt-2" disabled={busy} onClick={() => fileInput.current?.click()}>Attach a file</Button>
              <input ref={fileInput} type="file" hidden aria-label="Attachment file" accept={ACCEPT}
                     onChange={(e) => {
                       const file = e.target.files?.[0];
                       e.target.value = "";
                       if (file) act(`/finance/transactions/${id}/attachments`, uploadForm(file, { kind: t.is_credit ? "receipt" : "bill" }));
                     }} />
            </>
          )}
        </section>

        {t.appeals.length > 0 && (
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Appeals</h3>
            <ul className="space-y-3">
              {t.appeals.map((a) => <AppealRound key={a.id} appeal={a} />)}
            </ul>
            {t.can_comment && (
              <form className="mt-3 flex gap-2" onSubmit={(e) => {
                e.preventDefault();
                act(`/finance/transactions/${id}/appeal/comments`, { body: comment }).then(() => setComment(""));
              }}>
                <Input aria-label="Review comment" placeholder="Add a review comment" required maxLength={1000}
                       value={comment} onChange={(e) => setComment(e.target.value)} />
                <Button type="submit" variant="secondary" disabled={busy}>Comment</Button>
              </form>
            )}
          </section>
        )}

        {t.can_appeal && (
          <div className="border-t border-slate-100 pt-4">
            <Button disabled={busy} onClick={() => setAsking("appeal")}>Appeal with documents</Button>
          </div>
        )}

        {(t.can_verify || t.can_approve || t.can_reject || t.can_reverse) && (
          <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
            {t.can_verify && <Button disabled={busy} onClick={() => act(`${base}/verify`)}>Verify</Button>}
            {t.can_approve && <Button disabled={busy} onClick={() => act(`${base}/approve`)}>Approve and post</Button>}
            {t.can_reject && <Button variant="danger" disabled={busy} onClick={() => setAsking("reject")}>{t.status === "appealed" ? "Reject again" : "Reject"}</Button>}
            {t.can_reverse && <Button variant="danger" disabled={busy} onClick={() => setAsking("reverse")}>Reverse</Button>}
          </div>
        )}
      </div>
      {asking === "reject" && (
        <ReasonModal title={`Reject ${t.code}`} label="Reason (the person who submitted it will see it)" submitLabel="Reject" danger
                     onClose={() => setAsking(null)} onSubmit={(reason) => act(`${base}/reject`, { reason })} />
      )}
      {asking === "appeal" && <AppealModal id={id} code={t.code} onClose={() => setAsking(null)} onDone={(updated) => {
        qc.setQueryData(["transaction", id], updated);
        qc.invalidateQueries({ queryKey: ["finance"] });
      }} />}
      {asking === "reverse" && (
        <ReasonModal title={`Reverse ${t.code}`} label="Reason (recorded with the reversal)" submitLabel="Reverse" danger
                     warning={`This adds an opposite entry dated today, and the balance changes by ${money(t.amount)}. The original entry stays on record.`}
                     onClose={() => setAsking(null)} onSubmit={(reason) => act(`/finance/transactions/${id}/reverse`, { reason })} />
      )}
    </Modal>
  );
}

function AppealRound({ appeal: a }: { appeal: Appeal }) {
  return (
    <li className="rounded-lg border border-slate-200 p-3">
      {a.rejection_reason && <p className="text-slate-600">Rejected: “{a.rejection_reason}”</p>}
      <p className="mt-1 whitespace-pre-line text-slate-800">{a.note}</p>
      <p className="mt-1 text-xs text-slate-500">{a.submitted_by.full_name} · {formatDate(a.submitted_at)}</p>
      {a.comments.length > 0 && (
        <ul className="mt-2 space-y-1.5 border-l-2 border-slate-100 pl-3">
          {a.comments.map((c) => (
            <li key={c.id}>
              <span className="whitespace-pre-line text-slate-800">{c.body}</span>
              <span className="block text-xs text-slate-500">{c.author.full_name} · {formatDate(c.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
      {a.outcome && (
        <p className={`mt-2 font-medium ${a.outcome === "approved" ? "text-emerald-700" : "text-red-700"}`}>
          {a.outcome === "approved" ? "Approved" : `Rejected again: “${a.decision_note}”`}
          <span className="block text-xs font-normal text-slate-500">{a.decided_by?.full_name} · {a.decided_at && formatDate(a.decided_at)}</span>
        </p>
      )}
    </li>
  );
}

function AppealModal({ id, code, onClose, onDone }: { id: number; code: string; onClose: () => void; onDone: (t: TransactionDetail) => void }) {
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  return (
    <FormModal title={`Appeal ${code}`} submitLabel="Send appeal" onClose={onClose} onSubmit={async () => {
      const form = new FormData();
      form.append("note", note);
      files.forEach((f) => form.append("files", f));
      onDone(await api<TransactionDetail>(`/finance/transactions/${id}/appeal`, { method: "POST", body: form }));
    }}>
      <Field label="Why should this be approved?">
        <Input required minLength={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
      </Field>
      <Field label="Supporting documents" hint="1 to 5 files. All leaders can read them, and only you can add more.">
        <input type="file" required multiple accept={ACCEPT} aria-label="Supporting documents" className="block w-full text-sm"
               onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
      </Field>
    </FormModal>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="shrink-0 text-slate-500">{label}</dt>
      <dd className="min-w-0 text-right text-slate-800">{children}</dd>
    </div>
  );
}
