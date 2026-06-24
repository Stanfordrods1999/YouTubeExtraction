# YouTubeExtraction — Architecture (state as of now)

This document captures **what the codebase is doing today**. The repo is mid-migration
from the original Selenium YouTube scraper to a **LangGraph-based research/extraction
pipeline**. Both code paths currently coexist.

> TL;DR
> - **Legacy path** (`ScrapeRun.py` → `executor.py` → `YouTubeScraper.py`): multithreaded
>   Selenium scraper that dumps YouTube results to JSON files. Still present; the README
>   describes this one.
> - **Current path** (`src/app/graph/...` + `db/` + `supabase/`): a LangGraph pipeline that
>   expands a topic → discovers web sources → extracts page content, persisting everything
>   to a local Supabase (Postgres + pgvector). This is where the recent commits live
>   (`content extraction && subgraph creation`, `fixing html retrieval && fan out extractions`).

---

## 1. System overview — two paths

```mermaid
flowchart LR
    subgraph LEGACY["Legacy path — Selenium scraper (still in repo, described by README)"]
        direction TB
        L1["ScrapeRun.py<br/>click CLI: run-executor"]
        L2["exec/executor.py<br/>SeleniumThreadPoolExecutor<br/>mp.Queue + Thread pool + undetected Chrome"]
        L3["utils/YouTubeScraper.py<br/>open → scroll → collect videos → comments"]
        L4["per-query *_scrape.json files on disk"]
        L1 --> L2 --> L3 --> L4
    end

    subgraph NEW["Current path — LangGraph research pipeline (recent work)"]
        direction TB
        N1["langgraph.json<br/>graph: scraping_pipeline<br/>http app: src/agent/webapp.py"]
        N2["StateGraph<br/>topicExtractor → sourceDiscovery (subgraph)"]
        N3["Services + LLMs + web fetch"]
        N4["Supabase local Postgres + pgvector<br/>topics / sources / extraction_runs / extracted_units"]
        N1 --> N2 --> N3 --> N4
    end

    classDef legacy fill:#fde2e2,stroke:#c0392b,color:#000;
    classDef neo fill:#e2f0fd,stroke:#2471a3,color:#000;
    class L1,L2,L3,L4 legacy;
    class N1,N2,N3,N4 neo;
```

---

## 2. Current LangGraph pipeline (the detailed view)

Entry: `langgraph.json` registers the compiled graph `src.app.graph.graph:graph`
(`scrapingPipeline`) and a FastAPI HTTP app (`webapp.py`) whose lifespan calls
`init_repo()` to create the singleton `SupabaseRepository`.

The pipeline is **two levels of map-reduce fan-out** using LangGraph `Send`:

- **Level 1:** one `sourceDiscovery` subgraph run **per extracted topic**.
- **Level 2:** inside each subgraph, one `runExtractor` run **per discovered source**.

```mermaid
flowchart TD
    START((START)) --> TE["node: topicExtractor"]

    %% ---- topicExtractor internals ----
    TE --> TES["topicExtractionService.extract(state)"]
    TES --> LLM1{{"ChatOpenAI gpt-4.1-mini<br/>topic → related subtopics (JSON)"}}
    LLM1 --> TINS["repo.createTopic() → INSERT topics"]
    TINS --> TIDS["returns topicIds[]<br/>state.topicIds (operator.add)"]

    %% ---- fan out level 1 ----
    TIDS -. "fan_out_sources: Send('sourceDiscovery', {topic_id}) — one per topic" .-> SE

    subgraph SDG["subgraph: sourceDiscovery  (name = source-map-reduce, per topic)"]
        direction TB
        SDSTART((START)) --> SE["node: sourceExtractor"]

        %% sourceExtractor internals
        SE --> SES["sourceDiscoveryService.extract(state)"]
        SES --> SMETA["repo.getTopicMetadata() → SELECT topic"]
        SMETA --> LLM2{{"ChatOpenAI gpt-5.4 + web_search_preview<br/>find 5–15 sources (JSON)"}}
        LLM2 --> SINS["repo.createSources() → INSERT sources"]
        SINS --> SIDS["returns source_ids[]"]

        %% ---- fan out level 2 ----
        SIDS -. "fan_out_runs: Send('runExtractor', {source_id, source_url, topic_id}) — one per source" .-> RE

        RE["node: runExtractor"] --> RES["extractionService.extract()"]
        RES --> FETCH{{"curl_cffi AsyncSession.get(source_url)<br/>impersonate=chrome, timeout=30"}}
        FETCH --> PARSE["trafilatura → readable_text<br/>BeautifulSoup → JSON-LD structured data"]
        PARSE --> RINS["repo.createExtractions() → INSERT extraction_runs"]
    end

    SDG --> END((END))

    classDef node fill:#d5f5e3,stroke:#1e8449,color:#000;
    classDef svc fill:#fcf3cf,stroke:#b7950b,color:#000;
    classDef ext fill:#ebdef0,stroke:#6c3483,color:#000;
    classDef db fill:#d6eaf8,stroke:#21618c,color:#000;
    class TE,SE,RE node;
    class TES,SES,RES svc;
    class LLM1,LLM2,FETCH,PARSE ext;
    class TINS,TIDS,SMETA,SINS,SIDS,RINS db;
```

