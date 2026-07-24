# YouTubeExtraction

> A research **knowledge-extraction pipeline** built on LangGraph + Supabase/pgvector.
> It started life as a multithreaded YouTube scraper (still in the repo), but the
> active project is now a topic → source → extraction → embedding pipeline that turns
> a single research topic into a searchable store of embedded "atomic facts."

**Status: working end-to-end.** The pipeline runs topic → discovery → extraction →
embedding → human feedback → Rocchio refinement, with an optional bounded
re-extract loop. Remaining rough edges are tracked honestly in
[Known Issues / Review Findings](#known-issues--review-findings).

---

## Table of Contents

1. [What this repo is](#what-this-repo-is)
2. [Architecture](#architecture)
3. [Repository layout](#repository-layout)
4. [Data model](#data-model)
5. [Setup](#setup)
6. [Running](#running)
7. [Testing](#testing)
8. [Known Issues / Review Findings](#known-issues--review-findings)
9. [Legacy: the YouTube scraper](#legacy-the-youtube-scraper)

---

## What this repo is

There are **two generations of code** living side by side:

| Generation | Purpose | Entry point | Key files |
| --- | --- | --- | --- |
| **Current — LangGraph pipeline** | Given a research topic, expand it into subtopics, discover web sources for each, fetch & clean their content, decompose it into atomic factual units, and embed those units into a pgvector store. | `langgraph.json` → graph `scraping_pipeline` | `src/app/graph/`, `src/app/services/`, `db/`, `supabase/` |
| **Legacy — YouTube scraper** | Search YouTube for a list of queries with a pool of persistent Selenium browsers and dump video metadata + comments to JSON. | `ScrapeRun.py` (Click CLI) | `ScrapeRun.py`, `exec/executor.py`, `utils/YouTubeScraper.py` |

The recent commit history (`content extraction && subgraph creation`,
`fan out extractions`, `Rocchio Relevance`) and the branch
`reimplement/extraction-langraph` all belong to the **pipeline**. The scraper is
kept around but is not part of the pipeline's data flow.

The name "YouTubeExtraction" is historical — the current pipeline is **source-agnostic**
(it fetches arbitrary web URLs), not YouTube-specific.

---

## Architecture

The pipeline is a LangGraph `StateGraph` (`src/app/graph/graph.py`) with a nested
map-reduce subgraph. Every stage is a thin **node** that delegates to a **service**,
which does the LLM/HTTP work and persists to **Supabase**.

```
                                 ┌──────────────┐
                        ┌───────►│ topicExtractor│──── expands topic into subtopics (LLM)
                        │        │  (LLM → topics)│      → writes `topics`, returns topicIds
                        │        └──────┬────────┘
   START ──────────────┤               │  fan_out_sources: one Send() per topic id
                        │               ▼
                        │        ┌─────────────────────────────────────────────┐
                        │        │  sourceDiscovery  (subgraph, map-reduce)      │
                        │        │                                               │
                        │        │  sourceExtractor ── web-search for sources    │
                        │        │   (LLM+search → `sources`)                    │
                        │        │        │  fan_out_runs: one Send() per source │
                        │        │        ▼                                      │
                        │        │  runExtractor ── fetch HTML, clean, decompose │
                        │        │   (curl/browser → trafilatura → LLM →         │
                        │        │    `extraction_runs`)                         │
                        │        │        │                                      │
                        │        │        ▼                                      │
                        │        │  embedUnits ── batch-embed atomic units,      │
                        │        │   surface discovered sourceIds (→ pgvector)   │
                        │        └──────────────────┬──────────────────────────┘
                        │                           ▼
                        │        ┌──────────────────────────────────────┐
                        │        │  feedbackInterrupt (interruptSelections)│──── PAUSES the run;
                        │        │   interrupt(): user picks relevant      │     human picks which
                        │        │   source_ids → selected / non-selected  │     sources are relevant
                        │        └──────────────────┬──────────────────────┘
                        │                           │
                        └───────►┌──────────────┐   │
                                 │  embedTopic   │   │  both branches join here
                                 │ (topicEmbed)  │   │
                                 └──────┬───────┘   │
                                        ▼           ▼
                                 ┌──────────────────────────────────────┐
                                 │  centroidEmbedding                    │──── Rocchio: re-centres
                                 │  (TransformationService, α·q0 +       │     the topic centroid
                                 │   β·mean(rel) − γ·mean(non-rel))      │     from the feedback
                                 └──────────────────┬───────────────────┘
                                                    ▼
                                                   END
```

### Stage-by-stage (node → service → table)

| Stage | Node | Service | Model / tool | Writes |
| --- | --- | --- | --- | --- |
| Topic expansion | `nodes/topicExtractor.py` | `services/topicExtractionService.py` | `gpt-4.1-mini` (JSON output) | `topics` |
| Topic embedding | `nodes/topicEmbed.py` | *(inline OpenAI call)* | `text-embedding-3-small` | *(returns `topicCentroid` to state)* |
| Source discovery | `nodes/sourceExtractor.py` | `services/sourceDiscoveryService.py` | `ChatOpenAI` + `web_search_preview` tool | `sources` |
| Content extraction | `nodes/runExtractor.py` | `services/extractionService.py` | curl_cffi → SeleniumBase fallback, `trafilatura`, `gpt-4.1-mini` structured output | `extraction_runs` |
| Unit embedding | `nodes/embedUnits.py` | `services/embeddingServices.py` | `text-embedding-3-small` | `extracted_units` (+ surfaces `sourceIds` to state) |
| Human feedback | `nodes/interruptSelections.py` | *(LangGraph `interrupt`)* | — (human-in-the-loop) | *(returns `selectedSourceIds` / `nonselectedSourceIds`)* |
| Centroid refinement | `nodes/centroidEmbedding.py` | `services/transformationService.py` | Rocchio + `getEmbeddedUnits` (pgvector) | *(updates `topicCentroid`)* |

### Key concepts

- **Fan-out / map-reduce.** `fan_out_sources` (top graph) and `fan_out_runs`
  (subgraph) use LangGraph `Send` to run one branch per topic / per source in
  parallel. Results are reduced back through `Annotated[list, operator.add]`
  reducers on the state (e.g. `topicIds`, `extraction_run_ids`).
- **Atomic units.** `runExtractor` decomposes each source into self-contained
  statements typed as `fact | definition | statistic | claim | opinion`
  (see the prompt in `src/app/prompts/transformation.py`). This is the granularity
  that gets embedded and retrieved.
- **Tiered fetching.** `extractionService.sourceHTML()` tries a fast
  `curl_cffi` request impersonating Chrome first, and only falls back to a real
  headless SeleniumBase browser (behind a 2-slot semaphore) if the response looks
  blocked or too small.
- **Human-in-the-loop source selection.** After `sourceDiscovery` runs, the
  `feedbackInterrupt` node (`nodes/interruptSelections.py`) calls LangGraph's
  `interrupt()` to **pause the run**, advertising each discovered source's URL,
  discovery reason, and priority score. The human resumes with
  `{"action": "reextract" | "end", "selected_ids": [...]}`; the node partitions the
  sources into `selectedSourceIds` / `nonselectedSourceIds`. Because it interrupts,
  the graph must be run with a **checkpointer** and resumed with a
  `Command(resume=...)` (see *Running*).
- **Bounded re-extract loop.** After the centroid is refined, `route_after_centroid`
  either ends the run or (on `"reextract"`) loops back through `reconcileSources`,
  which seeds a new topic text from the selected sources and resets the accumulating
  state channels. The loop is capped by `MAX_ITERATIONS` (default 3).
- **Rocchio relevance feedback (now wired in).** `centroidEmbedding`
  (`nodes/centroidEmbedding.py`) feeds the topic centroid and the human's
  selected / non-selected sources to `TransformationService.compute_query_vector`,
  which fetches each set's unit embeddings (`getEmbeddedUnits`) and applies the
  classic Rocchio query-refinement formula
  (`α·q0 + β·mean(relevant) − γ·mean(non-relevant)`, then L2-normalised) to
  **re-centre `topicCentroid`**. `embedTopic` and `feedbackInterrupt` are both
  upstream of this node, so it runs once the initial centroid and the feedback are
  available. As of the latest commit this replaces the earlier "dead code" status:
  `transformationService.py` is now a real `TransformationService` class (repo-backed,
  with a `@staticmethod rocchio_embedding` and a divide-by-zero guard).

---

## Repository layout

```
YouTubeExtraction/
├── langgraph.json                 # LangGraph entry: graph `scraping_pipeline` + FastAPI app
├── pyproject.toml                 # Current dependency source of truth (uv, Python ≥3.13)
├── .env.example                   # Documented env vars (see src/app/config.py)
│
├── src/
│   ├── app/
│   │   ├── graph/
│   │   │   ├── graph.py            # Top-level StateGraph (…sourceDiscovery → feedbackInterrupt + embedTopic → centroidEmbedding)
│   │   │   ├── state.py            # TypedDict states: GlobalState / TopicState / sourceDiscoveryState (+ sourceIds / selected / non-selected)
│   │   │   ├── nodes/              # Thin graph nodes (delegate to services)
│   │   │   │   ├── topicExtractor.py
│   │   │   │   ├── topicEmbed.py
│   │   │   │   ├── sourceExtractor.py
│   │   │   │   ├── runExtractor.py
│   │   │   │   ├── embedUnits.py
│   │   │   │   ├── centroidEmbedding.py   # Rocchio centroid refinement (now wired in)
│   │   │   │   └── interruptSelections.py # human-in-the-loop source selection (interrupt)
│   │   │   └── subgraphs/
│   │   │       └── sourceDiscovery.py      # map-reduce subgraph: sourceExtractor → runExtractor → embedUnits
│   │   ├── services/               # Business logic + LLM/HTTP calls
│   │   │   ├── topicExtractionService.py
│   │   │   ├── sourceDiscoveryService.py
│   │   │   ├── extractionService.py        # fetch → clean → atomic-unit decomposition
│   │   │   ├── embeddingServices.py
│   │   │   └── transformationService.py    # TransformationService: Rocchio (wired into centroidEmbedding)
│   │   └── prompts/
│   │       └── transformation.py           # atomic-unit system prompt + message builder
│   └── agent/
│       └── webapp.py               # FastAPI app; lifespan initializes the Supabase repo
│
├── db/
│   ├── supabaseRepository.py       # All Supabase CRUD (topics/sources/extraction_runs/extracted_units)
│   └── session.py                  # Lazy singleton repo (init_repo / get_repo)
│
├── supabase/
│   ├── config.toml                 # Local Supabase stack config (ports, auth, storage…)
│   └── migrations/*.sql            # Schema: 4 tables + pgvector + FKs + grants
│
├── logs/Logging.py                 # Small logging wrapper (legacy scraper)
│
├── tests/
│   ├── node/                       # Node-level unit tests (embedUnits, topicEmbed, interrupt, centroid)
│   ├── unit/                       # Service/repo unit tests (embedding, Rocchio, topics, getEmbeddedUnits)
│   ├── integration/                # interrupt → resume → centroid slice with a real checkpointer
│   └── execdata.py                 # Legacy scraper smoke test
│
└── ── Legacy scraper ──
    ├── ScrapeRun.py                # Click CLI: `run-executor`
    ├── exec/executor.py            # SeleniumThreadPoolExecutor (pool of persistent browsers)
    ├── utils/YouTubeScraper.py     # YouTube search/scroll/collect + comment scraping
    ├── Makefile                    # install / chrome / chromedriver / run-scraper / test / lint
    ├── requirements.txt            # Legacy-only deps (NOT the pipeline deps)
    └── .github/workflows/makefile.yml  # CI that runs the legacy scraper
```

---

## Data model

Defined in `supabase/migrations/20260616094321_init_changes.sql`. Postgres with the
`vector` (pgvector) extension. One-to-many all the way down:

```
topics ──1:N──► sources ──1:N──► extraction_runs ──1:N──► extracted_units
```

| Table | Key columns | Notes |
| --- | --- | --- |
| `topics` | `id`, `topic_text`, `status`, `created_by`, `confidence`, `metadata` (jsonb) | One row per (sub)topic produced by `topicExtractor`. |
| `sources` | `id`, `topic_id` (FK), `source_type`, `source_url`, `discovery_reason`, `priority_score`, `status` | Web sources discovered per topic. |
| `extraction_runs` | `id`, `source_id` (FK), `status`, `confidence`, `metadata` (jsonb) | One run per source fetch/extraction. Atomic units are currently stored **inside `metadata`** as JSON. |
| `extracted_units` | `id`, `extraction_run_id` (FK), `semantic_type`, `content`, `confidence`, `embedding vector(1536)` | Intended home for individual atomic units + their embeddings. See Known Issues — the code doesn't fully populate this yet. The Rocchio step reads embeddings back via `getEmbeddedUnits`, joining `extracted_units → extraction_runs` on `source_id`. |

> The migration grants full DML (including `delete`/`truncate`) to the `anon` role.
> That is the default Supabase scaffolding and is fine for local dev, but must be
> tightened before any non-local deployment.

---

## Setup

### Prerequisites

- **Python 3.13** (`pyproject.toml` requires `>=3.13`).
- **[uv](https://docs.astral.sh/uv/)** for dependency management.
- **[Supabase CLI](https://supabase.com/docs/guides/cli)** (a local stack is used;
  see `supabase/config.toml`).
- An **OpenAI API key** (topic expansion, source discovery, extraction, and embeddings
  all call OpenAI).

### 1. Install dependencies

```bash
uv sync
```

> Note: `pyproject.toml` is the current source of truth. `requirements.txt` only
> covers the legacy scraper and will **not** install the pipeline's dependencies.

### 2. Start the local Supabase stack

```bash
supabase start          # boots Postgres, Studio, API on the ports in config.toml
supabase db reset       # applies migrations/ (creates the 4 tables + pgvector)
```

The API defaults to `http://127.0.0.1:54321`, Studio to `http://127.0.0.1:54323`.

### 3. Environment variables

`langgraph.json` loads `.env.local`. At minimum you'll want:

```bash
# .env.local
OPENAI_API_KEY=sk-...
```

> All other settings (Supabase URL/key, model ids, Rocchio α/β/γ, the loop cap)
> live in `src/app/config.py` and are overridable via env vars — see
> `.env.example`. The baked-in Supabase defaults are the CLI's public local-dev
> values, so the local stack works with zero extra config.

---

## Running

### The pipeline (LangGraph dev server)

```bash
uv run langgraph dev
```

This serves the `scraping_pipeline` graph (from `langgraph.json`) and the FastAPI app
in `src/agent/webapp.py`, which initializes the Supabase repo on startup. Open the
LangGraph Studio URL it prints, then invoke the graph with an input containing a
`topicText`, e.g.:

```json
{ "topicText": "quantum error correction" }
```

The run will expand the topic into subtopics, discover sources, extract and decompose
their content, and embed the resulting units — writing to the `topics`, `sources`,
`extraction_runs`, and `extracted_units` tables as it goes.

#### Human-in-the-loop: the source-selection interrupt

The graph **pauses** after source discovery: the `feedbackInterrupt` node calls
LangGraph's `interrupt()` and hands you the discovered sources — each with its
URL, discovery reason, and priority score, so the selection is reviewable. You
resume with the ids you consider *relevant* plus an action, and the
`centroidEmbedding` node uses that feedback to re-centre the topic centroid.
Choosing `"reextract"` loops the pipeline: the selected sources' discovery
reasons seed a new topic text and the whole discover → extract → embed cycle
runs again (bounded by `MAX_ITERATIONS`, default 3).

Because the graph interrupts, it must run with a **checkpointer** and a thread id. In
LangGraph Studio, the run will surface the `{"type": "source_selection", ...}`
payload and let you resume. Programmatically it looks like:

```python
from langgraph.types import Command

config = {"configurable": {"thread_id": "my-run"}}

# 1) First invocation pauses at the interrupt.
result = await graph.ainvoke({"topicText": "quantum error correction"}, config)
payload = result["__interrupt__"][0].value
# {"type": "source_selection", "source_ids": [...],
#  "sources": [{"id": ..., "source_url": ..., "discovery_reason": ..., "priority_score": ...}, ...]}

# 2) Resume with an action and the relevant source ids.
final = await graph.ainvoke(
    Command(resume={"action": "end", "selected_ids": ["src-id-1", "src-id-3"]}),
    config,
)
# final["topicCentroid"] is now the Rocchio-refined centroid.
# Use {"action": "reextract", ...} to run another discovery iteration instead.
```

> Note: `graph.compile()` in `graph.py` does **not** attach a checkpointer, so the
> interrupt only survives when the graph is served by a runtime that supplies one
> (the LangGraph dev server / API does). A bare `graph.ainvoke(...)` with no
> checkpointer cannot pause and resume.

### Querying the knowledge base (the read path)

Once a run has populated the store, the FastAPI app (served alongside the graph
by `langgraph dev`) exposes retrieval with citations. Similarity search runs
inside Postgres via the `match_units` RPC over an HNSW index — vectors never
ship to Python for scoring.

```bash
# Top-k atomic facts nearest the question, each with its source URL + reason
curl -s localhost:2024/query -X POST -H 'content-type: application/json' \
  -d '{"question": "How do surface codes correct errors?", "k": 5}'

# Same retrieval, then a synthesized answer with [n] citations
curl -s localhost:2024/answer -X POST -H 'content-type: application/json' \
  -d '{"question": "How do surface codes correct errors?"}'

# Browse what a run built
curl -s localhost:2024/topics
curl -s localhost:2024/topics/<topic_id>/sources
```

Pass `"thread_id": "<graph thread id>"` to either endpoint to **blend that
run's Rocchio-refined centroid into the query vector** (weighted sum,
L2-normalised) — retrieval then leans toward what the human marked relevant.
Both the initial and refined centroids are persisted per thread in
`topic_centroids` by `embedTopic` / `centroidEmbedding`.

### The legacy scraper

See [Legacy: the YouTube scraper](#legacy-the-youtube-scraper).

---

## Testing

Tests use `pytest` (config in `pyproject.toml`, `asyncio_mode = "auto"`,
`pythonpath = ["."]`; the seleniumbase/pytest-html plugins are disabled via
`addopts` so a bare run just works):

```bash
uv run pytest tests/ -v
```

### Suites

All suites are mock-only (no live Supabase or OpenAI) and pass:

| Suite | Covers |
| --- | --- |
| `tests/node/test_embed_units.py` | `embedUnits` — embeds each unique run once and returns the partial `{"sourceIds": [...]}` update (never the whole state). |
| `tests/node/test_topic_embed.py` | `topicEmbed` uses the configured embedding model and returns `topicCentroid`. |
| `tests/node/test_interrupt_selections.py` | `interruptSelections` — reviewable interrupt payload (URLs/reasons/scores), `{"action", "selected_ids"}` resume contract, partitioning, malformed-payload errors. |
| `tests/node/test_centroid_embedding.py` | `centroidEmbedding` wires the repo + `TransformationService` and returns the refined centroid. |
| `tests/unit/test_transformation_service.py` | `rocchio_embedding` math (α/β/γ terms, normalisation, zero-vector guard) and `compute_query_vector` orchestration. |
| `tests/unit/test_embed_service.py` | `embed_pending` — content + semantic_type inserted with each embedding, batching, and the strict-zip mismatch guard. |
| `tests/unit/test_get_embedded_units.py` | `SupabaseRepository.getEmbeddedUnits` — the `extracted_units ⋈ extraction_runs` filter and JSON→list embedding decode. |
| `tests/unit/test_topic_extraction_service.py` | `topicExtractionService.extract` persists the chain output and returns ids. |
| `tests/integration/test_feedback_loop.py` | `feedbackInterrupt → centroidEmbedding` in a real `StateGraph` with a `MemorySaver` checkpointer: invoke → pause → resume → recomputed centroid. |
| `tests/conftest.py` | Sets a dummy `OPENAI_API_KEY` so modules that build an `AsyncOpenAI()` at import time can be collected. |
| `tests/execdata.py` | Legacy scraper smoke test; launches a real browser (not part of the pipeline suite). |

---

## Does relevance feedback actually help? (evals)

`evals/` measures the Rocchio loop instead of assuming it works: for each
topic in a golden set it compares retrieval with the raw question embedding,
the question blended with the **initial** centroid, and the question blended
with the **Rocchio-refined** centroid — on P@k, MRR, and nDCG@k. Relevance
labels are source-level (the same signal the selection interrupt collects),
so no per-unit labeling is needed.

```bash
uv run python -m evals.run_eval --golden evals/golden.json --k 10
```

See [`evals/README.md`](evals/README.md) for the full workflow (run a topic →
select sources → author queries → run). The metric functions are pure and
covered by `tests/unit/test_eval_metrics.py`; results tables from real runs
belong here once generated.

---

## Known Issues / Review Findings

Most of the findings that used to live in this section were fixed by the
correctness pass on this branch (2026-07). Summary of what changed and what's
still open:

### Fixed

- **Browser fallback was silently dead.** `extractionService.py` did
  `from datetime import time` and then called `time.monotonic()` — an instant
  `AttributeError` swallowed by the fetch's exception handler, so the
  SeleniumBase tier never once returned HTML. Now `import time` (the module),
  and a total fetch failure records a `failed` run with
  `failure_reason='fetch_failed'` instead of burning an LLM call on empty text.
  The winning tier is recorded in `extraction_runs.extraction_strategy`.
- **Embeddings were orphaned from their text.** `extracted_units` rows now
  carry `content` and `semantic_type` alongside each `embedding`
  (`embed_pending` zips batch rows with the returned vectors, `strict=True`),
  so a similarity hit can always show the sentence it encodes.
- **Re-extract loop double-counted state.** `topicIds`/`sourceIds` used
  `operator.add` reducers, so the old "reset" (`{"topicIds": []}`) was a no-op
  and nodes returning the whole state doubled the channels each pass. They now
  use an `add_or_reset` reducer (write `None` to clear), all nodes return
  partial updates, `reconcileSources` performs the reset after reading the old
  ids, and `route_after_centroid` caps the loop at `MAX_ITERATIONS`.
- **Join-edge stall on iteration 2.** The
  `["embedTopic", "feedbackInterrupt"] → centroidEmbedding` barrier could
  never re-fire on a re-extract pass (embedTopic only runs from START); the
  edge is now simply `feedbackInterrupt → centroidEmbedding`.
- **Hardcoded Supabase connection.** Moved to env-driven `src/app/config.py`
  (pydantic-settings). The baked-in defaults are the CLI's public local-dev
  values, so `supabase start` still works with zero config. See `.env.example`.
- **`sourceDiscoveryService` prompt typos + unvalidated LLM JSON.** The stray
  `s` and no-op statement are gone, and discovered sources are validated with a
  pydantic model before insert (invalid entries are dropped and logged).
  Note: `gpt-5.4` is a **real, valid model id** (released 2026-03) — an earlier
  version of this README wrongly flagged it as a bug.
- **`getSources` filtered the wrong column** (`id` instead of `topic_id`).
- **Schema drift.** The code inserts `extraction_runs.topic_id`, which the
  initial migration never declared; migration
  `20260724120000_extraction_runs_topic_id.sql` captures it.
- **`embedUnits` contract.** Returns a partial `{"sourceIds": [...]}` update
  and tolerates a missing `source_ids` key; its tests match the real contract.
- **Tooling.** `openai`/`langchain-core`/`pydantic-settings` are declared
  direct dependencies; a bare `uv run pytest` works (the seleniumbase/
  pytest-html plugins are disabled via `addopts`); the broken live-Supabase
  `test_topicExtractor.py` was replaced by a mocked unit test.

### Still open

- **Over-broad DB grants.** The migration grants `delete`/`truncate`/`update`
  to the `anon` role on every table (default Supabase scaffolding). Fine
  locally; tighten before deploying.
- **Python version drift.** `pyproject.toml` requires `>=3.13`; the legacy
  `Makefile` uses `python3.12`.
- **CI still runs the legacy scraper** rather than the pipeline's test suite,
  and `requirements.txt` remains legacy-only (use `uv sync`).

---

## Legacy: the YouTube scraper

The original project — a multithreaded Selenium scraper for YouTube search results.
It is independent of the pipeline above.

**How it works:** `ScrapeRun.py` exposes a Click CLI whose `run-executor` command
builds a `SeleniumThreadPoolExecutor` (`exec/executor.py`). The executor keeps a pool
of **persistent** SeleniumBase browsers (one per worker) and feeds them a queue of
search queries. Each worker runs `YouTubeScraper.scrape` (`utils/YouTubeScraper.py`),
which opens the YouTube results page, scrolls to load more videos, collects each
video's title/link/channel/views and a datetime derived from the relative timestamp,
then visits each video to scrape comments. Results are written to
`./{query}_scrape.json`.

**Run it:**

```bash
# Requires Chrome + ChromeDriver (see the Makefile targets)
make install
make install-chrome install-chromedriver
make run-scraper

# or directly:
python ScrapeRun.py run-executor \
    --queries "Python programming tutorials" \
    --queries "Machine learning basics" \
    --max-cpu-count 4
```

**Caveats:** scraping YouTube may violate its Terms of Service; the executor's own
docstrings flag some awkward API design (`class_ref` / `max_cpu_usage` are more
convoluted than they need to be); and `YouTubeScraper.search()` is an empty method
(search is done via the results URL, not the search box).

---

*This README documents the repository as it stands, including its rough edges. If you
fix an item under [Known Issues](#known-issues--review-findings), please update that
section too.*
