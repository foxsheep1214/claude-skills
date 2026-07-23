"""Wiki schema routing, page discovery, and safe ingest paths."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from _paths import WIKI_ARTIFACT_DIRS

if TYPE_CHECKING:
    from _config import Config


_LINT_STUB_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_LINT_STUB_TYPE_RE = re.compile(r"^type:\s*['\"]?query['\"]?\s*$", re.MULTILINE)
_LINT_STUB_TAGS_RE = re.compile(r"^tags:\s*\[([^\]\n]*)\]", re.MULTILINE)


def _is_lint_stub_page(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            head = handle.read(512)
    except OSError:
        return False
    if not head.startswith("---") or not _LINT_STUB_TYPE_RE.search(head):
        return False
    match = _LINT_STUB_TAGS_RE.search(head)
    if not match:
        return False
    tags = {
        value.strip().strip("'\"").lower()
        for value in match.group(1).split(",")
    }
    return bool({"stub", "lint"} & tags)


def list_existing_slugs(config: Config) -> list[str]:
    """Return deterministic knowledge-page stems, excluding derived artifacts."""
    if not config.wiki_dir.exists():
        return []
    anchors = {"index", "log", "overview", "schema"}
    slugs: list[str] = []
    for path in config.wiki_dir.rglob("*.md"):
        if WIKI_ARTIFACT_DIRS.intersection(path.parts):
            continue
        stem = path.stem
        if stem.startswith("_") or stem in anchors:
            continue
        if path.parent.name == "queries" and _LINT_STUB_DATE_RE.match(stem):
            continue
        if _is_lint_stub_page(path):
            continue
        slugs.append(stem)
    slugs.sort()
    return slugs


BASE_PAGE_DIRS = {
    "sources",
    "concepts",
    "entities",
    "queries",
    "comparisons",
    "synthesis",
    "findings",
    "thesis",
    "methodology",
}


def load_schema_md(config: Config) -> str:
    for path in (config.wiki_root / "schema.md", config.wiki_dir / "schema.md"):
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except OSError:
            pass
    return ""


def schema_folders(schema_text: str) -> set[str]:
    """Return folder names declared as ``wiki/<folder>`` in schema text."""
    return set(
        re.findall(
            r"wiki/([a-z0-9][a-z0-9_-]*)/?(?!\.)",
            schema_text or "",
        )
    )


BASE_TYPE_TO_DIR = {
    "source": "sources",
    "concept": "concepts",
    "entity": "entities",
    "query": "queries",
    "comparison": "comparisons",
    "synthesis": "synthesis",
    "finding": "findings",
    "thesis": "thesis",
    "methodology": "methodology",
}

_SCHEMA_TYPE_RE = re.compile(r"^[a-z][a-z0-9_-]*$", re.IGNORECASE)


def parse_wiki_schema_routing(schema_text: str) -> dict[str, str]:
    """Parse the Page Types table into ``{frontmatter_type: bare_folder}``."""
    lines = (schema_text or "").split("\n")
    start, heading_level = -1, 6
    for index, raw in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", raw.strip())
        if match and re.match(
            r"^page\s+types$",
            match.group(2).strip(),
            re.IGNORECASE,
        ):
            start, heading_level = index, len(match.group(1))
            break
    if start < 0:
        return {}

    type_dirs: dict[str, str] = {}
    for raw in lines[start + 1 :]:
        heading = re.match(r"^(#{1,6})\s+", raw.strip())
        if heading and len(heading.group(1)) <= heading_level:
            break
        if not raw.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in raw.split("|")[1:-1]]
        if len(cells) < 2:
            continue
        page_type, page_dir = cells[0], cells[1]
        if not _SCHEMA_TYPE_RE.match(page_type):
            continue
        if page_dir != "wiki" and not page_dir.startswith("wiki/"):
            continue
        bare = (
            "" if page_dir == "wiki" else page_dir[len("wiki/") :]
        ).rstrip("/")
        if bare.startswith("/") or any(part == ".." for part in bare.split("/")):
            continue
        type_dirs[page_type] = bare
    return type_dirs


def schema_route_dir(
    frontmatter_type: str,
    routing: dict[str, str],
) -> str | None:
    if not frontmatter_type:
        return None
    if frontmatter_type in routing:
        return routing[frontmatter_type]
    return BASE_TYPE_TO_DIR.get(frontmatter_type)


_WINDOWS_RESERVED = {"con", "prn", "aux", "nul"}
for _index in range(1, 10):
    _WINDOWS_RESERVED.add(f"com{_index}")
    _WINDOWS_RESERVED.add(f"lpt{_index}")

_ILLEGAL_CHARS_RE = re.compile(r'[<>:"|?*\x00-\x1f]')


def is_safe_ingest_path(rel_path: str) -> bool:
    """Apply NashSU-compatible cross-platform path-safety checks."""
    if not rel_path or _ILLEGAL_CHARS_RE.search(rel_path):
        return False
    if rel_path.startswith(("/", "\\")):
        return False
    if len(rel_path) >= 2 and rel_path[1] == ":":
        return False
    if ".." in rel_path.split("/") or ".." in rel_path.split("\\"):
        return False
    for segment in rel_path.replace("\\", "/").split("/"):
        if not segment:
            continue
        if segment.endswith((" ", ".")):
            return False
        stem = segment.split(".", 1)[0].lower()
        if segment.lower() in _WINDOWS_RESERVED or stem in _WINDOWS_RESERVED:
            return False
    name = Path(rel_path).name
    base = name[:-3] if name.endswith(".md") else Path(rel_path).stem
    base = base.strip().strip(".").lower()
    if base in ("", "-", "--", "none", "null", "undefined", "n-a", "n/a"):
        return False
    if re.match(r"^\(.*\)$", base):
        return False
    return True


def source_slug_from_raw_path(
    raw_path: str | Path,
    wiki_root: str | Path,
) -> Path | None:
    """Derive ``wiki/sources/<relative raw path>.md`` for dedup checks."""
    root = Path(wiki_root).expanduser()
    path = Path(raw_path).expanduser()
    raw_root = root / "raw"
    if not path.is_absolute():
        path = raw_root / path
    try:
        relative = path.relative_to(raw_root).with_suffix(".md")
        if ".." in relative.parts:
            return None
    except ValueError:
        return None
    return root / "wiki" / "sources" / relative


__all__ = [
    "BASE_PAGE_DIRS",
    "BASE_TYPE_TO_DIR",
    "is_safe_ingest_path",
    "list_existing_slugs",
    "load_schema_md",
    "parse_wiki_schema_routing",
    "schema_folders",
    "schema_route_dir",
    "source_slug_from_raw_path",
]
