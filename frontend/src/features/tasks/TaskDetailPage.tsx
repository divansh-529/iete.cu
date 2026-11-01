import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { TaskDetail } from "../../api/types";
import { Alert, Badge, Button, Card, Empty, Field, formatDate, Input, PageHeader, relativeTime, Spinner,
  Textarea } from "../../components/ui";
import { ReasonModal } from "../org/modals";
import { PersonPicker } from "../org/PersonPicker";
import { PriorityBadge, TASK_STATUS, TaskStatusBadge } from "./status";
import { TaskFormModal } from "./TaskFormModal";

const OUTCOME_LABEL = { accepted: ["Accepted", "green"], changes_requested: ["Changes requested", "amber"],
                        rejected: ["Rejected", "red"] } as const;

export function TaskDetailPage() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const task = useQuery({ queryKey: ["task", id], queryFn: () => api<TaskDetail>(`/tasks/${id}`) });
  const [editing, setEditing] = useState(false);
  const [reopening, setReopening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (task.isLoading) return <Spinner />;
  if (task.error || !task.data) return <Alert>{errorMessage(task.error)}</Alert>;
  const t = task.data;
  const can = (a: TaskDetail["actions"][number]) => t.actions.includes(a);

  async function act(path: string, method: string, body?: unknown) {
    setError(null);
    try {
      qc.setQueryData(["task", id], await api<TaskDetail>(`/tasks/${id}${path}`, { method, body }));
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["event"] });
    } catch (err) {
      setError(errorMessage(err));
      throw err;
    }
  }

  return (
    <>
      <Link to="/app/tasks" className="text-sm text-brand-600 hover:underline">← Tasks</Link>
      <PageHeader title={t.title}
                  subtitle={[t.event?.name, t.department?.name].filter(Boolean).join(" · ")}
                  actions={
                    <div className="flex flex-wrap items-center gap-2">
                      <TaskStatusBadge status={t.status} overdue={t.overdue} /> <PriorityBadge priority={t.priority} />
                      {can("edit") && <Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button>}
                      {can("start") && <Button onClick={() => act("/start", "POST").catch(() => undefined)}>Start working</Button>}
                      {can("reopen") && <Button variant="secondary" onClick={() => setReopening(true)}>Reopen</Button>}
                    </div>
                  } />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      {t.blocked && t.status !== "completed" && (
        <div className="mb-4"><Alert tone="amber">Waiting on {t.depends_on.filter((d) => d.status !== "completed").map((d) => d.title).join(", ")}. It can be started once that's completed.</Alert></div>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Details">
            {t.description ? <p className="whitespace-pre-line text-sm text-slate-700">{t.description}</p> : <Empty>No details given.</Empty>}
          </Card>
          {can("submit") && <SubmitCard act={act} resubmit={t.submissions.some((s) => s.review_outcome === "changes_requested")} />}
          {can("review") && <ReviewCard t={t} act={act} />}
          <Card title={`Submitted work (${t.submissions.length})`}>
            {!t.submissions.length ? <Empty>Nothing submitted yet.</Empty> : (
              <ul className="space-y-3">
                {t.submissions.map((s) => (
                  <li key={s.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span><span className="font-medium">{s.submitted_by.full_name}</span> <span className="text-xs text-slate-500">{formatDate(s.submitted_at)}</span></span>
                      {s.review_outcome ? <Badge tone={OUTCOME_LABEL[s.review_outcome][1]}>{OUTCOME_LABEL[s.review_outcome][0]}</Badge>
                        : <Badge tone="amber">Waiting for review</Badge>}
                    </div>
                    {s.note && <p className="mt-2 whitespace-pre-line text-slate-700">{s.note}</p>}
                    {s.link_url && <a href={s.link_url} target="_blank" rel="noopener noreferrer" className="mt-1 block break-all text-brand-600 hover:underline">{s.link_url}</a>}
                    {s.reviewed_by && (
                      <p className="mt-2 rounded-md bg-slate-50 px-2 py-1.5 text-xs text-slate-600">
                        {s.reviewed_by.full_name}{s.review_remarks ? `: “${s.review_remarks}”` : " accepted it."}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <CommentsCard t={t} act={act} />
        </div>
        <div className="space-y-6">
          <Card title="About this task">
            <dl className="space-y-2 text-sm">
              <Row k="Due">{t.due_at ? <span className={t.overdue ? "font-medium text-red-600" : ""} title={formatDate(t.due_at)}>{relativeTime(t.due_at)}</span> : "—"}</Row>
              {t.event && <Row k="Event"><Link to={`/app/events/${t.event.id}`} className="text-brand-600 hover:underline">{t.event.name}</Link></Row>}
              {t.department && <Row k="Department">{t.department.name}</Row>}
              <Row k="Reviewer">{t.reviewer?.full_name ?? "—"}</Row>
              <Row k="Created by">{t.created_by.full_name}</Row>
            </dl>
          </Card>
          <AssigneesCard t={t} act={act} />
          {t.depends_on.length > 0 && (
            <Card title="Waits for">
              <ul className="space-y-1.5 text-sm">
                {t.depends_on.map((d) => (
                  <li key={d.id} className="flex items-center justify-between gap-2">
                    <Link to={`/app/tasks/${d.id}`} className="text-brand-600 hover:underline">{d.title}</Link>
                    <TaskStatusBadge status={d.status} />
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <Card title="History">
            <ol className="space-y-2">
              {t.history.map((h, i) => (
                <li key={i} className="text-xs text-slate-600">
                  <span className="font-medium text-slate-800">{TASK_STATUS[h.to_status as TaskDetail["status"]]?.[0] ?? h.to_status}</span>{" "}
                  · {h.changed_by.full_name} · {formatDate(h.changed_at)}
                  {h.remarks && <span className="block text-slate-500">“{h.remarks}”</span>}
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
      {editing && <TaskFormModal task={t} onClose={() => setEditing(false)} />}
      {reopening && <ReasonModal title="Reopen task" label="Why is it being reopened?" submitLabel="Reopen"
                                 onClose={() => setReopening(false)} onSubmit={(remarks) => act("/reopen", "POST", { remarks })} />}
    </>
  );
}

type Act = (path: string, method: string, body?: unknown) => Promise<void>;

function Row({ k, children }: { k: string; children: ReactNode }) {
  return <div className="flex justify-between gap-3"><dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-800">{children}</dd></div>;
}

function SubmitCard({ act, resubmit }: { act: Act; resubmit: boolean }) {
  const [note, setNote] = useState("");
  const [link, setLink] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    await act("/submissions", "POST", { note: note || null, link_url: link || null }).then(() => { setNote(""); setLink(""); }).catch(() => undefined);
  }
  return (
    <Card title={resubmit ? "Submit the updated work" : "Submit your work"}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Link (optional)" hint="Google Drive, Canva, GitHub… make sure the reviewer can open it.">
          <Input type="url" placeholder="https://" value={link} onChange={(e) => setLink(e.target.value)} />
        </Field>
        <Field label="Note (optional)"><Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What did you do? Anything the reviewer should know?" /></Field>
        <div className="flex justify-end"><Button type="submit" disabled={!note && !link}>Submit for review</Button></div>
      </form>
    </Card>
  );
}

function ReviewCard({ t, act }: { t: TaskDetail; act: Act }) {
  const [remarks, setRemarks] = useState("");
  const pending = t.submissions.find((s) => !s.review_outcome);
  const decide = (outcome: "accepted" | "changes_requested" | "rejected") =>
    act("/review", "POST", { outcome, remarks: remarks || null }).then(() => setRemarks("")).catch(() => undefined);
  return (
    <Card title="Review this submission" className="border-amber-200">
      {pending && <p className="mb-3 text-sm text-slate-600">Submitted by <strong>{pending.submitted_by.full_name}</strong> {relativeTime(pending.submitted_at)}. See it under “Submitted work”.</p>}
      <Field label="Feedback" hint="Required when asking for changes or rejecting.">
        <Textarea value={remarks} onChange={(e) => setRemarks(e.target.value)} />
      </Field>
      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <Button variant="danger" onClick={() => decide("rejected")}>Reject</Button>
        <Button variant="secondary" onClick={() => decide("changes_requested")}>Ask for changes</Button>
        <Button onClick={() => decide("accepted")}>Accept &amp; complete</Button>
      </div>
    </Card>
  );
}

function AssigneesCard({ t, act }: { t: TaskDetail; act: Act }) {
  const manage = t.actions.includes("assign");
  const ids = t.assignees.map((a) => a.id);
  const [adding, setAdding] = useState(false);
  return (
    <Card title="Assigned to">
      {!t.assignees.length && <p className="mb-2 text-sm text-slate-500">Nobody yet.</p>}
      <ul className="space-y-1.5">
        {t.assignees.map((a) => (
          <li key={a.id} className="flex items-center justify-between text-sm">
            <span className="font-medium">{a.full_name}</span>
            {manage && <button className="text-xs text-slate-400 hover:text-red-600"
                               onClick={() => act("/assignees", "PUT", { user_ids: ids.filter((i) => i !== a.id) }).catch(() => undefined)}>Remove</button>}
          </li>
        ))}
      </ul>
      {manage && !adding && (
        <Button variant="secondary" className="mt-3 w-full" onClick={() => setAdding(true)}>+ Add person</Button>
      )}
      {manage && adding && (
        <div className="mt-3 space-y-2">
          <PersonPicker value={null} exclude={ids}
                        onChange={(p) => p && act("/assignees", "PUT", { user_ids: [...ids, p.id] }).then(() => setAdding(false)).catch(() => undefined)} />
          <Button variant="ghost" className="w-full text-xs" onClick={() => setAdding(false)}>Cancel</Button>
        </div>
      )}
    </Card>
  );
}

function CommentsCard({ t, act }: { t: TaskDetail; act: Act }) {
  const [body, setBody] = useState("");
  return (
    <Card title={`Discussion (${t.comments.length})`}>
      <ul className="space-y-3">
        {t.comments.map((c) => (
          <li key={c.id} className="text-sm">
            <p><span className="font-medium">{c.author.full_name}</span> <span className="text-xs text-slate-400">{relativeTime(c.created_at)}</span></p>
            <p className="whitespace-pre-line text-slate-700">{c.body}</p>
          </li>
        ))}
      </ul>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); act("/comments", "POST", { body }).then(() => setBody("")).catch(() => undefined); }}>
        <Input required placeholder="Ask a question or post an update…" value={body} onChange={(e) => setBody(e.target.value)} />
        <Button type="submit" variant="secondary">Post</Button>
      </form>
    </Card>
  );
}
