import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { UserOrg } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Card, PageHeader } from "../../components/ui";
import { OrgHistoryCard, ProfileCard } from "../org/PersonOrg";
import { ChangePasswordForm } from "./ChangePasswordForm";

export function AccountPage() {
  const { me } = useAuth();
  const org = useQuery({ queryKey: ["my-org"], queryFn: () => api<UserOrg>("/me/org") });
  return (
    <>
      <PageHeader title="My account" subtitle={me?.user.email} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {org.data && <OrgHistoryCard org={org.data} />}
          <Card title="Change password">
            <div className="max-w-md"><ChangePasswordForm /></div>
          </Card>
        </div>
        <div>
          {org.data && me && <ProfileCard userId={me.user.id} profile={org.data.profile} editable self />}
        </div>
      </div>
    </>
  );
}
