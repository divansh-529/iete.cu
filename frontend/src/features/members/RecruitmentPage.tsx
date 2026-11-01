import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { Department, DepartmentDetail, MemberProposal, ProposalDecision } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Badge, Button, Card, Empty, Field, formatDate, Modal, PageHeader, relativeTime, Select, Spinner,
  Tabs } from "../../components/ui";
import { ReasonModal } from "../org/modals";
import { ProposeMemberModal } from "./ProposeMemberModal";
import { SignInDetails } from "./SignInDetails";

const TABS = [["pending", "Waiting for approval"], ["decided", "Decided"]] as const;
type Tab = (typeof TABS)[number][0];

export function RecruitmentPage() {
  const { can } = useAuth();
  const approver = can("users.approve");
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) ?? "pending";
  const [proposing, setProposing] = useState(false);
  const rows = useQuery({ queryKey: ["proposals", tab], queryFn: () => api<MemberProposal[]>(`/member-proposals?status=${tab}`) });

  return (
    <>
      <PageHeader title="Recruitment"
                  subtitle={approver ? "Leads propose new members; you approve or reject them. Approved members are emailed their sign-in details."
                    : "Members you've proposed, and whether they've been approved."}
                  actions={can("org.assign") && <Button onClick={() => setProposing(true)}>+ Propose new member</Button>} />
      <Tabs tabs={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />
      {rows.isLoading ? <Spinner /> : rows.error ? <Alert>{errorMessage(rows.error)}</Alert>
        : !rows.data?.length ? <Card><Empty>{tab === "pending" ? "Nothing is waiting for approval." : "No decisions yet."}</Empty></Card>
        : tab === "pending" ? (
          <div className="space-y-3">{rows.data.map((p) => <PendingRow key={p.id} p={p} />)}</div>
        ) : <DecidedTable rows={rows.data} approver={approver} />}
      {proposing && <PickDepartment onClose={() => setProposing(false)} />}
    </>
  );
}

function PendingRow({ p }: { p: MemberProposal }) {
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [result, setResult] = useState<ProposalDecision | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["proposals"] }); qc.invalidateQueries({ queryKey: ["users"] }); };

  async function approve() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api<ProposalDecision>(`/member-proposals/${p.id}/approve`, { method: "POST", body: {} }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-slate-900">{p.person.full_name}</p>
          <p className="text-sm text-slate-500">{p.person.email}</p>
          <p className="mt-1 text-sm text-slate-700">
            {p.department.name}{p.position && <> · <strong>{p.position.name}</strong></>}
          </p>
          <p className="mt-1 text-xs text-slate-500">Proposed by {p.proposed_by.full_name} {relativeTime(p.created_at)}</p>
          {p.note && <p className="mt-2 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">“{p.note}”</p>}
        </div>
        {p.can_decide ? (
          <div className="flex gap-2">
            <Button variant="danger" onClick={() => setRejecting(true)}>Reject</Button>
            <Button onClick={approve} disabled={busy}>{busy ? "Approving…" : "Approve & activate"}</Button>
          </div>
        ) : <Badge tone="amber">Waiting for approval</Badge>}
      </div>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      {rejecting && (
        <ReasonModal title={`Reject ${p.person.full_name}`} label="Reason (the proposer will see it)" submitLabel="Reject" danger
                     onClose={() => setRejecting(false)}
                     onSubmit={async (remarks) => { await api(`/member-proposals/${p.id}/reject`, { method: "POST", body: { remarks } }); refresh(); }} />
      )}
      {result && (
        <Modal title={`${p.person.full_name} is approved`} open onClose={() => { setResult(null); refresh(); }}>
          <div className="space-y-4">
            <p className="text-sm text-slate-600">The account is active and they've joined {p.department.name}{p.position ? ` as ${p.position.name}` : ""}.</p>
            <SignInDetails email={p.person.email} emailed={!!result.email_sent} password={result.default_password} loginUrl={result.login_url} />
            <div className="flex justify-end"><Button onClick={() => { setResult(null); refresh(); }}>Done</Button></div>
          </div>
        </Modal>
      )}
    </Card>
  );
}

