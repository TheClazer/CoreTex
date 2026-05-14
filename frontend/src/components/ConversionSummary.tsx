import type { ResultSummary } from "../types";

interface Props {
  summary: ResultSummary | null;
}

export function ConversionSummary({ summary }: Props) {
  if (!summary) {
    return <div className="warning-empty">No conversion run yet.</div>;
  }
  return (
    <div className="summary-grid">
      <div className="item">
        <div className="label">Template</div>
        <div className="value">{summary.template}</div>
      </div>
      <div className="item">
        <div className="label">Compile</div>
        <div className="value" style={{ color: summary.compile_ok ? "var(--ok)" : "var(--err)" }}>
          {summary.compile_ok ? "OK" : "FAIL"}
        </div>
      </div>
      <div className="item">
        <div className="label">Images</div>
        <div className="value">{summary.has_images ? "Bundled" : "None"}</div>
      </div>
      <div className="item">
        <div className="label">Citations</div>
        <div className="value">{summary.citation_count}</div>
      </div>
      <div className="item">
        <div className="label">Warnings</div>
        <div className="value">{summary.warning_count}</div>
      </div>
      {summary.compile_error_line !== null && (
        <div className="item">
          <div className="label">Error line</div>
          <div className="value">{summary.compile_error_line}</div>
        </div>
      )}
    </div>
  );
}
