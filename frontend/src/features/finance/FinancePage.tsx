import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { Department, EventSummary, FinAccount, Reconciliation, Ref, Transaction, TransactionDetail } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, Empty, Field, formatDate, Input, PageHeader, Select, Spinner, Tabs } from "../../components/ui";
import { FormModal } from "../org/modals";
import { MODE_LABELS, money, TransactionList, TransactionModal } from "./TransactionModal";

const today = () => new Date().toISOString().slice(0, 10);

export function FinancePage() {
  const { can, me } = useAuth();
  const viewer = can("finance.view");
  const approver = can("finance.expense.verify") || can("finance.expense.approve");
  const tabs = [
    ...(viewer ? [["accounts", "Accounts"], ["transactions", "Transactions"], ["rejected", "Rejected"]] as const : []),
    ...(approver ? [["to_act", "Needs my action"]] as const : []),
    ...(can("finance.expense.submit") ? [["mine", "My expenses"]] as const : []),
    ...(viewer || me?.can_view_roster ? [["appeals", "Appeals"]] as const : []),
    ...(viewer ? [["reconciliation", "Reconciliation"]] as const : []),
  ];
  type Tab = (typeof tabs)[number][0];
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab");
  const tab = (tabs.find(([k]) => k === asked)?.[0] ?? tabs[0]?.[0]) as Tab | undefined;
  const opened = Number(params.get("open")) || null;
  const open = (id: number) => setParams((p) => { p.set("open", String(id)); return p; });
  const close = () => setParams((p) => { p.delete("open"); return p; });

  return (
    <>
      <PageHeader title="Finance" subtitle="An entry counts in a balance only after it is approved. Posted entries are never edited; mistakes are reversed." />
      {tab && <Tabs tabs={tabs} value={tab} onChange={(t) => setParams({ tab: t })} />}
      {!tab && <Card><Empty>You don't have access to finance.</Empty></Card>}
      {tab === "accounts" && <AccountsTab />}
      {tab === "transactions" && <TransactionsTab onOpen={open} />}
      {tab === "rejected" && <Queue query="status=rejected" onOpen={open} empty="No rejected transactions." />}
      {tab === "to_act" && <Queue query="view=to_act" onOpen={open} empty="Nothing is waiting for you." />}
      {tab === "appeals" && <Queue query="view=appeals" onOpen={open} empty="No appeals." />}
      {tab === "mine" && <MineTab onOpen={open} />}
      {tab === "reconciliation" && <ReconciliationTab />}
      {opened && <TransactionModal id={opened} onClose={close} />}
    </>
  );
}

function useFinanceRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["finance"] });
}

function useAccounts(enabled = true) {
  return useQuery({ queryKey: ["finance", "accounts"], enabled, queryFn: () => api<FinAccount[]>("/finance/accounts") });
}

