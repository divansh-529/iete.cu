import type { BadgeTone } from "../../components/ui";

export const TRACKER_STATUS: Record<string, [BadgeTone, string]> = {
  in_progress: ["amber", "In progress"],
  completed: ["green", "All signed"],
  rejected: ["red", "Rejected"],
  cancelled: ["slate", "Cancelled"],
};

// What the person carrying the document can record at the current office.
export const STEP_RECORDS: [string, string][] = [
  ["submitted", "Submitted at the office"],
  ["signed", "Signed"],
  ["returned", "Returned with changes"],
  ["rejected", "Rejected"],
];

export const STEP_STATUS: Record<string, [BadgeTone, string]> = {
  pending: ["slate", "Not yet"],
  submitted: ["blue", "Submitted"],
  returned: ["amber", "Returned"],
  signed: ["green", "Signed"],
  rejected: ["red", "Rejected"],
};
