import { Navigate, useNavigate } from "react-router";
import { useAuth } from "../../auth/AuthContext";
import { Spinner } from "../../components/ui";
import { AuthLayout } from "../../layouts/AuthLayout";
import { ChangePasswordForm } from "./ChangePasswordForm";

export function ForcedChangePasswordPage() {
  const { me, loading } = useAuth();
  const navigate = useNavigate();
  if (loading) return <Spinner />;
  if (!me) return <Navigate to="/login" replace />;
  if (!me.user.must_change_password) return <Navigate to="/app" replace />;

  return (
    <AuthLayout title="Choose a new password"
                subtitle="You signed in with a temporary password. Set your own password to continue.">
      <ChangePasswordForm onDone={() => navigate("/app", { replace: true })} />
    </AuthLayout>
  );
}
