#!/usr/bin/env python3
"""Prepare a compact, immutable Alpha.7 longform authoring envelope.

The helper owns source normalization, atom spans, continuous Unit windows,
dialogue inventory, target selection evidence, and all derived hashes.  A
model/creator is expected to edit only the three named overlays for each
selected Unit.  Terminal status, PASS/CURRENT, validation results, and hashes
are deliberately absent from the editable surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from validate_longform_contract import (
    CONTRACT_VERSION,
    DIRECTOR_TARGET_MODES,
    derive_quote_classification_hints,
    expected_dialogue_ids_for_unit,
    expected_global_state,
    expected_feature_matrix,
    expected_helper_lock_projection,
    expected_locked_director_scaffold,
    expected_route_findings,
    expected_semantic_gate,
    expected_semantic_anchors,
    expected_sequence_minimum_shots,
    expected_sequence_anchor_groups,
    expected_single_shot_eligibility,
    expected_skeleton_sha256,
    expected_target_windows,
    expected_text_status_contract,
    infer_spoken_speaker_hint,
    normalize_text,
    semantic_span_containing_quote,
    sha256_text,
    sha256_value,
    source_anchor_is_complete,
    source_locked_nonlexical_speakers_from_window,
)


AUTHORING_VERSION = "alpha7-longform-authoring-1.5"
AUTHORING_GUIDE_VERSION = "alpha7-overlay-guide-1.5"
READ_ONLY_AUTHORING_VERSIONS = [
    "alpha7-longform-authoring-1.3", "alpha7-longform-authoring-1.4",
]
READ_ONLY_GUIDE_VERSIONS = ["alpha7-overlay-guide-1.3", "alpha7-overlay-guide-1.4"]

DOCX_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


def read_source_text(path: Path) -> str:
    """Read creator source text, including ordinary Word DOCX without extras."""

    if not path.is_file():
        raise ValueError(f"找不到来源文件：{path}")
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        text = path.read_text(encoding="utf-8-sig")
    elif suffix == ".docx":
        if not zipfile.is_zipfile(path):
            raise ValueError("这个 DOCX 文件已损坏或并非真正的 Word 文档，请重新保存后再试。")
        with zipfile.ZipFile(path, "r") as archive:
            entries = archive.infolist()
            for item in entries:
                normalized = item.filename.replace("\\", "/")
                parts = [part for part in normalized.split("/") if part]
                if (
                    normalized.startswith("/")
                    or re.match(r"^[A-Za-z]:", normalized)
                    or ".." in parts
                    or item.flag_bits & 0x1
                ):
                    raise ValueError("这个 DOCX 包含不安全或加密的内部文件，无法读取。")
            if sum(item.file_size for item in entries) > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise ValueError("这个 DOCX 解压后过大，请拆分文档后再试。")
            try:
                document_xml = archive.read("word/document.xml")
            except KeyError as exc:
                raise ValueError("这个 DOCX 缺少正文，请重新用 Word 保存后再试。") from exc
        try:
            root = ET.fromstring(document_xml)
        except ET.ParseError as exc:
            raise ValueError("这个 DOCX 的正文结构已损坏，请重新保存后再试。") from exc
        paragraph_tag = f"{{{DOCX_WORD_NAMESPACE}}}p"
        text_tag = f"{{{DOCX_WORD_NAMESPACE}}}t"
        tab_tag = f"{{{DOCX_WORD_NAMESPACE}}}tab"
        break_tags = {
            f"{{{DOCX_WORD_NAMESPACE}}}br",
            f"{{{DOCX_WORD_NAMESPACE}}}cr",
        }
        paragraphs: list[str] = []
        for paragraph in root.iter(paragraph_tag):
            parts: list[str] = []
            for node in paragraph.iter():
                if node.tag == text_tag and node.text:
                    parts.append(node.text)
                elif node.tag == tab_tag:
                    parts.append("\t")
                elif node.tag in break_tags:
                    parts.append("\n")
            paragraphs.append("".join(parts))
        text = "\n".join(paragraphs)
    else:
        raise ValueError("来源文件格式不支持。请使用 TXT、Markdown 或 Word DOCX 文件。")
    if not text.strip():
        raise ValueError("来源文件没有可读取的正文。")
    return text
DIRECTOR_SCAFFOLD_VERSION = "alpha7-director-scaffold-1.1"
IN_PLACE_COMMIT_MODE = "IN_PLACE_THREE_CARRIER_V1"
SIBLING_COMMIT_MODE = "SIBLING_THREE_CARRIER_V1"
TEMP_INPUT_NAMES = ["TARGET_PLAN.json", "AUTHORING.json", "OVERLAYS.json"]
DEFAULT_OUTPUT_NAMES = ["长篇文字测试包.md", "MACHINE_STATE.json", "RUN_SUMMARY.md"]
WINDOWS_RESERVED_BASENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
INVISIBLE_FILENAME_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
DEFAULT_USER_TARGET_MAX_ATOMS = 12
DEFAULT_USER_TARGET_MAX_CHARS = 1000
CONTINUATION_START_RE = re.compile(
    r"^(?:他|她|它|他们|她们|它们|其|这|那|而|但|可是|不过|所以|因此|接着|随后|同时|其中|此外|除此|又|还|也)"
)
AUTO_CONTEXT_DEPENDENT_START_RE = re.compile(
    r"^(?:他|她|它|他们|她们|它们|其|这才|这时|那时|于是|随后|接着|却|便|就|又|还|也|吓得|急忙|连忙)"
)
SELECTION_MODES = {
    "USER_TARGETED_EXACT_RANGES_V1",
    "MACHINE_REPRESENTATIVE_V1",
}
SLOT_RE = re.compile(r"\{\{VERBATIM_DIALOGUE_SLOT:([A-Za-z0-9._-]+)\}\}")
def _semantic_anchors_for_unit(
    unit: dict[str, Any],
    atom_map: dict[str, dict[str, Any]],
    dialogues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use the validator's sole canonical source-anchor derivation."""

    return expected_semantic_anchors(unit, atom_map, dialogues)


def _single_shot_eligibility(
    unit: dict[str, Any],
    semantic_anchors: list[dict[str, Any]],
    feature: dict[str, Any],
) -> dict[str, Any]:
    """Use the validator's sole canonical single-shot decision."""

    return expected_single_shot_eligibility(unit, semantic_anchors, feature)


def _sequence_anchor_groups(
    semantic_anchors: list[dict[str, Any]], minimum_shots: int
) -> list[list[dict[str, Any]]]:
    """Use the validator's sole canonical Sequence grouping."""

    return expected_sequence_anchor_groups(semantic_anchors, minimum_shots)


def _locked_director_scaffold(
    target_mode: str,
    semantic_anchors: list[dict[str, Any]],
    minimum_shots: int,
) -> dict[str, Any]:
    return expected_locked_director_scaffold(target_mode, semantic_anchors, minimum_shots)


def _action_addition_capacity(locked_shot: dict[str, Any]) -> int:
    """Return the remaining 1-3 item budget after helper-owned source anchors."""

    source_anchor_ids = locked_shot.get("source_anchor_ids")
    anchor_count = len(source_anchor_ids) if isinstance(source_anchor_ids, list) else 3
    return max(0, 3 - anchor_count)


def _editable_paths(
    slot_ids: list[str],
    locked_shots: list[dict[str, Any]],
    source_locked_speaker_ids: set[str] | None = None,
    directorial_claim_index: int | None = None,
) -> list[str]:
    source_locked_speaker_ids = source_locked_speaker_ids or set()
    paths = [
        "/director_overlay/performance",
        "/director_overlay/camera",
        "/director_overlay/sound",
    ]
    paths.extend(
        f"/director_overlay/dialogue_speakers/{dialogue_id}"
        for dialogue_id in slot_ids
        if dialogue_id not in source_locked_speaker_ids
    )
    paths.extend(f"/director_overlay/quote_classifications/{dialogue_id}" for dialogue_id in slot_ids)
    for index, locked_shot in enumerate(locked_shots):
        paths.append(f"/director_overlay/shot_creative/{index}/purpose")
        if _action_addition_capacity(locked_shot) > 0:
            paths.append(f"/director_overlay/shot_creative/{index}/action_additions")
        paths.append(f"/director_overlay/shot_creative/{index}/camera")
    paths.extend(
        [
            "/prompt_overlay/master_prompt_template",
            "/prompt_overlay/transform_plan/preserve",
            "/prompt_overlay/transform_plan/operations",
            "/prompt_overlay/transform_plan/deferred_provider_decisions",
            "/prompt_overlay/neutral_execution_prompt_template",
            "/prompt_overlay/negative_clauses",
            "/quality_overlay/scene_title",
            "/quality_overlay/findings",
        ]
    )
    if isinstance(directorial_claim_index, int) and directorial_claim_index >= 0:
        paths.append(f"/prompt_overlay/claims/{directorial_claim_index}/text")
    return paths


def _split_atoms(source_text: str) -> list[dict[str, Any]]:
    raw_pieces = source_text.splitlines(keepends=True)
    if not raw_pieces:
        raw_pieces = [source_text]
    if raw_pieces and "".join(raw_pieces) != source_text:
        raise ValueError("internal atomization failed to preserve normalized source")
    # Blank separator lines are byte-for-byte source, but they are not story
    # events and must not inflate a multi-atom scene window.  Attach them to the
    # preceding content atom (or the first following atom for a leading gap).
    pieces: list[str] = []
    leading = ""
    for piece in raw_pieces:
        if not piece.strip():
            if pieces:
                pieces[-1] += piece
            else:
                leading += piece
            continue
        pieces.append(leading + piece)
        leading = ""
    if leading:
        if pieces:
            pieces[-1] += leading
        else:
            raise ValueError("source text must contain at least one non-whitespace content atom")
    atoms: list[dict[str, Any]] = []
    cursor = 0
    for index, text in enumerate(pieces, start=1):
        atom_id = f"SRC{index:04d}"
        end = cursor + len(text)
        atoms.append(
            {
                "atom_id": atom_id,
                "kind": "STORY_EVENT",
                "source_class": "RENDERABLE_NARRATIVE",
                "compile_target": True,
                "compile_reason": "冻结来源行进入忠实文字编译",
                "start_cp": cursor,
                "end_cp": end,
                "text": text,
                "semantic_tags": ["CONTENT:EVENT"],
                "coverage_status": "mapped",
            }
        )
        cursor = end
    if cursor != len(source_text):
        raise ValueError("atom spans do not cover the normalized source")
    return atoms


def _atom_indexes_for_span(atoms: list[dict[str, Any]], start_cp: int, end_cp: int) -> tuple[int, int]:
    if not (0 <= start_cp < end_cp):
        raise ValueError("target source span must be non-empty")
    hits = [
        index
        for index, atom in enumerate(atoms)
        if atom["start_cp"] < end_cp and atom["end_cp"] > start_cp
    ]
    if not hits:
        raise ValueError("target source span does not intersect an atom")
    return hits[0], hits[-1]


def _unique_anchor_span(source_text: str, start_anchor: str, end_anchor: str) -> tuple[int, int]:
    if not start_anchor or not end_anchor:
        raise ValueError("start_anchor and end_anchor must be non-empty")
    starts = [match.start() for match in re.finditer(re.escape(start_anchor), source_text)]
    if len(starts) != 1:
        raise ValueError(f"start_anchor must occur exactly once; found {len(starts)}")
    start = starts[0]
    end_matches = [
        match.end()
        for match in re.finditer(re.escape(end_anchor), source_text[start:])
    ]
    if len(end_matches) != 1:
        raise ValueError(f"end_anchor after start must occur exactly once; found {len(end_matches)}")
    return start, start + end_matches[0]


