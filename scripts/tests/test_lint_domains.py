"""Tests for _lint_domains — domain-list de-hardcoding (round ii, point ①).

Verifies:
  * parse_domains_md extracts the first backticked slug per table row.
  * load_valid_domains prefers <project>/wiki/domains.md over the skill default.
  * Falls back to the skill default when no project-level file exists.
  * Returns an empty set (lenient signal) when neither file parses.
"""
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _lint_domains as ld  # noqa: E402


SKILL_DEFAULT_MD = """# Domains

| domain slug | name | notes |
|---|---|---|
| `circuit-fundamentals` | 电路基础 | resistors |
| `rf-microwave` | 射频微波 | S-params |
| `general` | 通用 | cross-domain |

Some prose with `not-a-row` here.
"""


class TestParseDomainsMd(unittest.TestCase):
    def test_extracts_first_backticked_cell_per_row(self):
        slugs = ld.parse_domains_md(SKILL_DEFAULT_MD)
        self.assertEqual(slugs, {"circuit-fundamentals", "rf-microwave", "general"})

    def test_ignores_backticked_tokens_in_prose(self):
        text = "see `foo-bar` inline\n| `real-slug` | x | y |\n"
        self.assertEqual(ld.parse_domains_md(text), {"real-slug"})

    def test_empty_when_no_table(self):
        self.assertEqual(ld.parse_domains_md("# just prose\nno table here"), set())

    def test_lowercases_slugs(self):
        text = "| `Power-Electronics` | x | y |\n"
        self.assertEqual(ld.parse_domains_md(text), {"power-electronics"})


class TestLoadValidDomains(unittest.TestCase):
    def test_project_override_wins(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            skill_root = root / "skill"
            (skill_root / "references").mkdir(parents=True)
            (skill_root / "references" / "domains.md").write_text(
                "| `skill-default` | x | y |\n", encoding="utf-8")
            (root / "wiki").mkdir()
            (root / "wiki" / "domains.md").write_text(
                "| `project-a` | x | y |\n| `project-b` | x | y |\n",
                encoding="utf-8")
            result = ld.load_valid_domains(root, skill_root)
            self.assertEqual(result, {"project-a", "project-b"})

    def test_falls_back_to_skill_default(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            skill_root = root / "skill"
            (skill_root / "references").mkdir(parents=True)
            (skill_root / "references" / "domains.md").write_text(
                "| `skill-default` | x | y |\n", encoding="utf-8")
            result = ld.load_valid_domains(root, skill_root)
            self.assertEqual(result, {"skill-default"})

    def test_empty_set_when_neither_parses(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            skill_root = root / "skill"
            result = ld.load_valid_domains(root, skill_root)
            self.assertEqual(result, set())

    def test_reads_actual_skill_default(self):
        # The real skill references/domains.md must parse to a non-empty set
        # containing the canonical hardware domains.
        skill_root = _SCRIPTS_DIR.parent
        with tempfile.TemporaryDirectory() as t:
            result = ld.load_valid_domains(Path(t), skill_root)
        self.assertIn("thermal-management", result)
        self.assertIn("rf-microwave", result)
        self.assertIn("general", result)


if __name__ == "__main__":
    unittest.main()
