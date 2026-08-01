# Engineering RAG Corpus

A provenance-aware engineering knowledge corpus and retrieval-augmented generation system for official documentation, community knowledge, and validated internal engineering work.

The Engineering RAG Corpus is designed to provide AI development tools—especially Codex—with reliable, source-grounded technical evidence before they write code, diagnose failures, recommend architecture, or modify infrastructure.

This project is not simply a collection of documentation and is not merely a vector database. It is a governed retrieval system that preserves source identity, authority, version, structure, and validation status while testing whether retrieved evidence is actually sufficient to support an answer.

## Project Status

**Active pilot implementation and retrieval-validation phase**

The first pilot source—the official AzerothCore Wiki—has been:

* acquired from its authoritative upstream repository;
* pinned to an exact commit;
* inventoried and registered;
* preserved as an immutable external snapshot;
* normalized with a deterministic Markdown parser;
* tested against multiple chunking strategies;
* embedded locally with a verified embedding model;
* evaluated with dense, lexical, and hybrid retrieval;
* tested against answerable and intentionally unanswerable questions.

The first abstention and evidence-sufficiency evaluation identified remaining weaknesses in structured table interpretation, command-signature validation, and alternative-valid evidence handling.

Full-source ingestion has **not** yet been authorized.

The immediate milestone is abstention calibration version 2 using a fresh sealed holdout evaluation set.

## Purpose

General-purpose AI models can provide broad software-engineering assistance, but they do not automatically know:

* the exact version of a project being used;
* which documentation is authoritative;
* whether a configuration key or command actually exists;
* how the local implementation differs from generic guidance;
* which prior fixes were tested successfully;
* which architecture decisions must be preserved;
* which operational procedures are authoritative;
* or whether retrieved text genuinely supports the requested conclusion.

The Engineering RAG Corpus exists to reduce work based on incomplete memory, stale training data, plausible invention, and unsupported assumptions.

The intended engineering workflow is:

```text
Inspect the active repository
→ query the Engineering RAG Corpus
→ retrieve source-grounded evidence
→ inspect provenance and authority
→ reason over evidence and current code
→ implement
→ test
→ validate
```

The corpus does not replace direct repository inspection, compilation, testing, or operational validation. It provides a stronger and more accurate knowledge foundation for those activities.

## Primary Consumers

The system is intended to support:

* Codex
* local AI development agents
* engineering assistants
* diagnostic tools
* documentation systems
* architecture-review workflows
* future blAIne knowledge and governance infrastructure

A planned read-only MCP or equivalent local interface will allow Codex to:

* search the corpus;
* retrieve supporting chunks;
* expand neighboring context;
* filter by source, project, authority, language, or provenance;
* inspect source status;
* cite exact documents, headings, symbols, and versions;
* reason over retrieved documentation alongside active source code;
* analyze retrieval failures and improve the RAG pipeline under controlled evaluation.

## Knowledge Classes

Every source belongs to one of three explicit provenance classes.

### Official Documentation

Identifier:

```text
official_docs
```

Vendor-, standards-, language-, or project-authoritative material.

Examples include:

* AzerothCore documentation and source
* Blizzard interface and API material
* CMake documentation
* Boost documentation
* Git and GitHub documentation
* database documentation
* Docker and Kubernetes documentation
* cloud-provider documentation
* programming-language references
* standards and formal specifications

Official material represents what an upstream project, vendor, or standards body formally documents or implements.

### Community Documentation

Identifier:

```text
community_docs
```

Community-maintained technical references, tutorials, examples, discussions, and independently maintained documentation.

Examples include:

* Warcraft Wiki and Wowpedia
* addon-development tutorials
* community-maintained API references
* technical articles
* issue discussions
* troubleshooting guides
* representative open-source projects
* protocol and file-format research
* implementation examples

Community material can provide practical details, edge cases, undocumented behavior, and real-world examples. It remains separately labeled because it does not carry the same authority as an official source.

### Internal Work

Identifier:

```text
internal_work
```

Engineering knowledge created through blAIne projects and related development work.

Examples include:

* architecture decisions
* system specifications
* validated fixes
* source-code documentation
* test and validation reports
* troubleshooting records
* deployment procedures
* operational runbooks
* project handoffs
* experiments
* known limitations
* implementation notes
* local infrastructure documentation

Internal material is not automatically authoritative. It must preserve its project context, creation date, source identity, validation state, and revision history.

