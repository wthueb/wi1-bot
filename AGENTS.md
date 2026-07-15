# Agent Guidelines for wi1-bot

## Build/Lint/Test Commands
- Run tests: `uv run pytest` or `pytest` (if dev dependencies installed)
- Run single test: `uv run pytest <pkg>/tests/test_file.py::TestClass::test_method` or `uv run pytest -k test_name`
- This repo is a uv workspace: `common`, `arr`, `wi1-bot`, `webhook`, `transcoder`, all sharing the `wi1_bot` namespace (no `wi1_bot/__init__.py` anywhere)
- Lint: `ruff check .` (auto-fix: `ruff check --fix .`)
- Format: `ruff format .`
- Type check: `ty check`
- Pre-commit hooks: `pre-commit run --all-files`

## Code Style
- **Python version**: >=3.12
- **Line length**: 100 characters
- **Type hints**: Type-checked with `ty` (`error-on-warning = true`). Always use type annotations.
- **Imports**: Sorted and organized (ruff's `I` rules). Use absolute imports from `wi1_bot`.
- **Formatting**: Follow ruff defaults (E, F, I rules)
- **Error handling**: Use pattern matching for errors (see `on_command_error` in bot.py)
- **Assertions**: Use `assert isinstance()` when working with pyarr API responses to satisfy type checker
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Docstrings**: Not heavily used in this codebase; prefer clear code over extensive docs
- **Async**: Discord bot commands use async/await patterns with `async with ctx.typing():`
