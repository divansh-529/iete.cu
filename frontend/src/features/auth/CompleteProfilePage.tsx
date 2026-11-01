import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { UserOrg } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Button, Field, Input, Select, Spinner } from "../../components/ui";
import { AuthLayout } from "../../layouts/AuthLayout";

/** Shown once after the first sign-in (and to anyone whose details are still missing). */
export function CompleteProfilePage() {
  const { me, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const ready = !!me && !me.user.must_change_password && !me.profile_complete;
  const org = useQuery({ queryKey: ["my-org"], enabled: ready, queryFn: () => api<UserOrg>("/me/org") });
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (loading) return <Spinner />;
  if (!me) return <Navigate to="/login" replace />;
  if (me.user.must_change_password) return <Navigate to="/change-password" replace />;
  if (me.profile_complete) return <Navigate to="/app" replace />;
  if (!org.data) return <Spinner />;

  const saved = org.data.profile;
  const form = {
    uid: saved.uid ?? "", iete_membership_id: saved.iete_membership_id ?? "", official_email: saved.official_email ?? "",
    block: saved.block ?? "", branch: saved.branch ?? "",
    year_of_study: saved.year_of_study ? String(saved.year_of_study) : "", phone: saved.phone ?? "", ...edits,
  };
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setEdits({ ...edits, [key]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/me/profile", {
        method: "PUT",
        body: { uid: form.uid, iete_membership_id: form.iete_membership_id || null, official_email: form.official_email,
                block: form.block, branch: form.branch,
                year_of_study: Number(form.year_of_study), phone: form.phone },
      });
      qc.invalidateQueries({ queryKey: ["my-org"] });
      await refresh();
      navigate("/app", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    window.location.replace("/login");
  }

  return (
    <AuthLayout title="Complete your profile" subtitle="The forum needs these details before you can continue.">
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field label="University ID"><Input required autoFocus value={form.uid} onChange={set("uid")} /></Field>
        <Field label="Official email">
          <Input type="email" required value={form.official_email} onChange={set("official_email")} />
        </Field>
        <Field label="Current block" hint="For example: C2">
          <Input required maxLength={20} value={form.block} onChange={set("block")} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Branch"><Input required value={form.branch} onChange={set("branch")} /></Field>
          <Field label="Year of study">
            <Select required value={form.year_of_study} onChange={set("year_of_study")}>
              <option value="">Select</option>
              {[1, 2, 3, 4, 5, 6].map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Phone">
          <Input type="tel" required pattern="[+]?[0-9 ]{10,20}" title="10 to 15 digits" autoComplete="tel"
                 value={form.phone} onChange={set("phone")} />
        </Field>
        <Field label="IETE membership ID" hint="Optional. Only for paid IETE members.">
          <Input value={form.iete_membership_id} onChange={set("iete_membership_id")} />
        </Field>
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Saving…" : "Save and continue"}</Button>
        <button type="button" onClick={logout} className="w-full text-center text-xs text-slate-500 hover:text-slate-700">Log out</button>
      </form>
    </AuthLayout>
  );
}
