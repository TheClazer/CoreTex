import { useState } from "react";
import { tempUrl } from "../api";

interface Props {
  texSource: string | null;
  blob: Blob | null;
  filename: string | null;
  overleafTempUrl: string | null;
  disabled?: boolean;
  onCopied: () => void;
  onNotice?: (message: string) => void;
}

export function ActionsBar({ texSource, blob, filename, overleafTempUrl, disabled, onCopied, onNotice }: Props) {
  const [copying, setCopying] = useState(false);

  const handleDownload = () => {
    if (!blob || !filename) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const handleCopy = async () => {
    if (!texSource) return;
    setCopying(true);
    try {
      await navigator.clipboard.writeText(texSource);
      onCopied();
    } finally {
      setCopying(false);
    }
  };

  const handleOverleaf = async () => {
    if (!overleafTempUrl) return;
    const absoluteTempUrl = new URL(tempUrl(overleafTempUrl), window.location.origin).toString();
    const url = `https://www.overleaf.com/docs?snip_uri=${encodeURIComponent(absoluteTempUrl)}`;
    // Open the tab synchronously inside the click so popup blockers allow it,
    // then only send it to Overleaf once the temp link is confirmed alive —
    // an expired link otherwise lands on Overleaf's "file not found" page.
    const win = window.open("about:blank", "_blank");
    try {
      const res = await fetch(absoluteTempUrl, { method: "HEAD" });
      if (!res.ok) throw new Error(`temp link returned ${res.status}`);
    } catch {
      win?.close();
      onNotice?.("Overleaf link expired. Convert again to get a fresh one.");
      return;
    }
    if (win) {
      win.opener = null;
      win.location.href = url;
    } else {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div className="actions-row" role="group" aria-label="Download actions">
      <button
        className="primary"
        onClick={handleDownload}
        disabled={disabled || !blob}
        aria-label={filename?.endsWith(".zip") ? "Download .zip" : "Download .tex"}
      >
        ⬇ Download {filename?.endsWith(".zip") ? ".zip" : ".tex"}
      </button>
      <button onClick={handleCopy} disabled={disabled || !texSource || copying}>
        {copying ? "Copying…" : "📋 Copy LaTeX"}
      </button>
      <button onClick={handleOverleaf} disabled={disabled || !overleafTempUrl}>
        ↗ Open in Overleaf
      </button>
    </div>
  );
}