## Provenance and Authority

The corpus does not flatten all information into anonymous text.

Every registered source, normalized document, chunk, embedding record, and retrieval result is intended to retain metadata such as:

* source identifier;
* source name;
* provenance class;
* authority level;
* upstream publisher or project;
* source URL;
* version, release, tag, or commit;
* acquisition date;
* license;
* source path;
* document title;
* heading or symbol path;
* language;
* parser version;
* chunking profile;
* content hash;
* validation status.

This allows the retrieval system to distinguish between:

* official project documentation;
* raw source implementation;
* community guidance;
* and validated internal engineering records.

The default combined retrieval policy will generally prefer:

```text
official_docs
→ validated internal_work
→ community_docs
```

This ordering is not absolute.

For example, a validated internal deployment procedure may be more relevant to a local environment than a generic official installation guide. Conflicting sources must remain independently identifiable rather than being silently merged.

## Domain Organization

The Engineering RAG Corpus is organized into engineering domains.

A domain may contain multiple upstream projects, technologies, providers, source types, and provenance classes.

Planned domains include:

* World of Warcraft and AzerothCore engineering
* cloud infrastructure
* programming languages
* build systems
* databases
* containers and orchestration
* CI/CD
* infrastructure as code
* observability
* security
* systems engineering
* hardware diagnostics
* AI and RAG engineering

Sources remain independently registered inside each domain.

For example, a future cloud domain may include:

```text
cloud
├── aws
├── azure
├── gcp
├── cloudflare
├── other_providers
├── shared_concepts
├── multicloud
└── internal_work
```

AWS, Azure, and Google Cloud documentation would remain separate sources even when they describe equivalent concepts.

## Initial Domain

The first domain is:

```text
World of Warcraft and AzerothCore engineering
```

The complete domain is expected to grow to include:

* official AzerothCore documentation;
* raw AzerothCore C++ source;
* AzerothCore SQL schemas and migrations;
* configuration files;
* modules and scripts;
* generated Doxygen reference material;
* Blizzard UI and FrameXML;
* WoW API documentation;
* Lua, XML, and TOC material;
* addon-development references;
* representative addon repositories;
* community-maintained technical material;
* validated internal AzerothCore and WoW engineering work.

Supporting engineering sources may include:

* C and C++;
* CMake;
* Boost;
* Git and GitHub;
* MySQL or MariaDB;
* SQL;
* Linux;
* shell;
* YAML;
* Docker and Docker Compose;
* build, debugging, deployment, and operational tooling.

These sources will not all be ingested simultaneously. Each source must first pass its own registration, normalization, chunking, retrieval, and validation gates.

## Current Pilot Source

The current one-source pilot uses the official AzerothCore Wiki.

```text
Source ID: azerothcore_wiki_official
Provenance: official_docs
Authority: official_project
Upstream: https://github.com/azerothcore/wiki.git
Branch at acquisition: master
Pinned commit: 7d540fc7e683c3bf34a2f465789f1b3df268b609
License: MIT
```

The source snapshot is stored outside the Git repository at:

```text
/run/media/deck/blAIne-476GB-SAM/blAIne/rag-data/engineering-rag/
└── sources/
    └── official_docs/
        └── azerothcore_wiki_official/
            └── snapshot/
```

The source contains:

* 1,054 inventoried files;
* 912 primary Markdown pages under `docs/`;
* approximately equal English and Spanish coverage;
* fenced code;
* technical tables;
* YAML front matter;
* redirect metadata;
* Liquid includes;
* raw HTML;
* command references;
* configuration documentation;
* database documentation;
* CMake and build guidance;
* troubleshooting procedures;
* oversized reference pages;
* small placeholders;
* repeated navigation content.

The snapshot is immutable and remains separate from normalized documents, chunks, embeddings, and indexes.

## Corpus Lifecycle

Every source passes through a controlled lifecycle:

```text
Inventory
→ Acquire
→ Verify
→ Freeze
→ Normalize
→ Chunk
→ Embed
→ Index
→ Retrieve
→ Evaluate
→ Validate
→ Promote
```

### Inventory

Determine exactly what a source contains.

Inventory records may include:

* file count;
* byte count;
* file formats;
* Git metadata;
* version or commit;
* shallow-clone status;
* missing submodules;
* missing Git LFS data;
* generated content;
* duplicates;
* licensing;
* unreadable files;
* inclusion and exclusion candidates.

