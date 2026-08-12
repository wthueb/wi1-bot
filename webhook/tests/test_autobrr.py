from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient
from prometheus_client import REGISTRY
from structlog.contextvars import get_contextvars

import wi1_bot.webhook.autobrr as autobrr_mod
from wi1_bot.arr.release import ReleasePushRequest, ReleasePushResult
from wi1_bot.webhook import __version__
from wi1_bot.webhook.app import app
from wi1_bot.webhook.autobrr import ArrTarget


class CapturingLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, object]]] = []

    def info(self, event: str, **context: object) -> None:
        self._record("info", event, context)

    def debug(self, event: str, **context: object) -> None:
        self._record("debug", event, context)

    def warning(self, event: str, **context: object) -> None:
        self._record("warning", event, context)

    def _record(self, level: str, event: str, context: dict[str, object]) -> None:
        self.records.append((level, event, {**get_contextvars(), **context}))


@pytest.fixture
def client(db: None) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def arr_clients() -> Iterator[dict[str, MagicMock]]:
    clients = {
        "radarr": MagicMock(),
        "radarr4k": MagicMock(),
        "sonarr": MagicMock(),
        "sonarr4k": MagicMock(),
    }
    targets = (
        ArrTarget("radarr", "radarr", clients["radarr"]),
        ArrTarget("radarr4k", "radarr", clients["radarr4k"]),
        ArrTarget("sonarr", "sonarr", clients["sonarr"]),
        ArrTarget("sonarr4k", "sonarr", clients["sonarr4k"]),
    )
    with patch.object(autobrr_mod, "_targets", targets):
        yield clients


def _push_payload() -> dict[str, object]:
    return {
        "title": "The.Show.S01E01.1080p-GROUP",
        "infoUrl": "https://indexer.example/details/1",
        "downloadUrl": "https://indexer.example/download?passkey=secret",
        "size": 1234,
        "indexer": "tracker",
        "downloadProtocol": "torrent",
        "protocol": "torrent",
        "publishDate": "2026-08-11T12:00:00Z",
        "downloadClientId": 3,
        "downloadClient": "qbit",
        "indexerFlags": 5,
        "futureField": "preserved",
    }


def _approved() -> ReleasePushResult:
    return ReleasePushResult(
        approved=True,
        rejected=False,
        temporarilyRejected=False,
    )


def _rejected(
    *reasons: str,
    temporarily_rejected: bool = False,
) -> ReleasePushResult:
    return ReleasePushResult(
        approved=False,
        rejected=True,
        temporarilyRejected=temporarily_rejected,
        rejections=list(reasons),
    )


@pytest.mark.parametrize("kind", ["radarr", "sonarr"])
def test_system_status_supports_autobrr_connection_test(
    client: FlaskClient,
    kind: str,
) -> None:
    response = client.get(f"/autobrr/{kind}/api/v3/system/status")

    assert response.status_code == 200
    assert response.get_json() == {"version": __version__}


