import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { PersonScores } from "../../api/types";
import { Alert, Card, Empty, formatDate, PageHeader, Spinner } from "../../components/ui";

const fmt = (n: string | number) => Number(n).toLocaleString("en-IN", { maximumFractionDigits: 1 });

/** One person's published score cards, newest round first. Only the Chairperson opens this; everyone else sees their own under Score cards. */
export function PersonScoresPage() {
  const id = Number(useParams().id);
  const data = useQuery({ queryKey: ["scores", "person", id], queryFn: () => api<PersonScores>(`/scores/people/${id}`) });
  if (data.isLoading) return <Spinner />;
  if (data.error || !data.data) return <Alert>{errorMessage(data.error)}</Alert>;
  const p = data.data;
  return (
    <>
      <Link to="/app/scores" className="text-sm text-brand-600 hover:underline">← Score cards</Link>
      <PageHeader title={p.person.full_name}
                  subtitle={p.cards.length ? `Total ${fmt(p.total)} out of ${fmt(p.max_total)} over ${p.cards.length} round(s)` : undefined} />
      {!p.cards.length ? <Card><Empty>No published score cards yet.</Empty></Card> : <PublishedCards cards={p.cards} />}
    </>
  );
}

export function PublishedCards({ cards }: { cards: PersonScores["cards"] }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {cards.map((c) => (
        <Card key={c.round_id} title={c.round_title}
              actions={<span className="font-display text-lg font-semibold text-slate-900">{fmt(c.total)} <span className="text-sm font-normal text-slate-400">/ 20</span></span>}>
          <p className="mb-3 text-xs text-slate-500">
            Scored as {c.category_label}{c.department && ` · ${c.department.name}`}{c.closed_at && ` · published ${formatDate(c.closed_at, false)}`}
          </p>
          <ul className="space-y-2">
            {c.slots.map((s) => (
              <li key={s.slot} className="text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600">{s.label}{s.scored_by && <span className="text-xs text-slate-400"> · {s.scored_by.full_name}</span>}</span>
                  <span className="font-medium tabular-nums">{s.given ? fmt(s.points ?? 0) : <span className="text-slate-400">not given</span>} <span className="text-slate-400">/ {fmt(s.max_points)}</span></span>
                </div>
                {s.remarks && <p className="text-xs text-slate-500">“{s.remarks}”</p>}
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}
