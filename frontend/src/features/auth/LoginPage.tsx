import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { Me } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Button, Field, Input } from "../../components/ui";
import { AuthLayout } from "../../layouts/AuthLayout";

export function LoginPage() {
  const { me, setMe } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (me) return <Navigate to={me.user.must_change_password ? "/change-password" : "/app"} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api<Me>("/auth/login", { method: "POST", body: { email, password } });
      setMe(result);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(result.user.must_change_password ? "/change-password" : from ?? "/app", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Sign in" subtitle="Accounts are created by the forum administrators.">
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field label="Email">
          <Input type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} autoFocus />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        <p className="text-center text-xs text-slate-500">Forgot your password? Ask an administrator to reset it.</p>
        <p className="text-center text-xs"><Link to="/" className="font-medium text-brand-600 hover:underline">← Back to home page</Link></p>
      </form>
    </AuthLayout>
  );
}
