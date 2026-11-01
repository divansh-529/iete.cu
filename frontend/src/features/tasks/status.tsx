import type { TaskPriority, TaskStatus } from "../../api/types";
import { Badge, type BadgeTone } from "../../components/ui";

export const TASK_STATUS: Record<TaskStatus, [string, BadgeTone]> = {
  not_started: ["Not started", "slate"],
  assigned: ["Assigned", "blue"],
  in_progress: ["In progress", "blue"],
  submitted: ["Submitted", "amber"],
  under_review: ["Under review", "amber"],
  completed: ["Completed", "green"],
  rejected: ["Rejected", "red"],
};

const PRIORITY: Record<TaskPriority, [string, BadgeTone]> = {
  low: ["Low", "slate"], medium: ["Medium", "slate"], high: ["High", "amber"], urgent: ["Urgent", "red"],
};

export function TaskStatusBadge({ status, overdue }: { status: TaskStatus; overdue?: boolean }) {
  const [label, tone] = TASK_STATUS[status];
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Badge tone={tone}>{label}</Badge>
      {overdue && <Badge tone="red">Overdue</Badge>}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: TaskPriority }) {
  const [label, tone] = PRIORITY[priority];
  return priority === "medium" || priority === "low" ? <span className="text-xs text-slate-500">{label}</span>
    : <Badge tone={tone}>{label}</Badge>;
}
