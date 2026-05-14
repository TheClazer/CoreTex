import { useState } from "react";
import { tempUrl } from "../api";

interface Props {
  texSource: string | null;
  blob: Blob | null;
  filename: string | null;
  overleafTempUrl: string | null;
  disabled?: boolean;
  onCopied: () => void;
}

export function ActionsBar({ texSource, blob, filename, overleafTempUrl, disabled, onCopied }: Props) {
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

  const handleOverleaf = () => {
    if (!overleafTempUrl) return;
    const absoluteTempUrl = new URL(tempUrl(overleafTempUrl), window.location.origin).toString();
    const url = `https://www.overleaf.com/docs?snip_uri=${encodeURIComponent(absoluteTempUrl)}`;
    window.open(url, "_blank", "noopener,noreferrer");
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
