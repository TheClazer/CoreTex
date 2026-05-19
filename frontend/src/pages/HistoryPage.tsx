import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ApiError,
  deleteHistoryItem,
  downloadHistoryItem,
  fetchHistory,
} from "../api";
import { useAuth } from "../auth/AuthContext";
import type { ConversionSummary, HistoryPage as HistoryPageData } from "../types";

const TEMPLATE_BADGE: Record<string, string> = {
  article: "article",
  ieee: "IEEE",
  acm: "ACM",
  springer: "LNCS",
};

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function HistoryPage() {
  const { user, loading: authLoading } = useAuth();
  const nav = useNavigate();
  const [data, setData] = useState<HistoryPageData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const p = await fetchHistory(50, 0);
      setData(p);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      nav("/login", { state: { from: "/history" }, replace: true });
      return;
    }
    void load();
  }, [authLoading, user, nav, load]);

  const handleDownload = async (item: ConversionSummary) => {
    setBusyId(item.id);
    try {
      const dl = await downloadHistoryItem(item.id);
      const url = URL.createObjectURL(dl.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = dl.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (item: ConversionSummary) => {
    if (!window.confirm(`Delete conversion of "${item.filename}"?`)) return;
    setBusyId(item.id);
    try {
      await deleteHistoryItem(item.id);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : (e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  if (authLoading || !user) {
    return (
      <div className="history-shell">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="history-shell">
      <header className="history-header">
        <div>
          <h1>Your conversions</h1>
          <p className="history-sub">
            {data
              ? `${data.total} total — each entry can be re-downloaded instantly without re-running the pipeline.`
              : "Loading…"}
          </p>
        </div>
        <Link to="/" className="primary">+ New conversion</Link>
      </header>

      {error && <div className="warning error" role="alert" style={{ marginBottom: "1rem" }}>{error}</div>}

      {data && data.items.length === 0 && (
        <div className="card history-empty">
          <h2 style={{ marginTop: 0 }}>No conversions yet</h2>
          <p>Drop a Word document on the home page — it'll show up here.</p>
          <Link to="/" className="primary">Convert your first document →</Link>
        </div>
      )}

      <ul className="history-list" aria-label="Conversion history">
        {data?.items.map((item) => (
          <li key={item.id} className="history-row">
            <div className="history-row-main">
              <div className="history-filename" title={item.filename}>{item.filename}</div>
              <div className="history-meta">
                <span className="badge">{TEMPLATE_BADGE[item.template] ?? item.template}</span>
                {item.has_images && <span className="badge soft">images</span>}
                {item.citation_count > 0 && <span className="badge soft">{item.citation_count} cites</span>}
                {item.warning_count > 0 && <span className="badge warn">{item.warning_count} warns</span>}
                <span className={`badge ${item.compile_ok ? "ok" : "err"}`}>
                  {item.compile_ok ? "compiled ✓" : "compile failed"}
                </span>
                <span className="history-date">{formatDate(item.created_at)}</span>
              </div>
            </div>
            <div className="history-row-actions">
              <button onClick={() => handleDownload(item)} disabled={busyId === item.id}>
                ⬇ Download
              </button>
              <button
                className="danger"
                onClick={() => handleDelete(item)}
                disabled={busyId === item.id}
                aria-label={`Delete conversion of ${item.filename}`}
              >
                🗑
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