function AccountsTab() {
  const { can } = useAuth();
  const list = useAccounts();
  const [editing, setEditing] = useState<FinAccount | "new" | null>(null);
  const [moving, setMoving] = useState(false);
  const accounts = list.data ?? [];
  const active = accounts.filter((a) => a.active);
  return (
    <>
      <div className="mb-3 flex flex-wrap justify-end gap-2">
        {can("finance.accounts.manage") && active.length > 1 && <Button variant="secondary" onClick={() => setMoving(true)}>Transfer between accounts</Button>}
        {can("finance.accounts.manage") && <Button onClick={() => setEditing("new")}>+ New account</Button>}
      </div>
      {list.isLoading ? <Spinner /> : list.error ? <Alert>{errorMessage(list.error)}</Alert>
        : !accounts.length ? <Card><Empty>No accounts yet. Add each bank account or fund with its balance on the day you start.</Empty></Card> : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {accounts.map((a) => (
            <section key={a.id} className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm shadow-slate-900/[0.03]">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-slate-900">{a.name}</h3>
                {!a.active && <Badge tone="red">Closed</Badge>}
              </div>
              <div className="mt-3 text-xs font-medium uppercase tracking-wide text-slate-500">Book balance</div>
              <div className="font-display text-2xl font-semibold text-slate-900 tabular-nums">{money(a.book_balance)}</div>
              <div className="mt-2 text-xs">
                {a.reconciled_to ? (
                  <span className={Number(a.reconciled_difference) ? "text-amber-700" : "text-emerald-700"}>
                    Reconciled up to {formatDate(a.reconciled_to, false)}
                    {Number(a.reconciled_difference) !== 0 && ` · ${money(a.reconciled_difference!)} difference`}
                  </span>
                ) : <span className="text-slate-500">Not reconciled yet</span>}
              </div>
              <div className="mt-2 text-xs text-slate-500">
                Opening {money(a.opening_balance)} on {formatDate(a.opening_date, false)} · in {money(a.credits)} · out {money(a.debits)}
              </div>
              {can("finance.accounts.manage") && <Button variant="ghost" className="mt-2 -ml-3" onClick={() => setEditing(a)}>Edit</Button>}
            </section>
          ))}
        </div>
      )}
      {editing && <AccountModal account={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
      {moving && <TransferModal accounts={active} onClose={() => setMoving(false)} />}
    </>
  );
}

function AccountModal({ account, onClose }: { account: FinAccount | null; onClose: () => void }) {
  const refresh = useFinanceRefresh();
  const [name, setName] = useState(account?.name ?? "");
  const [description, setDescription] = useState(account?.description ?? "");
  const [opening, setOpening] = useState(account?.opening_balance ?? "0.00");
  const [date, setDate] = useState(account?.opening_date ?? today());
  const [active, setActive] = useState(account?.active ?? true);
  return (
    <FormModal title={account ? `Edit ${account.name}` : "New account"} submitLabel="Save" onClose={onClose}
               onSubmit={async () => {
                 const body = { name, description: description || null, opening_balance: opening, opening_date: date, active };
                 await api(account ? `/finance/accounts/${account.id}` : "/finance/accounts", { method: account ? "PUT" : "POST", body });
                 refresh();
               }}>
      <Field label="Name" hint="For example: Main Society Account, Event Fund."><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
      <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Opening balance (₹)" hint="Locks once the account has entries."><Input type="number" step="0.01" required value={opening} onChange={(e) => setOpening(e.target.value)} /></Field>
        <Field label="As of"><Input type="date" required value={date} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
      {account && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Open for new entries</label>}
    </FormModal>
  );
}

function TransferModal({ accounts, onClose }: { accounts: FinAccount[]; onClose: () => void }) {
  const refresh = useFinanceRefresh();
  const [from, setFrom] = useState(String(accounts[0].id));
  const [to, setTo] = useState(String(accounts[1].id));
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today());
  const [purpose, setPurpose] = useState("");
  const pick = (value: string, set: (v: string) => void) => (
    <Select value={value} onChange={(e) => set(e.target.value)}>
      {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
    </Select>
  );
  return (
    <FormModal title="Transfer between accounts" submitLabel="Transfer" onClose={onClose}
               onSubmit={async () => {
                 await api("/finance/transfers", { method: "POST", body: { from_account_id: Number(from), to_account_id: Number(to), amount, txn_date: date, purpose } });
                 refresh();
               }}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="From">{pick(from, setFrom)}</Field>
        <Field label="To">{pick(to, setTo)}</Field>
        <Field label="Amount (₹)"><Input type="number" min="0.01" step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus /></Field>
        <Field label="Date"><Input type="date" required max={today()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
      <Field label="Purpose"><Input required minLength={3} value={purpose} onChange={(e) => setPurpose(e.target.value)} /></Field>
    </FormModal>
  );
}

function TransactionsTab({ onOpen }: { onOpen: (id: number) => void }) {
  const { can } = useAuth();
  const accounts = useAccounts();
  const [account, setAccount] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [recording, setRecording] = useState(false);
  const search = new URLSearchParams(Object.entries({ account_id: account, status: "posted", start, end }).filter(([, v]) => v));
  const rows = useQuery({ queryKey: ["finance", "transactions", search.toString()], queryFn: () => api<Transaction[]>(`/finance/transactions?${search}`) });
  const usable = accounts.data?.filter((a) => a.active) ?? [];
  return (
    <Card title="Transactions" actions={can("finance.income.record") && usable.length > 0 && <Button onClick={() => setRecording(true)}>+ Record income</Button>}>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Field label="Account">
          <Select value={account} onChange={(e) => setAccount(e.target.value)}>
            <option value="">All</option>
            {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
        </Field>
        <Field label="From"><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
        <Field label="To"><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
      </div>
      {rows.isLoading ? <Spinner /> : rows.error ? <Alert>{errorMessage(rows.error)}</Alert>
        : <TransactionList rows={rows.data ?? []} onOpen={onOpen} empty="No posted transactions yet." />}
      {recording && (
        <MoneyModal kind="income" accounts={usable} onClose={() => setRecording(false)} onDone={onOpen} />
      )}
    </Card>
  );
}

function Queue({ query, onOpen, empty }: { query: string; onOpen: (id: number) => void; empty: string }) {
  const rows = useQuery({ queryKey: ["finance", query], queryFn: () => api<Transaction[]>(`/finance/transactions?${query}`) });
  if (rows.isLoading) return <Spinner />;
  if (rows.error) return <Alert>{errorMessage(rows.error)}</Alert>;
  return <Card><TransactionList rows={rows.data ?? []} onOpen={onOpen} empty={empty} /></Card>;
}

function MineTab({ onOpen }: { onOpen: (id: number) => void }) {
  const names = useQuery({ queryKey: ["finance", "account-names"], queryFn: () => api<Ref[]>("/finance/account-names") });
  const [submitting, setSubmitting] = useState(false);
  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button disabled={!names.data?.length} title={names.data?.length ? undefined : "An account has to be added first"}
                onClick={() => setSubmitting(true)}>+ Submit an expense</Button>
      </div>
      <Queue query="view=mine" onOpen={onOpen} empty="You haven't submitted any expenses." />
      {submitting && names.data && <MoneyModal kind="expense" accounts={names.data} onClose={() => setSubmitting(false)} onDone={onOpen} />}
    </>
  );
}

function MoneyModal({ kind, accounts, onClose, onDone }: {
  kind: "income" | "expense"; accounts: Ref[]; onClose: () => void; onDone: (id: number) => void;
}) {
  const refresh = useFinanceRefresh();
  const expense = kind === "expense";
  const depts = useQuery({ queryKey: ["departments", false], enabled: expense, queryFn: () => api<Department[]>("/departments") });
  const events = useQuery({ queryKey: ["events", "calendar"], queryFn: () => api<EventSummary[]>("/events") });
  const [account, setAccount] = useState(String(accounts[0].id));
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(today());
  const [party, setParty] = useState("");
  const [purpose, setPurpose] = useState("");
  const [category, setCategory] = useState("");
  const [mode, setMode] = useState("upi");
  const [reference, setReference] = useState("");
  const [dept, setDept] = useState("");
  const [event, setEvent] = useState("");
  return (
    <FormModal title={expense ? "Submit an expense" : "Record income"} submitLabel={expense ? "Submit" : "Record"} onClose={onClose}
               onSubmit={async () => {
                 const created = await api<TransactionDetail>(expense ? "/finance/expenses" : "/finance/income", {
                   method: "POST",
                   body: { account_id: Number(account), amount, txn_date: date, counterparty: party, purpose, category: category || null,
                           payment_mode: mode, payment_reference: reference || null,
                           department_id: dept ? Number(dept) : null, event_id: event ? Number(event) : null },
                 });
                 refresh();
                 onDone(created.id);
               }}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount (₹)"><Input type="number" min="0.01" step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus /></Field>
        <Field label="Date"><Input type="date" required max={today()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
      </div>
      <Field label={expense ? "Paid to" : "Received from"}><Input required minLength={2} value={party} onChange={(e) => setParty(e.target.value)} /></Field>
      <Field label="Purpose"><Input required minLength={3} value={purpose} onChange={(e) => setPurpose(e.target.value)} /></Field>
      <Field label="Account">
        <Select value={account} onChange={(e) => setAccount(e.target.value)}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </Select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Paid by">
          <Select value={mode} onChange={(e) => setMode(e.target.value)}>
            {Object.entries(MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
        <Field label="Reference" hint="Optional."><Input value={reference} onChange={(e) => setReference(e.target.value)} /></Field>
      </div>
      {expense && (
        <Field label="Department" hint="The department this is for. Needed unless you can submit for the whole forum.">
          <Select value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">— None —</option>
            {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </Field>
      )}
      <Field label="Event" hint="Optional.">
        <Select value={event} onChange={(e) => setEvent(e.target.value)}>
          <option value="">— None —</option>
          {events.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </Select>
      </Field>
      <Field label="Category" hint="Optional. For example: Printing, Travel."><Input value={category} onChange={(e) => setCategory(e.target.value)} /></Field>
      <p className="text-xs text-slate-500">You can attach the {expense ? "bill" : "receipt"} on the next screen.</p>
    </FormModal>
  );
}

function ReconciliationTab() {
  const { can } = useAuth();
  const refresh = useFinanceRefresh();
  const accounts = useAccounts();
  const rows = useQuery({ queryKey: ["finance", "reconciliations"], queryFn: () => api<Reconciliation[]>("/finance/reconciliations") });
  const [adding, setAdding] = useState(false);
  const [account, setAccount] = useState("");
  const [date, setDate] = useState(today());
  const [statement, setStatement] = useState("");
  const [notes, setNotes] = useState("");
  return (
    <Card title="Reconciliation" actions={can("finance.reconcile") && !!accounts.data?.length && <Button onClick={() => setAdding(true)}>+ Reconcile</Button>}>
      <p className="mb-3 text-xs text-slate-500">Compare a bank statement with the book balance at the same date. Each record is kept as it was entered.</p>
      {rows.isLoading ? <Spinner /> : !rows.data?.length ? <Empty>No reconciliations yet.</Empty> : (
        <ul className="divide-y divide-slate-100 text-sm">
          {rows.data.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <span className="min-w-0">
                <span className="font-medium text-slate-900">{r.account.name}</span> <span className="text-slate-500">at {formatDate(r.period_end, false)}</span>
                <span className="block text-xs text-slate-500">
                  Statement {money(r.statement_balance)} · Books {money(r.book_balance)} · {r.reconciled_by.full_name}{r.notes && ` · ${r.notes}`}
                </span>
              </span>
              {Number(r.difference) === 0 ? <Badge tone="green">Matches</Badge> : <Badge tone="amber">{money(r.difference)} difference</Badge>}
            </li>
          ))}
        </ul>
      )}
      {adding && (
        <FormModal title="Reconcile an account" submitLabel="Save" onClose={() => setAdding(false)}
                   onSubmit={async () => {
                     await api("/finance/reconciliations", { method: "POST", body: {
                       account_id: Number(account || accounts.data![0].id), period_end: date, statement_balance: statement, notes: notes || null } });
                     refresh();
                   }}>
          <Field label="Account">
            <Select value={account} onChange={(e) => setAccount(e.target.value)}>
              {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Statement date"><Input type="date" required max={today()} value={date} onChange={(e) => setDate(e.target.value)} /></Field>
            <Field label="Statement balance (₹)"><Input type="number" step="0.01" required value={statement} onChange={(e) => setStatement(e.target.value)} /></Field>
          </div>
          <Field label="Notes" hint="Optional. For example, why there is a difference."><Input value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        </FormModal>
      )}
    </Card>
  );
}

/** The Finance tab on an event page. */
export function EventFinance({ eventId }: { eventId: number }) {
  const [opened, setOpened] = useState<number | null>(null);
  const rows = useQuery({ queryKey: ["finance", "event", eventId], queryFn: () => api<Transaction[]>(`/finance/transactions?event_id=${eventId}`) });
  const posted = rows.data?.filter((t) => t.status === "posted") ?? [];
  const total = posted.reduce((sum, t) => sum + (t.is_credit ? Number(t.amount) : -Number(t.amount)), 0);
  return (
    <Card title="Finance" actions={posted.length > 0 && <span className="text-sm font-semibold tabular-nums">Net {money(total)}</span>}>
      {rows.isLoading ? <Spinner /> : rows.error ? <Alert>{errorMessage(rows.error)}</Alert>
        : <TransactionList rows={rows.data ?? []} onOpen={setOpened} empty="No income or expenses linked to this event yet." />}
      {opened && <TransactionModal id={opened} onClose={() => setOpened(null)} />}
    </Card>
  );
}
