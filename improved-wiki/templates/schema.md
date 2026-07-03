# Schema

## Page Types

| type | directory |
|------|-----------|
| source | wiki/sources |
| concept | wiki/concepts |
| entity | wiki/entities |
| query | wiki/queries |
| comparison | wiki/comparisons |
| synthesis | wiki/synthesis |
| finding | wiki/findings |
| thesis | wiki/thesis |
| methodology | wiki/methodology |

> 本模板只列出 ingest 解析器从项目 `schema.md` 读取的 `## Page Types` → 目录路由（`_core.py::_parse_page_types`）。一个项目**根**下的实际 `schema.md` 还会携带命名/文件名规则——尤其是**严禁逗号**（raw 文件名与 wiki 页名都不得含 `,`/`，`，逗号会按逗号切分书名致断链，一律改 ` - `）以及供 `normalize_raw_names.py` 消费的 `rules:` YAML 块。权威规则见 `references/naming-conventions.md` 与 `references/raw-naming-conventions.md`。
