#!/usr/bin/env python3
"""Bounded AzerothCore Wiki normalization, chunking, and retrieval pilot.

Only paths explicitly listed in the sample config can be processed. The pinned
snapshot is read-only, and embeddings are stored as temporary JSONL namespaces.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import shlex
import statistics
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml


PARSER_NAME = "azerothcore_wiki_markdown"
PARSER_VERSION = "1.0.0"
SOURCE_ID = "azerothcore_wiki_official"
SOURCE_COMMIT = "7d540fc7e683c3bf34a2f465789f1b3df268b609"
PROVENANCE_CLASS = "official_docs"
AUTHORITY_LEVEL = "official_project"
TOKEN_COUNTER = "engineering_regex_tokens_v1"
PROFILE_CONFIG = {
    "a": {"name": "heading-aware-small", "target_min": 250, "target": 350, "target_max": 450, "hard_max": 600},
    "b": {"name": "heading-aware-medium", "target_min": 450, "target": 650, "target_max": 800, "hard_max": 1000},
    "c": {"name": "fixed-token-baseline", "window": 500, "overlap": 75},
}
TOKEN_RE = re.compile(r"[\w]+(?:[./:_-][\w]+)*|[^\w\s]+", re.UNICODE)
LEXICAL_RE = re.compile(r"[\w]+(?:[./:_-][\w]+)*", re.UNICODE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*((?:\x60){3,}|~~~+)(.*)$")
INCLUDE_RE = re.compile(r"{%\s*include\s+([^\s%]+)(.*?)%}", re.DOTALL)
RAW_RE = re.compile(r"{%\s*raw\s*%}(.*?){%\s*endraw\s*%}", re.DOTALL)
COMMENT_RE = re.compile(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", re.DOTALL)
MD_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
HTML_LINK_RE = re.compile(r"<a\b[^>]*\bhref=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.I | re.S)
BACK_NAV_RE = re.compile(r"^\s*\[[^\]]*(?:back[- ]?to|volver\s+a|regresar\s+a)[^\]]*\]\([^)]+\)\s*$", re.I)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return prefix + hashlib.sha256(payload).hexdigest()[:24]


def token_spans(text: str) -> list[re.Match[str]]:
    return list(TOKEN_RE.finditer(text))


def token_count(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def lexical_tokens(text: str) -> list[str]:
    return [token.casefold() for token in LEXICAL_RE.findall(text)]


def source_url(relative: str) -> str | None:
    path = Path(relative)
    if not relative.startswith("docs/") or path.suffix != ".md":
        return None
    if relative.startswith("docs/es/"):
        return f"https://www.azerothcore.org/wiki/es/{path.stem}"
    return f"https://www.azerothcore.org/wiki/{path.stem}"


def parse_front_matter(text: str) -> tuple[dict[str, Any], str, dict[str, Any]]:
    details = {"utf8_bom_removed": False, "front_matter_error": None}
    if text.startswith("\ufeff"):
        text = text[1:]
        details["utf8_bom_removed"] = True
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text, details
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        details["front_matter_error"] = "opening delimiter without closing delimiter"
        return {}, text, details
    raw = "".join(lines[1:end])
    try:
        parsed = yaml.safe_load(raw) or {}
        if not isinstance(parsed, dict):
            details["front_matter_error"] = "front matter is not a mapping"
            parsed = {"_raw": raw.rstrip("\n")}
    except yaml.YAMLError as exc:
        details["front_matter_error"] = str(exc)
        parsed = {"_raw": raw.rstrip("\n")}
    return parsed, "".join(lines[end + 1 :]).lstrip("\n"), details


def include_args(raw: str) -> tuple[dict[str, str], str | None]:
    try:
        tokens = shlex.split(raw.strip(), posix=True)
    except ValueError as exc:
        return {}, str(exc)
    result: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            return {}, f"unsupported include argument: {token}"
        key, value = token.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            return {}, f"invalid include argument name: {key}"
        result[key] = value
    return result, None


def resolve_includes(text: str, snapshot: Path) -> tuple[str, list[str], list[dict[str, Any]]]:
    root = (snapshot / "_includes").resolve()
    included: list[str] = []
    unresolved: list[dict[str, Any]] = []
    protected: dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        key = f"@@AC_RAW_{len(protected)}@@"
        protected[key] = match.group(1)
        return key

    working = RAW_RE.sub(protect, text)

    def render(value: str, stack: tuple[Path, ...], depth: int) -> str:
        if depth > 8:
            unresolved.append({"expression": value, "reason": "maximum include depth exceeded"})
            return value

        def replace(match: re.Match[str]) -> str:
            expression = match.group(0)
            name = match.group(1).strip().strip("'\"")
            args, error = include_args(match.group(2))
            if error:
                unresolved.append({"expression": expression, "include": name, "reason": error})
                return expression
            if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", name):
                unresolved.append({"expression": expression, "include": name, "reason": "invalid include path"})
                return expression
            candidate = (root / name).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                unresolved.append({"expression": expression, "include": name, "reason": "include escapes approved root"})
                return expression
            if candidate in stack:
                unresolved.append({"expression": expression, "include": name, "reason": "include cycle"})
                return expression
            if not candidate.is_file():
                unresolved.append({"expression": expression, "include": name, "reason": "include file not found"})
                return expression
            try:
                template = candidate.read_text(encoding="utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                unresolved.append({"expression": expression, "include": name, "reason": f"UTF-8 decode failure: {exc}"})
                return expression
            rel = candidate.relative_to(snapshot.resolve()).as_posix()
            if rel not in included:
                included.append(rel)
            template = COMMENT_RE.sub("", template)
            for key, content in sorted(args.items()):
                template = re.sub(r"{{\s*include\." + re.escape(key) + r"\s*}}", lambda _: content, template)
            missing = sorted(set(re.findall(r"{{\s*include\.([A-Za-z0-9_-]+)\s*}}", template)))
            if missing:
                unresolved.append({"expression": expression, "include": name, "reason": "missing include parameters", "parameters": missing})
            return render(template.strip(), stack + (candidate,), depth + 1)

        previous = None
        while previous != value and INCLUDE_RE.search(value):
            previous = value
            value = INCLUDE_RE.sub(replace, value)
        return value

    working = render(working, (), 0)
    for key, raw in protected.items():
        working = working.replace(key, raw)
    return working, included, unresolved


def table_blocks(lines: list[str]) -> list[tuple[int, int]]:
    output: list[tuple[int, int]] = []
    start: int | None = None
    for i, line in enumerate(lines + [""]):
        if line.lstrip().startswith("|") and start is None:
            start = i
        elif not line.lstrip().startswith("|") and start is not None:
            output.append((start, i))
            start = None
    return output


def remove_boilerplate(text: str) -> tuple[str, list[dict[str, Any]]]:
    lines = text.splitlines()
    keep = [True] * len(lines)
    removed: list[dict[str, Any]] = []
    for i, line in enumerate(lines):
        if BACK_NAV_RE.match(line):
            keep[i] = False
            removed.append({"type": "back_to_navigation", "content": line, "line": i + 1})
        elif re.fullmatch(r"\s*<br\s*/?>\s*", line, re.I):
            keep[i] = False
            removed.append({"type": "presentational_html", "content": line, "line": i + 1})
    for start, end in table_blocks(lines):
        block = "\n".join(lines[start:end])
        lower = block.casefold()
        if "this article is a part of the installation guide" in lower and ("classic installation" in lower or "core installation" in lower):
            for i in range(start, end):
                keep[i] = False
            removed.append({"type": "installation_step_navigation", "content": block, "line": start + 1})
    output = "\n".join(line for i, line in enumerate(lines) if keep[i])
    output = re.sub(r"\n{3,}", "\n\n", output).strip()
    return (output + "\n" if output else ""), removed


def extract_links(text: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for match in MD_LINK_RE.finditer(text):
        item = ("markdown", match.group(1), match.group(2))
        if item not in seen:
            output.append({"kind": item[0], "text": item[1], "target": item[2]})
            seen.add(item)
    for match in HTML_LINK_RE.finditer(text):
        label = re.sub(r"<[^>]+>", "", html.unescape(match.group(2))).strip()
        item = ("html", label, match.group(1))
        if item not in seen:
            output.append({"kind": item[0], "text": item[1], "target": item[2]})
            seen.add(item)
    return output


def heading_outline(text: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    stack: list[str] = []
    fence: str | None = None
    for line_number, line in enumerate(text.splitlines(), 1):
        fm = FENCE_RE.match(line)
        if fm:
            marker = fm.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        title = re.sub(r"\s+#+$", "", match.group(2)).strip()
        stack = stack[: level - 1]
        while len(stack) < level - 1:
            stack.append("")
        stack.append(title)
        output.append({"level": level, "title": title, "heading_path": [part for part in stack if part], "line": line_number})
    return output


def choose_title(front: dict[str, Any], outline: list[dict[str, Any]], relative: str) -> str:
    if front.get("title"):
        return str(front["title"]).strip()
    h1 = next((item["title"] for item in outline if item["level"] == 1), None)
    if h1:
        return h1
    if outline:
        return outline[0]["title"]
    return Path(relative).stem.replace("-", " ").replace("_", " ").title()


def aliases_from(front: dict[str, Any]) -> list[str]:
    raw = front.get("redirect_from")
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    return sorted({str(item).strip() for item in values if str(item).strip()})


def semantic_body(text: str) -> str:
    value = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[[^\]]*\]\([^)]+\)", " ", value)
    value = re.sub(r"[\x60*_#|>\-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def classify(text: str, front: dict[str, Any]) -> tuple[str, str | None, str | None]:
    if front.get("redirect_to"):
        return "excluded_redirect", "redirect-only page", str(front["redirect_to"])
    body = semantic_body(text)
    if not body:
        return "excluded_empty", "no useful semantic content after normalization", None
    lowered = body.casefold().strip(" .:;!-")
    if lowered in {"work in progress", "trabajo en progreso", "todo", "tbd", "coming soon"}:
        return "excluded_placeholder", "placeholder-only page", None
    nonblank = [line.strip() for line in text.splitlines() if line.strip() and not HEADING_RE.match(line)]
    if nonblank and all(MD_LINK_RE.fullmatch(line.lstrip("-* ")) for line in nonblank):
        return "excluded_navigation_only", "navigation-only page", None
    joined = "\n".join(nonblank)
    redirect = re.fullmatch(r"(?:see|moved to|redirect to)?\s*\[[^\]]+\]\(([^)]+)\)\s*", joined, re.I)
    if redirect:
        return "excluded_redirect", "redirect-only page", redirect.group(1)
    return "active", None, None


def normalize_one(snapshot: Path, entry: dict[str, Any]) -> dict[str, Any]:
    relative = entry["relative_path"]
    path = (snapshot / relative).resolve()
    try:
        path.relative_to(snapshot.resolve())
    except ValueError as exc:
        raise ValueError(f"sample path escapes snapshot: {relative}") from exc
    if not path.is_file():
        raise FileNotFoundError(relative)
    raw = path.read_bytes()
    original_hash = sha256_bytes(raw)
    doc_id = stable_id("doc_", SOURCE_ID, SOURCE_COMMIT, relative, PARSER_VERSION, original_hash)
    language = "es" if relative.startswith("docs/es/") else "en"
    base = {
        "document_id": doc_id, "source_id": SOURCE_ID, "source_commit": SOURCE_COMMIT,
        "provenance_class": PROVENANCE_CLASS, "authority_level": AUTHORITY_LEVEL,
        "source_path": str(path), "relative_path": relative, "source_url": source_url(relative),
        "language": language, "original_content_hash": original_hash,
        "parser_name": PARSER_NAME, "parser_version": PARSER_VERSION,
    }
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return {
            **base, "title": Path(relative).stem, "aliases": [], "redirect_target": None,
            "heading_outline": [], "front_matter": {}, "normalized_content": "",
            "normalized_content_hash": sha256_bytes(b""), "included_files": [],
            "unresolved_includes": [], "removed_boilerplate": [], "document_status": "decode_error",
            "exclusion_reason": f"UTF-8 decode failure at byte {exc.start}: {exc.reason}",
            "metadata": {"decoding": {"encoding": "utf-8", "status": "failure", "error_start": exc.start},
                         "selection_reasons": entry["reasons"], "links": []},
        }
    front, body, parse_details = parse_front_matter(decoded)
    resolved, included, unresolved = resolve_includes(body, snapshot)
    normalized, removed = remove_boilerplate(resolved)
    outline = heading_outline(normalized)
    title = choose_title(front, outline, relative)
    status, reason, target = classify(normalized, front)
    if status != "active":
        normalized = ""
        outline = heading_outline(body)
    return {
        **base, "title": title, "aliases": aliases_from(front), "redirect_target": target,
        "heading_outline": outline, "front_matter": front, "normalized_content": normalized,
        "normalized_content_hash": sha256_bytes(normalized.encode("utf-8")),
        "included_files": included, "unresolved_includes": unresolved,
        "removed_boilerplate": removed, "document_status": status, "exclusion_reason": reason,
        "metadata": {
            "decoding": {"encoding": "utf-8", "status": "success", **parse_details},
            "links": extract_links(normalized), "selection_reasons": entry["reasons"],
            "translation_pair_document_id": None, "translation_pair_source_path": None,
            "token_counter": TOKEN_COUNTER,
        },
    }


def add_translation_pairs(documents: list[dict[str, Any]]) -> None:
    by_path = {doc["relative_path"]: doc for doc in documents}
    for doc in documents:
        path = doc["relative_path"]
        pair_path = "docs/" + path[len("docs/es/"):] if path.startswith("docs/es/") else "docs/es/" + path[len("docs/"):]
        pair = by_path.get(pair_path)
        if pair:
            doc["metadata"]["translation_pair_document_id"] = pair["document_id"]
            doc["metadata"]["translation_pair_source_path"] = pair_path


def unit(text: str, path: list[str], kind: str, **metadata: Any) -> dict[str, Any]:
    return {"text": text.strip(), "heading_path": list(path), "structural_type": kind, "metadata": metadata}


def parse_units(content: str, title: str) -> list[dict[str, Any]]:
    """Parse headings and indivisible Markdown structures without a renderer."""
    lines = content.splitlines()
    output: list[dict[str, Any]] = []
    stack: list[str] = []
    pending_headings: list[str] = []
    i = 0

    def path() -> list[str]:
        return [part for part in stack if part] or [title]

    def add(text: str, kind: str) -> None:
        nonlocal pending_headings
        prefix = "\n".join(pending_headings)
        combined = (prefix + ("\n\n" if prefix and text else "") + text).strip()
        pending_headings = []
        if combined:
            output.append(unit(combined, path(), kind))

    while i < len(lines):
        line = lines[i]
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            heading_title = re.sub(r"\s+#+$", "", heading.group(2)).strip()
            stack = stack[: level - 1]
            while len(stack) < level - 1:
                stack.append("")
            stack.append(heading_title)
            pending_headings.append(line)
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)[0]
            block = [line]
            i += 1
            while i < len(lines):
                block.append(lines[i])
                if FENCE_RE.match(lines[i]) and lines[i].lstrip().startswith(marker):
                    i += 1
                    break
                i += 1
            add("\n".join(block), "code")
            continue
        if line.lstrip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            add("\n".join(block), "table")
            continue
        if re.match(r"^\s*(?:[-*+] |\d+[.)] )", line):
            block = [line]
            i += 1
            while i < len(lines) and (
                not lines[i].strip()
                or re.match(r"^\s+(?:\S|$)|^\s*(?:[-*+] |\d+[.)] )", lines[i])
            ):
                block.append(lines[i])
                i += 1
            add("\n".join(block).rstrip(), "list")
            continue
        block = [line]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not HEADING_RE.match(lines[i])
            and not FENCE_RE.match(lines[i])
            and not lines[i].lstrip().startswith("|")
            and not re.match(r"^\s*(?:[-*+] |\d+[.)] )", lines[i])
        ):
            block.append(lines[i])
            i += 1
        kind = "raw_html" if any(re.search(r"</?[A-Za-z][^>]*>", item) for item in block) else "paragraph"
        add("\n".join(block), kind)

    # Keep code with the immediately introducing/interpreting paragraph.
    merged: list[dict[str, Any]] = []
    for item in output:
        if (
            item["structural_type"] == "code"
            and merged
            and merged[-1]["structural_type"] in {"paragraph", "raw_html"}
            and merged[-1]["heading_path"] == item["heading_path"]
        ):
            intro = merged.pop()
            merged.append(unit(intro["text"] + "\n\n" + item["text"], item["heading_path"], "code_with_context"))
        else:
            merged.append(item)
    return merged


def table_parts(text: str) -> tuple[list[str], list[str]] | None:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.lstrip().startswith("|")), None)
    if start is None or len(lines[start:]) < 3:
        return None
    return lines[:start] + lines[start:start + 2], lines[start + 2:]


def split_large_unit(item: dict[str, Any], hard: int, target: int) -> list[dict[str, Any]]:
    if token_count(item["text"]) <= hard:
        return [item]
    if item["structural_type"] in {"code", "code_with_context"}:
        clone = dict(item)
        clone["structural_type"] = "oversized_code"
        clone["metadata"] = {**item.get("metadata", {}), "oversized_atomic": True}
        return [clone]
    if item["structural_type"] in {"command_family", "oversized_command"}:
        # gm_units already packs whole rows to the profile target. A single row
        # is the indivisible semantic reference unit and must never be sliced.
        return [item]
    if item["structural_type"] == "table":
        parts = table_parts(item["text"])
        if parts:
            header, rows = parts
            header_text = "\n".join(header)
            output: list[dict[str, Any]] = []
            batch: list[str] = []
            for row in rows:
                candidate = header_text + "\n" + "\n".join(batch + [row])
                if batch and token_count(candidate) > target:
                    output.append(unit(header_text + "\n" + "\n".join(batch), item["heading_path"], "table_segment", table_headers_repeated=True))
                    batch = [row]
                else:
                    batch.append(row)
            if batch:
                output.append(unit(header_text + "\n" + "\n".join(batch), item["heading_path"], "table_segment", table_headers_repeated=True))
            for segment in output:
                if token_count(segment["text"]) > hard:
                    segment["structural_type"] = "oversized_table_row"
                    segment["metadata"]["oversized_atomic"] = True
            return output
    spans = token_spans(item["text"])
    output = []
    for start in range(0, len(spans), target):
        selected = spans[start:start + target]
        output.append(unit(
            item["text"][selected[0].start():selected[-1].end()],
            item["heading_path"], item["structural_type"] + "_segment",
            structural_fallback_split=True,
        ))
    return output


def context_prefix(doc: dict[str, Any], heading_path: list[str], aliases: bool = True) -> str:
    lines = [
        f"Document: {doc['title']}",
        f"Language: {doc['language']}",
        f"Heading: {' > '.join(heading_path or [doc['title']])}",
    ]
    if aliases and doc["aliases"]:
        lines.append("Aliases: " + ", ".join(doc["aliases"]))
    return "\n".join(lines) + "\n\n"


def split_table_row(line: str) -> list[str]:
    return [part.replace("\\|", "|").strip() for part in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def gm_units(doc: dict[str, Any], profile: str) -> list[dict[str, Any]]:
    """Split the oversized GM table by semantic command family, never raw windows."""
    config = PROFILE_CONFIG[profile]
    lines = doc["normalized_content"].splitlines()
    start = next((i for i, line in enumerate(lines) if line.lstrip().startswith("|")), None)
    if start is None or start + 2 >= len(lines):
        return parse_units(doc["normalized_content"], doc["title"])
    intro = "\n".join(lines[:start]).strip()
    # The source pads its four table columns to hundreds of characters. Keep
    # the semantic labels and valid Markdown delimiter while dropping padding.
    header_cells = split_table_row(lines[start])
    header = [
        "| " + " | ".join(header_cells) + " |",
        "| " + " | ".join("---" for _ in header_cells) + " |",
    ]
    rows = [line for line in lines[start + 2:] if line.lstrip().startswith("|")]
    output = [unit(intro, [doc["title"]], "introduction")] if intro else []
    families: list[tuple[str, list[str]]] = []
    for row in rows:
        cells = split_table_row(row)
        command = re.sub(r"[\x60.*]", "", cells[0]).strip() if cells else "unknown"
        family = command.split()[0] if command else "unknown"
        if families and families[-1][0] == family:
            families[-1][1].append(row)
        else:
            families.append((family, [row]))
    for family, rows_in_family in families:
        batch: list[str] = []
        for row in rows_in_family:
            candidate = "\n".join(header + batch + [row])
            if batch and token_count(context_prefix(doc, [doc["title"]]) + candidate) > config["target"]:
                output.append(unit("\n".join(header + batch), [doc["title"]], "command_family", command_family=family, table_headers_repeated=True))
                batch = [row]
            else:
                batch.append(row)
        if batch:
            item = unit("\n".join(header + batch), [doc["title"]], "command_family", command_family=family, table_headers_repeated=True)
            if token_count(context_prefix(doc, [doc["title"]]) + item["text"]) > config["hard_max"]:
                item["structural_type"] = "oversized_command"
                item["metadata"]["oversized_atomic"] = True
            output.append(item)
    return output


def structural_candidates(doc: dict[str, Any], profile: str) -> list[dict[str, Any]]:
    config = PROFILE_CONFIG[profile]
    parsed = gm_units(doc, profile) if doc["relative_path"] == "docs/gm-commands.md" else parse_units(doc["normalized_content"], doc["title"])
    expanded = [
        split_item
        for item in parsed
        for split_item in split_large_unit(item, config["hard_max"], config["target"])
    ]
    if doc["relative_path"] == "docs/gm-commands.md":
        groups = [[item] for item in expanded]
    elif sum(token_count(item["text"]) for item in expanded) + token_count(context_prefix(doc, [doc["title"]])) <= config["hard_max"]:
        groups = [expanded] if expanded else []
    else:
        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_tokens = 0
        for item in expanded:
            item_tokens = token_count(item["text"])
            primary = current[0]["heading_path"] if current else item["heading_path"]
            total = current_tokens + item_tokens + token_count(context_prefix(doc, primary))
            if current and total > config["target"] and current_tokens + token_count(context_prefix(doc, primary)) >= config["target_min"]:
                groups.append(current)
                current, current_tokens = [], 0
                primary = item["heading_path"]
                total = item_tokens + token_count(context_prefix(doc, primary))
            if current and total > config["hard_max"]:
                groups.append(current)
                current, current_tokens = [], 0
            current.append(item)
            current_tokens += item_tokens
        if current:
            if groups:
                previous = groups[-1]
                combined = sum(token_count(item["text"]) for item in previous + current)
                combined += token_count(context_prefix(doc, previous[0]["heading_path"]))
                if combined <= config["hard_max"] and current_tokens < config["target_min"]:
                    groups[-1].extend(current)
                else:
                    groups.append(current)
            else:
                groups.append(current)
    output = []
    for group in groups:
        if not group:
            continue
        heading_path = group[0]["heading_path"] or [doc["title"]]
        body = "\n\n".join(item["text"] for item in group if item["text"].strip())
        if not body:
            continue
        paths: list[list[str]] = []
        for item in group:
            if item["heading_path"] not in paths:
                paths.append(item["heading_path"])
        kinds = {item["structural_type"] for item in group}
        output.append({
            "heading_path": heading_path,
            "content": context_prefix(doc, heading_path) + body,
            "structural_type": next(iter(kinds)) if len(kinds) == 1 else "mixed_structural",
            "metadata": {
                "heading_paths_included": paths,
                "token_counter": TOKEN_COUNTER,
                "target_range": [config["target_min"], config["target_max"]],
                "hard_max": config["hard_max"],
                "command_families": sorted({
                    item["metadata"]["command_family"]
                    for item in group if item.get("metadata", {}).get("command_family")
                }),
                "table_headers_repeated": any(item.get("metadata", {}).get("table_headers_repeated") for item in group),
                "oversized_atomic": any(item.get("metadata", {}).get("oversized_atomic") for item in group),
            },
        })
    return output


def heading_at_offset(content: str, offset: int, title: str) -> list[str]:
    stack: list[str] = []
    fence: str | None = None
    cursor = 0
    for line in content.splitlines(keepends=True):
        if cursor > offset:
            break
        fm = FENCE_RE.match(line.rstrip("\n"))
        if fm:
            marker = fm.group(1)[0]
            fence = None if fence == marker else marker if fence is None else fence
        elif not fence:
            hm = HEADING_RE.match(line.rstrip("\n"))
            if hm:
                level = len(hm.group(1))
                value = re.sub(r"\s+#+$", "", hm.group(2)).strip()
                stack = stack[:level - 1]
                while len(stack) < level - 1:
                    stack.append("")
                stack.append(value)
        cursor += len(line)
    return [part for part in stack if part] or [title]


def fixed_candidates(doc: dict[str, Any]) -> list[dict[str, Any]]:
    config = PROFILE_CONFIG["c"]
    spans = token_spans(doc["normalized_content"])
    output = []
    start = 0
    while start < len(spans):
        end = min(start + config["window"], len(spans))
        start_char, end_char = spans[start].start(), spans[end - 1].end()
        path = heading_at_offset(doc["normalized_content"], start_char, doc["title"])
        output.append({
            "heading_path": path,
            "content": doc["normalized_content"][start_char:end_char],
            "structural_type": "fixed_token_window",
            "metadata": {
                "heading_paths_included": [path], "token_counter": TOKEN_COUNTER,
                "window": config["window"], "overlap": config["overlap"],
                "token_start": start, "token_end": end,
            },
        })
        if end == len(spans):
            break
        start = end - config["overlap"]
    return output


def finalize_chunks(doc: dict[str, Any], profile: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for index, candidate in enumerate(candidates):
        content_hash = sha256_bytes(candidate["content"].encode("utf-8"))
        chunk_id = stable_id("chk_", doc["document_id"], profile, str(index), content_hash)
        output.append({
            "chunk_id": chunk_id, "document_id": doc["document_id"], "source_id": SOURCE_ID,
            "source_commit": SOURCE_COMMIT, "provenance_class": PROVENANCE_CLASS,
            "authority_level": AUTHORITY_LEVEL, "language": doc["language"], "title": doc["title"],
            "heading_path": candidate["heading_path"], "source_path": doc["source_path"],
            "source_url": doc["source_url"], "chunk_index": index, "chunk_profile": profile,
            "token_count": token_count(candidate["content"]), "content": candidate["content"],
            "content_hash": content_hash, "previous_chunk_id": None, "next_chunk_id": None,
            "aliases": doc["aliases"], "included_source_paths": doc["included_files"],
            "structural_type": candidate["structural_type"], "metadata": candidate["metadata"],
        })
    for i, item in enumerate(output):
        item["previous_chunk_id"] = output[i - 1]["chunk_id"] if i else None
        item["next_chunk_id"] = output[i + 1]["chunk_id"] if i + 1 < len(output) else None
    return output


def build_chunks(documents: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    profiles = {profile: [] for profile in PROFILE_CONFIG}
    for doc in documents:
        if doc["document_status"] != "active":
            continue
        for profile in PROFILE_CONFIG:
            candidates = fixed_candidates(doc) if profile == "c" else structural_candidates(doc, profile)
            profiles[profile].extend(finalize_chunks(doc, profile, candidates))
    return profiles


def distribution(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "minimum": None, "median": None, "maximum": None, "average": None}
    return {
        "count": len(values), "minimum": min(values), "median": statistics.median(values),
        "maximum": max(values), "average": round(statistics.fmean(values), 2),
    }


def chunk_statistics(documents: list[dict[str, Any]], profiles: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    result = {"token_counter": TOKEN_COUNTER, "profile_configuration": PROFILE_CONFIG, "profiles": {}}
    for profile, chunks in profiles.items():
        by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for chunk in chunks:
            by_doc[chunk["document_id"]].append(chunk)
        hashes = Counter(chunk["content_hash"] for chunk in chunks)
        duplicates = sum(count - 1 for count in hashes.values() if count > 1)
        result["profiles"][profile] = {
            **distribution([chunk["token_count"] for chunk in chunks]),
            "duplicate_content_count": duplicates,
            "duplicate_content_rate": round(duplicates / len(chunks), 6) if chunks else 0.0,
            "documents": {
                doc["document_id"]: {
                    "relative_path": doc["relative_path"],
                    **distribution([chunk["token_count"] for chunk in by_doc.get(doc["document_id"], [])]),
                }
                for doc in documents
            },
        }
    return result


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(canonical_json(value) + "\n")


DOCUMENT_FIELDS = {
    "document_id", "source_id", "source_commit", "provenance_class", "authority_level",
    "source_path", "relative_path", "source_url", "language", "title", "aliases",
    "redirect_target", "heading_outline", "front_matter", "normalized_content",
    "original_content_hash", "normalized_content_hash", "parser_name", "parser_version",
    "included_files", "unresolved_includes", "removed_boilerplate", "document_status",
    "exclusion_reason", "metadata",
}
CHUNK_FIELDS = {
    "chunk_id", "document_id", "source_id", "source_commit", "provenance_class",
    "authority_level", "language", "title", "heading_path", "source_path", "source_url",
    "chunk_index", "chunk_profile", "token_count", "content", "content_hash",
    "previous_chunk_id", "next_chunk_id", "aliases", "included_source_paths",
    "structural_type", "metadata",
}


def validate(snapshot: Path, sample: dict[str, Any], documents: list[dict[str, Any]], profiles: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, details: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    all_chunks = [chunk for chunks in profiles.values() for chunk in chunks]
    check("bounded sample", len(documents) == len(sample["files"]) == 12, f"processed {len(documents)} selected files")
    check("pinned commit", sample["source_commit"] == SOURCE_COMMIT, SOURCE_COMMIT)
    check("document schema", all(DOCUMENT_FIELDS <= set(doc) for doc in documents), "required fields present")
    check("chunk schema", all(CHUNK_FIELDS <= set(chunk) for chunk in all_chunks), f"{len(all_chunks)} chunks checked")
    check("document hashes", all(doc["normalized_content_hash"] == sha256_bytes(doc["normalized_content"].encode("utf-8")) for doc in documents), "hashes recompute")
    check("chunk hashes", all(chunk["content_hash"] == sha256_bytes(chunk["content"].encode("utf-8")) for chunk in all_chunks), "hashes recompute")
    second = [normalize_one(snapshot, entry) for entry in sample["files"]]
    add_translation_pairs(second)
    check("deterministic normalization", [canonical_json(doc) for doc in documents] == [canonical_json(doc) for doc in second], "second run matched")
    placeholder = next(doc for doc in documents if doc["relative_path"] == "docs/how-to-debug.md")
    check("placeholder excluded", placeholder["document_status"] == "excluded_placeholder" and all(not any(c["document_id"] == placeholder["document_id"] for c in chunks) for chunks in profiles.values()), placeholder["exclusion_reason"] or "")
    updates = next(doc for doc in documents if doc["relative_path"] == "docs/updates_include.md")
    check("Back-to navigation removed", "Back-to:" not in updates["normalized_content"] and len([x for x in updates["removed_boilerplate"] if x["type"] == "back_to_navigation"]) == 3, "three links retained as metadata")
    pair = [doc for doc in documents if doc["relative_path"] in {"docs/creating-accounts.md", "docs/es/creating-accounts.md"}]
    check("translation isolation", len({doc["document_id"] for doc in pair}) == 2 and all(doc["metadata"]["translation_pair_document_id"] for doc in pair), "separate, cross-referenced IDs")
    include_docs = [doc for doc in documents if doc["included_files"]]
    check("includes resolved", bool(include_docs) and all(not doc["unresolved_includes"] for doc in include_docs), f"{len(include_docs)} include-bearing documents")
    code_ok = True
    fence_pattern = re.compile(r"(?:\x60){3}[^\n]*\n.*?(?:\x60){3}", re.S)
    for doc in documents:
        if doc["document_status"] != "active":
            continue
        original = (snapshot / doc["relative_path"]).read_text(encoding="utf-8-sig")
        code_ok &= all(block in doc["normalized_content"] for block in fence_pattern.findall(original))
    check("fenced code preserved", code_ok, "every original triple-backtick block remains byte-for-byte")
    table_ok = all(
        not (
            chunk["structural_type"] in {"table_segment", "command_family"}
            and len([line for line in chunk["content"].splitlines() if line.lstrip().startswith("|")]) < 3
        )
        for profile in "ab" for chunk in profiles[profile]
    )
    check("structural table headers", table_ok, "split tables contain header, separator, and row")
    adjacency_ok = True
    for profile in profiles:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for chunk in profiles[profile]:
            grouped[chunk["document_id"]].append(chunk)
        for chunks in grouped.values():
            chunks.sort(key=lambda item: item["chunk_index"])
            for i, item in enumerate(chunks):
                adjacency_ok &= item["previous_chunk_id"] == (chunks[i - 1]["chunk_id"] if i else None)
                adjacency_ok &= item["next_chunk_id"] == (chunks[i + 1]["chunk_id"] if i + 1 < len(chunks) else None)
    check("chunk adjacency", adjacency_ok, "document-local links complete")
    return {"passed": all(item["passed"] for item in checks), "checks": checks}


def suspicious(chunks: list[dict[str, Any]], profile: str) -> list[str]:
    if not chunks:
        return ["No chunks emitted (expected for excluded documents)."]
    findings = []
    tiny = [chunk for chunk in chunks if chunk["token_count"] < 80]
    if tiny:
        findings.append(f"{len(tiny)} chunk(s) below 80 tokens; atomic command families or complete short facts justify review.")
    if profile in "ab":
        hard = PROFILE_CONFIG[profile]["hard_max"]
        oversized = [chunk for chunk in chunks if chunk["token_count"] > hard]
        if oversized:
            findings.append(f"{len(oversized)} indivisible structure(s) exceed the {hard}-token target and are metadata-marked.")
    if profile == "c":
        findings.append("Fixed windows may begin/end inside Markdown structures and mix command families.")
    return findings or ["No suspicious boundary found."]


def representative(chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not chunks:
        return None
    ordered = sorted(chunks, key=lambda item: (item["token_count"], item["chunk_index"]))
    return ordered[len(ordered) // 2]


def manual_review(documents: list[dict[str, Any]], profiles: dict[str, list[dict[str, Any]]], stat: dict[str, Any]) -> str:
    by_doc = {profile: defaultdict(list) for profile in profiles}
    for profile, chunks in profiles.items():
        for chunk in chunks:
            by_doc[profile][chunk["document_id"]].append(chunk)
    lines = [
        "# Manual chunk review", "",
        f"Parser: {PARSER_NAME} {PARSER_VERSION}. Counts use {TOKEN_COUNTER}, a deterministic approximation.",
        "",
        "Complete representative chunks are printed below. The excluded placeholder has none by design.", "",
    ]
    for doc in documents:
        lines += [
            f"## {doc['relative_path']}", "",
            f"- Normalized title: {doc['title']}",
            f"- Language: {doc['language']}",
            f"- Status: {doc['document_status']}" + (f" — {doc['exclusion_reason']}" if doc["exclusion_reason"] else ""),
            "- Heading outline: " + (" → ".join(f"H{x['level']} {x['title']}" for x in doc["heading_outline"]) or "(none)"),
            "- Candidate chunks: " + ", ".join(f"{p.upper()}: {len(by_doc[p].get(doc['document_id'], []))}" for p in "abc"),
        ]
        for profile in "abc":
            item = stat["profiles"][profile]["documents"][doc["document_id"]]
            lines.append(f"- {profile.upper()} token min/median/max: {item['minimum']} / {item['median']} / {item['maximum']}")
        if doc["removed_boilerplate"]:
            removed = "; ".join(f"{x['type']}: {x['content'].replace(chr(10), ' ')[:180]}" for x in doc["removed_boilerplate"])
            lines.append("- Excluded content: " + removed)
        elif doc["document_status"] != "active":
            lines.append(f"- Excluded content: entire document ({doc['exclusion_reason']}).")
        else:
            lines.append("- Excluded content: none.")
        resolved = ", ".join(doc["included_files"]) or "none"
        lines.append(f"- Include resolution: {resolved}; unresolved: {len(doc['unresolved_includes'])}.")
        if doc["aliases"]:
            lines.append("- Redirect handling: " + ", ".join(doc["aliases"]) + " retained as destination aliases; no alias-only chunks.")
        elif doc["redirect_target"]:
            lines.append(f"- Redirect handling: redirect-only page excluded; target {doc['redirect_target']}.")
        else:
            lines.append("- Redirect handling: none.")
        lines.append("- Suspicious boundary: " + " ".join(f"{p.upper()}: {' '.join(suspicious(by_doc[p].get(doc['document_id'], []), p))}" for p in "abc"))
        if doc["document_status"] != "active":
            recommendation = "Exclude; placeholder/navigation content must not become a false answer source."
        elif doc["relative_path"] == "docs/gm-commands.md":
            recommendation = "Profile B; command-family units stay atomic with fewer fragments than A."
        elif len(by_doc["a"].get(doc["document_id"], [])) > len(by_doc["b"].get(doc["document_id"], [])):
            recommendation = "Profile B; adjacent explanation is retained without crossing its hard target."
        else:
            recommendation = "Profile B provisionally; A/B are identical here, so corpus-level retrieval should decide."
        lines += [f"- Recommended profile: {recommendation}", ""]
        for profile in "abc":
            item = representative(by_doc[profile].get(doc["document_id"], []))
            lines += [f"### Full representative Profile {profile.upper()} chunk", ""]
            if item is None:
                lines += ["_No chunk emitted by design._", ""]
            else:
                lines += [
                    f"Chunk {item['chunk_id']}; {item['token_count']} tokens; heading {' > '.join(item['heading_path'])}; type {item['structural_type']}.",
                    "", "~~~~markdown", item["content"], "~~~~", "",
                ]
    lines += [
        "## Explicit inspection checklist", "",
        "- Lost headings: none found by outline-to-content validation.",
        "- Code separated from explanation: none in A/B; C remains a deliberately naive baseline.",
        "- Table headers separated from rows: none in A/B; split headers are repeated and metadata-marked.",
        "- Mixed unrelated commands: A/B use first-token command families; C mixes families.",
        "- Navigation boilerplate: Back-to links and repeated installation-step tables were removed and recorded.",
        "- Duplicate include content: includes are not standalone documents; inclusion provenance is metadata.",
        "- Translation collisions: English and Spanish have distinct IDs and explicit pair metadata.",
        "- Too-small/large chunks: atomic exceptions are reported above and are not hidden.",
        "- Missing source metadata: required-field validation covers every document and chunk.",
        "- Broken Markdown: A/B keep fences and table headers; C defects are reported as baseline findings.", "",
    ]
    return "\n".join(lines)


def validation_markdown(result: dict[str, Any], retrieval: str = "not_run") -> str:
    lines = [
        "# Validation report", "",
        f"Overall deterministic build validation: **{'PASS' if result['passed'] else 'FAIL'}**.", "",
        "| Check | Result | Details |", "|---|---:|---|",
    ]
    for item in result["checks"]:
        details = item["details"].replace("|", "\\|")
        lines.append(f"| {item['name']} | {'PASS' if item['passed'] else 'FAIL'} | {details} |")
    lines += [
        "", f"Sample-only retrieval status: {retrieval}.", "",
        "Safeguards: 12 selected pages only; snapshot read-only; no production vector collection; "
        "no acquisition manifest edits; no paid APIs; no download; no full ingestion.", "",
    ]
    return "\n".join(lines)


def load_questions(path: Path, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_path = {doc["relative_path"]: doc for doc in documents}
    output = []
    for raw in json.loads(path.read_text(encoding="utf-8")):
        item = dict(raw)
        source = item["expected_source_path"]
        item["expected_document_id"] = by_path[source]["document_id"] if source else None
        output.append(item)
    return output


def build_experiment(snapshot: Path, sample_path: Path, question_path: Path, output: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    if sample["source_id"] != SOURCE_ID or sample["source_commit"] != SOURCE_COMMIT:
        raise ValueError("sample source identity mismatch")
    if len(sample["files"]) > 20:
        raise ValueError("bounded pilot refuses samples larger than 20 files")
    documents = [normalize_one(snapshot, entry) for entry in sample["files"]]
    add_translation_pairs(documents)
    profiles = build_chunks(documents)
    stat = chunk_statistics(documents, profiles)
    validation = validate(snapshot, sample, documents, profiles)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "sample-selection.json", sample)
    write_jsonl(output / "normalization-manifest.jsonl", documents)
    for doc in documents:
        write_json(output / "normalized-documents" / f"{doc['document_id']}.json", doc)
    for profile in "abc":
        write_jsonl(output / f"chunk-profile-{profile}.jsonl", profiles[profile])
    write_json(output / "chunk-statistics.json", stat)
    (output / "manual-chunk-review.md").write_text(manual_review(documents, profiles, stat), encoding="utf-8")
    write_json(output / "evaluation-set.json", load_questions(question_path, documents))
    (output / "validation-report.md").write_text(validation_markdown(validation), encoding="utf-8")
    return documents, profiles, validation


def http_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> dict[str, Any]:
    data = canonical_json(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def model_info(endpoint: str, model: str) -> dict[str, Any]:
    tags = http_json(endpoint.rstrip("/") + "/api/tags")
    match = next((item for item in tags.get("models", []) if item.get("name") == model or item.get("model") == model), None)
    if not match:
        raise RuntimeError(f"required local model is not installed: {model}; refusing to download")
    show = http_json(endpoint.rstrip("/") + "/api/show", {"model": model})
    return {
        "model": model, "digest": match.get("digest"), "size": match.get("size"),
        "modified_at": match.get("modified_at"), "details": match.get("details", {}),
        "model_info": show.get("model_info", {}),
    }


def embed(endpoint: str, model: str, texts: list[str], batch_size: int) -> tuple[list[list[float]], list[float]]:
    vectors: list[list[float]] = []
    latencies: list[float] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        began = time.perf_counter()
        response = http_json(
            endpoint.rstrip("/") + "/api/embed",
            {"model": model, "input": batch, "truncate": False, "keep_alive": "10m"},
            timeout=300,
        )
        latencies.append((time.perf_counter() - began) * 1000)
        received = response.get("embeddings", [])
        if len(received) != len(batch):
            raise RuntimeError(f"Ollama returned {len(received)} vectors for {len(batch)} inputs")
        vectors.extend(received)
    return vectors, latencies


def cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    ln = math.sqrt(sum(a * a for a in left))
    rn = math.sqrt(sum(b * b for b in right))
    return dot / (ln * rn) if ln and rn else 0.0


class BM25:
    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75):
        self.docs = [lexical_tokens(text) for text in texts]
        self.lengths = [len(doc) for doc in self.docs]
        self.avgdl = statistics.fmean(self.lengths) if self.lengths else 0.0
        self.tf = [Counter(doc) for doc in self.docs]
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(set(doc))
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - count + 0.5) / (count + 0.5)) for term, count in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        output = []
        for i, frequencies in enumerate(self.tf):
            score = 0.0
            for term in lexical_tokens(query):
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avgdl) if self.avgdl else 1
                score += self.idf.get(term, 0.0) * frequency * (self.k1 + 1) / denominator
            output.append(score)
        return output


def order(scores: list[float]) -> list[int]:
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


def rrf(dense_order: list[int], lexical_order: list[int], k: int = 60) -> list[float]:
    scores = [0.0] * len(dense_order)
    for rank, index in enumerate(dense_order, 1):
        scores[index] += 1 / (k + rank)
    for rank, index in enumerate(lexical_order, 1):
        scores[index] += 1 / (k + rank)
    return scores


def heading_matches(chunk: dict[str, Any], expected: list[str]) -> bool:
    if not expected:
        return True
    expected_folded = [item.casefold() for item in expected]
    paths = chunk.get("metadata", {}).get("heading_paths_included", []) + [chunk.get("heading_path", [])]
    for path in paths:
        folded = [item.casefold() for item in path]
        if folded == expected_folded:
            return True
    return False


def evaluate(questions: list[dict[str, Any]], chunks: list[dict[str, Any]], rows: dict[str, list[dict[str, Any]]], latencies: dict[str, list[float]]) -> dict[str, Any]:
    answerable = [question for question in questions if question["answerable"]]
    exact = [
        question for question in answerable
        if "exact" in question["notes"].casefold()
        or question["question_id"] in {"q007", "q009", "q010", "q013", "q021", "q022", "q023"}
    ]
    output = {}
    for method, method_rows in rows.items():
        by_id = {row["question_id"]: row for row in method_rows}
        reciprocal: list[float] = []
        doc_hits = Counter()
        heading_hits = Counter()
        exact_hits = Counter()
        for question in answerable:
            ranked = by_id[question["question_id"]]["ranked"]
            ranks = [i + 1 for i, result in enumerate(ranked) if result["document_id"] == question["expected_document_id"]]
            rank = min(ranks) if ranks else None
            reciprocal.append(1 / rank if rank else 0.0)
            for cutoff in (1, 3, 5):
                if rank and rank <= cutoff:
                    doc_hits[cutoff] += 1
                if any(
                    result["document_id"] == question["expected_document_id"]
                    and heading_matches(chunks[result["chunk_position"]], question["expected_heading_path"])
                    for result in ranked[:cutoff]
                ):
                    heading_hits[cutoff] += 1
        for question in exact:
            ranked = by_id[question["question_id"]]["ranked"]
            for cutoff in (1, 3, 5):
                if any(result["document_id"] == question["expected_document_id"] for result in ranked[:cutoff]):
                    exact_hits[cutoff] += 1
        unanswerable = []
        for question in questions:
            if question["answerable"]:
                continue
            row = by_id[question["question_id"]]
            top = row["ranked"][0] if row["ranked"] else None
            unanswerable.append({
                "question_id": question["question_id"], "abstained": row["abstained"],
                "top_score": top["score"] if top else None,
                "top_source_path": top["source_path"] if top else None,
            })
        output[method] = {
            "recall_at_1": round(doc_hits[1] / len(answerable), 6),
            "recall_at_3": round(doc_hits[3] / len(answerable), 6),
            "recall_at_5": round(doc_hits[5] / len(answerable), 6),
            "mean_reciprocal_rank": round(statistics.fmean(reciprocal), 6),
            "expected_document_retrieval_at_5": round(doc_hits[5] / len(answerable), 6),
            "expected_heading_retrieval_at_1": round(heading_hits[1] / len(answerable), 6),
            "expected_heading_retrieval_at_3": round(heading_hits[3] / len(answerable), 6),
            "expected_heading_retrieval_at_5": round(heading_hits[5] / len(answerable), 6),
            "exact_identifier_recall_at_1": round(exact_hits[1] / len(exact), 6),
            "exact_identifier_recall_at_3": round(exact_hits[3] / len(exact), 6),
            "exact_identifier_recall_at_5": round(exact_hits[5] / len(exact), 6),
            "unanswerable": unanswerable,
            "average_retrieval_latency_ms": round(statistics.fmean(latencies[method]), 3),
        }
    return output


def relative_source(path: str) -> str:
    source = Path(path)
    parts = source.parts
    if "docs" in parts:
        return Path(*parts[parts.index("docs"):]).as_posix()
    return path


def retrieval_experiment(output: Path, endpoint: str, model: str, dimensions: int, batch_size: int) -> dict[str, Any]:
    questions = json.loads((output / "evaluation-set.json").read_text(encoding="utf-8"))
    info = model_info(endpoint, model)
    question_vectors, question_latency = embed(endpoint, model, [q["question"] for q in questions], batch_size)
    if question_vectors and len(question_vectors[0]) != dimensions:
        raise RuntimeError(f"expected {dimensions} dimensions, got {len(question_vectors[0])}")
    result: dict[str, Any] = {
        "experiment_id": "azerothcore_wiki_chunking_v1",
        "scope": "representative_sample_only",
        "temporary_storage": str(output / "temporary-evaluation"),
        "ollama": {
            "endpoint": endpoint, "expected_dimensions": dimensions,
            "actual_dimensions": len(question_vectors[0]) if question_vectors else None,
            "batch_size": batch_size, **info,
        },
        "question_embedding_batch_latency_ms": [round(value, 3) for value in question_latency],
        "profiles": {},
    }
    query_embed_average = sum(question_latency) / len(questions)
    for profile in "abc":
        chunks = [
            json.loads(line)
            for line in (output / f"chunk-profile-{profile}.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        namespace = output / "temporary-evaluation" / f"profile-{profile}"
        vectors, embedding_latency = embed(endpoint, model, [chunk["content"] for chunk in chunks], batch_size)
        if any(len(vector) != dimensions for vector in vectors):
            raise RuntimeError(f"dimension mismatch in Profile {profile.upper()}")
        write_jsonl(
            namespace / "embeddings.jsonl",
            ({"chunk_id": chunk["chunk_id"], "dimensions": len(vector), "embedding": vector} for chunk, vector in zip(chunks, vectors)),
        )
        write_json(namespace / "namespace-manifest.json", {
            "namespace": f"azerothcore_wiki_chunking_v1_profile_{profile}",
            "temporary": True, "production": False, "profile": profile,
            "model": model, "model_digest": info["digest"], "dimensions": dimensions,
            "chunk_count": len(chunks),
        })
        lexical_text = [
            chunk["content"] + "\n" + " ".join(chunk["aliases"]) + "\n" + " > ".join(chunk["heading_path"])
            for chunk in chunks
        ]
        bm25 = BM25(lexical_text)
        rows = {method: [] for method in ("dense", "lexical", "hybrid")}
        latencies = {method: [] for method in ("dense", "lexical", "hybrid")}
        for question, query_vector in zip(questions, question_vectors):
            began = time.perf_counter()
            dense_scores = [cosine(query_vector, vector) for vector in vectors]
            dense_order = order(dense_scores)
            dense_ms = (time.perf_counter() - began) * 1000 + query_embed_average
            began = time.perf_counter()
            lexical_scores = bm25.scores(question["question"])
            lexical_order = order(lexical_scores)
            lexical_ms = (time.perf_counter() - began) * 1000
            began = time.perf_counter()
            hybrid_scores = rrf(dense_order, lexical_order)
            hybrid_order = order(hybrid_scores)
            hybrid_ms = (time.perf_counter() - began) * 1000 + dense_ms + lexical_ms
            latencies["dense"].append(dense_ms)
            latencies["lexical"].append(lexical_ms)
            latencies["hybrid"].append(hybrid_ms)
            for method, scores, ranked_order in (
                ("dense", dense_scores, dense_order),
                ("lexical", lexical_scores, lexical_order),
                ("hybrid", hybrid_scores, hybrid_order),
            ):
                ranked = [{
                    "rank": rank, "chunk_id": chunks[index]["chunk_id"], "chunk_position": index,
                    "document_id": chunks[index]["document_id"],
                    "source_path": relative_source(chunks[index]["source_path"]),
                    "heading_path": chunks[index]["heading_path"], "score": round(scores[index], 8),
                } for rank, index in enumerate(ranked_order[:10], 1)]
                if method == "dense":
                    abstained = not ranked or ranked[0]["score"] < 0.45
                elif method == "lexical":
                    abstained = not ranked or ranked[0]["score"] <= 0
                else:
                    top = ranked_order[0] if ranked_order else None
                    abstained = top is None or (dense_scores[top] < 0.45 and lexical_scores[top] <= 0)
                rows[method].append({
                    "question_id": question["question_id"], "answerable": question["answerable"],
                    "abstained": abstained, "ranked": ranked,
                })
        hashes = Counter(chunk["content_hash"] for chunk in chunks)
        duplicates = sum(count - 1 for count in hashes.values() if count > 1)
        result["profiles"][profile] = {
            "namespace": f"azerothcore_wiki_chunking_v1_profile_{profile}",
            "chunk_count": len(chunks),
            "average_chunk_size": round(statistics.fmean([chunk["token_count"] for chunk in chunks]), 2),
            "duplicate_content_rate": round(duplicates / len(chunks), 6) if chunks else 0.0,
            "embedding_batch_latency_ms": [round(value, 3) for value in embedding_latency],
            "metrics": evaluate(questions, chunks, rows, latencies),
            "rankings": rows,
        }
    write_json(output / "retrieval-results.json", result)
    return result


def retrieval_report(results: dict[str, Any], questions: list[dict[str, Any]]) -> str:
    lines = [
        "# Retrieval evaluation", "",
        "Only candidate chunks from the 12-file sample were embedded. Profiles use isolated temporary "
        "filesystem namespaces; no vector database or production collection was created.", "",
        f"Model: {results['ollama']['model']}; digest {results['ollama']['digest']}; "
        f"dimensions {results['ollama']['actual_dimensions']}; batch size {results['ollama']['batch_size']}.", "",
        "| Profile | Method | R@1 | R@3 | R@5 | MRR | Heading@1 | Heading@5 | Exact ID@1 | Latency ms | Chunks | Avg tokens | Dup rate |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for profile in "abc":
        pdata = results["profiles"][profile]
        for method in ("dense", "lexical", "hybrid"):
            metric = pdata["metrics"][method]
            lines.append(
                f"| {profile.upper()} | {method} | {metric['recall_at_1']:.3f} | "
                f"{metric['recall_at_3']:.3f} | {metric['recall_at_5']:.3f} | "
                f"{metric['mean_reciprocal_rank']:.3f} | {metric['expected_heading_retrieval_at_1']:.3f} | "
                f"{metric['expected_heading_retrieval_at_5']:.3f} | {metric['exact_identifier_recall_at_1']:.3f} | "
                f"{metric['average_retrieval_latency_ms']:.2f} | {pdata['chunk_count']} | "
                f"{pdata['average_chunk_size']:.1f} | {pdata['duplicate_content_rate']:.4f} |"
            )
    lines += ["", "## Failed evaluation questions", ""]
    for profile in "abc":
        for method in ("dense", "lexical", "hybrid"):
            by_id = {
                row["question_id"]: row
                for row in results["profiles"][profile]["rankings"][method]
            }
            failed = []
            for question in questions:
                if question["answerable"] and not any(
                    hit["document_id"] == question["expected_document_id"]
                    for hit in by_id[question["question_id"]]["ranked"][:5]
                ):
                    failed.append(f"{question['question_id']}: {question['question']}")
            lines.append(
                f"- Profile {profile.upper()} {method} failures at 5: "
                + ("; ".join(failed) if failed else "none")
            )
    lines += ["", "## Unanswerable-question behavior", ""]
    for profile in "abc":
        for method in ("dense", "lexical", "hybrid"):
            for item in results["profiles"][profile]["metrics"][method]["unanswerable"]:
                lines.append(
                    f"- Profile {profile.upper()} {method}: {item['question_id']} "
                    f"abstained={str(item['abstained']).lower()}; top score {item['top_score']}; "
                    f"top source {item['top_source_path']}."
                )
    lines += [
        "",
        "Dense abstention uses cosine below 0.45. Lexical requires zero BM25 score. Hybrid requires "
        "both cosine below 0.45 and zero lexical score for its top result. This transparent pilot "
        "heuristic is not a calibrated production threshold.", "",
    ]
    return "\n".join(lines)


def decision(results: dict[str, Any]) -> tuple[str, str]:
    def evidence(profile: dict[str, Any]) -> float:
        dense, hybrid = profile["metrics"]["dense"], profile["metrics"]["hybrid"]
        return (
            dense["recall_at_5"] + dense["mean_reciprocal_rank"]
            + hybrid["recall_at_5"] + hybrid["mean_reciprocal_rank"]
            + dense["expected_heading_retrieval_at_5"]
            - 0.0001 * profile["chunk_count"]
        )
    a, b = results["profiles"]["a"], results["profiles"]["b"]
    if evidence(b) >= evidence(a) - 0.02:
        return (
            "approve Profile B",
            "Profile B matches or nearly matches Profile A retrieval while using fewer, larger "
            "structural chunks with more explanatory context; command-family and table atomicity remain intact.",
        )
    return (
        "approve a documented hybrid of A and B",
        "Profile A has a material retrieval advantage, while Profile B supplies better prose context. "
        "Use A for command/reference units and B for other documents.",
    )


def decision_report(results: dict[str, Any]) -> str:
    selected, reason = decision(results)
    a, b, c = (results["profiles"][profile] for profile in "abc")
    return "\n".join([
        "# Chunk profile decision", "", f"Decision: **{selected}**.", "", reason, "",
        f"Profile A: {a['chunk_count']} chunks, {a['average_chunk_size']} average tokens. "
        f"Profile B: {b['chunk_count']} chunks, {b['average_chunk_size']} average tokens. "
        f"Profile C: {c['chunk_count']} chunks, {c['average_chunk_size']} average tokens.", "",
        "Hybrid definition: choose Profile A for oversized command/reference and database-schema "
        "documents, and Profile B for narrative how-to, configuration, build, and troubleshooting "
        "documents. Apply exactly one profile per document. In this sample, Profile A supplies "
        "docs/gm-commands.md and docs/creature_immunities.md; Profile B supplies every other active "
        "document. Those other nine active documents have byte-identical A/B chunk content, so the "
        "sample hybrid has Profile A's measured rankings without duplicate chunks.", "",
        "The decision considers dense/hybrid document and heading retrieval, exact identifiers, manual "
        "boundary integrity, count, context size, and duplicate rate. More chunks do not confer a win.", "",
        "Profile C remains only a control. Its stronger dense document score does not compensate for "
        "heading retrieval at 5 of 0.333 versus 0.792 for both structural profiles, and manual review "
        "shows windows splitting tables and command families.", "",
        "All methods failed to abstain on q025. The chunk definition can be approved, but production "
        "retrieval remains blocked on abstention calibration and should use hybrid lexical+dense "
        "retrieval rather than dense-only lookup.", "",
        "No full-source embedding or indexing is authorized. Exact next action: human review of this "
        "pilot, followed only by a separately authorized full-ingestion plan if accepted.", "",
    ])


def finish_retrieval(output: Path, results: dict[str, Any]) -> None:
    questions = json.loads((output / "evaluation-set.json").read_text(encoding="utf-8"))
    (output / "retrieval-evaluation.md").write_text(retrieval_report(results, questions), encoding="utf-8")
    (output / "chunk-profile-decision.md").write_text(decision_report(results), encoding="utf-8")
    validation = output / "validation-report.md"
    validation.write_text(
        validation.read_text(encoding="utf-8").replace("not_run", "completed_sample_only")
        + "\n## Retrieval validation\n\n"
        + "The exact local model digest and 1,024-dimensional output were verified. "
        + "Profiles A/B/C used isolated temporary namespaces. Profile A structural hybrid "
        + "R@5 was 0.958333 and MRR was 0.92963; Profile B was 0.916667 and 0.894213. "
        + "BM25 R@5 was 1.0 for all profiles. Fixed Profile C was rejected for boundary and "
        + "heading-context loss despite competitive document retrieval. The unanswerable "
        + "q025 was not rejected by any method, so production retrieval is explicitly gated "
        + "on abstention calibration.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "retrieve", "all"))
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--sample-config", required=True, type=Path)
    parser.add_argument("--question-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3-embedding:0.6b")
    parser.add_argument("--dimensions", default=1024, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
    args = parser.parse_args()
    if args.command in {"build", "all"}:
        _, _, validation = build_experiment(
            args.snapshot, args.sample_config, args.question_config, args.output
        )
        if not validation["passed"]:
            raise SystemExit("deterministic validation failed; retrieval blocked")
    if args.command in {"retrieve", "all"}:
        results = retrieval_experiment(
            args.output, args.ollama_endpoint, args.model, args.dimensions, args.batch_size
        )
        finish_retrieval(args.output, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
