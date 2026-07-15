import logging
from pathlib import Path
from time import sleep

from wi1_bot.arr import Radarr, Sonarr

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
        for m in radarr.get_movies():
            movie_path = Path(m["path"])

            if new_path.is_relative_to(movie_path):
                # have to rescan the movie twice: Radarr/Radarr#7668
                radarr.rescan_movie(m["id"])
                sleep(5)
                radarr.rescan_movie(m["id"])
                break
    elif new_path.is_relative_to(sonarr_root):
        for s in sonarr.get_series():
            series_path = Path(s["path"])

            if new_path.is_relative_to(series_path):
                sonarr.rescan_series(s["id"])
                break
