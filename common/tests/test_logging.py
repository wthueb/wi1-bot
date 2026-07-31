import ast
import re
from pathlib import Path

import structlog
from pytest import CaptureFixture
from structlog.contextvars import bound_contextvars, clear_contextvars, get_contextvars

from wi1_bot.common.logging import setup_logging

LOG_METHODS = {"critical", "debug", "error", "exception", "info", "warning"}
LOGGER_NAMES = {"log", "logger"}


def test_logfmt_output_matches_existing_format(capsys: CaptureFixture[str]) -> None:
    setup_logging("logfmt")
    clear_contextvars()

    with bound_contextvars(job_id=7, worker_id="worker one"):
        structlog.get_logger("wi1_bot.sample").info(
            "transcode job claimed",
            path="/media/A Movie.mkv",
        )

    assert get_contextvars() == {}

    output = capsys.readouterr().out
    assert re.fullmatch(
        r'ts="\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}" '
        r"level=INFO logger=wi1_bot\.sample "
        r"src=test_logfmt_output_matches_existing_format:\d+ "
        r'msg="transcode job claimed" path="/media/A Movie\.mkv" '
        r'job_id=7 worker_id="worker one"\n',
        output,
    )


def test_application_log_messages_are_static() -> None:
    repository_dir = Path(__file__).parents[2]
    dynamic_messages: list[str] = []

    for path in sorted(repository_dir.glob("*/src/wi1_bot/**/*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and (
                    (isinstance(node.func.value, ast.Name) and node.func.value.id in LOGGER_NAMES)
                    or (
                        isinstance(node.func.value, ast.Attribute)
                        and node.func.value.attr in LOGGER_NAMES
                    )
                )
                and node.func.attr in LOG_METHODS
                and (
                    not node.args
                    or not isinstance(node.args[0], ast.Constant)
                    or not isinstance(node.args[0].value, str)
                )
            ):
                dynamic_messages.append(f"{path.relative_to(repository_dir)}:{node.lineno}")

    assert dynamic_messages == []
