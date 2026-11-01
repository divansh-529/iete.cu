import type { EventStatus } from "../../api/types";
import { Badge, type BadgeTone } from "../../components/ui";

export const EVENT_STATUS: Record<EventStatus, [string, BadgeTone]> = {
  draft: ["Draft", "slate"],
  proposed: ["Proposed", "violet"],
  awaiting_approval: ["Awaiting approval", "amber"],
  approved: ["Approved", "green"],
  open_for_registration: ["Registration open", "green"],
  ongoing: ["Ongoing", "blue"],
  completed: ["Completed", "green"],
  cancelled: ["Cancelled", "red"],
  archived: ["Archived", "slate"],
};

export function EventStatusBadge({ status }: { status: string }) {
  const [label, tone] = EVENT_STATUS[status as EventStatus] ?? [status, "slate"];
  return <Badge tone={tone}>{label}</Badge>;
}

/** The approval path, shown as steps on the event page. */
export const APPROVAL_STEPS: [EventStatus, string][] = [
  ["draft", "Draft"], ["proposed", "Leadership review"], ["awaiting_approval", "Chairperson approval"],
  ["approved", "Approved"], ["ongoing", "Ongoing"], ["completed", "Completed"],
];
