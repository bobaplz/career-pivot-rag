# SQL Reference: Core Concepts & The Mistakes Everyone Makes

A practical reference covering how SQL actually works, the patterns that matter in real analytics work, and the mistakes that bite even experienced analysts. Organized so the "why" behind each gotcha is clear, not just the rule.

---

## Table of Contents

1. [The One Thing That Explains Everything: Logical Execution Order](#1-logical-execution-order)
2. [NULL: Three-Valued Logic](#2-null-three-valued-logic)
3. [JOINs and the Fan-Out Trap](#3-joins-and-the-fan-out-trap)
4. [GROUP BY and Aggregation](#4-group-by-and-aggregation)
5. [Window Functions](#5-window-functions)
6. [Subqueries and CTEs](#6-subqueries-and-ctes)
7. [Dates, Times, and Timezones](#7-dates-times-and-timezones)
8. [Data Types and Implicit Conversion](#8-data-types-and-implicit-conversion)
9. [DISTINCT, UNION, and Set Operations](#9-distinct-union-and-set-operations)
10. [Strings and Pattern Matching](#10-strings-and-pattern-matching)
11. [Performance: Writing SARGable, Index-Friendly SQL](#11-performance)
12. [Correctness Habits That Prevent Production Incidents](#12-correctness-habits)
13. [Quick-Reference: Top 20 Mistakes Checklist](#13-top-20-mistakes-checklist)

---

## 1. Logical Execution Order

SQL is written in one order but executed in another. Most "why doesn't this work?" questions trace back to this single fact.

**Written order:**
```
SELECT → FROM → WHERE → GROUP BY → HAVING → ORDER BY → LIMIT
```

**Logical execution order:**
```
FROM / JOIN → WHERE → GROUP BY → HAVING → SELECT (incl. window functions) → DISTINCT → ORDER BY → LIMIT
```

### What this explains

**Mistake 1.1 — Using a SELECT alias in WHERE.**
```sql
SELECT premium * 1.1 AS adjusted_premium
FROM policies
WHERE adjusted_premium > 1000;   -- ERROR in most databases
```
WHERE runs before SELECT, so the alias doesn't exist yet. Repeat the expression or use a CTE/subquery. (Aliases *do* work in ORDER BY, because ORDER BY runs after SELECT. Some databases like MySQL and Postgres allow aliases in GROUP BY as a convenience — don't rely on it if you write cross-platform SQL.)

**Mistake 1.2 — Using a window function in WHERE.**
```sql
WHERE ROW_NUMBER() OVER (...) = 1   -- ERROR
```
Window functions are evaluated during the SELECT phase. Wrap in a CTE and filter outside, or use `QUALIFY` (Snowflake, BigQuery, Databricks).

**Mistake 1.3 — Confusing WHERE and HAVING.**
- `WHERE` filters **rows before** grouping.
- `HAVING` filters **groups after** aggregation.

```sql
-- Wrong: aggregate in WHERE
SELECT state, COUNT(*) FROM policies
WHERE COUNT(*) > 100      -- ERROR
GROUP BY state;

-- Right
SELECT state, COUNT(*) FROM policies
GROUP BY state
HAVING COUNT(*) > 100;
```
Performance note: put non-aggregate conditions in WHERE, not HAVING — filtering earlier means grouping less data.

**Mistake 1.4 — Expecting ordered results without ORDER BY.**
Tables have no inherent order. Results that "happen to come back sorted" (clustered index, small table, cached plan) will change under parallelism or data growth. If order matters, say so — and note that `ORDER BY` in a subquery/CTE/view generally does **not** guarantee order in the outer query.

---

## 2. NULL: Three-Valued Logic

NULL means "unknown," not "empty" or "zero." Every comparison with NULL yields `UNKNOWN`, and `WHERE` only passes rows that evaluate to `TRUE`. This one concept produces more silent bugs than anything else in SQL.

**Mistake 2.1 — `= NULL` and `<> NULL`.**
```sql
WHERE status = NULL     -- always returns zero rows
WHERE status <> NULL    -- also zero rows
```
Use `IS NULL` / `IS NOT NULL`.

**Mistake 2.2 — `<>` silently excludes NULLs.**
```sql
WHERE status <> 'Cancelled'
```
This drops rows where status is NULL — `NULL <> 'Cancelled'` is UNKNOWN, not TRUE. If NULLs should be kept:
```sql
WHERE status <> 'Cancelled' OR status IS NULL
-- or: WHERE COALESCE(status, '') <> 'Cancelled'
```

**Mistake 2.3 — `NOT IN` with a NULL in the list (the classic).**
```sql
SELECT * FROM policies
WHERE policy_id NOT IN (SELECT policy_id FROM cancellations);
```
If `cancellations.policy_id` contains even one NULL, this returns **zero rows**. Why: `x NOT IN (a, b, NULL)` expands to `x <> a AND x <> b AND x <> NULL`, and `x <> NULL` is UNKNOWN, poisoning the whole AND chain.

Fix — use `NOT EXISTS` (NULL-safe and usually faster):
```sql
SELECT p.* FROM policies p
WHERE NOT EXISTS (
  SELECT 1 FROM cancellations c WHERE c.policy_id = p.policy_id
);
```

**Mistake 2.4 — Aggregates ignore NULL (except COUNT(*)).**
- `COUNT(*)` counts rows. `COUNT(col)` counts non-NULL values. These differ, and the difference is often exactly what you're trying to measure.
- `AVG(col)` divides by the count of **non-NULL** values, not total rows. `AVG(score)` over (10, 20, NULL) is 15, not 10. If NULL means zero in your context, `AVG(COALESCE(score, 0))`.
- `SUM()` of an empty/all-NULL set returns NULL, not 0. Guard with `COALESCE(SUM(x), 0)`.

**Mistake 2.5 — NULL in GROUP BY and DISTINCT behaves differently than in comparisons.**
GROUP BY and DISTINCT treat all NULLs as one group/value (they use "distinctness," not equality). So `NULL = NULL` is UNKNOWN, but GROUP BY puts all NULLs in a single bucket. Know which semantics you're getting.

**Mistake 2.6 — Concatenation and arithmetic with NULL.**
`'Hello ' || NULL` → NULL (Postgres/Oracle standard behavior). `price + NULL` → NULL. One NULL column can wipe out a computed field for the whole row. COALESCE defensively.

**Mistake 2.7 — Division by zero and NULL denominators.**
```sql
-- Robust ratio pattern:
SELECT numerator / NULLIF(denominator, 0) AS ratio
```
`NULLIF(x, 0)` returns NULL when x = 0, converting a hard error into a NULL you can COALESCE or leave as "undefined."

---

## 3. JOINs and the Fan-Out Trap

**Mistake 3.1 — Fan-out: joining one-to-many then aggregating (the #1 silent metric inflator).**
```sql
-- Each policy has multiple claims; premium gets duplicated per claim:
SELECT SUM(p.premium)
FROM policies p
JOIN claims c ON c.policy_id = p.policy_id;   -- premium counted once PER CLAIM
```
Any time you join to a table where the key isn't unique, rows multiply. Aggregates computed after that join are inflated — and it often looks plausible enough to ship.

Fixes:
- Aggregate the many-side **first**, then join:
```sql
SELECT SUM(p.premium), SUM(c.claim_total)
FROM policies p
LEFT JOIN (
  SELECT policy_id, SUM(amount) AS claim_total
  FROM claims GROUP BY policy_id
) c ON c.policy_id = p.policy_id;
```
- Or use `COUNT(DISTINCT ...)` / conditional aggregation where appropriate.
- **Sanity check habit:** compare row counts before and after every join. If `COUNT(*)` grew and you didn't expect it, you have fan-out.

**Mistake 3.2 — Putting the right-table filter in WHERE and turning a LEFT JOIN into an INNER JOIN.**
```sql
-- Intended: all policies, with 2026 claims where they exist
SELECT p.policy_id, c.amount
FROM policies p
LEFT JOIN claims c ON c.policy_id = p.policy_id
WHERE c.claim_year = 2026;    -- BUG: drops policies with no claims
```
For unmatched rows, `c.claim_year` is NULL; `NULL = 2026` is UNKNOWN; WHERE removes the row. The LEFT JOIN is silently converted to an INNER JOIN.

Fix — put right-table conditions in the ON clause:
```sql
LEFT JOIN claims c
  ON c.policy_id = p.policy_id
 AND c.claim_year = 2026;
```
Rule of thumb: **for LEFT JOIN, conditions on the left table go in WHERE; conditions on the right table go in ON.** (For INNER JOIN it doesn't matter for correctness.)

**Mistake 3.3 — Anti-join done wrong.**
"Policies with no claims":
```sql
-- Correct patterns:
LEFT JOIN claims c ON ... WHERE c.policy_id IS NULL
-- or NOT EXISTS (preferred; NULL-safe, clear intent)
```
Avoid `NOT IN` per Mistake 2.3.

**Mistake 3.4 — NULLs never match in join conditions.**
`ON a.key = b.key` never matches when either side is NULL — those rows silently drop from an INNER JOIN. If NULL keys are meaningful, handle explicitly (`ON a.key = b.key OR (a.key IS NULL AND b.key IS NULL)`, or `IS NOT DISTINCT FROM` where supported).

**Mistake 3.5 — Accidental cross join / missing join condition.**
Forgetting one ON condition in a composite key join (`ON a.state = b.state` when it should be state + year) produces partial fan-out that's hard to spot. Comma-style joins (`FROM a, b WHERE ...`) make this worse — one forgotten WHERE clause = full Cartesian product. Use explicit `JOIN ... ON` syntax, always.

**Mistake 3.6 — Joining on the wrong grain.**
Know each table's grain (one row per what?) before joining. Joining a policy-level table to a hazard-level table and reporting "policy counts" without deduplication is the same fan-out bug wearing different clothes. State the grain in a comment at the top of nontrivial queries.

**Mistake 3.7 — "Fixing" fan-out with DISTINCT.**
Slapping `SELECT DISTINCT` on top of a fan-out hides the symptom, kills performance, and still breaks `SUM`/`AVG` (DISTINCT dedupes whole rows, not the double-counted amounts). Fix the join, not the output.

---

## 4. GROUP BY and Aggregation

**Mistake 4.1 — Non-aggregated columns in SELECT.**
Every SELECT column must be either in GROUP BY or inside an aggregate. Postgres/SQL Server/Snowflake raise an error. **MySQL (with default settings relaxed) and SQLite silently pick an arbitrary value** — a landmine when queries move between systems.

**Mistake 4.2 — COUNT(DISTINCT x) vs COUNT(x) vs COUNT(*).**
- `COUNT(*)` = rows.
- `COUNT(col)` = non-NULL values (duplicates counted).
- `COUNT(DISTINCT col)` = unique non-NULL values.
Pick deliberately. "Number of customers who ordered" is `COUNT(DISTINCT customer_id)`, not `COUNT(*)` on the orders table.

**Mistake 4.3 — Conditional aggregation done with joins instead of CASE.**
Pivoting counts by condition doesn't need multiple scans or self-joins:
```sql
SELECT state,
       COUNT(*) AS total,
       SUM(CASE WHEN status = 'written_out' THEN 1 ELSE 0 END) AS write_outs,
       COUNT(DISTINCT CASE WHEN status = 'written_out' THEN policy_id END) AS wo_policies
FROM inspections
GROUP BY state;
```
The `COUNT(DISTINCT CASE WHEN ... THEN key END)` pattern is the standard way to get deduplicated conditional counts in one pass (CASE returns NULL when the condition fails, and COUNT ignores NULLs).

**Mistake 4.4 — Averaging averages.**
`AVG(state_avg)` across states is not the overall average unless every state has the same row count. Weight properly: `SUM(x) / SUM(n)`, or aggregate from raw rows.

**Mistake 4.5 — Ratios of sums vs sums of ratios.**
`AVG(claims/premium)` per-row is not the portfolio loss ratio. Loss ratio = `SUM(claims) / SUM(premium)`. Decide which question you're answering; they diverge whenever the denominator varies across rows.

**Mistake 4.6 — HAVING on a different aggregate than displayed.**
Legal but confusing: `HAVING COUNT(*) > 10` while SELECT shows `AVG(x)`. Fine — just be aware HAVING can reference aggregates not in SELECT, and reviewers may miss the filter.

**Mistake 4.7 — GROUP BY on a computed expression, repeated inconsistently.**
If you `GROUP BY DATE_TRUNC('month', ts)` make sure SELECT uses the *identical* expression (or its alias where allowed). Slightly different expressions (`EXTRACT(MONTH ...)` in one place, `DATE_TRUNC` in another) cause errors or, worse, subtle mis-grouping across years.

---

## 5. Window Functions

### What they are

Window functions perform calculations across a set of rows related to the current row **without collapsing rows**. Each input row keeps its own output row; the function adds a computed value alongside it. The window is defined by `OVER (PARTITION BY ... ORDER BY ... [frame])`.

### Window functions vs GROUP BY

- **GROUP BY**: you want a summary and no longer need individual rows — one output row per group.
- **Window function**: you need row-level detail *and* group-level context simultaneously.

If you're computing an aggregate in a subquery and joining it back to the original table, that's the signal a window function is cleaner:
```sql
SELECT policy_id, state, premium,
       AVG(premium) OVER (PARTITION BY state) AS state_avg_premium
FROM policies;
```

### Core functions

**ROW_NUMBER / RANK / DENSE_RANK** — number rows within a partition; differ on ties:
```sql
ROW_NUMBER() OVER (ORDER BY sales DESC)  -- 1,2,3,4  unique; ties broken arbitrarily
RANK()       OVER (ORDER BY sales DESC)  -- 1,2,2,4  Olympic-style; gap after ties
DENSE_RANK() OVER (ORDER BY sales DESC)  -- 1,2,2,3  no gaps
```
Use ROW_NUMBER for dedup/"pick one," DENSE_RANK for "top N distinct values."

**LAG / LEAD** — previous/next row's value without a self-join:
```sql
SELECT month, revenue,
       LAG(revenue, 1, 0) OVER (ORDER BY month) AS prev_month,  -- 3rd arg = default
       revenue - LAG(revenue) OVER (ORDER BY month) AS mom_change
FROM monthly_sales;
```

**Running totals (SUM OVER)** — `ORDER BY` inside OVER makes an aggregate cumulative:
```sql
SUM(amount) OVER (PARTITION BY customer_id ORDER BY order_date)  -- running total per customer
SUM(amount) OVER (PARTITION BY state)                            -- partition total on every row
amount / SUM(amount) OVER (PARTITION BY state)                   -- percent-of-total
```

**NTILE(n)** — buckets rows into n roughly equal groups (quartiles, deciles). **FIRST_VALUE / LAST_VALUE** — see frame gotcha below.

### Common patterns

**Deduplication with ROW_NUMBER:**
```sql
WITH ranked AS (
  SELECT *,
         ROW_NUMBER() OVER (
           PARTITION BY policy_id
           ORDER BY updated_at DESC, record_id DESC   -- deterministic tiebreaker!
         ) AS rn
  FROM policy_snapshots
)
SELECT * FROM ranked WHERE rn = 1;
```
PARTITION BY defines what "duplicate" means; ORDER BY defines which copy wins. Use ROW_NUMBER, not RANK (RANK returns multiple rows on ties).

**Year-over-year with LAG:**
```sql
WITH yearly AS (
  SELECT state, EXTRACT(YEAR FROM policy_date) AS yr, COUNT(*) AS n
  FROM policies GROUP BY 1, 2
)
SELECT state, yr, n,
       LAG(n) OVER (PARTITION BY state ORDER BY yr) AS prev_year,
       ROUND(100.0 * (n - LAG(n) OVER (PARTITION BY state ORDER BY yr))
             / NULLIF(LAG(n) OVER (PARTITION BY state ORDER BY yr), 0), 1) AS yoy_pct
FROM yearly;
```
Note the layering: GROUP BY first to reach the yearly grain, then window across years.

### Window gotchas

**5.1 — Can't use in WHERE / GROUP BY / HAVING.** Evaluated after WHERE. Use a CTE, or `QUALIFY` (Snowflake/BigQuery/Databricks).

**5.2 — Missing or wrong-grain PARTITION BY.** No PARTITION BY = the whole result set is one window; your dedup keeps one row *total*. Over-partitioning (including a column that varies between "duplicates") dedupes nothing. Always ask: one row per *what*?

**5.3 — LAG assumes consecutive rows; gaps lie silently.** Missing 2024 data means LAG compares 2025 to 2023 and labels it "YoY." Densify with a calendar/spine table or verify `yr - LAG(yr) = 1`.

**5.4 — Default frame + ties makes running totals jumpy.** With ORDER BY, the default frame is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` — it includes all **peer rows** with the same ORDER BY value, so two rows on the same date both show the total including each other. For strict accumulation, add a unique tiebreaker or write `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` explicitly.

**5.5 — LAST_VALUE with the default frame.** `LAST_VALUE(x) OVER (PARTITION BY p ORDER BY d)` returns the *current* row's value, not the partition's last — the default frame stops at the current row (well, its peers). Fix: `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`, or just use FIRST_VALUE with reversed ordering.

**5.6 — Nondeterministic ROW_NUMBER on ties.** Tied timestamps mean rn = 1 can flip between runs — pipelines and audits will disagree with themselves. Always add a deterministic tiebreaker.

**5.7 — NULL ordering varies by database.** Postgres sorts NULLs last on ASC; SQL Server sorts them first. A NULL can quietly take rank 1. Use `NULLS LAST` where supported, or filter/COALESCE.

**5.8 — Can't nest window functions or wrap them in aggregates in one SELECT.** `AVG(LAG(x) OVER (...))` is invalid. Compute in a CTE, aggregate in the next layer.

**5.9 — Performance: each distinct OVER spec can trigger a separate sort.** Reuse window specs (or a named `WINDOW` clause), and filter rows in WHERE *before* the window step.

**Mental model:** almost all window gotchas come from one fact — window functions run **late** (after WHERE/GROUP BY, before final ORDER BY/LIMIT) and depend entirely on the window definition. Get partition grain, ordering determinism, and frame right; the rest follows.

---

## 6. Subqueries and CTEs

**Mistake 6.1 — Correlated subquery in SELECT running once per row.**
```sql
SELECT p.policy_id,
       (SELECT COUNT(*) FROM claims c WHERE c.policy_id = p.policy_id) AS n_claims
FROM policies p;   -- executes the subquery per policy row
```
Fine on small data; a scan-per-row disaster on large tables. Rewrite as a pre-aggregated join or a window function.

**Mistake 6.2 — Scalar subquery returning multiple rows.**
`WHERE premium = (SELECT premium FROM ...)` errors (or silently misbehaves in some engines) if the subquery returns >1 row. Use `IN`, `EXISTS`, or guarantee uniqueness with LIMIT/aggregation — and make sure that guarantee is *intentional*, not accidental.

**Mistake 6.3 — Assuming CTEs are always just readability sugar.**
In older Postgres (<12), CTEs were optimization fences (fully materialized). In modern engines they're usually inlined — but a CTE referenced multiple times may be recomputed each time in some engines and materialized in others. If a CTE is expensive and reused, check your engine's behavior; consider a temp table.

**Mistake 6.4 — Deeply nested subqueries instead of flat CTE chains.**
Not a correctness bug, but 5-level nesting is where logic errors hide. Flatten into named CTE steps (`raw → deduped → aggregated → final`); each CTE should be testable by running it alone.

**Mistake 6.5 — EXISTS vs IN semantics.**
`EXISTS` short-circuits on the first match and is NULL-safe. `IN` builds the value set. For "does a related row exist," prefer EXISTS; for a small literal list, IN is fine.

---

## 7. Dates, Times, and Timezones

**Mistake 7.1 — BETWEEN on timestamps (the end-of-day bug).**
```sql
WHERE created_at BETWEEN '2026-06-01' AND '2026-06-30'
```
`'2026-06-30'` coerces to `2026-06-30 00:00:00`, so everything after midnight on the 30th is **excluded** — you lose a whole day. Correct pattern is half-open intervals:
```sql
WHERE created_at >= '2026-06-01'
  AND created_at <  '2026-07-01'
```
Half-open ranges also compose perfectly (no gap or overlap between consecutive months). Make this your default for all time filtering.

**Mistake 7.2 — Wrapping the column in a function kills index use.**
```sql
WHERE YEAR(created_at) = 2026            -- full scan
WHERE created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'         -- index-friendly, same logic
```

**Mistake 7.3 — Ignoring timezones.**
"Today's orders" computed in UTC vs local time can differ by up to a full day of records. Know whether the column is `timestamp` (naive) or `timestamptz` (aware), what timezone the data was written in, and convert explicitly (`AT TIME ZONE`) before truncating to a date. Daylight saving transitions make "add 24 hours" ≠ "add 1 day."

**Mistake 7.4 — Date arithmetic assumptions.**
Month arithmetic isn't uniform: Jan 31 + 1 month is Feb 28/29 in most engines (silent clamping). "Last 30 days" ≠ "last month." YoY comparisons on Feb 29 need explicit handling. Fiscal calendars need a calendar dimension table, not arithmetic.

**Mistake 7.5 — String dates and format ambiguity.**
`'06/07/2026'` is June 7 or July 6 depending on locale settings. Store and compare dates as date types; when parsing strings, specify the format explicitly (`TO_DATE(str, 'MM/DD/YYYY')`). ISO format (`YYYY-MM-DD`) is the only string form that sorts correctly as text.

**Mistake 7.6 — Missing dates in time series.**
GROUP BY date only produces rows for dates that have data. Zero-activity days vanish, making charts and moving averages wrong. LEFT JOIN from a calendar/spine table (`generate_series` in Postgres) to densify.

---

## 8. Data Types and Implicit Conversion

**Mistake 8.1 — Integer division.**
```sql
SELECT 3 / 4;          -- 0 in Postgres/SQL Server (integer division!)
SELECT 3.0 / 4;        -- 0.75
SELECT 100 * cnt_a / cnt_b        -- may be 0 or truncated
SELECT 100.0 * cnt_a / cnt_b      -- correct percentage
```
Any ratio of two integer columns needs an explicit cast or a `1.0 *` / `100.0 *` nudge. This is one of the most common causes of "why is my rate column all zeros?"

**Mistake 8.2 — Floating point for money.**
`FLOAT`/`REAL` can't represent 0.1 exactly; sums drift by cents. Use `DECIMAL/NUMERIC` for currency, and never compare floats with `=` — compare within a tolerance.

**Mistake 8.3 — Implicit casts in join/filter conditions.**
`WHERE varchar_col = 123` forces a cast on one side — sometimes on the **column** side, which disables the index and can throw conversion errors when a single row contains a non-numeric string. Match types explicitly. Same for joining an `INT` key to a `VARCHAR` key across tables (a data-modeling smell worth fixing at the source).

**Mistake 8.4 — Leading zeros and numeric-looking strings.**
ZIP codes, phone numbers, and policy numbers are **strings**, not numbers. Casting to INT destroys leading zeros ('02116' → 2116) and breaks anything with hyphens. If it's not something you'd do arithmetic on, keep it text.

**Mistake 8.5 — Overflow in aggregates.**
`SUM` over an INT column can overflow on big tables (SQL Server errors; some engines wrap or promote). Cast to BIGINT/DECIMAL before summing large counts or amounts.

---

## 9. DISTINCT, UNION, and Set Operations

**Mistake 9.1 — DISTINCT as a band-aid.**
If you need DISTINCT and don't know *why* there are duplicates, you have an undiagnosed fan-out or grain problem (see 3.7). DISTINCT is legitimate when the duplication is understood and intended to be collapsed.

**Mistake 9.2 — DISTINCT applies to the whole row.**
`SELECT DISTINCT a, b, c` dedupes the (a, b, c) combination — not just `a`. Adding a column can suddenly "break" your dedup.

**Mistake 9.3 — UNION vs UNION ALL.**
`UNION` dedupes (expensive sort/hash across the whole combined set); `UNION ALL` just appends. If the inputs can't overlap — or duplicates are fine — use `UNION ALL`. Using bare UNION out of habit both slows the query and can silently remove legitimate duplicate rows.

**Mistake 9.4 — Set operations match by position, not name.**
`UNION` aligns columns by position. Same column count with swapped order = garbage data, no error (if types happen to be compatible). List columns explicitly and in identical order in every branch — never `SELECT *` into a UNION.

**Mistake 9.5 — COUNT(DISTINCT a, b) portability.**
Multi-column COUNT DISTINCT works in MySQL but not SQL Server/Postgres directly. Portable pattern: count over a concatenation with a safe delimiter, or count from a deduplicated subquery.

---

## 10. Strings and Pattern Matching

**Mistake 10.1 — Case sensitivity varies by database.**
Postgres string comparison is case-sensitive; SQL Server and MySQL default collations usually aren't. `WHERE state = 'ca'` works in one and returns nothing in another. Normalize deliberately: `WHERE LOWER(state) = 'ca'` (mind index implications — a functional index or a normalized column is better at scale).

**Mistake 10.2 — Trailing spaces.**
`CHAR(n)` pads with spaces; some engines ignore trailing spaces in `=` comparisons and others don't; LIKE is usually strict about them. Data loaded from CSVs/Excel is full of invisible whitespace. `TRIM()` on ingestion, not in every query.

**Mistake 10.3 — LIKE wildcards and leading %.**
`LIKE '%term%'` can't use a normal B-tree index — full scan. Leading-wildcard search at scale needs full-text search or trigram indexes. Also remember `%` and `_` are wildcards — a literal underscore in a pattern needs escaping (`LIKE 'a\_b' ESCAPE '\'`).

**Mistake 10.4 — NULL vs empty string.**
Postgres/SQL Server distinguish `NULL` from `''`; **Oracle treats `''` as NULL**. Cross-platform code that tests `col = ''` behaves differently. Decide on one convention per column and enforce it at load time.

**Mistake 10.5 — Concatenation NULL propagation.**
`first_name || ' ' || middle_name || ' ' || last_name` is entirely NULL if middle_name is. Use `CONCAT()` (treats NULL as '' in many engines — but verify yours) or `COALESCE` each piece. `CONCAT_WS(' ', ...)` is the cleanest where available.

---

## 11. Performance

The theme: help the engine **skip work**. Most performance mistakes are correctness-preserving but turn index seeks into full scans.

**Mistake 11.1 — Non-SARGable predicates.**
A predicate is SARGable (Search ARGument-able) if the engine can use an index for it. Functions on the column break this:
```sql
-- Non-SARGable → full scan          -- SARGable rewrite
WHERE YEAR(dt) = 2026                WHERE dt >= '2026-01-01' AND dt < '2027-01-01'
WHERE LEFT(code, 3) = 'ABC'          WHERE code LIKE 'ABC%'
WHERE amount * 1.1 > 100             WHERE amount > 100 / 1.1
WHERE COALESCE(status,'X') = 'A'     WHERE status = 'A'   (NULL can't equal 'A' anyway)
```
Rule: put functions on the **constant side**, keep the column bare.

**Mistake 11.2 — SELECT \* in production queries.**
Pulls columns you don't need (I/O, network, memory), defeats covering indexes, breaks downstream code when the table schema changes, and makes `UNION`/`INSERT INTO ... SELECT` fragile. Name your columns.

**Mistake 11.3 — Filtering late.**
Filter and aggregate as early as possible in the CTE chain; join small, pre-reduced sets rather than joining everything and filtering at the end. The optimizer often pushes predicates down for you — but not always, especially across CTE/materialization boundaries or non-deterministic functions.

**Mistake 11.4 — OR across different columns.**
`WHERE a = 1 OR b = 2` often prevents index usage on either column. `UNION ALL` of two indexed queries (with dedup handling) can be dramatically faster.

**Mistake 11.5 — Implicit conversion disabling indexes.** (See 8.3 — it's a performance bug as much as a correctness one.)

**Mistake 11.6 — DISTINCT/ORDER BY on huge intermediate results.**
Sorts are expensive. Dedup at the smallest possible set; don't ORDER BY inside subqueries where it's discarded anyway.

**Mistake 11.7 — Not reading the execution plan.**
`EXPLAIN` (or `EXPLAIN ANALYZE`) is the difference between guessing and knowing. Look for: full scans on large tables where you expected seeks, row-estimate vs actual mismatches (stale statistics), and nested-loop joins over huge inputs.

**Mistake 11.8 — Assuming LIMIT makes a query cheap.**
`ORDER BY x LIMIT 10` still has to sort (or at least top-N scan) everything that survives the WHERE clause. LIMIT without ORDER BY returns *arbitrary* rows — fine for eyeballing, never for logic.

---

## 12. Correctness Habits

Habits that catch the above before they reach a dashboard or a stakeholder deck:

1. **State the grain.** Comment every nontrivial query: "one row per policy per inspection." Verify with `COUNT(*) vs COUNT(DISTINCT key)`.
2. **Row-count checkpoints.** After each join or filter step in a CTE chain, know roughly how many rows you expect. Fan-out and accidental inner joins announce themselves in row counts.
3. **Reconcile totals.** Sum a key metric in the raw table and in the final output. If `SUM(premium)` changed and you didn't intend it to, a join duplicated or a filter dropped rows.
4. **Half-open date ranges, always.** `>= start AND < end`. No BETWEEN on timestamps.
5. **NOT EXISTS over NOT IN.** Permanently.
6. **Deterministic ordering** in any ROW_NUMBER/LIMIT that feeds a pipeline — add a unique tiebreaker.
7. **COALESCE at the edges,** not everywhere: handle NULLs at ingestion or at final presentation, and know which columns can legitimately be NULL in between.
8. **Test the CTE chain incrementally.** Each CTE should be runnable and checkable on its own.
9. **Beware cross-database habits.** NULL sorting, `''` vs NULL, case sensitivity, GROUP BY strictness, and division semantics all vary. When SQL moves between engines (e.g., Azure SQL ↔ Databricks ↔ Redshift), re-verify these specifically.
10. **If a number looks great, distrust it first.** Fan-out inflates metrics; silent NULL exclusion deflates them. The most dangerous SQL bugs return plausible answers.

---

## 13. Top 20 Mistakes Checklist

Quick scan before shipping a query:

| # | Mistake | Fix |
|---|---------|-----|
| 1 | `NOT IN` with NULLable subquery → zero rows | `NOT EXISTS` |
| 2 | `= NULL` / `<> NULL` | `IS [NOT] NULL` |
| 3 | `<>` filter silently drops NULLs | Add `OR col IS NULL` if intended |
| 4 | LEFT JOIN + right-table filter in WHERE → inner join | Move condition to `ON` |
| 5 | Join fan-out inflating SUM/COUNT | Pre-aggregate the many-side; check row counts |
| 6 | `BETWEEN` on timestamps loses the last day | Half-open range `>= start AND < end` |
| 7 | Integer division → 0 | `1.0 *` or explicit cast |
| 8 | Window function in WHERE | CTE + outer filter, or QUALIFY |
| 9 | ROW_NUMBER dedup without PARTITION BY / with ties | Correct partition + deterministic tiebreaker |
| 10 | LAG across gaps mislabeled as period-over-period | Densify with calendar table |
| 11 | LAST_VALUE with default frame | `ROWS BETWEEN ... UNBOUNDED FOLLOWING` |
| 12 | Running total jumpy on tied ORDER BY | Unique tiebreaker or explicit `ROWS` frame |
| 13 | `COUNT(col)` vs `COUNT(*)` confusion | Know that COUNT(col) skips NULLs |
| 14 | AVG ignoring NULLs when NULL means 0 | `AVG(COALESCE(x, 0))` |
| 15 | Averaging averages / summing ratios | Weight properly: `SUM(x)/SUM(n)` |
| 16 | UNION when UNION ALL intended | UNION ALL unless dedup is deliberate |
| 17 | Function wrapped around indexed column | Rewrite SARGable; constant side only |
| 18 | Implicit type cast in join/filter | Match types explicitly |
| 19 | Relying on result order without ORDER BY | Always ORDER BY when order matters |
| 20 | DISTINCT to hide unexplained duplicates | Diagnose the grain; fix the join |

---

*Compiled July 2026. Syntax examples default to PostgreSQL; platform differences (SQL Server, MySQL, Snowflake, Databricks, BigQuery, Oracle) are called out where they commonly bite.*
