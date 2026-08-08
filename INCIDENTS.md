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