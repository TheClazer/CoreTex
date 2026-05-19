import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { setToken } from "../api";
import { useAuth } from "../auth/AuthContext";

/** Captures the access token from the URL hash that the backend bounced
 * back to us with after a successful OAuth callback. */
export function OAuthCallback() {
  const nav = useNavigate();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const hash = window.location.hash.startsWith("#")
      ? window.location.hash.slice(1)
      : window.location.hash;
    const params = new URLSearchParams(hash);
    const token = params.get("token");
    const err = params.get("error");

    if (err) {
      setError(err.replace(/_/g, " "));
      return;
    }
    if (token) {
      setToken(token);
      refresh().finally(() => nav("/", { replace: true }));
    } else {
      setError("No token received from provider.");
    }
  }, [nav, refresh]);

  if (error) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h1>Sign-in failed</h1>
          <div className="warning error" role="alert">{error}</div>
          <a className="primary auth-submit" href="/login">Back to sign in</a>
        </div>
      </div>
    );
  }
  return (
    <div className="auth-shell">
      <div className="auth-card" aria-busy="true">
        <h1>Signing you in…</h1>
        <div className="spinner" style={{ marginTop: "1rem" }} />
      </div>
    </div>
  );
}
