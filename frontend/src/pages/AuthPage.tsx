import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ApiError, oauthStartUrl } from "../api";

type Mode = "login" | "signup";

interface Props {
  mode: Mode;
}

export function AuthPage({ mode }: Props) {
  const { signIn, signUp, providers } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const redirectTo = (location.state as { from?: string } | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "signup") await signUp(email, password, displayName || undefined);
      else await signIn(email, password);
      nav(redirectTo, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const isSignup = mode === "signup";

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-header">
          <div className="mark" aria-hidden>Cτ</div>
          <h1>{isSignup ? "Create your account" : "Welcome back"}</h1>
          <p className="auth-sub">
            {isSignup
              ? "Save your conversions and re-download from history."
              : "Sign in to access your conversion history."}
          </p>
        </div>

        {(providers.google || providers.github) && (
          <>
            <div className="oauth-row">
              {providers.google && (
                <a className="oauth-btn google" href={oauthStartUrl("google")}>
                  <span className="oauth-icon" aria-hidden>G</span> Continue with Google
                </a>
              )}
              {providers.github && (
                <a className="oauth-btn github" href={oauthStartUrl("github")}>
                  <span className="oauth-icon" aria-hidden>⌥</span> Continue with GitHub
                </a>
              )}
            </div>
            <div className="oauth-divider"><span>or</span></div>
          </>
        )}

        <form onSubmit={submit} className="auth-form" aria-label={isSignup ? "Sign up form" : "Sign in form"}>
          {isSignup && (
            <label className="auth-field">
              <span>Name <small>(optional)</small></span>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Ada Lovelace"
                autoComplete="name"
              />
            </label>
          )}
          <label className="auth-field">
            <span>Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </label>
          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isSignup ? "At least 8 characters" : "••••••••"}
              autoComplete={isSignup ? "new-password" : "current-password"}
            />
          </label>

          {error && (
            <div className="warning error" role="alert">{error}</div>
          )}

          <button className="primary auth-submit" type="submit" disabled={busy}>
            {busy ? "Please wait…" : isSignup ? "Create account →" : "Sign in →"}
          </button>
        </form>

        <div className="auth-foot">
          {isSignup ? (
            <>Already have an account? <Link to="/login">Sign in</Link></>
          ) : (
            <>New to CoreTex? <Link to="/signup">Create an account</Link></>
          )}
          <span className="dot-sep">·</span>
          <Link to="/">Continue without an account</Link>
        </div>
      </div>
    </div>
  );
}
