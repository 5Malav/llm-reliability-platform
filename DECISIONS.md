# Engineering Decisions

A running log of architectural decisions, the alternatives considered, and the reasoning. Each entry is a defensible choice, not a default.

---

## DEC-001 — SHA-pinned document corpus (not live scraping)

**Decision:** Pull Supabase docs from their public source repository (`apps/docs/content`), pinned to a specific commit SHA. Do **not** scrape rendered HTML.

**Rejected alternative:** Scraping the live docs website.

**Why:** A SHA-pinned corpus is reproducible — anyone can rebuild the exact vector store from the exact source. Scraping is fragile (breaks when the site's HTML changes) and unreproducible (the corpus silently drifts as the site updates). This is DVC-style thinking applied to documents: the data source is versioned, not a moving target.

**Trade-off:** When Supabase ships new docs, I must deliberately re-pin and re-index — the corpus doesn't auto-update. That's a feature: re-indexing becomes a controlled, observable event, not a silent change.

**Implementation:** Shallow sparse-checkout of only `apps/docs/content`, git metadata stripped so files become plain content. Pinned SHA: `5b68af1720454884faa18eee16cc2af5aa093181` (817 `.mdx` files, 6.6 MB). Recorded in `ingestion/data/SOURCES.md`.

---

## DEC-002 — Model & cost policy: Haiku-default, Batch-gated evals

**Decision:** Claude Haiku 4.5 is the default model everywhere (dev loops, smoke tests, LLM-as-judge). Sonnet 4.6 is used only where evals prove the quality gain justifies the cost. Full golden-eval runs happen only at phase gates, via the Batch API. Daily iteration uses a ~20-question smoke set.

**Rejected alternative:** Sonnet-by-default for quality; running the full eval set on every change.

**Why:** Haiku is ~5× cheaper than Sonnet at near-comparable quality for most tasks. The real budget killer is eval runs (150 questions × generation × multiple judge calls). Restricting full evals to phase gates and routing them through the Batch API (50% discount) keeps the entire project under a ~$20–30/month budget. Cost-per-query is itself a monitored metric — cost discipline is part of the product, not a constraint on it.

**Trade-off:** The ~20-question smoke set gives faster but less complete signal during iteration. Acceptable — full signal is available on demand at gates.

---

## DEC-003 — Docs-only corpus for v1.0; GitHub issues deferred

**Decision:** Build the initial pipeline on Supabase's 817 MDX docs alone. Defer GitHub issues to a post-v1.0 enrichment.

**Rejected alternative:** Pulling docs + issues together for v1.0.

**Why:** Validate the full RAG pipeline (chunk → embed → store → retrieve → cite) on clean, uniform data before adding a noisier, differently-formatted source. Adding issues on day one would mean debugging data quality and retrieval logic simultaneously. Sequencing reduces risk and isolates variables — get the simplest version working end-to-end, then enrich.

**Trade-off:** v1.0 answers happy-path questions well but not real-world debugging ("why is X failing for me"). Accepted — issues are a planned, measurable addition once the pipeline is proven, extending a validated system rather than building on unproven machinery.

## DEC-004 — Custom regex cleaner over MDX parser library

**Decision:** Clean MDX with a small custom script (strip-then-mask ordering, code-block protection) rather than a markdown/MDX parser library.

**Rejected alternative:** A generic MDX AST parser.

**Why:** Supabase uses non-standard MDX (`<$Show>`, `<$Partial>`) that generic parsers don't handle. For a bounded, inspected, one-time batch over 817 files, a targeted cleaner I control is simpler and more robust than a dependency that chokes on custom syntax — and when an edge case appears (INC-001), I can fix it because I wrote it.

**Trade-off:** The cleaner is corpus-specific, not general-purpose. Acceptable — it's a batch job for a fixed corpus, not a live pipeline over arbitrary MDX.

## DEC-005 — Fixed-size chunking: 500 tokens, 75-token overlap, 100-token floor

**Decision:** Chunk documents with a fixed 500-token sliding window, stepping 425 tokens (75-token / 15% overlap). Drop trailing slices under 100 tokens. Whole documents shorter than 500 tokens are kept intact regardless of size.

**Rejected alternatives:** Semantic chunking (an LLM call per split — slow, expensive, unjustified without a baseline). Structure-aware chunking at headings (uneven sizes, fragile on inconsistent docs).

**Why:** 500 tokens fits how documentation is written — one focused section per chunk: large enough for a complete how-to, small enough to keep the embedding sharp. 15% overlap protects answers that span a chunk boundary. The 100-token floor removes trailing scraps whose content is already present, complete, in the previous chunk via overlap.

**Important nuance:** the floor applies only to *sliced* remainders, not to whole short documents. Inspection showed 33 sub-100-token chunks were complete FAQ/troubleshooting answers ("why am I getting JWT expired errors?"). Small is not the same as incomplete — filtering by size alone would have deleted real answers.

**Trade-off:** These numbers are a starting hypothesis, not a tuned result. Chunk size is a config value; retrieval quality will be measured against the golden dataset in Phase 4–5, and this is the first dial to turn if results underperform.

## DEC-006 — Keep `_partials/`, exclude `_fixtures/`

**Decision:** Include Supabase's `_partials/` fragment files as first-class documents in the corpus. Exclude anything under `_fixtures/`.

**Rejected alternatives:** Excluding all `_partials/` (they're fragments, not standalone pages). Including everything (fixtures are build scaffolding).

**Why:** The cleaner strips `<$Partial>` injection tags, so partial content does not survive inside the pages that reference it — the partial file is the only remaining source. Some partials hold unique, high-value content (API rate limits exist nowhere else). Excluding them would create real knowledge holes. Fixtures, by contrast, are test scaffolding with zero informational value.

**Principle:** Filter on content value, not folder name. Same lesson as the chunk-size floor — unusual location or small size doesn't mean worthless; *incomplete* does.

## DEC-007 — Chunk metadata: URL, doc type; section headings deferred

**Decision:** Each chunk carries a resolvable docs URL and a document type (guide / troubleshooting / partial). Section-level headings are deferred to Phase 3.

**Why:** URL enables verifiable citation — the trust mechanism of the system. Doc type is nearly free (derived from the top-level folder) and becomes a retrieval filter: error-shaped questions can bias toward troubleshooting content. Section headings require tracking heading context through the chunking loop, and their value is speculative until retrieval quality can be measured — so they wait until Phase 3, when the eval set can show whether they help.

**Note on partials:** the 46 chunks sourced from `_partials/` carry `url: None` rather than a fabricated link. A wrong citation is worse than an absent one — it invites verification and sends the user somewhere the claim isn't.

## DEC-008 — Postgres + pgvector, no vector index for v1.0

**Decision:** Store chunks and embeddings in Postgres with the pgvector extension, running in Docker. Use `text-embedding-3-small` (1536 dimensions). Add a B-tree index on `doc_type`, but **no** vector index (HNSW/IVFFlat) for now.

**Rejected alternatives:** A dedicated vector database (Pinecone, Weaviate) — another service, another failure mode, another vendor, and a second source of truth to sync with metadata. `text-embedding-3-large` (3072d) — double the cost, storage, and comparison time for a quality gain I can't yet measure.

**Why no vector index:** At 2,654 rows a sequential scan is sub-millisecond. HNSW and IVFFlat are *approximate* — they trade recall for speed — so indexing here means accepting slightly worse results to solve a latency problem that doesn't exist. Search latency is instrumented in Phase 6; if p95 exceeds budget as the corpus grows, adding an index becomes a measured change with a before/after.

**Schema notes:** `chunk_id` carries a UNIQUE constraint as a re-run guard — a duplicate insert is rejected by the database rather than silently doubling the corpus. `url` is nullable because 46 partial-sourced chunks have no standalone page.

**Trade-off:** Changing embedding models later requires altering the column dimension and re-embedding the corpus. Known migration cost, accepted.

## DEC-009 — Chunk IDs derived from full source path

**Decision:** `chunk_id` = full source path with separators replaced, plus chunk index (`guides__ai__concepts__0`).

**Rejected alternative:** Filename stem plus index (`concepts__0`) — shorter and more readable, but not unique.

**Why:** Filenames repeat across folders in the source corpus; only the full path is unique. An identifier derived from a partial key will eventually collide, and the failure is silent — a dictionary keyed on it drops rows without error (INC-005). Readability is not worth correctness in an identifier.