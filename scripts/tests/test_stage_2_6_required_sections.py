"""Stage 2.6 required-sections validator (A10, audit 2026-07-07 M5).

Hard-gate: a source page missing whole template H2 sections is a severe
generation-quality failure. The validator must RAISE (no-silent-fallback
policy), and must be doctype-aware — papers use "Paper Summary" +
"Methodology & Results", not "Book Summary" + "Table of Contents & Key
Concepts". The prior fixed list false-positived on every paper (masked by
warn-only); these tests lock both the raise and the doctype branching.

Stdlib unittest only.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _stage_2_6_source_page as s26  # noqa: E402


_BOOK_BODY = (
    "## Book Summary\n\nA book.\n\n"
    "## Table of Contents & Key Concepts\n\n- ch1\n\n"
    "## Key Entities\n\n- e1\n\n"
    "## Main Arguments & Findings\n\n- claim1\n\n"
    "## Connections to Existing Wiki\n\nNone identified.\n\n"
    "## Contradictions & Tensions\n\nNone identified.\n\n"
    "## Recommendations\n\nNone.\n"
)
_PAPER_BODY = (
    "## Paper Summary\n\nA paper.\n\n"
    "## Methodology & Results\n\n- method\n\n"
    "## Key Entities\n\n- e1\n\n"
    "## Main Arguments & Findings\n\n- claim1\n\n"
    "## Connections to Existing Wiki\n\nNone identified.\n\n"
    "## Contradictions & Tensions\n\nNone identified.\n\n"
    "## Recommendations\n\nNone.\n"
)


class RequiredHeadingsByDoctype(unittest.TestCase):
    def test_book_headings_shape(self):
        h = s26._stage_2_6_required_headings("book")
        self.assertIn("Book Summary", h)
        self.assertIn("Table of Contents & Key Concepts", h)
        self.assertNotIn("Paper Summary", h)

    def test_paper_headings_shape(self):
        h = s26._stage_2_6_required_headings("paper")
        self.assertIn("Paper Summary", h)
        self.assertIn("Methodology & Results", h)
        self.assertNotIn("Book Summary", h)
        self.assertNotIn("Table of Contents & Key Concepts", h)

    def test_unknown_doctype_falls_back_to_book(self):
        # datasheet/standard/news/etc. all route through the book template.
        h = s26._stage_2_6_required_headings("datasheet")
        self.assertIn("Book Summary", h)

    def test_shared_sections_present_in_both(self):
        book = set(s26._stage_2_6_required_headings("book"))
        paper = set(s26._stage_2_6_required_headings("paper"))
        shared = {"Key Entities", "Main Arguments & Findings",
                  "Connections to Existing Wiki",
                  "Contradictions & Tensions", "Recommendations"}
        self.assertTrue(shared <= book)
        self.assertTrue(shared <= paper)


class ValidateRaisesOnMissing(unittest.TestCase):
    def test_book_complete_does_not_raise(self):
        s26._stage_2_6_validate_required_sections(_BOOK_BODY, "book")

    def test_paper_complete_does_not_raise(self):
        s26._stage_2_6_validate_required_sections(_PAPER_BODY, "paper")

    def test_book_missing_recommendations_raises(self):
        body = _BOOK_BODY.replace("## Recommendations\n\nNone.\n", "")
        with self.assertRaises(RuntimeError) as cm:
            s26._stage_2_6_validate_required_sections(body, "book")
        self.assertIn("Recommendations", str(cm.exception))

    def test_paper_missing_methodology_raises(self):
        body = _PAPER_BODY.replace("## Methodology & Results\n\n- method\n\n", "")
        with self.assertRaises(RuntimeError) as cm:
            s26._stage_2_6_validate_required_sections(body, "paper")
        self.assertIn("Methodology & Results", str(cm.exception))

    def test_paper_with_book_headings_raises(self):
        # A paper-formatted page must NOT pass the paper validator just because
        # it has "Book Summary" — proves the doctype branching is real and the
        # old false-positive (book list applied to papers) is gone.
        with self.assertRaises(RuntimeError) as cm:
            s26._stage_2_6_validate_required_sections(_BOOK_BODY, "paper")
        self.assertIn("Paper Summary", str(cm.exception))

    def test_book_with_paper_headings_raises(self):
        with self.assertRaises(RuntimeError) as cm:
            s26._stage_2_6_validate_required_sections(_PAPER_BODY, "book")
        self.assertIn("Book Summary", str(cm.exception))

    def test_default_source_kind_is_book(self):
        # Omitting source_kind must default to book (the else branch).
        with self.assertRaises(RuntimeError):
            s26._stage_2_6_validate_required_sections(_PAPER_BODY)

    def test_heading_must_be_h2_not_h3(self):
        # A heading demoted to ### must not satisfy the check.
        body = _BOOK_BODY.replace("## Recommendations\n", "### Recommendations\n")
        with self.assertRaises(RuntimeError):
            s26._stage_2_6_validate_required_sections(body, "book")


if __name__ == "__main__":
    unittest.main()