### Acquire

Obtain the source from an authoritative upstream location or recover it from an existing collection.

The acquisition should resolve to an exact version, release, tag, or commit whenever possible.

### Verify

Validate source integrity and completeness.

Verification may include:

* `git fsck`;
* exact commit resolution;
* worktree cleanliness;
* complete branch history;
* submodule status;
* Git LFS status;
* archive integrity;
* zero-byte detection;
* content hashes;
* licensing review.

### Freeze

Preserve the accepted source as an immutable snapshot.

The source snapshot is never rewritten by normalization or ingestion.

### Normalize

Convert supported source files into deterministic normalized documents while preserving meaningful structure.

Normalization may handle:

* Markdown;
* HTML;
* C and C++;
* Lua;
* XML;
* SQL;
* CMake;
* YAML;
* shell scripts;
* configuration files;
* Doxygen pages;
* internal reports.

Normalization is not plain-text extraction. It must preserve structures such as:

* headings;
* fenced code;
* tables;
* lists;
* command syntax;
* identifiers;
* aliases;
* links;
* include relationships;
* source paths;
* language;
* document hierarchy.

### Chunk

Divide normalized documents into retrieval units using source-aware and document-aware rules.

The project deliberately rejects a single blind fixed-size splitter for every content type.

Examples:

* documentation is divided by headings and semantic sections;
* command references are divided by command or command family;
* C++ is divided by classes, functions, methods, and registration blocks;
* SQL is divided by schema entity, statement, migration, or patch group;
* tables retain their headers and complete rows;
* code remains attached to its explanation;
* configuration files are divided by coherent sections or key groups;
* Lua, XML, and TOC material preserves addon relationships.

### Embed

Convert approved chunks into vector representations.

Embedding does not train the embedding model on the corpus. It encodes corpus chunks into the model’s existing vector space for similarity retrieval.

### Index

Store chunks, vectors, lexical terms, and metadata in searchable indexes.

### Retrieve

Return evidence for a query without assuming that the returned evidence is sufficient.

### Evaluate

Measure retrieval against manually reviewed engineering questions.

### Validate

Confirm that source, document, chunk, embedding, index, and retrieval invariants hold.

### Promote

A source is promoted only after retrieval quality and evidence sufficiency are demonstrated.

## Core Operational Principle

```text
Ingestion success is not retrieval success.
```

A source is not accepted merely because:

* files were parsed;
* chunks were generated;
* embeddings were created;
* or a vector database contains points.

A source is accepted only when the system can retrieve correct, sufficient, source-grounded evidence for real engineering questions while rejecting unsupported questions.

## Current Normalization Implementation

The official AzerothCore Wiki pilot uses:

```text
Parser: azerothcore_wiki_markdown
Version: 1.0.0
```

The parser currently supports:

* strict UTF-8 decoding;
* YAML-front-matter extraction;
* deterministic document identifiers;
* deterministic content hashes;
* heading preservation;
* exact fenced-code preservation;
* structured tables;
* lists and callouts;
* link metadata;
* redirect aliases;
* guarded Liquid-include resolution;
* include provenance;
* raw HTML retention when technically meaningful;
* repeated navigation removal;
* bilingual document isolation;
* translation-pair metadata;
* exclusion of empty redirects, placeholders, and navigation-only pages.

## Current Chunking Decision

Three candidate strategies were tested.

### Profile A — Structural Reference

Used for:

* oversized command pages;
* reference documents;
* database-schema documentation;
* large structured tables.

Characteristics:

* heading-aware;
* smaller semantic units;
* command-family and table-row preservation;
* hard size limits;
* source and heading context retained.

### Profile B — Structural Narrative

Used for:

* how-to documentation;
* configuration guides;
* build instructions;
* troubleshooting material;
* narrative technical explanations.

Characteristics:

* heading-aware;
* medium-sized semantic sections;
* paragraph- and code-aware splitting;
* source and heading context retained.

### Profile C — Fixed-Token Baseline

Profile C used fixed token windows with overlap.

It was rejected for production use because it:

* split technical tables;
* divided command families;
* damaged heading context;
* produced weaker structural evidence;
* mixed content that should remain separate.

The approved strategy assigns exactly one structural profile to each document.

## Embedding Configuration

The pilot currently uses a local Ollama installation.

