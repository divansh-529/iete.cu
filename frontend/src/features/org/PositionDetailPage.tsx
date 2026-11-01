import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { Assignment, Position } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, Empty, formatDate, PageHeader, Spinner } from "../../components/ui";
import { GrantsCard } from "../permissions/GrantsCard";
import { DeletePositionModal, PositionFormModal, ReasonModal, useOrgRefresh } from "./modals";
import { PositionList } from "./PositionList";

export const REASON_LABELS: Record<string, string> = {
  appointed: "Appointed", promoted: "Promoted", transferred: "Transferred", reinstated: "Reinstated",
  resigned: "Resigned", removed: "Removed", term_ended: "Term ended",
};

export function PositionDetailPage() {
  const id = Number(useParams().id);
  const { can, me } = useAuth();
  const refresh = useOrgRefresh();
  const navigate = useNavigate();
  const [modal, setModal] = useState<null | "edit" | "archive" | "restore" | "delete">(null);
  const position = useQuery({ queryKey: ["position", id], queryFn: () => api<Position>(`/positions/${id}`) });
  const history = useQuery({ queryKey: ["position-history", id], queryFn: () => api<Assignment[]>(`/positions/${id}/history`) });

  if (position.isLoading) return <Spinner />;
  if (position.error || !position.data) return <Alert>{errorMessage(position.error)}</Alert>;
  const p = position.data;
  const archived = p.status === "archived";
  const back = p.department_id ? `/app/org/departments/${p.department_id}` : "/app/org?tab=leadership";

  return (
    <>
      <Link to={back} className="text-sm text-brand-600 hover:underline">← {p.department_name ?? "Leadership"}</Link>
      <PageHeader title={p.title} subtitle={p.description ?? (p.department_name ? `${p.department_name} department` : "Leadership position")}
                  actions={
                    <div className="flex flex-wrap gap-2">
                      {archived && <Badge tone="red">Archived</Badge>}
                      {can("org.manage") && !archived && <Button variant="secondary" onClick={() => setModal("edit")}>Edit</Button>}
                      {can("org.manage") && !archived && <Button variant="secondary" onClick={() => setModal("archive")}>Archive</Button>}
                      {can("org.manage") && archived && <Button variant="secondary" onClick={() => setModal("restore")}>Restore</Button>}
                      {me?.user.is_super_admin && <Button variant="danger" onClick={() => setModal("delete")}>Delete</Button>}
                    </div>
                  } />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Current holder(s)">
          <PositionList positions={[p]} canAssign={can("org.assign") && !archived} canManage={can("org.manage")} />
        </Card>
        <Card title="History">
          {history.isLoading ? <Spinner /> : !history.data?.length ? <Empty>Nobody has held this position yet.</Empty> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {history.data.map((a) => (
                <li key={a.id} className="py-2">
                  <Link to={`/app/users/${a.user.id}`} className="font-medium hover:underline">{a.user.full_name}</Link>{" "}
                  {!a.valid_to && <Badge tone="green">Current</Badge>}
                  <div className="text-xs text-slate-500">
                    {formatDate(a.valid_from, false)} – {a.valid_to ? formatDate(a.valid_to, false) : "present"}
                    {" · "}{REASON_LABELS[a.start_reason] ?? a.start_reason}
                    {a.end_reason && <> → {REASON_LABELS[a.end_reason] ?? a.end_reason}</>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {can("permissions.view") && (
          <div className="lg:col-span-2">
            <GrantsCard subjectType="position" subjectId={p.id} subjectName={`the ${p.title} position`}
                        canManage={can("permissions.manage") && !archived} />
          </div>
        )}
      </div>
      {modal === "edit" && <PositionFormModal position={p} onClose={() => setModal(null)} />}
      {modal === "delete" && (
        <DeletePositionModal position={{ id: p.id, title: p.title, holderCount: p.holders.length }} onClose={() => setModal(null)}
                             onDeleted={() => navigate("/app/org", { replace: true })} />
      )}
      {(modal === "archive" || modal === "restore") && (
        <ReasonModal title={`${modal === "archive" ? "Archive" : "Restore"} ${p.title}`}
                     submitLabel={modal === "archive" ? "Archive" : "Restore"} danger={modal === "archive"}
                     warning={modal === "archive" ? "Anyone reporting to this position will report to its manager instead." : undefined}
                     onClose={() => setModal(null)}
                     onSubmit={async (reason) => { await api(`/positions/${p.id}/${modal}`, { method: "POST", body: { reason } }); refresh(); }} />
      )}
    </>
  );
}
