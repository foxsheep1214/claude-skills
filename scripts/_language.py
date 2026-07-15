"""Language detection — NashSU parity (detect-language.ts + output-language.ts).

Supports 25+ languages via Unicode script ranges and Latin-script diacritic/word
patterns. Used by ingest.py for output validation and wiki-lint-semantic.py for
LLM language directives.

Output language policy
-----------------------
The wiki holds only two languages. ``get_output_language`` / ``build_language_
directive`` auto-detect the source language via ``detect_language`` (which
still resolves 25+ languages), then collapse the result: Chinese source →
Chinese page; anything else (English, Norwegian, German, Japanese, ...) →
English page. ``detect_language`` itself is unchanged/unrestricted and is
also used standalone for source/consistency checks (see ``_ingest_write.py``).

To force a fixed output language regardless of source, set the env var
``IMPROVED_WIKI_OUTPUT_LANGUAGE`` to a language name (e.g. ``English``,
``Chinese``). The default value ``auto`` keeps the auto-detect+collapse
behavior above. This mirrors NashSU getOutputLanguage (output-language.ts):
an explicit, non-``auto`` value forces the language verbatim (not collapsed).
"""
from __future__ import annotations

import os
import re
from typing import Dict

# Env var that forces the LLM output language (NashSU getOutputLanguage parity).
# "auto" (the default) keeps auto-detection from the sampled text.
OUTPUT_LANGUAGE_ENV = "IMPROVED_WIKI_OUTPUT_LANGUAGE"


def detect_language(text: str) -> str:
    """Detect the primary language of a text string. Returns an English name."""
    if not text:
        return "English"

    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        if cp < 0x80:
            continue
        script = _get_script(cp)
        if script:
            counts[script] = counts.get(script, 0) + 1

    # Greek as math notation: isolated Greek letters (λ, σ, θ, Δ, …) flanked
    # by Latin/digits/operators are notation, not Greek-language text. Real
    # Greek has multi-letter word runs. Drop Greek from the script counts
    # when every Greek letter is an isolated singleton.
    if counts.get("Greek", 0) and not _has_greek_word_run(text):
        del counts["Greek"]

    # Japanese: Hiragana/Katakana + Kanji → Japanese (not Chinese)
    if counts.get("Japanese", 0) > 0 and counts.get("Chinese", 0) > 0:
        return "Japanese"

    # Dominant non-Latin script
    max_script = ""
    max_count = 0
    for script, count in counts.items():
        if count > max_count:
            max_script = script
            max_count = count

    if max_script == "Arabic" and max_count >= 2:
        return _detect_arabic_variant(text)
    if max_script and max_count >= 2:
        return max_script

    # Latin-script languages
    latin = _detect_latin(text)
    if latin:
        return latin
    return "English"


# Display / prompt names per language (NashSU getLanguagePromptName parity,
# language-metadata.ts). Falls back to the bare language name when absent.
_PROMPT_NAME_MAP: Dict[str, str] = {
    "Chinese": "Chinese (中文)",
    "Japanese": "Japanese (日本語)",
    "Korean": "Korean (한국어)",
    "Russian": "Russian (Русский)",
    "Arabic": "Arabic (العربية)",
    "Persian": "Persian (فارسی)",
    "Hebrew": "Hebrew (עברית)",
    "Thai": "Thai (ไทย)",
    "Hindi": "Hindi (हिन्दी)",
    "Bengali": "Bengali (বাংলা)",
    "Tamil": "Tamil (தமிழ்)",
    "Greek": "Greek (Ελληνικά)",
    "Georgian": "Georgian (ქართული)",
    "Armenian": "Armenian (Հայերեն)",
}


def _get_language_prompt_name(lang: str) -> str:
    """NashSU getLanguagePromptName parity: localized display name for a
    language, or the bare name when no mapping exists."""
    return _PROMPT_NAME_MAP.get(lang, lang)


