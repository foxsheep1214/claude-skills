"""Tests for _lint_fixes — ported from NashSU lint-fixes.ts (v0.5.1).

Covers make_query_slug, append_wikilink, rewrite_wikilink_target, and
ensure_broken_link_stub (uses tempfile). Stdlib unittest only.

Run:  python3 scripts/tests/test_lint_fixes.py
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _lint_fixes as f  # noqa: E402


class TestMakeQuerySlug(unittest.TestCase):
    def test_basic_kebab(self):
        self.assertEqual(f.make_query_slug("Foo Bar Baz"), "foo-bar-baz")

    def test_keeps_cjk(self):
        self.assertEqual(f.make_query_slug("功率变换器"), "功率变换器")

    def test_nfkc_normalizes_fullwidth(self):
        self.assertEqual(f.make_query_slug("ＡＢＣ"), "abc")

    def test_strips_punctuation(self):
        self.assertEqual(f.make_query_slug("Foo: Bar! (v2)"), "foo-bar-v2")

    def test_empty_falls_back_to_query(self):
        self.assertEqual(f.make_query_slug("!!!"), "query")

    def test_truncates_to_50(self):
        self.assertLessEqual(len(f.make_query_slug("a" * 200)), 50)


class TestAppendWikilink(unittest.TestCase):
    def test_appends_under_existing_related(self):
        content = "---\ntype: entity\n---\n\n# Foo\n\n## Related\n\n- [[bar]]\n"
        out = f.append_wikilink(content, "baz")
        self.assertIn("- [[baz]]", out)
        self.assertIn("- [[bar]]", out)

    def test_creates_related_heading_when_absent(self):
        content = "---\ntype: entity\n---\n\n# Foo\n\nbody\n"
        out = f.append_wikilink(content, "baz")
        self.assertIn("## Related\n", out)
        self.assertIn("- [[baz]]", out)

    def test_noop_when_link_present(self):
        content = "---\ntype: entity\n---\n\n## Related\n\n- [[baz]]\n"
        self.assertEqual(f.append_wikilink(content, "baz"), content)

    def test_noop_case_insensitive(self):
        content = "---\ntype: entity\n---\n\n## Related\n\n- [[Baz]]\n"
        self.assertEqual(f.append_wikilink(content, "baz"), content)


class TestRewriteWikilinkTarget(unittest.TestCase):
    def test_rewrites_plain(self):
        content = "See [[foo-barr]] for more.\n"
        out = f.rewrite_wikilink_target(content, "foo-barr", "foo-bar")
        self.assertIn("[[foo-bar]]", out)
        self.assertNotIn("[[foo-barr]]", out)

    def test_preserves_alias(self):
        content = "See [[foo-barr|the foo]] for more.\n"
        out = f.rewrite_wikilink_target(content, "foo-barr", "foo-bar")
        self.assertIn("[[foo-bar|the foo]]", out)

    def test_leaves_other_links(self):
        content = "[[a]] and [[foo-barr]] and [[b]]\n"
        out = f.rewrite_wikilink_target(content, "foo-barr", "foo-bar")
        self.assertIn("[[a]]", out)
        self.assertIn("[[b]]", out)
        self.assertIn("[[foo-bar]]", out)

    def test_case_insensitive_match(self):
        content = "[[Foo-Barr]]\n"
        out = f.rewrite_wikilink_target(content, "foo-barr", "foo-bar")
        self.assertIn("[[foo-bar]]", out)


class TestStub(unittest.TestCase):
    def test_relative_path_simple(self):
        self.assertEqual(
            f.stub_relative_path_from_broken_target("missing-thing"),
            "queries/missing-thing.md",
        )

    def test_relative_path_nested(self):
        rel = f.stub_relative_path_from_broken_target("concepts/missing-thing")
        self.assertTrue(rel.startswith("concepts/"))
        self.assertTrue(rel.endswith(".md"))

    def test_ensure_stub_creates_then_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            full, rel, created = f.ensure_broken_link_stub(td, "missing-thing")
            self.assertTrue(created)
            self.assertTrue(full.exists())
            self.assertEqual(rel, "queries/missing-thing.md")
            self.assertIn("type: query", full.read_text(encoding="utf-8"))
            _, _, created2 = f.ensure_broken_link_stub(td, "missing-thing")
            self.assertFalse(created2)

    def test_stub_title_humanized(self):
        self.assertEqual(
            f.stub_title_from_broken_target("missing-thing"),
            "missing thing",
        )


if __name__ == "__main__":
    unittest.main()
