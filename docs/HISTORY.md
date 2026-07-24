# Engineering history

This project started life as a multithreaded Selenium scraper for YouTube
search results — hence the repository name. That code now lives in
[`legacy/`](../legacy/). The active project is the LangGraph research pipeline
documented in the main README.

## The correctness pass (2026-07)

A full review of the pipeline surfaced a set of defects that were fixed in one
branch. They're preserved here because several are instructive:

- **The browser fallback was silently dead.** `from datetime import time`
  shadowed the `time` module, so `_browser_fetch`'s `time.monotonic()` raised
  `AttributeError` on its first line — swallowed by the fetch's exception
  handler. The SeleniumBase tier had never once returned HTML; any site that
  blocked the fast `curl_cffi` fetch silently contributed nothing. One-line
  fix, found only by tracing the failure path. Lesson: *watch every code path
  run at least once.*
- **Embeddings were orphaned from their text.** `extracted_units` rows were
  inserted with only `{extraction_run_id, embedding}` — the schema's `content`
  and `semantic_type` columns stayed NULL, and the batch-order pairing of
  vector↔sentence was discarded. Rocchio never noticed (it only averages
  vectors), but any retrieval feature was impossible: a similarity hit had no
  sentence to show. Fixed by inserting complete rows with `zip(strict=True)`.
- **The re-extract loop double-counted state.** `topicIds`/`sourceIds` used
  `operator.add` reducers, so the "reset" (`{"topicIds": []}`) was a no-op
  (`existing + [] = existing`), and nodes returning the whole mutated state
  doubled the channels every pass — each iteration would have re-fanned-out
  over every topic ever created. Fixed with an `add_or_reset` reducer
  (write `None` to clear), partial node updates, and an iteration cap.
- **A join edge that could never re-fire.** The
  `["embedTopic", "feedbackInterrupt"] → centroidEmbedding` barrier needed
  both parents, but `embedTopic` only runs from START — the loop's second
  iteration would have stalled after its interrupt. Replaced with a direct
  edge (embedTopic's write is always committed by the time the interrupt
  resolves). Pinned by `tests/integration/test_reextract_loop.py`.
- **Schema drift.** The code inserted `extraction_runs.topic_id`, which the
  committed migration never declared — local databases had been altered
  out-of-band. Captured in a migration.
- Smaller items: a hardcoded (public, local-dev) Supabase key replaced by
  env-driven config; a wrong filter column in `getSources`; prompt typos and
  unvalidated LLM JSON in source discovery; undeclared direct dependencies;
  CI that ran the legacy scraper instead of the test suite; a pytest
  collection crash from the seleniumbase plugin under setuptools ≥ 82.

An earlier version of the README flagged `gpt-5.4` as an invalid model id —
that was wrong (it shipped in March 2026) and is retracted.

## Still open

- The initial migration grants `delete`/`truncate`/`update` to the `anon`
  role on every table (default Supabase local scaffolding). Tighten with RLS
  before any non-local deployment.
- The legacy scraper is unmaintained and may violate YouTube's ToS if run.
