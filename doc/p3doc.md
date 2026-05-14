# Phase 3 Documentation — Tables, Images, Citations

Implements week 4 of the bible: rich-content handling, the zip packager,
and the full end-to-end pipeline.

## 1. Image handler (`app/converter/handlers/image_handler.py`)

* `process_images()` iterates over every `ImageNode`, decodes via Pillow,
  and re-encodes any image whose source bytes exceed a 2 MB budget.
* `img.thumbnail((1600, 1600), Image.LANCZOS)` caps the long edge.
* JPEGs re-encoded at `quality=85`, `optimize=True`; PNGs stay PNG; exotic
  formats (TIFF, BMP, WEBP) converted to PNG for pdflatex compatibility.
* Returns a `{filename: bytes}` dict consumed by the zip packager.

## 2. Table handler (`app/converter/handlers/table_handler.py`)

* `column_spec(table)` consumes `TableNode.col_alignments` and emits the
  LaTeX column-spec string (`l`/`c`/`r`), defaulting to all-`l` if the
  list is empty (fall back to row width).
* `total_columns(table)` returns the maximum `sum(c.col_span)` across rows
  so cell padding in the renderer knows when to fill empty slots.

## 3. Citation handling (renderer)

* The parser extracts every `w:fldChar … CITATION … w:fldChar` block into
  a `CitationNode` with `display_text` populated.
* The renderer emits `display_text % [CITATION -- manual BibTeX needed]`
  and pushes a warning to the accumulator.
* The `/status` endpoint counts warnings containing `[CITATION]` and
  returns the count in `result_summary.citation_count`; the frontend
  highlights citation warnings in cyan.

## 4. Zip packager (`app/api/routes.py`)

* On `/download/{job_id}`, if `result.has_images` is true, the worker has
  pickled `{filename: bytes}` into Redis at `figures:{job_id}` with the
  same TTL as the temp URL. The route loads it and writes each entry into
  `figures/` inside the response zip.
* The `.tex` is also written to Redis at `temp:{job_id}` so the Overleaf
  snip URL works for both `.tex` and `.zip` downloads.

## 5. Status response

`GET /status/{job_id}` now returns a `result_summary` with:

* `has_images`, `warning_count`, `citation_count`, `compile_ok`,
  `compile_error`, `compile_error_line`, `template`, `warnings`.

This matches the frontend `ResultSummary` interface in `src/types.ts`.
