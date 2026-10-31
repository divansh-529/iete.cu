import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../../api/client";
import type { Me } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Button, Field, Input } from "../../components/ui";

export const MIN_PASSWORD_LENGTH = 10;

export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const { setMe } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    if (next !== confirm) return setError("The new passwords do not match.");
    setBusy(true);
    try {
      const me = await api<Me>("/auth/change-password", {
        method: "POST", body: { current_password: current, new_password: next },
      });
      setMe(me);
      setCurrent(""); setNext(""); setConfirm("");
      setSuccess(true);
      onDone?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      {error && <Alert>{error}</Alert>}
      {success && <Alert tone="green">Password changed. Other devices have been signed out.</Alert>}
      <Field label="Current password">
        <Input type="password" autoComplete="current-password" required value={current}
               onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <Field label="New password" hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}>
        <Input type="password" autoComplete="new-password" required minLength={MIN_PASSWORD_LENGTH}
               value={next} onChange={(e) => setNext(e.target.value)} />
      </Field>
      <Field label="Confirm new password">
        <Input type="password" autoComplete="new-password" required value={confirm}
               onChange={(e) => setConfirm(e.target.value)} />
      </Field>
      <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Change password"}</Button>
    </form>
  );
}