def get_output_language(fallback_text: str = "") -> str:
    """Effective output language for LLM content generation.

    Policy (user ruling 2026-07-15): the wiki holds only two languages. A
    Chinese source produces a Chinese page; every other detected source
    language (English, Norwegian, German, Japanese, ...) produces an
    English page. This replaces the old "one page per detected source
    language" auto behavior, which let single-page languages (Norwegian,
    French, ...) leak into the KB — often from a false-positive detection
    off a few diacritic characters in an author name or address.

    If the user has set an explicit, non-"auto" override (via
    ``IMPROVED_WIKI_OUTPUT_LANGUAGE``), that value is honored verbatim and
    is NOT collapsed — it is a deliberate escape hatch (NashSU
    getOutputLanguage parity).
    """
    configured = os.environ.get(OUTPUT_LANGUAGE_ENV, "").strip()
    if configured and configured.lower() != "auto":
        return configured
    detected = detect_language((fallback_text or "English")[:2000])
    return "Chinese" if detected == "Chinese" else "English"


def build_language_directive(text: str) -> str:
    """Build a strong language directive to inject into LLM system prompts.

    NashSU buildLanguageDirective (output-language.ts) parity: state the
    mandatory output language for prose AND the proper-noun /
    technical-identifier / URL / paper-title / code-identifier preservation
    rules so the model localizes surrounding prose but NEVER translates
    identifiers. Honors the IMPROVED_WIKI_OUTPUT_LANGUAGE override.

    Signature is kept backward-compatible (single positional ``text`` arg) for
    existing ingest + lint callers.
    """
    lang = get_output_language(text)
    prompt_lang = _get_language_prompt_name(lang)
    return "\n".join([
        f"## ⚠️ MANDATORY OUTPUT LANGUAGE: {prompt_lang}",
        "",
        f"Write surrounding natural-language prose in **{prompt_lang}**.",
        f"All generated prose, including prose titles and section headings, "
        f"must be in {prompt_lang}.",
        "Do not translate, transliterate, or describe proper nouns and "
        "technical identifiers unless the source already uses a "
        "well-established localized form.",
        "Preserve organization names, product names, model names, dataset "
        "names, tool/library names, acronyms, code identifiers, file names, "
        "URLs, paper titles, citation strings, and technical terms that have "
        "no widely-used localized equivalent in their standard original form.",
        f"The source material or wiki content may be in a different language; "
        f"use it as evidence, but keep generated prose in {prompt_lang}.",
        "This language rule overrides weaker style instructions, but it does "
        "not override the proper-noun and technical-identifier preservation "
        "rule above.",
    ])


# ── Script detection ──

_GREEK_WORD_RUN = re.compile(r"[Ͱ-Ͽἀ-῿]{2,}")


def _has_greek_word_run(text: str) -> bool:
    """True if ``text`` contains ≥2 consecutive Greek letters — a word run.

    Isolated single Greek letters (math symbols like λ, σ, Δ) do not form a
    run, so a math-heavy English paragraph returns False and is not
    misclassified as Greek.
    """
    return bool(_GREEK_WORD_RUN.search(text))


def _get_script(cp: int):
    # CJK Unified Ideographs
    if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or \
       (0x20000 <= cp <= 0x2A6DF) or (0xF900 <= cp <= 0xFAFF):
        return "Chinese"
    # Japanese kana
    if (0x3040 <= cp <= 0x309F) or (0x30A0 <= cp <= 0x30FF) or \
       (0x31F0 <= cp <= 0x31FF) or (0xFF65 <= cp <= 0xFF9F):
        return "Japanese"
    # Korean Hangul
    if (0xAC00 <= cp <= 0xD7AF) or (0x1100 <= cp <= 0x11FF) or (0x3130 <= cp <= 0x318F):
        return "Korean"
    # Arabic
    if (0x0600 <= cp <= 0x06FF) or (0x0750 <= cp <= 0x077F) or \
       (0x08A0 <= cp <= 0x08FF) or (0xFB50 <= cp <= 0xFDFF) or (0xFE70 <= cp <= 0xFEFF):
        return "Arabic"
    # Hebrew
    if (0x0590 <= cp <= 0x05FF) or (0xFB1D <= cp <= 0xFB4F):
        return "Hebrew"
    # Thai
    if 0x0E00 <= cp <= 0x0E7F:
        return "Thai"
    # Devanagari
    if 0x0900 <= cp <= 0x097F:
        return "Hindi"
    # Bengali
    if 0x0980 <= cp <= 0x09FF:
        return "Bengali"
    # Tamil
    if 0x0B80 <= cp <= 0x0BFF:
        return "Tamil"
    # Cyrillic
    if (0x0400 <= cp <= 0x04FF) or (0x0500 <= cp <= 0x052F):
        return "Russian"
    # Greek
    if (0x0370 <= cp <= 0x03FF) or (0x1F00 <= cp <= 0x1FFF):
        return "Greek"
    # Georgian
    if (0x10A0 <= cp <= 0x10FF) or (0x2D00 <= cp <= 0x2D2F):
        return "Georgian"
    # Armenian
    if 0x0530 <= cp <= 0x058F:
        return "Armenian"
    return None


