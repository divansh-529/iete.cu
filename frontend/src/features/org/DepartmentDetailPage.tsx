import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { DepartmentDetail, Membership } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, Empty, formatDate, PageHeader, Spinner } from "../../components/ui";
import { GrantsCard } from "../permissions/GrantsCard";
import { CreateUserModal } from "../users/UsersPage";
import { AddMemberModal, DepartmentFormModal, PositionFormModal, ReasonModal, useOrgRefresh } from "./modals";
import { PositionList } from "./PositionList";

export function DepartmentDetailPage() {
  const id = Number(useParams().id);
  const { can, me } = useAuth();
  const refresh = useOrgRefresh();
  const [modal, setModal] = useState<null | "edit" | "position" | "member" | "new-member" | "archive" | "restore">(null);
  const [removing, setRemoving] = useState<Membership | null>(null);
  const dept = useQuery({ queryKey: ["department", id], queryFn: () => api<DepartmentDetail>(`/departments/${id}`) });

  if (dept.isLoading) return <Spinner />;
  if (dept.error || !dept.data) return <Alert>{errorMessage(dept.error)}</Alert>;
  const d = dept.data;
  const archived = d.status === "archived";
  // UI hint only (the API decides): a grant here, on the parent department, or everywhere.
  const scoped = (perm: string) => !!me && (me.all_permissions || me.permissions.some((p) =>
    p.code === perm && (p.scope_type === "global"
      || (p.scope_type === "department" && (p.scope_id === d.id || p.scope_id === d.parent_id)))));
  const canManage = scoped("org.manage") && !archived;
  const canAssign = scoped("org.assign") && !archived;

  return (
    <>
      <Link to="/app/org?tab=departments" className="text-sm text-brand-600 hover:underline">← Departments</Link>
      <PageHeader title={d.name} subtitle={d.description ?? undefined}
                  actions={
                    <div className="flex flex-wrap gap-2">
                      {archived && <Badge tone="red">Archived</Badge>}
                      {canManage && <Button variant="secondary" onClick={() => setModal("edit")}>Edit</Button>}
                      {canManage && <Button variant="secondary" onClick={() => setModal("archive")}>Archive</Button>}
                      {archived && scoped("org.manage") && <Button variant="secondary" onClick={() => setModal("restore")}>Restore</Button>}
                    </div>
                  } />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={`Positions (${d.positions.length})`}
              actions={canManage && <Button onClick={() => setModal("position")}>+ New position</Button>}>
          <PositionList positions={d.positions} canAssign={canAssign} canManage={scoped("org.manage")} />
        </Card>
        <Card title={`Members (${d.members.length})`}
              actions={canAssign && (
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" onClick={() => setModal("member")}>+ Add existing</Button>
                  <Button onClick={() => setModal("new-member")}>+ New account</Button>
                </div>
              )}>
          {!d.members.length ? <Empty>No members yet.</Empty> : (
            <ul className="divide-y divide-slate-100">
              {d.members.map((m) => (
                <li key={m.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span>
                    <Link to={`/app/users/${m.user.id}`} className="font-medium hover:underline">{m.user.full_name}</Link>
                    <span className="text-xs text-slate-500"> joined {formatDate(m.valid_from, false)}</span>
                  </span>
                  {canAssign && <Button variant="ghost" className="text-xs text-red-600" onClick={() => setRemoving(m)}>Remove</Button>}
                </li>
              ))}
            </ul>
          )}
        </Card>
        {can("permissions.view") && (
          <div className="lg:col-span-2">
            <GrantsCard subjectType="department" subjectId={d.id} subjectName={`the ${d.name} department`}
                        canManage={can("permissions.manage") && !archived} />
          </div>
        )}
      </div>
      {modal === "edit" && <DepartmentFormModal dept={d} onClose={() => setModal(null)} />}
      {modal === "position" && <PositionFormModal departmentId={d.id} onClose={() => setModal(null)} />}
      <CreateUserModal open={modal === "new-member"} department={d} canManage={scoped("org.manage")}
                       onClose={() => setModal(null)} />
      {modal === "member" && <AddMemberModal dept={d} existing={d.members.map((m) => m.user.id)} onClose={() => setModal(null)} />}
      {(modal === "archive" || modal === "restore") && (
        <ReasonModal title={`${modal === "archive" ? "Archive" : "Restore"} ${d.name}`}
                     submitLabel={modal === "archive" ? "Archive" : "Restore"} danger={modal === "archive"}
                     warning={modal === "archive" ? "Archived departments keep their history but cannot have members or positions. Its positions are archived too." : undefined}
                     onClose={() => setModal(null)}
                     onSubmit={async (reason) => { await api(`/departments/${d.id}/${modal}`, { method: "POST", body: { reason } }); refresh(); }} />
      )}
      {removing && (
        <ReasonModal title={`Remove ${removing.user.full_name} from ${d.name}`} submitLabel="Remove" danger
                     warning="Access granted to this department stops for them immediately."
                     onClose={() => setRemoving(null)}
                     onSubmit={async (reason) => { await api(`/department-memberships/${removing.id}/end`, { method: "POST", body: { reason } }); refresh(); }} />
      )}
    </>
  );
}
