# YouTubeExtraction

> A research **knowledge-extraction pipeline** built on LangGraph + Supabase/pgvector.
> It started life as a multithreaded YouTube scraper (still in the repo), but the
> active project is now a topic → source → extraction → embedding pipeline that turns
> a single research topic into a searchable store of embedded "atomic facts."

⚠️ **Status: work in progress.** The pipeline runs end-to-end in spirit but several
nodes have known bugs (see [Known Issues / Review Findings](#known-issues--review-findings)).
Treat this README as a map of *what the code is trying to do*, with the rough edges
called out honestly.

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
                        │        │  embedUnits ── batch-embed atomic units       │
                        │        │   (OpenAI embeddings → pgvector)              │
                        │        └─────────────────────────────────────────────┘
                        │
                        └───────►┌──────────────┐
                                 │  embedTopic   │──── embeds the raw topic text (runs in
                                 │ (topicEmbed)  │      parallel with topicExtractor)
                                 └──────────────┘
```

### Stage-by-stage (node → service → table)

| Stage | Node | Service | Model / tool | Writes |
| --- | --- | --- | --- | --- |
| Topic expansion | `nodes/topicExtractor.py` | `services/topicExtractionService.py` | `gpt-4.1-mini` (JSON output) | `topics` |
| Topic embedding | `nodes/topicEmbed.py` | *(inline OpenAI call)* | OpenAI embeddings | *(returns embedding to state)* |
| Source discovery | `nodes/sourceExtractor.py` | `services/sourceDiscoveryService.py` | `ChatOpenAI` + `web_search_preview` tool | `sources` |
| Content extraction | `nodes/runExtractor.py` | `services/extractionService.py` | curl_cffi → SeleniumBase fallback, `trafilatura`, `gpt-4.1-mini` structured output | `extraction_runs` |
| Unit embedding | `nodes/embedUnits.py` | `services/embeddingServices.py` | `text-embedding-3-small` | `extracted_units` |

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
- **Rocchio relevance feedback.** `services/transformationService.py` implements the
  classic Rocchio query-refinement formula
  (`α·q0 + β·mean(relevant) − γ·mean(non-relevant)`), intended to re-center the topic
  centroid from feedback. **It is not yet wired into the graph.**

---

## Repository layout

```
YouTubeExtraction/
├── langgraph.json                 # LangGraph entry: graph `scraping_pipeline` + FastAPI app
├── pyproject.toml                 # Current dependency source of truth (uv, Python ≥3.13)
├── main.py                        # Unused "Hello" stub
│
├── src/
│   ├── app/
│   │   ├── graph/
│   │   │   ├── graph.py            # Top-level StateGraph (topicExtractor + embedTopic → sourceDiscovery)
│   │   │   ├── state.py            # TypedDict states: GlobalState / TopicState / sourceDiscoveryState
│   │   │   ├── nodes/              # Thin graph nodes (delegate to services)
│   │   │   │   ├── topicExtractor.py
│   │   │   │   ├── topicEmbed.py
│   │   │   │   ├── sourceExtractor.py
│   │   │   │   ├── runExtractor.py
│   │   │   │   ├── embedUnits.py
│   │   │   │   ├── centroidEmbedding.py   # incomplete (see Known Issues)
│   │   │   │   └── interruptSelections.py # empty placeholder (human-in-the-loop?)
│   │   │   └── subgraphs/
│   │   │       └── sourceDiscovery.py      # map-reduce subgraph: sourceExtractor → runExtractor → embedUnits
│   │   ├── services/               # Business logic + LLM/HTTP calls
│   │   │   ├── topicExtractionService.py
│   │   │   ├── sourceDiscoveryService.py
│   │   │   ├── extractionService.py        # fetch → clean → atomic-unit decomposition
│   │   │   ├── embeddingServices.py
│   │   │   └── transformationService.py    # Rocchio (not yet wired in)
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
│   ├── node/test_embed_units.py    # Unit tests for the embedUnits node (solid)
│   ├── unit/test_embed_service.py  # Tests the *intended* embed_pending shape (see Known Issues)
│   ├── integration/test_topicExtractor.py  # Currently broken (see Known Issues)
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
| `extracted_units` | `id`, `extraction_run_id` (FK), `semantic_type`, `content`, `confidence`, `embedding vector(1536)` | Intended home for individual atomic units + their embeddings. See Known Issues — the code doesn't fully populate this yet. |

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
> Also see Known Issues — a few imported packages (`openai`, `langchain-openai`,
> `langchain-core`) are not yet declared in `pyproject.toml`.

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

> Supabase connection details are currently **hardcoded** in
> `db/supabaseRepository.py` (local URL + a local `sb_secret_...` key). See Known
> Issues — these should be moved to env vars before connecting to any real project.

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

### The legacy scraper

See [Legacy: the YouTube scraper](#legacy-the-youtube-scraper).

---

## Testing

Tests use `pytest` (config in `pyproject.toml`, `asyncio_mode = "auto"`,
`pythonpath = ["."]`).

```bash
uv run pytest tests/ -v
```

| Suite | State |
| --- | --- |
| `tests/node/test_embed_units.py` | **Solid.** Thorough unit tests for the `embedUnits` node (dedup, summing, error propagation, call-time DI). |
| `tests/unit/test_embed_service.py` | **Aspirational.** Asserts an id-keyed `{"id", "embedding"}` update shape that the current `embeddingService`/repo don't produce — documents the intended fix rather than current behavior. |
| `tests/integration/test_topicExtractor.py` | **Broken.** Passes `llm=None` to a constructor that doesn't accept it and asserts `result is List[str]`. Also hits a live local Supabase. |
| `tests/execdata.py` | Legacy scraper smoke test; launches a real browser. |

> The `Makefile` `test` target points at `tests/test_execdata.py`, which does not
> exist (the file is `tests/execdata.py`).

---

## Known Issues / Review Findings

These were found while parsing the code and are documented here so they're visible.
**No code has been changed** — this is a review, not a fix.

### Correctness bugs (pipeline)

1. **`nodes/topicEmbed.py` — wrong model + dropped result.**
   It calls `client.embeddings.create(model=MODEL, ...)` where `MODEL` is
   `"gpt-4.1-mini"` (imported from `extractionService`) — a **chat** model, not an
   embedding model, so the call will error. It also returns
   `{"topicEmbedding": ...}`, but `GlobalState` (in `graph/state.py`) has no
   `topicEmbedding` key (it defines `topicCentroid`), so even a successful result
   would be dropped by LangGraph.

2. **`services/sourceDiscoveryService.py` — invalid model + prompt typos.**
   `ChatOpenAI(model="gpt-5.4")` is not a real model id and will fail at call time.
   The prompt string has a **stray `s`** on its own line, and there is a no-op
   statement `metadata["topic_text"]` (line ~35) that does nothing.

3. **Embeddings are orphaned from their text.**
   `runExtractor`/`extractionService` store atomic units **inside**
   `extraction_runs.metadata` (JSON). `embeddingService.embed_pending` then reads
   that JSON, embeds each unit's `text`, and calls `updateUnitEmbeddings` — which
   **inserts** brand-new `extracted_units` rows containing only
   `{extraction_run_id, embedding}`. The unit `content` is never written, and the
   embeddings aren't linked back to the specific unit they came from. The repo's own
   TODO at `db/supabaseRepository.py:129` acknowledges this ("Need to alter and
   migrate data in metadata to create a new column called text"). Consequently
   `tests/unit/test_embed_service.py` — which expects `{"id", "embedding"}` keyed by
   unit id — does not match the current code.

4. **`db/supabaseRepository.py` — `getSources` filters the wrong column.**
   It does `.eq('id', topic_id)` where it should be `.eq('topic_id', topic_id)`.
   (This method is currently unused, but the query is wrong.)

5. **`nodes/centroidEmbedding.py` is a broken stub** — its entire contents are the
   token `import ` (a `SyntaxError` if it were ever imported). `nodes/interruptSelections.py`
   is empty (likely a placeholder for a human-in-the-loop interrupt that isn't built yet).

6. **`services/transformationService.py` — `rocchio_embedding` is missing `self`.**
   It's declared as an instance method but its signature starts with `q0`, so calling
   it on an instance would bind `q0` to `self`. It's effectively a static method
   (missing `@staticmethod`) and isn't wired into the graph anyway.

### Configuration & tooling

7. **Missing declared dependencies.** `pyproject.toml` imports `openai`,
   `langchain-openai`, and `langchain-core` at runtime but doesn't list them as
   direct dependencies. They may resolve transitively today, but that's fragile.

8. **Python version drift.** `pyproject.toml` requires `>=3.13`; the `Makefile` uses
   `python3.12`; the old README claimed 3.12. Pick one.

9. **`requirements.txt` is legacy-only.** It has no `langgraph`, `openai`,
   `langchain`, `supabase`, `trafilatura`, or `curl-cffi` — installing from it will
   not give you a working pipeline. Use `uv sync`.

10. **CI runs the wrong thing.** `.github/workflows/makefile.yml` runs
    `make run-scraper`, which launches real Chrome browsers to scrape YouTube inside
    GitHub Actions — slow, flaky, and unrelated to the pipeline. The `make test`
    target references a non-existent `tests/test_execdata.py`.

### Security / operational

11. **Hardcoded Supabase credentials.** `db/supabaseRepository.py:16-17` hardcodes the
    local URL and `sb_secret_...` key. Even though these are local-dev values, they
    should be read from the environment so the code works against a real project and
    no key is committed.

12. **Over-broad DB grants.** The migration grants `delete`/`truncate`/`update` to the
    `anon` role on every table (default Supabase scaffolding). Fine locally; tighten
    before deploying.

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
