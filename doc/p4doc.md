# Phase 4 Documentation — Equations, Remaining Templates, Compile Check

Implements weeks 5–6 of the bible: equation conversion, the three academic
templates, and the pdflatex compile check.

## 1. Equation handler (`app/converter/handlers/equation_handler.py`)

* `convert_equation(omml_xml)` wraps the OMML fragment in a synthetic
  one-paragraph `.docx` archive in memory (a valid `[Content_Types].xml`,
  `_rels/.rels`, `word/document.xml` envelope) and feeds it to Pandoc as a
  subprocess: `pandoc --from docx --to latex`. **This is the only place in
  the project Pandoc is invoked.**
* `_strip_pandoc_wrappers()` peels off `\[ … \]`, `\( … \)`, `$$ … $$`, or
  `$ … $` so the renderer can wrap math in the appropriate delimiter.
* When Pandoc is missing or the subprocess fails, `hydrate_equations()`
  sets `latex_string` to a placeholder and appends a warning.
* Subprocess timeout: 15 s per equation — protects against malformed input.

## 2. Display vs inline detection

* The parser tags every `m:oMathPara` as `display=True` (block-level) and
  every standalone `m:oMath` as `display=False`. The renderer emits
  `\begin{equation}…\end{equation}` vs `$…$`.

## 3. Templates

* **`article.tex.j2`** — default, `\documentclass[11pt]{article}`.
* **`ieee.tex.j2`** — `\documentclass[journal]{IEEEtran}` with author
  block, abstract, keywords placeholders.
* **`acm.tex.j2`** — `\documentclass[sigconf]{acmart}` with
  `\acmConference`, `\acmYear`, affiliation, abstract, keywords.
* **`springer.tex.j2`** — `\documentclass[runningheads]{llncs}`. Note:
  `llncs.cls` is not on CTAN; users must add it alongside the `.tex`
  (Overleaf ships it).

## 4. Compile check (`app/converter/compile_check.py`)

* Runs `pdflatex -interaction=nonstopmode -halt-on-error` inside a temp
  directory with `doc.tex` and any figures in `figures/`.
* Parses the log for the first `! …` message + matching `l.NNN`; returns
  `(compile_ok, error_message, error_line)`.
* If `pdflatex` is not on PATH the check is skipped gracefully and the
  worker adds a warning. Lets Windows dev work without TeX Live.

## 5. Required user-provided metadata

| Template | Fields the user should edit before publishing                            |
| -------- | ------------------------------------------------------------------------ |
| article  | `\title`, `\author`                                                       |
| ieee     | `\title`, `\IEEEauthorblockN`, `\IEEEauthorblockA`, abstract, keywords    |
| acm      | `\acmConference`, `\acmYear`, `\affiliation`, `\email`, abstract, keywords|
| springer | `\title`, `\author`, `\institute`, abstract, keywords; ship `llncs.cls`   |
