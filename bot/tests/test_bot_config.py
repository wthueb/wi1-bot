from typing import Any

import pytest
from pydantic import ValidationError

from wi1_bot.bot.config import Config, DiscordConfig


class TestQuotaConfig:
    @staticmethod
    def _discord(quotas: Any) -> DiscordConfig:
        return DiscordConfig(bot_token="t", channel_id=1, admin_id=2, quotas=quotas)

    def test_bare_number_is_shorthand_for_amount(self) -> None:
        cfg = self._discord({111: 123})

        assert cfg.quotas[111].amount == 123
        assert cfg.quotas[111].with_ == []

    def test_with_form_parses_additional_ids(self) -> None:
        cfg = self._discord({111: {"amount": 200, "with": [222, 333]}})

        assert cfg.quotas[111].amount == 200
        assert cfg.quotas[111].with_ == [222, 333]

    def test_none_becomes_empty(self) -> None:
        assert self._discord(None).quotas == {}

    def test_non_positive_amount_rejected(self) -> None:
        with pytest.raises(ValidationError):
            self._discord({111: 0})

    def test_member_in_two_groups_rejected(self) -> None:
        with pytest.raises(ValidationError, match="more than one quota"):
            self._discord(
                {
                    111: {"amount": 10, "with": [333]},
                    222: {"amount": 20, "with": [333]},
                }
            )

    def test_member_is_another_owner_rejected(self) -> None:
        with pytest.raises(ValidationError, match="more than one quota"):
            self._discord({111: {"amount": 10, "with": [222]}, 222: 20})

    def test_owner_in_own_with_list_rejected(self) -> None:
        with pytest.raises(ValidationError, match="more than one quota"):
            self._discord({111: {"amount": 10, "with": [111]}})


class TestTmdbConfig:
    def test_tmdb_is_optional(self) -> None:
        # the shared test config has no tmdb section
        assert Config().tmdb is None

    def test_tmdb_api_key_parses(self) -> None:
        cfg = Config(tmdb={"api_key": "abc"})  # type: ignore[arg-type]

        assert cfg.tmdb is not None
        assert cfg.tmdb.api_key == "abc"

    def test_empty_api_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Config(tmdb={"api_key": ""})  # type: ignore[arg-type]
