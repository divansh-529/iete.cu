import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { AllowedTransition, EventDetail, PersonRef, TaskSummary } from "../../api/types";
import { Alert, Button, Card, cx, Empty, Field, formatDate, fromInputDateTime, Input, PageHeader, Spinner,
  Tabs } from "../../components/ui";
import { FolderBrowser } from "../documents/FolderBrowser";
import { ReasonModal } from "../org/modals";
import { PersonPicker } from "../org/PersonPicker";
import { TaskFormModal } from "../tasks/TaskFormModal";
import { TaskTable } from "../tasks/TaskTable";
import { EventFormModal } from "./EventFormModal";
import { APPROVAL_STEPS, EVENT_STATUS, EventStatusBadge } from "./status";

const TABS = [["overview", "Overview"], ["team", "Team"], ["tasks", "Tasks"], ["checklist", "Checklist & milestones"],
  ["documents", "Documents"], ["history", "History"]] as const;
type Tab = (typeof TABS)[number][0];

export function EventDetailPage() {
  const id = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "overview";
  const qc = useQueryClient();
  const event = useQuery({ queryKey: ["event", id], queryFn: () => api<EventDetail>(`/events/${id}`) });
  const [editing, setEditing] = useState(false);
  const [moving, setMoving] = useState<AllowedTransition | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (event.isLoading) return <Spinner />;
  if (event.error || !event.data) return <Alert>{errorMessage(event.error)}</Alert>;
  const e = event.data;

  /** Every event action returns the updated event; store it and refresh the lists. */
  async function act(path: string, method: string, body?: unknown) {
    setError(null);
    try {
      const updated = await api<EventDetail>(`/events/${id}${path}`, { method, body });
      qc.setQueryData(["event", id], updated);
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
    } catch (err) {
      setError(errorMessage(err));
      throw err;
    }
  }

  const sentBack = e.status === "draft" && e.history[0]?.remarks && e.history[0].from_status !== null ? e.history[0] : null;

  return (
    <>
      <Link to="/app/events" className="text-sm text-brand-600 hover:underline">← Events</Link>
      <PageHeader title={e.name}
                  subtitle={[e.category, e.departments.map((d) => d.name).join(", ") || "Organisation-wide",
                    `run by ${e.owner.full_name}`].filter(Boolean).join(" · ")}
                  actions={
                    <div className="flex flex-wrap items-center gap-2">
                      <EventStatusBadge status={e.status} />
                      {e.can_edit && <Button variant="secondary" onClick={() => setEditing(true)}>Edit details</Button>}
                      {e.allowed_transitions.map((t) => (
                        <Button key={t.to_status} variant={t.tone}
                                onClick={() => t.needs_remarks ? setMoving(t) : act("/transition", "POST", { to_status: t.to_status }).catch(() => undefined)}>
                          {t.label}
                        </Button>
                      ))}
                    </div>
                  } />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {sentBack && (
        <div className="mb-4"><Alert tone="amber">
          <strong>Sent back for changes</strong> by {sentBack.changed_by.full_name}: “{sentBack.remarks}”. Update the details, then submit the proposal again.
        </Alert></div>
      )}
      <ApprovalSteps status={e.status} />
      <Tabs tabs={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />
      {tab === "overview" && <Overview e={e} />}
      {tab === "team" && <TeamTab e={e} act={act} />}
      {tab === "tasks" && <EventTasks e={e} />}
      {tab === "checklist" && <ChecklistTab e={e} act={act} />}
      {tab === "documents" && <FolderBrowser eventId={e.id} />}
      {tab === "history" && <HistoryTab e={e} />}
      {editing && <EventFormModal event={e} onClose={() => setEditing(false)} />}
      {moving && (
        <ReasonModal title={moving.label} label="Reason (the event's owner will see it)" submitLabel={moving.label}
                     danger={moving.tone === "danger"} onClose={() => setMoving(null)}
                     onSubmit={(remarks) => act("/transition", "POST", { to_status: moving.to_status, remarks })} />
      )}
    </>
  );
}

function ApprovalSteps({ status }: { status: EventDetail["status"] }) {
  if (status === "cancelled" || status === "archived") return null;
  const order = APPROVAL_STEPS.map(([s]) => s);
  const current = status === "open_for_registration" ? order.indexOf("approved") : order.indexOf(status);
  return (
    <ol className="mb-6 flex flex-wrap items-center gap-x-2 gap-y-2 text-xs font-medium">
      {APPROVAL_STEPS.map(([key, label], i) => (
        <li key={key} className="flex items-center gap-2">
          <span className={cx("flex items-center gap-1.5 rounded-full px-3 py-1",
            i < current ? "bg-emerald-50 text-emerald-700" : i === current ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-500")}>
            {i < current ? "✓" : i + 1} {label}
          </span>
          {i < APPROVAL_STEPS.length - 1 && <span className="text-slate-300">→</span>}
        </li>
      ))}
    </ol>
  );
}

function Overview({ e }: { e: EventDetail }) {
  const rows: [string, string][] = [
    ["Starts", formatDate(e.starts_at)], ["Ends", formatDate(e.ends_at)], ["Venue", e.venue ?? "—"],
    ["Capacity", e.capacity ? String(e.capacity) : "—"],
    ["Planned budget", e.budget_planned ? `₹${Number(e.budget_planned).toLocaleString("en-IN")}` : "—"],
    ["Public page", e.is_public ? "Yes, once approved" : "No"],
  ];
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="About" className="lg:col-span-2">
        {e.description ? <p className="whitespace-pre-line text-sm text-slate-700">{e.description}</p>
          : <Empty>No description yet.</Empty>}
      </Card>
      <Card title="Details">
        <dl className="space-y-2 text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-800">{v}</dd></div>
          ))}
        </dl>
      </Card>
    </div>
  );
}

