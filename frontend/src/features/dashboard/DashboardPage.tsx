import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../../api/client";
import type { EventSummary, MemberProposal, TaskSummary, UserPage } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { TriangleMotif } from "../../components/Brand";
import { Card } from "../../components/ui";
import { DashboardCalendar } from "./DashboardCalendar";

export function DashboardPage() {
  const { me, can } = useAuth();
  const counts = useQuery({
    queryKey: ["users", "counts"],
    enabled: !!me?.can_view_accounts,
    queryFn: async () => {
      const statuses = ["active", "invited", "suspended"] as const;
      const pages = await Promise.all(statuses.map((s) => api<UserPage>(`/users?status=${s}&limit=1`)));
      return Object.fromEntries(statuses.map((s, i) => [s, pages[i].total])) as Record<(typeof statuses)[number], number>;
    },
  });

  const myTasks = useQuery({ queryKey: ["tasks", "mine", false], queryFn: () => api<TaskSummary[]>("/tasks?view=mine&status=open") });
  const toReview = useQuery({ queryKey: ["tasks", "review", false], queryFn: () => api<TaskSummary[]>("/tasks?view=review") });
  const eventsToAct = useQuery({ queryKey: ["events", "action", "", ""], queryFn: () => api<EventSummary[]>("/events?view=action") });
  const proposals = useQuery({ queryKey: ["proposals", "pending"], enabled: can("users.approve"),
                               queryFn: () => api<MemberProposal[]>("/member-proposals?status=pending") });
  const overdue = myTasks.data?.filter((t) => t.overdue).length ?? 0;

  const permissionCount = me?.all_permissions ? null : new Set(me?.permissions.map((p) => p.code)).size;

  return (
    <>
      <section className="relative mb-7 overflow-hidden rounded-2xl bg-gradient-to-br from-brand-600 via-brand-700 to-brand-900 px-6 py-7 text-white shadow-lg shadow-brand-900/20 sm:px-8">
        <TriangleMotif className="pointer-events-none absolute -top-6 right-4 w-48 text-white/10 sm:w-60" />
        <div className="relative">
          <p className="text-sm font-medium text-brand-100/80">
            {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
          <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">Welcome, {me?.user.full_name.split(" ")[0]}</h1>
          <p className="mt-2 max-w-xl text-sm text-brand-100/90">
            {me?.all_permissions ? "You are signed in as the Chairperson." : "IETE Student Forum · Chandigarh University"}
          </p>
        </div>
      </section>
      <div className={`mb-7 grid gap-4 sm:grid-cols-3 ${can("users.approve") ? "xl:grid-cols-4" : ""}`}>
        <WorkTile to="/app/tasks?tab=mine" label="My open tasks" value={myTasks.data?.length}
                  note={overdue ? `${overdue} overdue` : undefined} />
        <WorkTile to="/app/tasks?tab=review" label="Waiting for my review" value={toReview.data?.length} />
        <WorkTile to="/app/events?tab=action" label="Events needing my action" value={eventsToAct.data?.length} />
        {can("users.approve") && (
          <WorkTile to="/app/recruitment" label="New members to approve" value={proposals.data?.filter((p) => p.can_decide).length} />
        )}
      </div>
      {counts.data && (
        <div className="mb-7 grid gap-4 sm:grid-cols-3">
          <Stat label="Active accounts" value={counts.data.active} accent="bg-emerald-500" />
          <Stat label="Awaiting first sign-in" value={counts.data.invited} accent="bg-brand-500" />
          <Stat label="Suspended" value={counts.data.suspended} accent="bg-amber-500" />
        </div>
      )}
      <div className="mb-7"><DashboardCalendar /></div>
      <Card title="Your access">
        {me?.all_permissions ? (
          <p className="text-sm text-slate-600">You have every permission. Use <Link to="/app/users" className="text-brand-600 hover:underline">Team accounts</Link> to create accounts and grant access.</p>
        ) : permissionCount ? (
          <p className="text-sm text-slate-600">You have {permissionCount} permission(s). Menu items appear for the areas you can use.</p>
        ) : (
          <p className="text-sm text-slate-600">You do not have any access yet. An administrator will grant you the access you need.</p>
        )}
      </Card>
    </>
  );
}

function WorkTile({ to, label, value, note }: { to: string; label: string; value?: number; note?: string }) {
  return (
    <Link to={to} className="group rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm shadow-slate-900/[0.03] transition hover:border-brand-400 hover:shadow-md">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-display text-3xl font-semibold text-slate-900 tabular-nums">{value ?? "–"}</span>
        {note && <span className="text-sm font-medium text-red-600">{note}</span>}
      </div>
      <div className="mt-1 text-xs font-medium text-brand-600 group-hover:underline">Open →</div>
    </Link>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm shadow-slate-900/[0.03]">
      <span className={`absolute inset-y-0 left-0 w-1 ${accent}`} />
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-2 font-display text-3xl font-semibold text-slate-900 tabular-nums">{value}</div>
    </div>
  );
}
