# AzerothCore Wiki evidence sufficiency and abstention

## Scope

This component calibrates explicit evidence decisions for the bounded
`azerothcore_wiki_official` pilot at source commit
`7d540fc7e683c3bf34a2f465789f1b3df268b609`. It reads the existing sample
chunks and embeddings from `azerothcore_wiki_chunking_v1`: Profile A for the
oversized command/reference and database-schema documents, and Profile B for
the narrative, configuration, build, and troubleshooting documents. Profile C
is excluded. The implementation does not normalize or embed additional wiki
pages and does not synthesize answers.

The three decisions are:

- `supported`: the retrieved structural evidence contains the requested fact
  and passes the frozen score, identifier, relation, language, and completeness
  checks.
- `insufficient_evidence`: a relevant document or section was found, but the
  passage is incomplete, conflicting, or lacks a required identifier, number,
  or requested relation.
- `no_relevant_evidence`: the best result does not clear the relevance floor,
  the query is outside the pilot scope, or only generic terminology matches.

Every decision includes confidence, reason codes, missing signals, normalized
component scores, matched identifiers, ranked chunks, and expanded evidence.

## Retrieval and deterministic features

The lexical channel uses BM25 over content plus preserved title, heading,
identifier, language, and provenance fields. The dense channel reuses the
sample chunk vectors from `qwen3-embedding:0.6b` and embeds only evaluation or
interactive queries. Reciprocal-rank fusion combines the two channels.

Scores are normalized independently before use:

- Dense cosine similarity uses per-query robust scaling from the median and
  95th percentile, clipped to `[0, 1]`.
- BM25 uses `score / (score + 8)`.
- RRF uses its two-channel theoretical maximum, `2 / 61`.

The decision model is an interpretable weighted score plus explicit guards. It
measures dense/lexical agreement, top-score margin, exact and identifier-like
matches, title and heading matches, query and rare-token coverage, language,
complete structural units, required numeric values, generic-only matches, and
conflicts. Raw scores from unlike retrieval channels are never compared.

Neighbor expansion is bounded to two adjacent chunks from the same document.
It requires an already relevant primary chunk and a measurable query-coverage,
structural-completion, or same-command-family gain. A neighbor cannot raise a
weak primary result above the no-relevance floor.

## Evaluation isolation

`config/azerothcore-wiki-abstention-evaluation.json` contains 64 manually
reviewed questions: 32 answerable and 32 intentionally unanswerable. Stable
question IDs define equal 32-question development and locked-holdout splits.
The `prepare` command materializes both splits with content hashes. The
`calibrate` command accepts only the development file and refuses locked items.
The separate `evaluate-holdout` command verifies the locked flag, development
hash, source/model identity, and frozen threshold configuration. No threshold
is selected or changed in that path.

## Commands

From the repository root, set the external paths appropriate to the host and
run:

```bash
python3 scripts/azerothcore_wiki_abstention.py prepare \
  --evaluation-config config/azerothcore-wiki-abstention-evaluation.json \
  --output /path/to/azerothcore_wiki_abstention_v1

python3 scripts/azerothcore_wiki_abstention.py calibrate \
  --development-set /path/to/azerothcore_wiki_abstention_v1/development-set.json \
  --chunk-experiment /path/to/azerothcore_wiki_chunking_v1 \
  --output /path/to/azerothcore_wiki_abstention_v1 \
  --ollama-endpoint http://127.0.0.1:11434 \
  --model qwen3-embedding:0.6b --batch-size 8

python3 scripts/azerothcore_wiki_abstention.py evaluate-holdout \
  --locked-holdout-set /path/to/azerothcore_wiki_abstention_v1/locked-holdout-set.json \
  --selected-thresholds /path/to/azerothcore_wiki_abstention_v1/selected-thresholds.json \
  --chunk-experiment /path/to/azerothcore_wiki_chunking_v1 \
  --output /path/to/azerothcore_wiki_abstention_v1 \
  --ollama-endpoint http://127.0.0.1:11434 \
  --model qwen3-embedding:0.6b --batch-size 8

python3 scripts/azerothcore_wiki_abstention.py report \
  --output /path/to/azerothcore_wiki_abstention_v1

python3 scripts/azerothcore_wiki_abstention.py query \
  --query 'What does .chatfilter list display?' \
  --selected-thresholds /path/to/azerothcore_wiki_abstention_v1/selected-thresholds.json \
  --chunk-experiment /path/to/azerothcore_wiki_chunking_v1 \
  --ollama-endpoint http://127.0.0.1:11434
```

The query command prints the query, decision, confidence, top-ranked evidence,
retrieval component scores, source and heading paths, matched identifiers,
missing signals, and reason codes.

## Promotion policy

Threshold configuration
`azerothcore_wiki_abstention_thresholds_v1` is source-commit, parser,
embedding-model-digest, and pilot-build specific. It remains experimental even
if a validation run passes. Full-source ingestion will change corpus size and
score distributions, so the thresholds must be recalibrated against a newly
reviewed development/holdout evaluation before production promotion.
