import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api } from "../../api/client";
import type { EventSummary, TaskSummary } from "../../api/types";
import { Card, cx, Empty } from "../../components/ui";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const NOT_ON_CALENDAR = ["draft", "cancelled"];
const MAX_IN_CELL = 2;

interface Item {
  key: string;
  to: string;
  title: string;
  kind: "event" | "task";
  overdue?: boolean;
}

function dayKey(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function addDays(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

/** Whole weeks, Monday first, that cover the month. */
function monthGrid(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = addDays(first, -((first.getDay() + 6) % 7));
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const days: Date[] = [];
  for (let d = start; d <= last || days.length % 7; d = addDays(d, 1)) days.push(d);
  return days;
}

export function DashboardCalendar() {
  const today = new Date();
  const [month, setMonth] = useState(new Date(today.getFullYear(), today.getMonth(), 1));
  const [selected, setSelected] = useState(today);
  const events = useQuery({ queryKey: ["events", "calendar"], queryFn: () => api<EventSummary[]>("/events") });
  const tasks = useQuery({ queryKey: ["tasks", "mine", false], queryFn: () => api<TaskSummary[]>("/tasks?view=mine&status=open") });
  const days = useMemo(() => monthGrid(month), [month]);

  const byDay = useMemo(() => {
    const map = new Map<string, Item[]>();
    const put = (d: Date, item: Item) => {
      const key = dayKey(d);
      map.set(key, [...(map.get(key) ?? []), item]);
    };
    for (const e of events.data ?? []) {
      if (!e.starts_at || NOT_ON_CALENDAR.includes(e.status)) continue;
      const item: Item = { key: `e${e.id}`, to: `/app/events/${e.id}`, title: e.name, kind: "event" };
      const start = new Date(e.starts_at);
      const end = new Date(e.ends_at ?? e.starts_at);
      for (const d of days) {
        const next = addDays(d, 1);
        if (start < next && end >= d) put(d, item);
      }
    }
    for (const t of tasks.data ?? []) {
      if (t.due_at) put(new Date(t.due_at), { key: `t${t.id}`, to: `/app/tasks/${t.id}`, title: t.title, kind: "task", overdue: t.overdue });
    }
    return map;
  }, [events.data, tasks.data, days]);

  const selectedItems = byDay.get(dayKey(selected)) ?? [];
  const shift = (n: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1));
  const goToday = () => {
    setMonth(new Date(today.getFullYear(), today.getMonth(), 1));
    setSelected(today);
  };

  return (
    <Card title={month.toLocaleDateString("en-IN", { month: "long", year: "numeric" })}
          actions={
            <div className="flex items-center gap-1 text-sm text-slate-600">
              <button onClick={() => shift(-1)} aria-label="Previous month" className="rounded-md px-2 py-1 hover:bg-slate-100">‹</button>
              <button onClick={goToday} className="rounded-md px-2 py-1 font-medium hover:bg-slate-100">Today</button>
              <button onClick={() => shift(1)} aria-label="Next month" className="rounded-md px-2 py-1 hover:bg-slate-100">›</button>
            </div>
          }>
      <div className="grid grid-cols-7 text-center text-xs font-medium text-slate-500">
        {WEEKDAYS.map((d) => <div key={d} className="pb-2">{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200">
        {days.map((d) => {
          const key = dayKey(d);
          const items = byDay.get(key) ?? [];
          const isToday = key === dayKey(today);
          const isSelected = key === dayKey(selected);
          return (
            <button key={key} onClick={() => setSelected(d)} aria-pressed={isSelected}
                    aria-label={`${d.toLocaleDateString("en-IN", { day: "numeric", month: "long" })}, ${items.length} item(s)`}
                    className={cx("flex min-h-14 min-w-0 flex-col items-start justify-start bg-white p-1 text-left hover:bg-slate-50 sm:min-h-20 sm:p-1.5",
                                  d.getMonth() !== month.getMonth() && "bg-slate-50 text-slate-400",
                                  isSelected && "ring-2 ring-inset ring-brand-500")}>
              <span className={cx("inline-flex size-6 items-center justify-center rounded-full text-xs tabular-nums",
                                  isToday && "bg-brand-600 font-semibold text-white")}>{d.getDate()}</span>
              <div className="mt-0.5 hidden w-full space-y-0.5 sm:block">
                {items.slice(0, MAX_IN_CELL).map((i) => (
                  <div key={i.key} className={cx("truncate rounded px-1 text-[11px] leading-4", chip(i))}>{i.title}</div>
                ))}
                {items.length > MAX_IN_CELL && <div className="px-1 text-[11px] text-slate-500">+{items.length - MAX_IN_CELL} more</div>}
              </div>
              {items.length > 0 && (
                <div className="mt-0.5 flex gap-0.5 px-1 sm:hidden">
                  {items.slice(0, 3).map((i) => <span key={i.key} className={cx("size-1.5 rounded-full", dot(i))} />)}
                </div>
              )}
            </button>
          );
        })}
      </div>
      <div className="mt-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-900">
          {selected.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}
        </h3>
        {selectedItems.length ? (
          <ul className="space-y-1.5 text-sm">
            {selectedItems.map((i) => (
              <li key={i.key} className="flex items-center gap-2">
                <span className={cx("size-2 shrink-0 rounded-full", dot(i))} />
                <Link to={i.to} className="min-w-0 truncate font-medium text-brand-700 hover:underline">{i.title}</Link>
                <span className="shrink-0 text-xs text-slate-500">{i.kind === "event" ? "Event" : i.overdue ? "Task overdue" : "Task due"}</span>
              </li>
            ))}
          </ul>
        ) : <Empty>Nothing on this day.</Empty>}
      </div>
    </Card>
  );
}

function chip(i: Item) {
  if (i.kind === "event") return "bg-brand-50 text-brand-700";
  return i.overdue ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-800";
}

function dot(i: Item) {
  if (i.kind === "event") return "bg-brand-500";
  return i.overdue ? "bg-red-500" : "bg-amber-500";
}
