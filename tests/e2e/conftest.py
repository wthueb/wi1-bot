"""Fixtures for the end-to-end transcoding-pipeline tests.

Brings up seeded Radarr + Sonarr instances, the webhook, and a transcoder worker via
pytest-docker (see ``compose.yaml``), and exposes real ``Radarr``/``Sonarr`` clients
pointed at the containers. The suite talks to real services over HTTP, so it deliberately
overrides the repo-root ``mock_arr_clients`` fixture that patches the pyarr clients.

On a test failure, the last lines of each service's container logs are printed (see
``_dump_logs_on_failure``).
"""

import os
import shutil
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import requests

from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Sonarr

# must match tests/e2e/config/webhook.yaml and the seeds' config.xml
API_KEY = "0123456789abcdef0123456789abcdef"
RADARR_SERVICE = "wi1-bot-radarr"
SONARR_SERVICE = "wi1-bot-sonarr"
WEBHOOK_SERVICE = "wi1-bot-webhook"
TRANSCODER_SERVICE = "wi1-bot-transcoder"
RELEASE_SERVER_SERVICE = "e2e-release-server"
_SERVICES = [
    RADARR_SERVICE,
    SONARR_SERVICE,
    WEBHOOK_SERVICE,
    TRANSCODER_SERVICE,
    RELEASE_SERVER_SERVICE,
]
LOG_TAIL = 40  # lines of each service's logs to print on failure

MOVIE_TMDB_ID = 10378  # Big Buck Bunny (2008), a public-domain film in TMDB
SERIES_TITLE = "Over the Garden Wall"  # keep in sync with regenerate_sonarr.py

_THIS_DIR = Path(__file__).parent
_REPO_ROOT = _THIS_DIR.parents[1]
_SEED_RADARR = _THIS_DIR / "seed" / "radarr"
_SEED_SONARR = _THIS_DIR / "seed" / "sonarr"
# a committed blacked-out clip (real stream layout, black video, muted audio)
_BLACKED_OUT_SRC = _REPO_ROOT / "transcoder" / "tests" / "files" / "none_ita_eng_audio.mkv"
FFMPEG_IMAGE = "lscr.io/linuxserver/ffmpeg:latest"

# The clip is looped (stream copy, instant) to clear each *arr's sample detection, which
# rejects files far shorter than the library item's runtime. ~3 min beats Big Buck Bunny
# (~10 min); the episode clip must exceed an Over the Garden Wall episode (~11 min).
_MOVIE_LOOPS = 35  # ~3 min
_EPISODE_LOOPS = 179  # ~15 min

# downloads named so each *arr's filename parser matches the seeded library item on scan
_MOVIE_DOWNLOAD_REL = Path("downloads/Big Buck Bunny (2008)/Big Buck Bunny (2008) Bluray-1080p.mkv")
_EPISODE_DOWNLOAD_REL = Path(f"tv/{SERIES_TITLE}/{SERIES_TITLE} - S01E01 Bluray-1080p.mkv")
_CF_HIGH_REL = Path(
    f"custom-format/high/{SERIES_TITLE}/{SERIES_TITLE} - S01E02 Bluray-1080p E2EHIGH.mkv"
)
_CF_LOW_REL = Path(f"custom-format/low/{SERIES_TITLE}.S01E02.Bluray-1080p.E2ELOW.mkv")
# scan paths INSIDE the containers (E2E_FIXTURES_DIR is mounted at /fixtures)
MOVIE_SCAN_PATH = "/fixtures/downloads/Big Buck Bunny (2008)"
SERIES_SCAN_PATH = f"/fixtures/tv/{SERIES_TITLE}"
CF_HIGH_SCAN_PATH = f"/fixtures/custom-format/high/{SERIES_TITLE}"
CF_LOW_SOURCE_PATH = f"/fixtures/{_CF_LOW_REL}"


@pytest.fixture(autouse=True)
def mock_arr_clients() -> Generator[None, None, None]:
    # Override the repo-root autouse fixture (conftest.py) that patches
    # RadarrClient/SonarrClient. The e2e suite makes real API calls, so this is a no-op.
    yield


