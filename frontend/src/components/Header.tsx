import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

interface Props {
  phase: string;
  elapsedMs: number;
}

const PHASE_LABEL: Record<string, string> = {
  idle: "Ready",
  uploading: "Uploading…",
  polling: "Converting…",
  downloading: "Finalising…",
  done: "Complete",
  error: "Error",
};

export function Header({ phase, elapsedMs }: Props) {
  const { user, signOut } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  const isBusy = phase === "uploading" || phase === "polling" || phase === "downloading";
  const cls = phase === "done" ? "ok" : phase === "error" ? "err" : isBusy ? "warn" : "";
  const onHistory = location.pathname === "/history";

  return (
    <header className="topbar">
      <Link to="/" className="brand" aria-label="CoreTex home">
        <div className="mark">Cτ</div>
        <div>
          <div>CoreTex</div>
          <div className="tagline">Word → LaTeX, in seconds.</div>
        </div>
      </Link>

      <div className="topbar-right">
        {!onHistory && (
          <div className={`status-pill ${cls}`} aria-live="polite">
            {isBusy ? <span className="spinner" aria-hidden="true" /> : <span className="dot" />}
            {PHASE_LABEL[phase] ?? phase}
            {isBusy && elapsedMs > 0 && (
              <span style={{ color: "var(--text-dim)", marginLeft: "0.4rem" }}>
                {(elapsedMs / 1000).toFixed(1)}s
              </span>
            )}
          </div>
        )}

        {user ? (
          <div className="account">
            <button
              className="account-chip"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
              onBlur={() => setTimeout(() => setMenuOpen(false), 150)}
            >
              <span className="avatar" aria-hidden>{(user.display_name || user.email)[0].toUpperCase()}</span>
              <span className="account-email">{user.display_name || user.email}</span>
              <span aria-hidden>▾</span>
            </button>
            {menuOpen && (
              <div className="account-menu" role="menu" onMouseDown={(e) => e.preventDefault()}>
                <Link to="/history" role="menuitem" onClick={() => setMenuOpen(false)}>
                  📚 History
                </Link>
                <button
                  role="menuitem"
                  onClick={() => {
                    signOut();
                    setMenuOpen(false);
                  }}
                >
                  ↩ Sign out
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="auth-actions">
            <Link to="/login" className="ghost-btn">Sign in</Link>
            <Link to="/signup" className="primary">Sign up</Link>
          </div>
        )}
      </div>
    </header>
  );
}
