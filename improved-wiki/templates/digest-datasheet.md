# digest-datasheet.md — Ingest template for component datasheets

> **Use this template** when a file lives at `raw/datasheet/<...>/*.pdf`.
> Datasheets are heavily structured (tables, figures, pinouts). The Ingest focuses on extracting the "key specs" table, electrical characteristics, and typical application topology. The output is a source page + a few concepts + ALWAYS an entity page for the part number.

---

## What the LLM is asked to produce

### Step 1: Analysis

```yaml
part_meta:
  part_number: "<e.g. TPS54360>"
  manufacturer: "<e.g. Texas Instruments>"
  family: "<e.g. TPS54360 family — buck converters>"
  package: "<e.g. HTSSOP-8>"
  datasheet_rev: "<e.g. SLVSAS5A — March 2018>"
  status: "active" | "NRND" | "obsolete" | "preview"

key_specs:
  # The single most important table — quoted verbatim from the datasheet
  category: "operating_rating" | "electrical_char" | "thermal" | "package"
  specs:
    - parameter: "<e.g. Input voltage range>"
      min: "<value>"
      typ: "<value>"
      max: "<value>"
      unit: "<V>"
      conditions: "<e.g. TA = 25°C>"

# For multiple spec categories, repeat key_specs:
# - category: "electrical_char"  (electrical characteristics table)
# - category: "thermal"          (thermal performance)
# - category: "package"          (mechanical / pinout)

pin_function_summary:
  - pin: "<name + number, e.g. VIN (pin 1)>"
    function: "<one-line description>"
  - pin: "<...>"

typical_application:
  topology: "<e.g. Synchronous Buck Converter>"
  input_range: "<e.g. 4.5V to 60V>"
  output: "<e.g. 3.3V @ 3.5A>"
  switching_frequency: "<e.g. 100kHz to 2.5MHz>"
  key_passive_components:
    - role: "input cap"
      typical_value: "<e.g. 1µF X7R>"
    - role: "inductor"
      typical_value: "<e.g. 10µH>"
    - role: "feedback divider"
      typical_value: "<e.g. R1=10kΩ, R2=3.16kΩ>"

features:
  # Marketing-style features, but written as engineering capabilities
  - "Wide input voltage range: 4.5V to 60V"
  - "..."
  
  # Mark which are actually differentiators vs commodity
  differentiators: ["..."]  # only the genuinely distinctive ones

protection_features:
  - "OCP (over-current protection)"
  - "OVP (over-voltage protection)"
  - "OTP (over-temperature protection)"
  - "UVLO (under-voltage lockout)"

applications_marketed:    # what the vendor says it's for
  - "Industrial PLC"
  - "..."

key_entities:
  - name: "<e.g. Texas Instruments>"
    role: "organization"
    wikilink_target: "Texas-Instruments"
  - name: "<e.g. TPS54360>"
    role: "model"  # a specific part number is an "entity" in our scheme
    wikilink_target: "TPS54360"

key_concepts:
  # Concepts that the datasheet uses / teaches / assumes
  - name: "Synchronous Buck Converter"
    importance: "core"
    wikilink_target: "synchronous-buck-converter"
  - name: "Current Mode Control"
    importance: "supporting"
    wikilink_target: "current-mode-control"

key_claims:    # the datasheet's spec claims — these are the "data points"
  - claim: "Efficiency peaks at 95% at 24Vin → 5Vout @ 1A"
    evidence: "Fig 6-1 (efficiency curve), SLVSAS5A datasheet, p. 7"
    section: "Typical Characteristics"

# What's MISSING from the datasheet — important for Lint to flag
known_limitations:
  - "No mention of EMI performance"
  - "No MTBF / reliability data"

# Cross-refs to vendor's other docs
companion_documents:
  - name: "TPS54360EVM User's Guide"
    url: "<slvu..."
  - name: "Application Note SLVA477"
    title: "Synchronous Buck Loop Compensation"
```

### Step 2: Generation

Files to write:

