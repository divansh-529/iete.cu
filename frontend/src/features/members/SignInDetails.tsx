import { Alert } from "../../components/ui";
import { CopyBox } from "../users/CopyBox";

/** After an account is activated: either "we emailed them", or the details to pass on by hand. */
export function SignInDetails({ email, emailed, password, loginUrl }: {
  email: string; emailed: boolean; password: string; loginUrl: string;
}) {
  if (emailed) {
    return <Alert tone="green">Sign-in details were emailed to <strong>{email}</strong>. They must choose their own password at first sign-in.</Alert>;
  }
  return (
    <div className="space-y-2">
      <Alert tone="amber">Email isn't set up yet, so nothing was sent. Share these details with them privately (WhatsApp or in person):</Alert>
      <CopyBox value={`Portal: ${loginUrl}\nEmail: ${email}\nFirst-time password: ${password}\n(You'll be asked to choose your own password.)`} />
    </div>
  );
}
