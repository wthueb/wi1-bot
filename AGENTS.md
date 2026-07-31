# Agent Guidelines for wi1-bot

## Repository overview

wi1-bot is a Python 3.12+ `uv` workspace with five distributions that share the
`wi1_bot` PEP 420 namespace:

| Directory | Distribution | Import package | Responsibility |
| --- | --- | --- | --- |
| `common/` | `common` | `wi1_bot.common` | Shared configuration, logging, and Pushover helpers |
| `arr/` | `arr` | `wi1_bot.arr` | Typed Radarr/Sonarr wrappers around `pyarr` |
| `bot/` | `wi1-bot` | `wi1_bot.bot` | Discord bot service |
| `webhook/` | `webhook` | `wi1_bot.webhook` | Arr webhook, metrics, SQLite queue, and worker API |
| `transcoder/` | `transcoder` | `wi1_bot.transcoder` | Replicable ffmpeg worker |

`common` and `arr` are libraries. The bot, webhook, and transcoder are independently
deployable services with separate console entry points, configuration templates, and
Docker images.

Do not add `wi1_bot/__init__.py`: the top-level namespace intentionally spans multiple
workspace distributions. Each actual subpackage, such as `wi1_bot.webhook`, does have
its own `__init__.py`. Use absolute imports rooted at `wi1_bot`.

The transcode flow is:

1. Radarr/Sonarr sends a completed-download event to the webhook.
2. The webhook stores an Arr-native path in its SQLite queue.
3. A transcoder claims a leased job over HTTP and maps the remote path to local storage.
4. The worker heartbeats while ffmpeg runs, then reports completion, retry, skip, or
   terminal failure.
5. The webhook rescans the resulting path in Radarr/Sonarr.

Preserve this service boundary: workers communicate with the webhook API and must not
access the queue database directly.

## Environment and dependencies

- Use `uv` from the repository root for workspace operations.
- Install the exact locked environment with `uv sync --locked`.
- When intentionally changing dependencies, update the appropriate package
  `pyproject.toml` and `uv.lock` together.
- Runtime dependencies belong in the relevant workspace package, not automatically in
  the root development dependency group.
- Versions are derived dynamically from Git metadata with `uv-dynamic-versioning`; do
  not hard-code package versions.
- Preserve Python 3.12 compatibility even when developing with a newer interpreter.

Configuration is modeled with Pydantic and pydantic-settings. Service config objects are
created at module import time, so tests and scripts must establish required environment
or configuration before importing modules that load `config`.

Settings load in this order: explicit initializer values, `WB_` environment variables,
then YAML. Nested environment overrides use `__`, for example
`WB_WORKER__WEBHOOK_URL`. `WB_CONFIG_PATH` selects a config file, `WB_LOG_DIR` selects
the log directory, and `WB_DB_PATH` selects the webhook SQLite database.

Keep real credentials out of the repository. Update the service
`config.yaml.template` files when adding user-facing settings, and add validation and
tests with the corresponding Pydantic model.

## Required CI checks

CI installs with `uv sync --locked`, then runs these checks in order:

```sh
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
```

Run all four before considering a code change complete. `ty` is configured with
`error-on-warning = true`, so warnings fail CI.

Useful local commands:

```sh
# Apply formatting
uv run ruff format .

# Apply safe lint fixes, then report anything remaining
uv run ruff check --fix .

# Run the repository's local pre-commit hooks
uv run pre-commit run --all-files

# Run one file, one test, or tests matching a name
uv run pytest webhook/tests/test_queue.py
uv run pytest webhook/tests/test_queue.py::test_name
uv run pytest -k test_name
```

The pre-commit hooks run Ruff with fixes, Ruff formatting, and `ty`; they do not run
pytest. Run pytest separately.

After the Python checks pass, CI builds linux/amd64 and linux/arm64 images from
`Dockerfile.bot`, `Dockerfile.webhook`, and `Dockerfile.transcoder`. If a change affects
packaging, entry points, native/runtime dependencies, or Dockerfiles, also validate the
affected image locally when practical.

## Python style and typing

- Ruff enforces `E`, `F`, and `I` rules with a 100-character line length.
- Add precise annotations to functions, methods, attributes, fixtures, and non-obvious
  local values. Avoid broad `Any` unless an untyped external boundary requires it.
- Prefer small typed models and explicit validation at external boundaries.
- Use `snake_case` for functions and variables and `PascalCase` for classes.
- Prefer clear code over explanatory docstrings; document behavior whose rationale,
  lifecycle, concurrency, or external contract is not obvious.
- Keep imports sorted and use `wi1_bot...` absolute imports.
- Do not add blanket type suppressions. Narrow untyped third-party results using
  validation or `assert isinstance(...)`; this pattern is especially important for
  `pyarr` responses.
