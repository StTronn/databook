# Block reference

| Block | Header | Body | Produces |
|---|---|---|---|
| sql | ```` ```sql <id> ```` | one query (SELECT / WITH / FROM / VALUES / PIVOT); may read imported tables and other blocks | table `<id>` |
| python | ```` ```python <id> ```` | function body; names of tables/blocks it mentions are DataFrames; `pd`, `Decimal`, `TZ` predefined; `return` a DataFrame (index is kept via reset_index) | table `<id>` |
| sheet | ```` ```sheet <id> ```` | YAML: `file`, `inputs {Sheet!A1: block.col \| number}`, `outputs {Sheet!A1: name}`, `show Sheet!A1:C9` | 1-row table `<id>` of outputs + rendered range |
| kpi | ```` ```kpi ```` | YAML list of `{label, value: block.col, format?, compare?: block.col}` | cards (pct deltas in pp) |
| chart | ```` ```chart ```` | YAML `{type, data: block, x: col, y: col \| [cols], variant?, format?, title?, description?}`; types/variants/combo: `databook components` | chart card with Chart/Table tabs (≤1000 rows) |
| table | ```` ```table ```` | YAML `{data: block, columns?: [..], sort?: "col desc", limit?, format?: {col: fmt}}` | table |

Order in the file doesn't matter for computation; blocks run in dependency order. Ids must be unique and must not
equal an imported table name. Deleting or renaming a block drops its table on the next run.

Diagnostic codes: REF_UNKNOWN, CYCLE, DUPLICATE_ID, MISSING_ID, UNCLOSED_FENCE, BAD_SPEC, BAD_FRONTMATTER, SQL_ERROR,
PY_ERROR, PY_NOT_DATAFRAME, PY_BAD_COLUMNS, SHEET_FILE_MISSING, SHEET_INPUT_IS_FORMULA, SHEET_FORMULA_ERROR,
SHEET_UNSUPPORTED_FN, INTERP_MULTIROW, CHART_COLUMN_MISSING, CHART_DUPLICATE_X, CHART_NOT_NUMERIC, CHART_NEGATIVE, CHART_NEEDS_ONE_ROW, CHART_BAND_ORDER, BAD_FENCE, LITERAL_NUMBER_IN_PROSE, PII_COLUMN_PUBLISHED (warning),
CHART_TRUNCATED (warning).

Import types for `--types col=<type>`: text, int, bool, money, decimal:N, json, timestamp, date:dmy, date:mdy,
local:dmy (naive local time in project TZ → TIMESTAMPTZ), unix (epoch seconds → TIMESTAMPTZ).
