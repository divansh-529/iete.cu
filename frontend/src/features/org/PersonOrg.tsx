import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { Profile, UserOrg } from "../../api/types";
import { Alert, Badge, Button, Card, Empty, Field, formatDate, Input, Modal, Select } from "../../components/ui";
import { REASON_LABELS } from "./PositionDetailPage";

const LIFECYCLE_TONE = { onboarding: "blue", probation: "amber", active: "green", alumni: "slate", removed: "red" } as const;

/** Current and past positions and departments for one person. */
export function OrgHistoryCard({ org }: { org: UserOrg }) {
  const current = org.positions.filter((p) => !p.valid_to);
  const past = org.positions.filter((p) => p.valid_to);
  const departments = org.memberships.filter((m) => !m.valid_to);
  return (
    <Card title="Organisation">
      <div className="space-y-4 text-sm">
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Current positions</h3>
          {current.length ? (
            <ul className="space-y-1">
              {current.map((a) => (
                <li key={a.id}>
                  <Link to={`/app/org/positions/${a.position_id}`} className="font-medium text-brand-700 hover:underline">{a.position_title}</Link>
                  {a.department_name && <span className="text-slate-500"> · {a.department_name}</span>}
                  <span className="text-xs text-slate-500"> since {formatDate(a.valid_from, false)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-slate-500">No current position.</p>}
        </div>
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Departments</h3>
          {departments.length ? (
            <div className="flex flex-wrap gap-1">
              {departments.map((m) => (
                <Link key={m.id} to={`/app/org/departments/${m.department_id}`}><Badge tone="blue">{m.department_name}</Badge></Link>
              ))}
            </div>
          ) : <p className="text-slate-500">Not in any department.</p>}
        </div>
        {past.length > 0 && (
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Designation history</h3>
            <ul className="space-y-1">
              {past.map((a) => (
                <li key={a.id} className="text-slate-600">
                  {a.position_title}{a.department_name && ` · ${a.department_name}`}
                  <span className="text-xs text-slate-500">
                    {" "}({formatDate(a.valid_from, false)} – {formatDate(a.valid_to, false)}, {REASON_LABELS[a.end_reason ?? ""] ?? a.end_reason})
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {!org.positions.length && !org.memberships.length && <Empty>Not yet placed in the organisation.</Empty>}
      </div>
    </Card>
  );
}

export function ProfileCard({ userId, profile, editable, self = false }: {
  userId: number; profile: Profile; editable: boolean; self?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  return (
    <Card title="Member profile" actions={editable && <Button variant="ghost" onClick={() => setEditing(true)}>Edit</Button>}>
      <dl className="space-y-2 text-sm">
        <Row label="Status"><Badge tone={LIFECYCLE_TONE[profile.lifecycle_status]}>{profile.lifecycle_status}</Badge></Row>
        <Row label="University ID">{profile.uid ?? "—"}</Row>
        <Row label="Branch">{profile.branch ?? "—"}</Row>
        <Row label="Year">{profile.year_of_study ?? "—"}</Row>
        <Row label="Phone">{profile.phone ?? "—"}</Row>
        <Row label="Joined">{formatDate(profile.joined_on, false)}</Row>
      </dl>
      {profile.responsibilities && <p className="mt-3 whitespace-pre-line text-sm text-slate-600">{profile.responsibilities}</p>}
      {editing && <ProfileModal userId={userId} profile={profile} self={self} onClose={() => setEditing(false)} />}
    </Card>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

function ProfileModal({ userId, profile, self, onClose }: { userId: number; profile: Profile; self: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    uid: profile.uid ?? "", phone: profile.phone ?? "", branch: profile.branch ?? "",
    year_of_study: profile.year_of_study ? String(profile.year_of_study) : "", joined_on: profile.joined_on ?? "",
    lifecycle_status: profile.lifecycle_status, responsibilities: profile.responsibilities ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });
  const orNull = (v: string) => (v.trim() ? v.trim() : null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const common = { phone: orNull(form.phone), branch: orNull(form.branch),
                     year_of_study: form.year_of_study ? Number(form.year_of_study) : null };
    try {
      if (self) {
        await api("/me/profile", { method: "PUT", body: common });
      } else {
        await api(`/users/${userId}/profile`, {
          method: "PUT",
          body: { ...common, uid: orNull(form.uid), joined_on: form.joined_on || null,
                  lifecycle_status: form.lifecycle_status, responsibilities: orNull(form.responsibilities) },
        });
      }
      qc.invalidateQueries({ queryKey: ["user-org"] });
      qc.invalidateQueries({ queryKey: ["my-org"] });
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal title="Edit profile" open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {!self && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="University ID"><Input value={form.uid} onChange={set("uid")} /></Field>
            <Field label="Status">
              <Select value={form.lifecycle_status} onChange={set("lifecycle_status")}>
                {Object.keys(LIFECYCLE_TONE).map((s) => <option key={s} value={s}>{s}</option>)}
              </Select>
            </Field>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Branch"><Input value={form.branch} onChange={set("branch")} /></Field>
          <Field label="Year of study">
            <Select value={form.year_of_study} onChange={set("year_of_study")}>
              <option value="">—</option>
              {[1, 2, 3, 4, 5, 6].map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Phone"><Input type="tel" value={form.phone} onChange={set("phone")} /></Field>
        {!self && (
          <>
            <Field label="Joined on"><Input type="date" value={form.joined_on} onChange={set("joined_on")} /></Field>
            <Field label="Responsibilities"><Input value={form.responsibilities} onChange={set("responsibilities")} /></Field>
          </>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit">Save</Button>
        </div>
      </form>
    </Modal>
  );
}
