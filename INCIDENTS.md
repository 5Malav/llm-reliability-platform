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