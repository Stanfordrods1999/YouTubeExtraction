"""Does Rocchio relevance feedback actually improve retrieval? Measure it.

For each topic in the golden set, retrieval runs in three configurations:

    question-only   the query embedding alone (baseline)
    blend-initial   query blended with the pre-feedback topic centroid
    blend-refined   query blended with the Rocchio-refined centroid

A retrieved unit counts as relevant iff its source_url is in the query's
labeled-relevant set — the same source-level signal the human gives at the
pipeline's selection interrupt, so no per-unit labeling is needed.

Usage (requires a populated local Supabase + OPENAI_API_KEY):

    uv run python -m evals.run_eval --golden evals/golden.json --k 10

Golden-set format: see evals/golden.example.json.
"""
import argparse
import asyncio
import json
from typing import Dict, List, Optional, Sequence

from openai import AsyncOpenAI

from db.session import init_repo
from evals.metrics import mrr, ndcg_at_k, precision_at_k
from src.app.config import settings
from src.app.services.queryService import QueryService

CONFIGS = ("question-only", "blend-initial", "blend-refined")


def judge(retrieved: Sequence[dict], relevant_urls: set) -> List[bool]:
    """Source-level relevance: a unit is relevant iff its source is labeled."""
    return [unit.get("source_url") in relevant_urls for unit in retrieved]


def score(relevances: Sequence[bool], k: int) -> Dict[str, float]:
    return {
        f"P@{k}": precision_at_k(relevances, k),
        "MRR": mrr(relevances),
        f"nDCG@{k}": ndcg_at_k(relevances, k),
    }


def mean_scores(rows: List[Dict[str, float]]) -> Optional[Dict[str, float]]:
    if not rows:
        return None
    return {
        metric: sum(r[metric] for r in rows) / len(rows)
        for metric in rows[0]
    }


def format_markdown_table(results: Dict[str, List[Dict[str, float]]], k: int) -> str:
    """One row per retrieval configuration, metrics averaged over queries."""
    metrics = [f"P@{k}", "MRR", f"nDCG@{k}"]
    lines = [
        "| configuration | " + " | ".join(metrics) + " | queries |",
        "|" + " --- |" * (len(metrics) + 2),
    ]
    for config in CONFIGS:
        avg = mean_scores(results.get(config, []))
        if avg is None:
            lines.append(f"| {config} | " + " | ".join("—" for _ in metrics) + " | 0 |")
            continue
        cells = " | ".join(f"{avg[m]:.3f}" for m in metrics)
        lines.append(f"| {config} | {cells} | {len(results[config])} |")
    return "\n".join(lines)


async def evaluate_topic(repo, client: AsyncOpenAI, topic: dict,
                         k: int, weight: float) -> Dict[str, List[Dict[str, float]]]:
    initial = await repo.getLatestCentroid(topic["thread_id"], kind="initial")
    refined = await repo.getLatestCentroid(topic["thread_id"], kind="refined")

    results: Dict[str, List[Dict[str, float]]] = {c: [] for c in CONFIGS}
    for query in topic["queries"]:
        resp = await client.embeddings.create(
            model=settings.embed_model, input=query["question"]
        )
        embedding = resp.data[0].embedding
        relevant = set(query["relevant_source_urls"])

        vectors = {
            "question-only": embedding,
            "blend-initial": QueryService.blend(embedding, initial, weight) if initial else None,
            "blend-refined": QueryService.blend(embedding, refined, weight) if refined else None,
        }
        for config, vector in vectors.items():
            if vector is None:
                continue
            hits = await repo.matchUnits(vector, k=k)
            results[config].append(score(judge(hits, relevant), k))

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", default="evals/golden.json",
                        help="Path to the golden-set JSON")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--weight", type=float, default=0.3,
                        help="Centroid blend weight for the blend-* configs")
    args = parser.parse_args()

    with open(args.golden) as f:
        golden = json.load(f)

    repo = await init_repo()
    client = AsyncOpenAI()

    for topic in golden:
        results = await evaluate_topic(repo, client, topic, args.k, args.weight)
        print(f"\n### {topic['name']}  (thread `{topic['thread_id']}`, "
              f"k={args.k}, blend weight={args.weight})\n")
        print(format_markdown_table(results, args.k))
    print()


if __name__ == "__main__":
    asyncio.run(main())
