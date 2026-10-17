# Retrieval evaluation

How well search finds the right policy section, measured — so retrieval choices rest on numbers.

```bash
uv run mypal-eval-retrieval                                                # dense vs BM25 vs hybrid
uv run mypal-eval-retrieval --rerank-model Xenova/ms-marco-MiniLM-L-6-v2  # + reranker
```

The tool parses the documents listed in `retrieval_questions.json` with the real ingestion pipeline, indexes them with the real models into a temporary Qdrant collection (deleted afterwards) and runs every question through each configuration. Postgres is not used. Full per-question results are written to `results/`.

## The question set

`retrieval_questions.json` — 39 questions over the **fictional** sample policies, written by the developer:

| Type | n | What it tests |
|---|---|---|
| exact | 7 | Wording close to the policy text |
| keyword | 6 | Codes and exact terms ("form SA-1", "Grade C") |
| paraphrase | 13 | Same meaning, different words ("unwell" → sick leave) |
| misspelling | 5 | Typos ("sik leaves", "salery advanse") |
| policy_name | 2 | Questions naming the policy |
| unanswerable | 6 | Not covered by any policy — should be referred to HR |

**Limitations.** This is a small development set on invented documents. It is not the ~100-question HR-approved golden set (Phase 8), and its results do not establish accuracy on real policies. With 33 answerable questions, one question is ±3 percentage points.

## Metrics

- **hit@k** — share of answerable questions with a correct section in the first k results. hit@5 matters most: the top 5 passages are what the language model sees.
- **MRR** — mean reciprocal rank: 1 if the correct section is first, ½ if second, ⅓ if third…
- **Confidence gate** — with best cosine similarity below `MYPAL_RETRIEVAL_MIN_SCORE`, the question is referred to HR without calling the model.

## Results (2026-10-17)

Models: `BAAI/bge-small-en-v1.5` (dense), `Qdrant/bm25` (keyword), RRF k = 60, `Xenova/ms-marco-MiniLM-L-6-v2` (reranker, top 10 candidates). Laptop CPU.

| Configuration | hit@1 | hit@3 | hit@5 | MRR | ms / question |
|---|---|---|---|---|---|
| dense | 79% | 91% | 94% | 0.86 | ~20–40 |
| BM25 | 61% | 67% | 76% | 0.66 | ~10 |
| hybrid (RRF) | 61% | 91% | 94% | 0.75 | ~35 |
| dense + reranker | 85% | 91% | **100%** | 0.90 | ~185 |
| **hybrid + reranker** (chosen) | 85% | 91% | **100%** | 0.89 | ~195 |

hit@1 by question type:

| Configuration | exact | keyword | misspelling | paraphrase | policy name |
|---|---|---|---|---|---|
| dense | 100% | 100% | 60% | 62% | 100% |
| BM25 | 100% | 100% | 40% | 31% | 50% |
| hybrid (RRF) | 100% | 100% | 60% | 23% | 50% |
| hybrid + reranker | 100% | 100% | 80% | 77% | 50% |

## Findings

1. **Hybrid RRF on its own made ranking worse** (hit@1 79% → 61%). BM25 is weak on paraphrases (31%), and RRF gives both lists an equal vote, so BM25's poor ordering pulled good dense results down. The dense model already handles the codes in these documents ("SA-1", "Grade C") — 100% on keyword questions.
2. **The cross-encoder reranker fixes the ordering** and is the only change that reached hit@5 = 100%: paraphrases 23–62% → 77%, misspellings 60% → 80%.
3. **BM25 adds nothing measurable on this set** — dense + reranker scores the same as hybrid + reranker.
4. **No similarity threshold separates answerable from unanswerable questions.** Best cosine scores: answerable 0.56–0.91, unanswerable 0.43–0.73 (overlapping). The reranker's scores overlap too (it scores misspellings very low even when the right passage is found). At the old threshold 0.65, 5 of 33 answerable questions were wrongly referred.

## Decisions

| Decision | Reason | Revisit when |
|---|---|---|
| Reranker on (`ms-marco-MiniLM-L-6-v2`) | Best on every metric; ~0.2 s per question is small next to 15–45 s of generation | Real-policy set shows no gain, or latency matters (GPU/hosted model) |
| Keep hybrid (BM25) as the candidate generator | No measured gain here, negligible cost (~10 ms). Real HR documents contain acronyms and codes (CL, PL, LTA, ESIC, form numbers) the small dense model may not know; BM25 finds those by exact match | The HR golden set shows BM25 never contributes → switch `MYPAL_RETRIEVAL_MODE=dense` |
| Gate lowered 0.65 → 0.55 | 0/33 answerable wrongly referred (was 5/33). Only clearly unrelated questions are stopped early; the rest are handled by the model's "not in policy" path and the validator | Real policies give a different score distribution |

**Second safety layer, checked with the real model (Ollama `qwen3.5:9b`) at threshold 0.55:** the four unanswerable questions that now pass the gate (dress code, work from home, gym membership, overtime) were all refused as "not in policy". Of the four answerable questions the old gate wrongly refused, two were answered correctly and two received reasonable clarification questions ("medical certificate" alone; "interns", which the policy calls trainees).
