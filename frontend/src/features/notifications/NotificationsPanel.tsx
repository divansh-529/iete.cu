import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useNavigate } from "react-router";
import { api } from "../../api/client";
import type { AppNotification, DocumentStatus, EventStatus, NotificationPage } from "../../api/types";
import { cx, Empty, relativeTime } from "../../components/ui";
import { DOCUMENT_STATUS } from "../documents/DocumentModal";
import { EVENT_STATUS } from "../events/status";

/** Unread count for the sidebar; the portal checks every minute. */
export function useNotifications(enabled = true) {
  return useQuery({ queryKey: ["notifications"], queryFn: () => api<NotificationPage>("/notifications"),
                    refetchInterval: 60_000, refetchIntervalInBackground: false, staleTime: 30_000, enabled });
}

function describe(n: AppNotification): { text: string; to: string } {
  const p = n.payload as Record<string, string>;
  const task = `/app/tasks/${p.task_id}`;
  const event = `/app/events/${p.event_id}`;
  switch (n.kind) {
    case "task.assigned": return { text: `${p.by} assigned you “${p.title}”`, to: task };
    case "task.submitted": return { text: `${p.by} submitted “${p.title}” for your review`, to: task };
    case "task.reviewed": return {
      text: p.outcome === "accepted" ? `${p.by} accepted your work on “${p.title}” ✓`
        : p.outcome === "rejected" ? `${p.by} rejected “${p.title}”` : `${p.by} asked for changes on “${p.title}”`, to: task };
    case "task.reopened": return { text: `${p.by} reopened “${p.title}”`, to: task };
    case "task.comment": return { text: `${p.by} commented on “${p.title}”: ${p.excerpt}`, to: task };
    case "task.due_soon": return { text: `“${p.title}” is due ${relativeTime(p.due_at)}`, to: task };
    case "event.status": return { text: `${p.by} moved “${p.name}” to ${EVENT_STATUS[p.to_status as EventStatus]?.[0] ?? p.to_status}`
                                    + (p.remarks ? `: “${p.remarks}”` : ""), to: event };
    case "event.needs_review": return { text: `${p.by} proposed “${p.name}”. It needs your review.`, to: event };
    case "event.needs_approval": return { text: `“${p.name}” is waiting for your approval`, to: event };
    case "event.team_added": return { text: `${p.by} added you to “${p.name}” as ${p.event_role}`, to: event };
    case "document.submitted": return { text: `${p.by} submitted “${p.title}” for your review`, to: `/app/documents?open=${p.document_id}` };
    case "document.reviewed": return { text: `${p.by} marked “${p.title}” as ${DOCUMENT_STATUS[p.to_status as DocumentStatus]?.[0] ?? p.to_status}`
                                         + (p.remarks ? `: “${p.remarks}”` : ""), to: `/app/documents?open=${p.document_id}` };
    case "expense.submitted": return { text: `${p.by} submitted ${p.code} (₹${p.amount}): ${p.purpose}. Please verify it.`, to: `/app/finance?tab=to_act&open=${p.transaction_id}` };
    case "expense.verified": return { text: `${p.by} verified ${p.code} (₹${p.amount}). It needs your approval.`, to: `/app/finance?tab=to_act&open=${p.transaction_id}` };
    case "expense.approved": return { text: `${p.by} approved your ${p.entry ?? "expense"} ${p.code} (₹${p.amount}) ✓`, to: `/app/finance?tab=mine&open=${p.transaction_id}` };
    case "expense.rejected": return { text: `${p.by} rejected your ${p.entry ?? "expense"} ${p.code}: “${p.reason}”`, to: `/app/finance?tab=mine&open=${p.transaction_id}` };
    case "entry.waiting": return { text: `${p.by} recorded ${p.code} (₹${p.amount}): ${p.purpose}. It needs your approval.`, to: `/app/finance?tab=to_act&open=${p.transaction_id}` };
    case "appeal.submitted": return { text: `${p.by} appealed the rejection of ${p.code} (₹${p.amount})`, to: `/app/finance?tab=appeals&open=${p.transaction_id}` };
    case "appeal.comment": return { text: `${p.by} commented on the appeal for ${p.code}`, to: `/app/finance?tab=appeals&open=${p.transaction_id}` };
    case "appeal.approved": return { text: `${p.by} approved your appeal for ${p.code} (₹${p.amount}) ✓`, to: `/app/finance?tab=appeals&open=${p.transaction_id}` };
    case "appeal.rejected": return { text: `${p.by} rejected your appeal for ${p.code}: “${p.reason}”`, to: `/app/finance?tab=appeals&open=${p.transaction_id}` };
    case "transaction.reversed": return { text: `${p.by} reversed ${p.code}: “${p.reason}”`, to: `/app/finance?tab=mine&open=${p.transaction_id}` };
    case "tracker.assigned": return { text: `${p.by} asked you to carry “${p.title}” for signatures`, to: `/app/tracker/${p.document_id}` };
    case "tracker.updated": return { text: p.done ? `“${p.title}” has every signature ✓` : `“${p.title}”: ${p.step} ${({ submitted: "has it now", signed: "signed ✓", returned: "returned it with changes", rejected: "rejected it" } as Record<string, string>)[p.status as string] ?? p.status} (${p.by})`, to: `/app/tracker/${p.document_id}` };
    case "tracker.handover": return { text: `${p.by} wants to hand you “${p.title}” for the next signatures. Accept it to take over.`, to: `/app/tracker/${p.document_id}` };
    case "tracker.handover_answered": return { text: p.accepted ? `${p.by} accepted “${p.title}” and carries it now` : `${p.by} couldn't take “${p.title}”: “${p.reason}”`, to: `/app/tracker/${p.document_id}` };
    case "tracker.cancelled": return { text: `${p.by} cancelled tracking of “${p.title}”: “${p.reason}”`, to: `/app/tracker/${p.document_id}` };
    case "score.round_opened": return { text: `Scoring is open: “${p.title}”. Please give your scores.`, to: "/app/scores?tab=score" };
    case "score.published": return { text: `“${p.title}” score cards are published. See yours.`, to: "/app/scores?tab=mine" };
    case "account.proposed": return { text: `${p.by} proposed ${p.name} for ${p.department}. Waiting for your approval.`, to: "/app/recruitment" };
    case "account.approved": return { text: `${p.by} approved ${p.name}. Their account is active.`, to: "/app/recruitment?tab=decided" };
    case "account.rejected": return { text: `${p.by} didn't approve ${p.name}: “${p.remarks}”`, to: "/app/recruitment?tab=decided" };
    default: return { text: n.kind, to: "/app" };
  }
}

