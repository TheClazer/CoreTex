interface Props {
  warnings: string[];
}

function classify(w: string): "citation" | "error" | "" {
  if (w.includes("[CITATION]")) return "citation";
  if (/fail/i.test(w)) return "error";
  return "";
}

export function WarningsPanel({ warnings }: Props) {
  if (warnings.length === 0) {
    return <div className="warning-empty">No warnings. Clean conversion.</div>;
  }
  return (
    <div className="warnings" role="region" aria-live="polite" aria-label="Conversion warnings">
      {warnings.map((w, i) => (
        <div key={i} className={`warning ${classify(w)}`}>{w}</div>
      ))}
    </div>
  );
}
