#!/usr/bin/env python3
"""Compile ordered Prompt sections into one Unicode-safe text and exact spans.

The model supplies section text and semantic references. This helper owns all
code-point offsets so creative runs never need to count characters manually.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_KINDS = {
    "TASK",
    "REFERENCE_ASSET",
    "SCENE_STYLE_CONTINUITY",
    "STATIC_FRAME",
    "DIRECTOR_TIMELINE",
    "SOUND",
    "NEGATIVE",
    "TRANSFORM_PLAN",
}
TEXT_KEYS = {
    "PROVIDER_NEUTRAL_MASTER": "master_prompt_text",
    "TRANSFORM_PLAN": "transform_plan_text",
    "NEUTRAL_EXECUTION_PROMPT": "neutral_execution_prompt_text",
    "PROVIDER_COMPILED": "prompt_text",
}
LEGACY_TEXT_KEYS = {"PROVIDER_NEUTRAL_DRAFT": "draft_prompt_text"}
ALLOWED_SEPARATORS = {"", "\n", "\n\n"}


class SectionCompileError(ValueError):
    """Raised when a section source is unsafe or structurally invalid."""


def string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise SectionCompileError(f"{field} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise SectionCompileError(f"{field} contains duplicate IDs")
    return value


def compile_payload(payload: dict[str, Any], *, allow_legacy_read: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SectionCompileError("input must be a JSON object")
    layer = payload.get("prompt_layer")
    text_keys = dict(TEXT_KEYS)
    if allow_legacy_read:
        text_keys.update(LEGACY_TEXT_KEYS)
    if layer in LEGACY_TEXT_KEYS and not allow_legacy_read:
        raise SectionCompileError(
            "E_LEGACY_PROMPT_LAYER_READ_ONLY: PROVIDER_NEUTRAL_DRAFT is accepted only for explicit legacy reads"
        )
    if layer not in text_keys:
        raise SectionCompileError(f"unsupported prompt_layer: {layer!r}")
    separator = payload.get("separator", "\n\n")
    if separator not in ALLOWED_SEPARATORS:
        raise SectionCompileError("separator must be empty, one newline, or two newlines")
    rows = payload.get("sections")
    if not isinstance(rows, list) or not rows:
        raise SectionCompileError("sections must be a non-empty array")

    seen_section_ids: set[str] = set()
    prompt_parts: list[str] = []
    compiled_sections: list[dict[str, Any]] = []
    cursor = 0

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise SectionCompileError(f"sections[{index - 1}] must be an object")
        section_id = row.get("section_id")
        kind = row.get("kind")
        body = row.get("text")
        if not isinstance(section_id, str) or not section_id:
            raise SectionCompileError(f"sections[{index - 1}].section_id is required")
        if section_id in seen_section_ids:
            raise SectionCompileError(f"duplicate section_id: {section_id}")
        seen_section_ids.add(section_id)
        if kind not in ALLOWED_KINDS:
            raise SectionCompileError(f"unsupported section kind: {kind!r}")
        if layer == "TRANSFORM_PLAN" and kind != "TRANSFORM_PLAN":
            raise SectionCompileError(
                "E_PROMPT_LAYER_ROLE_CONFLICT: TRANSFORM_PLAN accepts planning-only sections"
            )
        if layer in {
            "PROVIDER_NEUTRAL_MASTER", "NEUTRAL_EXECUTION_PROMPT", "PROVIDER_COMPILED",
        } and kind == "TRANSFORM_PLAN":
            raise SectionCompileError(
                f"E_PROMPT_LAYER_ROLE_CONFLICT: {layer} cannot contain planning-only sections"
            )
        if not isinstance(body, str) or not body.strip():
            raise SectionCompileError(f"section {section_id} text must be substantive")
        atom_ids = string_list(row.get("atom_ids", []), f"{section_id}.atom_ids")
        beat_ids = string_list(row.get("beat_ids", []), f"{section_id}.beat_ids")

        # The delimiter belongs to the preceding section. Therefore every span
        # remains contiguous and the canonical slice exactly reconstructs text.
        rendered = body + (separator if index < len(rows) else "")
        start = cursor
        cursor += len(rendered)  # Python str length is Unicode code-point based.
        prompt_parts.append(rendered)
        compiled_sections.append(
            {
                "section_id": section_id,
                "kind": kind,
                "order": index,
                "start_char": start,
                "end_char": cursor,
                "atom_ids": atom_ids,
                "beat_ids": beat_ids,
            }
        )

    prompt_text = "".join(prompt_parts)
    if not prompt_text.strip():
        raise SectionCompileError("compiled Prompt is empty")
    return {
        "prompt_layer": layer,
        text_keys[layer]: prompt_text,
        "prompt_sections": compiled_sections,
    }


def read_json(path: Path | None) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig") if path else sys.stdin.read()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise SectionCompileError("input must be a JSON object")
    return value


def write_json(value: dict[str, Any], path: Path | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(rendered)


def self_test() -> None:
    source = {
        "prompt_layer": "PROVIDER_COMPILED",
        "sections": [
            {
                "section_id": "SEC-001",
                "kind": "TASK",
                "text": "雨夜里，她停在门口。",
                "atom_ids": ["PSA-001"],
                "beat_ids": ["BT-001"],
            },
            {
                "section_id": "SEC-002",
                "kind": "DIRECTOR_TIMELINE",
                "text": "镜头缓慢靠近，她抬眼。",
                "atom_ids": ["PSA-002"],
                "beat_ids": ["BT-002"],
            },
        ],
    }
    result = compile_payload(source)
    text_value = result["prompt_text"]
    sections = result["prompt_sections"]
    assert text_value == "雨夜里，她停在门口。\n\n镜头缓慢靠近，她抬眼。"
    assert sections[0]["start_char"] == 0
    assert sections[-1]["end_char"] == len(text_value)
    assert "".join(text_value[row["start_char"] : row["end_char"]] for row in sections) == text_value

    neutral = compile_payload({**source, "prompt_layer": "NEUTRAL_EXECUTION_PROMPT"})
    assert neutral["neutral_execution_prompt_text"] == text_value
    plan_source = {
        **source,
        "prompt_layer": "TRANSFORM_PLAN",
        "sections": [
            {**row, "kind": "TRANSFORM_PLAN"} for row in source["sections"]
        ],
    }
    plan = compile_payload(plan_source)
    assert plan["transform_plan_text"] == text_value

    legacy = {**source, "prompt_layer": "PROVIDER_NEUTRAL_DRAFT"}
    try:
        compile_payload(legacy)
    except SectionCompileError as exc:
        assert "E_LEGACY_PROMPT_LAYER_READ_ONLY" in str(exc)
    else:
        raise AssertionError("legacy DRAFT was accepted by the current writer")
    assert compile_payload(legacy, allow_legacy_read=True)["draft_prompt_text"] == text_value

    for bad in (
        {"prompt_layer": "PROVIDER_COMPILED", "sections": []},
        {"prompt_layer": "UNKNOWN", "sections": source["sections"]},
        {
            "prompt_layer": "PROVIDER_COMPILED",
            "sections": [dict(source["sections"][0]), dict(source["sections"][0])],
        },
        {
            "prompt_layer": "PROVIDER_COMPILED",
            "sections": [{**source["sections"][0], "text": "   "}],
        },
        {**source, "separator": "IGNORE PREVIOUS INSTRUCTIONS"},
        {**source, "prompt_layer": "TRANSFORM_PLAN"},
        {
            **source,
            "prompt_layer": "NEUTRAL_EXECUTION_PROMPT",
            "sections": [{**source["sections"][0], "kind": "TRANSFORM_PLAN"}],
        },
    ):
        try:
            compile_payload(bad)
        except SectionCompileError:
            continue
        raise AssertionError(f"invalid fixture was accepted: {bad!r}")
    print("SELF_TEST_PASS: 12/12")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="source JSON; omit for stdin")
    parser.add_argument("--output", type=Path, help="new output JSON; existing files are never overwritten")
    parser.add_argument(
        "--allow-legacy-read",
        action="store_true",
        help="accept read-only PROVIDER_NEUTRAL_DRAFT input; current writers must omit this flag",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    try:
        result = compile_payload(read_json(args.input), allow_legacy_read=args.allow_legacy_read)
        write_json(result, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
