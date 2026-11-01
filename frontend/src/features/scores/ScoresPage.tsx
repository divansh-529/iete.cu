import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { LeaderboardRow, ScoreCard, ScoreRound, ScoreSlot, ToScore } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, cx, Empty, Field, formatDate, Input, Modal, PageHeader, Spinner,
  Tabs } from "../../components/ui";
import { FormModal } from "../org/modals";

const TABS = [["board", "Standings"], ["score", "Score now"], ["rounds", "Rounds"]] as const;
type Tab = (typeof TABS)[number][0];

const fmt = (n: string | number) => Number(n).toLocaleString("en-IN", { maximumFractionDigits: 1 });

export function ScoresPage() {
  const { me } = useAuth();
  const chair = !!me?.user.is_super_admin;
  const [params, setParams] = useSearchParams();
  const open = useQuery({ queryKey: ["scores", "to-score"], queryFn: () => api<ToScore | null>("/scores/to-score") });
  const defaultTab: Tab = open.data && (open.data.my_expected > 0 || chair) ? "score" : "board";
  const tab = (params.get("tab") as Tab) ?? defaultTab;
  return (
    <>
      <PageHeader title="Score cards"
                  subtitle="Everyone's scores, published when the Chairperson closes a round. Each round is worth up to 20; totals add up across rounds." />
      {open.data && (
        <div className="mb-4"><Alert tone="amber">
          <strong>{open.data.round.title}</strong> scoring is open.{" "}
          {open.data.my_expected > 0 ? `You've given ${open.data.my_given} of your ${open.data.my_expected} scores.`
            : chair ? "" : "Results are published when the Chairperson closes the round."}
        </Alert></div>
      )}
      <Tabs tabs={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />
      {tab === "board" && <Standings chair={chair} />}
      {tab === "score" && <ScoreNow data={open.data ?? null} loading={open.isLoading} chair={chair} />}
      {tab === "rounds" && <Rounds chair={chair} />}
    </>
  );
}

/** Chairperson only. Asks for a reason and a typed word, because this changes everyone's totals. */
function DeleteScoresModal({ title, word, warning, submitLabel, path, onClose }: {
  title: string; word: string; warning: string; submitLabel: string; path: string; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  return (
    <FormModal title={title} submitLabel={submitLabel} danger onClose={onClose}
               onSubmit={async () => {
                 await api(path, { method: "POST", body: { reason, confirm } });
                 qc.invalidateQueries({ queryKey: ["scores"] });
               }}>
      <Alert tone="amber">{warning}</Alert>
      <Field label="Reason (recorded in the audit log)">
        <Input required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
      </Field>
      <Field label={`Type “${word}” to confirm`}>
        <Input required value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
      </Field>
    </FormModal>
  );
}

function Standings({ chair }: { chair: boolean }) {
  const [resetting, setResetting] = useState(false);
  const board = useQuery({ queryKey: ["scores", "board"], queryFn: () => api<LeaderboardRow[]>("/scores/leaderboard") });
  if (board.isLoading) return <Spinner />;
  if (board.error) return <Alert>{errorMessage(board.error)}</Alert>;
  if (!board.data?.length) return <Card><Empty>No results yet. They appear here when the Chairperson closes a scoring round.</Empty></Card>;
  return (
    <Card title="Standings" actions={chair && <Button variant="danger" onClick={() => setResetting(true)}>Reset all scores</Button>}>
      {resetting && (
        <DeleteScoresModal title="Reset all scores" word="RESET" submitLabel="Reset all scores" path="/scores/reset"
                           warning="Every scoring round is deleted, including one still open. Everyone's total goes back to 0 and the screens won't show the old scores again."
                           onClose={() => setResetting(false)} />
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
            <tr><th className="py-2 pr-3 font-medium">#</th><th className="py-2 pr-4 font-medium">Name</th>
              <th className="py-2 pr-4 font-medium">Role</th><th className="py-2 pr-4 font-medium">Rounds</th>
              <th className="py-2 pr-4 font-medium">Latest round</th><th className="py-2 pr-4 font-medium">Total</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {board.data.map((b, i) => {
              const pct = Number(b.max_total) ? (Number(b.total) / Number(b.max_total)) * 100 : 0;
              return (
                <tr key={b.person.id} className="hover:bg-slate-50">
                  <td className="py-2.5 pr-3 font-display font-semibold text-slate-400">{i + 1}</td>
                  <td className="py-2.5 pr-4"><Link to={`/app/scores/people/${b.person.id}`} className="font-medium text-brand-700 hover:underline">{b.person.full_name}</Link></td>
                  <td className="py-2.5 pr-4 text-slate-600">{b.category_label}{b.department && ` · ${b.department}`}</td>
                  <td className="py-2.5 pr-4 text-slate-500">{b.rounds}</td>
                  <td className="py-2.5 pr-4 text-slate-600">{fmt(b.latest)} / 20</td>
                  <td className="py-2.5 pr-4">
                    <div className="flex items-center gap-3">
                      <span className="w-20 font-semibold text-slate-900 tabular-nums">{fmt(b.total)} / {fmt(b.max_total)}</span>
                      <span className="hidden h-2 w-28 overflow-hidden rounded-full bg-slate-100 sm:block">
                        <span className="block h-full rounded-full bg-brand-500" style={{ width: `${pct}%` }} />
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ScoreNow({ data, loading, chair }: { data: ToScore | null; loading: boolean; chair: boolean }) {
  // "Everyone" first: a card that just got scored stays in view (and shows "Saved ✓").
  const [filter, setFilter] = useState<"todo" | "all">("all");
  if (loading) return <Spinner />;
  if (!data) return <Card><Empty>No scoring round is open right now.{chair && " Open one on the Rounds tab."}</Empty></Card>;
  if (!data.cards.length) return <Card><Empty>You don't give scores in this round. Results appear under Standings once it closes.</Empty></Card>;
  const cards = filter === "all" ? data.cards : data.cards.filter((c) => c.slots.some((s) => s.editable && !s.given));
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm">
          {(["all", "todo"] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)}
                    className={cx("rounded-md px-3 py-1 font-medium", filter === f ? "bg-white shadow-xs text-slate-900" : "text-slate-500")}>
              {f === "todo" ? "Still to score" : "Everyone"}
            </button>
          ))}
        </div>
        {chair && <CloseRound round={data.round} />}
      </div>
      {!cards.length ? <Card><Empty>You've scored everyone. 🎉 You can still change scores until the round closes.</Empty></Card> : (
        <div className="grid gap-4 lg:grid-cols-2">
          {cards.map((c) => <ScoreCardForm key={c.card_id} card={c} chair={chair} />)}
        </div>
      )}
    </>
  );
}

function ScoreCardForm({ card, chair }: { card: ScoreCard; chair: boolean }) {
  return (
    <Card title={card.person.full_name}
          actions={<span className="text-xs text-slate-500">{card.category_label}{card.department && ` · ${card.department.name}`}</span>}>
      <div className="space-y-3">
        {card.slots.map((s) => s.editable ? <SlotInput key={s.slot} cardId={card.card_id} slot={s} />
          : (chair || s.points !== null) && (
            <div key={s.slot} className="flex items-center justify-between text-sm text-slate-500">
              <span>{s.label}</span>
              <span>{s.points !== null ? `${fmt(s.points)} / ${fmt(s.max_points)}` : s.given ? "given" : "not yet"}</span>
            </div>
          ))}
        {chair && <p className="border-t border-slate-100 pt-2 text-right text-sm font-semibold">So far: {fmt(card.total)} / 20</p>}
      </div>
    </Card>
  );
}

function SlotInput({ cardId, slot }: { cardId: number; slot: ScoreSlot }) {
  const qc = useQueryClient();
  const [points, setPoints] = useState(slot.points ?? "");
  const [remarks, setRemarks] = useState(slot.remarks ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved">(slot.given ? "saved" : "idle");
  const [error, setError] = useState<string | null>(null);
  async function save() {
    setState("saving");
    setError(null);
    try {
      await api(`/scores/cards/${cardId}/${slot.slot}`, { method: "PUT", body: { points: Number(points), remarks: remarks || null } });
      setState("saved");
      qc.invalidateQueries({ queryKey: ["scores"] });
    } catch (err) {
      setError(errorMessage(err));
      setState("idle");
    }
  }
  // Compare as numbers: the server sends "4.0" for a 4 typed here.
  const asNumber = (v: string | null) => (v === null || v === "" ? null : Number(v));
  const changed = asNumber(String(points)) !== asNumber(slot.points) || remarks !== (slot.remarks ?? "");
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex flex-wrap items-end gap-2">
        <Field label={`Your score as ${slot.label} (out of ${fmt(slot.max_points)})`}>
          <Input type="number" min={0} max={Number(slot.max_points)} step={0.5} required value={points} className="w-28"
                 onChange={(e) => { setPoints(e.target.value); setState("idle"); }} />
        </Field>
        <div className="min-w-40 flex-1">
          <Field label="Remark (optional, everyone sees it after publishing)">
            <Input value={remarks} onChange={(e) => { setRemarks(e.target.value); setState("idle"); }} maxLength={500} />
          </Field>
        </div>
        <Button variant={state === "saved" && !changed ? "secondary" : "primary"} disabled={points === "" || state === "saving"} onClick={save}>
          {state === "saving" ? "Saving…" : state === "saved" && !changed ? "Saved ✓" : "Save"}
        </Button>
      </div>
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}
    </div>
  );
}

function CloseRound({ round }: { round: ScoreRound }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missing = round.entries_expected - round.entries_given;
  return (
    <>
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-500">{round.entries_given} of {round.entries_expected} scores given</span>
        <Button onClick={() => setConfirm(true)}>Close &amp; publish</Button>
      </div>
      {confirm && (
        <Modal title={`Close ${round.title}?`} open onClose={() => setConfirm(false)}>
          <div className="space-y-4">
            {error && <Alert>{error}</Alert>}
            {missing > 0 && <Alert tone="amber">{missing} score(s) haven't been given yet. Missing parts count as 0.</Alert>}
            <p className="text-sm text-slate-600">Everyone will be able to see every score card from this round, and scores can't be changed afterwards.</p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setConfirm(false)}>Cancel</Button>
              <Button onClick={async () => {
                try {
                  await api(`/scores/rounds/${round.id}/close`, { method: "POST" });
                  qc.invalidateQueries({ queryKey: ["scores"] });
                  setConfirm(false);
                } catch (err) { setError(errorMessage(err)); }
              }}>Close &amp; publish</Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

function Rounds({ chair }: { chair: boolean }) {
  const qc = useQueryClient();
  const rounds = useQuery({ queryKey: ["scores", "rounds"], queryFn: () => api<ScoreRound[]>("/scores/rounds") });
  const [title, setTitle] = useState(new Date().toLocaleString("en-IN", { month: "long", year: "numeric" }));
  const [deleting, setDeleting] = useState<ScoreRound | null>(null);
  const [error, setError] = useState<string | null>(null);
  const anyOpen = rounds.data?.some((r) => r.status === "open");
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="Scoring rounds" className="lg:col-span-2">
        {rounds.isLoading ? <Spinner /> : !rounds.data?.length ? <Empty>No rounds yet.</Empty> : (
          <ul className="divide-y divide-slate-100">
            {rounds.data.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                <span><span className="font-medium">{r.title}</span> <span className="text-xs text-slate-500">opened {formatDate(r.opened_at, false)}{r.closed_at && ` · published ${formatDate(r.closed_at, false)}`}</span></span>
                <span className="flex items-center gap-2 text-xs text-slate-500">
                  {r.entries_given}/{r.entries_expected} scores · {r.cards} people
                  <Badge tone={r.status === "open" ? "amber" : "green"}>{r.status === "open" ? "Open" : "Published"}</Badge>
                  {chair && <button onClick={() => setDeleting(r)} aria-label={`Delete ${r.title}`}
                                    className="rounded-md px-2 py-1 font-medium text-red-700 hover:bg-red-50">Delete</button>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      {deleting && (
        <DeleteScoresModal title={`Delete ${deleting.title}`} word={deleting.title} submitLabel="Delete round"
                           path={`/scores/rounds/${deleting.id}/delete`}
                           warning="This round's scores are removed from everyone's totals and the screens won't show them again."
                           onClose={() => setDeleting(null)} />
      )}
      {chair && (
        <Card title="Open a new round">
          {anyOpen ? <p className="text-sm text-slate-500">Close the open round first (Score now tab).</p> : (
            <form className="space-y-3" onSubmit={async (e) => {
              e.preventDefault();
              setError(null);
              try {
                await api("/scores/rounds", { method: "POST", body: { title } });
                qc.invalidateQueries({ queryKey: ["scores"] });
              } catch (err) { setError(errorMessage(err)); }
            }}>
              {error && <Alert>{error}</Alert>}
              <Field label="Name of the round"><Input required minLength={3} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
              <p className="text-xs text-slate-500">Everyone except you gets a score card based on their current role. Scorers are notified.</p>
              <Button type="submit" className="w-full">Open scoring</Button>
            </form>
          )}
        </Card>
      )}
    </div>
  );
}
