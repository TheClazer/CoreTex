import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  fetchMe,
  fetchProviders,
  getToken,
  login as apiLogin,
  setToken,
  signup as apiSignup,
} from "../api";
import type { AuthProviders, User } from "../types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  providers: AuthProviders;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName?: string) => Promise<void>;
  signOut: () => void;
  refresh: () => Promise<void>;
}

const DEFAULT_PROVIDERS: AuthProviders = { email: true, google: false, github: false };

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState<AuthProviders>(DEFAULT_PROVIDERS);

  const loadMe = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    try {
      const me = await fetchMe();
      setUser(me);
    } catch {
      // Token invalid or expired
      setToken(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const p = await fetchProviders();
        setProviders(p);
      } catch {
        // Backend unreachable or auth disabled — leave defaults.
      }
      await loadMe();
      setLoading(false);
    })();
  }, [loadMe]);

  const signIn = useCallback(async (email: string, password: string) => {
    const res = await apiLogin(email, password);
    setToken(res.access_token);
    setUser(res.user);
  }, []);

  const signUp = useCallback(
    async (email: string, password: string, displayName?: string) => {
      const res = await apiSignup(email, password, displayName);
      setToken(res.access_token);
      setUser(res.user);
    },
    []
  );

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, providers, signIn, signUp, signOut, refresh: loadMe }),
    [user, loading, providers, signIn, signUp, signOut, loadMe]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
