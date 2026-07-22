# Engineering RAG Corpus

A provenance-aware engineering knowledge corpus and retrieval-augmented generation pipeline built from official documentation, community resources, and validated internal engineering work.

## Project Status

**Early development — source audit and acquisition phase**

The initial pilot domain focuses on World of Warcraft and AzerothCore engineering. The pilot will establish the ingestion, normalization, chunking, embedding, indexing, retrieval, and evaluation methods used when the broader engineering corpus is added.

No generated corpus, embedding, or vector-database artifacts should be considered production-ready yet.

## Purpose

The Engineering RAG Corpus is intended to provide reliable, source-grounded technical retrieval across a broad engineering knowledge base.

The system is designed to:

* Preserve exact source provenance.
* Separate authoritative, community, and internal knowledge.
* Use document-aware and source-aware chunking.
* Support deterministic, repeatable corpus builds.
* Produce auditable citations and retrieval evidence.
* Evaluate retrieval quality before expanding the corpus.
* Allow individual sources to be rebuilt without rebuilding everything.
* Avoid treating all technical content as equally authoritative.

## Knowledge Classes

Every source is assigned to one of three provenance classes.

### Official Documentation

Vendor-, standards-, language-, or project-authoritative material.

Examples include:

* AzerothCore documentation and source
* Blizzard interface and API material
* CMake documentation
* Boost documentation
* Git and GitHub documentation
* Language and framework documentation
* Database documentation
* Standards and formal specifications

Identifier:

```text
official_docs
```

### Community Documentation

Community-maintained technical references, tutorials, examples, discussions, and independently maintained documentation.

Examples include:

* Warcraft Wiki and Wowpedia
* Addon-development tutorials
* Community-maintained API references
* Technical articles
* Issue discussions
* Representative open-source addon repositories
* Community troubleshooting guides

Identifier:

```text
community_docs
```

### Internal Work

Validated engineering material produced through blAIne projects and related development work.

Examples include:

* Architecture decisions
* Project specifications
* Source-code documentation
* Test and validation reports
* Troubleshooting records
* Operational procedures
* System handoffs
* Engineering experiments
* Known fixes
* Implementation notes

Identifier:

```text
internal_work
```

Internal material is not automatically authoritative. It must retain validation state, project context, creation date, and source identity.

## Initial Pilot

The first pilot domain is:

```text
World of Warcraft and AzerothCore engineering
```

The pilot is expected to include a controlled selection of:

* AzerothCore documentation
* AzerothCore source and SQL
* AzerothCore build and runtime dependencies
* Blizzard UI and API material
* WoW addon-development references
* Lua, XML, and TOC material
* Selected community documentation
* Validated internal WoW and AzerothCore engineering records

Supporting engineering sources may include:

* C++
* CMake
* Boost
* SQL
* MySQL or MariaDB
* Git and GitHub
* Linux
* Shell
* YAML
* Docker and Docker Compose
* Build, debugging, and operational tooling

The initial pilot will use a limited source set. The complete recovered corpus will not be ingested until the pipeline has demonstrated reliable retrieval.

## Pipeline

The planned corpus lifecycle is:

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

Each stage should be:

* Independently runnable
* Resumable
* Idempotent where practical
* Bounded for memory safety
* Driven by manifests
* Traceable through deterministic identifiers
* Capable of processing one source independently

## Source Registration

Every source should have a registry record containing, when available:

* Stable source identifier
* Source name
* Provenance class
* Authority level
* Upstream publisher or project
* Source URL
* Version, release, tag, or commit
* Acquisition date
* License
* Local source path
* File count
* Byte count
* Inventory hash
* Inclusion status
* Parser assignment
* Chunking profile
* Validation status

No source should be embedded before it has been inventoried and registered.

## Chunking Strategy

The project will not use a single blind text splitter for all content.

Chunking profiles will be designed for specific document types, including:

* Structured documentation
* API references
* C and C++ source
* CMake
* SQL
* Lua
* XML
* TOC files
* YAML
* Shell scripts
* Configuration files
* Doxygen HTML
* Community tutorials
* Internal reports and troubleshooting records

Candidate chunk definitions will be tested against representative retrieval questions before the final profile is selected.

## Retrieval and Authority

Retrieval must expose the source evidence used to answer a query.

Expected filters include:

* Provenance class
* Source identifier
* Authority level
* Project
* Document type
* Technology
* Version
* Source path

The default combined retrieval policy should generally prefer:

```text
official_docs
→ validated internal_work
→ community_docs
```

This ordering is not absolute. For project-specific operational questions, validated internal material may be more relevant than general official documentation.

Conflicting sources must remain independently identifiable.

## Repository and Data Separation

This Git repository contains the definitions and tooling used to build and evaluate the corpus.