@pytest.mark.parametrize(
    ("kind", "method", "matching_targets", "other_targets"),
    [
        ("radarr", "get_movies", ("radarr", "radarr4k"), ("sonarr", "sonarr4k")),
        ("sonarr", "get_series", ("sonarr", "sonarr4k"), ("radarr", "radarr4k")),
    ],
)
def test_library_list_combines_only_requested_kind_and_exposes_minimal_fields(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
    kind: str,
    method: str,
    matching_targets: tuple[str, str],
    other_targets: tuple[str, str],
) -> None:
    primary_item: dict[str, object] = {
        "id": 1,
        "title": "Primary Title",
        "originalTitle": "Original Title",
        "alternateTitles": [{"title": "Alternate Title", "sourceType": "tmdb"}],
        "monitored": True,
        "path": "/private/media/primary",
        "tags": [10],
    }
    secondary_item: dict[str, object] = {
        "id": 1,
        "title": "4K Title",
        "alternateTitles": None,
        "monitored": False,
        "path": "/private/media/4k",
    }
    getattr(arr_clients[matching_targets[0]], method).return_value = [primary_item]
    getattr(arr_clients[matching_targets[1]], method).return_value = [secondary_item]

    response = client.get(f"/autobrr/{kind}/api/v3/{'movie' if kind == 'radarr' else 'series'}")

    assert response.status_code == 200
    expected_primary: dict[str, object] = {
        "title": "Primary Title",
        "alternateTitles": [{"title": "Alternate Title"}],
        "monitored": True,
    }
    if kind == "radarr":
        expected_primary["originalTitle"] = "Original Title"
    assert response.get_json() == [
        expected_primary,
        {
            "title": "4K Title",
            "alternateTitles": [],
            "monitored": False,
        },
    ]
    for target in matching_targets:
        getattr(arr_clients[target], method).assert_called_once_with()
    for target in other_targets:
        getattr(arr_clients[target], method).assert_not_called()
    assert "/private/media" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("kind", "method", "path"),
    [
        ("radarr", "get_movies", "/autobrr/radarr/api/v3/movie"),
        ("sonarr", "get_series", "/autobrr/sonarr/api/v3/series"),
    ],
)
def test_library_list_returns_empty_array_when_all_libraries_are_empty(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
    kind: str,
    method: str,
    path: str,
) -> None:
    for name in (kind, f"{kind}4k"):
        getattr(arr_clients[name], method).return_value = []

    response = client.get(path)

    assert response.status_code == 200
    assert response.get_json() == []


@pytest.mark.parametrize(
    ("path", "successful_target", "failed_target", "method"),
    [
        ("/autobrr/radarr/api/v3/movie", "radarr", "radarr4k", "get_movies"),
        ("/autobrr/sonarr/api/v3/series", "sonarr", "sonarr4k", "get_series"),
    ],
)
def test_library_list_failure_discards_partial_results(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
    path: str,
    successful_target: str,
    failed_target: str,
    method: str,
) -> None:
    getattr(arr_clients[successful_target], method).return_value = [
        {"title": "Partial Title", "alternateTitles": [], "monitored": True}
    ]
    getattr(arr_clients[failed_target], method).side_effect = RuntimeError("unavailable")

    response = client.get(path)

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "arr_list_failed",
        "failed_targets": [failed_target],
    }
    assert "Partial Title" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("path", "target", "method", "invalid_response"),
    [
        ("/autobrr/radarr/api/v3/movie", "radarr", "get_movies", {}),
        (
            "/autobrr/sonarr/api/v3/series",
            "sonarr",
            "get_series",
            [{"title": "Missing monitored state", "alternateTitles": []}],
        ),
    ],
)
def test_invalid_library_response_is_a_target_failure(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
    path: str,
    target: str,
    method: str,
    invalid_response: object,
) -> None:
    getattr(arr_clients[target], method).return_value = invalid_response
    getattr(arr_clients[f"{target}4k"], method).return_value = []

    response = client.get(path)

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "arr_list_failed",
        "failed_targets": [target],
    }


@pytest.mark.parametrize(
    "path",
    [
        "/autobrr/radarr/api/v3/movie",
        "/autobrr/sonarr/api/v3/series",
    ],
)
def test_missing_library_target_configuration_is_an_action_error(
    client: FlaskClient,
    path: str,
) -> None:
    with patch.object(autobrr_mod, "_targets", ()):
        response = client.get(path)

    assert response.status_code == 503
    assert response.get_json() == {"error": "no_targets_configured"}


