import { useEffect, useState } from "react";
import { ActionsBar } from "./components/ActionsBar";
import { ConversionSummary } from "./components/ConversionSummary";
import { Header } from "./components/Header";
import { LatexEditor } from "./components/LatexEditor";
import { TemplateSelector } from "./components/TemplateSelector";
import { UploadZone } from "./components/UploadZone";
import { WarningsPanel } from "./components/WarningsPanel";
import { useConversion } from "./hooks/useConversion";
import type { TemplateChoice } from "./types";

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [template, setTemplate] = useState<TemplateChoice>("article");
  const [toast, setToast] = useState<string | null>(null);
  const { state, start, reset } = useConversion();

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 2000);
    return () => window.clearTimeout(id);
  }, [toast]);

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

  return (
    <div className="app-shell">
      <Header phase={state.phase} elapsedMs={state.elapsedMs} />

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
              onCopied={() => setToast("Copied to clipboard")}
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

      <footer className="footer">
        <span>
          CoreTex · IR-pipeline Word → LaTeX converter ·{" "}
          <a href="https://github.com" target="_blank" rel="noopener noreferrer">
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