Expected repository contents include:

* Source registries
* Manifests
* Schemas
* Acquisition tools
* Normalization code
* Chunking profiles
* Embedding configuration
* Vector-store integration
* Retrieval tools
* Evaluation datasets
* Validation tools
* Tests
* Architecture decisions
* Documentation

Large generated or third-party artifacts should not normally be committed to Git.

Excluded or externally stored material includes:

* Raw third-party source trees
* Normalized document output
* Generated chunks
* Embedding vectors
* Vector-database storage
* Model files
* Build output
* Temporary processing data
* Large logs
* Large source archives

## Planned Repository Structure

```text
engineering-rag-corpus/
├── README.md
├── LICENSE
├── .gitignore
├── config/
├── docs/
│   ├── architecture/
│   ├── decisions/
│   └── reports/
├── schemas/
├── sources/
│   ├── registries/
│   └── manifests/
├── pipeline/
│   ├── inventory/
│   ├── normalize/
│   ├── chunk/
│   ├── embed/
│   ├── index/
│   ├── retrieve/
│   ├── evaluate/
│   └── validate/
├── evaluations/
├── tests/
└── tools/
```

The final structure may change as the pilot implementation establishes actual requirements.

## Validation Requirements

A corpus build should verify:

* Source manifests are complete.
* Source files remain unchanged.
* Normalized documents map to exact source records.
* Chunks map to exact documents and source locations.
* Chunk identifiers are deterministic.
* Empty chunks are rejected.
* Duplicate identifiers are rejected.
* Embedding dimensions are consistent.
* Successful chunk, embedding, and vector-point counts agree.
* Stale vector points are removed or replaced.
* Failed files are recorded without terminating the entire build.
* Unanswerable questions do not produce unsupported answers.
* Retrieval results expose supporting text and provenance.

## Evaluation

The pilot evaluation suite should include:

* Exact API-name retrieval
* Function and symbol lookup
* Configuration lookup
* SQL lookup
* Conceptual engineering questions
* Version-specific questions
* Ambiguous terminology
* Conflicting authority levels
* Source-filtered retrieval
* Questions not answered by the corpus

Expected measurements include:

* Recall at 1, 3, 5, and 10
* Mean reciprocal rank
* Expected-source retrieval rate
* Expected-section retrieval rate
* Retrieval latency
* Unsupported-answer rate
* Dense versus lexical or hybrid retrieval performance

## Resource Constraints

The initial implementation is being developed on a Steam Deck-class system.

The pipeline must therefore use conservative defaults for:

* Worker count
* Parser concurrency
* Embedding batch size
* Indexing batch size
* Maximum document size
* Maximum chunk size
* Temporary storage
* Logging verbosity

Large inputs should be streamed or processed incrementally. A single malformed file must not terminate the complete build.

## Roadmap

### Phase 1 — Audit and Acquisition

* Audit recovered official sources
* Identify AzerothCore dependencies
* Acquire missing official sources
* Acquire selected community sources
* Identify and register validated internal work
* Record versions, licenses, provenance, and hashes

### Phase 2 — WoW/AzerothCore Pilot

* Select the pilot source set
* Freeze source snapshots
* Implement normalization
* Define and test chunking profiles
* Select a local embedding model
* Build the pilot vector collection
* Implement retrieval
* Create a manually verified evaluation set
* Validate deterministic rebuilds

### Phase 3 — Pilot Expansion

* Add additional WoW and AzerothCore sources individually
* Add authority-aware ranking
* Add lexical or hybrid retrieval
* Measure cross-source retrieval quality
* Improve source conflict handling

### Phase 4 — Broader Engineering Corpus

Potential future domains include:

* C and C++
* Python
* JavaScript and TypeScript
* CMake
* Boost
* Git and GitHub
* Shell
* PowerShell
* YAML
* SQL and database systems
* Docker and Kubernetes
* CI/CD
* Terraform
* Cloud infrastructure
* Software architecture
* RAG engineering

## Governance Principles

The project is guided by:

* Transparency
* Honesty
* Agency
* Provenance
* Reproducibility
* Deterministic governance
* Auditable operational control

The corpus must preserve the distinction between what a source says, who produced it, which version it represents, and how confidently it should be used.

## Licensing

This repository’s license has not yet been finalized.

Third-party source material remains subject to its original license and should not be redistributed merely because it is referenced, processed, or indexed by this project.

Every acquired source must have its licensing and redistribution status recorded before inclusion.

## Contributing

Contribution procedures will be defined after the pilot architecture and source-registration process are stable.

Until then, changes should preserve:

* Source provenance
* Deterministic identifiers
* Repository/data separation
* Reproducible processing
* Explicit validation
* Clear authority classification
