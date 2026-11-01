import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { ApiError } from "./api/client";
import { AuthProvider } from "./auth/AuthContext";
import { AccountPage } from "./features/auth/AccountPage";
import { AcceptInvitePage } from "./features/auth/AcceptInvitePage";
import { CompleteProfilePage } from "./features/auth/CompleteProfilePage";
import { ForcedChangePasswordPage } from "./features/auth/ForcedChangePasswordPage";
import { LoginPage } from "./features/auth/LoginPage";
import { AuditPage } from "./features/audit/AuditPage";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { DocumentsPage } from "./features/documents/DocumentsPage";
import { FinancePage } from "./features/finance/FinancePage";
import { MembershipPage } from "./features/finance/MembershipPage";
import { RecruitmentPage } from "./features/members/RecruitmentPage";
import { PersonScoresPage } from "./features/scores/PersonScoresPage";
import { ScoresPage } from "./features/scores/ScoresPage";
import { EventDetailPage } from "./features/events/EventDetailPage";
import { EventsPage } from "./features/events/EventsPage";
import { DepartmentDetailPage } from "./features/org/DepartmentDetailPage";
import { OrgPage } from "./features/org/OrgPage";
import { PositionDetailPage } from "./features/org/PositionDetailPage";
import { RolesPage } from "./features/roles/RolesPage";
import { TaskDetailPage } from "./features/tasks/TaskDetailPage";
import { TasksPage } from "./features/tasks/TasksPage";
import { UserDetailPage } from "./features/users/UserDetailPage";
import { UsersPage } from "./features/users/UsersPage";
import "./index.css";
import { AppLayout } from "./layouts/AppLayout";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

// A 401 anywhere means the session ended (logout elsewhere, expiry, suspension): refresh `me`.
queryClient.getQueryCache().subscribe((event) => {
  const error = event.type === "updated" ? event.query.state.error : null;
  if (error instanceof ApiError && error.status === 401 && event.query.queryKey[0] !== "me") {
    queryClient.setQueryData(["me"], null);
  }
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/change-password" element={<ForcedChangePasswordPage />} />
            <Route path="/complete-profile" element={<CompleteProfilePage />} />
            <Route path="/accept-invite" element={<AcceptInvitePage />} />
            <Route path="/app" element={<AppLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="events" element={<EventsPage />} />
              <Route path="events/:id" element={<EventDetailPage />} />
              <Route path="tasks" element={<TasksPage />} />
              <Route path="tasks/:id" element={<TaskDetailPage />} />
              <Route path="documents" element={<DocumentsPage />} />
              <Route path="finance" element={<FinancePage />} />
              <Route path="membership" element={<MembershipPage />} />
              <Route path="recruitment" element={<RecruitmentPage />} />
              <Route path="scores" element={<ScoresPage />} />
              <Route path="scores/people/:id" element={<PersonScoresPage />} />
              <Route path="users" element={<UsersPage />} />
              <Route path="users/:id" element={<UserDetailPage />} />
              <Route path="org" element={<OrgPage />} />
              <Route path="org/departments/:id" element={<DepartmentDetailPage />} />
              <Route path="org/positions/:id" element={<PositionDetailPage />} />
              <Route path="roles" element={<RolesPage />} />
              <Route path="audit" element={<AuditPage />} />
              <Route path="account" element={<AccountPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/app" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
