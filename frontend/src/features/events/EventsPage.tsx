import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { EventSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Button, Card, Empty, formatDate, Input, PageHeader, Select, Spinner, Tabs } from "../../components/ui";
import { EventFormModal } from "./EventFormModal";
import { EVENT_STATUS, EventStatusBadge } from "./status";

const TABS = [["visible", "All events"], ["mine", "My events"], ["action", "Needs my action"]] as const;
type View = (typeof TABS)[number][0];

export function EventsPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const view = (params.get("tab") as View) ?? "visible";
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);

  const query = new URLSearchParams({ view });
  if (status && view !== "action") query.set("status", status);
  if (q) query.set("q", q);
  const events = useQuery({ queryKey: ["events", view, status, q], queryFn: () => api<EventSummary[]>(`/events?${query}`) });

  return (
    <>
      <PageHeader title="Events" subtitle="Propose events, get them approved, and run them with your team."
                  actions={can("events.create") && <Button onClick={() => setCreating(true)}>+ Propose event</Button>} />
      <Tabs tabs={TABS} value={view} onChange={(tab) => setParams({ tab })} />
      {view !== "action" && (
        <div className="mb-4 flex flex-wrap gap-2">
          <Input placeholder="Search events…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" />
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-48">
            <option value="">Any status (not archived)</option>
            {Object.entries(EVENT_STATUS).map(([key, [label]]) => <option key={key} value={key}>{label}</option>)}
          </Select>
        </div>
      )}
      {view === "action" && (
        <p className="mb-4 text-sm text-slate-500">Proposals waiting for your review or approval.</p>
      )}
      {events.isLoading ? <Spinner /> : events.error ? <Alert>{errorMessage(events.error)}</Alert>
        : !events.data?.length ? (
          <Card><Empty>{view === "action" ? "Nothing is waiting for you. 🎉" : view === "mine"
            ? "You don't own or help run any events yet." : "No events match."}</Empty></Card>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {events.data.map((e) => <EventCard key={e.id} event={e} />)}
          </div>
        )}
      {creating && <EventFormModal onClose={() => setCreating(false)} />}
    </>
  );
}

function EventCard({ event: e }: { event: EventSummary }) {
  const date = e.starts_at ? new Date(e.starts_at) : null;
  return (
    <Link to={`/app/events/${e.id}`}
          className="group flex gap-4 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm shadow-slate-900/[0.03] transition hover:border-brand-400 hover:shadow-md">
      <div className="flex w-14 shrink-0 flex-col items-center justify-center rounded-lg bg-brand-50 py-2 text-brand-700">
        {date ? (
          <>
            <span className="text-[11px] font-semibold uppercase">{date.toLocaleString("en-IN", { month: "short" })}</span>
            <span className="font-display text-xl font-semibold leading-none">{date.getDate()}</span>
          </>
        ) : <span className="text-[11px] font-medium text-brand-600">No date</span>}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <h3 className="truncate font-semibold text-slate-900 group-hover:text-brand-700">{e.name}</h3>
          <EventStatusBadge status={e.status} />
        </div>
        <p className="mt-0.5 truncate text-xs text-slate-500">
          {[e.category, e.venue, e.starts_at && formatDate(e.starts_at)].filter(Boolean).join(" · ") || "Details to be added"}
        </p>
        <p className="mt-2 truncate text-xs text-slate-500">
          {e.departments.map((d) => d.name).join(", ") || "Organisation-wide"} · run by {e.owner.full_name}
        </p>
        <p className="mt-1 text-xs text-slate-500">{e.team_size} on team · {e.open_tasks} open task(s)</p>
      </div>
    </Link>
  );
}
