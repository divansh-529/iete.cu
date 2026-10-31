import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { Me } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Button, Field, Input, Spinner } from "../../components/ui";
import { AuthLayout } from "../../layouts/AuthLayout";
import { MIN_PASSWORD_LENGTH } from "./ChangePasswordForm";

export function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { setMe } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const invite = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api<{ email: string; full_name: string }>(`/auth/invite/${encodeURIComponent(token)}`),
    enabled: !!token,
    retry: false,
  });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) return setError("The passwords do not match.");
    setBusy(true);
    try {
      const me = await api<Me>("/auth/accept-invite", { method: "POST", body: { token, new_password: password } });
      setMe(me);
      navigate("/app", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!token || invite.isError) {
    return (
      <AuthLayout title="Invite link not valid">
        <p className="text-sm text-slate-600">
          This link is invalid, already used, or has expired. Ask an administrator for a new one.
        </p>
        <Link to="/login" className="mt-4 inline-block text-sm font-medium text-brand-600 hover:underline">Go to sign in</Link>
      </AuthLayout>
    );
  }
  if (invite.isLoading) return <Spinner />;

  return (
    <AuthLayout title={`Welcome, ${invite.data!.full_name}`} subtitle={`Set a password for ${invite.data!.email}.`}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field label="Password" hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
          <Input type="password" autoComplete="new-password" required minLength={MIN_PASSWORD_LENGTH}
                 value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />
        </Field>
        <Field label="Confirm password">
          <Input type="password" autoComplete="new-password" required value={confirm}
                 onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Saving…" : "Set password and sign in"}</Button>
      </form>
    </AuthLayout>
  );
}
