# Golden Test Documents

This directory holds the 15 baseline `.docx` files the parser/renderer are
regression-tested against. Two sources:

1. **Synthetic (in repo)** – produced deterministically by
   `python -m tests.golden.generate`. These run in CI and cover the 15
   content-type slots from the bible (plain text, headings, lists, tables,
   merged cells, images, equations, footnotes, citations, page breaks,
   monospace, unicode, academic paper, etc.).

2. **Real-world (your contribution)** – drop any extra `.docx` files into
   this directory. Test discovery picks up everything matching `*.docx`,
   so adding real samples increases coverage with zero code changes.

## Regenerating

```bash
python -m tests.golden.generate
```

The script overwrites the synthetic files but leaves any user-dropped files
untouched (they have different names).

## Adding to the regression suite

Any new file added here is automatically exercised by:

* `tests/test_parser.py::test_all_golden_docs_parse_cleanly`
* `tests/test_renderer.py::test_all_golden_docs_render_to_latex`

A PR that breaks parsing or rendering on any golden doc must not be merged
(see CI workflow in `.github/workflows/ci.yml`).
