# Roadmap — closing the centroid loop

Companion to [README.md](README.md#known-issues--review-findings). Where the README
records what is *broken*, this file records what to *build next*, ordered so that each
tier makes the next one measurable.

**Baseline:** `7609df7` (`makeFeedbackLoop`).

---

## The problem this roadmap solves

The pipeline computes a Rocchio-refined query vector and never retrieves anything
with it.

`centroidEmbedding` writes the vector into `state["topicCentroid"]`, and
`route_after_centroid` either ends the run or jumps to `reconcileSources` — which
rebuilds `topicText` by concatenating the `discovery_reason` **strings** of the
selected sources. The vector is never read again.

Supporting facts:

- No similarity query exists anywhere in the repo. `getEmbeddedUnits` is the only
  vector read and it exists solely to compute a mean.
- `extracted_units.embedding` is a `vector(1536)` column with **no index**.
- `updateUnitEmbeddings` inserts rows holding only `{extraction_run_id, embedding}`,
  so no stored vector has retrievable text attached (README Known Issue #3).

The mathematics is present; the machinery is not. Tier 0 is the prerequisite for
everything below it.

---

## Tier 0 — Make the vectors load-bearing

**Blocking.** No research content. Until this lands, no later change can be observed.

- [ ] **0.1 — Keep each embedding attached to its text.**
      `embed_pending` builds `updates` from `resp.data` alone, never zipped against
      `batch`. The OpenAI response carries an explicit `index` field precisely because
      ordering is not guaranteed, so today's alignment is incidental.

      ```python
      # src/app/services/embeddingServices.py — embed_pending
      resp = await self.client.embeddings.create(model=EMBED_MODEL, input=texts)
      vecs = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

      updates = [
          {
              "extraction_run_id": self.e_run_id,
              "unit_index":        i + offset,
              "content":           r["text"],
              "semantic_type":     r["kind"],
              "embedding":         v,
          }
          for i, (r, v) in enumerate(zip(batch, vecs))
      ]
      ```

      *Done when:* a unit id round-trips vector → text.

- [ ] **0.2 — Normalize at write time.**
      Once every stored vector has `‖v‖ = 1`, cosine and inner product coincide and the
      index can use `vector_ip_ops` (no square root per comparison). OpenAI returns
      unit-norm vectors today, but that is a convenience, not a contract — and the
      whitening (1.3) and adapter (4.2) work will break it.

- [ ] **0.3 — Index the column, and measure what the index costs.**

      ```sql
      alter table extracted_units add column content text,
                                  add column unit_index int;
      create unique index on extracted_units (extraction_run_id, unit_index);

      create index on extracted_units
        using hnsw (embedding vector_ip_ops) with (m = 16, ef_construction = 64);

      set hnsw.ef_search = 100;  -- the recall/latency dial
      ```

      *Done when:* there is a recall@10-vs-`ef_search` curve measured against exact kNN
      on the real corpus. Adding the index is trivial; knowing its recall is the point.

- [ ] **0.4 — Give `topicCentroid` a consumer.**

      ```sql
      create function match_units(q vector(1536), k int, topic uuid)
      returns table (id uuid, content text, score float)
      language sql stable as $$
        select u.id, u.content, (u.embedding <#> q) * -1 as score
        from extracted_units u
        join extraction_runs r on r.id = u.extraction_run_id
        where r.topic_id = topic
        order by u.embedding <#> q
        limit k;
      $$;
      ```

      Graph change: insert a `retrieveEvidence` node between `centroidEmbedding` and
      `routeAfterCentroid`; have `reconcileSources` build the next round's context from
      retrieved units instead of `discovery_reason` prose.

      *Done when:* the re-extract path is driven by vectors, not by concatenated strings.

---

## Tier 1 — Past the single centroid

- [ ] **1.1 — Anchor to `q₀` so the query cannot drift.**
      `topicEmbed` returns early on `reextract`, so the refined centroid becomes the next
      round's `q0`. The original topic's weight therefore decays as `α^t` — textbook
      query drift. Keep the anchor separate from the running query:

      ```
      qₜ₊₁ = norm( α·q₀ + δ·qₜ + β·mean(Rₜ) − γ·mean(Nₜ) )
      alarm: cos(qₜ, q₀) < τ  →  stop or re-seed
      ```

- [ ] **1.2 — Ide dec-hi instead of mean-of-negatives.**
      Averaging rejected units drags the query toward the corpus mean, a direction that
      carries no information. Subtract only the highest-ranked non-relevant item.

      ```
      Rocchio:    q′ = αq₀ + β·mean(R) − γ·mean(N)
      Ide dec-hi: q′ = αq₀ + β·Σ R    − γ·argmax_{n∈N} cos(n, q)
      ```

- [ ] **1.3 — Measure anisotropy, then correct it.**
      Random sentence pairs in these models typically sit at cosine 0.3–0.6, not 0.
      Measure first, then strip the common component (*all-but-the-top*) or whiten.

      ```python
      # diagnostic: mean cosine between random unit pairs. isotropic ⇒ ≈ 0
      i, j = rng.integers(0, len(X), (2, 4000))
      print(np.einsum('ij,ij->i', Xn[i], Xn[j]).mean())

      # all-but-the-top
      Xc = X - X.mean(0)
      _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
      D  = Vt[:d]                        # d ≈ 1536 // 100
      Xa = Xc - (Xc @ D.T) @ D
      ```

- [ ] **1.4 — Fit the boundary instead of assuming it.**
      `mean(R) − mean(N)` *is* the nearest-centroid decision rule. With labelled
      positives and negatives, fit it — regularized toward `q₀` so a few clicks cannot
      spin the query off-topic. Scoring stays a single dot product.

      ```
      w = argmin Σ log(1 + e^{−yᵢ wᵀuᵢ}) + λ‖w − q₀‖²
      ```

- [ ] **1.5 — Multi-vector topics.**
      One centroid cannot represent a multi-faceted topic; its mean is near none of the
      facets. Spherical k-means on the relevant set, score by max. The principled version
      is a von Mises–Fisher mixture (`p(u | μ, κ) ∝ exp(κ·μᵀu)`) fitted by EM.

---

## Tier 2 — What you rank and what you show

- [ ] **2.1 — Hybrid retrieval fused by rank.** Dense embeddings miss exact identifiers
      and numbers — the content of a `statistic` unit. Add `tsvector` + `ts_rank_cd`, and
      fuse by rank, not score (BM25 and cosine are not on comparable scales):
      `RRF(u) = Σ 1 / (k + rankₗᵢₛₜ(u))`, `k ≈ 60`.
      *Largest quality jump per line of code in this document.*

- [ ] **2.2 — Diversify the evidence set.** Top-k by cosine returns ten paraphrases of
      one fact — a real failure mode given how the extractor fans out.
      MMR: `argmax λ·cos(u,q) − (1−λ)·max_{s∈S} cos(u,s)`.
      Richer: greedy MAP-DPP, `P(S) ∝ det(L_S)` — determinant as volume, so near-parallel
      vectors are penalized automatically.

- [ ] **2.3 — Matryoshka cascade.** `text-embedding-3-small` orders dimensions by
      importance, so a truncated-and-renormalized prefix is still usable. Store a 256-d
      column (`dimensions=256`), retrieve top-200 cheaply, rescore at full width.
      Then: binary quantization (sign per dimension, 192 bytes, Hamming via `bit` + XOR
      popcount) as a ~32× prefilter, with float rescoring. Measure the recall lost.

- [ ] **2.4 — Collapse near-duplicates.** Threshold pairwise cosine at ~0.95 within a
      topic, union-find the components, keep the highest-confidence representative.
      Makes the interrupt less tedious, which makes the Tier 3 labels better.

---

## Tier 3 — Evaluation (highest leverage after Tier 0)

Every `interruptSelections` resolution is a labelled relevance judgement over a
candidate set. None of it is persisted.

- [ ] **3.1 — Log the interrupt as a bandit event.**

      ```sql
      feedback_events(id, topic_id, round, query_vec vector(1536),
                      shown_ids uuid[], selected_ids uuid[], created_at)
      ```

      `shown_ids` must preserve **display order** — without it, position bias cannot be
      corrected later. One table, one insert, one afternoon; it is the input to the rest
      of Tier 3 and all of Tier 4.

- [ ] **3.2 — Write nDCG / MRR / Recall@k / MAP by hand.** Each is under fifteen lines,
      and the discount and ideal-ranking normalizer are where the intuition lives.

      ```python
      def ndcg(rels, k):
          g = np.asarray(rels[:k], float)
          d = 1 / np.log2(np.arange(2, len(g) + 2))
          ideal = np.sort(np.asarray(rels, float))[::-1][:k]
          return (g * d).sum() / max((ideal * d[:len(ideal)]).sum(), 1e-12)
      ```

- [ ] **3.3 — Replay offline; stop guessing α, β, γ.** `1.0 / 0.75 / 0.15` are from
      Rocchio (1971) on a collection nothing like this one. Sweep the simplex against
      logged events. Expect γ to want to be near zero — negative feedback usually helps
      far less than positive.

- [ ] **3.4 — Correct for logging bias.** The user could only select from what was shown,
      and preferred what was shown first, so naive replay flatters the logging policy.

      ```
      V̂_IPS(π) = (1/n) Σ rᵢ · π(aᵢ|xᵢ) / π₀(aᵢ|xᵢ)      (clip the ratio)
      ```

      Needs ε-greedy exploration in the slate so propensities are known and bounded away
      from zero. The most transferable technique in this document.

---

## Tier 4 — Learn the geometry

All of these run on CPU over frozen OpenAI embeddings.

- [ ] **4.1 — Low-rank metric learning.** `sim_W(q,u) = qᵀ(I + LLᵀ)u`, `L ∈ ℝ^{1536×r}`,
      `r ≈ 16`. Identity-plus-low-rank keeps it close to cosine and hard to overfit.

- [ ] **4.2 — Contrastive adapter.** Freeze the API embeddings, train a small MLP with
      InfoNCE over (topic, selected unit) positives, in-batch negatives plus hard
      negatives mined from high-ranked-but-rejected units.
      `ℒ = −log exp(sim(q,u⁺)/τ) / Σ_B exp(sim(q,u)/τ)`. Temperature τ is the parameter
      that teaches the most.

- [ ] **4.3 — Replace the guessed `priority_score` with a bandit.** An LLM currently
      invents a number and everything gets extracted anyway. Extraction costs browsers,
      tokens and latency, so source choice is a genuine exploration/exploitation problem.
      LinUCB fits because arms already have feature vectors (embed `discovery_reason`):

      ```
      pick argmax_a  θ̂ᵀx_a + β·√(x_aᵀ A⁻¹ x_a)
      A ← A + x_a x_aᵀ,  b ← b + r·x_a,  θ̂ = A⁻¹b
      ```

- [ ] **4.4 — Active learning for the interrupt.** Show the candidates nearest the
      decision boundary (`argmin |wᵀu − b|`), or BALD over an ensemble. Fewer clicks,
      faster convergence, and the interrupt becomes an active-learning component rather
      than a form.

---

## Tier 5 — Study the space

Self-contained investigations; low integration risk, high learning per line.

- [ ] **5.1 — Singular spectrum of the corpus.** Effective rank (entropy of the
      normalized spectrum) and a two-NN intrinsic-dimension estimate. Explains why
      truncation (2.3) costs so little and why whitening (1.3) helps.
- [ ] **5.2 — Bottom-up vs top-down topics.** `topicExtractor` invents subtopics before
      any evidence exists. Cluster the units instead (HDBSCAN over UMAP, or spherical
      k-means at full width) and compare with adjusted mutual information.
- [ ] **5.3 — Hyperbolic embeddings for the topic tree.** Trees embed into Euclidean
      space with distortion growing with depth (node count grows exponentially in radius,
      Euclidean volume polynomially). The Poincaré ball does not have this problem:
      `d(u,v) = arcosh(1 + 2‖u−v‖² / ((1−‖u‖²)(1−‖v‖²)))`.

---

## Suggested order

1. **All of Tier 0.** Until the loop is closed, every improvement below it is
   unobservable.
2. **3.1, the feedback log.** Do it before tuning anything, because everything you tune
   afterwards needs it.
3. **1.3 + 3.3 together.** Measure the space's anisotropy, then replay the logs to fit
   α, β, γ. This pairing is the step from "Rocchio is implemented" to "I know what
   Rocchio is doing in this space and why."

After that: **2.1** for the largest quality jump per line, **4.2** for the most
transferable skill.