# ── Arabic script refinement ──

def _detect_arabic_variant(text: str) -> str:
    persian_chars = set("پچژگ")
    persian_score = sum(3 for ch in text if ch in persian_chars)
    persian_score += sum(1 for ch in text if ch in "کی")
    arabic_score = sum(1 for ch in text if ch in "كي ةىإأؤئ")

    words = set(re.findall(r"\w+", text))
    persian_words = {"این", "است", "که", "برای", "های", "را", "در", "به", "از", "می", "یک"}
    arabic_words = {"ال", "في", "من", "على", "هذا", "هذه", "إلى", "التي", "الذي", "كان"}
    persian_score += sum(2 for w in persian_words if w in words)
    arabic_score += sum(2 for w in arabic_words if w in words)

    return "Persian" if persian_score >= 3 and persian_score > arabic_score else "Arabic"


# ── Latin-script language detection ──

def _detect_latin(text: str):
    lower = text.lower()
    words = set(re.findall(r"\w+", lower))

    # Vietnamese
    if re.search(r"[ảạắằẳẵặấầẩẫậđẻẽẹếềểễệỉĩịỏọốồổỗộơớờởỡợủũụưứừửữựỷỹỵ]", lower):
        return "Vietnamese"
    # Turkish
    if re.search(r"[ğış]", lower) and len(words & {"bir", "ve", "için", "ile", "bu", "da", "de"}) >= 2:
        return "Turkish"
    # Polish
    if re.search(r"[ąćęłńóśźż]", lower):
        return "Polish"
    # Czech
    if re.search(r"[ěšžřďťňů]", lower):
        return "Czech"
    # Romanian
    if re.search(r"[ăâîșț]", lower) and len(words & {"și", "este", "sau", "care", "pentru"}) >= 2:
        return "Romanian"
    # Hungarian
    if re.search(r"[őű]", lower):
        return "Hungarian"
    # German
    if len(words & {"und", "der", "die", "das", "ist"}) >= 2:
        return "German"
    # French
    if len(words & {"le", "la", "les", "est", "une", "des"}) >= 2:
        return "French"
    # Portuguese (before Spanish — stricter chars)
    if re.search(r"[ãõç]", lower) and len(words & {"o", "a", "os", "as", "de", "do", "da", "não", "que"}) >= 2:
        return "Portuguese"
    # Spanish (ñ/¿/¡ alone is a strong signal; otherwise require ≥2 function words)
    if re.search(r"[ñ¿¡]", lower) or len(words & {"el", "los", "las", "del", "por"}) >= 2:
        return "Spanish"
    # Italian
    if len(words & {"il", "della", "gli", "che", "è"}) >= 2:
        return "Italian"
    # Dutch
    if len(words & {"het", "een", "van", "dat"}) >= 2:
        return "Dutch"
    # Swedish
    if re.search(r"[åäö]", lower) and len(words & {"och", "att", "det", "är", "för"}) >= 2:
        return "Swedish"
    # Norwegian
    if re.search(r"[åæø]", lower) and len(words & {"og", "er", "det", "for", "med", "på"}) >= 2:
        return "Norwegian"
    # Danish
    if re.search(r"[åæø]", lower) and len(words & {"og", "er", "det", "til", "med", "af"}) >= 2:
        return "Danish"
    # Finnish
    if re.search(r"[äö]", lower) and len(words & {"ja", "on", "ei", "se", "että", "tai", "kun"}) >= 2:
        return "Finnish"
    # Indonesian
    if len(words & {"yang", "dari", "untuk", "dengan", "adalah"}) >= 2:
        return "Indonesian"

    return None
