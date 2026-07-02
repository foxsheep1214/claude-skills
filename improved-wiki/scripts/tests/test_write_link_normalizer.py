"""Tests for the Stage 3.1 write-time link normalizer (audit 2026-07-02, A5/M6).

One normalization pass applied to every non-listing FILE block right before
stage_3_1_write_wiki_file:
  1. related: entries → prefixed bare slugs (strip [[..]]/quotes, resolve the
     prefix against batch ∪ on-disk universe, drop unresolvable with a warn).
  2. Bare body wikilinks [[foo]] → prefixed when uniquely resolvable;
     ambiguous/missing left as-is + warned (never de-linked automatically).
  3. H1 heading lines: embedded wikilinks stripped to plain text.
  4. Self-links (own slug in body or related) de-linked/removed.

Also locks in: already-clean pages pass through byte-identical, and every fix
prints a loud per-page [normalize] line (never silent).

Stdlib unittest only — no network/LLM.
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _stage_3_write import (  # noqa: E402
    stage_3_1_build_slug_dirs,
    stage_3_1_normalize_page_links,
    _stage_3_1_scan_wiki_slug_dirs,
)

# Shared slug→dirs universe (batch ∪ disk shape the builders produce).
SLUG_DIRS: dict[str, set[str]] = {
    "matched-filter": {"concepts"},
    "bell-labs": {"entities"},
    "both-ways": {"concepts", "entities"},          # ambiguous stem
    "radar-handbook": {"sources/Book"},
    "pulse-compression": {"concepts"},              # "own page" in most tests
    "marcum": {"entities"},
}

OWN = "concepts/pulse-compression.md"


def _page(related_line: str = 'related: []', body: str = "\n# Title\n\nBody.\n") -> str:
    return (
        "---\n"
        "type: concept\n"
        'title: "Pulse Compression"\n'
        "created: 2026-07-02\n"
        "updated: 2026-07-02\n"
        "tags: [radar]\n"
        f"{related_line}\n"
        'sources: ["raw/Book/x.pdf"]\n'
        "---\n"
        f"{body}"
    )


def _run(rel_path: str, content: str, slug_dirs=None):
    """Run the normalizer, capturing stdout. Returns (new_content, printed)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = stage_3_1_normalize_page_links(rel_path, content, slug_dirs or SLUG_DIRS)
    return out, buf.getvalue()


class TestRelatedNormalization(unittest.TestCase):
    def test_strips_wikilink_wrapping_and_prefixes_bare_names(self):
        content = _page('related: ["[[concepts/matched-filter]]", "bell-labs"]')
        out, printed = _run(OWN, content)
        self.assertIn('related: ["concepts/matched-filter", "entities/bell-labs"]', out)
        self.assertIn("[normalize]", printed)

    def test_single_unquoted_wikilink_entry(self):
        # `related: [[concepts/matched-filter]]` parses to `[concepts/...]`
        # with stray single brackets — must still resolve, not be dropped.
        content = _page("related: [[concepts/matched-filter]]")
        out, _ = _run(OWN, content)
        self.assertIn('related: ["concepts/matched-filter"]', out)

    def test_unresolvable_entry_dropped_with_warn(self):
        content = _page('related: ["ghost-page", "concepts/matched-filter"]')
        out, printed = _run(OWN, content)
        self.assertIn('related: ["concepts/matched-filter"]', out)
        self.assertNotIn("ghost-page", out)
        self.assertIn("dropped 1 unresolvable", printed)
        self.assertIn("ghost-page", printed)

    def test_wrong_prefix_corrected_to_actual_dir(self):
        content = _page('related: ["entities/matched-filter"]')
        out, _ = _run(OWN, content)
        self.assertIn('related: ["concepts/matched-filter"]', out)

    def test_ambiguous_stem_kept_bare_with_warn(self):
        content = _page('related: ["both-ways"]')
        out, printed = _run(OWN, content)
        self.assertIn('related: ["both-ways"]', out)
        self.assertIn("ambiguous", printed)
        self.assertIn("both-ways", printed)

    def test_duplicates_collapse_after_normalization(self):
        content = _page('related: ["matched-filter", "concepts/matched-filter", "[[matched-filter]]"]')
        out, _ = _run(OWN, content)
        self.assertIn('related: ["concepts/matched-filter"]', out)
        self.assertEqual(out.count("concepts/matched-filter"), 1)

    def test_self_link_removed_from_related(self):
        content = _page('related: ["pulse-compression", "concepts/pulse-compression", "entities/bell-labs"]')
        out, printed = _run(OWN, content)
        self.assertIn('related: ["entities/bell-labs"]', out)
        self.assertIn("self-link", printed)

    def test_same_stem_in_other_dir_is_not_a_self_link(self):
        # Page concepts/both-ways relating to entities/both-ways is legitimate.
        content = _page('related: ["entities/both-ways"]')
        out, _ = _run("concepts/both-ways.md", content)
        self.assertIn('related: ["entities/both-ways"]', out)

    def test_block_form_related_normalized(self):
        content = (
            "---\n"
            "type: concept\n"
            'title: "X"\n'
            "related:\n"
            '  - "[[concepts/matched-filter]]"\n'
            "  - bell-labs\n"
            "tags: []\n"
            "---\n"
            "\n# Title\n"
        )
        out, _ = _run(OWN, content)
        self.assertIn('related: ["concepts/matched-filter", "entities/bell-labs"]', out)
        self.assertIn("tags: []", out)  # following field intact

    def test_absent_related_field_not_inserted(self):
        content = (
            "---\n"
            "type: concept\n"
            'title: "X"\n'
            "---\n"
            "\n# Title\n"
        )
        out, _ = _run(OWN, content)
        self.assertNotIn("related:", out)

    def test_sources_subdir_prefix_resolved_in_full(self):
        content = _page('related: ["radar-handbook"]')
        out, _ = _run(OWN, content)
        self.assertIn('related: ["sources/Book/radar-handbook"]', out)


