import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router";
import { api } from "../api/client";
import type { MemberProposal } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { BrandLogo } from "../components/Brand";
import { Button, cx, Modal, Spinner } from "../components/ui";
import { NotificationsPanel, useNotifications } from "../features/notifications/NotificationsPanel";

interface NavItem {
  to: string;
  label: string;
  icon: string;  // SVG path, 24×24 outline
  permission?: string | string[];   // any of these
  members?: boolean;                // the membership list goes by position (me.can_view_members)
}

const NAV: NavItem[] = [
  { to: "/app", label: "Dashboard", icon: "M3 12 12 4l9 8M5 10v10h5v-6h4v6h5V10" },
  // Events and Tasks are open to everyone: what each person sees there depends on their access.
  { to: "/app/events", label: "Events",
    icon: "M8 3v3m8-3v3M4 9h16M5 6h14a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1m4 7h2v2H9z" },
  { to: "/app/tasks", label: "Tasks", icon: "M9 11l3 3 8-8M20 12v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h11" },
  { to: "/app/documents", label: "Documents", permission: "documents.view",
    icon: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zm0 0v5h5M9 13h6m-6 4h6" },
  { to: "/app/finance", label: "Finance",
    permission: ["finance.view", "finance.expense.submit", "finance.expense.verify", "finance.expense.approve"],
    icon: "M3 7h18v12H3zm0 4h18M7 15h3" },
  { to: "/app/membership", label: "Membership", members: true,
    icon: "M4 5h16v14H4zm5 5a2 2 0 1 0 0-.01M6 16c.5-1.7 1.7-2.5 3-2.5s2.5.8 3 2.5m3-6h3m-3 3h3" },
  { to: "/app/scores", label: "Score cards",
    icon: "M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z" },
  { to: "/app/org", label: "Organisation", permission: "org.view",
    icon: "M12 3v5m0 0H6v4m6-4h6v4M4 12h4v4H4zm12 0h4v4h-4zM10 16h4v5h-4zm2-4v4" },
  { to: "/app/recruitment", label: "Recruitment", permission: ["users.approve", "org.assign"],
    icon: "M15 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1m6-9a3 3 0 1 0 0-6 3 3 0 0 0 0 6m10-1v6m3-3h-6" },
  { to: "/app/users", label: "Team accounts", permission: "users.view",
    icon: "M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6m13 9v-1a4 4 0 0 0-3-3.9M16 4.1a3 3 0 0 1 0 5.8" },
  { to: "/app/roles", label: "Roles", permission: "permissions.view",
    icon: "M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6zm-3 9 2 2 4-4" },
  { to: "/app/audit", label: "Audit log", permission: "audit.view",
    icon: "M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v0a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2m0 7h6m-6 4h4" },
];

function Icon({ d, className }: { d: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true" className={cx("size-5 shrink-0", className)}>
      <path d={d} />
    </svg>
  );
}

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
}