- Preserve existing async Discord command patterns, including `async`/`await` and
  `async with ctx.typing()` around potentially slow command work.
- Handle expected error variants explicitly. Pattern matching is preferred where it
  makes variants clearer, as in the Discord command error handler.

## Structured logging: strict rules

Logging uses `structlog`. Every log message must be a static string literal. Never put
runtime data into the event message with an f-string, interpolation, concatenation, a
dynamically selected string, or positional formatting arguments.

Every runtime value that should appear in a log record must be passed as structured
context, never embedded in the message. For a value used by only one log event, pass it
as a keyword argument on the log call:

```python
logger.info(
    "transcode job dispatched",
    filename=path.name,
    attempt=attempt,
)
```

When multiple log events need the same context, bind it once with a narrowly scoped
`bound_contextvars(...)` block instead of repeating keyword arguments:

```python
from structlog.contextvars import bound_contextvars

with bound_contextvars(
    job_id=job_id,
    worker_id=worker_id,
):
    logger.info("transcode job dispatched")
    logger.debug("transcode heartbeat accepted")
```

Do not write:

```python
logger.info(f"dispatched {path.name} to {worker_id}")
```

Additional logging requirements:

- Use log-call keyword fields for context specific to a single event.
- Bind shared context at the narrowest useful scope and allow `bound_contextvars` to
  restore the previous context automatically.
- Clear context at reused execution boundaries, such as the start of each Flask
  request, so values cannot leak between requests or jobs.
- Bind stable correlation data once around the whole operation when appropriate.
- Use `exc_info=True` when a traceback is useful; keep the accompanying event message
  static.
- Do not bind secrets, tokens, API keys, credentials, or unnecessarily large payloads.
- Add or update logging tests when changing processors, field normalization, or
  rendering. `common/tests/test_logging.py` enforces static application log messages.

`setup_logging` supports `logfmt` and JSON output. It merges contextvars and normalizes
the standard fields, including uppercase levels and source callsites. Preserve log field
semantics and compatibility unless a deliberate logging-format change is requested.

## Tests

- Put tests in the package they cover: `common/tests`, `arr/tests`, `bot/tests`,
  `webhook/tests`, or `transcoder/tests`.
- Add regression tests with every behavior change or bug fix.
- Prefer focused unit tests while iterating, then run the complete CI command set.
- Mock network calls and external services in unit tests. Do not require live Discord,
  TMDB, Pushover, Radarr, or Sonarr credentials.
- Tests involving ffmpeg may be conditionally skipped when ffmpeg is unavailable; keep
  non-ffmpeg logic independently testable.
- Webhook database tests must use an isolated temporary SQLite path and dispose/reset
  the cached engine after the test.
- Avoid tests whose outcome depends on wall-clock timing when the clock or lease values
  can be controlled directly.

## Webhook, queue, and database changes

- The webhook owns the SQLite database and runs Alembic migrations during startup.
- Change persisted schema through a new migration in
  `webhook/src/wi1_bot/webhook/migrations/versions/`; do not rely only on SQLAlchemy
  model changes.
- Keep `TranscodeItem` model changes, migrations, API serialization, queue behavior,
  metrics, and tests synchronized.
- Queue claims are serialized within the single webhook process and protected across
  worker failures by expiring leases. Preserve owner checks on heartbeats and the
  retry/terminal-failure semantics.
- SQLite stores the queue's timestamps as naive UTC. Keep timestamp creation and
  comparisons consistent with that convention.
- When changing routes or queue state transitions, update both endpoint tests and the
  lower-level queue tests.
- Prometheus label values must remain bounded. Never use user-controlled IDs, paths,
  filenames, exception text, or other high-cardinality values as metric labels.

## Service and deployment changes

- Console entry points are declared in each service's `pyproject.toml`; keep scripts,
  Docker entry points, and package names aligned.
- The transcoder image supplies ffmpeg and may use GPU acceleration. Do not assume
  ffmpeg or a GPU exists in ordinary unit-test environments.
- Arr paths and worker-local media paths can differ. Preserve remote path mapping and
  do not assume the webhook can see the worker's filesystem layout.
- The webhook is served by Waitress with a thread pool. Treat mutable process-global
  state as shared across request threads.
- If adding or changing service configuration, update its Pydantic model, config
  template, Compose environment/volume wiring when applicable, and tests.

## Change discipline

- Keep changes scoped to the requested behavior and preserve unrelated worktree edits.
- Do not commit generated caches, local databases, logs, media fixtures, credentials,
  or personal config files.
- Update README or templates when a public command, endpoint, configuration field,
  operational requirement, or deployment workflow changes.
- A change is complete only when its focused tests and all four CI checks pass, with
  additional Docker validation when the affected surface warrants it.
