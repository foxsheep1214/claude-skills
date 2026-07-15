"""Regression tests for _language.detect_language.

Stdlib ``unittest`` only — no pytest, no network, no LLM calls.

Run:
    python3 -m unittest tests.test_language   # from scripts/
    python3 scripts/tests/test_language.py     # from skill root

Each test maps to a real misdetection hit during radar-book ingestion
(see references/known-issues.md): math Greek symbols and stray Latin
function words must not flip the detected language of an English
technical document.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _language import (  # noqa: E402
    detect_language,
    build_language_directive,
    get_output_language,
    OUTPUT_LANGUAGE_ENV,
)


class TestMathGreekNotGreek(unittest.TestCase):
    """Isolated Greek letters used as math symbols (λ, σ, θ, Δ, …) are
    notation, not Greek-language text. An English paragraph full of them
    must stay English."""

    def test_english_radar_equation_stays_english(self):
        text = (
            "The radar equation: P_r = P_t G^2 λ^2 σ / ((4π)^3 R^4), where λ "
            "is wavelength, σ is RCS, θ beamwidth, φ phase. SNR depends on "
            "α, β, μ, ω, Δ, Σ across the aperture."
        )
        self.assertEqual(detect_language(text), "English")

    def test_isolated_single_greek_letter_is_not_greek(self):
        # Two isolated Greek letters (the old ≥2-count threshold) among Latin.
        self.assertEqual(detect_language("Let λ and μ vary."), "English")


class TestRealGreekIsGreek(unittest.TestCase):
    """Genuine Greek text — multi-letter runs forming words — must still
    be detected as Greek so the directive still works for Greek sources."""

    def test_greek_sentence(self):
        text = "Αυτό είναι ένα κείμενο στα ελληνικά για δοκιμή ανίχνευσης."
        self.assertEqual(detect_language(text), "Greek")


class TestStrayLatinTokenNotFrench(unittest.TestCase):
    """A single short French-looking token (e.g. 'le') appearing inside
    English text must not flip the document to French. The Advanced Metric
    Wave Radar English foreword was misdetected as French this way."""

    def test_english_with_stray_le_stays_english(self):
        text = (
            "Advanced Metric Wave Radar by Jianqi Wu. The idea to write this "
            "book relates to the International Radar Conferences attended in "
            "le series of nations."
        )
        self.assertEqual(detect_language(text), "English")

    def test_single_french_word_not_enough(self):
        # 'est' appears as a standalone token but the rest is English.
        self.assertEqual(detect_language("The estimate est given here."), "English")


class TestRealFrenchIsFrench(unittest.TestCase):
    """Genuine French — multiple function words — must still be detected."""

    def test_french_sentence(self):
        text = "Le radar est un système de détection qui utilise les ondes."
        self.assertEqual(detect_language(text), "French")


class TestChineseAndEnglish(unittest.TestCase):
    """Sanity: the dominant-script path still works."""

    def test_chinese_text(self):
        self.assertEqual(detect_language("先进米波雷达是一种重要的雷达体制。"), "Chinese")

    def test_plain_english(self):
        self.assertEqual(detect_language("This is a plain English sentence about radar."), "English")


class TestDiacriticNameNotNordic(unittest.TestCase):
    """A single Nordic diacritic (from an author name/affiliation) plus one
    incidental English function word must not flip an English paper to
    Norwegian/Danish/Swedish. Real hit: an Aalborg University arXiv paper
    (English body) with author "Alba Spliid Damkjær" (æ) and "Magnus Ørum
    Bastrup Poulsen" (ø) was misdetected as Norwegian because the abstract
    happened to contain the word "for" — the only Norwegian function word
    that also doubles as common English vocabulary."""

    def test_english_paper_with_danish_author_names_stays_english(self):
        text = (
            "Anders Malthe Westerkam, Alba Spliid Damkjaer, Magnus Oerum "
            "Bastrup Poulsen. Aalborg University, Aalborg Denmark.\n"
            "Abstract—We propose an analytic model for the second-order "
            "characteristics of the radar return signal from a swarm of "
            "rotor drones, presenting new challenges for radar detection."
        ).replace("ae", "æ").replace("Oerum", "Ørum")
        self.assertEqual(detect_language(text), "English")

    def test_single_nordic_function_word_not_enough(self):
        # One diacritic char + exactly one function word ("for") must not
        # be enough on its own (mirrors the German/French ≥2 threshold).
        self.assertEqual(
            detect_language("Poulsen Damkjær reaching for the radar data."),
            "English",
        )

    def test_real_norwegian_still_detected(self):
        text = "Vi målte støyen på radarsystemet og fant gode resultater."
        self.assertEqual(detect_language(text), "Norwegian")

    def test_real_danish_still_detected(self):
        text = "Dette system bruges til at måle støj fra dronen og fugle."
        self.assertEqual(detect_language(text), "Danish")


class TestMathAndAcronymFalsePositivesStayEnglish(unittest.TestCase):
    """Broader sweep (2026-07-15) of the same false-positive pattern across
    other detectors, found by scanning RadarWiki/HardwareWiki for pages whose
    body language came out neither Chinese nor English."""

    def test_two_letter_greek_math_pairs_stay_english(self):
        # σθ, αβ (alpha-beta tracking filter), 2πΔf — two single-letter Greek
        # symbols written back to back with no separator is common notation,
        # not a Greek word. Real hits: pa-vs-fda-vs-mimo-vs-fda-mimo.md,
        # classical-control-for-radar-servo-tracking.md.
        text = "Scaling σθ≈θbw/(km√(2SNR)). This method best matches an αβ/Kalman tracker over 2πΔf bandwidth."
        self.assertEqual(detect_language(text), "English")

    def test_los_el_radar_acronyms_not_spanish(self):
        # "LOS" (line-of-sight) and "EL" (elevation) lowercase to "los"/"el",
        # which used to be 2 of Spanish's 5 function words. Real hit:
        # satellite-communication-link-geometry-and-loss-budget.md.
        text = "LOS loss = 32.44 + 20 log(distance) + 20 log(freq), computed from the EL and AZ angles."
        self.assertEqual(detect_language(text), "English")

    def test_stray_tilde_char_not_portuguese(self):
        # A single ã/õ/ç from a tilde-accented math symbol plus incidental
        # "a"/"as" (both dropped from the word set) used to be enough.
        # Real hit: complementary-golay-codes.md.
        text = "The estimator ã is used here, as well as a related bound derived from the same sequence."
        self.assertEqual(detect_language(text), "English")

    def test_stray_tilde_vowel_not_vietnamese(self):
        # A single precomposed tilde/circumflex vowel (ũ, ẽ, ...) is exactly
        # how an "estimate"/"conjugate" math symbol renders over a Latin
        # letter. Real hit: cramer-rao-bound-for-mimo-radar.md, with
        # equations like "ũ†(...)" and "c̃".
        text = "The received signal model f = 2|b|^2 k^2 re{n_r ũ†(x - m)} uses ũ as the whitened vector."
        self.assertEqual(detect_language(text), "English")

    def test_cuk_converter_name_not_polish(self):
        # "Ćuk" (the Ćuk converter, named after Slobodan Ćuk) is the only
        # diacritic in an all-English power-electronics page. Real hits:
        # cuk-converter.md, buck-boost-converter-dc-dc.md, Hart's Power
        # Electronics textbook source page.
        text = "The Ćuk converter is a type of DC-DC converter named after Slobodan Ćuk, providing inverted output."
        self.assertEqual(detect_language(text), "English")

    def test_japanese_loanword_in_chinese_page_stays_chinese(self):
        # パス ("pass", as in a filter's passband) cited once inside an
        # otherwise Chinese circuit-design page used to flip the whole page
        # to "Japanese" off 4 stray kana characters against 500+ Han
        # characters. Real hit: "Bandstop filters Bainter topology" page.
        text = (
            "许多应用需要陷波滤波器（bandstop/notch filter）来消除特定频率信号，"
            "如音频信号处理、助听器反馈抑制、工频噪声抑制等。关键参数定义："
            "f0为陷波中心频率，带宽定义品质因数，通带パス特性决定滤波器性能，"
            "工程师需要根据具体应用场景选择合适的滤波器拓扑结构和元器件参数。"
        )
        self.assertEqual(detect_language(text), "Chinese")

    def test_genuine_japanese_still_detected(self):
        text = "これは日本語のテキストです。レーダーについて説明します。"
        self.assertEqual(detect_language(text), "Japanese")

    def test_genuine_polish_still_detected(self):
        text = "To jest bardzo ważne, że nie możemy zapomnieć o tym problemie, który się pojawił."
        self.assertEqual(detect_language(text), "Polish")

    def test_genuine_czech_still_detected(self):
        text = "Tento systém se používá pro sledování letadel a dronů, což je velmi užitečné pro obranu."
        self.assertEqual(detect_language(text), "Czech")

    def test_genuine_hungarian_still_detected(self):
        text = "Ez egy fontos kérdés, és sokan gondolkodnak róla a jövőben is."
        self.assertEqual(detect_language(text), "Hungarian")

    def test_genuine_vietnamese_still_detected(self):
        text = "Đây là một câu tiếng Việt để kiểm tra việc phát hiện ngôn ngữ."
        self.assertEqual(detect_language(text), "Vietnamese")

    def test_genuine_portuguese_still_detected(self):
        text = "Este sistema utiliza um radar para detectar aviões não tripulados, o que é muito importante."
        self.assertEqual(detect_language(text), "Portuguese")

    def test_genuine_spanish_still_detected(self):
        text = "Esta es una técnica de detección por radar, muy útil para el seguimiento de objetivos también."
        self.assertEqual(detect_language(text), "Spanish")


class TestOutputLanguageCollapsesToTwoLanguages(unittest.TestCase):
    """Policy (user ruling 2026-07-15): the wiki only ever holds Chinese or
    English pages. Any detected source language other than Chinese must
    collapse to English — it must NOT return the source's own language."""

    def setUp(self):
        self._old = os.environ.get(OUTPUT_LANGUAGE_ENV)
        os.environ.pop(OUTPUT_LANGUAGE_ENV, None)

    def tearDown(self):
        if self._old is None:
            os.environ.pop(OUTPUT_LANGUAGE_ENV, None)
        else:
            os.environ[OUTPUT_LANGUAGE_ENV] = self._old

    def test_chinese_source_stays_chinese(self):
        self.assertEqual(get_output_language("先进米波雷达是一种重要的雷达体制。"), "Chinese")

    def test_english_source_stays_english(self):
        self.assertEqual(get_output_language("This is a plain English sentence."), "English")

    def test_french_source_collapses_to_english(self):
        text = "Le radar est un système de détection qui utilise les ondes."
        self.assertEqual(detect_language(text), "French")  # raw detector unchanged
        self.assertEqual(get_output_language(text), "English")  # policy collapses it

    def test_norwegian_source_collapses_to_english(self):
        text = "Vi målte støyen på radarsystemet og fant gode resultater."
        self.assertEqual(detect_language(text), "Norwegian")  # raw detector unchanged
        self.assertEqual(get_output_language(text), "English")  # policy collapses it

    def test_japanese_source_collapses_to_english(self):
        text = "これは日本語のテキストです。レーダーについて説明します。"
        self.assertEqual(get_output_language(text), "English")


