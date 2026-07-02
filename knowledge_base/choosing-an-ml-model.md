# Choosing an ML Model: A Practical Guide

## Start with the question, not the model

The problem type picks the model family before you do. **Predicting a number** → regression. **Predicting a category** → classification (and ask: do you need calibrated probabilities, or just labels?). **Ordering items** → ranking, where what matters is relative order, not absolute scores. **Explaining drivers** → inference, where coefficient validity beats predictive accuracy and a black box may be the wrong tool entirely. **No labels** → clustering/anomaly detection, a different game with fuzzier evaluation. Two questions to settle before touching code: what decision will this model's output feed, and what does one unit of error cost? A model optimized for the wrong question is worse than no model — it's confidently wrong at scale.

## The baseline rule

Always start with a dummy baseline (predict the majority class / the mean) and a simple model (logistic or linear regression, lightly regularized). Every complex model must beat them to justify its existence — and its costs in training time, serving latency, explainability, and maintenance. Baselines expose problems early: if logistic regression already hits AUC 0.95, either the problem is easy or you have leakage (investigate before celebrating). If XGBoost beats logistic by 0.003 AUC, ship the logistic. The baseline is not a formality; it's the denominator of every claim you'll make about the fancy model.

## Decision guide by situation

### Tabular data → gradient boosting first (XGBoost/LightGBM)

For structured/tabular data, gradient-boosted trees are the default winner: they handle mixed dtypes, missing values, nonlinearities, and interactions with minimal preprocessing (no scaling, no one-hot for LightGBM's native categoricals), and they win most tabular benchmarks and Kaggle competitions. Deep learning rarely beats them on tables. Tune the few knobs that matter (learning rate + n_estimators with early stopping, max_depth/num_leaves, subsampling) and spend the saved time on features — feature quality moves tabular performance far more than model choice.

### Need interpretability → linear/logistic + regularization, or trees + SHAP

If stakeholders, regulators, or filings need to know *why* (common in insurance and credit), prefer inherently interpretable models: linear/logistic with L1/L2 regularization gives signed, sized coefficients — mind multicollinearity, which scrambles them. If you need boosted-tree accuracy *and* explanations, add SHAP: global importance plus per-prediction attribution. But be honest about the distinction — SHAP explains what the model did, not what causally drives the outcome. When the deliverable is a causal claim, model choice is the smaller problem; study design is the bigger one.

### Small data → simple models, strong CV

With hundreds to a few thousand rows, model capacity must shrink to match: regularized linear models, shallow trees, naive Bayes. Complex models will memorize, and — more dangerously — your *evaluation* becomes noisy: a single 80/20 split's score can swing wildly. Use repeated k-fold CV and report the standard deviation across folds, not just the mean; if the std dwarfs the gap between two models, you can't tell them apart. Every preprocessing choice and hyperparameter you tune on this data is another chance to overfit, so keep the whole pipeline small, not just the model.

### Text/images → transfer learning, not from scratch

Never train text or vision models from scratch on your own data — you don't have the data or compute that pretrained models embody. For text: embed with a pretrained sentence transformer and put logistic regression or boosting on top, or fine-tune a small pretrained model; for many tasks an LLM with few-shot prompting is now the fastest strong baseline. For images: fine-tune a pretrained CNN/ViT, or just use its frozen embeddings as features. From-scratch training on small corpora loses to a pretrained model plus a linear head almost every time.

## Evaluation pitfalls

### Accuracy on imbalanced data

With 2% positives, "always predict negative" scores 98% accuracy — accuracy is meaningless off-balance. Choose by error cost: **precision** when false positives are expensive (each flagged case triggers costly action), **recall** when false negatives are (missing a case is the disaster), **F1** to balance, **PR-AUC** over ROC-AUC under heavy imbalance (ROC-AUC looks deceptively rosy when negatives dominate). And remember the 0.5 threshold is not sacred — tune it on the cost structure; often the model is fine and only the cutoff is wrong.

### Data leakage

Leakage = information available at training time that won't exist at prediction time; it produces spectacular validation scores and production faceplants. **Target leakage:** a feature is a proxy for or consequence of the label ("claim_paid_amount" when predicting claim filing). **Train-test contamination:** fitting *any* transform — scaler, imputer, encoder, feature selection — on the full dataset before splitting leaks test statistics into training. Fit everything inside the CV loop (sklearn `Pipeline` makes this automatic). Red flag: validation metrics that look too good. They probably are.

### When CV splits must respect time or group structure

Random k-fold assumes rows are independent — often false. **Time series:** random splits train on the future to predict the past; use forward-chaining splits (`TimeSeriesSplit`) so training always precedes validation. **Grouped data** (multiple rows per policy, customer, property): random splits put the same entity on both sides, and the model "generalizes" by recognizing entities; use `GroupKFold` on the entity ID. The split must mirror deployment: if the model will score *new* policies in *future* months, validate on unseen policies in later months. When honest splits drop your score, that drop was always there — you just couldn't see it.

## Overfitting checklist

- [ ] Train vs validation gap small? (Large gap = memorizing)
- [ ] Score stable across CV folds? (High variance = fragile)
- [ ] Beats dummy + simple baseline by a margin that matters?
- [ ] Test set touched exactly once, after all decisions?
- [ ] All preprocessing fit inside CV folds, never on full data?
- [ ] No feature that's a proxy for the target or unavailable at prediction time?
- [ ] Splits respect time/group structure matching deployment?
- [ ] Hyperparameter search modest relative to data size? (1,000 configs on 500 rows = overfitting the validation set)
- [ ] Learning curve checked — would more data help, or is the model saturated?
- [ ] Performance sanity-checked on the most recent time slice, not just the pooled average?
