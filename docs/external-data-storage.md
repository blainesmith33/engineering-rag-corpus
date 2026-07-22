# External data storage boundary

The Engineering RAG Git repository contains only compact, reviewable registrations, schemas, policies, and reports. Source snapshots, exhaustive file inventories, and any future generated corpus data live beneath:

`/run/media/deck/blAIne-476GB-SAM/blAIne/rag-data/engineering-rag/`

For `azerothcore_wiki_official`, the layout is:

```text
sources/official_docs/azerothcore_wiki_official/
├── snapshot/   # full Git clone detached at the registered commit
├── manifests/  # exhaustive inventories and source/acquisition metadata
└── reports/    # structural and acquisition reports
```

The `snapshot/` directory is immutable evidence for the registered commit. Later processing must read from it and write to a separate generated-output path. It must never rewrite, normalize in place, or add build output to the snapshot.

Registration records use absolute snapshot paths because the external root is explicitly configured for this installation. A future portability layer may introduce a named data-root variable, but it must continue to resolve the same pinned source identity and inventory hash.
