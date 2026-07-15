from wi1_bot.transcoder.languages import keep_original_language, original_language_codes


class TestOriginalLanguageCodes:
    def test_english_returns_empty(self) -> None:
        assert original_language_codes("English") == []

    def test_none_returns_empty(self) -> None:
        assert original_language_codes(None) == []

    def test_empty_string_returns_empty(self) -> None:
        assert original_language_codes("") == []

    def test_unknown_language_returns_empty(self) -> None:
        assert original_language_codes("Klingon") == []

    def test_japanese(self) -> None:
        assert original_language_codes("Japanese") == ["jpn"]

    def test_case_insensitive(self) -> None:
        assert original_language_codes("japanese") == ["jpn"]
        assert original_language_codes("  KOREAN  ") == ["kor"]

    def test_language_with_b_and_t_codes(self) -> None:
        # German has both a bibliographic (ger) and terminological (deu) code
        assert original_language_codes("German") == ["ger", "deu"]

    def test_regional_variant_collapses_to_base_code(self) -> None:
        assert original_language_codes("Portuguese (Brazil)") == ["por"]


class TestKeepOriginalLanguage:
    def test_none_keep_list_unchanged(self) -> None:
        # no keep-list means every track is kept already
        assert keep_original_language(None, "Japanese") is None

    def test_empty_keep_list_unchanged(self) -> None:
        assert keep_original_language("", "Japanese") == ""
        assert keep_original_language("  ", "Japanese") == "  "

    def test_appends_non_english_original(self) -> None:
        assert keep_original_language("eng", "Japanese") == "eng,jpn"

    def test_appends_both_language_codes(self) -> None:
        assert keep_original_language("eng", "German") == "eng,ger,deu"

    def test_english_original_unchanged(self) -> None:
        assert keep_original_language("eng,spa", "English") == "eng,spa"

    def test_missing_original_unchanged(self) -> None:
        assert keep_original_language("eng,spa", None) == "eng,spa"

    def test_does_not_duplicate_existing_code(self) -> None:
        assert keep_original_language("eng,jpn", "Japanese") == "eng,jpn"

    def test_normalizes_whitespace_in_keep_list(self) -> None:
        assert keep_original_language("eng, spa", "Korean") == "eng,spa,kor"

    def test_unknown_original_unchanged(self) -> None:
        assert keep_original_language("eng", "Klingon") == "eng"
