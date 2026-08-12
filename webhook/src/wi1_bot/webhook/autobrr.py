from dataclasses import dataclass
from typing import Literal, cast

import structlog
from flask import Blueprint, request
from pydantic import ValidationError
from structlog.contextvars import bound_contextvars

from wi1_bot.arr import Radarr, ReleasePushRequest, ReleasePushResult, Sonarr
from wi1_bot.webhook import __version__

logger = structlog.get_logger(__name__)

blueprint = Blueprint("autobrr", __name__, url_prefix="/autobrr")

TargetName = Literal["radarr", "radarr4k", "sonarr", "sonarr4k"]
TargetKind = Literal["radarr", "sonarr"]
PushResponse = tuple[list[dict[str, bool | list[str]]], int] | tuple[dict[str, object], int]
ListItem = dict[str, object]
ListResponse = tuple[list[ListItem], int] | tuple[dict[str, object], int]


@dataclass(frozen=True)
class ArrTarget:
    name: TargetName
    kind: TargetKind
    client: Radarr | Sonarr


_targets: tuple[ArrTarget, ...] = ()


def configure_targets(targets: list[ArrTarget]) -> None:
    global _targets
    _targets = tuple(targets)


def _targets_for_kind(kind: TargetKind) -> tuple[ArrTarget, ...]:
    return tuple(target for target in _targets if target.kind == kind)


def _push_outcome(response: ReleasePushResult) -> str:
    if response.temporarily_rejected:
        return "temporarily_rejected"
    if response.rejected:
        return "rejected"
    return "approved"


def _sanitize_rejections(rejections: list[str], release: ReleasePushRequest) -> list[str]:
    sanitized = rejections.copy()
    for secret in release.sensitive_urls:
        sanitized = [reason.replace(secret, "<redacted>") for reason in sanitized]
    return sanitized


def _target_rejection(
    target: ArrTarget,
    result: ReleasePushResult,
    release: ReleasePushRequest,
) -> str:
    reasons = _sanitize_rejections(result.rejections, release)
    if not reasons:
        reasons = ["release rejected without a reason"]
    return f"{target.name}: {reasons!r}"


def _system_status() -> tuple[dict[str, str], int]:
    return {"version": __version__}, 200


def _error_response(
    error: str,
    status_code: int,
    *,
    failed_targets: list[TargetName] | None = None,
) -> tuple[dict[str, object], int]:
    body: dict[str, object] = {"error": error}
    if failed_targets is not None:
        body["failed_targets"] = failed_targets
    return body, status_code


def _list_item(kind: TargetKind, item: object) -> ListItem:
    if not isinstance(item, dict):
        raise TypeError("Arr library item must be an object")

    title = item.get("title")
    monitored = item.get("monitored")
    alternate_titles = item.get("alternateTitles", [])
    if alternate_titles is None:
        alternate_titles = []
    if not isinstance(title, str) or not title:
        raise TypeError("Arr library item title must be a non-empty string")
    if not isinstance(monitored, bool):
        raise TypeError("Arr library item monitored state must be a boolean")
    if not isinstance(alternate_titles, list):
        raise TypeError("Arr library item alternate titles must be a list")

    normalized_alternate_titles: list[dict[str, str]] = []
    for alternate_title in alternate_titles:
        if not isinstance(alternate_title, dict):
            raise TypeError("Arr alternate title must be an object")
        alternate_title_value = alternate_title.get("title")
        if not isinstance(alternate_title_value, str):
            raise TypeError("Arr alternate title must be a string")
        normalized_alternate_titles.append({"title": alternate_title_value})

    normalized: ListItem = {
        "title": title,
        "alternateTitles": normalized_alternate_titles,
        "monitored": monitored,
    }
    if kind == "radarr":
        original_title = item.get("originalTitle")
        if original_title is not None:
            if not isinstance(original_title, str):
                raise TypeError("Radarr original title must be a string")
            normalized["originalTitle"] = original_title

    return normalized


def _list(kind: TargetKind) -> ListResponse:
    with bound_contextvars(arr_kind=kind):
        targets = _targets_for_kind(kind)
        if not targets:
            logger.warning("autobrr library list refresh failed", reason="no_targets_configured")
            return _error_response("no_targets_configured", 503)

        items: list[ListItem] = []
        failed_targets: list[TargetName] = []

        for target in targets:
            with bound_contextvars(target=target.name):
                logger.info("autobrr library list target fetch started")
                try:
                    if kind == "radarr":
                        target_items = cast(Radarr, target.client).get_movies()
                    else:
                        target_items = cast(Sonarr, target.client).get_series()
                    if not isinstance(target_items, list):
                        raise TypeError("Arr library response must be a list")
                    normalized_items = [_list_item(kind, item) for item in target_items]
                except Exception as exc:
                    failed_targets.append(target.name)
                    logger.warning(
                        "autobrr library list target fetch failed",
                        error_type=type(exc).__name__,
                    )
                    continue

                items.extend(normalized_items)
                logger.info(
                    "autobrr library list target fetch completed",
                    item_count=len(normalized_items),
                )

        if failed_targets:
            logger.warning(
                "autobrr library list refresh failed",
                failed_targets=failed_targets,
            )
            return _error_response("arr_list_failed", 502, failed_targets=failed_targets)

        logger.info(
            "autobrr library list refresh completed",
            target_count=len(targets),
            item_count=len(items),
        )
        return items, 200