class TestBodyWikilinks(unittest.TestCase):
    def test_bare_unique_link_gets_prefix(self):
        content = _page(body="\n# Title\n\nSee [[matched-filter]] for detail.\n")
        out, printed = _run(OWN, content)
        self.assertIn("[[concepts/matched-filter]]", out)
        self.assertIn("prefixed 1 bare wikilink", printed)

    def test_alias_preserved_when_prefixing(self):
        content = _page(body="\n# Title\n\n见 [[matched-filter|匹配滤波器]]。\n")
        out, _ = _run(OWN, content)
        self.assertIn("[[concepts/matched-filter|匹配滤波器]]", out)

    def test_anchor_preserved_when_prefixing(self):
        content = _page(body="\n# Title\n\nSee [[matched-filter#定义]].\n")
        out, _ = _run(OWN, content)
        self.assertIn("[[concepts/matched-filter#定义]]", out)

    def test_ambiguous_left_as_is_with_warn(self):
        content = _page(body="\n# Title\n\nSee [[both-ways]].\n")
        out, printed = _run(OWN, content)
        self.assertIn("[[both-ways]]", out)  # NOT de-linked, NOT prefixed
        self.assertIn("left as-is", printed)
        self.assertIn("[[both-ways]]", printed)

    def test_missing_left_as_is_with_warn(self):
        content = _page(body="\n# Title\n\nSee [[no-such-page]].\n")
        out, printed = _run(OWN, content)
        self.assertIn("[[no-such-page]]", out)  # never de-linked automatically
        self.assertIn("left as-is", printed)

    def test_already_prefixed_link_untouched(self):
        content = _page(body="\n# Title\n\nSee [[concepts/matched-filter]].\n")
        out, printed = _run(OWN, content)
        self.assertIn("[[concepts/matched-filter]]", out)
        self.assertEqual(printed, "")  # clean page → silent


class TestH1Stripping(unittest.TestCase):
    def test_h1_wikilinks_stripped_to_alias_text(self):
        content = _page(body="\n# 脉冲压缩 与 [[concepts/matched-filter|匹配滤波器]]\n\nBody.\n")
        out, printed = _run(OWN, content)
        self.assertIn("# 脉冲压缩 与 匹配滤波器\n", out)
        self.assertNotIn("# 脉冲压缩 与 [[", out)
        self.assertIn("H1: de-linked 1", printed)

    def test_h1_bare_wikilink_stripped_to_stem_text(self):
        content = _page(body="\n# [[matched-filter]]\n\nBody.\n")
        out, _ = _run(OWN, content)
        self.assertIn("# matched-filter\n", out)

    def test_h2_wikilinks_not_stripped(self):
        content = _page(body="\n# Title\n\n## See [[concepts/matched-filter]]\n")
        out, _ = _run(OWN, content)
        self.assertIn("## See [[concepts/matched-filter]]", out)


