#!/usr/bin/env python3
"""Deterministic abstention and evidence-sufficiency calibration.

This module consumes only the existing bounded AzerothCore Wiki chunking pilot.
It does not normalize source pages, embed corpus chunks, or synthesize answers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    from azerothcore_wiki_chunking import (
        BM25, SOURCE_COMMIT, SOURCE_ID, canonical_json, cosine, embed,
        lexical_tokens, model_info, order, rrf, sha256_bytes,
    )
except ModuleNotFoundError:  # Imported as scripts.azerothcore_wiki_abstention in tests.
    from scripts.azerothcore_wiki_chunking import (
        BM25, SOURCE_COMMIT, SOURCE_ID, canonical_json, cosine, embed,
        lexical_tokens, model_info, order, rrf, sha256_bytes,
    )


CONFIDENCE_COMPONENT = "azerothcore_wiki_evidence_sufficiency"
CONFIDENCE_VERSION = "1.0.0"
THRESHOLD_VERSION = "azerothcore_wiki_abstention_thresholds_v1"
MODEL = "qwen3-embedding:0.6b"
MODEL_DIGEST = "ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d"
DIMENSIONS = 1024
REFERENCE_PATHS = {"docs/gm-commands.md", "docs/creature_immunities.md"}
DECISIONS = {"supported", "insufficient_evidence", "no_relevant_evidence"}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "do", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "the", "to", "what", "when", "where",
    "which", "why", "with", "your", "this", "that", "after", "all", "its", "into",
    "qué", "que", "cómo", "como", "cuál", "cual", "de", "del", "el", "en", "la", "las",
    "los", "para", "por", "se", "un", "una", "y", "después", "hay",
}
GENERIC_TERMS = {
    "account", "command", "configuration", "database", "debug", "file", "server",
    "setting", "table", "value", "wiki", "worldserver", "azerothcore", "use",
    "exact", "document", "old", "route", "addressed",
}
SPANISH_MARKERS = {"qué", "cómo", "cuál", "cuenta", "nivel", "contraseña", "reinos", "iniciar", "sesión"}
BACKTICK_RE = re.compile(r"`([^`]+)`")
FLAG_RE = re.compile(r"(?<!\w)-D[A-Z][A-Z0-9_]*(?:=[A-Za-z0-9_.+-]+)?")
DOT_COMMAND_RE = re.compile(r"(?<!\w)\.[a-z][a-z0-9_-]*(?:\s+[a-z][a-z0-9_-]*){0,3}", re.I)
UPPER_IDENTIFIER_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}(?:=[A-Za-z0-9_.+-]+)?\b")
SCOPED_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*::[A-Za-z_][A-Za-z0-9_]*\b")
PATH_RE = re.compile(r"(?:\./|/)?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+/?")
VERSION_RE = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")
NUMBER_RE = re.compile(r"\b\d{3,}\b")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def hash_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def relative_source(path: str) -> str:
    parts = Path(path).parts
    if "docs" in parts:
        return Path(*parts[parts.index("docs"):]).as_posix()
    return path


def load_hybrid_corpus(chunk_experiment: Path) -> tuple[list[dict[str, Any]], list[list[float]], dict[str, Any]]:
    """Load A for reference docs and B for every other active document."""
    chunks_by_profile = {
        profile: read_jsonl(chunk_experiment / f"chunk-profile-{profile}.jsonl")
        for profile in ("a", "b")
    }
    vectors_by_profile: dict[str, dict[str, list[float]]] = {}
    manifests = {}
    for profile in ("a", "b"):
        namespace = chunk_experiment / "temporary-evaluation" / f"profile-{profile}"
        manifests[profile] = json.loads((namespace / "namespace-manifest.json").read_text(encoding="utf-8"))
        vectors_by_profile[profile] = {
            row["chunk_id"]: row["embedding"]
            for row in read_jsonl(namespace / "embeddings.jsonl")
        }
        if manifests[profile]["model_digest"] != MODEL_DIGEST:
            raise ValueError(f"unexpected model digest for Profile {profile.upper()}")
        if manifests[profile]["dimensions"] != DIMENSIONS:
            raise ValueError(f"unexpected embedding dimensions for Profile {profile.upper()}")
    sample = json.loads((chunk_experiment / "sample-selection.json").read_text(encoding="utf-8"))
    path_order = {entry["relative_path"]: i for i, entry in enumerate(sample["files"])}
    selected = []
    for profile in ("a", "b"):
        for chunk in chunks_by_profile[profile]:
            path = relative_source(chunk["source_path"])
            use = profile == "a" if path in REFERENCE_PATHS else profile == "b"
            if use:
                clone = dict(chunk)
                clone["selected_hybrid_profile"] = profile
                clone["relative_source_path"] = path
                selected.append(clone)
    selected.sort(key=lambda chunk: (path_order[chunk["relative_source_path"]], chunk["chunk_index"]))
    vectors = [
        vectors_by_profile[chunk["selected_hybrid_profile"]][chunk["chunk_id"]]
        for chunk in selected
    ]
    documents: dict[str, set[str]] = defaultdict(set)
    for chunk in selected:
        documents[chunk["document_id"]].add(chunk["selected_hybrid_profile"])
    if any(len(profiles) != 1 for profiles in documents.values()):
        raise ValueError("hybrid corpus mixed profiles within a document")
    if len(selected) != 167:
        raise ValueError(f"expected 167 hybrid chunks, found {len(selected)}")
    corpus_manifest = {
        "source_id": SOURCE_ID,
        "source_commit": SOURCE_COMMIT,
        "hybrid_rule": {
            "profile_a_paths": sorted(REFERENCE_PATHS),
            "profile_b_rule": "all other active sample documents",
            "exactly_one_profile_per_document": True,
        },
        "chunk_count": len(selected),
        "document_count": len(documents),
        "selected_profiles": sorted({chunk["selected_hybrid_profile"] for chunk in selected}),
        "model": MODEL,
        "model_digest": MODEL_DIGEST,
        "dimensions": DIMENSIONS,
        "profile_manifests": manifests,
        "chunk_ids_hash": sha256_bytes("\n".join(chunk["chunk_id"] for chunk in selected).encode("utf-8")),
    }
    return selected, vectors, corpus_manifest


def clean_identifier(value: str) -> str:
    value = value.strip().strip("\"'")
    value = re.sub(r"[,;:?!]+$", "", value)
    return re.sub(r"\s+", " ", value)


def explicit_query_identifiers(query: str) -> list[str]:
    found: list[str] = []
    for pattern in (BACKTICK_RE, FLAG_RE, SCOPED_IDENTIFIER_RE, PATH_RE, UPPER_IDENTIFIER_RE):
        for match in pattern.finditer(query):
            value = clean_identifier(match.group(1) if pattern is BACKTICK_RE else match.group(0))
            if value and value not in found:
                found.append(value)
    for match in DOT_COMMAND_RE.finditer(query):
        value = clean_identifier(match.group(0))
        value = re.sub(r"\s+(?:command|do|does|accept|display|syntax)$", "", value, flags=re.I)
        if value.casefold().startswith(".conf"):
            continue
        if value and value not in found:
            found.append(value)
    return found


def required_numbers(query: str) -> list[str]:
    values = VERSION_RE.findall(query)
    values.extend(value for value in NUMBER_RE.findall(query) if value not in values)
    return list(dict.fromkeys(values))


def query_language(query: str) -> str:
    tokens = set(lexical_tokens(query))
    return "es" if tokens & SPANISH_MARKERS or re.search(r"[¿¡]", query) else "en"


def meaningful_query_tokens(query: str) -> list[str]:
    return [
        token for token in lexical_tokens(query)
        if token not in STOPWORDS and len(token) > 1
    ]


def strip_markup(text: str) -> str:
    value = re.sub(r"<[^>]+>", " ", text)
    value = re.sub(r"[\x60*_[\]{}()|#<>]", " ", value)
    return re.sub(r"\s+", " ", value).casefold().strip()


def contains_support(evidence: str, expected: str | None) -> bool:
    if not expected:
        return True
    return strip_markup(expected) in strip_markup(evidence)


def percentile(values: list[float], proportion: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * proportion
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def normalized_margin(scores: list[float], ranked: list[int]) -> float:
    if len(ranked) < 2:
        return 1.0
    top, second = scores[ranked[0]], scores[ranked[1]]
    denominator = max(abs(top), 1e-9)
    return max(0.0, min(1.0, (top - second) / denominator))


def token_coverage(query_tokens: list[str], evidence: str) -> float:
    if not query_tokens:
        return 0.0
    def form(token: str) -> str:
        return token[:-1] if len(token) > 4 and token.endswith("s") else token

    query_forms = {form(token) for token in query_tokens}
    evidence_tokens = {form(token) for token in lexical_tokens(evidence)}
    return sum(token in evidence_tokens for token in query_forms) / len(query_forms)


def local_identifier_context(content: str, identifiers: list[str]) -> str:
    if not identifiers:
        return content
    lines = content.splitlines()
    selected: set[int] = set()
    fence_ranges: list[tuple[int, int]] = []
    fence_start: int | None = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*(?:`){3}", line):
            if fence_start is None:
                fence_start = i
            else:
                fence_ranges.append((fence_start, i))
                fence_start = None

    def add_adjacent_paragraph(start: int, direction: int) -> None:
        i = start + direction
        while 0 <= i < len(lines) and not lines[i].strip():
            i += direction
        while (
            0 <= i < len(lines)
            and lines[i].strip()
            and not re.match(r"^#{1,6}\s", lines[i])
            and not re.match(r"^\s*(?:`){3}", lines[i])
        ):
            selected.add(i)
            i += direction

    for i, line in enumerate(lines):
        folded = line.casefold()
        if any(identifier.casefold() in folded for identifier in identifiers):
            containing_fence = next(
                ((start, end) for start, end in fence_ranges if start <= i <= end),
                None,
            )
            if containing_fence:
                selected.update(range(containing_fence[0], containing_fence[1] + 1))
                add_adjacent_paragraph(containing_fence[0], -1)
                continue
            if line.lstrip().startswith("|"):
                start = i
                while start > 0 and lines[start - 1].lstrip().startswith("|"):
                    start -= 1
                selected.update(range(start, min(i + 1, len(lines))))
                continue
            start = end = i
            while start > 0 and lines[start - 1].strip() and not re.match(r"^#{1,6}\s", lines[start - 1]):
                start -= 1
            while end + 1 < len(lines) and lines[end + 1].strip() and not re.match(r"^#{1,6}\s", lines[end + 1]):
                end += 1
            selected.update(range(start, end + 1))
            if start > 0 and re.match(r"^#{1,6}\s", lines[start - 1]):
                selected.add(start - 1)
            add_adjacent_paragraph(end, 1)
    return "\n".join(lines[i] for i in sorted(selected))


def complete_semantic_unit(chunk: dict[str, Any], evidence: str) -> tuple[float, list[str]]:
    missing = []
    fence_count = evidence.count("```")
    if fence_count % 2:
        missing.append("unclosed_code_fence")
    table_lines = [line for line in evidence.splitlines() if line.lstrip().startswith("|")]
    if table_lines and not any(re.search(r"\|\s*:?-{3,}", line) for line in table_lines):
        missing.append("table_header_absent")
    kind = chunk["structural_type"]
    if kind == "fixed_token_window":
        missing.append("fixed_window_not_allowed")
    complete = 0.0 if missing else 1.0
    return complete, missing


def corpus_document_frequency(chunks: list[dict[str, Any]]) -> tuple[Counter[str], int]:
    frequency: Counter[str] = Counter()
    for chunk in chunks:
        frequency.update(set(lexical_tokens(chunk["content"])))
    return frequency, len(chunks)


def rare_query_tokens(query_tokens: list[str], frequency: Counter[str], corpus_size: int) -> list[str]:
    rare = []
    for token in set(query_tokens):
        df = frequency.get(token, 0)
        identifier_like = bool(re.search(r"[._:/-]|\d", token))
        if identifier_like or df <= max(2, int(corpus_size * 0.08)):
            rare.append(token)
    return sorted(rare)


RELATION_TERMS = {
    "accept", "accepts", "arguments", "assign", "automatically", "cost", "days",
    "default", "disable", "disables", "display", "enable", "enables", "field",
    "fields", "flag", "option", "permanently", "port", "require", "requires",
    "retention", "security", "select", "sets", "syntax", "value", "variable",
}


def relation_tokens(query: str) -> list[str]:
    return sorted(set(lexical_tokens(query)) & RELATION_TERMS)


def contradiction_signals(query: str, local_context: str) -> list[str]:
    query_tokens = set(lexical_tokens(query))
    context_tokens = set(lexical_tokens(local_context))
    signals = []
    if query_tokens & {"enable", "enables"} and "disable" in context_tokens and not context_tokens & {"enable", "enables"}:
        signals.append("enable_disable_conflict")
    if query_tokens & {"disable", "disables"} and "enable" in context_tokens and not context_tokens & {"disable", "disables"}:
        signals.append("disable_enable_conflict")
    if "automatically" in query_tokens and "automatically" not in context_tokens:
        signals.append("automatic_claim_not_stated")
    if query_tokens & {"permanently", "retention", "days"} and not query_tokens.intersection(context_tokens):
        signals.append("persistence_or_retention_not_stated")
    return signals


class HybridEvidenceRetriever:
    def __init__(self, chunks: list[dict[str, Any]], vectors: list[list[float]]):
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector length mismatch")
        self.chunks = chunks
        self.vectors = vectors
        self.lexical_texts = [
            chunk["content"]
            + "\n"
            + " ".join(chunk.get("aliases", []))
            + "\n"
            + " > ".join(chunk.get("heading_path", []))
            for chunk in chunks
        ]
        self.bm25 = BM25(self.lexical_texts)
        self.frequency, self.corpus_size = corpus_document_frequency(chunks)
        self.by_chunk_id = {chunk["chunk_id"]: i for i, chunk in enumerate(chunks)}
        self.corpus_text_folded = "\n".join(self.lexical_texts).casefold()

    def retrieve(self, query: str, query_vector: list[float], neighbor_config: dict[str, Any] | None = None) -> dict[str, Any]:
        began = time.perf_counter()
        dense_scores = [cosine(query_vector, vector) for vector in self.vectors]
        lexical_scores = self.bm25.scores(query)
        dense_order = order(dense_scores)
        lexical_order = order(lexical_scores)
        fusion_scores = rrf(dense_order, lexical_order)
        fusion_order = order(fusion_scores)
        query_tokens = meaningful_query_tokens(query)
        explicit_ids = explicit_query_identifiers(query)
        numbers = required_numbers(query)
        language = query_language(query)
        top_index = fusion_order[0]
        top = self.chunks[top_index]

        p50 = percentile(dense_scores, 0.50)
        p95 = percentile(dense_scores, 0.95)
        dense_normalized = max(0.0, min(1.0, (dense_scores[top_index] - p50) / max(p95 - p50, 1e-9)))
        lexical_normalized = lexical_scores[top_index] / (lexical_scores[top_index] + 8.0) if lexical_scores[top_index] > 0 else 0.0
        hybrid_normalized = max(0.0, min(1.0, fusion_scores[top_index] / (2 / 61)))

        dense_top_doc = self.chunks[dense_order[0]]["document_id"]
        lexical_top_doc = self.chunks[lexical_order[0]]["document_id"]
        fusion_top_doc = top["document_id"]
        agreement = 1.0 if dense_top_doc == lexical_top_doc == fusion_top_doc else (
            0.5 if fusion_top_doc in {dense_top_doc, lexical_top_doc} else 0.0
        )
        channel_count = sum(
            fusion_top_doc in {self.chunks[index]["document_id"] for index in ranked[:3]}
            for ranked in (dense_order, lexical_order)
        )
        primary_relevance = 0.45 * dense_normalized + 0.35 * lexical_normalized + 0.20 * agreement

        primary_evidence = top["content"]
        primary_coverage = token_coverage(query_tokens, primary_evidence)
        expanded_indices, expansion_reasons = self._expand_neighbors(
            top_index, fusion_order, query_tokens, primary_coverage, primary_relevance,
            neighbor_config or {"min_primary_relevance": 0.30, "min_coverage_gain": 0.10, "max_neighbors": 2},
        )
        evidence_indices = [top_index] + expanded_indices
        expanded_evidence = "\n\n".join(self.chunks[index]["content"] for index in evidence_indices)

        matched_ids = [identifier for identifier in explicit_ids if identifier.casefold() in expanded_evidence.casefold()]
        corpus_matched_ids = [identifier for identifier in explicit_ids if identifier.casefold() in self.corpus_text_folded]
        missing_ids = [identifier for identifier in explicit_ids if identifier not in corpus_matched_ids]
        missing_top_ids = [identifier for identifier in explicit_ids if identifier not in matched_ids and identifier not in missing_ids]
        matched_numbers = [number for number in numbers if number in expanded_evidence]
        corpus_matched_numbers = [number for number in numbers if number in self.corpus_text_folded]
        missing_numbers = [number for number in numbers if number not in corpus_matched_numbers]

        coverage = token_coverage(query_tokens, expanded_evidence)
        rare_tokens = rare_query_tokens(query_tokens, self.frequency, self.corpus_size)
        rare_coverage = token_coverage(rare_tokens, expanded_evidence) if rare_tokens else coverage
        local_context = local_identifier_context(expanded_evidence, matched_ids)
        identifier_context_coverage = token_coverage(query_tokens, local_context) if explicit_ids and local_context else coverage
        relations = relation_tokens(query)
        relation_coverage = token_coverage(relations, local_context) if relations else 1.0
        conflicts = contradiction_signals(query, local_context)

        title_tokens = set(lexical_tokens(top["title"]))
        heading_tokens = set(lexical_tokens(" ".join(top.get("heading_path", []))))
        query_set = set(query_tokens)
        title_heading_match = (
            len(query_set & (title_tokens | heading_tokens)) / len(query_set)
            if query_set else 0.0
        )
        heading_match = bool(query_set & heading_tokens)
        language_match = 1.0 if language == top["language"] else 0.0
        complete, incomplete_signals = complete_semantic_unit(top, expanded_evidence)
        generic_only = (
            not matched_ids
            and rare_coverage < 0.25
            and coverage < 0.50
            and set(query_tokens).issubset(GENERIC_TERMS | STOPWORDS)
        )
        dense_margin = normalized_margin(dense_scores, dense_order)
        lexical_margin = normalized_margin(lexical_scores, lexical_order)
        fusion_margin = normalized_margin(fusion_scores, fusion_order)

        exact_ratio = len(matched_ids) / len(explicit_ids) if explicit_ids else 0.0
        support_score = (
            0.15 * dense_normalized
            + 0.19 * lexical_normalized
            + 0.10 * hybrid_normalized
            + 0.11 * agreement
            + 0.15 * coverage
            + 0.10 * rare_coverage
            + 0.05 * title_heading_match
            + 0.04 * language_match
            + 0.05 * complete
            + 0.06 * identifier_context_coverage
            + (0.10 * exact_ratio if explicit_ids else 0.0)
        )
        support_score -= 0.45 if missing_ids else 0.0
        support_score -= 0.20 if missing_numbers else 0.0
        support_score -= 0.20 if conflicts else 0.0
        support_score -= 0.10 if generic_only else 0.0
        support_score -= 0.08 if explicit_ids and relation_coverage < 0.34 else 0.0
        support_score = max(0.0, min(1.0, support_score))

        top_evidence = []
        for rank, index in enumerate(fusion_order[:5], 1):
            chunk = self.chunks[index]
            top_evidence.append({
                "rank": rank,
                "chunk_id": chunk["chunk_id"],
                "document_id": chunk["document_id"],
                "source_path": chunk["relative_source_path"],
                "title": chunk["title"],
                "heading_path": chunk["heading_path"],
                "language": chunk["language"],
                "selected_hybrid_profile": chunk["selected_hybrid_profile"],
                "structural_type": chunk["structural_type"],
                "dense_cosine": round(dense_scores[index], 8),
                "dense_normalized": round(max(0.0, min(1.0, (dense_scores[index] - p50) / max(p95 - p50, 1e-9))), 8),
                "bm25_score": round(lexical_scores[index], 8),
                "rrf_score": round(fusion_scores[index], 8),
                "content": chunk["content"],
            })
        latency = (time.perf_counter() - began) * 1000
        return {
            "query": query,
            "query_analysis": {
                "language": language,
                "tokens": query_tokens,
                "rare_tokens": rare_tokens,
                "explicit_identifiers": explicit_ids,
                "required_numbers": numbers,
            },
            "component_scores": {
                "dense_cosine": round(dense_scores[top_index], 8),
                "dense_normalized": round(dense_normalized, 8),
                "bm25_score": round(lexical_scores[top_index], 8),
                "lexical_normalized": round(lexical_normalized, 8),
                "rrf_score": round(fusion_scores[top_index], 8),
                "hybrid_normalized": round(hybrid_normalized, 8),
                "dense_margin": round(dense_margin, 8),
                "lexical_margin": round(lexical_margin, 8),
                "hybrid_margin": round(fusion_margin, 8),
                "dense_lexical_agreement": agreement,
                "independent_channel_count": channel_count,
                "query_token_coverage": round(coverage, 8),
                "rare_token_coverage": round(rare_coverage, 8),
                "identifier_context_coverage": round(identifier_context_coverage, 8),
                "relation_coverage": round(relation_coverage, 8),
                "title_heading_match": round(title_heading_match, 8),
                "heading_match": heading_match,
                "language_compatibility": language_match,
                "evidence_completeness": complete,
                "primary_relevance": round(primary_relevance, 8),
                "support_score": round(support_score, 8),
            },
            "matched_identifiers": matched_ids,
            "corpus_matched_identifiers": corpus_matched_ids,
            "missing_identifiers": missing_ids,
            "missing_top_identifiers": missing_top_ids,
            "matched_numbers": matched_numbers,
            "missing_numbers": missing_numbers,
            "conflict_signals": conflicts,
            "incomplete_signals": incomplete_signals,
            "generic_keyword_only": generic_only,
            "neighbor_evidence": {
                "expanded": bool(expanded_indices),
                "chunk_ids": [self.chunks[index]["chunk_id"] for index in expanded_indices],
                "reason_codes": expansion_reasons,
            },
            "expanded_evidence": expanded_evidence,
            "top_evidence": top_evidence,
            "ranking": {
                "dense_top_document_id": dense_top_doc,
                "lexical_top_document_id": lexical_top_doc,
                "hybrid_top_document_id": fusion_top_doc,
                "hybrid_document_ranks": self._document_ranks(fusion_order),
            },
            "retrieval_latency_ms": round(latency, 3),
        }

    def _document_ranks(self, ranked: list[int]) -> dict[str, int]:
        output = {}
        for rank, index in enumerate(ranked, 1):
            output.setdefault(self.chunks[index]["document_id"], rank)
        return output

    def _expand_neighbors(
        self,
        top_index: int,
        fusion_order: list[int],
        query_tokens: list[str],
        primary_coverage: float,
        primary_relevance: float,
        config: dict[str, Any],
    ) -> tuple[list[int], list[str]]:
        if primary_relevance < config["min_primary_relevance"]:
            return [], []
        top = self.chunks[top_index]
        top_twenty = set(fusion_order[:20])
        selected = []
        reasons = []
        current_text = top["content"]
        family = set(top.get("metadata", {}).get("command_families", []))
        for direction, chunk_id in (
            ("previous", top.get("previous_chunk_id")),
            ("next", top.get("next_chunk_id")),
        ):
            if not chunk_id or len(selected) >= config["max_neighbors"]:
                continue
            index = self.by_chunk_id.get(chunk_id)
            if index is None:
                continue
            candidate = self.chunks[index]
            if candidate["document_id"] != top["document_id"]:
                continue
            candidate_family = set(candidate.get("metadata", {}).get("command_families", []))
            candidate_text = current_text + "\n\n" + candidate["content"]
            gain = token_coverage(query_tokens, candidate_text) - token_coverage(query_tokens, current_text)
            family_continuation = bool(family and family == candidate_family and gain > 0)
            structural_continuation = bool(
                top["content"].count("```") % 2
                or (top["content"].lstrip().startswith("|") and not re.search(r"\|\s*:?-{3,}", top["content"]))
            )
            if index in top_twenty and (
                gain >= config["min_coverage_gain"] or family_continuation or structural_continuation
            ):
                selected.append(index)
                current_text = candidate_text
                if family_continuation:
                    reasons.append("command_family_neighbor")
                elif structural_continuation:
                    reasons.append(f"{direction}_structural_completion")
                else:
                    reasons.append(f"{direction}_coverage_gain")
        return selected, reasons


def threshold_candidates() -> list[dict[str, Any]]:
    output = []
    for support in (0.52, 0.58, 0.64, 0.70):
        for coverage in (0.30, 0.40, 0.50, 0.60):
            for rare in (0.00, 0.20, 0.40):
                for identifier_context in (0.20, 0.40, 0.60):
                    for relation_context in (0.50, 0.75, 1.00):
                        for agreement in (False, True):
                            output.append({
                            "support_score": support,
                            "min_query_coverage": coverage,
                            "min_rare_coverage": rare,
                            "min_identifier_context_coverage": identifier_context,
                            "require_dense_lexical_agreement": agreement,
                            "no_relevant_primary_relevance": 0.24,
                            "min_relation_coverage": relation_context,
                            "strict_absent_identifier_rejection": True,
                            "strict_missing_number_rejection": True,
                            "neighbor": {
                                "min_primary_relevance": 0.30,
                                "min_coverage_gain": 0.10,
                                "max_neighbors": 2,
                            },
                            })
    return output


def decide(feature: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
    scores = feature["component_scores"]
    reasons: list[str] = []
    missing_signals: list[str] = []
    explicit = feature["query_analysis"]["explicit_identifiers"]

    if feature["missing_identifiers"] and thresholds["strict_absent_identifier_rejection"]:
        decision = "no_relevant_evidence"
        reasons += ["identifier_absent", "out_of_sample_scope"]
        missing_signals.append("exact_identifier_match")
    elif feature["missing_numbers"] and thresholds["strict_missing_number_rejection"]:
        decision = (
            "insufficient_evidence"
            if scores["primary_relevance"] >= thresholds["no_relevant_primary_relevance"]
            else "no_relevant_evidence"
        )
        reasons.append("numeric_fact_absent")
        missing_signals.append("requested_numeric_fact")
    elif scores["primary_relevance"] < thresholds["no_relevant_primary_relevance"]:
        decision = "no_relevant_evidence"
        reasons += ["weak_semantic_only", "out_of_sample_scope"]
        missing_signals += ["lexical_support", "retrieval_channel_agreement"]
    else:
        checks = {
            "support_score": scores["support_score"] >= thresholds["support_score"],
            "query_coverage": scores["query_token_coverage"] >= thresholds["min_query_coverage"],
            "rare_coverage": scores["rare_token_coverage"] >= thresholds["min_rare_coverage"],
            "evidence_complete": scores["evidence_completeness"] >= 1.0,
            "identifier_context": (
                not explicit
                or (
                    not feature["missing_top_identifiers"]
                    and scores["identifier_context_coverage"] >= thresholds["min_identifier_context_coverage"]
                )
            ),
            "relation_context": (
                not explicit
                or scores["relation_coverage"] >= thresholds["min_relation_coverage"]
            ),
            "agreement": (
                not thresholds["require_dense_lexical_agreement"]
                or scores["dense_lexical_agreement"] >= 0.5
                or (
                    explicit
                    and len(feature["matched_identifiers"]) == len(explicit)
                    and scores["identifier_context_coverage"] >= 0.60
                )
            ),
            "no_conflict": not feature["conflict_signals"],
            "language": scores["language_compatibility"] >= 1.0,
            "not_generic": not feature["generic_keyword_only"],
        }
        if all(checks.values()):
            decision = "supported"
            if explicit:
                reasons.append("exact_identifier_match")
            if scores["dense_lexical_agreement"] >= 0.5:
                reasons.append("dense_lexical_agreement")
            if scores["heading_match"]:
                reasons.append("heading_match")
            reasons.append("complete_semantic_unit")
            if feature["neighbor_evidence"]["expanded"]:
                reasons.append("neighbor_evidence_complete")
        else:
            decision = "insufficient_evidence"
            if not checks["support_score"]:
                reasons.append("weak_semantic_only")
                missing_signals.append("minimum_support_score")
            if not checks["query_coverage"] or not checks["rare_coverage"]:
                reasons.append("generic_keyword_overlap")
                missing_signals.append("query_or_rare_token_coverage")
            if not checks["evidence_complete"]:
                reasons.append("insufficient_context")
                missing_signals.extend(feature["incomplete_signals"])
            if not checks["identifier_context"]:
                reasons.append("identifier_absent" if feature["missing_top_identifiers"] else "insufficient_context")
                missing_signals.append("identifier_and_requested_fact_in_same_context")
            if not checks["relation_context"]:
                reasons.append("insufficient_context")
                missing_signals.append("requested_relation_not_stated")
            if not checks["agreement"]:
                reasons.append("conflicting_results")
                missing_signals.append("dense_lexical_agreement")
            if not checks["no_conflict"]:
                reasons.append("conflicting_results")
                missing_signals.extend(feature["conflict_signals"])
            if not checks["language"]:
                reasons.append("language_mismatch")
                missing_signals.append("source_language_compatibility")
            if not checks["not_generic"]:
                reasons.append("generic_keyword_overlap")
        if scores["hybrid_margin"] < 0.01 and decision != "supported":
            reasons.append("low_score_margin")
    reasons = list(dict.fromkeys(reasons))
    missing_signals = list(dict.fromkeys(missing_signals))
    confidence = (
        scores["support_score"]
        if decision == "supported"
        else max(0.0, min(1.0, 1.0 - scores["support_score"] + (0.20 if feature["missing_identifiers"] else 0.0)))
    )
    result = {
        "query": feature["query"],
        "decision": decision,
        "confidence": round(confidence, 8),
        "reason_codes": reasons,
        "top_evidence": feature["top_evidence"],
        "component_scores": scores,
        "matched_identifiers": feature["matched_identifiers"],
        "missing_expected_signals": missing_signals,
        "threshold_configuration_version": THRESHOLD_VERSION,
        "neighbor_evidence": feature["neighbor_evidence"],
        "expanded_evidence": feature["expanded_evidence"],
        "query_analysis": feature["query_analysis"],
        "ranking": feature["ranking"],
        "retrieval_latency_ms": feature["retrieval_latency_ms"],
    }
    if result["decision"] not in DECISIONS or not result["reason_codes"]:
        raise AssertionError("every decision must be valid and interpretable")
    return result


def materialize_evaluation_sets(config_path: Path, chunk_experiment: Path, output: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    documents = read_jsonl(chunk_experiment / "normalization-manifest.jsonl")
    by_path = {doc["relative_path"]: doc for doc in documents}
    questions = []
    for raw in config["questions"]:
        item = dict(raw)
        source = item["expected_source_path"]
        item["expected_document_id"] = by_path[source]["document_id"] if source else None
        item["manual_reviewed"] = True
        questions.append(item)
    if len(questions) < 60:
        raise ValueError("evaluation set must contain at least 60 questions")
    counts = Counter((item["split"], item["answerable"]) for item in questions)
    expected = {
        ("development", True): 16,
        ("development", False): 16,
        ("locked_holdout", True): 16,
        ("locked_holdout", False): 16,
    }
    if len(counts) != len(expected) or any(counts[key] != value for key, value in expected.items()):
        raise ValueError(f"unexpected split composition: {counts}")
    development = [item for item in questions if item["split"] == "development"]
    holdout = [item for item in questions if item["split"] == "locked_holdout"]
    expanded = {
        key: config[key]
        for key in (
            "schema_version", "evaluation_id", "source_id", "source_commit", "indexed_scope",
            "split_method", "manual_review",
        )
    }
    expanded["composition"] = {
        "total": len(questions),
        "answerable": sum(item["answerable"] for item in questions),
        "unanswerable": sum(not item["answerable"] for item in questions),
        "development": len(development),
        "locked_holdout": len(holdout),
        "absence_classes": dict(sorted(Counter(
            item["absence_class"] for item in questions if not item["answerable"]
        ).items())),
    }
    expanded["questions"] = questions
    development_payload = {
        "evaluation_id": config["evaluation_id"],
        "split": "development",
        "locked": False,
        "questions_hash": hash_json(development),
        "questions": development,
    }
    holdout_payload = {
        "evaluation_id": config["evaluation_id"],
        "split": "locked_holdout",
        "locked": True,
        "calibration_use_prohibited": True,
        "questions_hash": hash_json(holdout),
        "questions": holdout,
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "expanded-evaluation-set.json", expanded)
    write_json(output / "development-set.json", development_payload)
    write_json(output / "locked-holdout-set.json", holdout_payload)
    return {"expanded": expanded, "development": development_payload, "holdout": holdout_payload}


def retrieval_metrics(questions: list[dict[str, Any]], feature_rows: list[dict[str, Any]]) -> dict[str, float]:
    by_id = {row["question_id"]: row for row in feature_rows}
    answerable = [question for question in questions if question["answerable"]]
    hits = Counter()
    reciprocal = []
    for question in answerable:
        ranks = by_id[question["question_id"]]["features"]["ranking"]["hybrid_document_ranks"]
        rank = ranks.get(question["expected_document_id"])
        reciprocal.append(1 / rank if rank else 0.0)
        for cutoff in (1, 3, 5):
            if rank and rank <= cutoff:
                hits[cutoff] += 1
    return {
        "answerable_recall_at_1": round(hits[1] / len(answerable), 6),
        "answerable_recall_at_3": round(hits[3] / len(answerable), 6),
        "answerable_recall_at_5": round(hits[5] / len(answerable), 6),
        "mean_reciprocal_rank": round(statistics.fmean(reciprocal), 6),
    }


def evaluate_decisions(
    questions: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    thresholds: dict[str, Any],
    query_embedding_latency_ms: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_question = {question["question_id"]: question for question in questions}
    results = []
    true_supported = 0
    all_supported = 0
    unanswerable_supported = 0
    answerable_count = sum(question["answerable"] for question in questions)
    unanswerable_count = len(questions) - answerable_count
    sufficient_accepts = 0
    exact_real_total = exact_real_accepted = 0
    false_identifier_total = false_identifier_rejected = 0
    latencies = []
    for row in feature_rows:
        question = by_question[row["question_id"]]
        decision_result = decide(row["features"], thresholds)
        decision_result["question_id"] = row["question_id"]
        decision_result["answerable"] = question["answerable"]
        decision_result["expected_document_id"] = question["expected_document_id"]
        decision_result["expected_source_path"] = question["expected_source_path"]
        decision_result["expected_heading_path"] = question["expected_heading_path"]
        decision_result["expected_supporting_text"] = question["expected_supporting_text"]
        decision_result["category"] = question["category"]
        decision_result["absence_class"] = question["absence_class"]
        top_doc = (
            decision_result["top_evidence"][0]["document_id"]
            if decision_result["top_evidence"] else None
        )
        correct_doc = question["answerable"] and top_doc == question["expected_document_id"]
        support_present = question["answerable"] and contains_support(
            decision_result["expanded_evidence"], question["expected_supporting_text"]
        )
        valid_support = decision_result["decision"] == "supported" and correct_doc and support_present
        decision_result["evaluation"] = {
            "top_document_correct": bool(correct_doc),
            "expected_support_present": bool(support_present),
            "valid_supported_decision": bool(valid_support),
        }
        if decision_result["decision"] == "supported":
            all_supported += 1
            if valid_support:
                true_supported += 1
                sufficient_accepts += 1
            if not question["answerable"]:
                unanswerable_supported += 1
        runtime_ids = explicit_query_identifiers(question["question"])
        if question["answerable"] and runtime_ids:
            exact_real_total += 1
            if valid_support:
                exact_real_accepted += 1
        if not question["answerable"] and runtime_ids:
            false_identifier_total += 1
            if decision_result["decision"] != "supported":
                false_identifier_rejected += 1
        decision_result["decision_latency_ms"] = round(
            decision_result["retrieval_latency_ms"] + query_embedding_latency_ms, 3
        )
        latencies.append(decision_result["decision_latency_ms"])
        results.append(decision_result)
    metrics = {
        **retrieval_metrics(questions, feature_rows),
        "supported_answer_precision": round(true_supported / all_supported, 6) if all_supported else 1.0,
        "supported_answer_recall": round(true_supported / answerable_count, 6),
        "unanswerable_rejection_rate": round((unanswerable_count - unanswerable_supported) / unanswerable_count, 6),
        "false_evidence_acceptance_rate": round(
            (all_supported - true_supported) / all_supported, 6
        ) if all_supported else 0.0,
        "false_rejection_rate": round((answerable_count - true_supported) / answerable_count, 6),
        "exact_identifier_acceptance_rate": round(exact_real_accepted / exact_real_total, 6) if exact_real_total else None,
        "false_identifier_rejection_rate": round(false_identifier_rejected / false_identifier_total, 6) if false_identifier_total else None,
        "accepted_evidence_sufficiency_rate": round(sufficient_accepts / all_supported, 6) if all_supported else 1.0,
        "average_decision_latency_ms": round(statistics.fmean(latencies), 3),
        "question_count": len(questions),
        "answerable_count": answerable_count,
        "unanswerable_count": unanswerable_count,
        "supported_count": all_supported,
    }
    return metrics, results


def build_feature_rows(
    questions: list[dict[str, Any]],
    retriever: HybridEvidenceRetriever,
    endpoint: str,
    model: str,
    batch_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    info = model_info(endpoint, model)
    if info["digest"] != MODEL_DIGEST:
        raise ValueError(f"model digest changed: {info['digest']}")
    vectors, batch_latencies = embed(
        endpoint, model, [question["question"] for question in questions], batch_size
    )
    if any(len(vector) != DIMENSIONS for vector in vectors):
        raise ValueError("query embedding dimension mismatch")
    rows = []
    for question, vector in zip(questions, vectors):
        rows.append({
            "question_id": question["question_id"],
            "features": retriever.retrieve(question["question"], vector),
        })
    embedding = {
        "endpoint": endpoint,
        "model": model,
        "model_digest": info["digest"],
        "dimensions": DIMENSIONS,
        "batch_size": batch_size,
        "batch_latencies_ms": [round(value, 3) for value in batch_latencies],
        "average_per_question_ms": round(sum(batch_latencies) / len(questions), 3),
    }
    return rows, embedding


def candidate_objective(metrics: dict[str, Any]) -> float:
    exact_accept = metrics["exact_identifier_acceptance_rate"] or 0.0
    false_id_reject = metrics["false_identifier_rejection_rate"] or 0.0
    return round(
        2.0 * metrics["supported_answer_precision"]
        + 1.5 * metrics["supported_answer_recall"]
        + 1.5 * metrics["unanswerable_rejection_rate"]
        + exact_accept
        + false_id_reject
        + metrics["accepted_evidence_sufficiency_rate"]
        - metrics["false_evidence_acceptance_rate"],
        8,
    )


def development_candidate_eligible(metrics: dict[str, Any]) -> bool:
    return (
        metrics["supported_answer_precision"] >= 0.90
        and metrics["unanswerable_rejection_rate"] >= 0.90
        and metrics["false_evidence_acceptance_rate"] <= 0.10
        and (metrics["false_identifier_rejection_rate"] or 0.0) >= 0.90
        and metrics["accepted_evidence_sufficiency_rate"] >= 1.0
    )


def select_thresholds(
    questions: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    development_hash: str,
    query_embedding_latency_ms: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    candidate_rows = []
    evaluated: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for index, candidate in enumerate(threshold_candidates()):
        metrics, _ = evaluate_decisions(
            questions, feature_rows, candidate, query_embedding_latency_ms
        )
        eligible = development_candidate_eligible(metrics)
        objective = candidate_objective(metrics)
        candidate_id = "thr_" + hashlib.sha256(canonical_json(candidate).encode("utf-8")).hexdigest()[:16]
        candidate_rows.append({
            "candidate_index": index,
            "candidate_id": candidate_id,
            "thresholds": candidate,
            "development_metrics": metrics,
            "development_gate_eligible": eligible,
            "objective": objective,
        })
        evaluated.append((candidate_rows[-1], candidate))
    winner_row, winner = max(
        evaluated,
        key=lambda pair: (
            pair[0]["development_gate_eligible"],
            pair[0]["objective"],
            pair[0]["development_metrics"]["supported_answer_recall"],
            pair[0]["development_metrics"]["unanswerable_rejection_rate"],
            -pair[1]["support_score"],
            canonical_json(pair[1]),
        ),
    )
    selected_metrics, selected_results = evaluate_decisions(
        questions, feature_rows, winner, query_embedding_latency_ms
    )
    selected = {
        "threshold_configuration_version": THRESHOLD_VERSION,
        "confidence_component": CONFIDENCE_COMPONENT,
        "confidence_component_version": CONFIDENCE_VERSION,
        "source_id": SOURCE_ID,
        "source_commit": SOURCE_COMMIT,
        "model": MODEL,
        "model_digest": MODEL_DIGEST,
        "dimensions": DIMENSIONS,
        "development_set_hash": development_hash,
        "calibration": {
            "scope": "development_only",
            "locked_holdout_accessed": False,
            "candidate_count": len(candidate_rows),
            "selected_candidate_id": winner_row["candidate_id"],
            "selection_objective": winner_row["objective"],
            "development_gate_eligible": winner_row["development_gate_eligible"],
        },
        "score_normalization": {
            "dense": "per-query robust scaling: (top - median) / (p95 - median), clipped to [0,1]",
            "lexical": "BM25 / (BM25 + 8), per top result",
            "hybrid": "RRF score divided by theoretical two-channel maximum 2/61, clipped to [0,1]",
            "raw_scores_directly_compared": False,
        },
        "feature_weights": {
            "dense_normalized": 0.15,
            "lexical_normalized": 0.19,
            "hybrid_normalized": 0.10,
            "dense_lexical_agreement": 0.11,
            "query_token_coverage": 0.15,
            "rare_token_coverage": 0.10,
            "title_heading_match": 0.05,
            "language_compatibility": 0.04,
            "evidence_completeness": 0.05,
            "identifier_context_coverage": 0.06,
            "exact_identifier_bonus": 0.10,
        },
        "thresholds": winner,
        "promotion_status": "experimental_not_promoted",
    }
    candidates_payload = {
        "threshold_configuration_version": THRESHOLD_VERSION,
        "calibration_scope": "development_only",
        "development_set_hash": development_hash,
        "locked_holdout_accessed": False,
        "candidate_count": len(candidate_rows),
        "candidates": candidate_rows,
    }
    return selected, candidate_rows, selected_metrics, selected_results


def calibrate(
    development_path: Path,
    chunk_experiment: Path,
    output: Path,
    endpoint: str,
    model: str,
    batch_size: int,
) -> dict[str, Any]:
    development = json.loads(development_path.read_text(encoding="utf-8"))
    if development.get("split") != "development" or development.get("locked"):
        raise ValueError("calibration accepts only an unlocked development set")
    if any(question["split"] != "development" for question in development["questions"]):
        raise ValueError("non-development item supplied to calibration")
    if development["questions_hash"] != hash_json(development["questions"]):
        raise ValueError("development-set hash mismatch")
    chunks, vectors, corpus_manifest = load_hybrid_corpus(chunk_experiment)
    retriever = HybridEvidenceRetriever(chunks, vectors)
    feature_rows, embedding_info = build_feature_rows(
        development["questions"], retriever, endpoint, model, batch_size
    )
    selected, candidate_rows, metrics, results = select_thresholds(
        development["questions"],
        feature_rows,
        development["questions_hash"],
        embedding_info["average_per_question_ms"],
    )
    write_json(output / "threshold-candidates.json", {
        "threshold_configuration_version": THRESHOLD_VERSION,
        "calibration_scope": "development_only",
        "development_set_hash": development["questions_hash"],
        "locked_holdout_accessed": False,
        "candidate_count": len(candidate_rows),
        "candidates": candidate_rows,
    })
    write_json(output / "selected-thresholds.json", selected)
    payload = {
        "split": "development",
        "set_hash": development["questions_hash"],
        "corpus_manifest": corpus_manifest,
        "embedding": embedding_info,
        "selected_candidate_id": selected["calibration"]["selected_candidate_id"],
        "metrics": metrics,
        "results": results,
    }
    write_json(output / "development-results.json", payload)
    return payload


def acceptance_gate(metrics: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "answerable_recall_at_5_at_least_0_90": metrics["answerable_recall_at_5"] >= 0.90,
        "unanswerable_rejection_at_least_0_90": metrics["unanswerable_rejection_rate"] >= 0.90,
        "false_evidence_acceptance_at_most_0_10": metrics["false_evidence_acceptance_rate"] <= 0.10,
        "false_identifier_rejection_reliable": (metrics["false_identifier_rejection_rate"] or 0.0) >= 0.90,
        "exact_identifier_acceptance_not_materially_degraded": (metrics["exact_identifier_acceptance_rate"] or 0.0) >= 0.80,
        "every_accept_has_sufficient_support": metrics["accepted_evidence_sufficiency_rate"] >= 1.0,
        "thresholds_not_tuned_on_holdout": selected["calibration"]["locked_holdout_accessed"] is False,
    }
    return {"passed": all(checks.values()), "checks": checks}


def evaluate_holdout(
    holdout_path: Path,
    selected_path: Path,
    chunk_experiment: Path,
    output: Path,
    endpoint: str,
    model: str,
    batch_size: int,
) -> dict[str, Any]:
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    if selected["calibration"]["locked_holdout_accessed"] is not False:
        raise ValueError("selected configuration does not prove holdout isolation")
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    if holdout.get("split") != "locked_holdout" or not holdout.get("locked"):
        raise ValueError("holdout evaluation requires a locked holdout set")
    if not holdout.get("calibration_use_prohibited"):
        raise ValueError("holdout lacks calibration prohibition marker")
    if any(question["split"] != "locked_holdout" for question in holdout["questions"]):
        raise ValueError("non-holdout item supplied to holdout evaluation")
    if holdout["questions_hash"] != hash_json(holdout["questions"]):
        raise ValueError("holdout-set hash mismatch")
    chunks, vectors, corpus_manifest = load_hybrid_corpus(chunk_experiment)
    retriever = HybridEvidenceRetriever(chunks, vectors)
    feature_rows, embedding_info = build_feature_rows(
        holdout["questions"], retriever, endpoint, model, batch_size
    )
    metrics, results = evaluate_decisions(
        holdout["questions"],
        feature_rows,
        selected["thresholds"],
        embedding_info["average_per_question_ms"],
    )
    gate = acceptance_gate(metrics, selected)
    payload = {
        "split": "locked_holdout",
        "locked": True,
        "set_hash": holdout["questions_hash"],
        "selected_threshold_configuration_version": selected["threshold_configuration_version"],
        "selected_thresholds_hash": hash_json(selected),
        "thresholds_changed_after_calibration": False,
        "corpus_manifest": corpus_manifest,
        "embedding": embedding_info,
        "metrics": metrics,
        "acceptance_gate": gate,
        "results": results,
    }
    write_json(output / "holdout-results.json", payload)
    return payload


def result_review(title: str, rows: list[dict[str, Any]], predicate: Any, explanation: str) -> str:
    selected = [row for row in rows if predicate(row)]
    lines = [f"# {title}", "", explanation, "", f"Count: **{len(selected)}**.", ""]
    if not selected:
        lines += ["No cases.", ""]
        return "\n".join(lines)
    for row in selected:
        top = row["top_evidence"][0] if row["top_evidence"] else None
        lines += [
            f"## {row['question_id']}: {row['query']}", "",
            f"- Decision: {row['decision']} ({row['confidence']})",
            f"- Category: {row['category']}",
            f"- Absence class: {row['absence_class']}",
            f"- Reason codes: {', '.join(row['reason_codes'])}",
            f"- Top source: {top['source_path'] if top else '(none)'}",
            f"- Top heading: {' > '.join(top['heading_path']) if top else '(none)'}",
            f"- Support score: {row['component_scores']['support_score']}",
            f"- Query coverage: {row['component_scores']['query_token_coverage']}",
            f"- Rare coverage: {row['component_scores']['rare_token_coverage']}",
            f"- Matched identifiers: {', '.join(row['matched_identifiers']) or '(none)'}",
            f"- Missing signals: {', '.join(row['missing_expected_signals']) or '(none)'}",
            "", "~~~~text",
            (row["expanded_evidence"][:1200] + ("…" if len(row["expanded_evidence"]) > 1200 else "")),
            "~~~~", "",
        ]
    return "\n".join(lines)


def metrics_table(development: dict[str, Any], holdout: dict[str, Any]) -> list[str]:
    lines = [
        "| Metric | Development | Locked holdout |",
        "|---|---:|---:|",
    ]
    keys = [
        "answerable_recall_at_1", "answerable_recall_at_3", "answerable_recall_at_5",
        "mean_reciprocal_rank", "supported_answer_precision", "supported_answer_recall",
        "unanswerable_rejection_rate", "false_evidence_acceptance_rate",
        "false_rejection_rate", "exact_identifier_acceptance_rate",
        "false_identifier_rejection_rate", "accepted_evidence_sufficiency_rate",
        "average_decision_latency_ms",
    ]
    for key in keys:
        lines.append(f"| {key} | {development['metrics'][key]} | {holdout['metrics'][key]} |")
    return lines


def generate_reports(output: Path) -> None:
    expanded = json.loads((output / "expanded-evaluation-set.json").read_text(encoding="utf-8"))
    development_set = json.loads((output / "development-set.json").read_text(encoding="utf-8"))
    holdout_set = json.loads((output / "locked-holdout-set.json").read_text(encoding="utf-8"))
    candidates = json.loads((output / "threshold-candidates.json").read_text(encoding="utf-8"))
    selected = json.loads((output / "selected-thresholds.json").read_text(encoding="utf-8"))
    development = json.loads((output / "development-results.json").read_text(encoding="utf-8"))
    holdout = json.loads((output / "holdout-results.json").read_text(encoding="utf-8"))

    false_acceptance = result_review(
        "False acceptance review",
        holdout["results"],
        lambda row: row["decision"] == "supported" and not row["evaluation"]["valid_supported_decision"],
        "Locked-holdout questions accepted without the expected supporting passage. This includes "
        "both unanswerable questions and answerable questions supported by the wrong evidence.",
    )
    false_rejection = result_review(
        "False rejection review",
        holdout["results"],
        lambda row: row["answerable"] and row["decision"] != "supported",
        "Locked-holdout answerable questions rejected despite retrieval of the expected supporting passage.",
    )
    (output / "false-acceptance-review.md").write_text(false_acceptance, encoding="utf-8")
    (output / "false-rejection-review.md").write_text(false_rejection, encoding="utf-8")

    selected_thresholds = selected["thresholds"]
    lines = [
        "# AzerothCore Wiki abstention evaluation", "",
        "## Scope", "",
        "The mechanism was calibrated and evaluated only against the existing 12-file pilot "
        "(11 active semantic documents). It reused the existing A/B chunk embeddings and embedded "
        "only 64 queries. It did not normalize or embed additional wiki pages.", "",
        "## Evaluation composition", "",
        f"- Total: {expanded['composition']['total']}",
        f"- Answerable/unanswerable: {expanded['composition']['answerable']} / {expanded['composition']['unanswerable']}",
        f"- Development/locked holdout: {expanded['composition']['development']} / {expanded['composition']['locked_holdout']}",
        f"- Absence classes: {json.dumps(expanded['composition']['absence_classes'], sort_keys=True)}",
        f"- Manual review: {expanded['manual_review']}",
        "", "## Calibration", "",
        f"- Candidate configurations tested on development only: {candidates['candidate_count']}",
        f"- Selected candidate: {selected['calibration']['selected_candidate_id']}",
        f"- Threshold version: {selected['threshold_configuration_version']}",
        f"- Locked holdout accessed during calibration: {selected['calibration']['locked_holdout_accessed']}",
        f"- Selected thresholds: {json.dumps(selected_thresholds, sort_keys=True)}",
        "", "## Score normalization", "",
        f"- Dense: {selected['score_normalization']['dense']}",
        f"- Lexical: {selected['score_normalization']['lexical']}",
        f"- Hybrid: {selected['score_normalization']['hybrid']}",
        "- Raw dense, lexical, and fusion scores are never directly compared.",
        "", "## Metrics", "",
        *metrics_table(development, holdout),
        "", "## Locked-holdout gate", "",
    ]
    for name, passed in holdout["acceptance_gate"]["checks"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    lines += [
        "", f"Overall gate: **{'PASS' if holdout['acceptance_gate']['passed'] else 'FAIL'}**.", "",
        "## Neighbor evidence", "",
        "Expansion is limited to at most two same-document adjacent structural chunks. It requires "
        "primary relevance above the frozen floor plus measurable coverage, structural completion, "
        "or same-command-family gain. Neighbor content cannot lift a weak primary result above the "
        "no-relevance floor.", "",
        "## Limitations", "",
        "- These thresholds are source-commit, parser, model-digest, and pilot-build specific.",
        "- Corpus-size and score distributions will change after full-source ingestion; thresholds must be recalibrated.",
        "- This layer makes evidence decisions only and performs no answer synthesis.",
        "- Experimental thresholds are not automatically promoted.", "",
    ]
    (output / "abstention-evaluation.md").write_text("\n".join(lines), encoding="utf-8")

    required = [
        "expanded-evaluation-set.json", "development-set.json", "locked-holdout-set.json",
        "threshold-candidates.json", "selected-thresholds.json", "development-results.json",
        "holdout-results.json", "false-acceptance-review.md", "false-rejection-review.md",
        "abstention-evaluation.md",
    ]
    rejection_reasons = all(
        row["reason_codes"]
        for row in holdout["results"]
        if row["decision"] != "supported"
    )
    checks = {
        "expanded_set_has_64_questions": expanded["composition"]["total"] == 64,
        "balanced_answerable_unanswerable": expanded["composition"]["answerable"] == expanded["composition"]["unanswerable"] == 32,
        "balanced_development_holdout": len(development_set["questions"]) == len(holdout_set["questions"]) == 32,
        "every_question_has_manual_check": all(row.get("manual_check") for row in expanded["questions"]),
        "development_hash_matches_selected": development_set["questions_hash"] == selected["development_set_hash"],
        "holdout_locked_before_evaluation": holdout_set["locked"] and holdout_set["calibration_use_prohibited"],
        "holdout_not_used_for_calibration": selected["calibration"]["locked_holdout_accessed"] is False,
        "thresholds_unchanged_for_holdout": holdout["thresholds_changed_after_calibration"] is False,
        "hybrid_has_167_chunks": holdout["corpus_manifest"]["chunk_count"] == 167,
        "fixed_profile_c_absent": holdout["corpus_manifest"]["selected_profiles"] == ["a", "b"],
        "model_digest_and_dimensions_verified": (
            holdout["embedding"]["model_digest"] == MODEL_DIGEST
            and holdout["embedding"]["dimensions"] == DIMENSIONS
        ),
        "every_rejection_has_reason": rejection_reasons,
        "all_required_outputs_present": all((output / name).exists() for name in required),
        "acceptance_gate": holdout["acceptance_gate"]["passed"],
    }
    validation_lines = [
        "# Abstention validation report", "",
        f"Overall: **{'PASS' if all(checks.values()) else 'FAIL'}**.", "",
        "| Check | Result |", "|---|---:|",
    ]
    validation_lines += [
        f"| {name} | {'PASS' if passed else 'FAIL'} |"
        for name, passed in checks.items()
    ]
    validation_lines += [
        "", "Safeguards: existing bounded hybrid chunks only; 64 query embeddings only; "
        "no full-source processing, production vector collection, new source, raw-source acquisition, "
        "community/internal ingestion, generative answer synthesis, holdout tuning, or automatic promotion.", "",
    ]
    (output / "validation-report.md").write_text("\n".join(validation_lines), encoding="utf-8")


def query_once(
    query: str,
    selected_path: Path,
    chunk_experiment: Path,
    endpoint: str,
    model: str,
) -> dict[str, Any]:
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    chunks, vectors, corpus_manifest = load_hybrid_corpus(chunk_experiment)
    retriever = HybridEvidenceRetriever(chunks, vectors)
    info = model_info(endpoint, model)
    if info["digest"] != MODEL_DIGEST:
        raise ValueError("query model digest differs from calibrated model")
    query_vectors, latencies = embed(endpoint, model, [query], 1)
    features = retriever.retrieve(query, query_vectors[0], selected["thresholds"]["neighbor"])
    result = decide(features, selected["thresholds"])
    result["decision_latency_ms"] = round(
        result["retrieval_latency_ms"] + sum(latencies), 3
    )
    result["corpus_manifest"] = corpus_manifest
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--evaluation-config", required=True, type=Path)
    prepare_parser.add_argument("--chunk-experiment", required=True, type=Path)
    prepare_parser.add_argument("--output", required=True, type=Path)

    calibrate_parser = sub.add_parser("calibrate")
    calibrate_parser.add_argument("--development-set", required=True, type=Path)
    calibrate_parser.add_argument("--chunk-experiment", required=True, type=Path)
    calibrate_parser.add_argument("--output", required=True, type=Path)
    calibrate_parser.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434")
    calibrate_parser.add_argument("--model", default=MODEL)
    calibrate_parser.add_argument("--batch-size", type=int, default=8)

    holdout_parser = sub.add_parser("evaluate-holdout")
    holdout_parser.add_argument("--locked-holdout-set", required=True, type=Path)
    holdout_parser.add_argument("--selected-thresholds", required=True, type=Path)
    holdout_parser.add_argument("--chunk-experiment", required=True, type=Path)
    holdout_parser.add_argument("--output", required=True, type=Path)
    holdout_parser.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434")
    holdout_parser.add_argument("--model", default=MODEL)
    holdout_parser.add_argument("--batch-size", type=int, default=8)

    report_parser = sub.add_parser("report")
    report_parser.add_argument("--output", required=True, type=Path)

    query_parser = sub.add_parser("query")
    query_parser.add_argument("--query", required=True)
    query_parser.add_argument("--selected-thresholds", required=True, type=Path)
    query_parser.add_argument("--chunk-experiment", required=True, type=Path)
    query_parser.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434")
    query_parser.add_argument("--model", default=MODEL)

    args = parser.parse_args()
    if args.command == "prepare":
        materialize_evaluation_sets(
            args.evaluation_config, args.chunk_experiment, args.output
        )
    elif args.command == "calibrate":
        calibrate(
            args.development_set, args.chunk_experiment, args.output,
            args.ollama_endpoint, args.model, args.batch_size,
        )
    elif args.command == "evaluate-holdout":
        evaluate_holdout(
            args.locked_holdout_set, args.selected_thresholds,
            args.chunk_experiment, args.output,
            args.ollama_endpoint, args.model, args.batch_size,
        )
    elif args.command == "report":
        generate_reports(args.output)
    elif args.command == "query":
        print(json.dumps(query_once(
            args.query, args.selected_thresholds, args.chunk_experiment,
            args.ollama_endpoint, args.model,
        ), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
