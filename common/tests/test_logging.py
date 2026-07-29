import re

import structlog
from pytest import CaptureFixture
from structlog.contextvars import bound_contextvars, clear_contextvars, get_contextvars

from wi1_bot.common.logging import setup_logging


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
