import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { ChartNode, Department, Position, Term } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, cx, Empty, Field, formatDate, Input, Modal, PageHeader, Spinner } from "../../components/ui";
import { AddToChartModal, DepartmentFormModal, PositionFormModal } from "./modals";
import { OrgChart } from "./OrgChart";
import { PositionList } from "./PositionList";

const TABS = [
  ["chart", "Org chart"],
  ["departments", "Departments"],
  ["leadership", "Leadership"],
  ["terms", "Terms"],
] as const;
type Tab = (typeof TABS)[number][0];

export function OrgPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "chart";
  return (
    <>
      <PageHeader title="Organisation" subtitle="Positions, reporting lines and departments. Changes take effect immediately and are kept in history." />
      <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map(([key, label]) => (
          <button key={key} onClick={() => setParams({ tab: key })}
                  className={cx("-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium",
                    tab === key ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-700")}>
            {label}
          </button>
        ))}
      </div>
      {tab === "chart" && <ChartTab />}
      {tab === "departments" && <DepartmentsTab />}
      {tab === "leadership" && <LeadershipTab />}
      {tab === "terms" && <TermsTab />}
    </>
  );
}

function ChartTab() {
  const { me } = useAuth();
  const [adding, setAdding] = useState(false);
  const chart = useQuery({ queryKey: ["chart"], queryFn: () => api<ChartNode[]>("/org/chart") });
  if (chart.isLoading) return <Spinner />;
  if (chart.error) return <Alert>{errorMessage(chart.error)}</Alert>;
  const vacant = chart.data!.filter((n) => n.holders.length === 0 && !n.is_category).length;
  const editable = !!me?.user.is_super_admin;
  return (
    <Card title="Reporting lines"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {vacant > 0 && <Badge tone="amber">{vacant} vacant position(s)</Badge>}
              {editable && <Button onClick={() => setAdding(true)}>+ Add lead or category</Button>}
            </div>
          }>
      {chart.data!.length ? <OrgChart nodes={chart.data!} editable={editable} /> : <Empty>No positions yet. Create them under Leadership or a department.</Empty>}
      {adding && <AddToChartModal onClose={() => setAdding(false)} />}
    </Card>
  );
}

function DepartmentsTab() {
  const { can } = useAuth();
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const depts = useQuery({
    queryKey: ["departments", showArchived],
    queryFn: () => api<Department[]>(`/departments?include_archived=${showArchived}`),
  });
  const names = new Map(depts.data?.map((d) => [d.id, d.name]));
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Show archived
        </label>
        {can("org.manage") && <Button onClick={() => setCreating(true)}>+ New department</Button>}
      </div>
      {depts.isLoading ? <Spinner /> : depts.error ? <Alert>{errorMessage(depts.error)}</Alert>
        : !depts.data?.length ? <Card><Empty>No departments yet.</Empty></Card> : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {depts.data.map((d) => (
            <Link key={d.id} to={`/app/org/departments/${d.id}`}
                  className="block rounded-lg border border-slate-200 bg-white p-4 shadow-xs transition-colors hover:border-brand-500">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-slate-900">{d.name}</h3>
                {d.status === "archived" && <Badge tone="red">Archived</Badge>}
              </div>
              {d.parent_id && <p className="text-xs text-slate-500">Part of {names.get(d.parent_id) ?? "another department"}</p>}
              <p className="mt-2 text-sm text-slate-600">
                {d.leads.length ? <>Lead: {d.leads.map((l) => l.full_name).join(", ")}</> : <span className="text-amber-700">No lead assigned</span>}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {d.member_count} member(s) · {d.position_count} position(s)
                {d.vacant_positions > 0 && <span className="text-amber-700"> · {d.vacant_positions} vacant</span>}
              </p>
            </Link>
          ))}
        </div>
      )}
      {creating && <DepartmentFormModal onClose={() => setCreating(false)} />}
    </>
  );
}

function LeadershipTab() {
  const { can } = useAuth();
  const [creating, setCreating] = useState(false);
  const positions = useQuery({ queryKey: ["positions", "leadership"], queryFn: () => api<Position[]>("/positions?leadership=true") });
  return (
    <Card title="Leadership positions"
          actions={can("org.manage") && <Button onClick={() => setCreating(true)}>+ New position</Button>}>
      <p className="mb-2 text-xs text-slate-500">Organisation-wide roles that do not belong to a single department.</p>
      {positions.isLoading ? <Spinner /> : positions.error ? <Alert>{errorMessage(positions.error)}</Alert>
        : <PositionList positions={positions.data ?? []} canAssign={can("org.assign")} canManage={can("org.manage")} />}
      {creating && <PositionFormModal departmentId={null} onClose={() => setCreating(false)} />}
    </Card>
  );
}

function TermsTab() {
  const { can } = useAuth();
  const terms = useQuery({ queryKey: ["terms"], queryFn: () => api<Term[]>("/terms") });
  const [editing, setEditing] = useState<Term | "new" | null>(null);
  return (
    <Card title="Committee terms" actions={can("org.manage") && <Button onClick={() => setEditing("new")}>+ New term</Button>}>
      <p className="mb-3 text-xs text-slate-500">Terms group history and leaderboards (e.g. 2026-27). One term is marked current.</p>
      {terms.isLoading ? <Spinner /> : !terms.data?.length ? <Empty>No terms yet.</Empty> : (
        <ul className="divide-y divide-slate-100">
          {terms.data.map((t) => (
            <li key={t.id} className="flex items-center justify-between gap-2 py-2.5 text-sm">
              <span>
                <span className="font-medium">{t.name}</span>{" "}
                <span className="text-slate-500">{formatDate(t.starts_on, false)} – {formatDate(t.ends_on, false)}</span>{" "}
                {t.is_current && <Badge tone="green">Current</Badge>}
              </span>
              {can("org.manage") && <Button variant="ghost" onClick={() => setEditing(t)}>Edit</Button>}
            </li>
          ))}
        </ul>
      )}
      {editing && <TermModal term={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </Card>
  );
}

function TermModal({ term, onClose }: { term: Term | null; onClose: () => void }) {
  const qc = useQueryClient();
  const year = new Date().getFullYear();
  const [name, setName] = useState(term?.name ?? `${year}-${String(year + 1).slice(2)}`);
  const [starts, setStarts] = useState(term?.starts_on ?? `${year}-07-01`);
  const [ends, setEnds] = useState(term?.ends_on ?? `${year + 1}-06-30`);
  const [current, setCurrent] = useState(term?.is_current ?? true);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      const body = { name, starts_on: starts, ends_on: ends, is_current: current };
      await api(term ? `/terms/${term.id}` : "/terms", { method: term ? "PUT" : "POST", body });
      qc.invalidateQueries({ queryKey: ["terms"] });
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal title={term ? `Edit term ${term.name}` : "New term"} open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field label="Name"><Input required value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Starts"><Input type="date" required value={starts} onChange={(e) => setStarts(e.target.value)} /></Field>
          <Field label="Ends"><Input type="date" required value={ends} onChange={(e) => setEnds(e.target.value)} /></Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={current} onChange={(e) => setCurrent(e.target.checked)} /> This is the current term
        </label>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit">Save</Button>
        </div>
      </form>
    </Modal>
  );
}