class TestDirectivePreservationClauses(unittest.TestCase):
    """build_language_directive must port NashSU buildLanguageDirective's
    preservation rules so the LLM localizes prose but NEVER translates
    proper nouns, technical identifiers, URLs, paper titles, or code."""

    def test_directive_states_mandatory_language(self):
        directive = build_language_directive("This is plain English text.")
        self.assertIn("MANDATORY OUTPUT LANGUAGE", directive)
        self.assertIn("English", directive)

    def test_directive_has_proper_noun_preservation(self):
        directive = build_language_directive("先进米波雷达是一种重要的雷达体制。")
        # Localized prose language is Chinese...
        self.assertIn("Chinese (中文)", directive)
        # ...but the preservation clauses must be present verbatim.
        self.assertIn("Do not translate, transliterate", directive)
        self.assertIn("proper nouns", directive)
        self.assertIn("organization names", directive)
        self.assertIn("acronyms", directive)
        self.assertIn("code identifiers", directive)
        self.assertIn("file names", directive)
        self.assertIn("URLs", directive)
        self.assertIn("paper titles", directive)
        self.assertIn("citation strings", directive)

    def test_directive_has_override_ordering_clause(self):
        directive = build_language_directive("plain English")
        self.assertIn("overrides weaker style instructions", directive)
        self.assertIn("does not override", directive)