class TestSelfLinks(unittest.TestCase):
    def test_bare_self_link_delinked(self):
        content = _page(body="\n# Title\n\n另见 [[pulse-compression]]。\n")
        out, printed = _run(OWN, content)
        self.assertIn("另见 pulse-compression。", out)
        self.assertNotIn("[[pulse-compression]]", out)
        self.assertIn("self-link", printed)

    def test_prefixed_self_link_delinked(self):
        content = _page(body="\n# Title\n\n另见 [[concepts/pulse-compression]]。\n")
        out, _ = _run(OWN, content)
        self.assertIn("另见 pulse-compression。", out)

    def test_aliased_self_link_delinked_to_alias(self):
        content = _page(body="\n# Title\n\n另见 [[concepts/pulse-compression|脉冲压缩]]。\n")
        out, _ = _run(OWN, content)
        self.assertIn("另见 脉冲压缩。", out)

    def test_same_stem_other_dir_body_link_kept(self):
        # entities/marcum linking [[concepts/marcum]] is a cross-dir link,
        # not a self-link (prefixed non-self links are left as-is).
        slug_dirs = dict(SLUG_DIRS)
        slug_dirs["marcum"] = {"concepts", "entities"}
        content = _page(body="\n# Title\n\nSee [[concepts/marcum]].\n")
        out, _ = _run("entities/marcum.md", content, slug_dirs)
        self.assertIn("[[concepts/marcum]]", out)


class TestPassThrough(unittest.TestCase):
    CLEAN = (
        "---\n"
        "type: concept\n"
        'title: "脉冲压缩"\n'
        "created: 2026-07-01\n"
        "updated: 2026-07-02\n"
        "tags: [radar]\n"
        'related: ["concepts/matched-filter", "entities/bell-labs"]\n'
        'sources: ["raw/Book/x.pdf"]\n'
        "---\n"
        "\n"
        "# 脉冲压缩\n"
        "\n"
        "正文 [[concepts/matched-filter]] 与 [[entities/bell-labs|贝尔实验室]]。\n"
        "\n"
        "## See Also\n"
        "- [[concepts/matched-filter]]\n"
    )

    def test_clean_page_byte_identical_and_silent(self):
        out, printed = _run(OWN, self.CLEAN)
        self.assertEqual(out, self.CLEAN)
        self.assertEqual(printed, "")

    def test_clean_page_without_related_byte_identical(self):
        content = "---\ntype: concept\ntitle: \"X\"\n---\n\n# X\n\nPlain body, no links.\n"
        out, printed = _run(OWN, content)
        self.assertEqual(out, content)
        self.assertEqual(printed, "")

    def test_targeted_fix_leaves_rest_byte_identical(self):
        dirty = self.CLEAN.replace("[[entities/bell-labs|贝尔实验室]]", "[[bell-labs|贝尔实验室]]")
        out, _ = _run(OWN, dirty)
        self.assertEqual(out, self.CLEAN)  # only the targeted span changed


class TestUniverseBuilders(unittest.TestCase):
    def _make_wiki(self, root: Path) -> Path:
        wiki = root / "wiki"
        for rel in ("concepts/alpha.md", "entities/beta.md", "sources/Book/gamma.md",
                    "REVIEW/2026-07-02-item.md", "concepts/_audit_x.md", "index.md"):
            p = wiki / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("---\ntype: concept\n---\nbody\n", encoding="utf-8")
        return wiki

    def test_scan_wiki_slug_dirs_excludes_artifacts_anchors_and_system(self):
        with tempfile.TemporaryDirectory() as td:
            wiki = self._make_wiki(Path(td))
            config = SimpleNamespace(wiki_dir=wiki)
            got = _stage_3_1_scan_wiki_slug_dirs(config)
        self.assertEqual(got, {
            "alpha": {"concepts"},
            "beta": {"entities"},
            "gamma": {"sources/Book"},
        })

    def test_build_slug_dirs_unions_batch_with_disk(self):
        valid = {"sources", "concepts", "entities", "queries", "comparisons"}
        blocks = [
            ("concepts/new-concept.md", "---\ntype: concept\ntitle: N\n---\nbody"),
            # bare filename → auto-correct routes by frontmatter type
            ("Some Entity.md", "---\ntype: entity\ntitle: Some Entity\n---\nbody"),
            # wiki/ prefix → auto-correct strips it
            ("wiki/concepts/other.md", "---\ntype: concept\ntitle: O\n---\nbody"),
            ("index.md", "# Index"),           # listing page — excluded
        ]
        with tempfile.TemporaryDirectory() as td:
            wiki = self._make_wiki(Path(td))
            config = SimpleNamespace(wiki_dir=wiki)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                got = stage_3_1_build_slug_dirs(blocks, config, valid, {})
        self.assertEqual(got.get("new-concept"), {"concepts"})
        self.assertEqual(got.get("Some Entity"), {"entities"})
        self.assertEqual(got.get("other"), {"concepts"})
        self.assertNotIn("index", got)
        self.assertEqual(got.get("alpha"), {"concepts"})  # disk pages present
        self.assertEqual(buf.getvalue(), "")  # quiet pre-pass: no duplicate prints


if __name__ == "__main__":
    unittest.main()