```text
Runtime: Ollama 0.32.1
Endpoint: http://127.0.0.1:11434/api/embed
Model: qwen3-embedding:0.6b
Model digest: ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d
Embedding dimensions: 1024
Vector normalization: L2-normalized
```

The model was selected as the pilot embedding candidate because it supports both technical prose and code-oriented retrieval within the resource limits of the initial development system.

The pilot model remains versioned and replaceable. A future model change would require a new embedding build and retrieval evaluation.

## Retrieval Architecture

The current pilot evaluates three retrieval channels.

### Dense Retrieval

Uses semantic similarity between query and chunk embeddings.

Dense retrieval is useful for conceptual questions and differently worded descriptions of the same topic.

### Lexical Retrieval

Uses BM25-style term matching.

Lexical retrieval is a required first-class component because engineering questions frequently contain exact identifiers such as:

* commands;
* API names;
* C++ symbols;
* SQL tables;
* SQL columns;
* configuration keys;
* CMake options;
* environment variables;
* file paths;
* filenames.

### Hybrid Retrieval

Combines dense and lexical rankings using reciprocal-rank fusion.

The current pilot also evaluates:

* title matching;
* heading matching;
* identifier detection;
* token coverage;
* rare-token coverage;
* language compatibility;
* retrieval-channel agreement;
* score margins;
* structural completeness;
* bounded neighboring-chunk expansion.

## Pilot Retrieval Results

A 12-document representative sample was used for initial chunk-definition evaluation.

The sample covered:

* ordinary documentation;
* fenced code;
* technical tables;
* YAML front matter;
* redirects;
* Liquid includes;
* bilingual pairs;
* oversized command references;
* placeholders;
* raw HTML;
* configuration;
* database material;
* CMake;
* troubleshooting.

Key results included:

* lexical Recall@5: `1.000`;
* Profile A hybrid Recall@1: `0.917`;
* Profile A hybrid Recall@5: `0.958`;
* Profile A hybrid MRR: `0.930`;
* Profile A hybrid exact-identifier Recall@1: `1.000`.

The fixed-token baseline achieved competitive document recall but was rejected because it damaged structural context.

## Evidence Sufficiency and Abstention

Search systems return nearest results even when no correct answer exists.

The Engineering RAG Corpus therefore requires an explicit decision layer that distinguishes:

```text
supported
insufficient_evidence
no_relevant_evidence
```

A result is not considered supported merely because it is the highest-ranked chunk.

Evidence-sufficiency analysis may consider:

* dense similarity;
* lexical score;
* hybrid score;
* retrieval-channel agreement;
* exact-identifier match;
* heading match;
* query-token coverage;
* rare-token coverage;
* requested-relation coverage;
* structural completeness;
* numeric-value agreement;
* neighboring evidence;
* conflicting results;
* generic keyword overlap.

## Abstention Evaluation Version 1

The first abstention evaluation used 64 manually reviewed questions:

* 32 answerable;
* 32 intentionally unanswerable.

The locked holdout results included:

* Recall@5: `1.000`;
* unanswerable rejection: `1.000`;
* false-evidence acceptance: `0.071429`;
* false-identifier rejection: `1.000`;
* accepted-evidence sufficiency: `0.928571`.

The acceptance gate failed because:

* exact existing-identifier acceptance was only `0.714286`;
* two complete valid results were falsely rejected;
* table-row relation binding was too literal;
* command-family evidence needed stronger structural interpretation;
* alternative-valid evidence was not labeled explicitly enough.

These failures were accepted as valid blockers. Full-source ingestion was not started.

## Current Acceptance Gate

The next milestone is abstention calibration version 2.

It must improve:

* table-row relation binding;
* command-signature completeness;
* identifier typing;
* alternative-valid evidence classification;
* neighboring-context controls;
* exact-identifier acceptance.

The exposed v1 holdout cannot be reused for final acceptance.

A new development set and a fresh sealed holdout must be created. Thresholds must be frozen before the new holdout is opened.

Full official-wiki ingestion remains blocked until this evaluation passes.

## Evaluation Hierarchy

Evaluation occurs at multiple levels.

### Source Evaluation

Proves that one specific source can be normalized, chunked, retrieved, and rejected correctly.

### Source-Type Regression Evaluation

Confirms that a validated parser and chunking profile remain effective for later sources of the same structural type.

### Multi-Source Integration Evaluation

Tests retrieval after several sources coexist.

This includes:

* duplicate information;
* conflicting guidance;
* version differences;
* authority ranking;
* cross-source retrieval;
* alternative-valid evidence.

### Domain Acceptance Evaluation

Tests the complete engineering domain after official, community, and internal sources are present.

For the WoW/AzerothCore domain, this will include questions requiring:

* documentation;
* raw source;
* SQL;
* configuration;
* addon APIs;
* community examples;
* internal validated work;
* or evidence from multiple sources.

### Continuing Regression Evaluation

Runs after source updates, parser changes, embedding-model changes, ranking changes, and new domain additions.

## Validation Requirements

A build must verify:

* source snapshots remain unchanged;
* source manifests are complete;
* every normalized document maps to a source record;
* every chunk maps to a normalized document;
* document and chunk identifiers are deterministic;
* empty chunks are rejected;
* duplicate identifiers are rejected;
* embedding dimensions are consistent;
* successful chunk, embedding, and vector counts agree;
* stale index entries are removed or replaced;
* changed files are detected;
* parser failures are recorded;
* embedding failures are recorded;
* one malformed file does not terminate the complete build;
* retrieval exposes supporting evidence and provenance;
* unsupported questions are rejected.

## Repository and Data Separation

The Git repository contains the definitions, code, governance records, and tests used to build the corpus.

The external data area contains large source and generated artifacts.

### Git Repository

Local repository:

```text
/run/media/deck/blAIne-476GB-SAM/blAIne/repositories/engineering-rag-corpus
```

GitHub repository:

```text
https://github.com/blainesmith33/engineering-rag-corpus
```

Expected repository content includes:

* source registries;
* manifests;
* schemas;
* acquisition records;
* normalization code;
* chunking profiles;
* embedding configuration;
* retrieval logic;
* abstention logic;
* evaluation datasets;
* validation tools;
* tests;
* architecture decisions;
* documentation;
* compact reports.

### External Data Root

```text
/run/media/deck/blAIne-476GB-SAM/blAIne/rag-data/engineering-rag
```

Externally stored material includes:

* frozen third-party source snapshots;
* normalized documents;
* generated chunks;
* embeddings;
* temporary evaluation artifacts;
* vector-database storage;
* model-independent index data;
* large processing reports;
* runtime logs.

### Model Storage

The current local Ollama model storage is:

```text
/home/deck/.local/share/ollama/models
```

Model files are not committed to the repository.

## Current Repository Structure

The current repository includes structures such as:

```text
engineering-rag-corpus/
├── README.md
├── .gitignore
├── config/
├── docs/
├── reports/
├── schemas/
├── scripts/
├── sources/
└── tests/
```

The structure will continue to evolve as additional source types and domain pipelines are implemented.

Generated corpus data must remain outside normal Git history.

## Resource Constraints

The initial implementation is being developed on a Steam Deck-class system.

The pipeline must use conservative and configurable limits for:

* parser concurrency;
* worker count;
* embedding batch size;
* indexing batch size;
* maximum document size;
* maximum chunk size;
* temporary storage;
* logging verbosity;
* vector-memory use.

Large inputs should be streamed or processed incrementally.

All major stages should be:

* resumable;
* independently runnable;
* idempotent where practical;
* manifest-driven;
* content-hash aware;
* capable of processing one source independently.

## Codex Integration

A major project goal is to make the corpus directly available to Codex.

The intended integration will provide read-only tools such as:

```text
engineering_rag_search
engineering_rag_read_chunk
engineering_rag_expand_context
engineering_rag_list_sources
engineering_rag_source_status
```

Codex should use the corpus when working on:

* AzerothCore modules;
* WoW addons;
* build and CMake problems;
* database changes;
* server configuration;
* deployment;
* troubleshooting;
* architecture;
* project-specific operational procedures.

A typical workflow will be:

```text
Inspect active source repository
+ retrieve relevant official documentation
+ retrieve exact implementation evidence
+ retrieve validated internal work
→ reason over combined evidence
→ implement
→ compile and test
```

Codex may also use failed retrieval evaluations to improve:

* parsers;
* normalization rules;
* chunk definitions;
* metadata;
* lexical retrieval;
* hybrid ranking;
* neighbor expansion;
* evidence-sufficiency decisions.

Experimental changes must remain isolated until they outperform the approved baseline and pass human review.

## Roadmap

### Phase 1 — Recovered Corpus Audit

Completed:

