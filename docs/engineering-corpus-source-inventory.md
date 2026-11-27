# Engineering_Corpus: accumulated engineering source collection

## Purpose and relationship to Engineering RAG

`Engineering_Corpus` is the accumulated engineering source-material collection intended to form a foundational knowledge base for the Engineering RAG project.

The collection predates the `engineering-rag-corpus` software repository. It is not a second copy of that software repository, and it is not an unrelated external dependency. It is the body of engineering material that the RAG software is being developed to organize, process, index, and retrieve.

The source collection is currently stored separately from the Git repository:

```text
/home/deck/Old-Drive-Import/Additional-Top-Level/Project_repositories/Engineering_Corpus
```

The source files have not been copied into this Git repository by this document's creation. This record makes the collection visible in the project's documentation and establishes its intended relationship to the software.

## Current filesystem inventory

The latest recorded filesystem scan reported:

| Measure | Recorded value |
|---|---:|
| Files | 907,585 |
| Directories | 152,422 |
| Total file bytes | 24,160,809,076 |
| Approximate decimal size | 24.16 GB |
| Metadata errors during scan | 2 |

The two metadata errors mean the scan could not obtain all requested metadata for two filesystem entries. The figures above are the scan's reported results; they should not be interpreted as a content-level validation or proof that every file is readable.

## Collection scope

The collection is a broad, multi-domain engineering reference base. The following paths were identified in its top-level collection inventory. They are listed as observed collection names/paths, not as a claim that every item has already been normalized, validated, or ingested.

### Search, information retrieval, and RAG

- `anserini`
- `beir`
- `elasticsearch`
- `faiss`
- `langchain`
- `lucene`
- `pyserini`
- `qdrant`
- `whoosh`
- `xapian-core`

### Machine learning, model tooling, and GPU computing

- `axolotl`
- `cuda-docs`
- `dcgm`
- `llama.cpp/index`
- `nccl`
- `open-gpu-kernel-modules`
- `peft`
- `sentence-transformers`
- `transformers`

### Cloud, infrastructure, deployment, and operations

- `ansible`
- `awsdocs`
- `azure_docs`
- `docker_docs`
- `gcp_python_docs_samples`
- `grafana`
- `helm`
- `jenkins_docs`
- `kubernetes`
- `nginx`
- `prometheus`
- `terraform`

### Programming languages, libraries, and build systems

- `bash`
- `bash_hackers_wiki`
- `boost`
- `cmake`
- `cppreference_doc/html`
- `doxygen`
- `dotnet_docs`
- `go_docs`
- `gradle`
- `maven`
- `mdn_content`
- `openjdk_jdk`
- `php-src`
- `python_cpython`
- `ruby`
- `rust`
- `typescript_website`

### Operating systems, hardware, storage, and systems engineering

- `dmidecode`
- `ethtool`
- `fio`
- `fwupd`
- `hwloc`
- `intel-pcm/sdm`
- `linux`
- `lm-sensors`
- `nvme-cli`
- `pciutils`
- `smartmontools`
- `stress-ng`
- `usbutils`
- `util-linux`

### Databases and data services

- `mysql-server`
- `postgresql`
- `redis`

### Version control and collaboration platforms

- `git_docs`
- `github_docs_actions`
- `gitlab_docs/current`

### General technical documentation

- `tldp`

This list is a current inventory of identified collection paths, not an exhaustive semantic catalog of every document or subdirectory. Some collections contain source-code repositories, some contain generated or rendered documentation, and others contain documentation, examples, tools, or supporting assets.

## Recorded file-type profile

The filesystem scan also recorded these high-frequency file extensions:

| Extension | File count |
|---|---:|
| `.java` | 103,136 |
| `.c` | 86,779 |
| `.md` | 74,687 |
| `.h` | 71,891 |
| `.png` | 54,747 |
| `.rs` | 39,045 |
| `.hpp` | 36,292 |

Files without an extension were also among the high-frequency categories, but their count is not recorded in the available summary. This table is a partial profile, not a complete extension distribution.

## Relationship to the current Git repository

The current `engineering-rag-corpus` repository contains a bounded, source-specific AzerothCore Wiki pilot, including source registration, acquisition records, processing code, evaluation configuration, and tests.

`Engineering_Corpus` is a separate, much broader accumulated engineering collection. It is not currently listed as a registered source in `sources/registry.json`. This document records its existence and scope; it does not claim that the collection has been acquired into the RAG data root, registered, normalized, chunked, embedded, indexed, or made retrievable.

The intended project relationship is:

1. Preserve `Engineering_Corpus` as a foundational source collection.
2. Bring it under the Engineering RAG project's source-management and provenance model.
3. Define and record its source boundaries and processing requirements.
4. Develop and validate ingestion against the actual material, preserving source identity and structure.
5. Make processed material available to retrieval only after the relevant validation and promotion requirements are met.

The source collection is part of the intended Engineering RAG system even while its files remain outside the Git repository. The Git repository documents and implements the software and metadata that manage the data; it does not need to contain a 24 GB copy of the source files.

## Inventory limitations and follow-up

This document records the available filesystem scan and identified collection paths. It is not a replacement for a future machine-readable manifest. In particular:

- The two metadata errors need to be resolved or explicitly accounted for in a later inventory.
- The extension profile is partial.
- The collection paths have not yet been converted into individual source records.
- The contents have not been comprehensively classified by document type, version, language, license, or provenance.
- No ingestion or retrieval coverage is claimed.

Future inventory updates should preserve the original collection paths and distinguish observed facts from inferred classifications. The original source collection should remain intact until any subsequent copy or data-root migration has been verified.