@blueprint.route("/radarr/api/v3/system/status", methods=["GET"])
def autobrr_radarr_status() -> tuple[dict[str, str], int]:
    return _system_status()


@blueprint.route("/sonarr/api/v3/system/status", methods=["GET"])
def autobrr_sonarr_status() -> tuple[dict[str, str], int]:
    return _system_status()


@blueprint.route("/radarr/api/v3/movie", methods=["GET"])
def autobrr_radarr_movies() -> ListResponse:
    return _list("radarr")


@blueprint.route("/sonarr/api/v3/series", methods=["GET"])
def autobrr_sonarr_series() -> ListResponse:
    return _list("sonarr")


def _push(kind: TargetKind) -> PushResponse:
    try:
        release = ReleasePushRequest.model_validate(request.get_json(silent=True))
    except ValidationError:
        logger.warning("autobrr release push failed", arr_kind=kind, reason="invalid_request")
        return _error_response("invalid_request", 422)

    with bound_contextvars(
        arr_kind=kind,
        release_title=release.title,
        protocol=release.protocol,
        indexer=release.indexer,
    ):
        targets = _targets_for_kind(kind)
        if not targets:
            logger.warning("autobrr release push failed", reason="no_targets_configured")
            return _error_response("no_targets_configured", 503)

        # Download-client IDs are local to one Arr instance. The proxy has no
        # per-target ID mapping, so let each fan-out target select its own client.
        target_release = release.model_copy(update={"download_client_id": 0})

        approved_targets: list[TargetName] = []
        rejected_results: list[tuple[ArrTarget, ReleasePushResult]] = []
        failed_targets: list[TargetName] = []
        outcomes: dict[TargetName, list[str]] = {}

        for target in targets:
            with bound_contextvars(target=target.name):
                logger.debug("autobrr release push started")
                try:
                    responses = target.client.push_release(target_release)
                    if not responses:
                        raise ValueError("release push returned no results")
                    if not all(isinstance(response, ReleasePushResult) for response in responses):
                        raise TypeError("release push returned an invalid result")
                except Exception as exc:
                    failed_targets.append(target.name)
                    logger.warning(
                        "autobrr release push failed",
                        error_type=type(exc).__name__,
                    )
                    continue

                target_outcomes: list[str] = []
                for result_index, response in enumerate(responses):
                    outcome = _push_outcome(response)
                    target_outcomes.append(outcome)
                    logger.debug(
                        "autobrr release push result received",
                        result_index=result_index,
                        outcome=outcome,
                        approved=response.approved,
                        rejected=response.rejected,
                        temporarily_rejected=response.temporarily_rejected,
                        rejection_reasons=_sanitize_rejections(response.rejections, release),
                    )
                outcomes[target.name] = target_outcomes

                # Autobrr's native Radarr/Sonarr clients inspect only the first item.
                first_response = responses[0]
                if first_response.approved:
                    approved_targets.append(target.name)
                else:
                    rejected_results.append((target, first_response))

        if approved_targets:
            result = ReleasePushResult(
                approved=True,
                rejected=False,
                temporarilyRejected=False,
            )
            logger.info(
                "autobrr release fan-out approved",
                approved_targets=approved_targets,
                rejected_targets=[target.name for target, _result in rejected_results],
                failed_targets=failed_targets,
                outcomes=outcomes,
            )
            return [result.as_api_dict()], 200

        if failed_targets:
            logger.warning(
                "autobrr release fan-out failed",
                failed_targets=failed_targets,
                rejected_targets=[target.name for target, _result in rejected_results],
                outcomes=outcomes,
            )
            return _error_response("arr_push_failed", 502, failed_targets=failed_targets)

        rejection_reasons = [
            "\n".join(
                _target_rejection(target, response, release)
                for target, response in rejected_results
            )
        ]
        result = ReleasePushResult(
            approved=False,
            rejected=True,
            temporarilyRejected=all(
                response.temporarily_rejected for _target, response in rejected_results
            ),
            rejections=rejection_reasons,
        )
        logger.debug(
            "autobrr release fan-out rejected",
            rejected_targets=[target.name for target, _result in rejected_results],
            rejection_reasons=rejection_reasons,
            outcomes=outcomes,
        )
        return [result.as_api_dict()], 200


@blueprint.route("/radarr/api/v3/release/push", methods=["POST"])
def autobrr_radarr_push() -> PushResponse:
    return _push("radarr")


@blueprint.route("/sonarr/api/v3/release/push", methods=["POST"])
def autobrr_sonarr_push() -> PushResponse:
    return _push("sonarr")
