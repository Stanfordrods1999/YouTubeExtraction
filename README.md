# YouTube Extraction — LLM Research & Extraction Pipeline

Turn a single **topic** into a researched, structured, and (eventually) **vector-searchable knowledge base**.

This project began as a multithreaded Selenium YouTube scraper and has grown into an **LLM-powered
research pipeline** orchestrated with [LangGraph](https://langchain-ai.github.io/langgraph/). Given a
topic, it expands it into researchable subtopics, then discovers high-quality sources for each one in
parallel, persisting everything to a Postgres (Supabase) data model that is purpose-built for a later
**content-extraction + embedding** stage. The original YouTube scraper is retained as a **legacy
ingestion component** (see [Legacy: YouTube Scraper](#legacy-youtube-selenium-scraper)).

---

## Table of Contents

1. [Architecture at a Glance](#architecture-at-a-glance)
2. [The Pipeline (LangGraph)](#the-pipeline-langgraph)
3. [Data Model](#data-model)
4. [Tech Stack](#tech-stack)
5. [Project Structure](#project-structure)
6. [Setup](#setup)
7. [Running](#running)
8. [Testing](#testing)
9. [Legacy: YouTube Selenium Scraper](#legacy-youtube-selenium-scraper)
10. [Data Engineering Roadmap](#data-engineering-roadmap)
11. [Contributing](#contributing)
12. [License](#license)

---

## Architecture at a Glance

The system is a directed pipeline. A topic flows in, fans out into subtopics, and each subtopic is
researched independently:

```
                ┌──────────────────┐
   topicText ──►│  topicExtractor  │   GPT-4.1-mini → subtopics → INSERT topics
                └────────┬─────────┘   returns topicIds[]
                         │
                 fan_out_sources              (conditional edge — a "map" step)
                 one Send() per topicId
            ┌────────────┼────────────┐
            ▼            ▼            ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │sourceExtr. │ │sourceExtr. │ │sourceExtr. │   GPT-5.4 + web_search
   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘   → INSERT sources
         └──────────────┼──────────────┘
                        ▼
                       END
```

The database schema already models **two stages beyond what the code does today** — content extraction
and embedding — which is exactly where the project is headed:

```
topics ──1:N──► sources ──1:N──► extraction_runs ──1:N──► extracted_units
  ✅ built         ✅ built          ⏳ schema only           ⏳ schema only
                                                            embedding vector(1536)  ← RAG / semantic search
```

Legend: ✅ implemented today · ⏳ table exists in the migration but is not yet written to by code.

---

## The Pipeline (LangGraph)

The graph is defined in [`src/app/graph/graph.py`](src/app/graph/graph.py) and compiled as
`scrapingPipeline`. It is registered for the LangGraph runtime in
[`langgraph.json`](langgraph.json) as the `scraping_pipeline` graph.

### Shared state

State flows through the graph as a typed dict, [`GlobalState`](src/app/graph/state.py):

| Field | Type | Purpose |
| --- | --- | --- |
| `topicText` | `str` | The original input topic. |
| `topicState` | `Optional[List[TopicState]]` | Optional list of structured topics. |
| `topicIds` | `Annotated[List[str], operator.add]` | IDs of persisted topics. The `operator.add` reducer **accumulates** ids across nodes. |

### Nodes

**1. `topicExtractor`** — *entry node*
([node](src/app/graph/nodes/topicExtractor.py) ·
[service](src/app/services/topicExtractionService.py))

- **Input:** `topicText`.
- **Work:** runs a `ChatPromptTemplate → ChatOpenAI(gpt-4.1-mini, temperature=0) → JsonOutputParser`
  chain to expand the topic into independently-researchable subtopics (each with `topicText`, `status`,
  `createdBy`, `confidence`, `metadata`).
- **Output:** persists subtopics to the `topics` table and returns `{"topicIds": [...]}` into shared state.

**2. `fan_out_sources`** — *conditional edge (router, not a node)*
([graph.py](src/app/graph/graph.py))

- For each `topicId`, emits a `Send("sourceExtractor", {"topic_id": topicId})`, dynamically spawning
  **one parallel `sourceExtractor` branch per topic**. This is the classic LangGraph **map / fan-out**
  pattern.

**3. `sourceExtractor`** — *fan-out worker*
([node](src/app/graph/nodes/sourceExtractor.py) ·
[service](src/app/services/sourceDiscoveryService.py))

- **Input:** a single `topic_id`.
- **Work:** loads topic metadata, then calls `ChatOpenAI(gpt-5.4)` bound to the
  `web_search_preview` tool to find **5–15** relevant sources, each typed
  (`article | research_paper | website | government_report | news | video | other`), URL-bearing,
  reasoned, and scored (`priority_score` ∈ [0, 1]).
- **Output:** persists discovered sources to the `sources` table (linked by `topic_id`).

### Flow

```
START → topicExtractor → (fan_out_sources) → sourceExtractor × N → END
```

---

## Data Model

Defined in [`supabase/migrations/`](supabase/migrations/) on Postgres with the **pgvector** extension.

| Table | Key columns | Status |
| --- | --- | --- |
| `topics` | `id`, `topic_text`, `status`, `confidence`, `created_by`, `metadata (jsonb)` | ✅ written by `topicExtractor` |
| `sources` | `id`, `topic_id → topics`, `source_type`, `source_url`, `discovery_reason`, `priority_score`, `status` | ✅ written by `sourceExtractor` |
| `extraction_runs` | `id`, `source_id → sources`, `extraction_strategy`, `status`, `confidence`, `failure_reason`, `started_at`, `completed_at`, `requires_human`, `metadata (jsonb)` | ⏳ schema only |
| `extracted_units` | `id`, `extraction_run_id → extraction_runs`, `semantic_type`, `content`, `source_offset`, `confidence`, `embedding vector(1536)` | ⏳ schema only |

`extraction_runs` and `extracted_units` are the foundation for the next phase: fetching content from each
discovered source, splitting it into semantic units, and embedding those units for retrieval. The
`requires_human` flag on `extraction_runs` signals a planned **human-in-the-loop** review path.

Data access is centralized in [`db/supabaseRepository.py`](db/supabaseRepository.py)
(`getTopicMetadata`, `createTopic`, `createSources`), instantiated as a singleton in
[`db/session.py`](db/session.py) and initialized via the FastAPI lifespan in
[`src/agent/webapp.py`](src/agent/webapp.py).

> ⚠️ **Configuration note:** the Supabase URL and key are currently **hardcoded** in
> `db/supabaseRepository.py` (a local-dev key pointing at `127.0.0.1:54321`). Before any non-local use,
> move these to environment variables (`SUPABASE_URL`, `SUPABASE_KEY`). See [Setup](#setup).

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Language / tooling | Python **3.13**, [`uv`](https://docs.astral.sh/uv/) (lockfile: `uv.lock`) |
| Orchestration | LangGraph (`langgraph-cli[inmem]`) |
| LLM | LangChain (`langchain-openai`, `langchain-core`) + OpenAI (`gpt-4.1-mini`, `gpt-5.4` + web search) |
| Data store | Supabase (Postgres 17 + **pgvector**), async `supabase` client |
| API | FastAPI (`fastapi[standard]`) |
| Legacy scraping | Selenium 4.26.1, SeleniumBase 4.32.12, undetected-chromedriver |
| Quality / test | pytest, pytest-asyncio, flake8 (+ bugbear, docstrings) |

> **Heads-up:** `langchain-openai` and `langchain-core` are imported by the services but are **not yet
> declared** in `pyproject.toml`. Until that's fixed, install them explicitly (see [Setup](#setup)).

---

## Project Structure

```
YouTubeExtraction/
├── src/
│   ├── agent/
│   │   └── webapp.py                      # FastAPI app (lifespan-managed Supabase client)
│   └── app/
│       ├── graph/
│       │   ├── graph.py                   # LangGraph definition (scrapingPipeline)
│       │   ├── state.py                   # GlobalState / TopicState / sourceDiscoveryState
│       │   └── nodes/
│       │       ├── topicExtractor.py      # Node: topic → subtopics
│       │       └── sourceExtractor.py     # Node: topic_id → sources
│       └── services/
│           ├── topicExtractionService.py  # GPT-4.1-mini topic chain
│           └── sourceDiscoveryService.py  # GPT-5.4 + web-search source discovery
├── db/
│   ├── session.py                         # Repo singleton (init_repo / get_repo)
│   └── supabaseRepository.py              # Async Supabase data-access layer
├── supabase/
│   ├── config.toml                        # Local Supabase stack config
│   └── migrations/                        # Schema: topics, sources, extraction_runs, extracted_units
├── utils/
│   └── YouTubeScraper.py                  # Legacy: Selenium YouTube scraper
├── exec/
│   └── executor.py                        # Legacy: SeleniumThreadPoolExecutor
├── logs/
│   └── Logging.py                         # Logging helper
├── tests/
│   ├── integration/
│   │   └── test_topicExtractor.py         # Async pipeline test
│   └── execdata.py                        # Test fixtures / queries
├── ScrapeRun.py                           # Legacy: Click CLI entry for the scraper
├── main.py                                # Trivial entry point
├── langgraph.json                         # LangGraph deploy config
├── pyproject.toml                         # Project + dependencies (uv)
├── requirements.txt                       # Legacy dependency subset (scraper only)
└── Makefile                               # Legacy scraper build/run targets
```

---

## Setup

### 1. Prerequisites

- **Python 3.13** (see `.python-version`)
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- [Supabase CLI](https://supabase.com/docs/guides/local-development) for the local Postgres stack
- An **OpenAI API key**
- *(Legacy scraper only)* Google Chrome + ChromeDriver

### 2. Install dependencies

```bash
uv sync
# langchain deps are used by the services but not yet declared — add them explicitly:
uv pip install langchain-openai langchain-core
```

> `requirements.txt` is a **legacy subset** kept for the old scraper's CI. Prefer `uv sync`.

### 3. Configure environment

Create a `.env.local` (loaded by LangGraph via `langgraph.json`):

```bash
OPENAI_API_KEY=sk-...
# Recommended once the hardcoded values are removed from db/supabaseRepository.py:
# SUPABASE_URL=http://127.0.0.1:54321
# SUPABASE_KEY=your-local-service-key
```

### 4. Start Supabase & apply the schema

```bash
supabase start          # boots local Postgres + API on 127.0.0.1:54321
supabase db reset       # applies migrations in supabase/migrations/
```

---

## Running

### The LangGraph pipeline (primary)

Launch the LangGraph dev server (in-memory runtime + Studio UI):

```bash
uv run langgraph dev
```

Then invoke the `scraping_pipeline` graph with an input such as:

```json
{ "topicText": "Renewable energy storage" }
```

The run will populate the `topics` and `sources` tables.

### The FastAPI app

The app in [`src/agent/webapp.py`](src/agent/webapp.py) initializes the Supabase repository on startup
and is served by the LangGraph runtime (`http.app` in `langgraph.json`).

### Legacy scraper

See [Legacy: YouTube Selenium Scraper](#legacy-youtube-selenium-scraper).

---

## Testing

```bash
uv run pytest
```

The async integration test [`tests/integration/test_topicExtractor.py`](tests/integration/test_topicExtractor.py)
mocks the LLM chain (`_run_extraction_chain`) and asserts topics are inserted. `pytest` is configured for
`asyncio_mode = "auto"` in `pyproject.toml`.

> The `make test` / `make lint` targets are **legacy** (they reference Python 3.12 and an old test path).
> Use `uv run pytest` and `uv run flake8 src tests` directly.

---

## Legacy: YouTube Selenium Scraper

The original component scrapes YouTube search results with a custom thread-pool executor over persistent,
undetected Chrome drivers. It is **independent of the LangGraph pipeline** and is kept as a candidate
**ingestion / extraction strategy** for the roadmap below.

- **Entry point:** [`ScrapeRun.py`](ScrapeRun.py) (Click CLI)
- **Executor:** [`exec/executor.py`](exec/executor.py) — `SeleniumThreadPoolExecutor` distributes queries
  across worker drivers via `multiprocessing` queues and threads.
- **Scraper:** [`utils/YouTubeScraper.py`](utils/YouTubeScraper.py) — extracts title, link, channel,
  views, publish time, and comments.

```bash
export SELENIUMBASE_CHROME_DRIVER=/path/to/chromedriver
uv run python ScrapeRun.py run-executor \
    --queries "Python programming tutorials" \
    --queries "Machine learning basics" \
    --max-cpu-count 4 --max-cpu-usage
```

Output: one JSON file per query, `"{query}_scrape.json"`, with records of the form:

```json
{
  "Search_Query": "...",
  "Link": "...",
  "Title": "...",
  "YT_Channel": "...",
  "YT_Views": "...",
  "YT_Time": "MM/DD/YYYY, HH:MM:SS",
  "Comments": ["...", "..."]
}
```

Convenience target: `make run-scraper` (installs Chrome/ChromeDriver via `make install-chrome
install-chromedriver` first).

---

## Data Engineering Roadmap

The current pipeline is a solid **operational core**, but it lacks production data-engineering tooling for
validation, scheduling, scalable extraction, and analytics. This section maps tools onto the existing
4-stage data model and — importantly — explains **when each one earns its place**, so the architecture can
grow incrementally rather than all at once.

### Target architecture

```
 PRODUCERS                  BUS / QUEUE              CONSUMERS / WORKERS           STORES & SERVING
 ─────────                  ───────────              ───────────────────          ────────────────
 topic intake ─┐                                  ┌─► content extractor ─┐
 source disc.  ├─►  queue (Phase 2)            ┌─►├─► chunker            ├─► Postgres + pgvector  (operational)
 YT scraper  ──┘    Kafka  (Phase 3)  ─────────┘  └─► embedder ──────────┘   Parquet lake + dbt/DuckDB (analytics)
```

### Phase 1 — Harden what exists (do this first)

| Concern | Gap today | Recommended | Why |
| --- | --- | --- | --- |
| **Validation & data quality** | Loose `TypedDict`s; raw `json.loads` of LLM output | **Pydantic v2** for node I/O; **Pandera** for row-frame checks before insert | Fail fast on malformed LLM JSON; give nodes typed contracts |
| **Orchestration & scheduling** | Graph invoked manually | **Prefect** *or* **Dagster** | Scheduling, retries, backfills, run observability. LangGraph stays as the *in-run* graph; the orchestrator drives runs around it |

*Recommendation:* pick **Dagster** if you want to think in assets/lineage (a natural fit for
`topics → sources → units`); pick **Prefect** for lighter-weight flows.

### Phase 2 — Build the missing stages (`extraction_runs → extracted_units`)

| Concern | Recommended | Notes |
| --- | --- | --- |
| **Content extraction** | `httpx` + `trafilatura`/`readability`, plus the **Selenium scraper as one strategy** | One `extraction_run` per source, recording `status` / `extraction_strategy` / `confidence` / `requires_human` |
| **Chunking & embeddings** | LangChain text splitters → OpenAI embeddings → `extracted_units.embedding` | Builds the searchable knowledge base feeding RAG / semantic search |
| **Decoupling workers** | A simple **work queue** first — Postgres-backed, or **Redis + RQ/Celery** | Lets extraction/embedding workers scale independently of discovery, *without* the weight of Kafka |

### Phase 3 — Scale & analytics (only when volume justifies it)

| Concern | Recommended | Notes |
| --- | --- | --- |
| **Event streaming** | **Apache Kafka** as the durable event bus | Topics like `sources.discovered → content.extracted → units.embedded` |
| **Analytics & modeling** | **dbt + DuckDB**, **Parquet** on object storage | A small "lake" + transformation layer for metrics, data-quality marts, and lineage alongside operational Supabase |

#### Where does Kafka fit — and do you need it yet?

Kafka is a **durable, replayable event log** that decouples *producers* (topic/source discovery, always-on
scrapers) from *consumers* (extraction, embedding workers). It shines when you need independent scaling per
stage, backpressure/durability, and **replay** — e.g. re-embedding the entire corpus with a new model by
replaying `content.extracted`.

But Kafka is **operationally heavy**. Start with a queue (Phase 2) and adopt Kafka only when at least one is
true:

- **Continuous, high-volume ingestion** (always-on scrapers/streams, not one run per topic).
- **Multiple independent consumers** need the *same* event stream.
- You need **durable buffering + replay** as a first-class capability.

If none apply yet, a Postgres/Redis-backed queue gives you 80% of the benefit at 20% of the cost.

> **Start here:** add **Pydantic** + **one orchestrator** before anything else → then build the
> **extraction + embedding** stages behind a **simple queue** → add **Kafka** and the **dbt/DuckDB**
> analytics layer **last**, only when scale demands it.

---

## Contributing

1. Branch from the active development branch.
2. Keep changes typed and tested (`uv run pytest`, `uv run flake8 src tests`).
3. Open a pull request describing the change and which pipeline stage(s) it touches.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
