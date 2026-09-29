---
name: obsidian-bases
description: Use when creating or editing Obsidian Bases (.base) files with YAML schema, filters, formulas, computed properties, views (table, cards, list, map), summaries, file properties, date arithmetic, and duration math. Not for regular Markdown notes or non-Obsidian database views.
---

# Obsidian Bases

## Overview
Bases are YAML-based database views in Obsidian. A `.base` file defines filters, formulas, views, and summaries to organize and display notes.

## Workflow
1. **Create** a `.base` file with valid YAML.
2. **Define scope** via `filters` (tag, folder, property, date).
3. **Add formulas** (optional computed properties).
4. **Configure views** (`table`, `cards`, `list`, `map`) with `order`.
5. **Validate** YAML syntax, check referenced properties/formulas.
6. **Test** in Obsidian – open `.base` file to confirm rendering.

## Schema (YAML Structure)
```yaml
filters:          # Global filters (single string or recursive object with and/or/not)
formulas:         # Computed properties
  formula_name: 'expression'
properties:       # Display names & settings for properties
  property_name:
    displayName: "Display Name"
summaries:        # Custom summary formulas
  custom_summary: 'values.mean().round(3)'
views:            # One or more views
  - type: table | cards | list | map
    name: "View Name"
    limit: 10
    groupBy:
      property: property_name
      direction: ASC | DESC
    filters:      # View-specific filters (same rules as global)
    order:        # Properties to display
      - file.name
      - property_name
      - formula.formula_name
    summaries:    # Map properties to summary formulas
      property_name: Average
```

## Filter Syntax
- **Single filter**: `filters: 'status == "done"'`
- **AND**: `filters: { and: [ ... ] }`
- **OR**: `filters: { or: [ ... ] }`
- **NOT**: `filters: { not: [ ... ] }`
- **Nested**: combine `and`/`or`/`not` recursively.

### Filter Operators
| Operator | Description |
|----------|-------------|
| `==` | equals |
| `!=` | not equal |
| `>` / `<` | greater / less |
| `>=` / `<=` | greater or equal / less or equal |
| `&&` | logical and |
| `\|\|` | logical or |
| `!` | logical not |

## Properties
### Three Types
1. **Note properties** – from frontmatter: `note.author` or just `author`
2. **File properties** – metadata: `file.name`, `file.mtime`, etc.
3. **Formula properties** – computed: `formula.my_formula`

### File Properties Reference
| Property | Type | Description |
|----------|------|-------------|
| `file.name` | String | File name |
| `file.basename` | String | Name without extension |
| `file.path` | String | Full path |
| `file.folder` | String | Parent folder |
| `file.ext` | String | Extension |
| `file.size` | Number | Size in bytes |
| `file.ctime` | Date | Created time |
| `file.mtime` | Date | Modified time |
| `file.tags` | List | All tags |
| `file.links` | List | Internal links |
| `file.backlinks` | List | Files linking to this |
| `file.embeds` | List | Embeds |
| `file.properties` | Object | All frontmatter |

### The `this` Keyword
- In main content area → refers to the base file itself.
- When embedded → refers to the embedding file.
- In sidebar → refers to the active file in main content.

## Formula Syntax
Defined in `formulas` section. Examples:
```yaml
formulas:
  total: "price * quantity"
  status_icon: 'if(done, "✅", "⏳")'
  formatted_price: 'if(price, price.toFixed(2) + " dollars")'
  created: 'file.ctime.format("YYYY-MM-DD")'
  days_old: '(now() - file.ctime).days'
  days_until_due: 'if(due_date, (date(due_date) - today()).days, "")'
```

### Key Functions
| Function | Signature | Description |
|----------|-----------|-------------|
| `date()` | `date(string): date` | Parse string to date (`YYYY-MM-DD HH:mm:ss`) |
| `now()` | `now(): date` | Current date and time |
| `today()` | `today(): date` | Current date (time = 00:00:00) |
| `if()` | `if(condition, trueResult, falseResult?)` | Conditional |
| `duration()` | `duration(string): duration` | Parse duration string |
| `file()` | `file(path): file` | Get file object |
| `link()` | `link(path, display?): Link` | Create a link |

### Duration Type
- Subtracting two dates returns a **Duration** (not a number).
- Fields: `.days`, `.hours`, `.minutes`, `.seconds`, `.milliseconds`
- **IMPORTANT**: Do not call `.round()`, `.floor()`, `.ceil()` directly on Duration. Access a numeric field first (e.g., `.days`), then apply number functions.
```yaml
# CORRECT
"(date(due_date) - today()).days.round(0)"
# WRONG
"((date(due) - today()) / 86400000).round(0)"
```

### Date Arithmetic
```yaml
"now() + \"1 day\""   # Tomorrow
"today() + \"7d\""    # A week from today
"(now() - file.ctime).days"  # Days as number
```
Duration units: `y/year/years`, `M/month/months`, `d/day/days`, `w/week/weeks`, `h/hour/hours`, `m/minute/minutes`, `s/second/seconds`.

## View Types
### Table View
```yaml
views:
  - type: table
    name: "My Table"
    order:
      - file.name
      - status
      - due_date
    summaries:
      price: Sum
      count: Average
```
### Cards View
```yaml
views:
  - type: cards
    name: "Gallery"
    order:
      - file.name
      - cover_image
      - description
```
### List View
```yaml
views:
  - type: list
    name: "Simple List"
    order:
      - file.name
      - status
```
### Map View
Requires latitude/longitude properties and the Maps community plugin.

## Default Summary Formulas
| Name | Formula |
|------|---------|
| Sum | `values.sum()` |
| Average | `values.average()` |
| Count | `values.length` |
| Count Unique | `values.unique().length` |
| Count Empty | `values.filter(v => !v).length` |
| Count Not Empty | `values.filter(v => v).length` |
| Earliest | `values.min()` |
| Latest | `values.max()` |
| Percent Empty | `values.filter(v => !v).length / values.length * 100` |
| Percent Not Empty | `values.filter(v => v).length / values.length * 100` |

## Complete Example
```yaml
---
filters:
  and:
    - 'status != "archived"'
    - 'priority > 2'
formulas:
  days_until_due: 'if(due_date, (date(due_date) - today()).days, "No due date")'
  formatted_date: 'file.ctime.format("YYYY-MM-DD")'
properties:
  status:
    displayName: "Project Status"
  priority:
    displayName: "Priority Level"
views:
  - type: table
    name: "Active Projects"
    limit: 20
    groupBy:
      property: status
      direction: ASC
    order:
      - file.name
      - status
      - priority
      - formula.days_until_due
    summaries:
      priority: Average
  - type: list
    name: "Quick View"
    limit: 10
    order:
      - file.name
      - status
---
```

## References
- [Obsidian Bases documentation](https://help.obsidian.md/bases/syntax)