# Engineering RAG Corpus Registry

This repository stores schemas, source registrations, acquisition records, and compact policy/report documents. Raw snapshots and generated corpus payloads are intentionally external to Git.

The first registered source is `azerothcore_wiki_official`, pinned at commit `7d540fc7e683c3bf34a2f465789f1b3df268b609`. Its snapshot and complete per-file manifests are under:

`/run/media/deck/blAIne-476GB-SAM/blAIne/rag-data/engineering-rag/sources/official_docs/azerothcore_wiki_official/`

The first bounded normalization/chunk-definition pilot is implemented by
`scripts/azerothcore_wiki_chunking.py` and specified in
`docs/azerothcore-wiki-normalization-chunking.md`. Generated sample artifacts
remain external under `experiments/azerothcore_wiki_chunking_v1/` in the data
root. The pilot never creates a production vector collection or triggers
full-source ingestion.
