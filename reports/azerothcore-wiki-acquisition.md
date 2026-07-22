# Official AzerothCore Wiki acquisition report

## Result

The official AzerothCore Wiki was acquired as a full Git clone, pinned by detaching the checkout at commit `7d540fc7e683c3bf34a2f465789f1b3df268b609`, and stored outside the Engineering RAG Git repository.

| Field | Value |
|---|---|
| Source ID | `azerothcore_wiki_official` |
| Upstream | `https://github.com/azerothcore/wiki.git` |
| Branch at acquisition | `master` |
| Exact commit | `7d540fc7e683c3bf34a2f465789f1b3df268b609` |
| Exact tag | None |
| Nearest reachable tag | `v2.2.0` (1,878 commits behind HEAD) |
| Acquired | `2026-07-21T19:19:13-07:00` |
| License | MIT, `.github/LICENSE` |
| Snapshot | `/run/media/deck/blAIne-476GB-SAM/blAIne/rag-data/engineering-rag/sources/official_docs/azerothcore_wiki_official/snapshot` |
| Primary docs | `docs/` |
| Files / bytes | 1,054 / 18,696,345 |
| Inventory SHA-256 | `b85d91f93b97537a0e3c3eab1070d6030740d75dcdc24b5fcb8ac2974df93d27` |

## Validation

- Full checkout: yes (`git rev-parse --is-shallow-repository` returned `false`).
- Git integrity: `git fsck --full` passed without findings.
- Worktree: clean after detaching at the resolved commit.
- Upstream/refspec: origin is recorded; all origin branches were fetched by `+refs/heads/*:refs/remotes/origin/*`.
- Dependencies: no submodules, no `.gitmodules`, and no Git LFS pointers.
- Inventory: all 1,054 tracked worktree files have one JSONL record; CSV contains one header and 1,054 data rows.
- Inventory reproducibility: a second generation matched JSONL, CSV, and inclusion/exclusion JSONL byte-for-byte.
- Checkout anomalies: no symlinks, zero-byte worktree files, or untracked files.
- Source boundary: the snapshot is outside the Engineering RAG repository.
- Processing boundary: no site generation, normalization, chunking, embeddings, vectors, or indexes were created.

## Proposed content boundary

- Include: 912 `docs/**/*.md` pages, retaining language metadata.
- Conditional: nine `_includes/` files and `_data/alerts.yml`, only for safe template/metadata resolution.
- Exclude from prose ingestion: 132 license/governance/CI, Jekyll theme/layout, Docker/Gemfile, JavaScript/CSS/font, image, sitemap, verification, and repository-support files. These remain present and hashed in the immutable snapshot.

## Uncertainties

- HEAD has no exact release tag. `v2.2.0` is only the nearest reachable historical tag and should not be treated as the snapshot version.
- The repository-level MIT license is present under `.github/LICENSE` and is recorded as supplied; redistribution policy should still preserve its notice.
- Language is inferred from path conventions (`docs/es/` for Spanish; other primary pages as English), not automatic language detection.
- Near-duplicate results are a bounded heuristic and require human confirmation before any deduplication policy.
- The Jekyll remote theme points to a movable `master`, but the theme is excluded and the site generator was not run.

## Next action

Define and validate a normalization/chunk-definition specification for this one pinned source, using a manually curated evaluation set that covers headings, tables, fenced code, redirects, Liquid includes, bilingual pairs, an oversized command/reference page, and a very small placeholder. Do not create embeddings or vectors until those parse and retrieval-oriented chunk definitions pass manual review.
