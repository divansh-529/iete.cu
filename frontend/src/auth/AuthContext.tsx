import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { api, ApiError } from "../api/client";
import type { Me } from "../api/types";

interface AuthValue {
  me: Me | null;
  loading: boolean;
  /** UI hint only. The backend checks every request again. */
  can: (permission: string) => boolean;
  refresh: () => Promise<void>;
  setMe: (me: Me | null) => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });

  const me = data ?? null;
  const value: AuthValue = {
    me,
    loading: isLoading,
    can: (permission) =>
      !!me && (me.all_permissions || me.permissions.some((p) => p.code === permission)),
    refresh: () => qc.invalidateQueries({ queryKey: ["me"] }),
    setMe: (next) => qc.setQueryData(["me"], next),
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