def _loop_clip(work: Path, out_name: str, loops: int) -> None:
    """Loop the committed clip to ``out_name`` in ``work`` (stream copy) via a throwaway
    ffmpeg container, so the host needs no local ffmpeg."""
    subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{_BLACKED_OUT_SRC.parent}:/src:ro",
            "-v", f"{work}:/out",
            FFMPEG_IMAGE,
            "-hide_banner", "-y",
            "-stream_loop", str(loops),
            "-i", f"/src/{_BLACKED_OUT_SRC.name}",
            "-c", "copy",
            f"/out/{out_name}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )  # fmt: skip


@pytest.fixture(scope="session")
def e2e_env() -> Generator[dict[str, str], None, None]:
    """Prepare the per-run seed copies and the blacked-out downloads, and export the paths
    the compose file interpolates. Runs before the stack is brought up."""
    for seed in (_SEED_RADARR, _SEED_SONARR):
        if not (seed / f"{seed.name}.db").exists():
            pytest.skip(
                f"seed missing at {seed}. Generate the seeds with "
                "`python tests/e2e/seed/regenerate_radarr.py` and "
                "`python tests/e2e/seed/regenerate_sonarr.py` (see tests/e2e/seed/README.md)."
            )

    work = Path(tempfile.mkdtemp(prefix="wi1bot-e2e-"))

    # throwaway copies of the committed seeds so the containers never dirty the fixtures
    radarr_config = work / "radarr-config"
    sonarr_config = work / "sonarr-config"
    shutil.copytree(_SEED_RADARR, radarr_config)
    shutil.copytree(_SEED_SONARR, sonarr_config)

    fixtures = work / "fixtures"
    for out_name, loops in (("movie.mkv", _MOVIE_LOOPS), ("episode.mkv", _EPISODE_LOOPS)):
        _loop_clip(work, out_name, loops)

    for out_name, rel in (
        ("movie.mkv", _MOVIE_DOWNLOAD_REL),
        ("episode.mkv", _EPISODE_DOWNLOAD_REL),
        ("episode.mkv", _CF_HIGH_REL),
        ("episode.mkv", _CF_LOW_REL),
    ):
        dest = fixtures / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(work / out_name, dest)

    env = {
        "E2E_RADARR_CONFIG": str(radarr_config),
        "E2E_SONARR_CONFIG": str(sonarr_config),
        "E2E_FIXTURES_DIR": str(fixtures),
    }
    os.environ.update(env)

    yield env

    shutil.rmtree(work, ignore_errors=True)


@pytest.fixture(scope="session")
def docker_compose_file(e2e_env: dict[str, str]) -> str:
    # depend on e2e_env so the seed copies, fixtures, and env vars exist before `up`
    return str(_THIS_DIR / "compose.yaml")


@pytest.fixture(scope="session")
def docker_setup() -> list[str]:
    # no --build: compose builds the :e2e images only when missing locally and reuses
    # the exact CI build artifacts when the workflow has loaded them
    return ["up -d"]


@pytest.fixture(scope="session")
def docker_cleanup() -> list[str]:
    return ["down -v"]


def _responsive(url: str, headers: dict[str, str] | None = None) -> bool:
    try:
        return requests.get(url, headers=headers or {}, timeout=5).status_code == 200
    except requests.RequestException:
        return False


@pytest.fixture(scope="session")
def services(docker_ip: str, docker_services: Any) -> dict[str, str]:
    radarr_url = f"http://{docker_ip}:{docker_services.port_for(RADARR_SERVICE, 7878)}"
    sonarr_url = f"http://{docker_ip}:{docker_services.port_for(SONARR_SERVICE, 8989)}"
    webhook_url = f"http://{docker_ip}:{docker_services.port_for(WEBHOOK_SERVICE, 9000)}"

    docker_services.wait_until_responsive(
        timeout=180.0, pause=2.0, check=lambda: _responsive(f"{webhook_url}/health")
    )
    for arr_url in (radarr_url, sonarr_url):
        docker_services.wait_until_responsive(
            timeout=180.0,
            pause=2.0,
            check=lambda url=arr_url: _responsive(
                f"{url}/api/v3/system/status", headers={"X-Api-Key": API_KEY}
            ),
        )

    return {"radarr_url": radarr_url, "sonarr_url": sonarr_url, "webhook_url": webhook_url}


