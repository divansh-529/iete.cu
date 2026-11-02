import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, apiDownload, errorMessage } from "../../api/client";
import type { RosterGroup, RosterPerson } from "../../api/types";
import { Alert, Badge, Button, Card, Empty, Input, PageHeader, Spinner } from "../../components/ui";

/** Each department's Lead with their team under them, and the list as an Excel file. */
export function TeamListPage() {
  const roster = useQuery({ queryKey: ["roster"], queryFn: () => api<RosterGroup[]>("/org/roster") });
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function download(label: string, query: string, fallback: string) {
    setBusy(label);
    setError(null);
    try {
      await apiDownload(`/org/roster/export${query}`, fallback);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  if (roster.isLoading) return <Spinner />;
  if (roster.error) return <Alert>{errorMessage(roster.error)}</Alert>;
  const needle = q.trim().toLowerCase();
  const matches = (p: RosterPerson) => [p.name, p.email, p.uid, p.mobile, p.block].some((v) => v?.toLowerCase().includes(needle));
  const groups = (roster.data ?? []).map((g) => ({ ...g, shown: needle ? g.people.filter(matches) : g.people }))
    .filter((g) => !needle || g.shown.length);
  const several = (roster.data?.length ?? 0) > 1;

  return (
    <>
      <PageHeader title="Team list" subtitle="Each Lead with their team. These details are private, so please keep downloaded lists safe."
                  actions={several && (
                    <Button disabled={!!busy} onClick={() => download("all", "", "Core Team Members.xlsx")}>
                      {busy === "all" ? "Preparing…" : "Download all"}
                    </Button>
                  )} />
      {error && <div className="mb-4"><Alert>{error}</Alert></div>}
      <div className="mb-4 max-w-md">
        <Input aria-label="Search the team list" placeholder="Search name, email, UID, mobile or block" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!groups.length && <Card><Empty>{needle ? "Nobody matches that search." : "No departments yet."}</Empty></Card>}
      <div className="space-y-5">
        {groups.map((g) => {
          const leads = g.shown.filter((p) => p.is_lead);
          const team = g.shown.filter((p) => !p.is_lead);
          const label = `${g.id ?? "leadership"}`;
          return (
            <Card key={label} title={`${g.name} (${g.people.length})`}
                  actions={g.id !== null && (
                    <Button variant="secondary" disabled={!!busy} onClick={() => download(label, `?department_id=${g.id}`, `${g.name} Members.xlsx`)}>
                      {busy === label ? "Preparing…" : "Download list"}
                    </Button>
                  )}>
              {!g.shown.length ? <Empty>Nobody in this department yet.</Empty> : (
                <>
                  {leads.length ? (
                    <ul className="space-y-2">{leads.map((p) => <PersonRow key={p.user_id} p={p} highlight />)}</ul>
                  ) : g.id !== null && !needle && <p className="mb-2 text-sm font-medium text-amber-700">No Lead assigned</p>}
                  {team.length > 0 && (
                    <ul className="mt-2 ml-2 space-y-2 border-l-2 border-brand-200 pl-3 sm:ml-4 sm:pl-5">
                      {team.map((p) => <PersonRow key={p.user_id} p={p} />)}
                    </ul>
                  )}
                </>
              )}
            </Card>
          );
        })}
      </div>
    </>
  );
}

function PersonRow({ p, highlight }: { p: RosterPerson; highlight?: boolean }) {
  return (
    <li className={`rounded-lg border px-3 py-2 text-sm ${highlight ? "border-brand-200 bg-brand-50" : "border-slate-200 bg-white"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-900">{p.name}</span>
        {p.position && <Badge tone={highlight ? "blue" : "slate"}>{p.position}</Badge>}
      </div>
      <dl className="mt-1 grid gap-x-5 gap-y-0.5 text-xs text-slate-600 sm:grid-cols-2 lg:grid-cols-4">
        <div className="min-w-0 truncate"><dt className="inline text-slate-400">Email </dt><dd className="inline">{p.email}</dd></div>
        <div><dt className="inline text-slate-400">UID </dt><dd className="inline">{p.uid ?? "—"}</dd></div>
        <div><dt className="inline text-slate-400">Mobile </dt><dd className="inline">{p.mobile ?? "—"}</dd></div>
        <div><dt className="inline text-slate-400">Block </dt><dd className="inline">{p.block ?? "—"}</dd></div>
      </dl>
    </li>
  );
}