def _resolve_user_targets(
    source_text: str, atoms: list[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    raw_targets = plan.get("targets")
    if not isinstance(raw_targets, list) or not 3 <= len(raw_targets) <= 5:
        raise ValueError("USER_TARGETED_EXACT_RANGES_V1 requires 3-5 targets")
    atom_positions = {atom["atom_id"]: index for index, atom in enumerate(atoms)}
    max_atoms = plan.get("max_target_atoms", DEFAULT_USER_TARGET_MAX_ATOMS)
    max_chars = plan.get("max_target_chars", DEFAULT_USER_TARGET_MAX_CHARS)
    if (
        not isinstance(max_atoms, int)
        or isinstance(max_atoms, bool)
        or max_atoms < 2
        or not isinstance(max_chars, int)
        or isinstance(max_chars, bool)
        or max_chars < 100
    ):
        raise ValueError("max_target_atoms/max_target_chars must be sensible positive integers")
    resolved: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for serial, target in enumerate(raw_targets, start=1):
        if not isinstance(target, dict):
            raise ValueError("every target must be an object")
        target_id = target.get("target_id", f"T{serial:03d}")
        if not isinstance(target_id, str) or not target_id or target_id in seen_ids:
            raise ValueError("target_id must be unique and non-empty")
        seen_ids.add(target_id)
        target_mode = target.get("target_mode")
        if target_mode not in DIRECTOR_TARGET_MODES:
            raise ValueError(f"{target_id}: target_mode must be EDITED_SEQUENCE or GENERATABLE_SHOT")
        atom_range = target.get("atom_range")
        if isinstance(atom_range, dict):
            first = atom_range.get("first_atom_id")
            last = atom_range.get("last_atom_id")
            if first not in atom_positions or last not in atom_positions:
                raise ValueError(f"{target_id}: atom_range references an unknown atom")
            first_index, last_index = atom_positions[first], atom_positions[last]
        else:
            start_cp, end_cp = _unique_anchor_span(
                source_text,
                target.get("start_anchor"),
                target.get("end_anchor"),
            )
            first_index, last_index = _atom_indexes_for_span(atoms, start_cp, end_cp)
        before = target.get("context_atoms_before", 0)
        after = target.get("context_atoms_after", 0)
        if (
            not isinstance(before, int)
            or isinstance(before, bool)
            or before < 0
            or not isinstance(after, int)
            or isinstance(after, bool)
            or after < 0
        ):
            raise ValueError(f"{target_id}: context_atoms_before/after must be non-negative integers")
        if first_index > last_index:
            raise ValueError(f"{target_id}: atom range is reversed")
        resolved.append(
            {
                "target_id": target_id,
                "first_index": first_index,
                "last_index": last_index,
                "context_atoms_before": before,
                "context_atoms_after": after,
                "target_mode": target_mode,
                "allow_wide_window": target.get("allow_wide_window", False),
                "allow_continuation_boundary": target.get("allow_continuation_boundary", False),
            }
        )
    resolved.sort(key=lambda item: (item["first_index"], item["last_index"]))
    for left, right in zip(resolved, resolved[1:]):
        if right["first_index"] <= left["last_index"]:
            raise ValueError("explicit target ranges must not overlap")
    for index, target in enumerate(resolved):
        lower = resolved[index - 1]["last_index"] + 1 if index > 0 else 0
        upper = resolved[index + 1]["first_index"] - 1 if index + 1 < len(resolved) else len(atoms) - 1
        target["first_index"] = max(lower, target["first_index"] - target.pop("context_atoms_before"))
        target["last_index"] = min(upper, target["last_index"] + target.pop("context_atoms_after"))
        for flag in ("allow_wide_window", "allow_continuation_boundary"):
            if not isinstance(target[flag], bool):
                raise ValueError(f"{target['target_id']}: {flag} must be boolean")
        selected = atoms[target["first_index"] : target["last_index"] + 1]
        selected_text = "".join(atom["text"] for atom in selected)
        if not target.pop("allow_wide_window") and (
            len(selected) > max_atoms or len(selected_text) > max_chars
        ):
            raise ValueError(
                f"E_USER_TARGET_WINDOW_WIDE:{target['target_id']}: "
                f"selected {len(selected)} atoms/{len(selected_text)} chars; narrow the anchors "
                "or explicitly set allow_wide_window=true after editorial review"
            )
        stripped = selected_text.rstrip()
        next_text = (
            atoms[target["last_index"] + 1]["text"].lstrip()
            if target["last_index"] + 1 < len(atoms)
            else ""
        )
        incomplete_punctuation = bool(re.search(r"[,，、：:；;—-]$", stripped))
        unbalanced_quotes = stripped.count("“") != stripped.count("”")
        direct_continuation = bool(
            len(selected) >= 6 and next_text and CONTINUATION_START_RE.match(next_text)
        )
        if not target.pop("allow_continuation_boundary") and (
            incomplete_punctuation or unbalanced_quotes or direct_continuation
        ):
            raise ValueError(
                f"E_USER_TARGET_BOUNDARY_INCOMPLETE:{target['target_id']}: "
                "the selected window ends inside a clause/quote or before a direct discourse continuation; "
                "extend to the next complete event boundary"
            )
    return resolved


def _dialogue_inventory(source_text: str, atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for serial, match in enumerate(re.finditer(r"“([^”]+)”", source_text), start=1):
        text = match.group(1)
        first, last = _atom_indexes_for_span(atoms, match.start(1), match.end(1))
        semantic_span = semantic_span_containing_quote(
            source_text, match.start(), match.end()
        )
        semantic_start_cp = (
            semantic_span["start_cp"] if semantic_span is not None else None
        )
        semantic_end_cp = (
            semantic_span["end_cp"] if semantic_span is not None else None
        )
        speaker_hint = infer_spoken_speaker_hint(
            source_text,
            match.start(),
            match.end(),
            contract_version=CONTRACT_VERSION,
        )
        classification_hints, context_evidence = derive_quote_classification_hints(
            source_text,
            match.start(),
            match.end(),
            text,
            semantic_start_cp=semantic_start_cp,
            semantic_end_cp=semantic_end_cp,
        )
        vocal_speaker = context_evidence.get("vocalization_speaker_hint")
        if "LIKELY_NON_LEXICAL_VOCALIZATION" in classification_hints:
            speaker_hint = (
                vocal_speaker
                if isinstance(vocal_speaker, str)
                and vocal_speaker != "SOURCE_UNSPECIFIED"
                else "SOURCE_UNSPECIFIED"
            )
        inventory.append(
            {
                "dialogue_id": f"DLG{serial:04d}",
                "speaker": "SOURCE_UNSPECIFIED",
                "speaker_hint": speaker_hint,
                "source_quote_type": "UNCLASSIFIED_SOURCE_QUOTE",
                "text": text,
                "text_sha256": sha256_text(text),
                "start_cp": match.start(1),
                "end_cp": match.end(1),
                "source_refs": [atom["atom_id"] for atom in atoms[first : last + 1]],
                "classification_hints": classification_hints,
                "context_evidence": context_evidence,
            }
        )
    return inventory


def _fail_on_unresolved_strong_nonlexical(
    inventory: list[dict[str, Any]],
) -> None:
    """Stop before authoring when a clear vocal event lacks a source owner."""

    unresolved = [
        item
        for item in inventory
        if "LIKELY_NON_LEXICAL_VOCALIZATION" in item.get("classification_hints", [])
        and item.get("speaker_hint") == "SOURCE_UNSPECIFIED"
    ]
    if not unresolved:
        return
    details = "、".join(
        f"{item.get('dialogue_id')}“{item.get('text', '')}”"
        for item in unresolved
    )
    raise ValueError(
        "E_NON_LEXICAL_VOCALIZATION_SPEAKER: "
        f"{details} 具有明确人物发声结构，但来源主体仍无法唯一确定；"
        "请补充来源中的明确人物归属后重新准备，不能在创作填写区猜测或改成环境声。"
    )


def _resolve_machine_targets(
    atoms: list[dict[str, Any]], dialogue_inventory: list[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    sample_count = plan.get("sample_count", 3)
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or not 3 <= sample_count <= 5:
        raise ValueError("MACHINE_REPRESENTATIVE_V1 sample_count must be 3-5")
    # Form deterministic scene-sized candidates first.  A Pilot is selected
    # from these windows; an atom is never treated as a Unit by itself merely
    # because it contains a quotation mark.
    if len(atoms) < sample_count * 2:
        raise ValueError(
            "MACHINE_REPRESENTATIVE_V1 needs at least two source atoms per requested Pilot window"
        )
    preferred_size = max(2, min(4, len(atoms) // sample_count))
    candidate_windows = _partition_gap(0, len(atoms) - 1, preferred_size)
    if len(candidate_windows) < sample_count:
        raise ValueError("source is too short to form the requested number of distinct multi-atom windows")

    candidate_units = [
        {
            "unit_id": f"U{index + 1:03d}",
            "order": index + 1,
            "source_refs": [atom["atom_id"] for atom in atoms[first : last + 1]],
            "source_window": _source_window(atoms, first, last),
        }
        for index, (first, last) in enumerate(candidate_windows)
    ]
    candidate_features = expected_feature_matrix(
        {
            "units": candidate_units,
            "source_atoms": atoms,
            "source_dialogue_inventory": dialogue_inventory,
            "selection_request": {"target_modes": {}},
        }
    )

    def feature_tokens(feature: dict[str, Any]) -> set[str]:
        tokens = {feature["position_bucket"], feature["route_risk"]}
        if feature["has_verbatim_dialogue"]:
            tokens.add("VERBATIM_DIALOGUE")
        if feature["dialogue_turn_count"] >= 4:
            tokens.add("DIALOGUE_DENSE")
        if feature["speaker_count"] >= 3:
            tokens.add("MULTI_SPEAKER")
        if feature["action_or_reaction_signal_count"]:
            tokens.add("ACTION_REACTION")
        return tokens

    selected: list[int] = []
    covered: set[str] = set()
    count = len(candidate_windows)
    for slot in range(sample_count):
        if slot == 0:
            picked = 0
            selected.append(picked)
            covered.update(feature_tokens(candidate_features[picked]))
            continue
        if slot == sample_count - 1:
            picked = count - 1
            if picked in selected:
                picked = next(index for index in reversed(range(count)) if index not in selected)
            selected.append(picked)
            covered.update(feature_tokens(candidate_features[picked]))
            continue
        ideal = round((slot + 0.5) * (count - 1) / sample_count)
        desired_bucket = ("OPENING", "MIDDLE", "LATE")[min(2, (slot * 3) // sample_count)]
        candidates = sorted(
            range(count),
            key=lambda index: (
                index in selected,
                candidate_features[index]["position_bucket"] != desired_bucket,
                -len(feature_tokens(candidate_features[index]) - covered),
                candidate_features[index]["route_risk"] == "LOW",
                not candidate_features[index]["has_verbatim_dialogue"],
                abs(index - ideal),
                index,
            ),
        )
        picked = next(index for index in candidates if index not in selected)
        selected.append(picked)
        covered.update(feature_tokens(candidate_features[picked]))
    selected.sort()
    resolved: list[dict[str, Any]] = []
    for serial, index in enumerate(selected, start=1):
        first_index, last_index = candidate_windows[index]
        auto_findings: list[str] = []
        first_text = normalize_text(atoms[first_index]["text"]).lstrip()
        previous_selected_last = candidate_windows[selected[serial - 2]][1] if serial > 1 else -1
        if (
            first_index > 0
            and first_index - 1 > previous_selected_last
            and AUTO_CONTEXT_DEPENDENT_START_RE.search(first_text)
        ):
            first_index -= 1
            auto_findings.append("AUTO_CONTEXT_EXPANDED:ANAPHORIC_OR_REACTION_ENTRY")
        feature = candidate_features[index]
        target_mode = "EDITED_SEQUENCE" if feature["route_risk"] != "LOW" else "GENERATABLE_SHOT"
        resolved.append(
            {
                "target_id": f"T{serial:03d}",
                "first_index": first_index,
                "last_index": last_index,
                "target_mode": target_mode,
                "auto_route_findings": auto_findings,
            }
        )
    return resolved


def _partition_gap(first: int, last: int, preferred_size: int = 4) -> list[tuple[int, int]]:
    """Partition an uncovered source gap into compact, mostly multi-atom scenes."""
    if first > last:
        return []
    count = last - first + 1
    if count <= preferred_size + 1:
        return [(first, last)]
    sizes: list[int] = []
    remaining = count
    while remaining:
        size = min(preferred_size, remaining)
        if remaining - size == 1:
            size += 1
        sizes.append(size)
        remaining -= size
    result: list[tuple[int, int]] = []
    cursor = first
    for size in sizes:
        result.append((cursor, cursor + size - 1))
        cursor += size
    return result


def _source_window(atoms: list[dict[str, Any]], first: int, last: int) -> dict[str, Any]:
    selected = atoms[first : last + 1]
    text = "".join(atom["text"] for atom in selected)
    return {
        "first_atom_id": selected[0]["atom_id"],
        "last_atom_id": selected[-1]["atom_id"],
        "atom_count": len(selected),
        "start_cp": selected[0]["start_cp"],
        "end_cp": selected[-1]["end_cp"],
        "text_sha256": sha256_text(text),
    }


def _build_units(
    atoms: list[dict[str, Any]], targets: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    target_to_unit: dict[str, str] = {}
    units: list[dict[str, Any]] = []
    segments: list[tuple[int, int, dict[str, Any] | None]] = []
    cursor = 0
    for target in targets:
        for first, last in _partition_gap(cursor, target["first_index"] - 1):
            segments.append((first, last, None))
        segments.append((target["first_index"], target["last_index"], target))
        cursor = target["last_index"] + 1
    for first, last in _partition_gap(cursor, len(atoms) - 1):
        segments.append((first, last, None))
    for index, last, target in segments:
        serial = len(units) + 1
        unit_id = f"U{serial:03d}"
        refs = [atom["atom_id"] for atom in atoms[index : last + 1]]
        units.append(
            {
                "unit_id": unit_id,
                "order": serial,
                "source_refs": refs,
                "source_window": _source_window(atoms, index, last),
            }
        )
        if target is not None:
            target_to_unit[target["target_id"]] = unit_id
    return units, target_to_unit


def _feature_matrix(
    atoms: list[dict[str, Any]],
    units: list[dict[str, Any]],
    dialogues: list[dict[str, Any]],
    target_modes: dict[str, str],
) -> list[dict[str, Any]]:
    return expected_feature_matrix(
        {
            "units": units,
            "source_atoms": atoms,
            "source_dialogue_inventory": dialogues,
            "selection_request": {"target_modes": target_modes},
        }
    )


def _selection_evidence(
    selection_mode: str,
    units: list[dict[str, Any]],
    selected_unit_ids: list[str],
    unit_manifest_sha256: str,
    feature_matrix: list[dict[str, Any]],
    feature_matrix_sha256: str,
) -> dict[str, Any]:
    positions = [next(i for i, unit in enumerate(units) if unit["unit_id"] == unit_id) for unit_id in selected_unit_ids]
    gaps = [right - left for left, right in zip(positions, positions[1:])]
    matrix_map = {item["unit_id"]: item for item in feature_matrix}
    covered: list[str] = []
    for unit_id in selected_unit_ids:
        item = matrix_map[unit_id]
        for feature in (
            item["position_bucket"],
            "VERBATIM_DIALOGUE" if item["has_verbatim_dialogue"] else "NO_VERBATIM_DIALOGUE",
            "DIALOGUE_DENSE" if item.get("dialogue_turn_count", 0) >= 4 else None,
            "MULTI_SPEAKER" if item.get("speaker_count", 0) >= 3 else None,
            "ACTION_REACTION" if item.get("action_or_reaction_signal_count", 0) >= 1 else None,
            item.get("route_risk"),
            item.get("target_mode"),
        ):
            if feature and feature not in covered:
                covered.append(feature)
    available: list[str] = []
    for item in feature_matrix:
        for feature in (
            item["position_bucket"],
            "VERBATIM_DIALOGUE" if item["has_verbatim_dialogue"] else None,
            "DIALOGUE_DENSE" if item.get("dialogue_turn_count", 0) >= 4 else None,
            "MULTI_SPEAKER" if item.get("speaker_count", 0) >= 3 else None,
            "ACTION_REACTION" if item.get("action_or_reaction_signal_count", 0) >= 1 else None,
            item.get("route_risk"),
            item.get("target_mode"),
        ):
            if feature and feature not in available:
                available.append(feature)
    return {
        "algorithm": selection_mode,
        "selected_unit_ids": selected_unit_ids,
        "selected_order_indexes": positions,
        "adjacent_order_gaps": gaps,
        "derived_noncontiguous": bool(gaps) and all(gap > 1 for gap in gaps),
        "covered_features": covered,
        "missing_available_features": [feature for feature in available if feature not in covered],
        "unit_manifest_sha256": unit_manifest_sha256,
        "feature_matrix_sha256": feature_matrix_sha256,
    }


def _assert_helper_baseline(
    contract: dict[str, Any], target_windows: list[dict[str, Any]]
) -> None:
    """Fail before model authoring if helper-owned projections disagree."""

    if target_windows != expected_target_windows(contract):
        raise ValueError(
            "E_PREPARE_HELPER_BASELINE: target_windows differ from the "
            "validator's canonical helper projection"
        )
    request = contract["selection_request"]
    feature_map = {
        item["unit_id"]: item for item in expected_feature_matrix(contract)
    }
    window_map = {item["unit_id"]: item for item in target_windows}
    for unit_id in request["sample_unit_ids"]:
        expected = expected_route_findings(
            feature_map[unit_id], window_map[unit_id]["single_shot_eligibility"]
        )
        if request["route_findings"].get(unit_id) != expected:
            raise ValueError(
                "E_PREPARE_HELPER_BASELINE: route_findings differ from the "
                f"canonical feature/eligibility projection for {unit_id}"
            )


def build_target_plan(selection_mode: str, sample_count: int) -> dict[str, Any]:
    """Build the only target plan that can be derived without creator ranges.

    Explicit-range selection remains available through the legacy target-plan
    input because exact source anchors cannot be guessed from a sample count.
    """

    if selection_mode != "MACHINE_REPRESENTATIVE_V1":
        raise ValueError(
            "high-level plan generation supports MACHINE_REPRESENTATIVE_V1 only; "
            "USER_TARGETED_EXACT_RANGES_V1 requires an explicit target-plan JSON"
        )
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or not 3 <= sample_count <= 5:
        raise ValueError("sample_count must be an integer from 3 to 5")
    return {"selection_mode": selection_mode, "sample_count": sample_count}


def _canonical_workflow_commands(
    run_id: str,
    output_dir: Path,
    *,
    commit_mode: str,
    source_path: Path | None = None,
    selection_mode: str | None = None,
    sample_count: int | None = None,
    output_names: list[str] | None = None,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    temp_root = (
        output_dir
        if commit_mode == IN_PLACE_COMMIT_MODE
        else output_dir.parent / f".alpha7-tmp-{run_id}"
    )
    finalizer = Path(__file__).resolve().with_name("finalize_longform_contract.py")
    base = [
        str(Path(sys.executable).resolve()),
        str(finalizer),
        str(temp_root / "AUTHORING.json"),
        str(output_dir),
        "--overlays",
        str(temp_root / "OVERLAYS.json"),
    ]
    workflow: dict[str, Any] = {
        "mode": "CHECK_THEN_COMMIT_V1",
        "check_argv": [*base, "--check-overlays"],
        "retry_argv": [*base, "--check-overlays"],
        "commit_argv": base,
        "failure_policy": "CHECK 失败时保留三份载体，只修改 OVERLAYS.json 后重试；不得验后改名或复制。",
    }
    if source_path is not None and selection_mode is not None and sample_count is not None:
        prepare = Path(__file__).resolve()
        names = output_names or list(DEFAULT_OUTPUT_NAMES)
        workflow["reprepare_argv"] = [
            str(Path(sys.executable).resolve()),
            str(prepare),
            str(source_path.resolve()),
            "--output-dir",
            str(output_dir),
            "--run-id",
            run_id,
            "--selection-mode",
            selection_mode,
            "--sample-count",
            str(sample_count),
            "--package-name",
            names[0],
            "--machine-state-name",
            names[1],
            "--run-summary-name",
            names[2],
            "--reprepare",
        ]
    return workflow


def _canonical_output_names(run_id: str, output_names: list[str] | None) -> list[str]:
    del run_id  # retained in the signature for legacy import compatibility
    names = output_names or list(DEFAULT_OUTPUT_NAMES)
    role_extensions = (".md", ".json", ".md")
    invalid_windows_name = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
    collision_keys = (
        [
            unicodedata.normalize("NFC", name).rstrip(" .").casefold()
            for name in names
            if isinstance(name, str)
        ]
        if isinstance(names, list)
        else []
    )
    if (
        not isinstance(names, list)
        or len(names) != 3
        or len(set(collision_keys)) != 3
        or any(
            not isinstance(name, str)
            or not name
            or unicodedata.normalize("NFC", name) != name
            or name in {".", ".."}
            or Path(name).name != name
            or invalid_windows_name.search(name) is not None
            or INVISIBLE_FILENAME_RE.search(name) is not None
            or name.endswith((".", " "))
            or name.split(".", 1)[0].upper() in WINDOWS_RESERVED_BASENAMES
            or not name.casefold().endswith(extension)
            for name, extension in zip(names, role_extensions)
        )
    ):
        raise ValueError(
            "output_names must be three unique safe basenames in package(.md), "
            "machine-state(.json), run-summary(.md) role order"
        )
    return list(names)


def source_read_scope_attestation() -> dict[str, Any]:
    return {
        "attestation_version": "alpha7-guide-only-scope-1.0",
        "status": "DECLARED_PROCESS_BOUNDARY",
        "formal_authoring_inputs": [
            "OVERLAYS.json.authoring_guide",
            "OVERLAYS.json.target_windows",
            "OVERLAYS.json.compiled_unit_overlays",
        ],
        "forbidden_reads": ["scripts", "tests", "schemas", "fixtures", "self-test gold"],
        "host_enforcement": "NOT_EXPOSED",
    }


def runtime_helper_scripts_sha256() -> str:
    script_root = Path(__file__).resolve().parent
    projection = [
        {
            "name": name,
            "sha256": hashlib.sha256((script_root / name).read_bytes()).hexdigest(),
        }
        for name in (
            "prepare_longform_authoring.py",
            "finalize_longform_contract.py",
            "validate_longform_contract.py",
        )
    ]
    return sha256_value(projection)


def prepare_authoring(
    source_text: str,
    plan: dict[str, Any],
    run_id: str,
    *,
    output_dir: Path | None = None,
    output_names: list[str] | None = None,
    commit_mode: str = SIBLING_COMMIT_MODE,
    source_path: Path | None = None,
    sample_count: int | None = None,
) -> dict[str, Any]:
    source_text = normalize_text(source_text)
    if not source_text.strip():
        raise ValueError("source text must contain non-whitespace content")
    if not re.fullmatch(r"RUN\d+", run_id):
        raise ValueError("run_id must match RUN followed by digits")
    selection_mode = plan.get("selection_mode")
    if selection_mode not in SELECTION_MODES:
        raise ValueError("selection_mode is missing or unsupported")
    atoms = _split_atoms(source_text)
    dialogues = _dialogue_inventory(source_text, atoms)
    _fail_on_unresolved_strong_nonlexical(dialogues)
    source_anomalies: list[dict[str, Any]] = []
    if source_text.count("“") != source_text.count("”"):
        source_anomalies.append(
            {
                "anomaly_id": "ANOM-QUOTE-BALANCE-001",
                "kind": "UNBALANCED_CHINESE_DOUBLE_QUOTE",
                "left_count": source_text.count("“"),
                "right_count": source_text.count("”"),
                "policy": "PRESERVE_AND_REVIEW",
            }
        )
    plan_anomalies = plan.get("source_anomalies", [])
    if not isinstance(plan_anomalies, list):
        raise ValueError("source_anomalies must be a structured array when provided")
    anomaly_ids = {item["anomaly_id"] for item in source_anomalies}
    for index, item in enumerate(plan_anomalies, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"source_anomalies[{index - 1}] must be an object; strings are not accepted")
        allowed = {"anomaly_id", "kind", "text", "variant", "span"}
        if set(item) - allowed:
            raise ValueError(f"source_anomalies[{index - 1}] has unsupported fields")
        anomaly_id = item.get("anomaly_id", f"ANOM-USER-{index:03d}")
        kind = item.get("kind")
        if not isinstance(anomaly_id, str) or not anomaly_id.strip() or anomaly_id in anomaly_ids:
            raise ValueError("source anomaly IDs must be unique non-empty strings")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError(f"{anomaly_id}: kind must be a non-empty string")
        anomaly: dict[str, Any] = {
            "anomaly_id": anomaly_id,
            "kind": kind,
            "policy": "PRESERVE_AND_REVIEW",
        }
        text_evidence = item.get("text")
        variant = item.get("variant")
        span = item.get("span")
        has_evidence = False
        if text_evidence is not None:
            if not isinstance(text_evidence, str) or not text_evidence.strip():
                raise ValueError(f"{anomaly_id}: text evidence must be non-empty")
            if normalize_text(text_evidence) not in source_text:
                raise ValueError(f"{anomaly_id}: text evidence is not present in the frozen source")
            anomaly["text"] = normalize_text(text_evidence)
            has_evidence = True
        if variant is not None:
            if not isinstance(variant, str) or not variant.strip():
                raise ValueError(f"{anomaly_id}: variant must be non-empty")
            anomaly["variant"] = normalize_text(variant)
            has_evidence = True
        if span is not None:
            if not isinstance(span, dict) or set(span) != {"start_cp", "end_cp"}:
                raise ValueError(f"{anomaly_id}: span must contain exactly start_cp/end_cp")
            start_cp, end_cp = span.get("start_cp"), span.get("end_cp")
            if (
                not isinstance(start_cp, int)
                or isinstance(start_cp, bool)
                or not isinstance(end_cp, int)
                or isinstance(end_cp, bool)
                or not (0 <= start_cp < end_cp <= len(source_text))
            ):
                raise ValueError(f"{anomaly_id}: span is outside the frozen source")
            excerpt = source_text[start_cp:end_cp]
            anomaly["span"] = {
                "start_cp": start_cp,
                "end_cp": end_cp,
                "text_sha256": sha256_text(excerpt),
            }
            has_evidence = True
        if not has_evidence:
            raise ValueError(f"{anomaly_id}: provide text, variant, or an exact span")
        anomaly_ids.add(anomaly_id)
        source_anomalies.append(anomaly)
    targets = (
        _resolve_user_targets(source_text, atoms, plan)
        if selection_mode == "USER_TARGETED_EXACT_RANGES_V1"
        else _resolve_machine_targets(atoms, dialogues, plan)
    )
    units, target_to_unit = _build_units(atoms, targets)
    target_modes = {target_to_unit[item["target_id"]]: item["target_mode"] for item in targets}
    provisional_features = _feature_matrix(atoms, units, dialogues, target_modes)
    feature_by_unit = {item["unit_id"]: item for item in provisional_features}
    atom_map = {atom["atom_id"]: atom for atom in atoms}
    unit_map = {unit["unit_id"]: unit for unit in units}
    semantic_anchors_by_unit: dict[str, list[dict[str, Any]]] = {}
    single_shot_by_unit: dict[str, dict[str, Any]] = {}
    route_findings: dict[str, list[str]] = {}
    for target in targets:
        unit_id = target_to_unit[target["target_id"]]
        unit = unit_map[unit_id]
        feature = feature_by_unit[unit_id]
        semantic_anchors = _semantic_anchors_for_unit(unit, atom_map, dialogues)
        eligibility = _single_shot_eligibility(unit, semantic_anchors, feature)
        semantic_anchors_by_unit[unit_id] = semantic_anchors
        single_shot_by_unit[unit_id] = eligibility
        if not eligibility["eligible"]:
            target["target_mode"] = "EDITED_SEQUENCE"
        findings = expected_route_findings(feature, eligibility)
        if findings:
            route_findings[unit_id] = findings
    target_modes = {target_to_unit[item["target_id"]]: item["target_mode"] for item in targets}
    manifest_projection = [
        {
            "unit_id": unit["unit_id"],
            "order": unit["order"],
            "source_refs": unit["source_refs"],
            "source_window": unit["source_window"],
        }
        for unit in units
    ]
    unit_manifest_sha256 = sha256_value(manifest_projection)
    feature_matrix = _feature_matrix(atoms, units, dialogues, target_modes)
    feature_matrix_sha256 = sha256_value(feature_matrix)
    selected_unit_ids = [target_to_unit[item["target_id"]] for item in targets]
    evidence = _selection_evidence(
        selection_mode,
        units,
        selected_unit_ids,
        unit_manifest_sha256,
        feature_matrix,
        feature_matrix_sha256,
    )
    canonical_output_dir = (
        output_dir.resolve()
        if output_dir is not None
        else (Path.cwd() / f"{run_id.lower()}-longform-output").resolve()
    )
    exact_output_names = _canonical_output_names(run_id, output_names)
    if commit_mode not in {IN_PLACE_COMMIT_MODE, SIBLING_COMMIT_MODE}:
        raise ValueError("commit_mode is unsupported")
    if commit_mode == IN_PLACE_COMMIT_MODE and {
        name.casefold() for name in exact_output_names
    }.intersection(name.casefold() for name in TEMP_INPUT_NAMES):
        raise ValueError("in-place final output names must not collide with the three carrier names")
    manifest_path = Path(__file__).resolve().parent.parent / "MANIFEST.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("runtime MANIFEST.json is missing or unreadable") from exc
    skill_build_id = manifest.get("build") if isinstance(manifest, dict) else None
    if not isinstance(skill_build_id, str) or not skill_build_id:
        raise ValueError("runtime MANIFEST.json has no build identity")
    temp_root_value = "." if commit_mode == IN_PLACE_COMMIT_MODE else f".alpha7-tmp-{run_id}"
    contract: dict[str, Any] = {
        "authoring_version": AUTHORING_VERSION,
        "contract_version": CONTRACT_VERSION,
        "engine": "SILVER_LONGFORM",
        "delivery_mode": "TEXT_ONLY_ECO_TEST",
        "project_status": "GLOBAL_READY",
        "source": {
            "ledger": "SOURCE_ATOMS",
            "source_sha256": sha256_text(source_text),
            "source_complete": True,
        },
        "source_atoms": atoms,
        "source_atoms_sha256": sha256_value(atoms),
        "source_dialogue_inventory": dialogues,
        "source_dialogue_inventory_sha256": sha256_value(dialogues),
        "source_anomalies": source_anomalies,
        "source_anomalies_sha256": sha256_value(source_anomalies),
        "unit_manifest_sha256": unit_manifest_sha256,
        "feature_matrix_sha256": feature_matrix_sha256,
        "selection_request": {
            "selection_mode": selection_mode,
            "sample_unit_ids": selected_unit_ids,
            "target_ids": [item["target_id"] for item in targets],
            "target_modes": {unit_id: target_modes[unit_id] for unit_id in selected_unit_ids},
            "route_findings": {unit_id: route_findings.get(unit_id, []) for unit_id in selected_unit_ids},
            "selection_evidence": evidence,
        },
        "authorizations": [],
        "project_rules": [
            {"rule_id": "RULE001", "text": "保持来源忠实", "semantic_tags": ["CONTROL:FAITHFUL"]}
        ],
        "continuity_bible": {"identity": "冻结", "world": "冻结"},
        "visual_continuity_domains": [{"domain_id": "VCD001", "description": "统一视觉域"}],
        "units": units,
        "batch_plan": {"requested_mode": "FULL_PROJECT", "normalized_mode": "FULL_EXPORT", "batches": []},
        "checkpoints": [],
        "latest_checkpoint_id": None,
        "latest_checkpoint_sha256": None,
        "production_validation": "NOT_TESTED",
        "production_evidence": {},
        "status_contract": expected_text_status_contract("GLOBAL_READY"),
        "output_contract": {
            "workspace_memory_policy": "DO_NOT_WRITE",
            "strict_output_set": True,
            "exact_relative_output_names": exact_output_names,
            "commit_mode": commit_mode,
            "temp_root": temp_root_value,
            "temp_input_names": list(TEMP_INPUT_NAMES),
            "temp_root_cleaned": False,
        },
        "authoring_workflow": _canonical_workflow_commands(
            run_id,
            canonical_output_dir,
            commit_mode=commit_mode,
            source_path=source_path,
            selection_mode=selection_mode,
            sample_count=sample_count,
            output_names=exact_output_names,
        ),
        "runtime_identity": {
            "identity_version": "alpha7-runtime-identity-1.0",
            "skill_build_id": skill_build_id,
            "skill_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "helper_scripts_sha256": runtime_helper_scripts_sha256(),
            "python_runtime": sys.version,
            "helper_lock_sha256": None,
            "archive_identity_status": "NOT_EXPOSED",
        },
        "continuation_authorization": {
            "scope": "TEXT_ONLY_TO_RUN_SUMMARY",
            "external_actions": False,
            "creative_defaults": "PROPOSED_ONLY",
            "stop_conditions": [
                "SOURCE_AMBIGUITY_AFFECTS_MEANING",
                "P0_BLOCKER",
                "CONTEXT_INSUFFICIENT",
            ],
        },
    }
    contract["global_state"] = expected_global_state(contract)
    contract["global_state_sha256"] = sha256_value(contract["global_state"])
    contract["skeleton_sha256"] = expected_skeleton_sha256(contract, [unit["unit_id"] for unit in units])

    dialogue_map = {item["dialogue_id"]: item for item in dialogues}
    target_windows: list[dict[str, Any]] = []
    overlays: list[dict[str, Any]] = []
    for target in targets:
        unit_id = target_to_unit[target["target_id"]]
        unit = unit_map[unit_id]
        slot_ids = expected_dialogue_ids_for_unit(unit, dialogues)
        source_window_text = source_text[
            unit["source_window"]["start_cp"] : unit["source_window"]["end_cp"]
        ]
        minimum_shots = (
            expected_sequence_minimum_shots(
                source_window_text,
                dialogue_turns=len(slot_ids),
                atom_count=len(unit["source_refs"]),
            )
            if target["target_mode"] == "EDITED_SEQUENCE"
            else 0
        )
        locked_scaffold = _locked_director_scaffold(
            target["target_mode"],
            semantic_anchors_by_unit[unit_id],
            minimum_shots,
        )
        fixed_transform_roles = {
            "source_role": "PROVIDER_NEUTRAL_MASTER",
            "target_role": "NEUTRAL_EXECUTION_PROMPT",
            "derivation": "HELPER_DERIVED",
        }
        target_window = {
            "target_id": target["target_id"],
            "unit_id": unit_id,
            "target_mode": target["target_mode"],
            "source_window": unit["source_window"],
            "source_excerpt": source_window_text,
            "dialogue_slot_ids": slot_ids,
            "quote_classification_hints": {
                dialogue_id: {
                    "classification_hints": dialogue_map[dialogue_id]["classification_hints"],
                    "context_evidence": dialogue_map[dialogue_id]["context_evidence"],
                }
                for dialogue_id in slot_ids
            },
            "route_findings": route_findings.get(unit_id, []),
            "single_shot_eligibility": single_shot_by_unit[unit_id],
            "locked_director_scaffold": locked_scaffold,
            "locked_scaffold_sha256": sha256_value(locked_scaffold),
            "fixed_transform_roles": fixed_transform_roles,
        }
        semantic_gate = expected_semantic_gate(contract, unit, locked_scaffold)
        target_window["semantic_gate"] = semantic_gate
        target_windows.append(target_window)
        source_locked_nonlexical_speakers = (
            source_locked_nonlexical_speakers_from_window(target_window)
        )
        creative_shots = (
            [
                {
                    "shot_id": shot["shot_id"],
                    "purpose": "",
                    "action_additions": [],
                    "camera": "",
                }
                for shot in locked_scaffold["shots"]
            ]
            if target["target_mode"] == "EDITED_SEQUENCE"
            else []
        )
        creative_locked_shots = (
            locked_scaffold["shots"]
            if target["target_mode"] == "EDITED_SEQUENCE"
            else []
        )
        overlays.append(
            {
                "unit_id": unit_id,
                "editable_paths": _editable_paths(
                    slot_ids,
                    creative_locked_shots,
                    set(source_locked_nonlexical_speakers),
                    len(semantic_gate["claim_slots"]) - 1,
                ),
                "director_overlay": {
                    "performance": "",
                    "camera": "",
                    "sound": "",
                    "dialogue_speakers": {
                        dialogue_id: "SOURCE_UNSPECIFIED"
                        for dialogue_id in slot_ids
                        if dialogue_id not in source_locked_nonlexical_speakers
                    },
                    "quote_classifications": {dialogue_id: "UNSET" for dialogue_id in slot_ids},
                    "shot_creative": creative_shots,
                },
                "prompt_overlay": {
                    "master_prompt_template": "",
                    "transform_plan": {
                        "preserve": [],
                        "operations": [],
                        "deferred_provider_decisions": [],
                    },
                    "neutral_execution_prompt_template": "",
                    "claims": copy_json(semantic_gate["claim_slots"]),
                    "negative_clauses": [],
                },
                "quality_overlay": {
                    "scene_title": "",
                    "findings": [],
                },
            }
        )
    envelope = {
        "immutable_contract": contract,
        "target_windows": target_windows,
        "compiled_unit_overlays": overlays,
    }
    contract["authoring_guide_sha256"] = sha256_value(_authoring_guide(envelope))
    contract["helper_lock_sha256"] = sha256_value(expected_helper_lock_projection(contract))
    contract["runtime_identity"]["helper_lock_sha256"] = contract["helper_lock_sha256"]
    _assert_helper_baseline(contract, target_windows)
    return envelope


def run_self_test() -> dict[str, Any]:
    source = "开端。\n“第一句。”\n动作继续。\n中段。\n“第二句。”\n转折。\n尾段。\n“第三句。”\n结束。\n"
    plan = {
        "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
        "targets": [
            {"target_id": "T001", "start_anchor": "开端。", "end_anchor": "第一句。", "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
            {"target_id": "T002", "start_anchor": "中段。", "end_anchor": "第二句。", "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
            {"target_id": "T003", "start_anchor": "尾段。", "end_anchor": "第三句。", "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
        ],
    }
    envelope = prepare_authoring(source, plan, "RUN0")
    contract = envelope["immutable_contract"]
    if "".join(atom["text"] for atom in contract["source_atoms"]) != normalize_text(source):
        raise AssertionError("source atoms changed source text")
    if len(envelope["compiled_unit_overlays"]) != 3:
        raise AssertionError("self-test did not expose exactly three target overlays")
    expected_transform_plan = {
        "preserve": [],
        "operations": [],
        "deferred_provider_decisions": [],
    }
    if any(
        overlay["prompt_overlay"].get("transform_plan") != expected_transform_plan
        for overlay in envelope["compiled_unit_overlays"]
    ):
        raise AssertionError("prepare did not restrict transform_plan to three creative arrays")
    for window, overlay in zip(envelope["target_windows"], envelope["compiled_unit_overlays"]):
        if window["locked_scaffold_sha256"] != sha256_value(window["locked_director_scaffold"]):
            raise AssertionError("locked director scaffold hash was not deterministic")
        if window["fixed_transform_roles"] != {
            "source_role": "PROVIDER_NEUTRAL_MASTER",
            "target_role": "NEUTRAL_EXECUTION_PROMPT",
            "derivation": "HELPER_DERIVED",
        }:
            raise AssertionError("fixed transform roles were not helper-owned")
        if set(overlay["director_overlay"]) != {
            "performance", "camera", "sound", "dialogue_speakers",
            "quote_classifications", "shot_creative",
        }:
            raise AssertionError("compact director overlay leaked locked or machine-proof fields")
        if set(overlay["quality_overlay"]) != {"scene_title", "findings"}:
            raise AssertionError("compact quality overlay leaked status/check fields")
        if any(
            token in path
            for path in overlay["editable_paths"]
            for token in ("shot_id", "provenance", "status", "checks", "source_role", "target_role")
        ):
            raise AssertionError("editable_paths exposed a locked field")
    if any(window["source_window"]["atom_count"] < 2 for window in envelope["target_windows"]):
        raise AssertionError("self-test target did not retain a multi-atom window")
    compact = compact_overlay_work_surface(envelope)
    guide = compact.get("authoring_guide")
    if (
        not isinstance(guide, dict)
        or guide.get("guide_version") != AUTHORING_GUIDE_VERSION
        or "NON_LEXICAL_VOCALIZATION" not in guide.get("quote_classification_enum", [])
        or guide.get("record_shapes", {}).get("fixed_transform_roles", {}).get("derivation")
        != "HELPER_DERIVED"
        or guide.get("compatibility", {}).get("read_only_authoring_versions")
        != READ_ONLY_AUTHORING_VERSIONS
        or set(guide.get("unit_requirements", {}))
        != set(contract["selection_request"]["sample_unit_ids"])
    ):
        raise AssertionError("compact overlay did not carry its self-contained authoring guide")

    punctuated_source = (
        "甲推开舱门，乙停在门外。\n\n"
        "甲说：“照明正常，先别进来。”\n\n"
        "中段的风掠过桌面，纸页翻到背面。\n\n"
        "乙回答：“我看见了，马上关门。”\n\n"
        "尾声的灯再次亮起，门锁发出轻响。\n\n"
        "甲低声说：“等确认，再离开。”\n"
    )
    punctuated = prepare_authoring(
        punctuated_source,
        {
            "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
            "targets": [
                {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0002"}, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0003", "last_atom_id": "SRC0004"}, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0005", "last_atom_id": "SRC0006"}, "target_mode": "EDITED_SEQUENCE"},
            ],
        },
        "RUN11",
    )
    punctuated_contract = punctuated["immutable_contract"]
    punctuated_atoms = {
        atom["atom_id"]: atom for atom in punctuated_contract["source_atoms"]
    }
    if any(
        not source_anchor_is_complete(
            anchor["exact_text"], punctuated_atoms[anchor["source_ref"]]["text"]
        )
        for window in punctuated["target_windows"]
        for anchor in window["locked_director_scaffold"]["semantic_anchors"]
    ):
        raise AssertionError(
            "complete sentences with internal commas or closing quotes failed the source-anchor gate"
        )

    machine_source = "".join(
        f"场景{i:02d}，人物{'看向门口' if i % 3 == 0 else '向前走'}。\n"
        if i not in {5, 12, 19}
        else f"“机器样本对白{i:02d}。”角色说道。\n"
        for i in range(1, 25)
    )
    machine = prepare_authoring(
        machine_source,
        {"selection_mode": "MACHINE_REPRESENTATIVE_V1", "sample_count": 3},
        "RUN1",
    )
    machine_contract = machine["immutable_contract"]
    if any(window["source_window"]["atom_count"] < 2 for window in machine["target_windows"]):
        raise AssertionError("machine selection emitted a single-atom Pilot window")
    flattened = [
        ref
        for unit in machine_contract["units"]
        for ref in unit["source_refs"]
    ]
    if flattened != [atom["atom_id"] for atom in machine_contract["source_atoms"]]:
        raise AssertionError("machine selection broke unique full-source Unit ownership")
    evidence = machine_contract["selection_request"]["selection_evidence"]
    if evidence["feature_matrix_sha256"] != machine_contract["feature_matrix_sha256"]:
        raise AssertionError("machine selection evidence is not bound to the feature matrix")
    if not {"VERBATIM_DIALOGUE", "ACTION_REACTION"}.issubset(set(evidence["covered_features"])):
        raise AssertionError("machine selection ignored deterministic dialogue/action features")

    blank_separated_source = "".join(
        f"内容段{i:02d}，人物向前走。\n\n" for i in range(1, 10)
    )
    blank_separated = prepare_authoring(
        blank_separated_source,
        {"selection_mode": "MACHINE_REPRESENTATIVE_V1", "sample_count": 3},
        "RUN9",
    )
    blank_contract = blank_separated["immutable_contract"]
    if (
        len(blank_contract["source_atoms"]) != 9
        or any(not atom["text"].strip() for atom in blank_contract["source_atoms"])
        or "".join(atom["text"] for atom in blank_contract["source_atoms"])
        != normalize_text(blank_separated_source)
        or any(window["source_window"]["atom_count"] < 2 for window in blank_separated["target_windows"])
    ):
        raise AssertionError("blank separator lines inflated or damaged multi-content-atom windows")

    dense_source = (
        "门被推开。\n"
        "“先别进去。”甲说道。\n"
        "“里面有人。”乙说道。\n"
        "“我去看看。”丙说道。\n"
        "“一起走。”甲说道。\n"
        "三人回头，抓住门把，再次停下。\n"
        "远处灯亮。\n"
        "屋外安静。\n"
        "风吹过树梢。\n"
        "道路延伸。\n"
        "钟声响起。\n"
        "天色渐暗。\n"
    )
    dense_plan = {
        "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
        "targets": [
            {
                "target_id": "T001",
                "start_anchor": "门被推开。",
                "end_anchor": "三人回头，抓住门把，再次停下。",
                "context_atoms_before": 0,
                "context_atoms_after": 0,
                "target_mode": "GENERATABLE_SHOT",
            },
            {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0008", "last_atom_id": "SRC0009"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "GENERATABLE_SHOT"},
            {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0011", "last_atom_id": "SRC0012"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "GENERATABLE_SHOT"},
        ],
    }
    dense = prepare_authoring(dense_source, dense_plan, "RUN2")
    dense_request = dense["immutable_contract"]["selection_request"]
    first_id = dense_request["sample_unit_ids"][0]
    if dense_request["target_modes"][first_id] != "EDITED_SEQUENCE":
        raise AssertionError("dense multi-speaker dialogue was not rerouted to EDITED_SEQUENCE")
    if dense_request["route_findings"][first_id] != [
        "SPLIT_REQUIRED:MULTI_TURN_DIALOGUE_SPLIT_REQUIRED",
        "SPLIT_REQUIRED:SINGLE_SHOT_INELIGIBLE",
    ]:
        raise AssertionError("dense route did not record the exact risk + single-shot findings")

    overlap_rejected = False
    try:
        prepare_authoring(
            source,
            {
                "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
                "targets": [
                    {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0003"}, "target_mode": "EDITED_SEQUENCE"},
                    {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0003", "last_atom_id": "SRC0005"}, "target_mode": "EDITED_SEQUENCE"},
                    {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0007", "last_atom_id": "SRC0009"}, "target_mode": "EDITED_SEQUENCE"},
                ],
            },
            "RUN3",
        )
    except ValueError:
        overlap_rejected = True
    if not overlap_rejected:
        raise AssertionError("explicit overlapping target ranges were accepted")

    wide_rejected = False
    wide_source = "".join(f"连续事件{i:02d}完成。\n" for i in range(1, 26))
    try:
        prepare_authoring(
            wide_source,
            {
                "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
                "targets": [
                    {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0015"}, "target_mode": "EDITED_SEQUENCE"},
                    {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0016", "last_atom_id": "SRC0018"}, "target_mode": "EDITED_SEQUENCE"},
                    {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0021", "last_atom_id": "SRC0023"}, "target_mode": "EDITED_SEQUENCE"},
                ],
            },
            "RUN4",
        )
    except ValueError as exc:
        wide_rejected = "E_USER_TARGET_WINDOW_WIDE" in str(exc)
    if not wide_rejected:
        raise AssertionError("unreviewed 15-atom USER target escaped the bounded-window gate")

    incomplete_rejected = False
    incomplete_source = "未完分句，\n下一句补完。\n中段一。\n中段二。\n尾段一。\n尾段二。\n"
    try:
        prepare_authoring(
            incomplete_source,
            {
                "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
                "targets": [
                    {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0001"}, "target_mode": "GENERATABLE_SHOT"},
                    {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0003", "last_atom_id": "SRC0004"}, "target_mode": "GENERATABLE_SHOT"},
                    {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0005", "last_atom_id": "SRC0006"}, "target_mode": "GENERATABLE_SHOT"},
                ],
            },
            "RUN5",
        )
    except ValueError as exc:
        incomplete_rejected = "E_USER_TARGET_BOUNDARY_INCOMPLETE" in str(exc)
    if not incomplete_rejected:
        raise AssertionError("USER target ending inside a clause escaped the boundary gate")

    thin_sequence_rejected = False
    thin_sequence_source = (
        "甲抬手，乙停步，丙转身。\n"
        "中段甲。\n中段乙。\n"
        "尾段甲。\n尾段乙。\n"
    )
    try:
        prepare_authoring(
            thin_sequence_source,
            {
                "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
                "targets": [
                    {
                        "target_id": "T001",
                        "atom_range": {
                            "first_atom_id": "SRC0001",
                            "last_atom_id": "SRC0001",
                        },
                        "target_mode": "EDITED_SEQUENCE",
                    },
                    {
                        "target_id": "T002",
                        "atom_range": {
                            "first_atom_id": "SRC0002",
                            "last_atom_id": "SRC0003",
                        },
                        "target_mode": "GENERATABLE_SHOT",
                    },
                    {
                        "target_id": "T003",
                        "atom_range": {
                            "first_atom_id": "SRC0004",
                            "last_atom_id": "SRC0005",
                        },
                        "target_mode": "GENERATABLE_SHOT",
                    },
                ],
            },
            "RUN10",
        )
    except ValueError as exc:
        thin_sequence_rejected = "E_SEQUENCE_SOURCE_WINDOW_THIN" in str(exc)
    if not thin_sequence_rejected:
        raise AssertionError("single-anchor Sequence was padded instead of failing closed")

    vocal_source = "前景建立。\n只听“啊”的一声，是唐僧的痛叫。\n嗖-\n中段推进。\n尾段建立。\n尾段结束。\n"
    vocal = prepare_authoring(
        vocal_source,
        {
            "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
            "targets": [
                {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0002"}, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0003", "last_atom_id": "SRC0004"}, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0005", "last_atom_id": "SRC0006"}, "target_mode": "EDITED_SEQUENCE"},
            ],
        },
        "RUN6",
    )
    vocal_quote = next(
        item for item in vocal["immutable_contract"]["source_dialogue_inventory"] if item["text"] == "啊"
    )
    if "LIKELY_NON_LEXICAL_VOCALIZATION" not in vocal_quote["classification_hints"]:
        raise AssertionError("character pain vocalization was not distinguished from SFX")

    time_jump_source = "".join(
        [
            "开场建立。\n", "人物进入。\n", "间隔事件一。\n", "间隔事件二。\n",
            "中段建立。\n", "人物停下。\n", "夜里灯光熄灭。\n", "三年后大门重开。\n",
            "旧物被发现。\n", "人物离开。\n", "尾声之前。\n", "尾声结束。\n",
        ]
    )
    time_jump = prepare_authoring(
        time_jump_source,
        {
            "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
            "targets": [
                {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0002"}, "target_mode": "GENERATABLE_SHOT"},
                {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0005", "last_atom_id": "SRC0006"}, "target_mode": "GENERATABLE_SHOT"},
                {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0007", "last_atom_id": "SRC0010"}, "target_mode": "GENERATABLE_SHOT"},
            ],
        },
        "RUN10",
    )
    time_jump_window = next(window for window in time_jump["target_windows"] if window["unit_id"] == "U004")
    if (
        time_jump_window["target_mode"] != "EDITED_SEQUENCE"
        or time_jump_window["single_shot_eligibility"]["eligible"]
        or "ATOM_COUNT_GT_3" not in time_jump_window["single_shot_eligibility"]["reasons"]
        or "TIME_TRANSITION_PRESENT" not in time_jump_window["single_shot_eligibility"]["reasons"]
        or time_jump["immutable_contract"]["selection_request"]["route_findings"].get("U004")
        != ["SPLIT_REQUIRED:SINGLE_SHOT_INELIGIBLE"]
    ):
        raise AssertionError(
            "LOW-risk U004 with a time jump did not retain the exact single-shot finding"
        )

    anomaly_plan = copy_json(plan)
    anomaly_plan["source_anomalies"] = [
        {"anomaly_id": "ANOM-TEXT", "kind": "SOURCE_TYPO", "text": "动作继续。"},
        {"anomaly_id": "ANOM-VARIANT", "kind": "KNOWN_VARIANT", "variant": "人名异写，原样保留"},
        {"anomaly_id": "ANOM-SPAN", "kind": "PUNCTUATION_REVIEW", "span": {"start_cp": 0, "end_cp": 3}},
    ]
    anomaly_envelope = prepare_authoring(source, anomaly_plan, "RUN8")
    user_anomalies = [
        item
        for item in anomaly_envelope["immutable_contract"]["source_anomalies"]
        if item["anomaly_id"].startswith("ANOM-")
    ]
    if len(user_anomalies) != 3:
        raise AssertionError("structured source anomaly evidence was not preserved")
    invalid_anomaly_rejected = False
    try:
        invalid_plan = copy_json(plan)
        invalid_plan["source_anomalies"] = ["这里有异写"]
        prepare_authoring(source, invalid_plan, "RUN7")
    except ValueError:
        invalid_anomaly_rejected = True
    if not invalid_anomaly_rejected:
        raise AssertionError("string source anomaly was silently ignored")
    return {
        "self_test": "PASS",
        "authoring_version": AUTHORING_VERSION,
        "contract_version": CONTRACT_VERSION,
        "target_count": 3,
        "machine_multi_atom_selection": True,
        "blank_separator_preservation": True,
        "dense_route_rewrite": True,
        "time_jump_u004_sequence": True,
        "punctuated_complete_sentence_anchors": True,
        "overlap_attack_rejected": True,
        "structured_source_anomalies": True,
        "invalid_anomaly_rejected": True,
        "self_contained_authoring_guide": True,
        "user_window_bounds": True,
        "thin_sequence_window_rejected": True,
        "non_lexical_vocalization_hint": True,
        "source_atoms_immutable": True,
        "production_validation": "NOT_TESTED",
    }


def _authoring_guide(envelope: dict[str, Any]) -> dict[str, Any]:
    contract = envelope["immutable_contract"]
    atom_map = {atom["atom_id"]: atom for atom in contract["source_atoms"]}
    unit_map = {unit["unit_id"]: unit for unit in contract["units"]}
    overlay_map = {
        overlay["unit_id"]: overlay
        for overlay in envelope["compiled_unit_overlays"]
    }
    quote_map = {
        item["dialogue_id"]: item
        for item in contract["source_dialogue_inventory"]
        if isinstance(item, dict) and isinstance(item.get("dialogue_id"), str)
    }
    requirements: dict[str, Any] = {}
    for window in envelope["target_windows"]:
        unit = unit_map[window["unit_id"]]
        source_locked_nonlexical_speakers = (
            source_locked_nonlexical_speakers_from_window(window)
        )
        requirements[unit["unit_id"]] = {
            "target_mode": window["target_mode"],
            "single_shot_eligibility": copy_json(window["single_shot_eligibility"]),
            "locked_director_scaffold": copy_json(window["locked_director_scaffold"]),
            "locked_scaffold_sha256": window["locked_scaffold_sha256"],
            "fixed_transform_roles": copy_json(window["fixed_transform_roles"]),
            "semantic_gate": copy_json(window["semantic_gate"]),
            "minimum_shots": window["locked_director_scaffold"]["minimum_shots"],
            "action_addition_capacity_by_shot": {
                shot["shot_id"]: _action_addition_capacity(shot)
                for shot in (
                    window["locked_director_scaffold"]["shots"]
                    if window["target_mode"] == "EDITED_SEQUENCE"
                    else []
                )
            },
            "ordered_source_refs": list(unit["source_refs"]),
            "source_segments": [
                {
                    "source_ref": ref,
                    "start_cp": atom_map[ref]["start_cp"],
                    "end_cp": atom_map[ref]["end_cp"],
                    "text": atom_map[ref]["text"],
                    "text_sha256": sha256_text(atom_map[ref]["text"]),
                }
                for ref in unit["source_refs"]
            ],
            "quote_catalog": [
                {
                    "dialogue_id": dialogue_id,
                    "text": quote_map[dialogue_id]["text"],
                    "source_refs": copy_json(quote_map[dialogue_id]["source_refs"]),
                    "speaker_hint": quote_map[dialogue_id].get("speaker_hint", "SOURCE_UNSPECIFIED"),
                    "speaker_policy": (
                        "SOURCE_LOCKED_NONLEXICAL"
                        if dialogue_id in source_locked_nonlexical_speakers
                        else "AUTHOR_SET_ONLY_IF_SPOKEN_DIALOGUE"
                    ),
                    "source_locked_speaker": source_locked_nonlexical_speakers.get(
                        dialogue_id
                    ),
                    "classification_hints": copy_json(
                        window["quote_classification_hints"][dialogue_id]["classification_hints"]
                    ),
                    "context_evidence": copy_json(
                        window["quote_classification_hints"][dialogue_id]["context_evidence"]
                    ),
                    "required_template_slot": f"{{{{VERBATIM_DIALOGUE_SLOT:{dialogue_id}}}}}",
                }
                for dialogue_id in window["dialogue_slot_ids"]
            ],
            "editable_paths": copy_json(overlay_map[unit["unit_id"]]["editable_paths"]),
            "editable_overlay_template": copy_json(overlay_map[unit["unit_id"]]),
        }
    return {
        "guide_version": AUTHORING_GUIDE_VERSION,
        "compatibility": {
            "write_version": AUTHORING_VERSION,
            "read_only_authoring_versions": list(READ_ONLY_AUTHORING_VERSIONS),
            "read_only_guide_versions": list(READ_ONLY_GUIDE_VERSIONS),
        },
        "purpose": (
            "只填写 compiled_unit_overlays 中 editable_paths 精确列出的创作叶；"
            "锁定来源结构、镜头编号、角色与转换角色均不可编辑。"
        ),
        "context_rule": (
            "本指南含完整来源段、确定性语义锚、锁定导演骨架与创作面；"
            "禁止读取 scripts、tests、schema、fixtures 或版本历史。"
        ),
        "source_read_scope_attestation": source_read_scope_attestation(),
        "workflow": {
            "steps": [
                "按 unit_requirements 的锁定语义锚与镜头骨架完成每个 Unit。",
                "只修改 editable_paths 精确列出的叶；不得增删键、改 ID、改锁或改固定角色。",
                "先逐字执行 check_argv；失败时保留 temp_root，只修改可编辑创作叶后逐字执行 retry_argv。",
                "只有 check 返回 overlays_valid=true，才逐字执行 commit_argv。",
            ],
            **copy_json(contract["authoring_workflow"]),
        },
        "editable_path_rule": {
            "path_format": "RFC6901_ABSOLUTE_POINTER",
            "policy": "ONLY_LISTED_LEAVES_EDITABLE",
            "forbidden": [
                "unit_id",
                "shot_id",
                "source_ref",
                "source_anchor_id",
                "locked_director_scaffold",
                "locked_scaffold_sha256",
                "fixed_transform_roles",
                "quote_assignments",
                "execution_beats",
                "status",
                "checks",
                "provenance",
                "claim relation/source_refs/slot structure",
            ],
        },
        "overlay_object_schema": {
            "root_exact_keys": [
                "authoring_version",
                "helper_lock_sha256",
                "authoring_guide_sha256",
                "authoring_guide",
                "source_read_scope_attestation",
                "target_windows",
                "compiled_unit_overlays",
            ],
            "unit_overlay_exact_keys": [
                "unit_id",
                "editable_paths",
                "director_overlay",
                "prompt_overlay",
                "quality_overlay",
            ],
            "director_overlay_exact_shape": {
                "performance": "非空创作字符串；finalizer 自动派生提案证明",
                "camera": "非空创作字符串；不得与逐镜 camera 冲突",
                "sound": "非空创作字符串；主体与顺序明确",
                "dialogue_speakers": (
                    "只包含仍允许创作者填写人物的口播候选 quote ID，且每个键都必须在 editable_paths 中。"
                    "SOURCE_LOCKED_NONLEXICAL 项不会出现在这个映射中；其只读来源主体只在 quote_catalog 显示"
                ),
                "quote_classifications": "精确包含 quote_catalog 全部 quote ID",
                "shot_creative": (
                    "EDITED_SEQUENCE 与 locked shots 一一对应且同序；"
                    "每项仅 shot_id/purpose/action_additions/camera。GENERATABLE_SHOT 必须为空数组"
                ),
            },
            "shot_creative_exact_shape": {
                "shot_id": "helper 预填且不可编辑",
                "purpose": "非空、场景特异的戏剧任务；不得使用泛化模板",
                "action_additions": [
                    "默认保持空数组；它是可选补充，不是必须完成项。每镜最多填写 "
                    "action_addition_capacity_by_shot 标明的条数；容量为 0 时不可编辑。"
                    "只写来源没有给出的非剧情导演调度，不得复述、缩写或改写锁定来源动作"
                ],
                "camera": "非空、可执行且服务本镜任务；不得使用泛化模板",
            },
            "prompt_overlay_exact_shape": {
                "master_prompt_template": "导演设计层；每个最终 SPOKEN_DIALOGUE slot 恰出现一次",
                "transform_plan": {
                    "preserve": "可编辑数组",
                    "operations": "可编辑数组",
                    "deferred_provider_decisions": "可编辑数组",
                },
                "neutral_execution_prompt_template": (
                    "可复制执行层；不得复制 MASTER 正文；每个最终 SPOKEN_DIALOGUE slot 恰出现一次"
                ),
                "claims": (
                    "helper 已预填来源逐字槽与一个 DIRECTORIAL_CONTROL 空槽；"
                    "来源槽全文、relation、source_refs、数量和顺序均不可编辑。"
                    "只可填写 editable_paths 指向的导演控制 text，留空表示不用该槽"
                ),
                "negative_clauses": "完整负向句数组",
            },
            "quality_overlay_exact_shape": {
                "scene_title": "作者填写具体场景名，不得使用 Unit ID 或样片N",
                "findings": "作者发现的未解决问题；空数组不等于独立编辑审阅通过",
            },
        },
        "record_shapes": {
            "semantic_anchor": {
                "anchor_id": "helper 派生且不可编辑",
                "source_ref": "唯一来源 atom",
                "start_cp": "冻结来源字符起点",
                "end_cp": "冻结来源字符终点",
                "exact_text": "冻结来源逐字语义片段",
                "text_sha256": "exact_text 的 SHA-256",
                "anchor_role": "ACTION_BEAT/REACTION_BEAT/DIALOGUE_BEAT/TIME_TRANSITION",
                "quote_ids": ["与该片段相交的来源引号 ID；尚未等同 SPOKEN_DIALOGUE"],
            },
            "single_shot_eligibility": {
                "decision": "ELIGIBLE/INELIGIBLE",
                "eligible": "与 decision 及 reasons 严格一致",
                "reasons": [
                    "ATOM_COUNT_GT_3/SEMANTIC_ANCHORS_GT_4/TIME_TRANSITION_PRESENT/"
                    "DIALOGUE_TURNS_GE_4/SPEAKER_COUNT_GE_3/DURATION_FLOOR_GT_12/ROUTE_RISK_*"
                ],
                "atom_count": "当前窗口来源 atom 数",
                "semantic_anchor_count": "当前窗口语义锚数",
                "dialogue_turn_count": "来源引号轮次",
                "speaker_count": "可复算说话者数",
                "time_jump_anchor_ids": ["TIME_TRANSITION 锚 ID"],
            },
            "locked_director_scaffold": {
                "scaffold_version": DIRECTOR_SCAFFOLD_VERSION,
                "derivation": "HELPER_DERIVED",
                "target_mode": "EDITED_SEQUENCE/GENERATABLE_SHOT",
                "minimum_shots": "Sequence 锁定镜头数；Shot 为 0",
                "semantic_anchors": ["semantic_anchor"],
                "entry_anchor_ids": ["锁定入口锚"],
                "action_anchor_ids": ["按来源顺序覆盖全部语义锚"],
                "exit_anchor_ids": ["锁定出口锚"],
                "continuity_anchor_ids": ["锁定边界连续性锚"],
                "shots": [
                    {
                        "shot_id": "SH001 起连续递增",
                        "source_refs": ["本镜冻结来源 refs"],
                        "source_anchor_ids": ["本镜冻结语义锚"],
                        "quote_ids": ["本镜候选来源引号；由最终分类过滤为 dialogue_slot_ids"],
                    }
                ],
                "field_provenance": {
                    "entry": "HELPER_DERIVED + source_anchor_ids",
                    "action_state_chain": "HELPER_DERIVED + source_anchor_ids",
                    "exit": "HELPER_DERIVED + source_anchor_ids",
                    "continuity": "HELPER_DERIVED + source_anchor_ids",
                    "shots": "HELPER_DERIVED + source_anchor_ids",
                },
            },
            "fixed_transform_roles": {
                "source_role": "PROVIDER_NEUTRAL_MASTER",
                "target_role": "NEUTRAL_EXECUTION_PROMPT",
                "derivation": "HELPER_DERIVED",
            },
            "quote_assignment": {
                "dialogue_id": "来源引号 ID，由 helper 派生",
                "shot_id": "唯一锁定镜头，由 locked shots.quote_ids 派生",
                "kind": "最终引号分类",
                "speaker": "口播或非词汇人声主体；无法从来源确定时退回",
                "text": "冻结来源逐字引号内容",
                "source_refs": ["冻结来源 refs"],
            },
            "claim_record": {
                "text": "来源槽由 helper 逐字派生；只有预分配导演控制槽正文可编辑",
                "relation": (
                    "VERBATIM/FAITHFUL_PARAPHRASE/VISUALIZATION/"
                    "CONTINUITY_CARRY/PROJECT_CONTROL/DIRECTORIAL_CONTROL"
                ),
                "source_refs": ["支撑该主张的当前 Unit source_ref"],
            },
        },
        "director_rules": {
            "locked_source_rule": (
                "entry/action_state_chain/exit/continuity/shots 只由 locked_director_scaffold 派生；"
                "模型不得手填来源锚、shot_plan 或 provenance。"
            ),
            "single_shot_rule": (
                "INELIGIBLE 必须路由 EDITED_SEQUENCE；ELIGIBLE 仍尊重用户显式 Sequence。"
            ),
            "shot_creative_rule": (
                "Sequence 的 shot_creative 与 locked shots 同序同 ID；"
                "purpose 和 camera 必须真实、场景特异、非泛化；"
                "action_additions 默认保持 []，仅在逐镜剩余容量大于 0 且确有非剧情导演调度时填写，"
                "不得把锁定来源动作换句话再写一次。"
            ),
            "proposal_rule": (
                "finalizer 从 performance/camera/sound 与 shot_creative 自动派生创作提案证明；"
                "模型不得手填 inference。"
            ),
            "execution_compile_rule": (
                "finalizer 从锁定镜头确定性派生 quote_assignments 与 execution_beats；"
                "模型不得手填。逐镜 audio_order 只含本镜口播、本镜非词汇人声和本镜明确来源声响；"
                "顶层 sound 只表达整体声音原则，不复制到每一镜。"
            ),
            "duration_rule": (
                "时长下限由口播、非词汇停顿、画面文字阅读、动作分句、相机运动和明确连续秒数共同计算；"
                "超过 12 秒必须在锁定分组阶段继续拆镜，单个完整语义锚仍超过 12 秒则退回，禁止硬截。"
            ),
        },
        "quote_classification_enum": [
            "SPOKEN_DIALOGUE",
            "INTERNAL_THOUGHT",
            "NON_LEXICAL_VOCALIZATION",
            "SFX",
            "QUOTED_TEXT",
        ],
        "quote_rules": {
            "SPOKEN_DIALOGUE": "两层模板各保留一次 slot，并标说话者；禁止重打或给 slot 补标点。",
            "INTERNAL_THOUGHT": "逐字放入 performance，不作 spoken slot。",
            "NON_LEXICAL_VOCALIZATION": (
                "人物或动物的痛叫、喘息等不归 SFX；主体由 helper 从同一来源边界确定并在 "
                "quote_catalog 标为 SOURCE_LOCKED_NONLEXICAL，创作者不得改名。仍无法确定时在准备阶段退回，"
                "不得靠填写区猜测或改成环境声。finalizer 在 MP 与中性执行工作稿的正确镜头位置各写一次"
                "‘镜头 N：主体发出“原文”’，并只进入本镜 audio_order。"
            ),
            "SFX": "只用于无发声主体的效果声；只进入来源所在镜头的 audio_order。",
            "QUOTED_TEXT": (
                "按世界内标签或引文处理；MP 与中性执行工作稿均在正确镜头写"
                "‘镜头 N：画面文字（不朗读）：“原文”’，绝不进入 audio_order。"
            ),
        },
        "prompt_rules": {
            "master_prompt_template": (
                "写导演设计：戏剧意图、空间策略、表演与连续性；"
                "每个 SPOKEN_DIALOGUE slot 恰出现一次。"
            ),
            "transform_plan": (
                "只填写 preserve/operations/deferred_provider_decisions 三数组；"
                "source_role/target_role 由 fixed_transform_roles 锁定。"
            ),
            "neutral_execution_prompt_template": (
                "写可直接复制的逐镜或动作顺序；必须与 MASTER 有实质差异；"
                "每个 spoken slot 恰出现一次，并保留 helper 要求的逐镜非词汇人声与画面文字 cue。"
            ),
            "internal_id_rule": "工程 ID 只能出现在 slot/JSON 固定字段，禁止进入自然语言正文。",
            "claim_rule": (
                "禁止手写、增删或换标 SOURCE/FAITHFUL 主张；来源主张由锁定语义锚确定性生成。"
                "只能选择填写预分配 DIRECTORIAL_CONTROL 正文，并接受首次揭示与动作关系 Gate。"
            ),
        },
        "repair_playbook": {
            "E_EDITABLE_PATH": "只恢复 editable_paths 列出的创作叶，不改 ID、锁、固定角色或键集合。",
            "E_LOCKED_SCAFFOLD": "重新 prepare；不得在 overlay 内修补语义锚、锁定镜头或 hash。",
            "E_NON_LEXICAL_VOCALIZATION_SPEAKER": (
                "人物发声的来源主体无法唯一确定；不要循环修改 dialogue_speakers，也不能改成 SFX。"
                "应补充来源中的明确人物归属后重新准备，或退回该来源片段。"
            ),
            "E_SINGLE_SHOT_ROUTE": "按 single_shot_eligibility 路由；INELIGIBLE 必须拆为 Sequence。",
            "E_SHOT_CREATIVE": (
                "逐镜补足场景特异 purpose 和 camera；action_additions 默认保持 []，"
                "不能把可选项当成必填项。"
            ),
            "E_SHOT_ACTION_ADDITION_CAPACITY": (
                "按 unit_requirements.action_addition_capacity_by_shot 修正："
                "容量为 0 时保持 []；容量大于 0 时不得超量，也不得复述锁定来源动作。"
            ),
            "E_OUT_OF_WINDOW_PLOT_ACTION": "删除当前窗口未发生的剧情推进，不得降格成导演提案。",
            "E_SEMANTIC_CLAIM_LOCK": "恢复 prepare 生成的来源主张槽，只填写导演控制槽正文。",
            "E_SEMANTIC_FUTURE_REVELATION": "按错误路径删除尚未在当前来源窗口首次出现的专名、引文或状态词。",
            "E_SEMANTIC_ACTION_SUBJECT": "按错误路径把动作执行主体改回当前来源明确锁定的人物。",
            "E_SEMANTIC_ACTION_REVIEW_REQUIRED": "该中文动作关系无法机械唯一确认；不要自报通过，交给内容复核。",
            "E_CONTENT_SELF_REVIEW_COMPUTED": "修正文稿本身；status/checks 由 helper 复算。",
        },
        "quality_rule": (
            "作者只填写 scene_title/findings；结构状态、内容检查与独立编辑审阅由后续层分别派生。"
        ),
        "unit_requirements": requirements,
    }

def compact_overlay_work_surface(envelope: dict[str, Any]) -> dict[str, Any]:
    contract = envelope["immutable_contract"]
    guide = _authoring_guide(envelope)
    guide_sha256 = sha256_value(guide)
    if guide_sha256 != contract.get("authoring_guide_sha256"):
        raise ValueError("immutable authoring guide hash mismatch")
    return {
        "authoring_version": contract["authoring_version"],
        "helper_lock_sha256": contract["helper_lock_sha256"],
        "authoring_guide_sha256": guide_sha256,
        "authoring_guide": guide,
        "source_read_scope_attestation": source_read_scope_attestation(),
        "target_windows": copy_json(envelope["target_windows"]),
        "compiled_unit_overlays": copy_json(envelope["compiled_unit_overlays"]),
    }


def copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _write_json_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_json_replace(path: Path, value: Any) -> None:
    """Rewrite one registered carrier without deleting or creating side files."""

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare an immutable Alpha.7 longform authoring envelope")
    parser.add_argument("source", nargs="?", type=Path, help="UTF-8 source TXT")
    parser.add_argument("target_plan", nargs="?", type=Path, help="small target-plan JSON")
    parser.add_argument("output", nargs="?", type=Path, help="authoring-envelope JSON")
    parser.add_argument("--run-id", default="RUN0", help="RUN followed by digits")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="high-level mode: final strict output directory; an existing empty directory uses in-place carriers",
    )
    parser.add_argument(
        "--selection-mode",
        default="MACHINE_REPRESENTATIVE_V1",
        choices=sorted(SELECTION_MODES),
        help="high-level selection mode; explicit ranges still require the legacy target-plan form",
    )
    parser.add_argument("--sample-count", type=int, default=3, help="high-level representative Pilot size, 3-5")
    parser.add_argument("--package-name", help="exact final package basename")
    parser.add_argument("--machine-state-name", help="exact final machine-state basename")
    parser.add_argument("--run-summary-name", help="exact final run-summary basename")
    parser.add_argument(
        "--reprepare",
        action="store_true",
        help="rewrite only an exact registered three-carrier preparation; never touches final outputs",
    )
    parser.add_argument(
        "--overlays-output",
        type=Path,
        help="optional compact three-overlay work surface for the model/creator",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        try:
            result = run_self_test()
        except Exception as exc:
            print(json.dumps({"self_test": "FAIL", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
            return 1
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    high_level = args.output_dir is not None
    if args.source is None:
        parser.error("source is required unless --self-test is used")
    if high_level and any(value is not None for value in (args.target_plan, args.output, args.overlays_output)):
        parser.error("--output-dir high-level mode owns TARGET_PLAN/AUTHORING/OVERLAYS paths; omit legacy path arguments")
    if not high_level and (args.target_plan is None or args.output is None):
        parser.error("legacy mode requires source, target_plan, and output")
    if not high_level and args.overlays_output is None:
        parser.error("--overlays-output is required for the self-contained authoring workflow")
    try:
        if high_level:
            output_dir = args.output_dir.resolve()
            if output_dir.exists() and (not output_dir.is_dir() or output_dir.is_symlink()):
                raise ValueError("E_OUTPUT_TARGET_UNSAFE: output directory must be a normal directory")
            output_entries = list(output_dir.iterdir()) if output_dir.exists() else []
            if output_dir.exists():
                commit_mode = IN_PLACE_COMMIT_MODE
                temp_parent = output_dir
            else:
                commit_mode = SIBLING_COMMIT_MODE
                temp_parent = output_dir.parent / f".alpha7-tmp-{args.run_id}"
            if args.reprepare:
                if not temp_parent.is_dir() or temp_parent.is_symlink():
                    raise ValueError("E_REPREPARE_SCOPE: registered carrier directory is missing or unsafe")
                if {item.name for item in temp_parent.iterdir()} != set(TEMP_INPUT_NAMES):
                    raise ValueError("E_REPREPARE_SCOPE: reprepare accepts only the exact three registered carriers")
            else:
                if output_entries:
                    raise ValueError(
                        "E_OUTPUT_TARGET_NOT_EMPTY: existing WorkBuddy task directory must be empty before prepare"
                    )
                if commit_mode == SIBLING_COMMIT_MODE and temp_parent.exists():
                    raise ValueError(
                        "E_TEMP_ROOT_CONTRACT: canonical temp root already exists; use persisted reprepare_argv or a new run-id"
                    )
            source_text = read_source_text(args.source)
            plan = build_target_plan(args.selection_mode, args.sample_count)
            requested_names = None
            if any((args.package_name, args.machine_state_name, args.run_summary_name)):
                if not all((args.package_name, args.machine_state_name, args.run_summary_name)):
                    raise ValueError("all three exact output-name options must be supplied together")
                requested_names = [args.package_name, args.machine_state_name, args.run_summary_name]
            envelope = prepare_authoring(
                source_text,
                plan,
                args.run_id,
                output_dir=output_dir,
                output_names=requested_names,
                commit_mode=commit_mode,
                source_path=args.source,
                sample_count=args.sample_count,
            )
            if not temp_parent.exists():
                temp_parent.mkdir(parents=True, exist_ok=False)
            target_plan_path = temp_parent / "TARGET_PLAN.json"
            authoring_path = temp_parent / "AUTHORING.json"
            overlays_path = temp_parent / "OVERLAYS.json"
            writer = _write_json_replace if args.reprepare else _write_json_new
            writer(target_plan_path, plan)
            writer(authoring_path, envelope)
            writer(overlays_path, compact_overlay_work_surface(envelope))
            print(
                json.dumps(
                    {
                        "prepared": True,
                        "authoring_version": AUTHORING_VERSION,
                        "guide_version": AUTHORING_GUIDE_VERSION,
                        "target_plan_generated": True,
                        "selection_mode": args.selection_mode,
                        "sample_count": args.sample_count,
                        "temp_root": str(temp_parent),
                        "commit_mode": commit_mode,
                        "authoring": str(authoring_path),
                        "compact_overlays": str(overlays_path),
                        "final_output_directory": str(output_dir),
                        "exact_output_names": envelope["immutable_contract"]["output_contract"]["exact_relative_output_names"],
                        "check_argv": envelope["immutable_contract"]["authoring_workflow"]["check_argv"],
                        "commit_argv": envelope["immutable_contract"]["authoring_workflow"]["commit_argv"],
                        "reprepare_argv": envelope["immutable_contract"]["authoring_workflow"]["reprepare_argv"],
                        "editable_overlay_count": len(envelope["compiled_unit_overlays"]),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        input_paths = {args.source.resolve(), args.target_plan.resolve()}
        output_paths = {args.output.resolve()}
        if args.overlays_output is not None:
            output_paths.add(args.overlays_output.resolve())
        if len(output_paths) != (2 if args.overlays_output is not None else 1):
            raise ValueError("authoring and compact overlay outputs must be different files")
        if input_paths.intersection(output_paths):
            raise ValueError("output must not overwrite source or target plan")
        if any(path.exists() for path in output_paths):
            raise ValueError("prepare uses new-file semantics; output already exists")
        expected_temp_root = f".alpha7-tmp-{args.run_id}"
        temp_parent = args.output.resolve().parent
        if (
            temp_parent.name != expected_temp_root
            or args.target_plan.resolve().parent != temp_parent
            or args.overlays_output.resolve().parent != temp_parent
            or args.target_plan.name != "TARGET_PLAN.json"
            or args.output.name != "AUTHORING.json"
            or args.overlays_output.name != "OVERLAYS.json"
        ):
            raise ValueError(
                "E_TEMP_ROOT_CONTRACT: TARGET_PLAN.json/AUTHORING.json/OVERLAYS.json must be the only "
                f"authoring files inside the declared sibling temp root {expected_temp_root}"
            )
        existing_temp_entries = [item.name for item in temp_parent.iterdir()] if temp_parent.exists() else []
        if set(existing_temp_entries) - {"TARGET_PLAN.json"}:
            raise ValueError(
                "E_TEMP_ROOT_CONTRACT: authoring temp_root contains an undeclared file; "
                "do not create fill_overlays.py or other helper artifacts"
            )
        source_text = read_source_text(args.source)
        plan = json.loads(args.target_plan.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise ValueError("target plan root must be an object")
        inferred_output_dir = args.output.resolve().parent.parent / f"{args.run_id.lower()}-longform-output"
        envelope = prepare_authoring(source_text, plan, args.run_id, output_dir=inferred_output_dir)
        _write_json_new(args.output, envelope)
        if args.overlays_output is not None:
            _write_json_new(args.overlays_output, compact_overlay_work_surface(envelope))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"prepared": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "prepared": True,
                "authoring_version": AUTHORING_VERSION,
                "output": str(args.output.resolve()),
                "compact_overlays": str(args.overlays_output.resolve()) if args.overlays_output else None,
                "editable_overlay_count": len(envelope["compiled_unit_overlays"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