@pytest.fixture(scope="session")
def radarr(services: dict[str, str]) -> Radarr:
    # construct the client directly (not via ArrConfig) so the URL has no trailing
    # slash / base path for pyarr
    return Radarr(services["radarr_url"], API_KEY)


@pytest.fixture(scope="session")
def sonarr(services: dict[str, str]) -> Sonarr:
    return Sonarr(services["sonarr_url"], API_KEY)


def _configure_usenet_blackhole(arr_url: str, folder: str) -> None:
    headers = {"X-Api-Key": API_KEY}
    schema_response = requests.get(
        f"{arr_url}/api/v3/downloadclient/schema",
        headers=headers,
        timeout=30,
    )
    schema_response.raise_for_status()
    schemas: Any = schema_response.json()
    blackhole = next(
        schema for schema in schemas if schema.get("implementation") == "UsenetBlackhole"
    )
    blackhole["name"] = "e2e-usenet-blackhole"
    blackhole["enable"] = True
    for field in blackhole["fields"]:
        if field.get("name") == "nzbFolder":
            field["value"] = f"{folder}/nzb"
        elif field.get("name") == "watchFolder":
            field["value"] = f"{folder}/watch"

    create_response = requests.post(
        f"{arr_url}/api/v3/downloadclient",
        headers=headers,
        json=blackhole,
        timeout=30,
    )
    create_response.raise_for_status()


@pytest.fixture(scope="session")
def usenet_blackhole_clients(services: dict[str, str]) -> None:
    for kind in ("radarr", "sonarr"):
        _configure_usenet_blackhole(services[f"{kind}_url"], f"/media/blackhole/{kind}")


@pytest.fixture(scope="session")
def movie_id(radarr: Radarr) -> int:
    movies = radarr.get_movies()
    assert movies, "seeded Radarr has no movies"
    movie = next((m for m in movies if m.get("tmdbId") == MOVIE_TMDB_ID), movies[0])
    return int(movie["id"])


@pytest.fixture(scope="session")
def series_id(sonarr: Sonarr) -> int:
    series = sonarr.get_series()
    assert series, "seeded Sonarr has no series"
    show = next((s for s in series if s.get("title") == SERIES_TITLE), series[0])
    return int(show["id"])


@pytest.fixture(scope="session")
def movie_scan_path() -> str:
    return MOVIE_SCAN_PATH


@pytest.fixture(scope="session")
def series_scan_path() -> str:
    return SERIES_SCAN_PATH


@pytest.fixture(scope="session")
def custom_format_paths() -> dict[str, str]:
    return {
        "high_scan": CF_HIGH_SCAN_PATH,
        "low_source": CF_LOW_SOURCE_PATH,
    }


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    # stash each phase's report on the item so fixtures can see the outcome
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"_e2e_rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def _dump_logs_on_failure(
    request: pytest.FixtureRequest, docker_compose_file: str, docker_compose_project_name: str
) -> Generator[None, None, None]:
    yield
    rep = getattr(request.node, "_e2e_rep_call", None)
    if rep is None or not rep.failed:
        return
    for svc in _SERVICES:
        result = subprocess.run(
            [
                "docker", "compose",
                "-f", docker_compose_file,
                "-p", docker_compose_project_name,
                "logs", "--no-color", "--tail", str(LOG_TAIL), svc,
            ],
            capture_output=True,
            text=True,
        )  # fmt: skip
        print(f"\n===== {svc} (last {LOG_TAIL} log lines) =====\n{result.stdout}{result.stderr}")