@pytest.mark.parametrize(
    ("path", "pushed", "not_pushed"),
    [
        (
            "/autobrr/radarr/api/v3/release/push",
            ("radarr", "radarr4k"),
            ("sonarr", "sonarr4k"),
        ),
        (
            "/autobrr/sonarr/api/v3/release/push",
            ("sonarr", "sonarr4k"),
            ("radarr", "radarr4k"),
        ),
    ],
)
def test_any_approval_wins_and_pushes_only_to_requested_kind(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
    path: str,
    pushed: tuple[str, str],
    not_pushed: tuple[str, str],
) -> None:
    arr_clients[pushed[0]].push_release.return_value = [_approved()]
    arr_clients[pushed[1]].push_release.return_value = [_rejected("Existing file is preferred")]
    audit_logger = CapturingLogger()

    with patch.object(autobrr_mod, "logger", audit_logger):
        response = client.post(path, json=_push_payload())

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "approved": True,
            "rejected": False,
            "temporarilyRejected": False,
            "rejections": [],
        }
    ]
    expected_request = ReleasePushRequest.model_validate(_push_payload()).model_copy(
        update={"download_client_id": 0}
    )
    for name in pushed:
        arr_clients[name].push_release.assert_called_once_with(expected_request)
        assert "downloadClientId" not in expected_request.as_arr_payload()
    for name in not_pushed:
        arr_clients[name].push_release.assert_not_called()

    assert audit_logger.records[-1] == (
        "info",
        "autobrr release fan-out approved",
        {
            "arr_kind": path.split("/")[2],
            "release_title": "The.Show.S01E01.1080p-GROUP",
            "protocol": "torrent",
            "indexer": "tracker",
            "approved_targets": [pushed[0]],
            "rejected_targets": [pushed[1]],
            "failed_targets": [],
            "outcomes": {pushed[0]: ["approved"], pushed[1]: ["rejected"]},
        },
    )
    assert [level for level, _event, _context in audit_logger.records].count("info") == 1


def test_all_rejections_are_combined_and_secrets_are_redacted(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
) -> None:
    secret_url = str(_push_payload()["downloadUrl"])
    arr_clients["radarr"].push_release.return_value = [
        _rejected(
            f"Unable to use {secret_url}",
            temporarily_rejected=True,
        )
    ]
    arr_clients["radarr4k"].push_release.return_value = [_rejected(temporarily_rejected=True)]
    audit_logger = CapturingLogger()

    with patch.object(autobrr_mod, "logger", audit_logger):
        response = client.post("/autobrr/radarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "approved": False,
            "rejected": True,
            "temporarilyRejected": True,
            "rejections": [
                "radarr: ['Unable to use <redacted>']\n"
                "radarr4k: ['release rejected without a reason']"
            ],
        }
    ]
    assert "passkey=secret" not in response.get_data(as_text=True)
    assert "passkey=secret" not in repr(audit_logger.records)
    assert not any(level == "info" for level, _event, _context in audit_logger.records)
    assert audit_logger.records[-1][0:2] == (
        "debug",
        "autobrr release fan-out rejected",
    )