class TestOutputLanguageOverride(unittest.TestCase):
    """IMPROVED_WIKI_OUTPUT_LANGUAGE forces the output language regardless of
    the source text (NashSU getOutputLanguage parity)."""

    def setUp(self):
        self._old = os.environ.get(OUTPUT_LANGUAGE_ENV)

    def tearDown(self):
        if self._old is None:
            os.environ.pop(OUTPUT_LANGUAGE_ENV, None)
        else:
            os.environ[OUTPUT_LANGUAGE_ENV] = self._old

    def test_auto_default_detects_from_text(self):
        os.environ.pop(OUTPUT_LANGUAGE_ENV, None)
        self.assertEqual(get_output_language("先进米波雷达是雷达体制。"), "Chinese")

    def test_explicit_auto_value_still_detects(self):
        os.environ[OUTPUT_LANGUAGE_ENV] = "auto"
        self.assertEqual(get_output_language("先进米波雷达是雷达体制。"), "Chinese")

    def test_override_forces_language_over_source(self):
        os.environ[OUTPUT_LANGUAGE_ENV] = "French"
        # Source is Chinese, but override forces French.
        self.assertEqual(get_output_language("先进米波雷达是雷达体制。"), "French")
        directive = build_language_directive("先进米波雷达是雷达体制。")
        self.assertIn("French", directive)
        self.assertNotIn("Chinese (中文)", directive)

    def test_override_blank_falls_back_to_detect(self):
        os.environ[OUTPUT_LANGUAGE_ENV] = ""
        self.assertEqual(get_output_language("先进米波雷达是雷达体制。"), "Chinese")


if __name__ == "__main__":
    unittest.main()