type Act = (path: string, method: string, body?: unknown) => Promise<void>;

const ROLES = ["coordinator", "volunteer", "speaker", "judge", "anchor", "photographer"];

function TeamTab({ e, act }: { e: EventDetail; act: Act }) {
  const [person, setPerson] = useState<PersonRef | null>(null);
  const [role, setRole] = useState("volunteer");
  async function add(ev: FormEvent) {
    ev.preventDefault();
    if (!person) return;
    await act("/team", "POST", { user_id: person.id, event_role: role }).then(() => setPerson(null)).catch(() => undefined);
  }
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title={`Team (${e.team.length + 1})`} className="lg:col-span-2">
        <ul className="divide-y divide-slate-100">
          <li className="flex items-center justify-between py-2.5 text-sm">
            <span className="font-medium">{e.owner.full_name}</span><span className="text-xs text-slate-500">Owner</span>
          </li>
          {e.team.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-2 py-2.5 text-sm">
              <span><span className="font-medium">{m.user.full_name}</span> <span className="text-xs capitalize text-slate-500">· {m.event_role}</span></span>
              {e.can_manage && (
                <Button variant="ghost" className="px-2 py-1 text-xs text-red-600"
                        onClick={() => act(`/team/${m.id}`, "DELETE").catch(() => undefined)}>Remove</Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
      {e.can_manage && (
        <Card title="Add to team">
          <form onSubmit={add} className="space-y-3">
            <Field group label="Person"><PersonPicker value={person} onChange={setPerson} autoFocus={false}
                                                exclude={[e.owner.id, ...e.team.map((m) => m.user.id)]} /></Field>
            <Field label="Role on this event">
              <Input list="event-roles" required value={role} onChange={(ev) => setRole(ev.target.value)} />
              <datalist id="event-roles">{ROLES.map((r) => <option key={r} value={r} />)}</datalist>
            </Field>
            <Button type="submit" disabled={!person} className="w-full">Add to team</Button>
          </form>
        </Card>
      )}
    </div>
  );
}

function EventTasks({ e }: { e: EventDetail }) {
  const [creating, setCreating] = useState(false);
  const tasks = useQuery({ queryKey: ["tasks", "event", e.id], queryFn: () => api<TaskSummary[]>(`/tasks?event_id=${e.id}`) });
  return (
    <Card title="Tasks for this event" actions={e.can_add_tasks && <Button onClick={() => setCreating(true)}>+ New task</Button>}>
      {tasks.isLoading ? <Spinner /> : tasks.error ? <Alert>{errorMessage(tasks.error)}</Alert>
        : <TaskTable tasks={tasks.data ?? []} showHome={false} empty="No tasks yet. Break the event into tasks and assign them." />}
      {creating && <TaskFormModal eventId={e.id} departmentId={e.departments[0]?.id ?? null} onClose={() => setCreating(false)} />}
    </Card>
  );
}

function ChecklistTab({ e, act }: { e: EventDetail; act: Act }) {
  const [label, setLabel] = useState("");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const done = e.checklist.filter((c) => c.done_at).length;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title={`Checklist (${done}/${e.checklist.length})`}>
        {!e.checklist.length && <Empty>Nothing on the checklist yet.</Empty>}
        <ul className="space-y-1">
          {e.checklist.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={!!c.done_at} disabled={!e.can_manage}
                       onChange={(ev) => act(`/checklist/${c.id}`, "PUT", { label: c.label, done: ev.target.checked }).catch(() => undefined)} />
                <span className={c.done_at ? "text-slate-400 line-through" : ""}>{c.label}</span>
              </label>
              <span className="flex items-center gap-2">
                {c.done_by && <span className="text-xs text-slate-400">{c.done_by.full_name}</span>}
                {e.can_manage && <button className="text-xs text-slate-400 hover:text-red-600" aria-label="Delete"
                                         onClick={() => act(`/checklist/${c.id}`, "DELETE").catch(() => undefined)}>✕</button>}
              </span>
            </li>
          ))}
        </ul>
        {e.can_manage && (
          <form className="mt-3 flex gap-2" onSubmit={(ev) => { ev.preventDefault(); act("/checklist", "POST", { label }).then(() => setLabel("")).catch(() => undefined); }}>
            <Input required minLength={2} placeholder="e.g. Book the auditorium" value={label} onChange={(ev) => setLabel(ev.target.value)} />
            <Button type="submit" variant="secondary">Add</Button>
          </form>
        )}
      </Card>
      <Card title="Milestones">
        {!e.milestones.length && <Empty>No milestones yet.</Empty>}
        <ul className="divide-y divide-slate-100">
          {e.milestones.map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={!!m.done_at} disabled={!e.can_manage}
                       onChange={(ev) => act(`/milestones/${m.id}`, "PUT", { title: m.title, due_at: m.due_at, done: ev.target.checked }).catch(() => undefined)} />
                <span className={m.done_at ? "text-slate-400 line-through" : "font-medium"}>{m.title}</span>
              </label>
              <span className="flex items-center gap-2 text-xs text-slate-500">
                {m.due_at ? formatDate(m.due_at, false) : "No date"}
                {e.can_manage && <button className="text-slate-400 hover:text-red-600" aria-label="Delete"
                                         onClick={() => act(`/milestones/${m.id}`, "DELETE").catch(() => undefined)}>✕</button>}
              </span>
            </li>
          ))}
        </ul>
        {e.can_manage && (
          <form className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto_auto]"
                onSubmit={(ev) => { ev.preventDefault(); act("/milestones", "POST", { title, due_at: fromInputDateTime(due) }).then(() => { setTitle(""); setDue(""); }).catch(() => undefined); }}>
            <Input required minLength={2} placeholder="e.g. Posters published" value={title} onChange={(ev) => setTitle(ev.target.value)} />
            <Input type="datetime-local" value={due} onChange={(ev) => setDue(ev.target.value)} />
            <Button type="submit" variant="secondary">Add</Button>
          </form>
        )}
      </Card>
    </div>
  );
}

function HistoryTab({ e }: { e: EventDetail }) {
  return (
    <Card title="Status history">
      <ol className="space-y-3">
        {e.history.map((h, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="mt-1.5 size-2 shrink-0 rounded-full bg-brand-500" />
            <div>
              <p>
                <span className="font-medium">{h.changed_by.full_name}</span>{" "}
                {h.from_status ? <>moved it to <strong>{EVENT_STATUS[h.to_status as EventDetail["status"]]?.[0] ?? h.to_status}</strong></> : "created the draft"}
              </p>
              {h.remarks && <p className="text-slate-600">“{h.remarks}”</p>}
              <p className="text-xs text-slate-400">{formatDate(h.changed_at)}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
