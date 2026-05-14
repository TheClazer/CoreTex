# Phase 2 Documentation — Parser & Renderer Baseline

Implements weeks 2–3 of the bible: the Word OOXML parser, the LaTeX renderer,
and the character escape layer.

## 1. Parser (`app/converter/parser.py`)

* Reads `.docx` bytes via `python-docx` + raw `lxml` queries through the
  `w:`, `r:`, `a:`, `m:` namespaces.
* Walks `doc.element.body` in document order so paragraphs and tables stay
  interleaved correctly.
* Heading detection: maps Word style names `Heading 1..4` (and `Title` → 1)
  to `HeadingNode.level`.
* Run detection: `paragraph.runs` with `bold/italic/underline` flags, plus
  font-name inspection (`Courier`, `Consolas`, `Mono`, `Menlo`) → `code=True`.
* List detection: primary signal is `w:numPr`; fallback to style names
  (`List Number`, `List Bullet`, `List Bullet 2`, …) using synthetic numIds
  `1000` (ordered) and `2000` (unordered).
* Tables: row/cell extraction, `w:gridSpan` → `col_span`, `w:vMerge=restart`
  → `row_span`, per-cell alignment from `<w:jc>`, column alignment voted
  from per-column majority.
* Inline extractions: hyperlinks (via `r:id` lookup), OMML equations
  (inline `m:oMath`, display `m:oMathPara`), citations (`w:fldChar` +
  `w:instrText` pairs containing `CITATION`), footnote refs (resolved
  against `word/footnotes.xml`).
* Images: zip-walked from `word/media/`, matched by relationship ID, raw
  bytes stored in `ImageNode.image_data` for the image handler to compress.
* Page breaks: standalone `<w:br w:type="page"/>` paragraphs become
  `PageBreakNode`; inline page-break runs append `PageBreakNode` after the
  paragraph.

## 2. Renderer (`app/converter/renderer.py`)

* Pure-Python walker — Pandoc is never invoked here.
* Per-node renderers for every IR type. Run formatting nests from inside
  out (`\textbf{\textit{...}}`).
* Lists support arbitrary nesting via a recursive `_render_list_items` walk.
* Tables emit `\begin{tabular}{lcr…}` with `\toprule` / `\midrule` /
  `\bottomrule`; merged cells use `\multicolumn{N}{align}{…}`.
* **Smart preamble injection** (`_required_packages`): walks the doc and
  only emits `\usepackage{amsmath}` when equations exist,
  `\usepackage{hyperref}` when hyperlinks exist, `\usepackage{graphicx}`
  when images exist, `\usepackage{booktabs}` when tables exist,
  `\usepackage{enumitem}` when lists exist.
* Jinja2 templates use custom `<< >>` / `<% %>` delimiters so LaTeX braces
  pass through untouched. `StrictUndefined` catches missing template vars
  at render time.

## 3. Escape layer (`app/converter/escape.py`)

* Handles all 10 reserved characters: `\ { } % & $ # _ ^ ~`.
* Backslash uses a `\x00`-delimited placeholder so the curly braces in
  `\textbackslash{}` are not re-escaped by the subsequent rules.
* Unicode mappings: em-dash, en-dash, ellipsis, curly quotes (both
  directions), non-breaking space, guillemets, bullet, copyright,
  registered, trademark, degree.
* Separate `escape_url()` for the URL argument of `\href{...}{…}`.

## 4. Tests

* 17 unit tests in `tests/test_escape.py` — every reserved character,
  combinations, Unicode edge cases, URL escapes.
* 9 parser tests in `tests/test_parser.py` — including the
  `test_all_golden_docs_parse_cleanly` regression sweep over every
  `.docx` in `tests/golden/`.
* 16 renderer tests in `tests/test_renderer.py` — node-by-node coverage,
  the four-template wrap test, and `test_all_golden_docs_render_to_latex`.
