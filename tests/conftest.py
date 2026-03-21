from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_arr_clients() -> Generator[dict[str, Any], None, None]:
    with (
        patch("wi1_bot.arr.radarr.RadarrClient") as mock_radarr,
        patch("wi1_bot.arr.sonarr.SonarrClient") as mock_sonarr,
    ):
        yield {"radarr": mock_radarr, "sonarr": mock_sonarr}
