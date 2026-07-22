import copy
import inspect
import unittest

from scripts.azerothcore_wiki_abstention import (
    HybridEvidenceRetriever,
    calibrate,
    decide,
    select_thresholds,
    threshold_candidates,
)


def feature(
    query="What does the evidence say?",
    explicit=None,
    matched=None,
    missing=None,
    primary=0.8,
    support=0.85,
    agreement=1.0,
    coverage=0.8,
    rare=0.8,
    identifier_context=0.8,
    relation=0.8,
    generic=False,
    top_document="doc_expected",
    evidence="Complete supporting evidence.",
):
    explicit = explicit or []
    matched = matched or []
    missing = missing or []
    return {
        "query": query,
        "query_analysis": {
            "language": "en", "tokens": ["complete", "evidence"],
            "rare_tokens": ["evidence"], "explicit_identifiers": explicit,
            "required_numbers": [],
        },
        "component_scores": {
            "dense_cosine": 0.7, "dense_normalized": 0.9,
            "bm25_score": 20.0, "lexical_normalized": 0.8,
            "rrf_score": 0.03, "hybrid_normalized": 0.9,
            "dense_margin": 0.2, "lexical_margin": 0.2, "hybrid_margin": 0.02,
            "dense_lexical_agreement": agreement, "independent_channel_count": 2,
            "query_token_coverage": coverage, "rare_token_coverage": rare,
            "identifier_context_coverage": identifier_context,
            "relation_coverage": relation, "title_heading_match": 0.5,
            "heading_match": True, "language_compatibility": 1.0,
            "evidence_completeness": 1.0, "primary_relevance": primary,
            "support_score": support,
        },
        "matched_identifiers": matched,
        "corpus_matched_identifiers": matched,
        "missing_identifiers": missing,
        "missing_top_identifiers": [],
        "matched_numbers": [], "missing_numbers": [], "conflict_signals": [],
        "incomplete_signals": [], "generic_keyword_only": generic,
        "neighbor_evidence": {"expanded": False, "chunk_ids": [], "reason_codes": []},
        "expanded_evidence": evidence,
        "top_evidence": [{
            "rank": 1, "chunk_id": "chunk_1", "document_id": top_document,
            "source_path": "docs/test.md", "title": "Test",
            "heading_path": ["Test"], "language": "en",
            "selected_hybrid_profile": "b", "structural_type": "mixed_structural",
            "dense_cosine": 0.7, "dense_normalized": 0.9,
            "bm25_score": 20.0, "rrf_score": 0.03, "content": evidence,
        }],
        "ranking": {
            "dense_top_document_id": top_document,
            "lexical_top_document_id": top_document,
            "hybrid_top_document_id": top_document,
            "hybrid_document_ranks": {top_document: 1},
        },
        "retrieval_latency_ms": 1.0,
    }


