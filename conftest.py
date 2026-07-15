import os
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# point every service's Config at the shared combined test config before any
# package module (which instantiates its Config at import time) is imported
os.environ.setdefault("WB_CONFIG_PATH", str(Path(__file__).parent / "tests" / "config.yaml"))


@pytest.fixture(autouse=True)
def mock_arr_clients() -> Generator[dict[str, Any], None, None]:
    with (
        patch("wi1_bot.arr.radarr.RadarrClient") as mock_radarr,
        patch("wi1_bot.arr.sonarr.SonarrClient") as mock_sonarr,
    ):
        yield {"radarr": mock_radarr, "sonarr": mock_sonarr}
