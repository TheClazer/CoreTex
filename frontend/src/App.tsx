import { useEffect, useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Header } from "./components/Header";
import { AuthProvider } from "./auth/AuthContext";
import { AuthPage } from "./pages/AuthPage";
import { ConverterPage } from "./pages/ConverterPage";
import { HistoryPage } from "./pages/HistoryPage";
import { OAuthCallback } from "./pages/OAuthCallback";

function AppShell() {
  const [toast, setToast] = useState<string | null>(null);
  const [phase, setPhase] = useState("idle");
  const [elapsed, setElapsed] = useState(0);

  // The header reads phase + elapsed; pages publish them via custom events
  // so we don't have to hoist conversion state above the router.
  useEffect(() => {
    const onPhase = (e: Event) => {
      const detail = (e as CustomEvent).detail as { phase: string; elapsedMs: number };
      setPhase(detail.phase);
      setElapsed(detail.elapsedMs);
    };
    window.addEventListener("coretex:phase", onPhase as EventListener);
    return () => window.removeEventListener("coretex:phase", onPhase as EventListener);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 2000);
    return () => window.clearTimeout(id);
  }, [toast]);

  return (
    <div className="app-shell">
      <Header phase={phase} elapsedMs={elapsed} />

      <Routes>
        <Route path="/" element={<ConverterPage onToast={setToast} />} />
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/signup" element={<AuthPage mode="signup" />} />
        <Route path="/auth/callback" element={<OAuthCallback />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="*" element={<ConverterPage onToast={setToast} />} />
      </Routes>

      <footer className="footer">
        <span>
          CoreTex · IR-pipeline Word → LaTeX converter ·{" "}
          <a href="https://github.com/TheClazer/CoreTex" target="_blank" rel="noopener noreferrer">
            GitHub
          </a>
        </span>
        <span>
          Tip: <span className="kbd">Ctrl</span>+<span className="kbd">C</span> inside the editor copies the
          selected LaTeX.
        </span>
      </footer>

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </BrowserRouter>
  );
}
