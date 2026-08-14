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