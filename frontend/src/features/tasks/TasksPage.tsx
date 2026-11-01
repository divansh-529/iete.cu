import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { Department, TaskStatus, TaskSummary, UserOrg } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Button, Card, cx, Input, PageHeader, relativeTime, Select, Spinner, Tabs } from "../../components/ui";
import { PriorityBadge } from "./status";
import { TaskFormModal } from "./TaskFormModal";
import { TaskTable } from "./TaskTable";

const TABS = [["mine", "My tasks"], ["review", "To review"], ["board", "Department board"], ["all", "All tasks"]] as const;
type Tab = (typeof TABS)[number][0];

export function TasksPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "mine";
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader title="Tasks" subtitle="Work assigned to you, work waiting for your review, and each department's board."
                  actions={can("tasks.create") && <Button onClick={() => setCreating(true)}>+ New task</Button>} />
      <Tabs tabs={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />
      {tab === "mine" && <ListTab view="mine" empty="Nothing assigned to you right now." />}
      {tab === "review" && <ListTab view="review" empty="No submissions are waiting for your review." />}
      {tab === "board" && <BoardTab />}
      {tab === "all" && <AllTab />}
      {creating && <TaskFormModal onClose={() => setCreating(false)} />}
    </>
  );
}

function ListTab({ view, empty }: { view: "mine" | "review"; empty: string }) {
  const [showDone, setShowDone] = useState(false);
  const tasks = useQuery({ queryKey: ["tasks", view, showDone],
                           queryFn: () => api<TaskSummary[]>(`/tasks?view=${view}${showDone || view === "review" ? "" : "&status=open"}`) });
  return (
    <Card actions={view === "mine" && (
      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" checked={showDone} onChange={(e) => setShowDone(e.target.checked)} /> Show finished
      </label>
    )} title={view === "mine" ? "Assigned to me" : "Waiting for my review"}>
      {tasks.isLoading ? <Spinner /> : tasks.error ? <Alert>{errorMessage(tasks.error)}</Alert>
        : <TaskTable tasks={tasks.data ?? []} empty={empty} />}
    </Card>
  );
}

const COLUMNS: [string, TaskStatus[]][] = [
  ["To do", ["not_started", "assigned"]], ["In progress", ["in_progress"]],
  ["Waiting for review", ["submitted", "under_review"]], ["Done", ["completed", "rejected"]],
];

function BoardTab() {
  const depts = useQuery({ queryKey: ["departments", false], queryFn: () => api<Department[]>("/departments") });
  const mine = useQuery({ queryKey: ["me-org"], queryFn: () => api<UserOrg>("/me/org") });
  const [picked, setPicked] = useState("");
  const fallback = mine.data?.memberships.find((m) => !m.valid_to)?.department_id ?? depts.data?.[0]?.id;
  const dept = picked || (fallback ? String(fallback) : "");
  const tasks = useQuery({ queryKey: ["tasks", "board", dept], enabled: !!dept,
                           queryFn: () => api<TaskSummary[]>(`/tasks?department_id=${dept}`) });
  return (
    <>
      <div className="mb-4">
        <Select value={dept} onChange={(e) => setPicked(e.target.value)} className="w-64">
          {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </Select>
      </div>
      {tasks.isLoading ? <Spinner /> : tasks.error ? <Alert>{errorMessage(tasks.error)}</Alert> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map(([title, statuses]) => {
            const items = (tasks.data ?? []).filter((t) => statuses.includes(t.status));
            return (
              <section key={title} className="rounded-xl bg-slate-100/70 p-3">
                <h3 className="mb-2 flex items-center justify-between px-1 text-sm font-semibold text-slate-700">
                  {title} <span className="rounded-full bg-white px-2 text-xs font-medium text-slate-500">{items.length}</span>
                </h3>
                <div className="space-y-2">
                  {items.map((t) => (
                    <Link key={t.id} to={`/app/tasks/${t.id}`}
                          className={cx("block rounded-lg border bg-white p-3 shadow-xs transition hover:border-brand-400",
                            t.overdue ? "border-red-200" : "border-slate-200")}>
                      <p className="text-sm font-medium text-slate-900">{t.title}</p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        <PriorityBadge priority={t.priority} />
                        {t.due_at && <span className={t.overdue ? "font-medium text-red-600" : ""}>{relativeTime(t.due_at)}</span>}
                        {t.status === "rejected" && <span className="text-red-600">Rejected</span>}
                      </div>
                      <p className="mt-1.5 truncate text-xs text-slate-500">{t.assignees.map((a) => a.full_name).join(", ") || "Unassigned"}</p>
                    </Link>
                  ))}
                  {!items.length && <p className="px-1 py-3 text-center text-xs text-slate-400">Empty</p>}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </>
  );
}

function AllTab() {
  const [status, setStatus] = useState("open");
  const [q, setQ] = useState("");
  const query = new URLSearchParams();
  if (status) query.set("status", status);
  if (q) query.set("q", q);
  const tasks = useQuery({ queryKey: ["tasks", "all", status, q], queryFn: () => api<TaskSummary[]>(`/tasks?${query}`) });
  return (
    <Card>
      <div className="mb-4 flex flex-wrap gap-2">
        <Input placeholder="Search tasks…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44">
          <option value="open">Open</option>
          <option value="overdue">Overdue</option>
          <option value="submitted">Submitted</option>
          <option value="completed">Completed</option>
          <option value="rejected">Rejected</option>
          <option value="">Everything</option>
        </Select>
      </div>
      {tasks.isLoading ? <Spinner /> : tasks.error ? <Alert>{errorMessage(tasks.error)}</Alert>
        : <TaskTable tasks={tasks.data ?? []} empty="No tasks match." />}
    </Card>
  );
}
