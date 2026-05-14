# Phase 5 Documentation — Frontend, CI, Deployment

Implements weeks 7–8 of the bible: the React frontend, the CI workflow,
and deployment to Railway + Vercel.

## 1. Frontend (`frontend/`)

* Vite + React 18 + TypeScript (strict mode).
* `src/App.tsx`: left column (Upload → Template → Convert → Summary →
  Warnings) and right column (CodeMirror editor + action bar).
* `src/hooks/useConversion.ts` owns the full job lifecycle: upload → poll
  every 2 s → fetch download → expose `texSource`, `downloadBlob`,
  `overleafTempUrl`, `summary`, `phase`, `elapsedMs`.
* Polling uses recursive `setTimeout`, never `setInterval`, so a slow
  `/status` cannot stack requests.
* `UploadZone.tsx` — `react-dropzone` with `.docx` + 20 MB validation,
  ARIA-labelled, keyboard accessible.
* `TemplateSelector.tsx` — radio-group fieldset, four templates,
  `:has(input:checked)` CSS highlights the active card.
* `LatexEditor.tsx` — CodeMirror 6 with the legacy `stex` mode, a
  `StateField` + `StateEffect` that decorates the compile-error line and
  scrolls it into view.
* `ActionsBar.tsx` — Download, Copy LaTeX, Open in Overleaf (composes
  `https://www.overleaf.com/docs?snip_uri=…`).
* `api.ts` — uses `VITE_API_BASE` (empty in dev → Vite proxy; full URL in
  production).

## 2. Vite proxy

`vite.config.ts` proxies `/convert`, `/status`, `/download`, `/temp` to
`http://localhost:8000` so dev needs no CORS configuration.

## 3. Accessibility & polish

* Status pill uses `aria-live="polite"` and shows an animated spinner.
* Dropzone has `role="button"`, `tabIndex={0}`, visible focus ring.
* All controls have `:focus-visible` outlines.
* Toasts use `role="status"`.
* Mobile layout collapses to single column under 880 px.

## 4. Tests

`frontend/src/__tests__/` contains Vitest specs. Run with `npm test`.

## 5. CI (`.github/workflows/ci.yml`)

Two jobs run on every PR + push to `main`:

* **backend** — Python 3.12, installs Pandoc, runs `ruff` + `pytest`.
* **frontend** — Node 20, runs `tsc --noEmit`, ESLint, Vitest, `vite build`.

## 6. Deployment

See **`DEPLOY.md`** in the repo root for the full Railway + Vercel walkthrough.