def test_mixed_permanent_and_temporary_rejections_are_not_temporary(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
) -> None:
    arr_clients["sonarr"].push_release.return_value = [
        _rejected("Delay profile", temporarily_rejected=True)
    ]
    arr_clients["sonarr4k"].push_release.return_value = [_rejected("Unknown Series")]

    response = client.post("/autobrr/sonarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 200
    assert response.get_json()[0]["temporarilyRejected"] is False


def test_rejections_are_grouped_by_target_for_autobrr_display(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
) -> None:
    arr_clients["sonarr"].push_release.return_value = [
        _rejected(
            "WEB-DL-2160p is not wanted in profile",
            "Existing file on disk is of equal or higher preference: WEBDL-1080p v1",
        )
    ]
    arr_clients["sonarr4k"].push_release.return_value = [_rejected("Episode is not monitored")]

    response = client.post("/autobrr/sonarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 200
    assert response.get_json()[0]["rejections"] == [
        "sonarr: ['WEB-DL-2160p is not wanted in profile', "
        "'Existing file on disk is of equal or higher preference: WEBDL-1080p v1']\n"
        "sonarr4k: ['Episode is not monitored']"
    ]


def test_approval_wins_even_when_another_target_fails(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
) -> None:
    arr_clients["radarr"].push_release.return_value = [_approved()]
    arr_clients["radarr4k"].push_release.side_effect = RuntimeError(
        "https://indexer.example/download?passkey=secret"
    )
    audit_logger = CapturingLogger()

    with patch.object(autobrr_mod, "logger", audit_logger):
        response = client.post("/autobrr/radarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 200
    assert response.get_json()[0]["approved"] is True
    assert audit_logger.records[-1][2]["failed_targets"] == ["radarr4k"]
    assert any(
        level == "warning" and event == "autobrr release push failed"
        for level, event, _context in audit_logger.records
    )
    assert [level for level, _event, _context in audit_logger.records].count("info") == 1
    assert "passkey=secret" not in repr(audit_logger.records)


def test_failure_without_an_approval_returns_gateway_error(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
) -> None:
    arr_clients["sonarr"].push_release.return_value = [_rejected("Unknown Series")]
    arr_clients["sonarr4k"].push_release.side_effect = RuntimeError("unavailable")

    response = client.post("/autobrr/sonarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 502
    assert response.get_json() == {
        "error": "arr_push_failed",
        "failed_targets": ["sonarr4k"],
    }


@pytest.mark.parametrize("invalid_result", [[], [object()]])
def test_empty_or_invalid_downstream_result_is_a_target_failure(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
    invalid_result: list[object],
) -> None:
    arr_clients["radarr"].push_release.return_value = [_rejected("Not wanted")]
    arr_clients["radarr4k"].push_release.return_value = invalid_result

    response = client.post("/autobrr/radarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 502
    assert response.get_json()["failed_targets"] == ["radarr4k"]


def test_only_first_downstream_result_controls_the_native_outcome(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
) -> None:
    arr_clients["radarr"].push_release.return_value = [
        _rejected("First result rejected"),
        _approved(),
    ]
    arr_clients["radarr4k"].push_release.return_value = [_rejected("Not wanted")]

    response = client.post("/autobrr/radarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 200
    assert response.get_json()[0] == {
        "approved": False,
        "rejected": True,
        "temporarilyRejected": False,
        "rejections": [
            "radarr: ['First result rejected']\nradarr4k: ['Not wanted']",
        ],
    }


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {**_push_payload(), "title": ""},
        {**_push_payload(), "downloadUrl": None},
        {**_push_payload(), "protocol": "invalid"},
    ],
)
def test_invalid_payload_is_an_action_error(client: FlaskClient, payload: object) -> None:
    response = client.post("/autobrr/sonarr/api/v3/release/push", json=payload)

    assert response.status_code == 422
    assert response.get_json() == {"error": "invalid_request"}


def test_missing_target_configuration_is_an_action_error(client: FlaskClient) -> None:
    with patch.object(autobrr_mod, "_targets", ()):
        response = client.post("/autobrr/radarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 503
    assert response.get_json() == {"error": "no_targets_configured"}


def test_only_native_arr_routes_are_registered() -> None:
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    assert {
        "/autobrr/radarr/api/v3/system/status",
        "/autobrr/radarr/api/v3/movie",
        "/autobrr/radarr/api/v3/release/push",
        "/autobrr/sonarr/api/v3/system/status",
        "/autobrr/sonarr/api/v3/series",
        "/autobrr/sonarr/api/v3/release/push",
    } <= rules
    assert {
        "/autobrr/radarr/check",
        "/autobrr/radarr/push",
        "/autobrr/sonarr/check",
        "/autobrr/sonarr/push",
    }.isdisjoint(rules)


def test_autobrr_route_uses_normalized_http_metrics(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
) -> None:
    arr_clients["radarr"].push_release.return_value = [_rejected("Not wanted")]
    arr_clients["radarr4k"].push_release.return_value = [_rejected("Not wanted")]
    labels = {
        "method": "POST",
        "route": "/autobrr/radarr/api/v3/release/push",
        "status_code": "200",
    }
    before = REGISTRY.get_sample_value("wi1_bot_webhook_http_requests_total", labels) or 0

    response = client.post("/autobrr/radarr/api/v3/release/push", json=_push_payload())

    assert response.status_code == 200
    assert REGISTRY.get_sample_value("wi1_bot_webhook_http_requests_total", labels) == before + 1


def test_autobrr_library_route_uses_normalized_http_metrics(
    client: FlaskClient,
    arr_clients: dict[str, MagicMock],
) -> None:
    arr_clients["sonarr"].get_series.return_value = []
    arr_clients["sonarr4k"].get_series.return_value = []
    labels = {
        "method": "GET",
        "route": "/autobrr/sonarr/api/v3/series",
        "status_code": "200",
    }
    before = REGISTRY.get_sample_value("wi1_bot_webhook_http_requests_total", labels) or 0

    response = client.get("/autobrr/sonarr/api/v3/series")

    assert response.status_code == 200
    assert REGISTRY.get_sample_value("wi1_bot_webhook_http_requests_total", labels) == before + 1