class AbstentionTests(unittest.TestCase):
    def setUp(self):
        self.thresholds = threshold_candidates()[0]

    def test_exact_real_command_accepted(self):
        result = decide(feature(
            query="What is `.damage` syntax?", explicit=[".damage"],
            matched=[".damage"], evidence=".damage $damage_amount [$school]",
        ), self.thresholds)
        self.assertEqual(result["decision"], "supported")
        self.assertIn("exact_identifier_match", result["reason_codes"])

    def test_exact_nonexistent_command_rejected(self):
        result = decide(feature(
            query="What is `.damageall` syntax?", explicit=[".damageall"],
            missing=[".damageall"], support=0.4,
        ), self.thresholds)
        self.assertEqual(result["decision"], "no_relevant_evidence")
        self.assertIn("identifier_absent", result["reason_codes"])

    def test_exact_real_configuration_key_accepted(self):
        result = decide(feature(
            query="What does `GDB_ENABLED=1` do?", explicit=["GDB_ENABLED=1"],
            matched=["GDB_ENABLED=1"], evidence="export GDB_ENABLED=1 enables GDB execution",
        ), self.thresholds)
        self.assertEqual(result["decision"], "supported")

    def test_similar_nonexistent_configuration_key_rejected(self):
        result = decide(feature(
            query="What does `GDB_ENABLE=1` do?", explicit=["GDB_ENABLE=1"],
            missing=["GDB_ENABLE=1"],
        ), self.thresholds)
        self.assertEqual(result["decision"], "no_relevant_evidence")

    def test_semantic_question_accepted(self):
        result = decide(feature(
            query="Why are database files squashed?",
            evidence="A clean install is quicker because updates are in base files.",
        ), self.thresholds)
        self.assertEqual(result["decision"], "supported")

    def test_generic_keyword_only_match_rejected(self):
        result = decide(feature(
            query="What server setting is used?", primary=0.4, support=0.45,
            coverage=0.2, rare=0.0, generic=True,
        ), self.thresholds)
        self.assertNotEqual(result["decision"], "supported")
        self.assertIn("generic_keyword_overlap", result["reason_codes"])

    def test_out_of_domain_question_rejected(self):
        result = decide(feature(
            query="How long should bread bake?", primary=0.1,
            support=0.2, coverage=0.1, rare=0.0,
        ), self.thresholds)
        self.assertEqual(result["decision"], "no_relevant_evidence")

    def test_missing_source_question_rejected(self):
        result = decide(feature(
            query="What did internal ticket `ENG-427` decide?",
            explicit=["ENG-427"], missing=["ENG-427"],
        ), self.thresholds)
        self.assertEqual(result["decision"], "no_relevant_evidence")

    def test_dense_lexical_disagreement_is_interpretable(self):
        thresholds = copy.deepcopy(self.thresholds)
        thresholds["require_dense_lexical_agreement"] = True
        result = decide(feature(agreement=0.0), thresholds)
        self.assertEqual(result["decision"], "insufficient_evidence")
        self.assertIn("conflicting_results", result["reason_codes"])

    def test_neighbor_expansion_requires_relevance_and_gain(self):
        chunks = [
            {
                "chunk_id": "one", "document_id": "doc", "content": "debug boundary",
                "title": "GM Commands", "heading_path": ["GM Commands"], "language": "en",
                "aliases": [], "structural_type": "command_family",
                "metadata": {"command_families": ["debug"]},
                "previous_chunk_id": None, "next_chunk_id": "two",
            },
            {
                "chunk_id": "two", "document_id": "doc", "content": "duration fill z",
                "title": "GM Commands", "heading_path": ["GM Commands"], "language": "en",
                "aliases": [], "structural_type": "command_family",
                "metadata": {"command_families": ["debug"]},
                "previous_chunk_id": "one", "next_chunk_id": None,
            },
        ]
        retriever = HybridEvidenceRetriever(chunks, [[1.0, 0.0], [0.9, 0.1]])
        selected, reasons = retriever._expand_neighbors(
            0, [0, 1], ["debug", "boundary", "duration"], 2 / 3, 0.8,
            {"min_primary_relevance": 0.3, "min_coverage_gain": 0.1, "max_neighbors": 2},
        )
        self.assertEqual(selected, [1])
        self.assertIn("command_family_neighbor", reasons)
        weak, _ = retriever._expand_neighbors(
            0, [0, 1], ["debug", "boundary", "duration"], 2 / 3, 0.1,
            {"min_primary_relevance": 0.3, "min_coverage_gain": 0.1, "max_neighbors": 2},
        )
        self.assertEqual(weak, [])

    def test_threshold_behavior_is_deterministic(self):
        item = feature(explicit=[".damage"], matched=[".damage"])
        self.assertEqual(decide(item, self.thresholds), decide(item, self.thresholds))

    def test_locked_holdout_isolation(self):
        self.assertNotIn("holdout", inspect.signature(calibrate).parameters)
        questions = [
            {
                "question_id": "dev-a", "question": "supported", "answerable": True,
                "expected_document_id": "doc_expected", "expected_source_path": "docs/test.md",
                "expected_heading_path": ["Test"], "expected_supporting_text": "Complete",
                "category": "semantic", "absence_class": None,
            },
            {
                "question_id": "dev-u", "question": "missing", "answerable": False,
                "expected_document_id": None, "expected_source_path": None,
                "expected_heading_path": [], "expected_supporting_text": None,
                "category": "missing", "absence_class": "out_of_domain",
            },
        ]
        rows = [
            {"question_id": "dev-a", "features": feature(evidence="Complete")},
            {"question_id": "dev-u", "features": feature(primary=0.1, support=0.1)},
        ]
        first = select_thresholds(questions, rows, "dev-hash", 0.0)[0]
        unrelated_locked_holdout = [{"question": "changed holdout label"}]
        second = select_thresholds(questions, rows, "dev-hash", 0.0)[0]
        self.assertEqual(first, second)
        self.assertFalse(first["calibration"]["locked_holdout_accessed"])
        self.assertTrue(unrelated_locked_holdout)


if __name__ == "__main__":
    unittest.main()
