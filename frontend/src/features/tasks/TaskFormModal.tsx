import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../../api/client";
import type { Department, EventSummary, PersonRef, TaskDetail, TaskPriority, TaskSummary } from "../../api/types";
import { Field, fromInputDateTime, Input, Select, Textarea, toInputDateTime } from "../../components/ui";
import { FormModal } from "../org/modals";
import { PersonPicker } from "../org/PersonPicker";

/** Create a task (optionally for a fixed event) or edit one. Assignees are set here on create;
 *  afterwards they are managed on the task page. */
export function TaskFormModal({ task, eventId = null, departmentId = null, onClose }: {
  task?: TaskDetail; eventId?: number | null; departmentId?: number | null; onClose: () => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [title, setTitle] = useState(task?.title ?? "");
  const [description, setDescription] = useState(task?.description ?? "");
  const [priority, setPriority] = useState<TaskPriority>(task?.priority ?? "medium");
  const [due, setDue] = useState(toInputDateTime(task?.due_at));
  const [dept, setDept] = useState(String(task?.department?.id ?? departmentId ?? ""));
  const [event, setEvent] = useState(String(task?.event?.id ?? eventId ?? ""));
  const [reviewer, setReviewer] = useState<PersonRef | null>(task?.reviewer ?? null);
  const [assignees, setAssignees] = useState<PersonRef[]>([]);
  const [deps, setDeps] = useState<number[]>(task?.depends_on.map((d) => d.id) ?? []);

  const depts = useQuery({ queryKey: ["departments", false], queryFn: () => api<Department[]>("/departments") });
  const events = useQuery({ queryKey: ["events", "visible", "", ""], queryFn: () => api<EventSummary[]>("/events?view=visible"),
                            enabled: eventId === null });
  const siblings = useQuery({
    queryKey: ["tasks", "siblings", dept, event],
    queryFn: () => api<TaskSummary[]>(`/tasks?${event ? `event_id=${event}` : `department_id=${dept}`}`),
    enabled: !!(dept || event),
  });
  const runnable = events.data?.filter((e) => !["cancelled", "archived"].includes(e.status)) ?? [];
  const candidates = (siblings.data ?? []).filter((t) => t.id !== task?.id);

  return (
    <FormModal title={task ? "Edit task" : "New task"} onClose={onClose} submitLabel={task ? "Save" : "Create task"}
               onSubmit={async () => {
                 const body = {
                   title, description: description || null, priority, due_at: fromInputDateTime(due),
                   department_id: dept ? Number(dept) : null, event_id: event ? Number(event) : null,
                   reviewer_id: reviewer?.id ?? null, depends_on: deps,
                   ...(task ? {} : { assignee_ids: assignees.map((a) => a.id) }),
                 };
                 const saved = await api<TaskDetail>(task ? `/tasks/${task.id}` : "/tasks", { method: task ? "PUT" : "POST", body });
                 qc.setQueryData(["task", saved.id], saved);
                 qc.invalidateQueries({ queryKey: ["tasks"] });
                 qc.invalidateQueries({ queryKey: ["event"] });
                 if (!task && eventId === null) navigate(`/app/tasks/${saved.id}`);
               }}>
      <Field label="What needs doing?"><Input required minLength={3} value={title} onChange={(e) => setTitle(e.target.value)} autoFocus /></Field>
      <Field label="Details (optional)"><Textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Priority">
          <Select value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)}>
            <option value="low">Low</option><option value="medium">Medium</option>
            <option value="high">High</option><option value="urgent">Urgent</option>
          </Select>
        </Field>
        <Field label="Due"><Input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
        <Field label="Department" hint={eventId === null ? "A task belongs to a department, an event, or both." : undefined}>
          <Select value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">— None —</option>
            {depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </Field>
        {eventId === null && (
          <Field label="Event">
            <Select value={event} onChange={(e) => setEvent(e.target.value)}>
              <option value="">— None —</option>
              {runnable.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </Select>
          </Field>
        )}
      </div>
      <Field group label="Reviewer" hint="Checks the submitted work. Leave empty to review it yourself.">
        <PersonPicker value={reviewer} onChange={setReviewer} autoFocus={false} />
      </Field>
      {!task && (
        <Field group label="Assign to (optional)">
          <div className="space-y-2">
            {assignees.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {assignees.map((a) => (
                  <span key={a.id} className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-xs text-brand-700">
                    {a.full_name}
                    <button type="button" aria-label={`Remove ${a.full_name}`} onClick={() => setAssignees(assignees.filter((x) => x.id !== a.id))}>✕</button>
                  </span>
                ))}
              </div>
            )}
            <PersonPicker value={null} onChange={(p) => p && setAssignees([...assignees, p])}
                          exclude={assignees.map((a) => a.id)} autoFocus={false} />
          </div>
        </Field>
      )}
      {candidates.length > 0 && (
        <Field group label="Waits for (optional)" hint="This task can't start until these are completed.">
          <div className="max-h-32 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
            {candidates.map((t) => (
              <label key={t.id} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={deps.includes(t.id)}
                       onChange={(e) => setDeps(e.target.checked ? [...deps, t.id] : deps.filter((d) => d !== t.id))} />
                {t.title}
              </label>
            ))}
          </div>
        </Field>
      )}
    </FormModal>
  );
}
