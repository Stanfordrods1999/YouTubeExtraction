# Retrieval evals: measuring the Rocchio feedback loop

This harness answers one question with numbers instead of vibes: **does the
human's source selection (via Rocchio) actually improve retrieval?**

## Workflow

1. **Run the pipeline** on a topic with a known thread id (LangGraph Studio or
   the API). At the selection interrupt, pick the relevant sources — this is
   the feedback Rocchio folds into the refined centroid. Both centroids
   (`initial`, `refined`) are persisted to `topic_centroids` automatically.
2. **Author a golden set** (`evals/golden.json`, format in
   `golden.example.json`): a few natural questions per topic, each labeled
   with the source URLs that genuinely answer it. Labels are source-level —
   the same granularity the interrupt collects — so no per-unit labeling.
3. **Run it**:

   ```bash
   uv run python -m evals.run_eval --golden evals/golden.json --k 10
   ```

It prints a markdown table per topic comparing `question-only` (baseline),
`blend-initial`, and `blend-refined` retrieval on P@k, MRR, and nDCG@k.
Paste the table into the main README when you have real numbers.

The metric functions (`evals/metrics.py`) and the judging/formatting helpers
are pure and covered by `tests/unit/test_eval_metrics.py`; only `run_eval.py`
itself needs the live database.

Sweeping the Rocchio weights is a loop over env vars:

```bash
for beta in 0.5 0.75 1.0; do
  ROCCHIO_BETA=$beta uv run python -m evals.run_eval ...
done
```
