from wi1_bot.bot.discord.helpers import parse_user_tag


def test_parse_user_tag_current_format() -> None:
    assert parse_user_tag("william-123456789012345678") == ("william", 123456789012345678)


def test_parse_user_tag_legacy_format() -> None:
    assert parse_user_tag("william: 123456789012345678") == ("william", 123456789012345678)


def test_parse_user_tag_name_with_hyphen() -> None:
    assert parse_user_tag("william-h-123456789012345678") == ("william-h", 123456789012345678)


def test_parse_user_tag_name_with_digits() -> None:
    assert parse_user_tag("4k-123456789012345678") == ("4k", 123456789012345678)


def test_parse_user_tag_non_user_tag() -> None:
    assert parse_user_tag("sonarr-favorites") is None


def test_parse_user_tag_short_number_is_not_a_user() -> None:
    assert parse_user_tag("season-2") is None
