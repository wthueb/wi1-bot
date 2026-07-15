"""Helpers for preserving a title's original (non-English) audio/subtitle tracks.

Radarr/Sonarr report a title's ``originalLanguage`` as an English display name
(e.g. ``"Japanese"``). Media files tag their audio/subtitle streams with ISO
639-2 codes (e.g. ``"jpn"``), which is also what the transcoding ``languages``
keep-list uses. This module maps the former to the latter so the transcoder can
avoid stripping the original-language tracks of foreign-language content.

Some languages have two ISO 639-2 codes -- a bibliographic (B) and a
terminological (T) variant (e.g. German is ``ger``/``deu``). Files use one or
the other, so both are returned when they differ.
"""

# Radarr/Sonarr language name (lowercased) -> ISO 639-2 code(s).
# Sourced from Radarr's Language enum; regional variants collapse to their base
# language's code (e.g. "Portuguese (Brazil)" -> "por").
LANGUAGE_NAME_TO_CODES: dict[str, tuple[str, ...]] = {
    "english": ("eng",),
    "french": ("fre", "fra"),
    "spanish": ("spa",),
    "spanish (latino)": ("spa",),
    "german": ("ger", "deu"),
    "italian": ("ita",),
    "danish": ("dan",),
    "dutch": ("dut", "nld"),
    "flemish": ("dut", "nld"),
    "japanese": ("jpn",),
    "icelandic": ("ice", "isl"),
    "chinese": ("chi", "zho"),
    "russian": ("rus",),
    "polish": ("pol",),
    "vietnamese": ("vie",),
    "swedish": ("swe",),
    "norwegian": ("nor",),
    "finnish": ("fin",),
    "turkish": ("tur",),
    "portuguese": ("por",),
    "portuguese (brazil)": ("por",),
    "greek": ("gre", "ell"),
    "korean": ("kor",),
    "hungarian": ("hun",),
    "hebrew": ("heb",),
    "lithuanian": ("lit",),
    "czech": ("cze", "ces"),
    "arabic": ("ara",),
    "hindi": ("hin",),
    "bulgarian": ("bul",),
    "malayalam": ("mal",),
    "ukrainian": ("ukr",),
    "slovak": ("slo", "slk"),
    "thai": ("tha",),
    "romanian": ("rum", "ron"),
    "latvian": ("lav",),
    "persian": ("per", "fas"),
    "catalan": ("cat",),
    "croatian": ("hrv",),
    "serbian": ("srp",),
    "bosnian": ("bos",),
    "estonian": ("est",),
    "tamil": ("tam",),
    "indonesian": ("ind",),
    "telugu": ("tel",),
    "macedonian": ("mac", "mkd"),
    "slovenian": ("slv",),
    "malay": ("may", "msa"),
    "malaysian": ("may", "msa"),
    "kannada": ("kan",),
    "albanian": ("alb", "sqi"),
    "afrikaans": ("afr",),
    "marathi": ("mar",),
    "tagalog": ("tgl",),
    "urdu": ("urd",),
    "romansh": ("roh",),
    "mongolian": ("mon",),
    "bengali": ("ben",),
}


def original_language_codes(name: str | None) -> list[str]:
    """Return the ISO 639-2 code(s) for a non-English original language.

    Returns an empty list when the language is English (already the assumed
    default), unknown, or missing -- in which case no extra tracks need to be
    kept.
    """
    if not name:
        return []

    codes = LANGUAGE_NAME_TO_CODES.get(name.strip().lower())

    if codes is None or "eng" in codes:
        return []

    return list(codes)


def keep_original_language(languages: str | None, original_language: str | None) -> str | None:
    """Add a non-English original language to a comma-separated keep-list.

    ``languages`` is the transcoding profile's keep-list (audio/subtitle tracks
    whose language is not in it get stripped). When it is empty/unset, every
    track is kept already, so it is returned unchanged. Otherwise the original
    language's ISO 639-2 code(s) are appended if not already present, so that a
    foreign-language title's original audio/subtitles survive transcoding.
    """
    if not languages or not languages.strip():
        return languages

    keep = [lang.strip() for lang in languages.split(",") if lang.strip()]

    for code in original_language_codes(original_language):
        if code not in keep:
            keep.append(code)

    return ",".join(keep)