1. **`wiki/sources/<Mfr> - <Part-Number>.md`** — source page
   - Body: part metadata, key specs tables, pin function summary, typical application, features/protection, "参见" with concept + entity pages

2. **`wiki/entities/<Part-Number>.md`** — entity page for the part
   - Frontmatter: `type: entity`
   - Body: brief description, package, datasheet rev, status, key specs summary, "参见" with vendor, with related parts, with relevant concept pages

3. **`wiki/entities/<Manufacturer>.md`** — entity page for the manufacturer (if not already exists)
   - Frontmatter: `type: entity`
   - Body: vendor description, related product lines, "参见"

4. **`wiki/concepts/<slug>.md`** — concept pages for the 2-5 key concepts the datasheet uses
   - Only if they don't already exist

5. **Update `wiki/index.md`**, **`wiki/log.md`**, **`wiki/overview.md`**

---

## Prompt template (the actual prompt sent to the LLM)

```
# Role
You are the LLM maintainer of a Karpathy-pattern personal knowledge base.
You ingest component datasheets into a structured wiki.

# Input
- Part number: {part_number}
- Manufacturer: {manufacturer}
- File path: {raw_path}
- Extracted text: <full text in <extracted_text>...</extracted_text>>
- Existing wiki context: <slugs in <existing_wiki>...</existing_wiki>>

# Task
Two-step chain.

## Step 1: Analysis
YAML block with the full analysis. Use the schema in §Analysis above.
A datasheet is expected to produce 1 source page + 1-2 entity pages (the part, sometimes the manufacturer) + 1-3 concept pages.

## Step 2: Generation
File contents in order:
### File 1: wiki/sources/<Mfr> - <Part-Number>.md
### File 2: wiki/entities/<Part-Number>.md (the part itself is an entity)
### File 3 (optional): wiki/entities/<Manufacturer>.md (only if not already in wiki)
### File 4..N: wiki/concepts/<slug>.md (1-3 files)
### Update: wiki/index.md
### Append: wiki/log.md

# Constraints
- Every `[[wikilink]]` MUST use the FULL filename stem (per improved-wiki §6.2)
- Frontmatter must follow improved-wiki §5
- Quoted spec values must be from the datasheet, not from general knowledge
- Use a markdown table for the key_specs (not bullet lists)
- The pin_function_summary should be a markdown table
- Mark all known_limitations in the source page
- Cross-reference companion_documents as wikilinks if the corresponding wiki page exists
```

---

## Type-specific guidance

- **Don't bloat with marketing**: datasheets often have 20+ "feature" bullets. Extract 3-7 genuine differentiators, not the full marketing list.
- **Key specs table is the source of truth**: most datasheet users come back for the specs table. Make it the first thing after metadata in the source page.
- **Part-number as entity page**: every part number gets its own `wiki/entities/<Part-Number>.md` page. This makes them linkable from concept pages ("used in design X", "see also TPS54331"). Datasheets that mention 5+ other parts will generate cross-refs naturally.
- **Companion docs**: vendor app notes and reference designs often pair with a datasheet. If the user already ingested them, the datasheet source page should link to them.

---

## Common pitfalls when ingesting datasheets

| Symptom | Fix |
|---|---|
| LLM produces 10+ "feature" bullets from marketing | Tighten prompt: "Extract at most 5 differentiators. Distinguish what makes this part BETTER than competitors from what is standard for the category" |
| Spec values are wrong (LLM hallucinated) | The analysis must say "this value is from page X table Y" for every spec. Re-Ingest if values don't match the source text |
| Pin function table is missing or wrong | Pin tables are highly tabular. minerU VLM usually extracts them well. If not, flag the source as OCR-failed and only ingest the front-matter sections |
| The datasheet has many "ordering information" tables (variants) | Don't extract all variants. The entity page should describe the family; only ingest the specific part as the main entity |

---

## See also

- `SKILL.md` §5, §6
- `templates/digest-applicationnote.md` — vendor app notes (the typical companion doc)
- `templates/digest-designexample.md` — reference designs (another typical companion)
