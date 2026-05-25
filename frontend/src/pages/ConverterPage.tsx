import { useEffect, useState } from "react";
import { ActionsBar } from "../components/ActionsBar";
import { ConversionSummary } from "../components/ConversionSummary";
import { LatexEditor } from "../components/LatexEditor";
import { TemplateSelector } from "../components/TemplateSelector";
import { UploadZone } from "../components/UploadZone";
import { WarningsPanel } from "../components/WarningsPanel";
import { useConversion } from "../hooks/useConversion";
import { useAuth } from "../auth/useAuth";
import type { TemplateChoice } from "../types";

interface Props {
  onToast: (msg: string) => void;
}

export function ConverterPage({ onToast }: Props) {
  const { user } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [template, setTemplate] = useState<TemplateChoice>("article");
  const { state, start, reset } = useConversion();

  const isBusy =
    state.phase === "uploading" ||
    state.phase === "polling" ||
    state.phase === "downloading";

  const handleConvert = () => {
    if (file) start(file, template);
  };

  const handleReset = () => {
    setFile(null);
    reset();
  };

  // Show a brief banner when a conversion came from the dedup cache.
  useEffect(() => {
    if (state.cached && state.phase === "done") {
      onToast("Restored from history — identical upload");
    }
  }, [state.cached, state.phase, onToast]);

  // Publish phase + elapsed to the persistent Header (which lives above the router).
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("coretex:phase", {
        detail: { phase: state.phase, elapsedMs: state.elapsedMs },
      })
    );
  }, [state.phase, state.elapsedMs]);

  return (
    <main>
      <section aria-label="Conversion controls" className="stack">
        <div className="card">
          <h2>1. Upload</h2>
          <UploadZone onFile={setFile} selectedFile={file} disabled={isBusy} />
        </div>

        <div className="card">
          <h2>2. Template</h2>
          <TemplateSelector value={template} onChange={setTemplate} disabled={isBusy} />
        </div>

        <div className="card">
          <h2>3. Convert</h2>
          <div className="actions-row">
            <button
              className="primary"
              onClick={handleConvert}
              disabled={!file || isBusy}
              aria-label="Start conversion"
            >
              {isBusy ? "Working…" : "Convert →"}
            </button>
            <button onClick={handleReset} disabled={isBusy && state.phase !== "error"}>
              Reset
            </button>
          </div>
          {!user && (
            <p className="hint" style={{ marginTop: "0.6rem" }}>
              <a href="/login">Sign in</a> to save your conversions to history.
            </p>
          )}
          {state.error && (
            <div className="warning error" role="alert" style={{ marginTop: "0.75rem" }}>
              {state.error}
            </div>
          )}
        </div>

        <div className="card">
          <h2>Summary</h2>
          <ConversionSummary summary={state.summary} />
        </div>

        <div className="card">
          <h2>Warnings {state.summary && `(${state.summary.warning_count})`}</h2>
          <WarningsPanel warnings={state.summary?.warnings ?? []} />
        </div>
      </section>

      <section aria-label="LaTeX output" className="card editor-wrapper">
        <div className="editor-toolbar">
          <h2 style={{ margin: 0 }}>LaTeX source</h2>
          <ActionsBar
            texSource={state.texSource}
            blob={state.downloadBlob}
            filename={state.downloadFilename}
            overleafTempUrl={state.overleafTempUrl}
            disabled={state.phase !== "done"}
            onCopied={() => onToast("Copied to clipboard")}
          />
        </div>
        {state.texSource ? (
          <LatexEditor
            value={state.texSource}
            errorLine={state.summary?.compile_error_line ?? null}
          />
        ) : (
          <div className="editor-shell">
            <div className="editor-empty">
              <div>
                <p style={{ fontWeight: 600, fontSize: "1.1rem" }}>
                  Drop a Word document to see the generated LaTeX here.
                </p>
                <p style={{ marginTop: "0.5rem" }}>
                  Syntax-highlighted, copyable, and one click into Overleaf.
                </p>
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
