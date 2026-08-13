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