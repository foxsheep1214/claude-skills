"""Tests for the NashSU searchQueries parity on review items.

Stage 3.4 populates ``search_queries`` (2-3 web-search queries) on
suggestion/missing-page reviews; the field rides in the review page
frontmatter and is surfaced by ``sweep_reviews`` so deep-research can seed
its web queries with no extra LLM call. These tests pin the render + the
frontmatter round-trip without an LLM.

Run:  python3 scripts/tests/test_review_search_queries.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _stage_3_4_review as review  # noqa: E402
import sweep_reviews  # noqa: E402


class TestRenderReviewPage(unittest.TestCase):
    def test_search_queries_in_frontmatter_and_body(self):
        md = review._render_review_page(
            "missing-page", "缺少 GaN HEMT 驱动电路设计",
            "实体被引用但无独立页面", ["concepts/gan-hemt.md"],
            ["gan hemt gate driver design", "sic gan driver dead time"],
            "high", "2026-06-28", "RF-Circuit-Design",
        )
        self.assertIn('search_queries: ["gan hemt gate driver design", "sic gan driver dead time"]', md)
        self.assertIn("## Search Queries (Deep Research)", md)
        self.assertIn("- gan hemt gate driver design", md)

    def test_no_search_queries_renders_empty_bracket_no_body_section(self):
        md = review._render_review_page(
            "confirm", "数值需核对", "参数存疑", ["sources/foo.md"],
            [], "medium", "2026-06-28", "Book",
        )
        self.assertIn("search_queries: []", md)
        self.assertNotIn("## Search Queries (Deep Research)", md)


class TestSweepRoundTrip(unittest.TestCase):
    """sweep_reviews._parse_frontmatter must read search_queries back as a list."""

    def test_parse_search_queries_flow_sequence(self):
        md = review._render_review_page(
            "suggestion", "补充对比", "建议增加对比页", ["concepts/a.md"],
            ["foo bar baz", "qux quux"], "medium", "2026-06-28", "Book",
        )
        fm = sweep_reviews._parse_frontmatter(md)
        self.assertIsInstance(fm.get("search_queries"), list)
        self.assertEqual(fm["search_queries"], ["foo bar baz", "qux quux"])

    def test_parse_empty_search_queries(self):
        md = review._render_review_page(
            "duplicate", "重复", "可能重复", [], [], "low", "2026-06-28", "Book",
        )
        fm = sweep_reviews._parse_frontmatter(md)
        self.assertEqual(fm.get("search_queries"), [])


class TestPromptAsksForSearchQueries(unittest.TestCase):
    """The Stage 3.4 system prompt must instruct the LLM to emit search_queries
    for suggestion/missing-page (NashSU SEARCH-line parity)."""

    def test_prompt_mentions_search_queries(self):
        import inspect
        src = inspect.getsource(review.stage_3_4_review_suggestions)
        self.assertIn("search_queries", src)
        self.assertIn("suggestion", src)
        self.assertIn("missing-page", src)


if __name__ == "__main__":
    unittest.main()
