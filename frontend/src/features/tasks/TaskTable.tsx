import { Link } from "react-router";
import type { TaskSummary } from "../../api/types";
import { Empty, formatDate, relativeTime } from "../../components/ui";
import { PriorityBadge, TaskStatusBadge } from "./status";

/** A list of tasks: title, where it belongs, who's on it, due date and status. */
export function TaskTable({ tasks, showHome = true, empty = "No tasks." }: {
  tasks: TaskSummary[]; showHome?: boolean; empty?: string;
}) {
  if (!tasks.length) return <Empty>{empty}</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="py-2 pr-4 font-medium">Task</th>
            {showHome && <th className="py-2 pr-4 font-medium">Belongs to</th>}
            <th className="py-2 pr-4 font-medium">Assigned to</th>
            <th className="py-2 pr-4 font-medium">Due</th>
            <th className="py-2 pr-4 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {tasks.map((t) => (
            <tr key={t.id} className="hover:bg-slate-50">
              <td className="py-2.5 pr-4">
                <Link to={`/app/tasks/${t.id}`} className="font-medium text-brand-700 hover:underline">{t.title}</Link>{" "}
                <PriorityBadge priority={t.priority} />
              </td>
              {showHome && (
                <td className="py-2.5 pr-4 text-slate-600">
                  {[t.event?.name, t.department?.name].filter(Boolean).join(" · ")}
                </td>
              )}
              <td className="py-2.5 pr-4 text-slate-600">
                {t.assignees.map((a) => a.full_name).join(", ") || <span className="text-slate-400">Unassigned</span>}
              </td>
              <td className={`py-2.5 pr-4 ${t.overdue ? "font-medium text-red-600" : "text-slate-500"}`}
                  title={t.due_at ? formatDate(t.due_at) : undefined}>
                {t.due_at ? relativeTime(t.due_at) : "—"}
              </td>
              <td className="py-2.5 pr-4"><TaskStatusBadge status={t.status} overdue={t.overdue} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