export function AppLayout() {
  const { me, loading, can } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const ready = !!me && !me.user.must_change_password && me.profile_complete;
  const notifications = useNotifications(ready);
  const unread = notifications.data?.unread ?? 0;
  const approver = ready && can("users.approve");
  const waiting = useQuery({ queryKey: ["proposals", "pending"], enabled: approver, refetchInterval: 120_000,
                             queryFn: () => api<MemberProposal[]>("/member-proposals?status=pending") });
  const toDecide = waiting.data?.filter((p) => p.can_decide).length ?? 0;

  if (loading) return <Spinner />;
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (me.user.must_change_password) return <Navigate to="/change-password" replace />;
  if (!me.profile_complete) return <Navigate to="/complete-profile" replace />;

  async function logout() {
    setLoggingOut(true);
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    // Full page load, so nothing of this user stays in memory for whoever signs in next.
    window.location.replace("/login");
  }

  const items = NAV.filter((i) => (i.members ? me.can_view_members : !i.permission || [i.permission].flat().some((p) => can(p))));

  return (
    <div className="min-h-screen bg-slate-50 md:flex">
      <aside className="border-b border-slate-200 bg-white md:sticky md:top-0 md:flex md:h-screen md:w-64 md:flex-col md:border-r md:border-b-0">
        <div className="h-1 bg-gradient-to-r from-brand-600 via-brand-500 to-brand-700" />
        <div className="flex items-center justify-between gap-2 px-4 py-4">
          <BrandLogo className="w-44 md:w-52" />
          <button className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-100 md:hidden"
                  onClick={() => setMenuOpen((o) => !o)} aria-label="Toggle menu" aria-expanded={menuOpen}>
            <Icon d={menuOpen ? "M6 6l12 12M18 6 6 18" : "M4 7h16M4 12h16M4 17h16"} />
            {unread > 0 && !menuOpen && <span className="absolute top-1 right-1 size-2.5 rounded-full bg-red-500" />}
          </button>
        </div>
        <div className={cx("px-5 pb-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase", !menuOpen && "hidden md:block")}>
          Management Portal
        </div>
        <nav className={cx("flex-1 space-y-1 overflow-y-auto px-3 pb-4", !menuOpen && "hidden md:block")}>
          {items.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/app"}
                     onClick={() => setMenuOpen(false)}
                     className={({ isActive }) => cx(
                       "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                       isActive
                         ? "bg-brand-50 text-brand-700 before:absolute before:inset-y-2 before:left-0 before:w-1 before:rounded-r before:bg-brand-600"
                         : "text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                     )}>
              {({ isActive }) => (
                <>
                  <Icon d={item.icon} className={isActive ? "text-brand-600" : "text-slate-400 group-hover:text-slate-600"} />
                  {item.label}
                  {item.to === "/app/recruitment" && toDecide > 0 && (
                    <span className="ml-auto rounded-full bg-amber-500 px-2 py-0.5 text-[11px] font-semibold text-white">{toDecide}</span>
                  )}
                </>
              )}
            </NavLink>
          ))}
          <button onClick={() => { setPanelOpen(true); setMenuOpen(false); }}
                  className="group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900">
            <Icon d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 0 0-4-5.7V5a2 2 0 1 0-4 0v.3A6 6 0 0 0 6 11v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9"
                  className="text-slate-400 group-hover:text-slate-600" />
            Notifications
            {unread > 0 && <span className="ml-auto rounded-full bg-red-500 px-2 py-0.5 text-[11px] font-semibold text-white">{unread > 99 ? "99+" : unread}</span>}
          </button>
        </nav>
        <div className={cx("border-t border-slate-200 p-3", !menuOpen && "hidden md:block")}>
          <div className="flex items-center gap-3 rounded-lg p-2">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-xs font-semibold text-white">
              {initials(me.user.full_name)}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-slate-900">{me.user.full_name}</div>
              <div className="truncate text-xs text-slate-500">{me.user.email}</div>
            </div>
          </div>
          <div className="mt-1 grid grid-cols-2 gap-1 text-xs font-medium">
            <NavLink to="/app/account" onClick={() => setMenuOpen(false)}
                     className="rounded-md px-2 py-1.5 text-center text-slate-600 hover:bg-slate-100 hover:text-slate-900">My account</NavLink>
            <button onClick={() => setConfirmLogout(true)} className="rounded-md px-2 py-1.5 text-slate-600 hover:bg-red-50 hover:text-red-700">Log out</button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 lg:px-10 lg:py-8">
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
      {panelOpen && <NotificationsPanel onClose={() => setPanelOpen(false)} />}
      <Modal title="Log out?" open={confirmLogout} onClose={() => setConfirmLogout(false)}>
        <p className="text-sm text-slate-600">Are you sure you want to log out?</p>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmLogout(false)} disabled={loggingOut}>Cancel</Button>
          <Button onClick={logout} disabled={loggingOut}>{loggingOut ? "Logging out…" : "Yes, log out"}</Button>
        </div>
      </Modal>
    </div>
  );
}
