import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, errorMessage } from "../../api/client";
import type { AuditEvent, PermissionAuditRow } from "../../api/types";
import { Alert, Badge, Button, Card, cx, Empty, formatDate, PageHeader, Spinner } from "../../components/ui";

const PAGE = 50;

export function AuditPage() {
  const [tab, setTab] = useState<"events" | "permissions">("events");
  return (
    <>
      <PageHeader title="Audit log"
                  subtitle="An append-only record of important actions. Entries cannot be edited or deleted." />
      <div className="mb-4 flex gap-1 border-b border-slate-200">
        {([["events", "All activity"], ["permissions", "Permission changes"]] as const).map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
                  className={cx("-mb-px border-b-2 px-4 py-2 text-sm font-medium",
                    tab === key ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-700")}>
            {label}
          </button>
        ))}
      </div>
      <Card>{tab === "events" ? <AuditList /> : <PermissionAuditList />}</Card>
    </>
  );
}

function usePaged<T extends { id: number }>(key: unknown[], path: string, filters: Record<string, string>) {
  return useInfiniteQuery({
    queryKey: [...key, filters],
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ ...filters, limit: String(PAGE) });
      if (pageParam) params.set("before_id", String(pageParam));
      return api<T[]>(`${path}?${params}`);
    },
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1].id : null),
  });
}

export function AuditList({ filters = {}, compact = false }: { filters?: Record<string, string>; compact?: boolean }) {
  const q = usePaged<AuditEvent>(["audit"], "/audit", filters);
  if (q.isLoading) return <Spinner />;
  if (q.error) return <Alert>{errorMessage(q.error)}</Alert>;
  const rows = q.data?.pages.flat() ?? [];
  if (!rows.length) return <Empty>No activity recorded.</Empty>;
  return (
    <>
      <ul className="divide-y divide-slate-100 text-sm">
        {rows.map((e) => (
          <li key={e.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2.5">
            <div className="min-w-0">
              <Badge tone={e.action.startsWith("auth.") ? "slate" : "blue"}>{e.action}</Badge>{" "}
              <span className="text-slate-700">{e.actor_name ?? "System"}</span>
              {!compact && e.entity_id != null && (
                <span className="text-slate-500"> → {e.entity_type} #{e.entity_id}</span>
              )}
              {describeChange(e) && <div className="mt-0.5 text-xs text-slate-500">{describeChange(e)}</div>}
            </div>
            <div className="text-xs text-slate-500">
              {formatDate(e.created_at)}{!compact && e.ip ? ` · ${e.ip}` : ""}
            </div>
          </li>
        ))}
      </ul>
      {q.hasNextPage && (
        <div className="mt-3 text-center">
          <Button variant="secondary" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>Load more</Button>
        </div>
      )}
    </>
  );
}

function describeChange(e: AuditEvent): string | null {
  const after = e.after ?? {};
  const before = e.before ?? {};
  if (typeof after.reason === "string") return `Reason: ${after.reason}`;
  const changed = Object.keys(after).filter((k) => k !== "reason" && JSON.stringify(after[k]) !== JSON.stringify(before[k]));
  if (!e.before || !changed.length) return null;
  return changed.map((k) => `${k}: ${String(before[k])} → ${String(after[k])}`).join(", ");
}

function PermissionAuditList() {
  const q = usePaged<PermissionAuditRow>(["permission-audit"], "/permission-audit", {});
  if (q.isLoading) return <Spinner />;
  if (q.error) return <Alert>{errorMessage(q.error)}</Alert>;
  const rows = q.data?.pages.flat() ?? [];
  if (!rows.length) return <Empty>No permission changes yet.</Empty>;
  const tone = (a: string) => (a === "grant" || a === "role_create" ? "green" : a === "revoke" || a === "role_delete" ? "red" : "amber");
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="py-2 pr-4 font-medium">When</th>
              <th className="py-2 pr-4 font-medium">Action</th>
              <th className="py-2 pr-4 font-medium">By</th>
              <th className="py-2 pr-4 font-medium">Whose access</th>
              <th className="py-2 pr-4 font-medium">What</th>
              <th className="py-2 pr-4 font-medium">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r.id} className="align-top">
                <td className="whitespace-nowrap py-2 pr-4 text-xs text-slate-500">{formatDate(r.created_at)}</td>
                <td className="py-2 pr-4"><Badge tone={tone(r.action)}>{r.action}</Badge></td>
                <td className="py-2 pr-4">{r.actor_name ?? "System"}</td>
                <td className="py-2 pr-4">{r.subject_name ?? (r.subject_type ? `${r.subject_type} #${r.subject_id}` : "—")}</td>
                <td className="py-2 pr-4">
                  {r.permission_code ? <code>{r.permission_code}</code>
                    : r.role_id ? `role #${r.role_id}` : "—"}
                  {r.scope_type && r.scope_type !== "global" && <span className="text-slate-500"> @ {r.scope_type} #{r.scope_id}</span>}
                </td>
                <td className="py-2 pr-4 text-slate-600">{r.reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {q.hasNextPage && (
        <div className="mt-3 text-center">
          <Button variant="secondary" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>Load more</Button>
        </div>
      )}
    </>
  );
}