function DecidedTable({ rows, approver }: { rows: MemberProposal[]; approver: boolean }) {
  const [resent, setResent] = useState<{ p: MemberProposal; r: ProposalDecision } | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function resend(p: MemberProposal) {
    setError(null);
    try {
      setResent({ p, r: await api<ProposalDecision>(`/member-proposals/${p.id}/send-email`, { method: "POST" }) });
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <Card>
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
            <tr><th className="py-2 pr-4 font-medium">Person</th><th className="py-2 pr-4 font-medium">Department</th>
              <th className="py-2 pr-4 font-medium">Decision</th><th className="py-2 pr-4 font-medium">By</th><th className="py-2 pr-4 font-medium" /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((p) => (
              <tr key={p.id}>
                <td className="py-2.5 pr-4"><span className="font-medium">{p.person.full_name}</span><br /><span className="text-xs text-slate-500">{p.person.email}</span></td>
                <td className="py-2.5 pr-4 text-slate-600">{p.department.name}{p.position && ` · ${p.position.name}`}</td>
                <td className="py-2.5 pr-4">
                  <Badge tone={p.status === "approved" ? "green" : "red"}>{p.status === "approved" ? "Approved" : "Rejected"}</Badge>
                  {p.decision_remarks && <span className="block text-xs text-slate-500">“{p.decision_remarks}”</span>}
                </td>
                <td className="py-2.5 pr-4 text-slate-600">{p.decided_by?.full_name}<br /><span className="text-xs text-slate-400">{formatDate(p.decided_at)}</span></td>
                <td className="py-2.5 pr-4 text-right">
                  {p.status === "approved" && (p.email_sent_at ? <span className="text-xs text-slate-500">Emailed</span>
                    : approver && p.account_status === "invited"
                      ? <Button variant="secondary" className="px-2 py-1 text-xs" onClick={() => resend(p)}>Email details</Button> : null)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {resent && (
        <Modal title={`Sign-in details for ${resent.p.person.full_name}`} open onClose={() => setResent(null)}>
          <SignInDetails email={resent.p.person.email} emailed={!!resent.r.email_sent} password={resent.r.default_password} loginUrl={resent.r.login_url} />
        </Modal>
      )}
    </Card>
  );
}

/** Choose the department first, then the proposal form (it needs that department's positions). */
function PickDepartment({ onClose }: { onClose: () => void }) {
  const { me } = useAuth();
  const depts = useQuery({ queryKey: ["departments", false], queryFn: () => api<Department[]>("/departments") });
  const [picked, setPicked] = useState("");
  const detail = useQuery({ queryKey: ["department", Number(picked)], enabled: !!picked,
                            queryFn: () => api<DepartmentDetail>(`/departments/${picked}`) });
  // A recruiter can only propose where they hold org.assign; show those departments (all of them for org-wide recruiters).
  const scopes = me?.all_permissions ? null : me?.permissions.filter((p) => p.code === "org.assign") ?? [];
  const global = scopes === null || scopes.some((s) => s.scope_type === "global");
  const allowed = depts.data?.filter((d) => global || scopes!.some((s) => s.scope_id === d.id || s.scope_id === d.parent_id)) ?? [];

  if (detail.data) {
    return <ProposeMemberModal department={detail.data} canManage={!!me?.all_permissions} onClose={onClose} />;
  }
  return (
    <Modal title="Propose a new member" open onClose={onClose}>
      <div className="space-y-4">
        <Field label="Which department are they joining?">
          <Select value={picked} onChange={(e) => setPicked(e.target.value)} autoFocus>
            <option value="">Choose…</option>
            {allowed.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </Field>
        {detail.isLoading && <Spinner />}
        <div className="flex justify-end"><Button variant="secondary" onClick={onClose}>Cancel</Button></div>
      </div>
    </Modal>
  );
}
