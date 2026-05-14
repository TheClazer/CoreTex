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
  const isBusy = phase === "uploading" || phase === "polling" || phase === "downloading";
  const cls = phase === "done" ? "ok" : phase === "error" ? "err" : isBusy ? "warn" : "";
  return (
    <header className="topbar">
      <div className="brand">
        <div className="mark">Cτ</div>
        <div>
          <div>CoreTex</div>
          <div className="tagline">Word → LaTeX, in seconds.</div>
        </div>
      </div>
      <div className={`status-pill ${cls}`} aria-live="polite">
        {isBusy ? <span className="spinner" aria-hidden="true" /> : <span className="dot" />}
        {PHASE_LABEL[phase] ?? phase}
        {isBusy && elapsedMs > 0 && (
          <span style={{ color: "var(--text-dim)", marginLeft: "0.4rem" }}>
            {(elapsedMs / 1000).toFixed(1)}s
          </span>
        )}
      </div>
    </header>
  );
}
