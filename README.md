# YouTubeExtraction

> A research **knowledge-extraction pipeline** built on LangGraph + Supabase/pgvector.
> It started life as a multithreaded YouTube scraper (still in the repo), but the
> active project is now a topic → source → extraction → embedding pipeline that turns
> a single research topic into a searchable store of embedded "atomic facts."

⚠️ **Status: work in progress.** The pipeline runs end-to-end in spirit but several
nodes have known bugs (see [Known Issues / Review Findings](#known-issues--review-findings)).
Treat this README as a map of *what the code is trying to do*, with the rough edges
called out honestly.

📍 **Documented at `5d7ac8b` (`Admission Gate Logic`).** The graph has changed twice
since this README last described it, and both changes are structural:

| Commit | What it did to the graph |
| --- | --- |
| `7609df7` `makeFeedbackLoop` | Turned a straight line into a **cycle**. The human's answer at the interrupt now carries an *action* as well as a selection, and `reextract` routes the run back through `topicExtractor` with a rebuilt topic. → [details](#what-the-feedback-loop-commit-changed) |
| `5d7ac8b` `Admission Gate Logic` | Inserted **`admitTopics`** between `topicExtractor` and the fan-out, and moved the fan-out itself into that node. On a re-extract round it ranks the new subtopics by cosine similarity to the refined centroid and admits only the top 5 — the **first thing in the repo that reads `topicCentroid` back**. → [details](#what-the-admission-gate-commit-changed) |

Between them they also fixed two of the loop bugs this README recorded and left one
open — see [Known Issues](#the-feedback-loop-and-admission-gate-commits-7609df7--5d7ac8b).

---

## Table of Contents

1. [What this repo is](#what-this-repo-is)
2. [Architecture](#architecture)
   - [What the feedback-loop commit changed](#what-the-feedback-loop-commit-changed)
   - [What the admission-gate commit changed](#what-the-admission-gate-commit-changed)
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
`fan out extractions`, `Rocchio Relevance`, `makeFeedbackLoop`, `Admission Gate Logic`)
and the branch
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
                    START
                      │
                      ├────────────────────────────────────────────┐
                      ▼                                            ▼
   ┌───────────────────────────────────────┐    ┌───────────────────────────────────────┐
   │ topicExtractor                        │    │ embedTopic  (topicEmbed)              │
   │ expands the topic into subtopics      │    │ q₀ = embed(topicText) using           │
   │ (LLM) → writes `topics`,              │    │ text-embedding-3-small                │
   │ returns topicIds                      │    │                                       │
   └──────────────────┬────────────────────┘    └──────────────────┬────────────────────┘
                      ▼                                            │
   ┌───────────────────────────────────────┐                       │
   │ admitTopics  (admissionGate)          │                       │
   │ round 1: pass-through.  reextract:    │                       │
   │ cos(topicCentroid, embed(topic_text)) │                       │
   │ → keep top 5, mark the rest rejected  │                       │
   │ Command(goto=[Send(sourceDiscovery)]) │                       │
   └──────────────────┬────────────────────┘                       │
    one Send() per admitted topic id                               │
                      ▼                                            │
   ┌───────────────────────────────────────┐                       │
   │ sourceDiscovery (map-reduce subgraph) │                       │
   │   sourceExtractor → `sources`         │                       │
   │    fan_out_runs: one Send()/source    │                       │
   │   runExtractor    → `extraction_runs` │                       │
   │   embedUnits      → `extracted_units` │                       │
   │    (+ surfaces sourceIds to state)    │                       │
   └──────────────────┬────────────────────┘                       │
                      ▼                                            │
   ┌───────────────────────────────────────┐                       │
   │ feedbackInterrupt                     │                       │
   │ (nodes/interruptSelections.py)        │                       │
   │ interrupt() PAUSES the run; the human │                       │
   │ answers {action, selected_ids} → sets │                       │
   │ userAction / selected / non-selected  │                       │
   └──────────────────┬────────────────────┘                       │
                      │                                            │
                      └─────────────────┬──────────────────────────┘
                                        ▼   join: centroidEmbedding waits for BOTH branches
                     ┌──────────────────┴────────────────────┐
                     │ centroidEmbedding                     │
                     │ Rocchio:  α·q₀ + β·mean(relevant)     │
                     │                − γ·mean(non-relevant) │
                     │ then L2-normalised → topicCentroid    │
                     └──────────────────┬────────────────────┘
                                        ▼
                     ┌──────────────────┴────────────────────┐
                     │ routeAfterCentroid                    │
                     │ returns Command(goto=…)               │
                     └────────┬──────────────────────────┬───┘
               userAction ==  │                          │  anything else
                 "reextract"  ▼                          ▼
           ┌───────────────────────────────────────┐
           │ reconcileSources                      │    END
           │ getSourcesbyId(selected sources) →    │
           │ join their `discovery_reason` prose   │
           │ → the next round's topicText          │
           └──────────────────┬────────────────────┘
                              │
                              └──►  back to topicExtractor   (the graph's only back-edge)
```

### What the feedback-loop commit changed

`7609df7` (`makeFeedbackLoop`) is the first of the two commits that reshaped the graph.
Before it, `centroidEmbedding` was wired straight to `END`; the run computed one refined
centroid and stopped. It now ends in a **cycle**:

| | Before `7609df7` | After `7609df7` |
| --- | --- | --- |
| Terminal edge | `centroidEmbedding → END` | `centroidEmbedding → routeAfterCentroid`, which returns `Command(goto=…)` |
| Nodes | 5 top-level | **+2**: `routeAfterCentroid`, `reconcileSources` |
| Loop edge | — | **`reconcileSources → topicExtractor`** (the only back-edge in the graph) |
| Resume payload | a comma-separated string or a list of ids | **a JSON object** `{"action": …, "selected_ids": [...]}` |
| `GlobalState` | — | **+`userAction: str`** — the branch key the router reads |
| `topicEmbed` | always embeds `topicText` | returns early (no re-embed) when `userAction == "reextract"`, so the refined centroid survives as the next round's `q₀` |
| Repository | — | **+`getSourcesbyId(source_ids)`** — selects `discovery_reason` for the chosen sources |

The intent: let a human say *"these sources were the right ones — now go again"*, and have
the next round start from the selected sources' own `discovery_reason` text plus the
Rocchio-refined centroid. What actually happens today is narrower — see
[Known Issues](#the-feedback-loop-and-admission-gate-commits-7609df7--5d7ac8b).

### What the admission-gate commit changed

`5d7ac8b` (`Admission Gate Logic`) is the current head of
`reimplement/extraction-langraph`. It adds one node and moves the fan-out into it:

| | Before `5d7ac8b` | After `5d7ac8b` |
| --- | --- | --- |
| Fan-out | `add_conditional_edges("topicExtractor", fan_out_sources, ["sourceDiscovery"])` | `add_edge("topicExtractor", "admitTopics")`; the gate returns `Command(goto=[Send("sourceDiscovery", …)])` |
| `fan_out_sources` | the fan-out | **dead code** — still defined in `graph.py`, referenced by nothing |
| Topic filtering | none — every subtopic got a full source-discovery pass | on `reextract`, subtopics are **ranked by `cos(topicCentroid, embed(topic_text))` and cut to the top 5**; the rest are `UPDATE topics SET status='rejected'` |
| `topicCentroid` | written by `centroidEmbedding`, never read again | **read by the gate** to score the next round's subtopics |
| Round reset | `"topicIds": []` (a no-op under the `operator.add` reducer) | **`Overwrite([])`** for both `topicIds` and `sourceIds` — the reset now actually resets |
| Repository | — | **+`getTopicsMetadata(ids)`** (id → `topic_text`) and **+`rejectTopics(ids)`** |

The gate is deliberately inert on the first pass — `if state.get("userAction") !=
"reextract": return fanOut(state["topicIds"])` — because there is no feedback-refined
centroid to gate against yet.

The same commit carries fixes outside the graph: `extractionService` had
`from datetime import time` shadowing the `time` module (now `import time`), skips
non-HTML/PDF responses by content-type, and runs `build_extraction_input` in a thread;
`embeddingServices` retries embedding batches with exponential backoff on rate-limit,
connection, timeout and 5xx errors instead of failing the run; `runExtractor` returns no
update when a fetch yields nothing; and the topic-extraction prompt now caps its output
at 5 subtopics.

### Stage-by-stage (node → service → table)

| Stage | Node | Service | Model / tool | Writes |
| --- | --- | --- | --- | --- |
| Topic expansion | `nodes/topicExtractor.py` | `services/topicExtractionService.py` | `gpt-4.1-mini` (JSON output) | `topics` |
| Topic embedding | `nodes/topicEmbed.py` | *(inline OpenAI call)* | `text-embedding-3-small` | *(returns `topicCentroid` to state)* |
| Topic admission | `nodes/admissionGate.py` | `db.getTopicsMetadata` / `db.rejectTopics` | `text-embedding-3-small` + cosine (numpy) | `topics.status = 'rejected'` for the losers; fans out over the winners |
| Source discovery | `nodes/sourceExtractor.py` | `services/sourceDiscoveryService.py` | `ChatOpenAI` + `web_search_preview` tool | `sources` |
| Content extraction | `nodes/runExtractor.py` | `services/extractionService.py` | curl_cffi → SeleniumBase fallback, `trafilatura`, `gpt-4.1-mini` structured output | `extraction_runs` |
| Unit embedding | `nodes/embedUnits.py` | `services/embeddingServices.py` | `text-embedding-3-small` | `extracted_units` (+ surfaces `sourceIds` to state) |
| Human feedback | `nodes/interruptSelections.py` | *(LangGraph `interrupt`)* | — (human-in-the-loop) | *(returns `selectedSourceIds` / `nonselectedSourceIds`)* |
| Centroid refinement | `nodes/centroidEmbedding.py` | `services/transformationService.py` | Rocchio + `getEmbeddedUnits` (pgvector) | *(updates `topicCentroid`)* |
| Routing | `nodes/routeAfterCentroid.py` | *(none — pure `Command` router)* | — | *(`goto` `reconcileSources` or `END`; clears per-round state)* |
| Re-extraction seed | `nodes/reconcileSources.py` | `db.getSourcesbyId` | — | *(returns a new `topicText` joined from `discovery_reason`)* |

### Key concepts

- **Fan-out / map-reduce.** `admissionGate` (top graph) and `fan_out_runs`
  (subgraph) use LangGraph `Send` to run one branch per topic / per source in
  parallel. Results are reduced back through `Annotated[list, operator.add]`
  reducers on the state (e.g. `topicIds`, `extraction_run_ids`). Note that the top
  graph's fan-out moved in `5d7ac8b`: it used to be the `fan_out_sources` function on
  a conditional edge, and it is now the `goto=[Send(...)]` of the gate's returned
  `Command`. `fan_out_sources` is still defined in `graph.py` but nothing calls it.
- **Admission gate (`nodes/admissionGate.py`).** Sits between topic expansion and
  source discovery and decides *which subtopics are worth spending a discovery pass on*.
  On the first pass it is a pass-through. On a `reextract` round it loads the new
  subtopics' `topic_text` (`getTopicsMetadata`), embeds them with
  `text-embedding-3-small`, scores each against the Rocchio-refined `topicCentroid`
  with a hand-rolled cosine (`computeSimilarities`, with a `1e-12` zero-norm guard),
  keeps the **top 5**, and writes `status='rejected'` on the rest before fanning out.
  This is the point where relevance feedback finally *does* something: before
  `5d7ac8b`, `topicCentroid` was written and never read.
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
  `interrupt()` to **pause the run** and hand the discovered `sourceIds` back to the
  caller. Since `7609df7` the resume value is **an object, not a bare list**:

  ```json
  { "action": "reextract", "selected_ids": ["src-id-1", "src-id-3"] }
  ```

  A JSON *string* is accepted too (it is `json.loads`-ed first). The node reads
  `response['action']` into `userAction`, `response['selected_ids']` into
  `selectedSourceIds`, and puts everything else in `nonselectedSourceIds`. Both keys
  are read unguarded, so a resume value missing either one raises `KeyError` inside
  the node. Because it interrupts, the graph must be run with a **checkpointer** and
  resumed with a `Command(resume=...)` (see *Running*).
- **The re-extraction loop (`userAction`).** `routeAfterCentroid`
  (`nodes/routeAfterCentroid.py`) is a pure router: it returns
  `Command(goto="reconcileSources")` when `userAction == "reextract"` and
  `Command(goto=END)` otherwise. On the re-extract branch it also clears the
  round's state (`topicText`, `topicState`, `topicIds`, and both selection lists) in
  the same `Command(update=...)`. `reconcileSources` then calls
  `getSourcesbyId(selectedSourceIds or sourceIds)`, joins those rows'
  `discovery_reason` strings with blank lines, and returns that as the **new
  `topicText`** — which the back-edge feeds straight into `topicExtractor` for another
  round. `topicEmbed` short-circuits on `reextract` specifically so the round-2 topic
  is *not* re-embedded from scratch; the Rocchio-refined centroid is meant to carry
  over as the next `q₀`.
  (`5d7ac8b` made the round reset real by switching it to `Overwrite([])`; one thing
  about this loop still does not behave as written — see
  [Known Issue #17](#the-feedback-loop-and-admission-gate-commits-7609df7--5d7ac8b).)
- **Rocchio relevance feedback (now wired in).** `centroidEmbedding`
  (`nodes/centroidEmbedding.py`) feeds the topic centroid and the human's
  selected / non-selected sources to `TransformationService.compute_query_vector`,
  which fetches each set's unit embeddings (`getEmbeddedUnits`) and applies the
  classic Rocchio query-refinement formula
  (`α·q0 + β·mean(relevant) − γ·mean(non-relevant)`, then L2-normalised) to
  **re-centre `topicCentroid`**. `embedTopic` and `feedbackInterrupt` are both
  upstream of this node via a single `add_edge([...], "centroidEmbedding")` **join**,
  so it runs once the initial centroid *and* the feedback are available — and only
  once (see Known Issue #17). As of that commit this replaces the earlier "dead code" status:
  `transformationService.py` is now a real `TransformationService` class (repo-backed,
  with a `@staticmethod rocchio_embedding` and a divide-by-zero guard).

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
│   │   │   ├── graph.py            # Top-level StateGraph — now cyclic (…centroidEmbedding → routeAfterCentroid → reconcileSources ↺ topicExtractor)
│   │   │   │                        # NB: `fan_out_sources` here is dead since 5d7ac8b — admissionGate owns the fan-out
│   │   │   ├── state.py            # TypedDict states: GlobalState / TopicState / sourceDiscoveryState (+ userAction / sourceIds / selected / non-selected)
│   │   │   ├── nodes/              # Thin graph nodes (delegate to services)
│   │   │   │   ├── topicExtractor.py
│   │   │   │   ├── admissionGate.py       # cosine gate + Send fan-out            (added 5d7ac8b)
│   │   │   │   ├── topicEmbed.py          # returns early when userAction == "reextract"
│   │   │   │   ├── sourceExtractor.py
│   │   │   │   ├── runExtractor.py
│   │   │   │   ├── embedUnits.py
│   │   │   │   ├── centroidEmbedding.py   # Rocchio centroid refinement (now wired in)
│   │   │   │   ├── routeAfterCentroid.py  # Command router: reconcileSources vs END  (added 7609df7)
│   │   │   │   ├── reconcileSources.py    # rebuilds topicText from discovery_reason (added 7609df7)
│   │   │   │   └── interruptSelections.py # human-in-the-loop gate: {action, selected_ids}
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
│   │                               # + getSourcesbyId() — discovery_reason for the loop (added 7609df7)
│   │                               # + getTopicsMetadata() / rejectTopics() — the gate  (added 5d7ac8b)
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
│   ├── unit/test_embed_service.py  # embed_pending: text↔vector pairing, unit_index, strict zip
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
| `topics` | `id`, `topic_text`, `status`, `created_by`, `confidence`, `metadata` (jsonb) | One row per (sub)topic produced by `topicExtractor`. Since `5d7ac8b`, `status` is also written by the graph: subtopics the admission gate does not admit are set to `'rejected'`. |
| `sources` | `id`, `topic_id` (FK), `source_type`, `source_url`, `discovery_reason`, `priority_score`, `status` | Web sources discovered per topic. Since `7609df7`, `discovery_reason` is load-bearing rather than informational: `getSourcesbyId` reads it back and `reconcileSources` concatenates it into the next round's `topicText`. |
| `extraction_runs` | `id`, `source_id` (FK), `status`, `confidence`, `metadata` (jsonb) | One run per source fetch/extraction. Atomic units are currently stored **inside `metadata`** as JSON. |
| `extracted_units` | `id`, `extraction_run_id` (FK), `unit_index`, `semantic_type`, `content`, `confidence`, `embedding vector(1536)` | Individual atomic units + their embeddings. `content` is the unit's `text` — the exact string that was embedded — and `unit_index` is its ordinal in `extraction_runs.metadata`; together with `extraction_run_id` that ordinal is the upsert key. The Rocchio step reads embeddings back via `getEmbeddedUnits`, joining `extracted_units → extraction_runs` on `source_id`. |

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

The run will expand the topic into subtopics, pass them through the admission gate
(a no-op on the first round), discover sources for each, extract and decompose their
content, and embed the resulting units — writing to the `topics`, `sources`,
`extraction_runs`, and `extracted_units` tables as it goes.

#### Human-in-the-loop: the source-selection interrupt

Since the Rocchio commit, the graph **pauses** after source discovery: the
`feedbackInterrupt` node calls LangGraph's `interrupt()` and returns the discovered
`sourceIds` to you. You then resume with the ids you consider *relevant* **and what you
want to happen next**, and the `centroidEmbedding` node uses that feedback to re-centre
the topic centroid.

Because the graph interrupts, it must run with a **checkpointer** and a thread id. In
LangGraph Studio, the run will surface the `{"type": "topic_selection", "source_ids": [...]}`
payload and let you resume. Programmatically it looks like:

```python
from langgraph.types import Command

config = {"configurable": {"thread_id": "my-run"}}

# 1) First invocation pauses at the interrupt.
result = await graph.ainvoke({"topicText": "quantum error correction"}, config)
payload = result["__interrupt__"][0].value          # {"type": "topic_selection", "source_ids": [...]}

# 2) Resume with an object carrying BOTH keys. `action` drives routeAfterCentroid;
#    anything other than "reextract" ends the run.
final = await graph.ainvoke(
    Command(resume={"action": "end", "selected_ids": ["src-id-1", "src-id-3"]}),
    config,
)
# final["topicCentroid"] is now the Rocchio-refined centroid.
```

> ⚠️ **The resume contract changed in `7609df7`.** It used to accept
> `"src-id-1, src-id-3"` (a comma-separated string) or a plain list. Both now fail:
> a string is parsed with `json.loads`, and the node indexes `response['action']` and
> `response['selected_ids']`. Passing the old shape raises `JSONDecodeError` /
> `TypeError` inside `feedbackInterrupt`.

#### Asking for another round (`action: "reextract"`)

Resume with `"action": "reextract"` and the graph does not stop at `END`. Instead
`routeAfterCentroid` sends it to `reconcileSources`, which rebuilds `topicText` from the
`discovery_reason` of the sources you selected and loops back into `topicExtractor`:

```python
final = await graph.ainvoke(
    Command(resume={"action": "reextract", "selected_ids": ["src-id-1"]}),
    config,
)
# The run does NOT finish here: it expands the rebuilt topic, passes the new
# subtopics through the admission gate, discovers sources for the admitted ones,
# and pauses at a second `topic_selection` interrupt.
assert "__interrupt__" in final
```

This is the round where the refined centroid earns its keep: `admitTopics` scores each
new subtopic against it and drops all but the top 5, marking the others `rejected` in
`topics`. Watch the `gate scores: [...]` line it logs to see the ranking.

> **One cycle only.** The second interrupt is effectively the end of the run: whatever
> you answer, the graph halts after `feedbackInterrupt` and never reaches
> `centroidEmbedding` again. This is Known Issue #17 — the `[embedTopic,
> feedbackInterrupt] → centroidEmbedding` join never re-arms, because `embedTopic` is
> only reachable from `START`.

> Note: `graph.compile()` in `graph.py` does **not** attach a checkpointer, so the
> interrupt only survives when the graph is served by a runtime that supplies one
> (the LangGraph dev server / API does). A bare `graph.ainvoke(...)` with no
> checkpointer cannot pause and resume.

### The legacy scraper

See [Legacy: the YouTube scraper](#legacy-the-youtube-scraper).

---

## Testing

Tests use `pytest` (config in `pyproject.toml`, `asyncio_mode = "auto"`,
`pythonpath = ["."]`).

```bash
# The seleniumbase pytest plugin (a legacy-scraper dep) crashes on collection
# with setuptools ≥82 because pkg_resources was removed. Disable it + pytest-html
# to run the pipeline suite:
uv run pytest -p no:seleniumbase -p no:sb_pytest -p no:html tests/ -v
```

**Current result at `5d7ac8b`: 19 passed, 10 failed** (excluding the legacy scraper's
`tests/execdata.py` and `tests/integration/test_topicExtractor.py`, which need live
services). Five of those failures pre-date the feedback-loop commit (Known Issue #13);
the other five are that commit's own regression (#18) — the tests below still describe
the pre-`7609df7` interrupt contract. `5d7ac8b` neither fixed nor broke any test, and
added none: `admissionGate` — the only node with real logic of its own (cosine scoring,
a top-K cut, a DB write on the rejected set) — has **no test coverage at all**.

### Existing suites

| Suite | State |
| --- | --- |
| `tests/node/test_embed_units.py` | **⚠️ Broken by the Rocchio commit.** The node now returns the whole mutated `state` (not `{"embedded_count": ...}`) and reads `state["source_ids"]`, so every assertion here fails and the empty-input case raises `KeyError`. These tests still describe the *old* contract and need rewriting (or the node needs revisiting — see Known Issues). |
| `tests/unit/test_embed_service.py` | ✅ **Passing.** Rewritten against the real `extraction_runs.metadata` row shape (`{kind, text, topic_id, source_id}`). Asserts each vector is stored with its own `content`, that the pairing survives an out-of-order `resp.data`, that `unit_index` keeps counting across batches, and that a short response raises instead of misaligning. |
| `tests/integration/test_topicExtractor.py` | **Broken.** Passes `llm=None` to a constructor that doesn't accept it and asserts `result is List[str]`. Also hits a live local Supabase. |
| `tests/execdata.py` | Legacy scraper smoke test; launches a real browser. |

### Tests added for the Rocchio / feedback work

These cover the code the latest commit introduced (all mock-only — no live
Supabase or OpenAI — and all pass under the command above):

| Suite | Covers |
| --- | --- |
| `tests/unit/test_transformation_service.py` | `rocchio_embedding` math (α/β/γ terms, normalisation, zero-vector guard, list output) and `compute_query_vector` (fetches both selections, skips the repo on empty id lists). |
| `tests/unit/test_get_embedded_units.py` | `SupabaseRepository.getEmbeddedUnits` — the `extracted_units ⋈ extraction_runs` filter and JSON→list embedding decode, against a fake client chain. |
| `tests/node/test_topic_embed.py` | `topicEmbed` now uses `text-embedding-3-small` and returns `topicCentroid` (the two bugs the commit fixed). |
| `tests/node/test_interrupt_selections.py` | **⚠️ Broken by `7609df7` (4/4 failing).** Written against the old contract: the node is now `async` and expects `{"action", "selected_ids"}`, so calling it synchronously with `"a, c"` / `["b"]` yields `TypeError: 'coroutine' object is not subscriptable`. Needs `await` + the new payload, plus a case for `userAction`. |
| `tests/node/test_centroid_embedding.py` | `centroidEmbedding` wires the repo + `TransformationService` and writes the refined centroid back to state. |
| `tests/integration/test_feedback_loop.py` | **⚠️ Broken by `7609df7` (1/1 failing).** Same cause: it resumes with `Command(resume="s1, s3")`, which now hits `json.loads` and raises `JSONDecodeError`. The graph shape it builds (`feedbackInterrupt → centroidEmbedding → END`) also predates `routeAfterCentroid` / `reconcileSources`. |
| `tests/conftest.py` | Sets a dummy `OPENAI_API_KEY` so modules that build an `AsyncOpenAI()` at import time (e.g. `topicEmbed`) can be collected. |

### Still needed

- **Repair the two suites `7609df7` broke** (Known Issue #18): `await` the now-async
  `interruptSelections`, resume with `{"action", "selected_ids"}`, and assert the
  `userAction` it writes.
- **Cover the loop and the gate.** Nothing exercises `routeAfterCentroid`,
  `reconcileSources`, or `admissionGate`. Worth adding: `computeSimilarities` against
  hand-computed cosines (including the zero-norm guard); that the gate is a
  pass-through when `userAction != "reextract"`; that it rejects exactly the
  non-admitted ids; the router's two branches; that `reconcileSources` falls back to
  `sourceIds` when `selectedSourceIds` is empty; and a full-topology cycle test
  asserting how many rounds actually run (Known Issues #15–#17 and #19 were all found
  that way — a stubbed copy of `graph.py`'s wiring under a `MemorySaver`).
- **Rewrite `tests/node/test_embed_units.py`** to the node's current contract once
  its return shape is settled (see Known Issue #13).
- **A live integration test for `getEmbeddedUnits`** against a seeded local Supabase
  (the join on `extraction_runs.source_id` and the JSON-string `embedding` column are
  only exercised with a fake client today).
- **A full-graph resume test** (`graph.py`) once the upstream nodes it depends on
  (`sourceDiscoveryService` model id, `embedUnits` return shape) are fixed — currently
  a real end-to-end run can't reach the interrupt.
- **A live integration test for the write path** — `test_embed_service.py` now
  matches the real metadata and update shapes, but the upsert on
  `(extraction_run_id, unit_index)` is only exercised against a mock; its idempotence
  needs a seeded local Supabase to prove.

> The `Makefile` `test` target points at `tests/test_execdata.py`, which does not
> exist (the file is `tests/execdata.py`).

---

## Known Issues / Review Findings

These were found while parsing the code and are documented here so they're visible.
The **Rocchio commit** (`feat: implement Rocchio relevance feedback for topic
embeddings`) fixed several of the items below (marked ✅) and introduced one new
regression (#13). The **feedback-loop commit** (`7609df7`) added four more (#15–#18),
two of which the **admission-gate commit** (`5d7ac8b`) has since fixed. The remaining
items are still open at `5d7ac8b`.

### Correctness bugs (pipeline)

1. ✅ **Fixed — `nodes/topicEmbed.py` wrong model + dropped result.**
   Previously it called `client.embeddings.create(model=MODEL, ...)` with the **chat**
   model `MODEL` (`"gpt-4.1-mini"`) and returned `{"topicEmbedding": ...}`, a key
   `GlobalState` doesn't define. The Rocchio commit hard-codes
   `model='text-embedding-3-small'` and returns `{"topicCentroid": ...}`. (The now-unused
   `from ...extractionService import MODEL` import is still present but harmless.)

2. **`services/sourceDiscoveryService.py` — invalid model + prompt typos.**
   `ChatOpenAI(model="gpt-5.4")` is not a real model id and will fail at call time.
   The prompt string has a **stray `s`** on its own line, and there is a no-op
   statement `metadata["topic_text"]` (line ~35) that does nothing.

3. ✅ **Fixed — embeddings were orphaned from their text.**
   `runExtractor`/`extractionService` store atomic units **inside**
   `extraction_runs.metadata` (JSON). `embeddingService.embed_pending` read that
   JSON, embedded each unit's `text`, and called `updateUnitEmbeddings` — which
   **inserted** brand-new `extracted_units` rows containing only
   `{extraction_run_id, embedding}`. The unit `content` was never written, so every
   row in the live table has `content = null` and no stored vector could be read
   back.

   `extracted_units.content` is **the unit's `text`** — the exact string sent to the
   embedding model. `embed_pending` now writes it alongside `semantic_type` (the
   metadata entry's `"kind"`) and `unit_index` (its ordinal in the run's `metadata`
   array), pairs each vector to its row via the response's documented `index` field,
   and uses `zip(..., strict=True)` so a short response raises instead of silently
   shifting every later text onto the wrong vector. `updateUnitEmbeddings` upserts on
   `(extraction_run_id, unit_index)` — added by
   `supabase/migrations/20260831101500_unit_content_alignment.sql` — so re-embedding a
   run overwrites its rows rather than appending a second copy.
   `SupabaseRepository.getUnitsByRun` reads text and vector back together.

   **Existing rows cannot be backfilled:** their ordinal position is unrecoverable
   (the whole batch shares one `created_at`). Run
   `delete from extracted_units where content is null;` and re-run the embed node.

4. **`db/supabaseRepository.py` — `getSources` filters the wrong column.**
   It does `.eq('id', topic_id)` where it should be `.eq('topic_id', topic_id)`.
   (This method is currently unused, but the query is wrong.)

5. ✅ **Fixed — `centroidEmbedding.py` / `interruptSelections.py` were stubs.**
   `centroidEmbedding.py` used to be the bare token `import ` (a `SyntaxError`) and
   `interruptSelections.py` was empty. The Rocchio commit implements both: the former
   calls `TransformationService.compute_query_vector`, the latter is the human-in-the-loop
   `interrupt()` node. Both are now wired into `graph.py`.

6. ✅ **Fixed — `transformationService.py` `rocchio_embedding` signature + wiring.**
   It's now a proper `@staticmethod` on the renamed `TransformationService` class (with
   a divide-by-zero guard and `.tolist()` output), and it *is* wired into the graph via
   `centroidEmbedding`. Note the **class was renamed** `transformationService` →
   `TransformationService`; any external importer using the old name must update.

### Regression introduced by the Rocchio commit

13. **`nodes/embedUnits.py` — changed contract breaks its tests + can `KeyError`.**
    To surface source ids for the new interrupt, `embedUnits` now does
    `state['sourceIds'] = [X['id'] for X in state['source_ids']]` and `return state`
    (the whole mutated dict) instead of the previous `return {"embedded_count": total}`.
    Two problems:
    - It reads `state["source_ids"]`, which isn't set on the fan-in path — the node's
      own tests call it with only `extraction_run_ids`, so it raises `KeyError:
      'source_ids'`. **All of `tests/node/test_embed_units.py` now fails.**
    - Returning the full mutated `state` (rather than a partial update) is a LangGraph
      anti-pattern and also drops the `embedded_count` the old tests asserted.
    Decide the intended contract (likely: return a partial `{"sourceIds": [...]}` and
    read source ids from wherever they're actually populated), then rewrite the node's
    tests to match.

### The feedback-loop and admission-gate commits (`7609df7` / `5d7ac8b`)

Items #15–#17 and #19 were confirmed by replaying `graph.py`'s exact wiring (same nodes,
same edges, stub bodies) under a `MemorySaver` and streaming the node updates, once per
commit.

15. ✅ **Fixed in `5d7ac8b` — `routeAfterCentroid`'s reset of `topicIds` was a no-op, so
    old topics were re-processed every round.** The router used to clear the round with

    ```python
    update={"topicText": "", "topicState": None, "topicIds": [], ...}
    ```

    but `GlobalState.topicIds` is `Annotated[List[str], operator.add]`, and a reducer
    channel *merges* an update instead of replacing it — `[]` reduced to `existing + []`,
    so the list survived. Round 2 fanned out over round 1's topic ids **and** the new
    ones (observed `topicIds == ['t1', 't2']` after the reset, with `sourceDiscovery`
    re-running for `t1`), re-extracting at full LLM/fetch cost. `5d7ac8b` wraps both
    accumulating keys in LangGraph's `Overwrite` sentinel:

    ```python
    update={"topicText": "", "topicState": None,
            "topicIds": Overwrite([]), "sourceIds": Overwrite([])}
    ```

    Re-running the probe against the current wiring shows round 2 starting clean:
    `topicIds == ['r2-t1' … 'r2-t5']`, no round-1 ids.

16. ✅ **Fixed in `5d7ac8b` — `sourceIds` was never reset and accumulated duplicates.**
    It is also `Annotated[..., operator.add]` and was *not* in the router's update at
    all, so ids piled up across rounds — and because of #15 the same source was
    re-discovered and appended again (observed round-2 interrupt payload:
    `{'source_ids': ['s-t1', 's-t1', 's-t2']}`). That fed duplicates to the human, and
    `nonselectedSourceIds` — built as `[s for s in sourceIds if s not in selected]` —
    inherited them, so Rocchio's `mean(non-relevant)` double-counted those units.
    `Overwrite([])` on `sourceIds` fixes it; round 2 now surfaces only its own sources.

17. **The loop can only run once — the second round's feedback is silently
    discarded.** `graph.py` joins two branches into one node:

    ```python
    builder.add_edge(["embedTopic", "feedbackInterrupt"], "centroidEmbedding")
    ```

    (unchanged in `5d7ac8b`). A multi-source `add_edge` compiles to a barrier that
    fires only when **every** named node has written. `embedTopic` is reachable only from `START`, so it writes
    exactly once. On the second cycle `feedbackInterrupt` writes, the barrier stays
    half-filled, and `centroidEmbedding` — and therefore `routeAfterCentroid` — never
    runs again. The run just stops after the second interrupt: answering
    `{"action": "reextract"}` a second time changes nothing, and no second Rocchio
    refinement happens — and since `5d7ac8b`, the admission gate is starved with it:
    round 3's subtopics would be the first the gate could rank against a
    twice-refined centroid. Observed on both commits: after resuming the round-2
    interrupt, the only node update is `feedbackInterrupt` and `state.next == ()`.
    *Fix:* route the initial-centroid branch into the cycle (e.g. `embedTopic →
    topicExtractor` before the fan-out) or drop the join and have `centroidEmbedding`
    read `topicCentroid` from state, which is where it already lives.

    Related: `topicEmbed`'s `if state.get('userAction') == 'reextract': return state`
    guard is currently unreachable for the same reason — `embedTopic` never runs a
    second time. It is the right guard for the fixed wiring, not for today's.

18. **The resume-payload change broke 5 tests.** Making `interruptSelections` async
    and switching its input from *ids* to `{"action", "selected_ids"}` invalidated
    `tests/node/test_interrupt_selections.py` (4 tests) and
    `tests/integration/test_feedback_loop.py` (1). See *Testing*. The payload is also
    read unguarded — a resume value missing either key raises `KeyError` from inside
    the node, which surfaces as a graph-execution error rather than a re-prompt.

19. **The gate's top-5 cut and the extractor's 5-topic cap cancel out.** The same
    commit that added `admitted = [id for id, _ in ranked[:5]]` also changed the
    topic-extraction prompt to `CAP IT TO A MAXIMUM OF 5`. When the LLM honours that
    cap the gate ranks 5 candidates and admits all 5, so it rejects nothing and the
    cosine scoring is pure overhead — the behaviour is only observable when the model
    overshoots. Whichever number is meant to be the real filter, the two should not be
    equal (and the cut is a hard-coded literal, not a threshold on the scores the gate
    just computed — a `τ` on similarity with a min-K floor would make it do the job its
    own docstring implies).

20. **The gate's repository calls are unguarded.** `getTopicsMetadata` raises
    `ValueError` if *any* requested id is missing rather than skipping it, and its
    return annotation says `List[dict]` while it returns a `dict`. `rejectTopics`
    ignores the response entirely, so a failed update is silent, and it is called with
    `set(topicIds) - set(admitted)` — an empty set on the common path, which still
    issues an `UPDATE … WHERE id IN ()`.

Not a regression, but worth recording next to them:

- **`reconcileSources` re-seeds the loop with prose, not vectors.** It rebuilds
  `topicText` by joining the selected sources' `discovery_reason` strings — the LLM's
  own justification for picking each source, not the extracted content. The refined
  `topicCentroid` now has exactly one consumer (the admission gate, which scores
  *topics*); nothing retrieves against the embedded units, and `extracted_units.embedding`
  still has no index. `ROADMAP.md` at this commit is a spec for a separate `Graph.md`
  document rather than the tiered plan it held at `6904353`, and it predates `5d7ac8b`
  — it still describes the admission gate as unbuilt.
- **`getSourcesbyId` raises on an empty result.** `reconcileSources` passes
  `selectedSourceIds or sourceIds`; if the human selects nothing *and* the fallback is
  empty, the repository raises `ValueError("Data could not be fetched")` mid-graph.
- **Debug `print()`s in graph nodes.** `routeAfterCentroid` prints `userAction:` and
  `interruptSelections` prints the raw resume value on every run. Should be the
  project's logger, or removed.

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

14. **`pytest` collection crashes out of the box.** `seleniumbase` (a legacy-scraper
    dep) ships a pytest plugin whose `pytest_configure` reads pytest-html's `htmlpath`
    option, and pytest-html imports `pkg_resources` — which `setuptools>=82` (pinned via
    `setuptools>=82.0.1`) removed. So a plain `uv run pytest tests/` dies during plugin
    load. Work around it with `-p no:seleniumbase -p no:sb_pytest -p no:html`, or drop
    seleniumbase from the pipeline's test environment.

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
