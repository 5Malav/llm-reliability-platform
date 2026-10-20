# Incident Log

Real failures encountered building and running this system, in SRE post-mortem style. Captured as they happen — root cause, fix, and prevention. These are the raw material for the public incident log (Phase 11).

---

## Template (copy for each incident)

### INC-XXX — [Short title]

- **Date:**
- **Symptom:** What broke, as observed.
- **Impact:** What it affected (a query, the pipeline, a deploy).
- **Root cause:** The actual underlying reason (not the surface symptom).
- **Fix:** What resolved it.
- **Prevention:** What stops it recurring (a test, a check, a guardrail).

---

<!-- Real incidents go below this line as they occur. -->

### INC-001 — MDX component tags survived cleaning (masking-order bug)

- **Date:** 2026-08-11
- **Symptom:** Component tags (`<$Show>`, `<TabPanel>`, multi-line `<Tabs>`) remained in cleaned output, clustered around code blocks. Affected 1–2 of 793 files.
- **Impact:** Leftover markup would embed into chunks and could surface inside cited answers — a correctness/trust issue in a reliability project. Low blast radius but real.
- **Root cause:** Two-part. (1) Code blocks were masked *before* tags were stripped; where tags wrapped adjacent code, the masking swallowed them into placeholders, so they escaped the strip and reappeared on restore. (2) Multi-line `<Tabs ...>` tags weren't matched because the strip regex didn't span newlines.
- **Fix:** (1) Reordered pipeline to strip ALL tags *before* masking code (strip-then-mask). (2) Added `re.DOTALL` so the regex matches multi-line tags.
- **Prevention:** Verified cleaned *content* via grep across all 793 files, not just the processed-count. The count said 793/793 clean; content inspection revealed the bugs. **Lesson: verify output content, not just counts — the failure that looks like success is the dangerous one.**

### INC-002 — Chunker produced 2-token fragment chunks

- **Date:** 2026-08-12
- **Symptom:** Initial chunking run reported success (2,760 chunks) but the smallest chunk was 2 tokens; 138 chunks were under 100 tokens. Samples: `" }} ```"`, `" seamless onboarding"`.
- **Impact:** Fragment chunks would be embedded (wasted cost), stored as retrieval noise, and — worst — could be retrieved as context for an answer. A 3-word chunk gives the model almost no grounding, which is an invitation to hallucinate. Directly undermines the project's core goal.
- **Root cause:** The sliding window advances by 425 tokens and takes whatever remains at the end of a document, with no minimum. Documents whose length fell just past a step boundary produced tiny trailing scraps.
- **Fix:** Added `MIN_CHUNK_TOKENS = 100` — trailing slices below the floor are dropped. Safe because overlap means that content already appears, complete, in the previous chunk.
- **Follow-up finding:** 33 sub-100-token chunks survived the fix. Investigation showed these are *whole short documents* (total_chunks = 1) taking the early-return path — complete FAQ answers, not fragments. Correctly left intact. **Lesson: filter on completeness, not size.**
- **Prevention:** Inspected the distribution of chunk sizes and read the actual smallest chunks rather than trusting the "complete" summary. Third time in this phase that content inspection caught what the summary hid.

### INC-004 — Stale output files caused pipeline count mismatch

- **Date:** 2026-08-13
- **Symptom:** After excluding test fixtures, the cleaner reported 792 documents but the chunker read 793. Fixture chunks persisted in the corpus despite the filter.
- **Impact:** Corpus contained a test-scaffolding document that should have been excluded. Silent — no error, just two stages quietly disagreeing on document count.
- **Root cause:** The cleaner wrote new output without clearing the old. A previously-generated fixture JSON survived the re-run, so the output directory held a mix of two configurations. The stage was incremental when it needed to be idempotent.
- **Fix:** Cleaner now wipes its output directory before writing, so a re-run reflects current settings exactly.
- **Prevention:** Cross-checked counts between consecutive pipeline stages. The mismatch (792 vs 793) was the only signal — neither stage errored. **Lesson: when two stages disagree on a count, believe the disagreement.**

### INC-005 — chunk_id collisions silently dropped 119 chunks

- **Date:** 2026-08-14
- **Symptom:** Embedding job reported "2,654 chunks embedded" but "2,535 total in file." No error raised — two summary lines simply disagreed by 119.
- **Impact:** 119 chunks of real documentation silently missing from the corpus (AI concepts, semantic search guides). The system would have reported "no information available" for content that was successfully ingested and paid for. Downstream, the `chunk_id UNIQUE` constraint would have rejected these inserts in Postgres, surfacing as confusing constraint errors far from the actual cause.
- **Root cause:** `chunk_id` was built from `path.stem` — the filename without its folders. Supabase reuses common filenames across topic folders (`guides/ai/concepts.mdx` and `guides/realtime/concepts.mdx`). Both produced `concepts__0`. The results dictionary was keyed by `chunk_id`, so the second document silently overwrote the first. 87 colliding IDs, 119 lost rows.
- **Fix:** Build the document key from the full source path with separators replaced (`guides/ai/concepts.mdx` → `guides__ai__concepts`). Path uniqueness now guarantees ID uniqueness.
- **Prevention:** Cross-checked "chunks processed" against "chunks saved" — the only signal. Added a uniqueness assertion to the verification step. **Lesson: when a job reports two counts, check they agree. Identity derived from a partial key is identity waiting to collide.**

### OBS-001 — Retrieval redundancy: multiple chunks from one document