* inspected the recovered acquisition collection;
* identified direct WoW/AzerothCore material;
* identified supporting AzerothCore dependencies;
* classified broader engineering sources;
* separated direct, dependency, supporting, and unrelated material;
* identified missing official, community, and internal coverage.

### Phase 2 — First Source Acquisition

Completed:

* acquired the official AzerothCore Wiki;
* pinned it to an exact commit;
* recorded provenance and licensing;
* created reproducible inventories;
* preserved an immutable external snapshot;
* registered the source in the repository.

### Phase 3 — Chunking and Retrieval Pilot

Completed:

* implemented deterministic Markdown normalization;
* tested structural and fixed-token chunking;
* selected document-specific structural profiles;
* installed and verified a local embedding model;
* implemented lexical, dense, and hybrid retrieval experiments;
* created manually reviewed evaluation questions;
* measured retrieval performance.

### Phase 4 — Abstention Calibration

In progress:

* abstention v1 completed;
* unanswerable and nonexistent-identifier rejection demonstrated;
* structured evidence weaknesses identified;
* abstention v2 pending;
* full-source ingestion blocked until the gate passes.

### Phase 5 — Complete Official Wiki Ingestion

Pending:

* normalize all accepted wiki pages;
* apply approved structural profiles;
* generate complete embeddings;
* create an isolated full-source index;
* recalibrate score distributions;
* run full-source retrieval evaluation;
* validate deterministic rebuild behavior.

### Phase 6 — Raw AzerothCore Source

Pending:

* acquire and pin raw AzerothCore source;
* register C++, SQL, CMake, configuration, and module material;
* implement syntax-aware chunking;
* test exact symbols and implementation retrieval;
* integrate documentation and source-code evidence.

### Phase 7 — WoW/AzerothCore Domain Expansion

Pending:

* recovered AzerothCore Doxygen;
* Blizzard UI and API material;
* Lua, XML, and TOC references;
* addon-development sources;
* selected community documentation;
* representative addon repositories;
* validated internal engineering work.

### Phase 8 — Domain Integration Evaluation

Pending:

* cross-source retrieval;
* official/community/internal authority ranking;
* duplicate and conflict handling;
* version-aware retrieval;
* multi-source evidence;
* domain-wide abstention recalibration;
* Codex integration.

### Phase 9 — Broader Engineering Domains

Potential domains include:

* cloud infrastructure;
* C and C++;
* Python;
* JavaScript and TypeScript;
* CMake;
* Boost;
* Git and GitHub;
* shell;
* PowerShell;
* YAML;
* SQL and database systems;
* Docker and Kubernetes;
* CI/CD;
* Terraform;
* observability;
* software architecture;
* security;
* AI and RAG engineering.

## Governance Principles

The project is guided by:

* provenance;
* transparency;
* reproducibility;
* deterministic processing;
* authority awareness;
* source separation;
* explicit validation;
* auditable operational control;
* human approval before promotion;
* honest abstention when evidence is insufficient.

The system must preserve the distinction between:

* what a source says;
* who produced it;
* which version it represents;
* how it was processed;
* how strongly it supports a query;
* and whether the evidence has been validated.

## Licensing

The repository’s own license has not yet been finalized.

Third-party material remains subject to its original license and must not be redistributed merely because it is registered, normalized, embedded, or indexed by this project.

Every source must record:

* upstream license;
* redistribution status;
* attribution requirements;
* source version;
* acquisition method;
* local storage boundary.

The official AzerothCore Wiki pilot source is registered as MIT-licensed. Its existing copyright and attribution notices must be preserved where required.

## Contributing

Contribution procedures will be finalized after the first source passes full ingestion and retrieval acceptance.

Until then, changes should preserve:

* source provenance;
* deterministic identifiers;
* repository/data separation;
* reproducible processing;
* fixed evaluation sets;
* sealed holdout integrity;
* explicit validation;
* clear authority classification;
* human-controlled promotion.

## Current Next Step

Implement abstention calibration version 2.

The next evaluation must:

* improve structured table-row interpretation;
* improve command-signature evidence;
* classify identifiers by type;
* distinguish valid alternative evidence from related but insufficient evidence;
* create a new sealed holdout;
* freeze configuration before opening the holdout;
* preserve perfect rejection of nonexistent identifiers;
* pass every acceptance threshold before full-source ingestion.

The complete official AzerothCore Wiki must not be embedded or indexed as a production source until that gate passes.
