# Pandas Patterns for SQL-Minded Analysts

If you think in SQL, pandas is mostly a vocabulary problem — the concepts map cleanly, but the defaults, gotchas, and idioms differ in ways that produce silent bugs. This guide translates SQL mental models into pandas, then covers the traps that bite SQL people hardest.

---

## Table of Contents

1. [SQL → pandas Translation Table](#1-sql--pandas-translation-table)
2. [Filtering](#2-filtering)
3. [GroupBy Patterns](#3-groupby-patterns)
4. [Merge (JOIN) Gotchas](#4-merge-join-gotchas)
5. [Method Chaining Style](#5-method-chaining-style)
6. [Common Mistakes](#6-common-mistakes)
7. [Quick-Reference Cheat Sheet](#7-quick-reference-cheat-sheet)

---

## 1. SQL → pandas Translation Table

| SQL | pandas | Notes |
|-----|--------|-------|
| `SELECT col1, col2` | `df[['col1', 'col2']]` | Double brackets → DataFrame; single → Series |
| `SELECT DISTINCT col` | `df['col'].unique()` / `df.drop_duplicates(subset=['col'])` | `unique()` returns array; `drop_duplicates` keeps rows |
| `WHERE x > 5` | `df[df['x'] > 5]` or `df.query('x > 5')` | See §2 |
| `WHERE x IN (...)` | `df[df['x'].isin([...])]` | `isin`, not `in` |
| `WHERE x IS NULL` | `df[df['x'].isna()]` | Never `== None` or `== np.nan` |
| `ORDER BY x DESC, y` | `df.sort_values(['x','y'], ascending=[False, True])` | |
| `GROUP BY k` + aggregates | `df.groupby('k').agg(...)` | See §3 |
| `HAVING cnt > 10` | `.agg(...)` then filter result, or `.filter(lambda g: len(g) > 10)` | `.filter` returns original rows, not aggregates |
| `COUNT(*)` | `len(df)` / `.size()` | `.size()` counts rows incl. NaN |
| `COUNT(col)` | `df['col'].count()` | Counts non-NaN — same semantics as SQL! |
| `COUNT(DISTINCT col)` | `df['col'].nunique()` | Excludes NaN by default (`dropna=False` to include) |
| `JOIN` | `pd.merge(a, b, on='k', how='inner')` | Default is inner — see §4 |
| `LEFT JOIN` | `pd.merge(a, b, on='k', how='left')` | |
| `UNION ALL` | `pd.concat([a, b], ignore_index=True)` | |
| `UNION` (dedup) | `pd.concat([a, b]).drop_duplicates()` | |
| `CASE WHEN` | `np.select(conditions, choices, default)` / `np.where(cond, a, b)` | `np.where` = simple 2-branch; `np.select` = multi-branch |
| `COALESCE(a, b)` | `df['a'].fillna(df['b'])` / `.combine_first()` | |
| `ROW_NUMBER() OVER (PARTITION BY k ORDER BY d)` | `df.sort_values('d').groupby('k').cumcount() + 1` | 0-based → +1 |
| `RANK()` / `DENSE_RANK()` | `df.groupby('k')['x'].rank(method='min' / 'dense')` | `method=` controls tie behavior |
| `SUM(x) OVER (PARTITION BY k)` | `df.groupby('k')['x'].transform('sum')` | **transform = window function** — see §3 |
| `SUM(x) OVER (PARTITION BY k ORDER BY d)` (running) | `df.sort_values('d').groupby('k')['x'].cumsum()` | |
| `LAG(x) OVER (PARTITION BY k ORDER BY d)` | `df.sort_values('d').groupby('k')['x'].shift(1)` | `shift(-1)` = LEAD |
| `x - LAG(x)` | `.groupby('k')['x'].diff()` | Convenience for the common case |
| `NTILE(4)` | `pd.qcut(df['x'], 4, labels=False)` | Quantile buckets |
| `LIMIT 10` | `df.head(10)` | `nlargest`/`nsmallest` = ORDER BY + LIMIT in one, faster |
| `SELECT ... INTO new_table` | `df2 = df...` (assignment) | |
| Pivot / conditional aggregation | `pd.pivot_table` / `pd.crosstab` | |

Two semantic differences worth internalizing up front:

- **NaN behaves like SQL NULL in aggregations** (skipped by `sum`, `mean`, `count`) **but not in comparisons the same way** — `NaN == NaN` is `False` in pandas (SQL gives UNKNOWN), and crucially `df[df['x'] != 5]` **keeps** NaN rows in pandas, whereas SQL's `<> 5` drops NULLs. Opposite defaults; check which one you want.
- **Row order is real in pandas.** SQL tables are unordered sets; DataFrames have positional order and an index. Order-dependent operations (`shift`, `cumsum`, `cumcount`, `drop_duplicates(keep='first')`) silently depend on current row order — **always `sort_values` explicitly first**, just like you'd always write ORDER BY inside an OVER clause.

---

## 2. Filtering

### .loc vs boolean mask vs .query()

Three equivalent ways to write `WHERE premium > 1000 AND state == 'CA'`:

```python
# 1. Boolean mask — the workhorse
df[(df['premium'] > 1000) & (df['state'] == 'CA')]

# 2. .loc — same mask, but supports column selection and (critically) assignment
df.loc[(df['premium'] > 1000) & (df['state'] == 'CA'), ['policy_id', 'premium']]

# 3. .query() — reads like SQL
df.query("premium > 1000 and state == 'CA'")
```

Rules SQL people trip on:

- **Use `&`, `|`, `~`** — not `and`, `or`, `not`. Python's keywords try to evaluate a whole Series as a single boolean and raise `ValueError: The truth value of a Series is ambiguous`.
- **Parenthesize every condition.** `&` binds tighter than `>`, so `df['a'] > 1 & df['b'] > 2` parses wrong. `(df['a'] > 1) & (df['b'] > 2)`.
- **`isin` for IN, `~isin` for NOT IN, `between` for BETWEEN** (`df['x'].between(a, b)` — inclusive both ends by default, unlike the half-open ranges you should use for timestamps).
- **NULL checks:** `isna()` / `notna()`. `df['x'] == np.nan` is always False for every row — same trap as SQL's `= NULL`.
- **`.query()` niceties:** reference variables with `@` (`df.query("state == @target_state")`), backtick columns with spaces (`` `loss ratio` > 0.6 ``). Great for readability in chains; slightly limited (no arbitrary functions), and a mask is easier to debug because you can inspect it directly.

When to use which: masks for anything programmatic or complex; `.loc` whenever you're **assigning** (see next section); `.query()` inside method chains for readability.

### The chained indexing trap (SettingWithCopyWarning)

The single most misunderstood pandas warning. The problem:

```python
# Chained indexing — TWO separate operations: df[...] then [...] 
df[df['state'] == 'CA']['premium'] = 0     # may modify a temporary copy, not df!
```

`df[df['state'] == 'CA']` returns a new object (maybe a view, maybe a copy — pandas doesn't guarantee which). Assigning into it may update a throwaway intermediate, and `df` stays unchanged. Pandas emits `SettingWithCopyWarning` because it *can't tell* whether you wanted that.

The fix — do it in **one** `.loc` call, always:

```python
df.loc[df['state'] == 'CA', 'premium'] = 0     # one operation, guaranteed to hit df
```

The read-side version of the same trap:

```python
sub = df[df['state'] == 'CA']    # is sub a view or a copy? Undefined.
sub['premium'] = 0               # warning; may or may not touch df
```

If you're deliberately carving out a subset to work on, make ownership explicit:

```python
sub = df[df['state'] == 'CA'].copy()   # sub is definitively independent
sub['premium'] = 0                     # no warning, df untouched
```

Two habits eliminate the whole class of bugs: **assign via a single `.loc[rows, cols] = value`**, and **`.copy()` any subset you intend to mutate**. (Pandas 3.0's copy-on-write makes chained assignment simply *not work* rather than *maybe work* — the habits above are correct under both regimes.)

---

## 3. GroupBy Patterns

### agg with named aggregations

The pandas equivalent of a multi-aggregate SELECT, with clean output column names:

```python
# SQL:
# SELECT state,
--        COUNT(*)              AS n_policies,
--        SUM(premium)          AS total_premium,
--        AVG(premium)          AS avg_premium,
--        COUNT(DISTINCT agent) AS n_agents
# FROM policies GROUP BY state;

summary = df.groupby('state').agg(
    n_policies=('policy_id', 'size'),
    total_premium=('premium', 'sum'),
    avg_premium=('premium', 'mean'),
    n_agents=('agent', 'nunique'),
).reset_index()
```

Notes:

- Named aggregation (`new_name=('col', 'func')`) beats the older dict style — no MultiIndex columns to flatten afterward.
- `as_index=False` or a trailing `.reset_index()` keeps the group key as a regular column (SQL-like output). Without it, the key becomes the index — fine, but surprising when you try to select it as a column later.
- **`groupby` drops NaN keys by default** (`dropna=True`) — SQL's GROUP BY keeps NULL as its own group. If NULL-keyed rows matter, pass `dropna=False`. This is a silent row-loss trap.
- `observed=True` for categorical keys — otherwise you get rows for category levels with zero data.
- Custom logic: `('col', lambda s: (s > 100).mean())` works but is slow on big data; prefer building a helper column first and aggregating it with a built-in.

### transform = window function (attach group-level values to every row)

`transform` returns a result **the same length as the input**, aligned to the original rows — exactly what `SUM(...) OVER (PARTITION BY ...)` does. This is *the* concept that makes pandas click for SQL people:

```python
# SQL: AVG(premium) OVER (PARTITION BY state)
df['state_avg'] = df.groupby('state')['premium'].transform('mean')

# Percent of group total:  premium / SUM(premium) OVER (PARTITION BY state)
df['pct_of_state'] = df['premium'] / df.groupby('state')['premium'].transform('sum')

# Filter groups by an aggregate without losing row detail
# SQL: ... WHERE state IN (SELECT state FROM t GROUP BY state HAVING COUNT(*) >= 100)
df[df.groupby('state')['policy_id'].transform('size') >= 100]
```

The mental model:

| Grain of result | SQL | pandas |
|---|---|---|
| One row per group | `GROUP BY` | `.groupby().agg()` |
| One row per original row | window function | `.groupby().transform()` / `.shift()` / `.cumsum()` / `.rank()` |

Ordered window functions map to sorted groupby chains:

```python
df = df.sort_values(['policy_id', 'updated_at'])            # ORDER BY inside OVER

df['prev_premium'] = df.groupby('policy_id')['premium'].shift(1)      # LAG
df['running_total'] = df.groupby('policy_id')['premium'].cumsum()     # SUM OVER (... ORDER BY)
df['rn'] = df.groupby('policy_id').cumcount() + 1                     # ROW_NUMBER

# Dedup: keep latest record per policy (ROW_NUMBER ... WHERE rn = 1)
latest = (df.sort_values('updated_at', ascending=False)
            .drop_duplicates(subset='policy_id', keep='first'))
```

That last idiom — `sort_values` + `drop_duplicates(subset=, keep=)` — is the pandas dedup pattern, and it has the same determinism requirement as SQL: **if the sort key has ties, which row survives is arbitrary.** Add a tiebreaker column to the sort, exactly as you'd add one to the OVER clause.

### The pandas equivalent of SQL's COUNT(DISTINCT CASE WHEN...)

The conditional-deduplicated-count pattern — "distinct policies where status = written_out, per state" — translates as **build the conditional column first, then aggregate it**:

```python
# SQL: COUNT(DISTINCT CASE WHEN status = 'written_out' THEN policy_id END)

out = (df
       .assign(wo_policy=df['policy_id'].where(df['status'] == 'written_out'))
       .groupby('state')
       .agg(
           total_policies=('policy_id', 'nunique'),
           wo_policies=('wo_policy', 'nunique'),   # nunique skips NaN → CASE WHEN semantics
       )
       .assign(wo_rate=lambda d: d['wo_policies'] / d['total_policies'])
       .reset_index())
```

`Series.where(cond)` is the direct analog of `CASE WHEN cond THEN col END` — it keeps the value where the condition holds and puts NaN elsewhere, and `nunique`/`count`/`sum` then skip the NaN just like SQL aggregates skip NULL.

Other conditional-aggregation equivalents:

```python
# SUM(CASE WHEN status='written_out' THEN 1 ELSE 0 END)  — conditional count
n_wo = df.groupby('state')['status'].agg(lambda s: (s == 'written_out').sum())
# faster vectorized version: build the flag first
df['is_wo'] = (df['status'] == 'written_out')
df.groupby('state')['is_wo'].sum()

# Full pivot in one call:
pd.crosstab(df['state'], df['status'])                       # counts
pd.pivot_table(df, index='state', columns='status',
               values='premium', aggfunc='sum', fill_value=0)  # sums
```

The general principle: **in SQL you put the CASE inside the aggregate; in pandas you materialize the CASE as a column (fast, vectorized), then aggregate with a built-in.** Lambdas inside `.agg` work but run per-group in Python — orders of magnitude slower on large frames.

---

## 4. Merge (JOIN) Gotchas

### The how= default trap, and preventing fan-out with validate=

**Trap 1 — the default is `how='inner'`.** SQL makes you write the join type; `pd.merge(a, b, on='k')` silently drops non-matching rows from both sides. Every merge should state `how=` explicitly, even when it's inner — it documents intent and prevents the "where did my rows go" hunt.

**Trap 2 — fan-out is just as silent as in SQL, but pandas gives you a guardrail SQL doesn't: `validate=`.**

```python
merged = policies.merge(
    claims_agg,
    on='policy_id',
    how='left',
    validate='one_to_one',      # 'm:1', '1:m', 'm:m' also available
)
# Raises MergeError immediately if claims_agg has duplicate policy_ids
```

If you believe the right side is unique per key, **assert it** — `validate='m:1'` (many policies rows : one lookup row) is the most common contract. When it raises, you've caught a duplicated-dimension bug at the merge instead of in an inflated metric three steps later. Make `validate=` a default habit, not a debugging tool.

Also mirror the SQL habit of row-count checkpoints:

```python
assert len(merged) == len(policies), f"fan-out: {len(policies)} → {len(merged)}"
```

**Trap 3 — NaN join keys.** Unlike SQL (where NULL never equals NULL), **pandas matches NaN to NaN in merge keys** — NaN-keyed rows on both sides will happily cross-join with each other. Drop or fill NaN keys before merging unless you specifically want that.

**Trap 4 — dtype mismatch on keys.** Merging an `int64` key to an `object` (string) key doesn't error — it just matches nothing (or worse, partially). `'123' != 123`. Check `df.dtypes` on both sides; a key that came through CSV once is a string forever until you cast it. This is the pandas version of SQL's implicit-conversion trap, except pandas doesn't even try to convert.

**Trap 5 — overlapping non-key columns get suffixed.** Both frames having a `status` column produces `status_x` / `status_y` silently. Pass `suffixes=('', '_claims')` deliberately, or better, select only needed columns before merging: `claims[['policy_id', 'amount']]`.

### Diagnosing joins with indicator=True

`indicator=True` adds a `_merge` column telling you where each row came from — a built-in join diagnostic:

```python
m = policies.merge(cancellations, on='policy_id', how='outer', indicator=True)
m['_merge'].value_counts()
# both          8,214
# left_only     1,102   ← policies with no cancellation
# right_only       17   ← cancellations with no matching policy (data quality!)
```

Three uses:

```python
# 1. Anti-join (SQL: NOT EXISTS) — the clean pandas idiom
active = (policies
          .merge(cancellations[['policy_id']], on='policy_id',
                 how='left', indicator=True)
          .query("_merge == 'left_only'")
          .drop(columns='_merge'))

# 2. Semi-join (SQL: EXISTS) — but isin is simpler:
policies[policies['policy_id'].isin(cancellations['policy_id'])]

# 3. Reconciliation: run any important merge as how='outer', indicator=True
#    once during development; the value_counts tells you match rates instantly.
```

`right_only` rows on a merge you expected to be complete are the same signal as a reconciliation total not tying out in SQL — investigate before shipping.

---

## 5. Method Chaining Style

The pandas equivalent of a clean CTE chain: one expression, top-to-bottom readable, no intermediate variable soup, no mutation of earlier state.

```python
result = (
    pd.read_csv('inspections.csv', parse_dates=['inspected_at'])
    .rename(columns=str.lower)
    .query("state in ('LA', 'TX', 'SC') and inspected_at >= '2025-01-01'")
    .assign(
        yr=lambda d: d['inspected_at'].dt.year,
        is_wo=lambda d: d['status'].eq('written_out'),
    )
    .groupby(['state', 'yr'], as_index=False)
    .agg(
        n_policies=('policy_id', 'nunique'),
        n_wo=('is_wo', 'sum'),
    )
    .assign(wo_rate=lambda d: d['n_wo'] / d['n_policies'])
    .sort_values(['state', 'yr'])
)
```

Why this style wins (same reasons CTE chains beat nested subqueries):

- **Reads in execution order** — read → filter → derive → aggregate → derive → sort, like FROM → WHERE → SELECT → GROUP BY.
- **No stale intermediates.** `df2`, `df_temp`, `df_final_v3` each carry hidden state; a chain has none. Every `.assign`/`.query` returns a new frame, which also sidesteps the entire SettingWithCopy problem.
- **Debuggable by truncation** — comment out the tail of the chain to inspect any intermediate stage, exactly like running one CTE at a time. Or insert `.pipe(lambda d: (print(d.shape), d)[1])` as a checkpoint.

Key chain-friendly tools:

- **`.assign(new_col=lambda d: ...)`** — the SELECT-expression of chaining. The lambda receives the *current* state of the chain, which is why it's a lambda and not a reference to the original `df`.
- **`.query()`** — WHERE that doesn't need the frame's variable name.
- **`.pipe(func)`** — inject any custom function into the chain (`.pipe(add_fiscal_year)`); keeps domain logic named and testable.
- **`.rename`, `.astype`, `.sort_values`, `.reset_index`** — all return new frames; all chainable.

Style notes: wrap the whole chain in parentheses (no backslashes), one method per line, and break chains that exceed ~10–12 steps into two named stages — a chain is a paragraph, not a novel.

---

## 6. Common Mistakes

### The inplace=True habit

Drop it entirely.

```python
df.dropna(inplace=True)                 # habit to unlearn
df = df.dropna()                        # do this
```

Why:

- **It doesn't save memory the way people assume** — most `inplace=True` operations still build a new object internally and swap it in.
- **It returns `None`,** which breaks chaining and produces the classic `df = df.sort_values(inplace=True)` → `df is None` bug.
- **It hides mutation.** In a notebook, an `inplace=True` cell run twice or out of order leaves the frame in a state no single cell explains. Reassignment makes every transformation visible and re-runnable.
- The pandas team has deprecated `inplace` on many methods and discourages it everywhere — copy-on-write semantics make it pointless.

### Vectorize instead of iterrows()

`iterrows()` is the pandas equivalent of a cursor loop in SQL — almost always the wrong tool, 100–1000x slower than vectorized operations, and it yields each row as a `Series` (dtype-coerced copies: your ints may come back as floats, and writing to the row does nothing).

```python
# Slow, and the assignment doesn't even work reliably:
for i, row in df.iterrows():
    df.loc[i, 'flag'] = 'high' if row['premium'] > 1000 else 'low'

# Vectorized:
df['flag'] = np.where(df['premium'] > 1000, 'high', 'low')

# Multi-branch CASE WHEN:
df['tier'] = np.select(
    [df['premium'] > 5000, df['premium'] > 1000],
    ['jumbo', 'high'],
    default='standard',
)
```

Escalation ladder when you're tempted to loop:

1. **Arithmetic / comparisons on whole columns** — just write the expression (`df['a'] * df['b']`).
2. **Conditional logic** — `np.where` / `np.select` / `Series.where` / `Series.mask`.
3. **Lookups** — `.map(dict)` / `.replace` / a merge against a lookup frame (never a loop of `.loc` lookups).
4. **String/date operations** — the `.str` and `.dt` accessors are vectorized (`df['name'].str.upper()`, `df['ts'].dt.month`).
5. **Per-group logic** — `groupby` + `agg`/`transform`/`apply` before any manual loop over groups.
6. **`.apply(axis=1)`** — still a Python-level row loop, only marginally better than iterrows. Last resort for genuinely row-wise logic that can't vectorize.
7. **`itertuples()`** if you truly must iterate — several times faster than `iterrows` and preserves dtypes.

The mindset shift: in SQL you never think "for each row"; you describe the whole-column transformation. Keep that mindset in pandas — it's the same declarative muscle.

### copy vs view

The deeper issue behind SettingWithCopyWarning (§2): slicing a DataFrame sometimes returns a **view** (shares memory with the original) and sometimes a **copy**, and the rules are internal implementation details you should not try to memorize. Consequences:

```python
sub = df[df['state'] == 'CA']    # view or copy? Not defined by the API.
sub['premium'] = 0               # might mutate df, might not, warns either way
```

The discipline:

- **Mutating the original?** One-step `.loc[rows, cols] = value` on the original frame.
- **Keeping an independent subset?** `.copy()` at the moment of slicing: `sub = df[mask].copy()`. Explicit ownership, no ambiguity, warning gone for the right reason (not suppressed).
- **Neither?** Prefer the chaining style (§5), where nothing is mutated and the question never arises.
- Never silence the warning with `pd.set_option('mode.chained_assignment', None)` — that converts a loud maybe-bug into a silent one.

Pandas 3.0 (copy-on-write default) resolves the ambiguity: any frame derived from another behaves as a copy, and chained assignment reliably does nothing (raising instead of maybe-working). Code written with the two habits above is correct before and after the transition.

### Bonus round — smaller traps worth knowing

- **`axis` confusion:** `axis=0` operates *down* columns (per-column result), `axis=1` *across* rows. `df.drop('col', axis=1)` vs `df.drop(index)` — prefer the explicit `columns=` / `index=` keywords.
- **`sort_values` puts NaN last by default** regardless of ascending — `na_position='first'` to change. (SQL databases disagree with each other here; pandas at least is consistent.)
- **`astype(int)` on a column with NaN raises** — NaN is a float. Use the nullable `'Int64'` dtype (capital I) or fill first.
- **`read_csv` dtype guessing:** ZIP codes lose leading zeros, big IDs become floats, dates stay strings. Pass `dtype={'zip': str, 'policy_id': str}` and `parse_dates=[...]` explicitly — same "numeric-looking strings are strings" rule as SQL.
- **`groupby().apply()` ambiguity:** output shape depends on what the function returns (scalar → Series, Series → DataFrame, DataFrame → concatenated). If `agg` or `transform` can express it, use them — faster and shape-predictable.
- **Index alignment on assignment:** `df['new'] = some_series` aligns by *index*, not position. After filtering/sorting one side, this silently inserts NaN where indexes don't match. When you mean positional assignment, use `.to_numpy()` or `reset_index(drop=True)` both sides — and after any filter, a `.reset_index(drop=True)` avoids a whole family of alignment surprises.

---

## 7. Quick-Reference Cheat Sheet

| Situation | Do this | Not this |
|---|---|---|
| Conditional assignment | `df.loc[mask, 'col'] = v` | `df[mask]['col'] = v` |
| Subset you'll mutate | `sub = df[mask].copy()` | `sub = df[mask]` |
| WHERE with multiple conditions | `(a) & (b)` with parens | `and` / missing parens |
| NULL check | `.isna()` / `.notna()` | `== np.nan` |
| NOT IN | `~df['k'].isin(vals)` or left-merge + `left_only` | manual loops |
| Window function | `.groupby(k)[x].transform(f)` | merge the agg back by hand |
| LAG / running total / ROW_NUMBER | `sort_values` **then** `.shift` / `.cumsum` / `.cumcount` | trusting current row order |
| Dedup keep-latest | `sort_values(..., tiebreaker).drop_duplicates(subset, keep='first')` | ties left ambiguous |
| COUNT(DISTINCT CASE WHEN) | `.where(cond)` column + `nunique` | per-group lambdas on big data |
| Every merge | explicit `how=`, `validate=`, row-count assert | bare `pd.merge(a, b, on=k)` |
| Join diagnosis | `indicator=True` + `value_counts()` | eyeballing |
| Multi-step transformation | one parenthesized chain with `.assign`/`.query`/`.pipe` | df2, df3, df_final_v2 |
| Any transformation | `df = df.method()` | `inplace=True` |
| Row-wise logic | `np.where` / `np.select` / `.map` / vectorized accessors | `iterrows()` / `apply(axis=1)` |
| CSV IDs and ZIPs | `dtype=str` on read | letting pandas guess |

---

*Compiled July 2026. Written for pandas 2.x; notes flag behaviors that change under pandas 3.0 copy-on-write.*
