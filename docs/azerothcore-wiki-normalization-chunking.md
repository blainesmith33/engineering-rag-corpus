# AzerothCore Wiki normalization and chunk-definition pilot

## Scope and safeguards

Parser `azerothcore_wiki_markdown` version `1.0.0` processes only paths listed
in `config/azerothcore-wiki-chunking-sample.json`. It refuses samples above 20
files. Include resolution may read approved files under `_includes/`, but
include files never become standalone documents. The program does not write to
the snapshot, create a vector database, download models, or start full-source
ingestion.

The deterministic token counter (`engineering_regex_tokens_v1`) groups words,
technical identifiers, and contiguous punctuation. Counts are engineering
approximations used for chunk-definition comparisons, not claims about the
embedding model's private tokenizer.

## Normalization contract

1. Read bytes and hash them before strict UTF-8 decoding. A BOM is accepted and
   recorded. Decode failures produce an excluded manifest record.
2. Parse YAML front matter before Markdown. Preserve the mapping and derive
   `redirect_from` aliases.
3. Protect Liquid raw blocks, then resolve only includes beneath the pinned
   `_includes` directory. Enforce resolved-path containment, a depth limit of
   eight, and cycle detection. Keep unresolved expressions and reasons.
4. Remove Back-to/Volver-a navigation, standalone presentational `<br>` tags,
   and repeated Installation Guide step tables. Record every removal.
5. Retain meaningful HTML, Markdown tables, callouts, links, lists, headings,
   and fenced code. Original fenced blocks must occur byte-for-byte in the
   normalized content.
6. Assign language from the pinned source convention (`docs/es/` is Spanish;
   other selected `docs/` pages are English). Translation pairs have distinct
   IDs plus bidirectional relationship metadata.
7. Exclude placeholder, empty, redirect-only, and navigation-only pages.
   Short complete technical facts remain active.

Document IDs hash source ID, commit, relative path, parser version, and original
content hash. Normalized hashes are SHA-256 over UTF-8 normalized content.

## Chunk profiles

- Profile A: heading-aware, target 250–450 approximate tokens, target midpoint
  350, hard target 600.
- Profile B: heading-aware, target 450–800, target midpoint 650, hard target
  1,000.
- Profile C: fixed 500-token windows with 75-token overlap.

A and B retain title, language, aliases, and heading path in chunk content.
Atomic units are paragraphs, lists, fenced code, HTML blocks, and tables.
Introducing prose is attached to the following code block. Split tables repeat
headers. An indivisible code block, table row, or command row may exceed a hard
target only with explicit metadata.

The oversized GM command table is split first by the command's first identifier
(command family), then packs complete rows to the profile target. Command,
security, syntax, and description remain together. The unusually padded source
table delimiter is compacted in chunks to a valid four-column Markdown
delimiter without changing semantic headers or rows.

Profile C deliberately applies source-order token windows. It preserves chunk
metadata but may break Markdown structures; it is an evaluation control.

## Evaluation

The reviewed question configuration contains 25 questions: 24 answerable and
one deliberately unanswerable. Sample chunks alone are embedded with local
`qwen3-embedding:0.6b`. Each profile uses a separate directory beneath
`temporary-evaluation/` containing an embeddings JSONL file and namespace
manifest marked `temporary=true` and `production=false`.

Dense cosine retrieval, BM25, and reciprocal-rank-fusion hybrid retrieval are
measured at 1, 3, and 5 along with MRR, heading retrieval, exact identifiers,
latency, counts, average size, duplicates, and explicit unanswerable behavior.
No result from this pilot authorizes full-source embedding.

## Reproduction

From the repository root:

~~~bash
python3 scripts/azerothcore_wiki_chunking.py all \
  --snapshot /path/to/pinned/wiki/snapshot \
  --sample-config config/azerothcore-wiki-chunking-sample.json \
  --question-config config/azerothcore-wiki-evaluation-questions.json \
  --output /path/to/azerothcore_wiki_chunking_v1 \
  --ollama-endpoint http://127.0.0.1:11434 \
  --model qwen3-embedding:0.6b \
  --dimensions 1024 \
  --batch-size 8
~~~
