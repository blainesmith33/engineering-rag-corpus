import json
import tempfile
import unittest
from pathlib import Path

from scripts.azerothcore_wiki_chunking import (
    PARSER_VERSION,
    classify,
    normalize_one,
    parse_front_matter,
    resolve_includes,
    sha256_bytes,
)


class NormalizationTests(unittest.TestCase):
    def test_front_matter_precedes_markdown(self):
        front, body, details = parse_front_matter(
            "---\nredirect_from: /Old\nflag: true\n---\n# Title\nBody\n"
        )
        self.assertEqual(front["redirect_from"], "/Old")
        self.assertTrue(front["flag"])
        self.assertEqual(body, "# Title\nBody\n")
        self.assertIsNone(details["front_matter_error"])

    def test_include_path_and_cycle_guards(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "_includes").mkdir()
            (root / "_includes" / "ok.html").write_text(
                "Note: {{include.content}}", encoding="utf-8"
            )
            (root / "_includes" / "cycle.html").write_text(
                "{% include cycle.html %}", encoding="utf-8"
            )
            normalized, included, unresolved = resolve_includes(
                '{% include ok.html content="safe fact" %}\n'
                "{% include ../secret.html %}\n"
                "{% include cycle.html %}\n",
                root,
            )
            self.assertIn("Note: safe fact", normalized)
            self.assertEqual(included, ["_includes/ok.html", "_includes/cycle.html"])
            self.assertTrue(any(x["reason"] == "include escapes approved root" for x in unresolved))
            self.assertTrue(any(x["reason"] == "include cycle" for x in unresolved))

    def test_placeholder_exclusion(self):
        status, reason, target = classify("## Work in progress\n", {})
        self.assertEqual(status, "excluded_placeholder")
        self.assertEqual(reason, "placeholder-only page")
        self.assertIsNone(target)

    def test_document_identity_and_hash_are_repeatable(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "docs").mkdir()
            (root / "_includes").mkdir()
            (root / "docs" / "page.md").write_text("# Fact\n\nUseful fact.\n", encoding="utf-8")
            entry = {"relative_path": "docs/page.md", "reasons": ["test"]}
            first = normalize_one(root, entry)
            second = normalize_one(root, entry)
            self.assertEqual(first["document_id"], second["document_id"])
            self.assertEqual(first["normalized_content_hash"], second["normalized_content_hash"])
            self.assertEqual(
                first["normalized_content_hash"],
                sha256_bytes(first["normalized_content"].encode("utf-8")),
            )
            self.assertEqual(first["parser_version"], PARSER_VERSION)


if __name__ == "__main__":
    unittest.main()
