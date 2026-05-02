# CoreTex: Word to LaTeX Converter (Phase 1 Documentation)

## Overview
This document serves as an ongoing log of architecture decisions, file scaffolding, and logic implementations for the CoreTex backend (FastAPI + Redis/RQ). It is designed to keep all team members aligned on the current state of the backend.

## 1. Project Scaffolding
- **Structure setup**: Created a robust, modular layout for the application directly in the main workspace root (`CoreTex/`).
- **Core modules**: Included structural stubs for API routing (`app/api/`), the core business logic parsing & rendering layers (`app/converter/`), and background task queue workers (`app/queue/`).
- **Testing**: Added scaffolding for integration and unit testing (`tests/`) including a `golden/` directory to store static `.docx` test cases.

## 2. Dependencies Setup
- Defined production packages in `requirements.txt` anchored on standard minimums for **Python 3.12**.
- **Key libraries**: `fastapi` and `uvicorn[standard]` for the web framework, `pydantic[email]` (v2) for rigid data validation, `python-docx` and `lxml` for parsing MS Word XML, `redis` and `rq` for asynchronous job processing, `Pillow` for image compression, `Jinja2` for LaTeX generation, and `slowapi` for endpoint rate limiting.
- Defined development necessities in `requirements-dev.txt`, bringing in `black`, `ruff`, and `pytest-asyncio` for formatting, linting, and async testing workflows.

## 3. Git Configuration
- Augmented the `.gitignore` rule set to explicitly block local Python cache artifacts (`venv/`, `__pycache__/`, `*.pyc`). 
- Resynced the git index to ensure the staging area remains pristine and free from erroneously tracked cache files.

## 4. Intermediate Representation (IR) Schema Design
- **Path**: `app/converter/ir_schema.py`
- Engineered the rigid intermediate state that connects the parsing layer (Word doc reading) and the rendering layer (LaTeX generation).
- Modeled extensively using **Pydantic v2** constructs. Utilizes `Literal` typing for straightforward node_type pattern matching.
- **Node Entities Developed**: `RunNode`, `HeadingNode`, `ParagraphNode`, `ListItemNode`, `ListNode`, `TableCellNode`, `TableRowNode`, `TableNode`, `ImageNode`, `EquationNode`, `FootnoteNode`, `HyperlinkNode`, `CitationNode`, and `PageBreakNode`.
- Packaged as a unified `IRNode` type union and wrapped into an `IRDocument`. Defined the ultimate background task output struct as `ConversionResult`.
- **Constraint Rule**: IR structures are labeled as **frozen** after Week 1. Any modifications to structural schemas from this point require explicit team sign-off.

## 5. Application Entrypoint
- **Path**: `app/main.py`
- Initialized the core FastAPI application configuration (`Word to LaTeX Converter`).
- Wired **SlowAPI** (`Limiter`) globally directly into the app state and initialized rate limiting middleware using `get_remote_address` to protect future endpoints against abuse.
- Plumbed **CORS middleware** permitting local development connectivity (e.g. Vite frontend running on `http://localhost:5173`) and open traffic (`*`) to ensure unblocked development testing.
- Included the base API `router` import path mapping to `app.api.routes` (Note: the router structure needs to be fully instantiated next).
- Exposed a basic root health check endpoint (`GET /`).

## Next Immediate Technical Steps
- Implement the baseline routing structures inside `app/api/routes.py` to instantiate the `APIRouter` and allow `main.py` to boot up successfully without `ImportError`.
- Begin implementing the parsing algorithms in `app/converter/parser.py` using `python-docx`.
- Establish the Redis connection logic and task handling in `app/queue/worker.py`.

## 6. Environment Configuration
- Added `.env` file for local development and excluded it via `.gitignore` to avoid secrets leakage.
- Created `.env.example` as a template for team members to sync configurations easily.
- Instantiated `app/config.py` using Pydantic's `BaseSettings`. We now expose a module-level `settings` object that maps directly to the `.env` values.
- Integrated a property (`max_file_size_bytes`) directly into our settings model.
- Refactored `app/api/routes.py` and `app/queue/worker.py` to strip out explicit config dictionaries and raw `os.getenv` calls, routing everything back through our centralized `settings` object.

## 7. API Endpoint Integration Testing
A test suite has been added under `tests/test_integration.py` covering our REST endpoints via `pytest`, `pytest-asyncio`, and `httpx.AsyncClient` with `ASGITransport`.

**Test Cases Created:**
1. **`test_root_endpoint`**: Verifies that `GET /` consistently routes through and returns `{"status": "ok"}`.
2. **`test_convert_rejects_non_docx`**: Checks our file signature assertion logic to ensure files without the magic bytes (like simple `.txt` uploads) fail immediately with an HTTP 400 payload before hitting background queues.
3. **`test_convert_rejects_large_file`**: Validates the payload limiting validation logic inside `POST /convert`. We fake a file larger than `settings.MAX_FILE_SIZE_MB` and confirm it gracefully traps an HTTP 413 (Payload Too Large).
4. **`test_convert_accepts_valid_docx`**: Simulates the happy-path. Employs a procedural test fixture utilizing `python-docx` to synthesize a minimal but structurally valid `.docx` document in-memory. Asserts the route succeeds and the Redis task correctly hits the mocked RQ queue with a 200 HTTP response.
5. **`test_status_not_found`**: Enforces error handling for `GET /status/{job_id}` routing. It forcefully mimics an RQ `NoSuchJobError` condition to confirm the API replies cleanly with a logical `"status": "not_found"` mapping rather than throwing a stack trace.
6. **`test_temp_not_found`**: Tests our Overleaf-oriented intermediate link retrieval `GET /temp/{job_id}` by mocking the Redis `get` command to miss, ensuring we send back a crisp HTTP 404 informing the user their download TTL expired.

## Mocking Logic Note
- Due to the complexities of containerizing tests consistently locally vs. remote environments, our test suite aggressively mocks interactions with `redis_conn` and `conversion_queue` using `unittest.mock.patch`. This guarantees the CI/CD pipeline and the CLI command `pytest` will run consistently without expecting live Docker services in the background.
