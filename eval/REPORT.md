# Evaluation Report — Phase 5 (`v1.4`)

Measured against the 120-question hand-written golden dataset (`eval/golden_dataset.jsonl`).

## Summary

| Metric | Baseline as first reported (`v1.3`) | Baseline, corrected measurement | `v1.4` |
|---|---|---|---|
| Unanswerable questions declined | 17 / 35 | **35 / 35** | **35 / 35** |
| Hallucinated answers | 18 (reported) | **0** | **0** |
| Answerable questions answered (end to end) | 78 / 85 | 57 / 65 | **58 / 65** |
| Retrieval: expected doc in top 5 | — | 65 / 85 | **70 / 85** |
| Retrieval: bare tokens found | 10 / 20 (fuzzy) | 16 / 20 | **20 / 20** |
| Hedge rate (end to end) | — | — | 26 / 100 |
| Cost per question | $0.0039 | $0.0039 | $0.0040 |

The baseline column was wrong in two directions. It overstated failures on unanswerable questions, and it mixed bare-token retrieval tests into answer scoring. The corrected column re-scores the **same** baseline run with fixed metrics. The `v1.4` column is a fresh run after the one pipeline change below.

## What changed in the system

One setting:

| Setting | Before | After | Evidence |
|---|---|---|---|
| `BM25_WEIGHT` | 0.5 | **1.0** | Retrieval sweep below |

### Retrieval sweep (85 answerable questions, no LLM calls)

| BM25 weight | Total | simple_lookup | multi_step | exact_token |
|---|---|---|---|---|
| 0.0 (vector only) | 63 | 29 / 40 | 18 / 25 | 16 / 20 |
| 0.5 (previous) | 65 | 30 / 40 | 19 / 25 | 16 / 20 |
| **1.0** | **70** | **30 / 40** | **20 / 25** | **20 / 20** |
| 1.5 | 63 | 27 / 40 | 18 / 25 | 18 / 20 |
| 2.0 | 63 | 27 / 40 | 18 / 25 | 18 / 20 |

- Hybrid retrieval adds **+7** correct documents over vector search alone.
- Above 1.0, keyword matches start displacing good semantic results (`simple_lookup` 30 → 27).
- Retrieval is deterministic, so these differences are real rather than run-to-run noise.

## What changed in the measurement

Most of this phase was fixing the yardstick, not the system.

**1. Hedges were scored as hallucinations.** All 18 "wrongly answered" questions had in fact opened with the exact refusal sentence, then added a line about what the documentation *did* cover. The detector required a refusal to be under ~190 characters, so a correct refusal with one helpful sentence counted as a failure. Hedges now count as declines and are tracked separately as an early-warning signal. ([INC-008](../INCIDENTS.md))

**2. Bare tokens were scored on their answers.** Twenty questions are bare strings (`aal2`, `42501`, `maybeSingle()`) written to test keyword retrieval. A bare string is not a question — the model reasonably asks for clarification. These are now scored on retrieval only.

**3. Bare tokens had the wrong test.** A token such as `exchangeCodeForSession` appears in four or more documents. Requiring one specific file marked correct retrievals as misses. They are now scored on whether any retrieved chunk contains the token text.

**4. Two dataset labels were wrong.** `maybeSingle` appears only in `generating-types.mdx`; `SUPABASE_SERVICE_ROLE_KEY` did not appear in its labelled file at all. Both corrected. ([INC-009](../INCIDENTS.md))

## Tried and reverted

**BM25 override of the refusal gate.** Bare tokens score high cosine distance because they have no sentence context, so the gate refused them. Letting a strong keyword score override the gate failed: "pizza" scores 13.47 against the PostGIS guide, which uses a restaurant example dataset. Keyword presence is not evidence of answerability. Reverted. ([OBS-004](../INCIDENTS.md))

## Still open

**Seven answerable questions declined end to end:** enterprise SSO setup, mobile OAuth return flow, calling an Edge Function from JavaScript, foreign keys, configuring backups, server-side session validation, Management API authentication. Some may be retrieval misses; some may be wrong labels.

**Fifteen retrieval misses** among normal questions (10 `simple_lookup`, 5 `multi_step`). Given two labels were already wrong, some of these are likely label errors rather than retrieval failures.

**Unanswerable questions are mostly easy.** Most use absolute phrasing ("exact", "guaranteed", "confidential"). The hard refusals are mild, ordinary questions. The set should be extended in that direction.

**Not tested:** candidate depth, RAGAS and DeepEval metrics. Deferred — the hand-built set already produced specific, actionable findings.

## Reproduce

```bash
python -m eval.validate_dataset     # dataset integrity
python -m eval.retrieval_eval       # retrieval sweep, free, ~7 min
python -m eval.run_golden           # full end-to-end run, ~$0.50, ~8 min
python -m eval.summarize            # end-to-end results
```

Reference run for `v1.4`: `eval/results/run-20261020-041848.jsonl`
