# Engineering RAG Corpus

Engineering RAG Corpus is a bounded, provenance-aware pilot for retrieving evidence from engineering documentation and deciding whether that evidence is sufficient to support a conclusion. Its current code focuses on one pinned source: the official AzerothCore Wiki. It is not a production corpus or a deployed multi-domain retrieval service.

## Purpose and design

The project addresses a practical weakness in AI-assisted engineering: a model can produce plausible guidance without knowing the project version, the authority of a source, or whether the retrieved passage actually supports the answer. The pilot tests a source-grounded workflow that keeps source identity, version, document structure, language, and evidence sufficiency visible.

Its design distinguishes:

- **Source acquisition and provenance:** record the upstream, commit, license, source scope, and integrity evidence.
- **Normalization and chunking:** preserve headings, code, tables, includes, language, and references; compare structural profiles with a fixed-window baseline.
- **Retrieval:** evaluate lexical, dense, and hybrid results against a small manually reviewed question set.
- **Evidence sufficiency:** return `supported`, `insufficient_evidence`, or `no_relevant_evidence`; this component does not generate an answer.
- **Promotion:** keep the pilot bounded; successful processing alone does not authorize full-source ingestion.

The source-specific pilot code is not the shared generic RAG engine. A future reusable engine is described in [`retrieval_augmented_generation_system`](https://github.com/blainesmith33/retrieval_augmented_generation_system), which currently documents architecture and ownership boundaries only.

## Current implementation

The local `main` checkout contains a bounded Python implementation and fixtures:

- `scripts/azerothcore_wiki_chunking.py` — deterministic normalization and chunk-profile evaluation for explicitly listed sample files. It reads the pinned snapshot, limits the sample size, records provenance, and does not create a production vector collection or trigger full-source ingestion.
- `scripts/azerothcore_wiki_abstention.py` — evidence sufficiency and abstention calibration/query logic for the previously generated pilot sample. It consumes sample chunks and embeddings; it does not normalize additional pages, embed the corpus, or synthesize answers.
- `config/` — sample selection, evaluation questions, and abstention evaluation configuration.
- `schemas/` and `sources/` — source records, acquisition manifests, and source inclusion policy.
- `docs/` and `reports/` — processing contracts, external data boundary, and historical acquisition evidence.
- `tests/test_azerothcore_wiki_chunking.py` and `tests/test_azerothcore_wiki_abstention.py` — focused test code is present.

The repository history records the implementation milestones:

- `bb6d691574372dd9eeb14dcc5015e2dd213cb99b` — register the official wiki snapshot.
- `32b7d0c3602f0114624dba8b32b883b2a70de491` — implement the bounded chunking pilot.
- `a69f3f70a10190ed19fb4952a799751e58c09b27` — add abstention calibration.

These commits establish that code and tests were added. No test suite was run for this review, and the available records do not justify claiming that the current checkout’s tests pass today.

## Pilot scope and validation status

The registered source is `azerothcore_wiki_official`, pinned to upstream commit `7d540fc7e683c3bf34a2f465789f1b3df268b609`. The acquisition report records a full clone, 1,054 inventoried files, a reproducible inventory, and a clean snapshot at acquisition time. It also records that normalization, embeddings, vectors, and an index had not been created at that acquisition checkpoint. Later code and documents describe a bounded sample normalization/chunking and retrieval evaluation, followed by an abstention v1 evaluation over 64 manually reviewed questions (32 answerable and 32 intentionally unanswerable).

The abstention documentation says v1 identified remaining weaknesses, including exact-identifier acceptance, table-row relation binding, command-family interpretation, and alternative-valid evidence. It calls for a new sealed holdout and v2 calibration; full-source ingestion remains blocked until the acceptance gate passes. The reported evaluation figures in the detailed remote README are historical project reports, not results independently reproduced during this review.

At the time of this review, the configured external data root—`/run/media/deck/blAIne-476GB-SAM/blAIne/rag-data/engineering-rag/`—was not available in the review environment. The acquisition report and source registration refer to the pinned source snapshot and experiment outputs there. Consequently, end-to-end reproduction from the recorded inputs could not be verified during this review. The snapshot and generated experiment artifacts must be restored or re-registered before claiming reproducibility.

**Status:** bounded source-specific prototype with code, fixtures, and tests; historical acquisition and evaluation evidence; full-source ingestion and production promotion not authorized; end-to-end reproducibility not verified during this review. This is more than a documentation-only project, but less than a complete operational engineering RAG system.

## Development direction and contribution context

The relevant CICS conversation archive shows the project’s direction changing over time. In March, the work was described as broad, multi-domain source acquisition, with engineering and conversation corpora kept distinct. Blaine questioned claims that coverage was nearly complete, raised missing sources and future scale as planning concerns, and explicitly required organization by domain/section and then language. Later, the local repository narrowed the work to a one-source AzerothCore Wiki pilot with explicit sample and abstention gates. The early multi-million-chunk scale discussion is not a measured corpus size or a finalized implementation requirement.

Primary conversation references: `chat_archives/cics_raw_chats/Coding RAG Milestone_69bc8fd2-9f5c-83e8-9dd9-4713e7824673.md`, message 156 (section/domain then language requirement); and `Engineering RAG Corpus Completion_69bf3e95-d35c-83e8-a5e9-ae3479771eea.md`, messages 1, 69, 75, and 83 (acquisition handoff, concern about missing sources, scale discussion, and stated direction). The corresponding oversized raw JSON files were not retrievable through the connected tool in this review; these citations use their readable Markdown companions.

Blaine’s supported contribution includes the problem framing, domain and provenance requirements, project boundaries, implementation priorities, and evaluation expectations. AI tools assisted with technical design, Python code, tests, troubleshooting, and documentation. The repository artifacts do not establish that Blaine independently wrote every line or technical mechanism; the conversations do show active review and direction, including correction of a proposed chunk layout that did not meet the stated section/language organization.

## Public repository visibility

The implementation and this README are published on GitHub `main` at reconciliation commit `7043b99` (2026-11-26). The public branch includes the bounded prototype source, tests, schemas, configuration, reports, and supporting documentation described above. The previous, substantially longer root README is preserved at [`docs/history/README-main-2026-08-01.md`](docs/history/README-main-2026-08-01.md), with a provenance note alongside it.

Publication makes the implementation inspectable; it does not establish that the external source snapshot and generated experiment artifacts are currently available or that end-to-end reproduction has been verified.

## Repository and data boundary

The Git repository stores compact code, source records, schemas, policies, evaluation definitions, tests, and reports. Large source snapshots, generated chunks, embeddings, and indexes are external runtime data. That separation is intentional, but it requires the external data root and reproducibility records to remain available to anyone expected to reproduce the work.

## References

- [`scripts/azerothcore_wiki_chunking.py`](scripts/azerothcore_wiki_chunking.py)
- [`scripts/azerothcore_wiki_abstention.py`](scripts/azerothcore_wiki_abstention.py)
- [`docs/azerothcore-wiki-normalization-chunking.md`](docs/azerothcore-wiki-normalization-chunking.md)
- [`docs/azerothcore-wiki-abstention.md`](docs/azerothcore-wiki-abstention.md)
- [`docs/external-data-storage.md`](docs/external-data-storage.md)
- [`reports/azerothcore-wiki-acquisition.md`](reports/azerothcore-wiki-acquisition.md)
- [`sources/`](sources/), [`config/`](config/), [`schemas/`](schemas/), [`tests/`](tests/)