### Layer map (node → service → external/DB)

| Graph node | Service | LLM / network | DB writes (SupabaseRepository) |
|---|---|---|---|
| `topicExtractor` | `topicExtractionService` | `gpt-4.1-mini` (subtopic expansion) | `createTopic()` → `topics` |
| `sourceExtractor` | `sourceDiscoveryService` | `gpt-5.4` + `web_search_preview` | `getTopicMetadata()` read; `createSources()` → `sources` |
| `runExtractor` | `extractionService` | `curl_cffi` HTTP GET → `trafilatura` + `BeautifulSoup` | `createExtractions()` → `extraction_runs` |

All DB access funnels through the `SupabaseRepository` singleton, obtained via
`db/session.py` (`init_repo()` / `get_repo()`), pointed at a **local** Supabase
(`http://127.0.0.1:54321`).

---

## 3. Data model (Supabase / Postgres)

Defined in `supabase/migrations/20260616094321_init_changes.sql`.

```mermaid
erDiagram
    topics ||--o{ sources : "topic_id"
    sources ||--o{ extraction_runs : "source_id"
    extraction_runs ||--o{ extracted_units : "extraction_run_id"

    topics {
        uuid id PK
        text topic_text
        text status
        text created_by
        float confidence
        timestamp created_at
        jsonb metadata
    }
    sources {
        uuid id PK
        uuid topic_id FK
        text source_type
        text source_url
        text discovery_reason
        float priority_score
        text status
        timestamp created_at
    }
    extraction_runs {
        uuid id PK
        uuid source_id FK
        text extraction_strategy
        text status
        float confidence
        text failure_reason
        timestamp started_at
        timestamp completed_at
        bool requires_human
        jsonb metadata
    }
    extracted_units {
        uuid id PK
        uuid extraction_run_id FK
        text semantic_type
        text content
        text source_offset
        float confidence
        vector embedding "1536-dim (pgvector)"
        timestamp created_at
    }
```

---

## 4. Status / known gaps (as of now)

These are observations from the current code, useful context for the next steps:

- **`extracted_units` is defined but never written.** The pipeline stops at
  `extraction_runs` (raw `metadata`). The semantic-unit + embedding stage
  (the `vector(1536)` column) is not implemented yet.
- **`runExtractor` returns nothing** — it writes `extraction_runs` but does not push
  state back, so the reduce step has no aggregated output.
- **`extraction_runs` insert is partial** — only `source_id`, `topic_id`, `metadata`
  are written; `status`, `extraction_strategy`, `started_at`/`completed_at`,
  `confidence` stay null.
- **`getSources()` (priority-filtered fetch) exists but is unused** in the graph;
  sources flow straight from `createSources()`'s return value into the fan-out.
- **Supabase URL + service key are hard-coded** in `db/supabaseRepository.py`.
- **Tests are stale vs. current code**: `tests/integration/test_topicExtractor.py`
  constructs `topicExtractionService(repo=..., llm=None)`, but the service `__init__`
  no longer accepts `llm`; assertions (`result is List[str]`) are also placeholders.
- **Two model-name oddities** to confirm: `gpt-5.4` and `gpt-4.1-mini` in the services.
- **README still documents the legacy Selenium scraper**, not this pipeline.
