from unittest.mock import MagicMock, patch

import wi1_bot.transcoder.worker as worker_mod
from wi1_bot.transcoder.transcoder import JobResult


def _posts(mock_requests: MagicMock) -> list[tuple[str, dict[str, object]]]:
    return [(c.args[0], c.kwargs["json"]) for c in mock_requests.post.call_args_list]


def test_report_complete_posts_filename() -> None:
    with patch.object(worker_mod, "requests") as mock_requests:
        worker_mod._report("http://wh", 5, JobResult("complete", filename="a-TRANSCODED.mkv"))

    assert _posts(mock_requests) == [
        ("http://wh/jobs/5/complete", {"filename": "a-TRANSCODED.mkv"}),
    ]


def test_report_skip_completes_without_filename() -> None:
    with patch.object(worker_mod, "requests") as mock_requests:
        worker_mod._report("http://wh", 5, JobResult("skip"))

    assert _posts(mock_requests) == [("http://wh/jobs/5/complete", {})]


def test_report_retry_fails_with_retry_true() -> None:
    with patch.object(worker_mod, "requests") as mock_requests:
        worker_mod._report("http://wh", 5, JobResult("retry", reason="interrupted"))

    assert _posts(mock_requests) == [
        ("http://wh/jobs/5/fail", {"retry": True, "reason": "interrupted"}),
    ]


def test_report_fail_includes_log_tail() -> None:
    with patch.object(worker_mod, "requests") as mock_requests:
        worker_mod._report("http://wh", 5, JobResult("fail", reason="boom", log_tail="ffmpeg died"))

    assert _posts(mock_requests) == [
        ("http://wh/jobs/5/fail", {"retry": False, "reason": "boom", "log_tail": "ffmpeg died"}),
    ]


def test_report_swallows_network_errors() -> None:
    with patch.object(worker_mod, "requests") as mock_requests:
        mock_requests.RequestException = Exception
        mock_requests.post.side_effect = Exception("connection refused")
        # a failed report must not raise (the lease will expire and re-dispatch)
        worker_mod._report("http://wh", 5, JobResult("complete", filename="a.mkv"))
