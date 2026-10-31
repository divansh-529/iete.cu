import { useState } from "react";
import { Link } from "react-router";
import type { Holder, Position } from "../../api/types";
import { Badge, Button, Empty, formatDate } from "../../components/ui";
import { AssignModal, EndAssignmentModal, TransferModal } from "./modals";

/** Lead and deputy seats can only be filled or vacated with org.manage (an administrator). */
export const isLeadership = (p: Position) => p.is_lead || p.is_deputy;

/** Positions with their current holders and assign/end/move actions. */
export function PositionList({ positions, canAssign, canManage }:
  { positions: Position[]; canAssign: boolean; canManage: boolean }) {
  const canStaff = (p: Position) => canAssign && (canManage || !isLeadership(p));
  const [assigning, setAssigning] = useState<Position | null>(null);
  const [ending, setEnding] = useState<{ holder: Holder; position: Position } | null>(null);
  const [moving, setMoving] = useState<{ holder: Holder; position: Position } | null>(null);

  if (!positions.length) return <Empty>No positions yet.</Empty>;
  return (
    <>
      <ul className="divide-y divide-slate-100">
        {positions.map((p) => {
          const full = p.holders.length >= p.max_holders;
          return (
            <li key={p.id} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/app/org/positions/${p.id}`} className="font-medium text-brand-700 hover:underline">{p.title}</Link>
                  {p.is_lead && <Badge tone="blue">Lead</Badge>}
                  {p.is_deputy && <Badge>Deputy</Badge>}
                  {p.holders.length === 0 && <Badge tone="amber">Vacant</Badge>}
                  {p.max_holders > 1 && <span className="text-xs text-slate-500">{p.holders.length}/{p.max_holders} filled</span>}
                </div>
                {canStaff(p) && !full && <Button variant="secondary" onClick={() => setAssigning(p)}>Assign</Button>}
              </div>
              {p.holders.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {p.holders.map((h) => (
                    <li key={h.assignment_id} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-1.5 text-sm">
                      <span>
                        <Link to={`/app/users/${h.user.id}`} className="font-medium hover:underline">{h.user.full_name}</Link>
                        <span className="text-xs text-slate-500"> since {formatDate(h.valid_from, false)}</span>
                      </span>
                      {canStaff(p) && (
                        <span className="flex gap-1">
                          <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => setMoving({ holder: h, position: p })}>Move</Button>
                          <Button variant="ghost" className="px-2 py-1 text-xs text-red-600" onClick={() => setEnding({ holder: h, position: p })}>End</Button>
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      {assigning && <AssignModal position={assigning} onClose={() => setAssigning(null)} />}
      {ending && <EndAssignmentModal holder={ending.holder} positionTitle={ending.position.title} onClose={() => setEnding(null)} />}
      {moving && <TransferModal holder={moving.holder} position={moving.position} canManage={canManage}
                                onClose={() => setMoving(null)} />}
    </>
  );
}