export function NotificationsPanel({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { data } = useNotifications();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function markRead(ids?: number[]) {
    await api("/notifications/read", { method: "POST", body: { ids: ids ?? null } });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  }

  return (
    <div className="fixed inset-0 z-40" onMouseDown={onClose}>
      <aside role="dialog" aria-label="Notifications" onMouseDown={(e) => e.stopPropagation()}
             className="absolute inset-y-0 right-0 flex w-full max-w-sm flex-col border-l border-slate-200 bg-white shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Notifications</h2>
          <div className="flex items-center gap-2">
            {!!data?.unread && <button className="text-xs font-medium text-brand-600 hover:underline" onClick={() => markRead()}>Mark all read</button>}
            <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100" aria-label="Close">✕</button>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto">
          {!data?.items.length ? <div className="p-5"><Empty>You're all caught up.</Empty></div> : (
            <ul className="divide-y divide-slate-100">
              {data.items.map((n) => {
                const { text, to } = describe(n);
                return (
                  <li key={n.id}>
                    <button className={cx("flex w-full gap-3 px-5 py-3 text-left text-sm hover:bg-slate-50", !n.read_at && "bg-brand-50/50")}
                            onClick={() => { if (!n.read_at) markRead([n.id]); onClose(); navigate(to); }}>
                      <span className={cx("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-brand-600")} />
                      <span>
                        <span className="block text-slate-800">{text}</span>
                        <span className="text-xs text-slate-400">{relativeTime(n.created_at)}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