- **Date:** 2026-08-14
- **Observation:** A query for GitHub authentication returned two of five results from the same source document (`self-hosted-oauth`), different chunks. Result diversity is reduced — fewer distinct sources reach the answer stage.
- **Impact:** Not a failure, but a quality ceiling. If two slots go to one document, the LLM sees a narrower evidence base than the top-k count suggests.
- **Planned fix:** Phase 3 — either cap chunks per document in the result set, or apply reranking with diversity. Deferred until retrieval quality can be measured against the golden dataset.

### OBS-002 — Partials retrieve well but have no citable URL

- **Date:** 2026-08-14
- **Observation:** A query for API rate limits returned a `_partials/` chunk as the single best match (distance 0.39) — better than any full guide. But partials carry `url: None` by design (DEC-006), so this best-answer chunk cannot be linked.
- **Impact:** The strongest retrieval result for some queries is uncitable. Raises a Phase 2 design question: how does the answer layer present a grounded claim with no source link?
- **Options:** cite the parent page that includes the partial, or state the source name without a link. Deferred to Phase 2 answer design.

### INC-006 — Refusal string used as a preamble, corrupting the refusal metric

- **Date:** 2026-08-29
- **Symptom:** A well-retrieved query ("why am I getting row level security errors?", distance 0.477 — within the answerable range) produced the exact refusal sentence followed by a complete, correctly-cited answer.
- **Impact:** The refusal metric lied. Detection used `text.startswith(REFUSAL)`, so this logged as `refused=True` while the user received a full answer. A Phase 6 dashboard would have shown a refusal that never happened — silent metric corruption, exactly the failure class this project exists to catch.
- **Root cause:** Two failures. (1) Prompt ambiguity: Rule 4 (partial answers) conflicted with Rule 3 (refuse), so the model satisfied both. (2) Naive detection: a prefix match cannot distinguish a refusal from a refusal-shaped preamble.
- **Fix:** (1) Prompt Rule 3 now states the refusal must be the entire response. (2) `is_refusal()` requires the response to be short as well as prefix-matching. (3) Added a separate `hedged` flag that records the contradiction when it still occurs.
- **Residual:** The hedge still occurs on this query after the prompt fix, but is now correctly classified (`refused=False`, `hedged=True`) rather than miscounted. The behavior is visible instead of hidden — a known issue with a metric attached, not a silent one.
- **Prevention:** Any string-matched behavior needs a check that the match *is* the whole behavior, not merely its prefix.

### OBS-003 — Cross-encoder reranker degraded retrieval on this corpus

- **Date:** 2026-10-02
- **Observation:** `ms-marco-MiniLM-L-6-v2` reranking made results worse on both test queries, promoting topically-similar but incorrect pages above pages containing the actual answer. Added ~5s per query.
- **Suspected cause:** domain mismatch — model trained on web-search passages, applied to technical documentation with tables, code blocks and reference material. It appears to favour short focused troubleshooting pages over longer reference docs.
- **Action:** not shipped. Revisit with measurement in Phase 5.

### OBS-004 — BM25 cannot distinguish "mentioned" from "documented"

- **Date:** 2026-10-13
- **Attempted:** let a strong BM25 score override the distance refusal gate, to fix 7 bare-token queries being wrongly refused.
- **Why it failed:** "pizza" scores 13.47 against the PostGIS guide, which uses a restaurant example dataset. The term is in the corpus as sample data, not as documentation. BM25 measures lexical presence, not answerability.
- **Conclusion:** the premise was unsound, not the implementation. Reverted.

### INC-008 — Refusal metric scored correct refusals as hallucinations

- **Date:** 2026-10-20
- **Symptom:** baseline reported 18 of 35 unanswerable questions answered — 51% failure on the project's headline claim.
- **Impact:** the README published a refusal accuracy of 49%. The real figure was 100%. The metric, not the system, was failing.
- **Root cause:** `is_refusal()` required the response to be under ~190 characters. All 18 "failures" opened with the exact refusal sentence and then added a line about what the documentation did cover. Longer than the limit, so scored as answered.
- **Fix:** hedges count as declines in scoring; hedge rate tracked as a separate metric. README corrected publicly.
- **Prevention:** read failures before fixing them. We were one step from rewriting the prompt to solve a hallucination problem that did not exist.

### INC-009 — Golden dataset labels wrong; bare-token test too strict

- **Date:** 2026-10-20
- **Symptom:** 10 of 20 bare-token questions appeared to miss the correct document.
- **Root cause:** two labels were wrong (`maybeSingle` lives only in `generating-types.mdx`; `SUPABASE_SERVICE_ROLE_KEY` was absent from its labelled file). And most tokens appear in 4+ documents, so requiring one specific file marked correct retrievals as misses.
- **Fix:** corrected both labels; bare tokens now scored on whether any retrieved chunk contains the token text. Result: 20 / 20.
- **Prevention:** validating that a labelled file *exists* is not validating that it *contains the answer*. Check labels against the corpus with grep.

### INC-010 — Confirm run measured code that was supposed to be reverted

- **Date:** 2026-10-20
- **Symptom:** a full eval run was used to confirm a change, but the BM25 override from Step 1 — documented as reverted — was still active in `rag.py`.
- **Impact:** results (59/65, $0.5052) described different code from what the notes, README and report claimed. Caught before commit.
- **Root cause:** the revert instruction was never applied, and code state wasn't checked before measuring.
- **Fix:** reverted properly, verified with `grep`, re-ran: 58/65, 35/35, $0.4761. Out-of-scope questions are gated again, which is where the $0.03 saving comes from.
- **Prevention:** check the code is in the expected state *before* a measurement run, not after. A number is only as trustworthy as the code it was measured against.