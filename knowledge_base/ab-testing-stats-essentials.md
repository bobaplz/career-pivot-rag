# A/B Testing & Stats Essentials for Analysts

## The core question: is the difference real or noise?

Every metric moves between any two groups, even identical ones — randomness guarantees it. A/B testing answers one question: is the observed difference larger than what chance alone would plausibly produce? Statistics doesn't prove the treatment worked; it quantifies how surprising the result would be if it did nothing.

## Hypothesis testing in 5 sentences

We assume the null hypothesis (H0): the treatment has no effect. We run the experiment and compute how incompatible the observed data is with that assumption. The p-value is the probability of seeing a difference this large (or larger) *if H0 were true* — it is not the probability that H0 is true. Before the test, we fix a threshold alpha (typically 0.05): the false-positive rate we're willing to accept. If p < alpha, we reject H0 and call the result statistically significant; otherwise we've failed to detect an effect — which is not proof there is none.

## Power, sample size, MDE — why "run it a week" isn't a plan

Alpha controls false positives; **power** (typically 80%) controls false negatives — the probability of detecting an effect *when it exists*. Power depends on sample size, baseline rate, variance, and the **MDE** (minimum detectable effect): the smallest lift worth acting on. These four lock together — decide the MDE first, then compute the required sample size, then derive the duration from your traffic. "Run it a week" reverses this: it fixes duration and silently accepts whatever MDE your traffic can support, which for small effects is often "none." An underpowered test that comes back non-significant tells you nothing — you couldn't have detected the effect even if it was there. Rule of thumb for proportions: n per group ≈ 16·p(1−p)/MDE². Also run in whole-week blocks to avoid day-of-week bias.

## Common tests and when to use them

**Two-proportion z-test** — for binary outcomes (converted or not, clicked or not). Compares conversion rates between two groups; the workhorse of most product A/B tests. Valid when counts are large enough (roughly ≥10 successes and failures per group).

**t-test** — for continuous metrics (revenue per user, session duration, cycle time). Compares group means; use Welch's version (unequal variances) by default. Robust to non-normality at typical A/B sample sizes thanks to the CLT, but heavy-tailed metrics like revenue may need huge samples, winsorization, or a nonparametric check (Mann-Whitney).

**Chi-square test** — for categorical outcomes with more than two levels (plan chosen: basic/pro/enterprise) or more than two groups. Tests whether the distribution across categories differs between variants. For a 2×2 case it's equivalent to the z-test; a significant result tells you *something* differs, so follow up to find *where*.

## Pitfalls

### Peeking (early stopping)

Checking results repeatedly and stopping the moment p < 0.05 inflates your false-positive rate far above 5% — with daily peeks, often past 25%. A random walk will wander below the line eventually. Fix the sample size in advance and test once, or use methods built for monitoring (sequential testing, alpha-spending, Bayesian approaches).

### Multiple comparisons

Test 20 metrics (or segments, or variants) at alpha = 0.05 and you expect one false positive by design — the chance of at least one is ~64%. Declare one primary metric up front; treat the rest as exploratory. If several decisions ride on the test, correct (Bonferroni: divide alpha by the number of tests; or FDR/Benjamini-Hochberg). Segment-hunting after the fact ("it worked for mobile users in Texas!") is multiple comparisons wearing a costume — treat such findings as hypotheses for the *next* test.

### Simpson's paradox

An effect can hold in every segment yet reverse in the aggregate (or vice versa) when group composition differs — e.g., the variant wins in both new and returning users but loses overall because it drew a higher share of low-converting new users. Defense: randomize properly so composition is balanced, run a sample-ratio-mismatch check, and read segment-level results alongside the topline before concluding.

### Practical vs statistical significance

With enough traffic, a +0.01%p lift will be "significant" — and still not worth shipping. Statistical significance says the effect is likely real; it says nothing about whether it matters. Always report the confidence interval, not just the p-value, and compare the effect size against the MDE and the cost of shipping. Conversely, a non-significant result with a wide CI is "we don't know yet," not "no effect."

## Checklist before/after running a test

**Before**

- [ ] One primary metric and a directional hypothesis, written down
- [ ] MDE chosen from business value, not from hope
- [ ] Sample size / duration computed from alpha, power, MDE (whole weeks)
- [ ] Randomization unit defined (user, not session) and consistent with the metric
- [ ] Guardrail metrics listed (latency, errors, revenue)
- [ ] Analysis plan fixed: test, segments, stopping rule

**After**

- [ ] Sample ratio matches the intended split (SRM check)
- [ ] No peeking-driven stop; planned n reached
- [ ] Effect size + confidence interval reported, not just p
- [ ] Guardrails clean; segments read as exploratory only
- [ ] Practical significance judged against MDE and shipping cost
- [ ] Decision and learnings documented — including nulls
