import logging
from pathlib import Path
from time import perf_counter, sleep

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.webhook.metrics import RESCAN_DURATION, RESCAN_OPERATIONS

logger = logging.getLogger(__name__)


def rescan_content(
    radarr: Radarr,
    sonarr: Sonarr,
    radarr_root: Path,
    sonarr_root: Path,
    new_path: Path,
) -> None:
    """Tell Radarr/Sonarr to rescan the folder a freshly transcoded file landed in.

    All paths are Arr-native (as Radarr/Sonarr report them), so no remote-path
    mapping is needed here — the transcoder does its own mapping and reports back the
    filename, from which the webhook rebuilds the Arr-native ``new_path``.
    """
    if new_path.is_relative_to(radarr_root):
        target = "radarr"
    elif new_path.is_relative_to(sonarr_root):
        target = "sonarr"
    else:
        target = "unknown"

    started_at = perf_counter()
    try:
        found = False
        if target == "radarr":
            for movie in radarr.get_movies():
                movie_path = Path(movie["path"])

                if new_path.is_relative_to(movie_path):
                    # have to rescan the movie twice: Radarr/Radarr#7668
                    radarr.rescan_movie(movie["id"])
                    sleep(5)
                    radarr.rescan_movie(movie["id"])
                    found = True
                    break
        elif target == "sonarr":
            for series in sonarr.get_series():
                series_path = Path(series["path"])

                if new_path.is_relative_to(series_path):
                    sonarr.rescan_series(series["id"])
                    found = True
                    break

        outcome = "success" if found else "not_found"
        RESCAN_OPERATIONS.labels(target=target, outcome=outcome).inc()
    except Exception:
        RESCAN_OPERATIONS.labels(target=target, outcome="error").inc()
        raise
    finally:
        RESCAN_DURATION.labels(target=target).observe(perf_counter() - started_at)
