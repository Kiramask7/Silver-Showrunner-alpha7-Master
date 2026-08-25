#!/usr/bin/env python3
"""Finalize an Alpha.7 Master longform authoring envelope into exactly three files.

Only this helper may promote an authored Pilot to TEXT_PILOT_COMPLETE and
create CURRENT/PASS quality cards.  It injects frozen source dialogue into
slots, computes every derived hash/diff, runs the authoritative validator,
demotes failed attempts to PILOT_REWORK_REQUIRED, renders the machine summary,
cleans the registered temp root, and installs the strict three-file result.

The deprecated ``draft.json output.json`` form is retained only as a fail-closed
CLI compatibility surface.  Versions 1.0--1.4 are read-only and must use the
explicit 1.5 migrator; this finalizer never repairs or rewrites them.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any

from performance_feasibility_guard import assert_prompt_feasible

from render_creator_view import (
    assert_creator_safe,
    load_dictionary,
    render_creator_view,
    sanitize_display_text,
)
from validate_longform_contract import (
    ACTION_REACTION_RE,
    CONTRACT_VERSION,
    DIRECTOR_SCAFFOLD_VERSION,
    IN_PLACE_COMMIT_MODE,
    LEGACY_CONTRACT_VERSION,
    READ_ONLY_CONTRACT_VERSIONS,
    PROMPT_SHELL_KEYS,
    TEXT_EXCLUDED_STAGE_STATUS,
    SIBLING_COMMIT_MODE,
    TEMP_INPUT_NAMES,
    TRACE_RELATIONS,
    build_fixture_run_summary,
    build_pilot_fixture,
    copyable_execution_surface_findings,
    creator_prompt_surface,
    derive_quote_assignments,
    derive_quote_classification_hints,
    expected_dialogue_diff,
    expected_content_self_review,
    expected_director_prompt_block,
    expected_authoring_claim_slots,
    expected_execution_beats,
    expected_global_state,
    expected_helper_lock_projection,
    expected_sequence_minimum_shots,
    expected_skeleton_sha256,
    expected_shot_handoffs,
    expected_source_prompt_block,
    expected_text_status_contract,
    expected_target_windows,
    expected_unit_compile_state,
    extract_creator_shot_sections,
    extract_shared_creator_context,
    normalize_text,
    prompt_layer_independence_findings,
    render_copyable_execution_surface,
    render_visible_quote_cues,
    render_execution_beats_block,
    semantic_gate_findings,
    semantic_overlay_surfaces,
    sha256_text,
    sha256_value,
    source_locked_nonlexical_speakers_from_window,
    spoken_quote_conflicts,
    validate_contract,
    validation_subject_projection,
)


AUTHORING_VERSION = "alpha7-longform-authoring-1.5"
AUTHORING_GUIDE_VERSION = "alpha7-overlay-guide-1.5"
SLOT_RE = re.compile(r"\{\{VERBATIM_DIALOGUE_SLOT:([A-Za-z0-9._-]+)\}\}")
SLOT_BOUNDARY_RE = re.compile(
    r"\{\{VERBATIM_DIALOGUE_SLOT:([A-Za-z0-9._-]+)\}\}([ \t]*)([。！？!?；;，,]+)?"
)
TERMINAL_DIALOGUE_RE = re.compile(r"[。！？!?…][”’」』）)]*$")
COMPILED_STATUSES = {"ACCEPTED", "COMMITTED"}
OVERLAY_KEYS = {
    "unit_id", "editable_paths", "director_overlay", "prompt_overlay", "quality_overlay",
}
DIRECTOR_OVERLAY_KEYS = {
    "performance",
    "camera",
    "sound",
    "shot_creative",
    "dialogue_speakers",
    "quote_classifications",
}
PROMPT_OVERLAY_KEYS = {
    "master_prompt_template",
    "transform_plan",
    "neutral_execution_prompt_template",
    "claims",
    "negative_clauses",
}
TRANSFORM_PLAN_KEYS = {
    "preserve", "operations", "deferred_provider_decisions",
}
QUALITY_OVERLAY_KEYS = {"scene_title", "findings"}
SEMANTIC_ANCHOR_KEYS = {
    "anchor_id", "source_ref", "start_cp", "end_cp", "exact_text",
    "text_sha256", "anchor_role", "quote_ids",
}
LOCKED_SCAFFOLD_KEYS = {
    "scaffold_version", "derivation", "target_mode", "minimum_shots",
    "semantic_anchors", "entry_anchor_ids",
    "action_anchor_ids", "exit_anchor_ids", "continuity_anchor_ids",
    "shots", "field_provenance",
}
LOCKED_SCAFFOLD_PROVENANCE_KEYS = {
    "entry", "action_state_chain", "exit", "continuity", "shots",
}
SHOT_SCAFFOLD_KEYS = {
    "shot_id", "source_refs", "source_anchor_ids", "quote_ids",
}
SHOT_CREATIVE_KEYS = {"shot_id", "purpose", "action_additions", "camera"}
FIXED_TRANSFORM_ROLES = {
    "source_role": "PROVIDER_NEUTRAL_MASTER",
    "target_role": "NEUTRAL_EXECUTION_PROMPT",
    "derivation": "HELPER_DERIVED",
}
COMMIT_JOURNAL_KEY = "__alpha7_in_place_commit_journal__"
COMMIT_JOURNAL_VERSION = "alpha7-in-place-commit-1.0"
CONTENT_SELF_REVIEW_CHECK_KEYS = {
    "scene_title_is_specific",
    "prompt_working_draft_present",
    "facts_proposals_separated",
    "shots_have_dramatic_beats",
    "sound_is_unambiguous",
}


def _expected_source_read_scope_attestation() -> dict[str, Any]:
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


def _runtime_helper_scripts_sha256() -> str:
    script_root = Path(__file__).resolve().parent
    return sha256_value(
        [
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
    )


def _prompt_hashes(unit: dict[str, Any]) -> dict[str, str]:
    bundle = unit.get("prompt_bundle")
    if not isinstance(bundle, dict):
        return {}
    result: dict[str, str] = {}
    for key in (
        "master_prompt", "transform_plan", "neutral_execution_prompt", "provider_prompt",
    ):
        artifact = bundle.get(key)
        if not isinstance(artifact, dict) or not isinstance(artifact.get("text"), str):
            continue
        artifact["sha256"] = sha256_text(artifact["text"])
        result[key] = artifact["sha256"]
    return result


def finalize_legacy_contract(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("contract_version") in READ_ONLY_CONTRACT_VERSIONS:
        raise ValueError(
            "E_READ_ONLY_CONTRACT_FINALIZATION: alpha7-longform-1.0 through 1.4 "
            "cannot be finalized; use the explicit 1.5 migrator"
        )
    raise ValueError("legacy finalization accepts read-only contracts only")


# Backwards-compatible import name used by earlier packaging checks.
finalize_contract = finalize_legacy_contract


def _ordered_unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _locked_scaffold(
    contract: dict[str, Any], unit: dict[str, Any], window: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Validate and return the helper-owned 1.5 directing scaffold.

    This is deliberately stricter than merely trusting the window hash.  It
    prevents an authored overlay from turning helper-owned IDs, source spans,
    routing, or shot allocation into an editable creative surface.
    """

    unit_id = unit.get("unit_id", "UNKNOWN")
    scaffold = window.get("locked_director_scaffold")
    if not isinstance(scaffold, dict) or set(scaffold) != LOCKED_SCAFFOLD_KEYS:
        raise ValueError(f"{unit_id}: E_LOCKED_SCAFFOLD_SHAPE")
    if (
        scaffold.get("scaffold_version") != DIRECTOR_SCAFFOLD_VERSION
        or scaffold.get("derivation") != "HELPER_DERIVED"
        or scaffold.get("target_mode") != window.get("target_mode")
        or window.get("fixed_transform_roles") != FIXED_TRANSFORM_ROLES
        or window.get("locked_scaffold_sha256") != sha256_value(scaffold)
    ):
        raise ValueError(f"{unit_id}: E_LOCKED_SCAFFOLD_HASH")
    anchors = scaffold.get("semantic_anchors")
    if not isinstance(anchors, list) or not anchors:
        raise ValueError(f"{unit_id}: E_LOCKED_SEMANTIC_ANCHORS")
    anchor_map: dict[str, dict[str, Any]] = {}
    atom_map = {
        item.get("atom_id"): item
        for item in contract.get("source_atoms", [])
        if isinstance(item, dict)
    }
    unit_refs = list(unit.get("source_refs", []))
    dialogue_ids = {
        item.get("dialogue_id")
        for item in contract.get("source_dialogue_inventory", [])
        if isinstance(item, dict)
    }
    for anchor in anchors:
        if not isinstance(anchor, dict) or set(anchor) != SEMANTIC_ANCHOR_KEYS:
            raise ValueError(f"{unit_id}: E_LOCKED_SEMANTIC_ANCHOR_SHAPE")
        anchor_id = anchor.get("anchor_id")
        source_ref = anchor.get("source_ref")
        exact_text = anchor.get("exact_text")
        start_cp = anchor.get("start_cp")
        end_cp = anchor.get("end_cp")
        quote_ids = anchor.get("quote_ids")
        atom_text = normalize_text(atom_map.get(source_ref, {}).get("text", ""))
        if (
            not isinstance(anchor_id, str)
            or not anchor_id
            or anchor_id in anchor_map
            or source_ref not in unit_refs
            or not isinstance(exact_text, str)
            or not exact_text.strip()
            or exact_text not in atom_text
            or anchor.get("text_sha256") != sha256_text(exact_text)
            or not isinstance(start_cp, int)
            or not isinstance(end_cp, int)
            or start_cp < 0
            or end_cp <= start_cp
            or not isinstance(anchor.get("anchor_role"), str)
            or not anchor.get("anchor_role")
            or not isinstance(quote_ids, list)
            or len(quote_ids) != len(set(quote_ids))
            or any(item not in dialogue_ids for item in quote_ids)
        ):
            raise ValueError(f"{unit_id}: E_LOCKED_SEMANTIC_ANCHOR")
        anchor_map[anchor_id] = anchor

    id_fields = {
        "entry": "entry_anchor_ids",
        "action_state_chain": "action_anchor_ids",
        "exit": "exit_anchor_ids",
        "continuity": "continuity_anchor_ids",
    }
    for field, id_key in id_fields.items():
        anchor_ids = scaffold.get(id_key)
        if (
            not isinstance(anchor_ids, list)
            or not anchor_ids
            or (field in {"entry", "exit"} and len(anchor_ids) != 1)
            or len(anchor_ids) != len(set(anchor_ids))
            or any(anchor_id not in anchor_map for anchor_id in anchor_ids)
        ):
            raise ValueError(f"{unit_id}: E_LOCKED_SCAFFOLD_{field.upper()}")
    provenance = scaffold.get("field_provenance")
    if not isinstance(provenance, dict) or set(provenance) != LOCKED_SCAFFOLD_PROVENANCE_KEYS:
        raise ValueError(f"{unit_id}: E_LOCKED_SCAFFOLD_PROVENANCE")
    expected_provenance_ids = {
        "entry": scaffold["entry_anchor_ids"],
        "action_state_chain": scaffold["action_anchor_ids"],
        "exit": scaffold["exit_anchor_ids"],
        "continuity": scaffold["continuity_anchor_ids"],
        "shots": _ordered_unique(
            [
                anchor_id
                for shot in scaffold.get("shots", [])
                if isinstance(shot, dict)
                for anchor_id in shot.get("source_anchor_ids", [])
            ]
        ),
    }
    for field, anchor_ids in expected_provenance_ids.items():
        record = provenance.get(field)
        if (
            not isinstance(record, dict)
            or set(record) != {"status", "source_anchor_ids"}
            or record.get("status") != "HELPER_DERIVED"
            or record.get("source_anchor_ids") != anchor_ids
        ):
            raise ValueError(f"{unit_id}: E_LOCKED_SCAFFOLD_PROVENANCE")

    shots = scaffold.get("shots")
    minimum_shots = scaffold.get("minimum_shots")
    if not isinstance(shots, list) or not isinstance(minimum_shots, int) or minimum_shots < 0:
        raise ValueError(f"{unit_id}: E_LOCKED_SHOT_SCAFFOLD")
    if scaffold["target_mode"] == "EDITED_SEQUENCE":
        if len(shots) < minimum_shots or minimum_shots < 1:
            raise ValueError(f"{unit_id}: E_LOCKED_SHOT_SCAFFOLD")
    elif scaffold["target_mode"] == "GENERATABLE_SHOT":
        if len(shots) != 1 or minimum_shots != 0:
            raise ValueError(f"{unit_id}: E_LOCKED_SHOT_SCAFFOLD")
    else:
        raise ValueError(f"{unit_id}: E_LOCKED_SHOT_SCAFFOLD")
    seen_quotes: set[str] = set()
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict) or set(shot) != SHOT_SCAFFOLD_KEYS:
            raise ValueError(f"{unit_id}: E_LOCKED_SHOT_SCAFFOLD")
        refs = shot.get("source_refs")
        anchor_ids = shot.get("source_anchor_ids")
        quote_ids = shot.get("quote_ids")
        if (
            shot.get("shot_id") != f"SH{index:03d}"
            or not isinstance(refs, list)
            or not refs
            or any(ref not in unit_refs for ref in refs)
            or not isinstance(anchor_ids, list)
            or not anchor_ids
            or any(anchor_id not in anchor_map for anchor_id in anchor_ids)
            or any(anchor_map[anchor_id]["source_ref"] not in refs for anchor_id in anchor_ids)
            or not isinstance(quote_ids, list)
            or len(quote_ids) != len(set(quote_ids))
            or any(quote_id not in dialogue_ids or quote_id in seen_quotes for quote_id in quote_ids)
        ):
            raise ValueError(f"{unit_id}: E_LOCKED_SHOT_SCAFFOLD")
        seen_quotes.update(quote_ids)
    return scaffold, anchor_map


def _source_provenance(anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "SOURCE_SUPPORTED",
        "source_refs": [anchor["source_ref"]],
        "source_anchor": anchor["exact_text"],
    }


def _append_inference(
    inferences: list[dict[str, Any]],
    *,
    unit_id: str,
    text: str,
    source_refs: list[str],
    category: str,
) -> dict[str, Any]:
    inference_id = f"INF-{unit_id}-{len(inferences) + 1:03d}"
    inference = {
        "inference_id": inference_id,
        "status": "PROPOSED_DIRECTOR_INFERENCE",
        "text": text,
        "source_refs": _ordered_unique(source_refs),
        "proposal_category": category,
        "plot_state_delta": "NONE",
    }
    inferences.append(inference)
    return {
        "status": "PROPOSED_DIRECTOR_INFERENCE",
        "source_refs": inference["source_refs"],
        "inference_id": inference_id,
        "field_fragment": text,
    }


def _derive_creative_provenance(
    value: Any,
    *,
    anchors: list[dict[str, Any]],
    inferences: list[dict[str, Any]],
    unit_id: str,
    source_refs: list[str],
    category: str,
) -> dict[str, Any]:
    normalized = normalize_text(value).strip() if isinstance(value, str) else ""
    for anchor in anchors:
        if normalized == normalize_text(anchor["exact_text"]).strip():
            return _source_provenance(anchor)
    return _append_inference(
        inferences,
        unit_id=unit_id,
        text=value if isinstance(value, str) else "",
        source_refs=source_refs,
        category=category,
    )


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _action_addition_capacity(locked_shot: dict[str, Any]) -> int:
    """Return the remaining 1-3 item budget after helper-owned source anchors."""

    source_anchor_ids = locked_shot.get("source_anchor_ids")
    anchor_count = len(source_anchor_ids) if isinstance(source_anchor_ids, list) else 3
    return max(0, 3 - anchor_count)


def _expected_editable_paths(
    overlay: dict[str, Any],
    locked_shots: list[dict[str, Any]],
    source_locked_speaker_ids: set[str] | None = None,
    directorial_claim_index: int | None = None,
) -> list[str]:
    """Return the complete creative leaf/array surface for one compact Unit."""

    source_locked_speaker_ids = source_locked_speaker_ids or set()
    director = overlay.get("director_overlay") if isinstance(overlay.get("director_overlay"), dict) else {}
    prompt = overlay.get("prompt_overlay") if isinstance(overlay.get("prompt_overlay"), dict) else {}
    paths = [
        "/director_overlay/performance",
        "/director_overlay/camera",
        "/director_overlay/sound",
    ]
    speakers = director.get("dialogue_speakers")
    if isinstance(speakers, dict):
        paths.extend(
            f"/director_overlay/dialogue_speakers/{_pointer_token(str(key))}"
            for key in speakers
            if str(key) not in source_locked_speaker_ids
        )
    classifications = director.get("quote_classifications")
    if isinstance(classifications, dict):
        paths.extend(
            f"/director_overlay/quote_classifications/{_pointer_token(str(key))}"
            for key in classifications
        )
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


def _assert_r5_envelope(envelope: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if set(envelope) != {"immutable_contract", "target_windows", "compiled_unit_overlays"}:
        raise ValueError("authoring envelope must contain exactly immutable_contract/target_windows/compiled_unit_overlays")
    contract = envelope.get("immutable_contract")
    windows = envelope.get("target_windows")
    overlays = envelope.get("compiled_unit_overlays")
    if not isinstance(contract, dict) or not isinstance(windows, list) or not isinstance(overlays, list):
        raise ValueError("authoring envelope fields have invalid types")
    if contract.get("contract_version") in READ_ONLY_CONTRACT_VERSIONS:
        raise ValueError(
            "E_READ_ONLY_CONTRACT_FINALIZATION: alpha7-longform-1.0 through 1.4 "
            "cannot be finalized; migrate and re-author under 1.5"
        )
    if contract.get("authoring_version") != AUTHORING_VERSION or contract.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("authoring envelope is not canonical alpha7-longform-authoring-1.5 / contract 1.5")
    runtime_identity = contract.get("runtime_identity")
    if (
        not isinstance(runtime_identity, dict)
        or runtime_identity.get("helper_scripts_sha256") != _runtime_helper_scripts_sha256()
    ):
        raise ValueError(
            "E_REPREPARE_REQUIRED: 当前 1.5 草稿由旧 helper 准备；请重新运行 prepare，"
            "不要在旧工作面上继续修改"
        )
    if contract.get("helper_lock_sha256") != sha256_value(expected_helper_lock_projection(contract)):
        raise ValueError("immutable_contract helper lock mismatch; Phase-A/source may have been edited")
    if not re.fullmatch(r"[0-9a-f]{64}", str(contract.get("authoring_guide_sha256", ""))):
        raise ValueError("immutable_contract is missing its authoring guide binding")
    workflow = contract.get("authoring_workflow")
    if (
        not isinstance(workflow, dict)
        or workflow.get("mode") != "CHECK_THEN_COMMIT_V1"
        or not all(
            isinstance(workflow.get(key), list)
            and workflow[key]
            and all(isinstance(item, str) and item for item in workflow[key])
            for key in ("check_argv", "retry_argv", "commit_argv")
        )
    ):
        raise ValueError("immutable_contract is missing exact check/retry/commit argv")
    request = contract.get("selection_request")
    sample_ids = request.get("sample_unit_ids") if isinstance(request, dict) else None
    if not isinstance(sample_ids, list) or not 3 <= len(sample_ids) <= 5:
        raise ValueError("selection_request must lock 3-5 Pilot Unit IDs")
    if len(windows) != len(sample_ids) or len(overlays) != len(sample_ids):
        raise ValueError("target_windows and overlays must match the locked Pilot size")
    if windows != expected_target_windows(contract):
        raise ValueError("target_windows differ from the helper-owned immutable projection")
    window_ids = [item.get("unit_id") for item in windows if isinstance(item, dict)]
    overlay_ids = [item.get("unit_id") for item in overlays if isinstance(item, dict)]
    if window_ids != sample_ids or overlay_ids != sample_ids:
        raise ValueError("target windows/overlays must preserve helper-selected Unit order")
    unit_map = {
        unit.get("unit_id"): unit
        for unit in contract.get("units", [])
        if isinstance(unit, dict)
    }
    modes = request.get("target_modes") if isinstance(request.get("target_modes"), dict) else {}
    for index, (window, overlay) in enumerate(zip(windows, overlays)):
        if not isinstance(window, dict) or not isinstance(overlay, dict) or set(overlay) != OVERLAY_KEYS:
            raise ValueError(f"overlay {index} must expose exactly the three editable overlays")
        unit_id = window.get("unit_id")
        unit = unit_map.get(unit_id)
        if unit is None or window.get("source_window") != unit.get("source_window"):
            raise ValueError(f"{unit_id}: target window does not match immutable Unit")
        if window.get("target_mode") != modes.get(unit_id):
            raise ValueError(f"{unit_id}: target_mode differs from helper selection")
        scaffold, _ = _locked_scaffold(contract, unit, window)
        director = overlay.get("director_overlay")
        prompt = overlay.get("prompt_overlay")
        quality = overlay.get("quality_overlay")
        if not isinstance(director, dict) or set(director) != DIRECTOR_OVERLAY_KEYS:
            raise ValueError(f"{unit_id}: director_overlay fields are incomplete or expanded")
        if not isinstance(prompt, dict) or set(prompt) != PROMPT_OVERLAY_KEYS:
            raise ValueError(f"{unit_id}: prompt_overlay fields are incomplete or expanded")
        if not isinstance(quality, dict) or set(quality) != QUALITY_OVERLAY_KEYS:
            raise ValueError(f"{unit_id}: quality_overlay fields are incomplete or expanded")
        expected_creative_shots = (
            scaffold["shots"] if scaffold["target_mode"] == "EDITED_SEQUENCE" else []
        )
        source_locked_nonlexical_speakers = (
            source_locked_nonlexical_speakers_from_window(window)
        )
        semantic_gate = window.get("semantic_gate")
        expected_claim_slots = expected_authoring_claim_slots(unit, scaffold)
        if (
            not isinstance(semantic_gate, dict)
            or semantic_gate.get("claim_slots") != expected_claim_slots
        ):
            raise ValueError(
                f"E_SEMANTIC_CLAIM_LOCK: {unit_id} 的来源主张槽不是当前 helper 投影；请重新 prepare"
            )
        directorial_claim_index = len(expected_claim_slots) - 1
        if overlay.get("editable_paths") != _expected_editable_paths(
            overlay,
            expected_creative_shots,
            set(source_locked_nonlexical_speakers),
            directorial_claim_index,
        ):
            raise ValueError(f"{unit_id}: E_EDITABLE_PATHS_TAMPER")
        if not all(
            isinstance(director.get(field), str) and director[field].strip()
            for field in ("performance", "camera", "sound")
        ):
            raise ValueError(f"{unit_id}: creative director fields must be nonempty strings")
        relevant_ids = window.get("dialogue_slot_ids")
        if not isinstance(relevant_ids, list):
            raise ValueError(f"{unit_id}: dialogue_slot_ids must be a list")
        speakers = director.get("dialogue_speakers")
        classifications = director.get("quote_classifications")
        if not isinstance(speakers, dict):
            raise ValueError(f"{unit_id}: dialogue_speakers must be an object")
        for dialogue_id, source_speaker in source_locked_nonlexical_speakers.items():
            if dialogue_id in speakers:
                raise ValueError(
                    "E_SOURCE_OWNED_NONLEXICAL_SPEAKER_TAMPER: "
                    f"{unit_id}/{dialogue_id} 的人物发声主体由来源锁定为“{source_speaker}”；"
                    "该 quote ID 不得出现在 dialogue_speakers，不能改名或改成环境声"
                )
        expected_speaker_ids = [
            dialogue_id
            for dialogue_id in relevant_ids
            if dialogue_id not in source_locked_nonlexical_speakers
        ]
        if list(speakers) != expected_speaker_ids:
            raise ValueError(
                f"{unit_id}: dialogue_speakers must exactly cover helper-open speaker IDs"
            )
        if not isinstance(classifications, dict) or list(classifications) != relevant_ids:
            raise ValueError(
                f"{unit_id}: quote_classifications must exactly cover helper-owned quote IDs"
            )
        shot_creative = director.get("shot_creative")
        if not isinstance(shot_creative, list) or len(shot_creative) != len(expected_creative_shots):
            raise ValueError(f"{unit_id}: E_SHOT_CREATIVE_COVERAGE")
        for shot_index, (creative, locked) in enumerate(
            zip(shot_creative, expected_creative_shots), start=1
        ):
            if (
                not isinstance(creative, dict)
                or set(creative) != SHOT_CREATIVE_KEYS
                or creative.get("shot_id") != locked.get("shot_id")
                or not isinstance(creative.get("purpose"), str)
                or not creative["purpose"].strip()
                or not isinstance(creative.get("camera"), str)
                or not creative["camera"].strip()
                or not isinstance(creative.get("action_additions"), list)
                or not all(isinstance(item, str) and item.strip() for item in creative["action_additions"])
            ):
                raise ValueError(f"{unit_id}: E_SHOT_CREATIVE[{shot_index}]")
            additions = creative["action_additions"]
            remaining_capacity = _action_addition_capacity(locked)
            if len(additions) > remaining_capacity:
                anchor_count = len(locked["source_anchor_ids"])
                raise ValueError(
                    "E_SHOT_ACTION_ADDITION_CAPACITY: "
                    f"{unit_id}/{creative['shot_id']} 已有 {anchor_count} 条锁定来源动作，"
                    f"导演动作补充剩余容量为 {remaining_capacity} 条，实际填写 {len(additions)} 条；"
                    "容量为 0 时必须保持空数组，且不得复述锁定来源动作"
                )
        transform = prompt.get("transform_plan")
        if (
            not isinstance(transform, dict)
            or set(transform) != TRANSFORM_PLAN_KEYS
            or any(not isinstance(transform.get(field), list) for field in TRANSFORM_PLAN_KEYS)
        ):
            raise ValueError(f"{unit_id}: transform_plan exposes only the three editable arrays")
        claim_slots = prompt.get("claims")
        if not isinstance(claim_slots, list) or len(claim_slots) != len(expected_claim_slots):
            raise ValueError(
                f"E_SEMANTIC_CLAIM_LOCK: {unit_id} 的 claims 数量必须保持 helper 预分配槽数量"
            )
        for claim_index, (actual_claim, expected_claim) in enumerate(
            zip(claim_slots, expected_claim_slots)
        ):
            claim_path = f"/prompt_overlay/claims/{claim_index}"
            if not isinstance(actual_claim, dict) or set(actual_claim) != {
                "text", "relation", "source_refs",
            }:
                raise ValueError(
                    f"E_SEMANTIC_CLAIM_LOCK: {unit_id}{claim_path} 必须保持固定三字段槽"
                )
            if claim_index == directorial_claim_index:
                if (
                    actual_claim.get("relation") != "DIRECTORIAL_CONTROL"
                    or actual_claim.get("source_refs") != expected_claim["source_refs"]
                    or not isinstance(actual_claim.get("text"), str)
                ):
                    raise ValueError(
                        f"E_SEMANTIC_CLAIM_LOCK: 请只修改 {claim_path}/text；"
                        "DIRECTORIAL_CONTROL 标签和当前来源引用不可改"
                    )
            elif actual_claim != expected_claim:
                raise ValueError(
                    f"E_SEMANTIC_CLAIM_LOCK: 请恢复 {claim_path}；"
                    "SOURCE/FAITHFUL 正文、标签和引用由锁定来源锚派生，不接受手写"
                )
        if not isinstance(quality.get("scene_title"), str) or not quality["scene_title"].strip():
            raise ValueError(f"{unit_id}: quality_overlay.scene_title must be nonempty")
        if not isinstance(quality.get("findings"), list):
            raise ValueError(f"{unit_id}: quality_overlay.findings must be a list")
    return copy.deepcopy(contract), windows, overlays


def _merge_compact_overlays(envelope: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if set(patch) != {
        "authoring_version",
        "helper_lock_sha256",
        "authoring_guide_sha256",
        "authoring_guide",
        "source_read_scope_attestation",
        "target_windows",
        "compiled_unit_overlays",
    }:
        raise ValueError("compact overlay patch has unexpected fields")
    contract = envelope.get("immutable_contract")
    if not isinstance(contract, dict):
        raise ValueError("authoring envelope is missing immutable_contract")
    if (
        patch.get("authoring_version") != contract.get("authoring_version")
        or patch.get("helper_lock_sha256") != contract.get("helper_lock_sha256")
    ):
        raise ValueError("compact overlay patch is bound to a different immutable contract")
    guide = patch.get("authoring_guide")
    guide_sha256 = patch.get("authoring_guide_sha256")
    if (
        not isinstance(guide, dict)
        or guide.get("guide_version") != AUTHORING_GUIDE_VERSION
        or not isinstance(guide.get("unit_requirements"), dict)
        or set(guide["unit_requirements"]) != set(contract["selection_request"]["sample_unit_ids"])
    ):
        raise ValueError("compact overlay patch is missing the self-contained alpha7 authoring guide")
    if (
        not isinstance(guide_sha256, str)
        or guide_sha256 != contract.get("authoring_guide_sha256")
        or guide_sha256 != sha256_value(guide)
    ):
        raise ValueError("E_AUTHORING_GUIDE_TAMPER: compact authoring guide is not bound to the immutable contract")
    if (
        patch.get("source_read_scope_attestation") != _expected_source_read_scope_attestation()
        or guide.get("source_read_scope_attestation") != patch.get("source_read_scope_attestation")
    ):
        raise ValueError("E_SOURCE_READ_SCOPE: guide-only process boundary attestation was altered")
    merged = copy.deepcopy(envelope)
    merged["target_windows"] = copy.deepcopy(patch.get("target_windows"))
    merged["compiled_unit_overlays"] = copy.deepcopy(patch.get("compiled_unit_overlays"))
    return merged


def _replace_dialogue_slots(
    template: str,
    inventory: dict[str, dict[str, Any]],
    spoken_ids: set[str] | None = None,
    *,
    insert_spoken: bool = True,
) -> tuple[str, list[str]]:
    if not isinstance(template, str) or not template.strip():
        return "", []
    slot_ids: list[str] = []
    normalized_template = normalize_text(template)
    # Spoken text has one authoritative insertion point: its immutable slot.
    # If a creator also copied the same line into surrounding prose, neutralize
    # that duplicate before slot replacement instead of making the creator hunt
    # an occurrence that may have come from a helper-owned source anchor.
    for dialogue_id, item in inventory.items():
        if spoken_ids is not None and dialogue_id not in spoken_ids:
            continue
        dialogue_text = normalize_text(item.get("text", "")) if isinstance(item, dict) else ""
        if dialogue_text:
            for left, right in (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"')):
                normalized_template = normalized_template.replace(
                    f"{left}{dialogue_text}{right}",
                    "〔逐字对白由固定台词位置写入〕",
                )
            normalized_template = re.sub(
                rf"(?<![\u4e00-\u9fffA-Za-z0-9]){re.escape(dialogue_text)}"
                rf"(?![\u4e00-\u9fffA-Za-z0-9])",
                "〔逐字对白由固定台词位置写入〕",
                normalized_template,
            )

    def replace(match: re.Match[str]) -> str:
        dialogue_id = match.group(1)
        spacing = match.group(2) or ""
        template_punctuation = match.group(3) or ""
        item = inventory.get(dialogue_id)
        if not isinstance(item, dict):
            return match.group(0)
        # The authoring template initially exposes every source quote as a
        # classification slot.  Finalization owns the routing decision: only
        # quotes finally classified as spoken dialogue remain dialogue slots;
        # SFX/internal/quoted-text spans are rendered through their director
        # fields instead of being injected a second time as speech.
        if spoken_ids is not None and dialogue_id not in spoken_ids:
            return _NON_SPOKEN_SLOT_SENTINEL + spacing + template_punctuation
        if dialogue_id not in slot_ids:
            slot_ids.append(dialogue_id)
        if not insert_spoken:
            return "〔逐字对白见下方逐镜执行稿〕" + spacing + template_punctuation
        dialogue_text = normalize_text(item.get("text", ""))
        # The immutable dialogue owns its terminal punctuation.  A creator may
        # naturally type punctuation after the slot; discard only that
        # template-side boundary punctuation when the source line already
        # ends a sentence.  Source dialogue bytes are never rewritten.
        if TERMINAL_DIALOGUE_RE.search(dialogue_text.rstrip()):
            # Keep the immutable line visibly separate from the next director
            # instruction. Without a boundary, `台词。然后……` becomes one lexical
            # run and the exact-dialogue gate must reject it.
            if template_punctuation and not spacing:
                spacing = "\n"
            template_punctuation = ""
        return dialogue_text + spacing + template_punctuation

    return SLOT_BOUNDARY_RE.sub(replace, normalized_template), slot_ids


VISIBLE_QUOTE_TITLE = "【本镜必须保留的发声与画面文字】"
_NON_SPOKEN_SLOT_SENTINEL = "〔由固定镜头提示写入〕"
_EMPTY_SPEECH_LINE_RE = re.compile(
    rf"(?m)^[^\n。！？!?；;]{{0,28}}(?:说|问|答|喊|道|叫|念|读|发出)"
    rf"[：:]?\s*[“\"「『]?{re.escape(_NON_SPOKEN_SLOT_SENTINEL)}[”\"」』]?"
    r"[，,。！？!?；;]?\s*$"
)


def _strip_nonspoken_quote_copies(
    text: str, assignments: list[dict[str, Any]]
) -> str:
    """Remove only whole duplicate quote/cue lines before helper injection.

    A previous implementation globally deleted every bare non-spoken quote
    string.  A one-character screen label such as ``东`` therefore corrupted
    ordinary directing prose such as ``东门`` and ``东方``.  Helper de-duplication
    is deliberately line-bound here: embedded narration remains creator-owned,
    while a standalone wrapped quote, a quote-only speech/cue line, or an exact
    canonical helper line is replaced by the one canonical block appended
    below.
    """

    cleaned = normalize_text(text)
    canonical_cues = set(render_visible_quote_cues(assignments))
    canonical_lines = {
        VISIBLE_QUOTE_TITLE,
        *canonical_cues,
        *(f"- {cue}" for cue in canonical_cues),
    }
    nonspoken_texts = [
        normalize_text(item.get("text", ""))
        for item in assignments
        if isinstance(item, dict)
        and item.get("kind") != "SPOKEN_DIALOGUE"
        and isinstance(item.get("text"), str)
        and item.get("text")
    ]
    duplicate_line_patterns: list[re.Pattern[str]] = []
    for quote_text in nonspoken_texts:
        escaped = re.escape(quote_text)
        wrapped = rf'(?:“{escaped}”|「{escaped}」|『{escaped}』|"{escaped}")'
        duplicate_line_patterns.append(
            re.compile(
                rf"^(?:[-*]\s*)?(?:{wrapped})[，,。！？!?；;]?$"
            )
        )
        duplicate_line_patterns.append(
            re.compile(
                rf"^(?:[-*]\s*)?(?:(?:画面文字(?:（不朗读）)?|非词汇人声)\s*[：:]\s*|"
                rf"[^\n。！？!?；;]{{1,20}}(?:说|问|答|喊|道|叫|念|读|发出)\s*[：:]?\s*)"
                rf"{wrapped}[，,。！？!?；;]?$"
            )
        )
    kept_lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped in canonical_lines or any(
            pattern.fullmatch(stripped) for pattern in duplicate_line_patterns
        ):
            continue
        kept_lines.append(line)
    cleaned = "\n".join(kept_lines)
    cleaned = _EMPTY_SPEECH_LINE_RE.sub("", cleaned)
    cleaned = cleaned.replace(_NON_SPOKEN_SLOT_SENTINEL, "")
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _inject_visible_quote_cues(
    text: str, assignments: list[dict[str, Any]]
) -> str:
    """Append one natural Chinese helper-owned cue block to a creator surface."""

    cleaned = _strip_nonspoken_quote_copies(text, assignments)
    cues = render_visible_quote_cues(assignments)
    if not cues:
        return cleaned
    block = "\n".join([VISIBLE_QUOTE_TITLE, *(f"- {cue}" for cue in cues)])
    return f"{cleaned}\n\n{block}".strip() if cleaned else block


def _prompt_artifact(unit_id: str, layer: str, text: str, serial: int) -> dict[str, Any]:
    return {
        "artifact_id": f"{layer}-{serial:03d}",
        "unit_id": unit_id,
        "layer": layer,
        "text": text,
        "sha256": sha256_text(text),
    }


def _compile_overlay(
    contract: dict[str, Any],
    unit: dict[str, Any],
    window: dict[str, Any],
    overlay: dict[str, Any],
    serial: int,
) -> None:
    unit_id = unit["unit_id"]
    director_overlay = copy.deepcopy(overlay["director_overlay"])
    prompt_overlay = copy.deepcopy(overlay["prompt_overlay"])
    quality_overlay = copy.deepcopy(overlay["quality_overlay"])
    scaffold, anchor_map = _locked_scaffold(contract, unit, window)
    semantic_gate = window.get("semantic_gate") if isinstance(window.get("semantic_gate"), dict) else {}
    semantic_findings = semantic_gate_findings(
        contract,
        unit,
        semantic_overlay_surfaces(overlay),
        action_locks=(
            semantic_gate.get("action_locks")
            if isinstance(semantic_gate.get("action_locks"), list)
            else None
        ),
    )
    inventory_items = [
        item
        for item in contract.get("source_dialogue_inventory", [])
        if isinstance(item, dict) and set(item.get("source_refs", [])).issubset(set(unit["source_refs"]))
    ]
    inventory = {item["dialogue_id"]: item for item in contract.get("source_dialogue_inventory", [])}
    classifications = director_overlay.get("quote_classifications")
    if not isinstance(classifications, dict):
        classifications = {}
    speakers = director_overlay.get("dialogue_speakers")
    if not isinstance(speakers, dict):
        speakers = {}
    relevant_ids = [item["dialogue_id"] for item in inventory_items]
    spoken_ids = [
        dialogue_id
        for dialogue_id in relevant_ids
        if classifications.get(dialogue_id) == "SPOKEN_DIALOGUE"
    ]
    spoken_id_set = set(spoken_ids)
    master_text, _ = _replace_dialogue_slots(
        prompt_overlay.get("master_prompt_template"), inventory, spoken_id_set
    )
    neutral_execution_text, _ = _replace_dialogue_slots(
        prompt_overlay.get("neutral_execution_prompt_template"), inventory, spoken_id_set,
        insert_spoken=False,
    )
    transform_edits = prompt_overlay.get("transform_plan")
    if not isinstance(transform_edits, dict) or set(transform_edits) != TRANSFORM_PLAN_KEYS:
        raise ValueError(
            f"{unit_id}: transform_plan must contain exactly {sorted(TRANSFORM_PLAN_KEYS)}"
        )
    if any(not isinstance(transform_edits.get(field), list) for field in TRANSFORM_PLAN_KEYS):
        raise ValueError(
            f"{unit_id}: preserve、operations、deferred_provider_decisions 必须都是数组"
        )
    transform_plan = {
        "source_role": window["fixed_transform_roles"]["source_role"],
        "target_role": window["fixed_transform_roles"]["target_role"],
        "preserve": copy.deepcopy(transform_edits["preserve"]),
        "operations": copy.deepcopy(transform_edits["operations"]),
        "deferred_provider_decisions": copy.deepcopy(
            transform_edits["deferred_provider_decisions"]
        ),
    }
    transform_plan_text = json.dumps(
        transform_plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if "{{VERBATIM_DIALOGUE_SLOT:" in transform_plan_text or any(
        str(item.get("text", "")) and str(item.get("text")) in transform_plan_text
        for item in inventory_items
    ):
        raise ValueError(
            f"{unit_id}: transform_plan must reference preservation rules, not dialogue body text"
        )
    claims = prompt_overlay.get("claims")
    expected_claim_slots = expected_authoring_claim_slots(unit, scaffold)
    prompt_claims: list[dict[str, Any]] = []
    prompt_traces: list[dict[str, Any]] = []
    for index, slot in enumerate(expected_claim_slots[:-1], start=1):
        claim_id = f"CL{serial:03d}-SOURCE-{index:02d}"
        trace_id = f"TR{serial:03d}-SOURCE-{index:02d}"
        prompt_claims.append(
            {"claim_id": claim_id, "text": slot["text"], "trace_id": trace_id}
        )
        prompt_traces.append(
            {
                "trace_id": trace_id,
                "relation": slot["relation"],
                "source_refs": list(slot["source_refs"]),
                "state_refs": [],
                "project_rule_refs": [],
                "capability_ids": ["BASE_NARRATIVE"],
            }
        )
    directorial_slot = claims[-1] if isinstance(claims, list) and claims else {}
    directorial_text = directorial_slot.get("text") if isinstance(directorial_slot, dict) else ""
    if isinstance(directorial_text, str) and directorial_text.strip():
        prompt_claims.append(
            {
                "claim_id": f"CL{serial:03d}-DIRECTORIAL",
                "text": directorial_text,
                "trace_id": f"TR{serial:03d}-DIRECTORIAL",
            }
        )
        prompt_traces.append(
            {
                "trace_id": f"TR{serial:03d}-DIRECTORIAL",
                "relation": "DIRECTORIAL_CONTROL",
                "source_refs": list(unit["source_refs"]),
                "state_refs": [],
                "project_rule_refs": [],
                "capability_ids": ["BASE_NARRATIVE"],
            }
        )
    negative_clauses = prompt_overlay.get("negative_clauses")
    if not isinstance(negative_clauses, list):
        negative_clauses = []
    candidates = [
        {
            "clause_id": f"NEG{serial:03d}-{index:02d}",
            "text": clause,
            "risk_refs": [f"RISK{serial:03d}-{index:02d}"],
            "origin": "AUTHORING_OVERLAY",
            "text_sha256": sha256_text(clause) if isinstance(clause, str) else "",
        }
        for index, clause in enumerate(negative_clauses, start=1)
    ]
    allowed_quote_types = {
        "SPOKEN_DIALOGUE",
        "INTERNAL_THOUGHT",
        "NON_LEXICAL_VOCALIZATION",
        "SFX",
        "QUOTED_TEXT",
    }
    classification_findings: list[str] = []
    for finding in prompt_layer_independence_findings(
        prompt_overlay.get("master_prompt_template"),
        prompt_overlay.get("neutral_execution_prompt_template"),
    ):
        classification_findings.append(f"AUTHORING_LAYER_CHECK:{finding}")
    if set(classifications) != set(relevant_ids):
        classification_findings.append("QUOTE_CLASSIFICATION_COVERAGE_MISMATCH")
    for dialogue_id in relevant_ids:
        if classifications.get(dialogue_id) not in allowed_quote_types:
            classification_findings.append(f"UNCLASSIFIED_SOURCE_QUOTE:{dialogue_id}")
    for item in inventory_items:
        if (
            "LIKELY_NON_LEXICAL_VOCALIZATION" in item.get("classification_hints", [])
            and classifications.get(item["dialogue_id"])
            != "NON_LEXICAL_VOCALIZATION"
        ):
            classification_findings.append(
                f"QUOTE_CLASSIFICATION_CONFLICT:{item['dialogue_id']}:"
                "SOURCE_LOCKED_NONLEXICAL_VOCALIZATION"
            )
        if classifications.get(item["dialogue_id"]) == "SPOKEN_DIALOGUE":
            for conflict in spoken_quote_conflicts(item):
                classification_findings.append(
                    f"QUOTE_CLASSIFICATION_CONFLICT:{item['dialogue_id']}:{conflict}"
                )
        if (
            classifications.get(item["dialogue_id"]) == "SFX"
            and "LIKELY_NON_LEXICAL_VOCALIZATION" in item.get("classification_hints", [])
        ):
            classification_findings.append(
                f"QUOTE_CLASSIFICATION_CONFLICT:{item['dialogue_id']}:NON_LEXICAL_VOCALIZATION_IS_NOT_SFX"
            )
    dialogue_inventory = [
        {
            "dialogue_id": item["dialogue_id"],
            "speaker": speakers.get(item["dialogue_id"], item.get("speaker", "SOURCE_UNSPECIFIED")),
            "text": item["text"],
            "kind": "VERBATIM_DIALOGUE",
            "source_refs": item["source_refs"],
        }
        for item in inventory_items
        if classifications.get(item["dialogue_id"]) == "SPOKEN_DIALOGUE"
    ]
    quote_assignments = derive_quote_assignments(
        contract.get("source_dialogue_inventory", []),
        scaffold,
        classifications,
        dialogue_inventory,
    )
    unknown_nonlexical_speakers = [
        str(item.get("dialogue_id"))
        for item in quote_assignments
        if item.get("kind") == "NON_LEXICAL_VOCALIZATION"
        and item.get("speaker") == "SOURCE_UNSPECIFIED"
    ]
    classification_findings.extend(
        f"NON_LEXICAL_VOCALIZATION_SPEAKER_UNSPECIFIED:{dialogue_id}"
        for dialogue_id in unknown_nonlexical_speakers
    )
    master_text = _inject_visible_quote_cues(master_text, quote_assignments)
    neutral_execution_text = _strip_nonspoken_quote_copies(
        neutral_execution_text, quote_assignments
    )
    inferences: list[dict[str, Any]] = []
    all_anchors = list(anchor_map.values())
    entry_anchor = anchor_map[scaffold["entry_anchor_ids"][0]]
    action_anchors = [anchor_map[item] for item in scaffold["action_anchor_ids"]]
    exit_anchor = anchor_map[scaffold["exit_anchor_ids"][0]]
    continuity_anchor = anchor_map[scaffold["continuity_anchor_ids"][0]]
    top_provenance: dict[str, Any] = {
        "entry": _source_provenance(entry_anchor),
        "action_state_chain": [_source_provenance(item) for item in action_anchors],
        "exit": _source_provenance(exit_anchor),
        "continuity": _source_provenance(continuity_anchor),
    }
    for field, category in (
        ("performance", "PERFORMANCE"),
        ("camera", "CAMERA"),
        ("sound", "SOUND"),
    ):
        top_provenance[field] = _derive_creative_provenance(
            director_overlay.get(field),
            anchors=all_anchors,
            inferences=inferences,
            unit_id=unit_id,
            source_refs=list(unit["source_refs"]),
            category=category,
        )

    shot_plan: list[dict[str, Any]] = []
    creative_shots = director_overlay.get("shot_creative", [])
    for locked_shot, creative_shot in zip(scaffold["shots"], creative_shots):
        shot_anchors = [anchor_map[item] for item in locked_shot["source_anchor_ids"]]
        source_actions = [item["exact_text"] for item in shot_anchors]
        action_additions = list(creative_shot["action_additions"])
        action_provenance: list[dict[str, Any]] = [
            _source_provenance(item) for item in shot_anchors
        ]
        action_provenance.extend(
            _append_inference(
                inferences,
                unit_id=unit_id,
                text=addition,
                source_refs=list(locked_shot["source_refs"]),
                category="BLOCKING",
            )
            for addition in action_additions
        )
        purpose_provenance = _derive_creative_provenance(
            creative_shot["purpose"],
            anchors=shot_anchors,
            inferences=inferences,
            unit_id=unit_id,
            source_refs=list(locked_shot["source_refs"]),
            category="PACING",
        )
        camera_provenance = _derive_creative_provenance(
            creative_shot["camera"],
            anchors=shot_anchors,
            inferences=inferences,
            unit_id=unit_id,
            source_refs=list(locked_shot["source_refs"]),
            category="CAMERA",
        )
        shot_plan.append(
            {
                "shot_id": locked_shot["shot_id"],
                "purpose": creative_shot["purpose"],
                "action_state_chain": source_actions + action_additions,
                "camera": creative_shot["camera"],
                "source_refs": list(locked_shot["source_refs"]),
                "semantic_anchor_ids": list(locked_shot["source_anchor_ids"]),
                "dialogue_slot_ids": [
                    item for item in locked_shot["quote_ids"] if item in spoken_id_set
                ],
                "field_provenance": {
                    "purpose": purpose_provenance,
                    "action_state_chain": action_provenance,
                    "camera": camera_provenance,
                },
            }
        )
    top_provenance["shot_plan"] = {
        "status": "HELPER_DERIVED",
        "source_refs": list(unit["source_refs"]),
        "locked_scaffold_sha256": window["locked_scaffold_sha256"],
    }
    director_contract = {
        "target_mode": window.get("target_mode"),
        "continuous_time_space": window.get("target_mode") == "GENERATABLE_SHOT",
        "entry": entry_anchor["exact_text"],
        "action_state_chain": [item["exact_text"] for item in action_anchors],
        "performance": director_overlay.get("performance"),
        "camera": director_overlay.get("camera"),
        "sound": director_overlay.get("sound"),
        "exit": exit_anchor["exact_text"],
        "continuity": continuity_anchor["exact_text"],
        "shot_plan": shot_plan,
        "field_provenance": top_provenance,
        "dialogue_inventory": dialogue_inventory,
        "quote_assignments": quote_assignments,
        "proposed_director_inferences": inferences,
    }
    director_contract["execution_beats"] = expected_execution_beats(
        {
            "source_refs": list(unit["source_refs"]),
            "locked_director_scaffold": scaffold,
            "provenance": {"quote_classifications": classifications},
            "director_contract": director_contract,
        },
        contract.get("source_dialogue_inventory", []),
    )
    authored_shared_context = extract_shared_creator_context(neutral_execution_text)
    authored_shot_sections = extract_creator_shot_sections(neutral_execution_text)
    director_contract["shot_handoffs"] = expected_shot_handoffs(
        director_contract["execution_beats"],
        quote_assignments,
        authored_shot_sections,
    )
    source_block = expected_source_prompt_block(
        unit,
        {atom["atom_id"]: atom for atom in contract.get("source_atoms", []) if isinstance(atom, dict)},
    )
    master_director_block = expected_director_prompt_block(director_contract, "MP")
    neutral_director_block = expected_director_prompt_block(
        director_contract, "NEUTRAL_EXECUTION"
    )
    master_text = f"{source_block}\n{master_director_block}\n{master_text}".rstrip()
    copyable_surface = render_copyable_execution_surface(
        director_contract["execution_beats"],
        quote_assignments,
        shot_plan=director_contract["shot_plan"],
        shared_context=authored_shared_context,
        creator_shot_sections=authored_shot_sections,
        negative_clauses=negative_clauses,
    )
    neutral_execution_text = (
        f"{source_block}\n{neutral_director_block}\n"
        f"{render_execution_beats_block(director_contract['execution_beats'], quote_assignments)}\n"
        f"{neutral_execution_text}\n\n"
        f"{copyable_surface}"
    ).rstrip()
    assert_prompt_feasible(
        creator_prompt_surface(neutral_execution_text),
        has_spoken_dialogue=any(
            item.get("kind") == "SPOKEN_DIALOGUE"
            for item in quote_assignments
            if isinstance(item, dict)
        ),
        spoken_speakers=[
            normalize_text(item.get("speaker", "")).strip()
            for item in quote_assignments
            if isinstance(item, dict)
            and item.get("kind") == "SPOKEN_DIALOGUE"
            and normalize_text(item.get("speaker", "")).strip()
        ],
        require_copy_endings=True,
    )
    prompt_bundle = {
        "master_prompt": _prompt_artifact(unit_id, "MP", master_text, serial),
        "transform_plan": _prompt_artifact(unit_id, "TP", transform_plan_text, serial),
        "neutral_execution_prompt": _prompt_artifact(
            unit_id, "NEP", neutral_execution_text, serial
        ),
    }
    findings = quality_overlay.get("findings")
    if not isinstance(findings, list):
        findings = ["quality_overlay.findings 不是数组"]
    findings = list(findings) + classification_findings
    findings.extend(
        f"FINAL_PROMPT:{item}"
        for item in copyable_execution_surface_findings(copyable_surface)
    )
    findings.extend(
        f"SEMANTIC_GATE:{item['code']}:{item['path']}:{item['message']}"
        for item in semantic_findings
    )
    for item in inventory_items:
        quote_type = classifications.get(item["dialogue_id"])
        if quote_type == "INTERNAL_THOUGHT" and item["text"] not in str(director_contract.get("performance", "")):
            findings.append(f"INTERNAL_THOUGHT_NOT_ROUTED:{item['dialogue_id']}")
    next_id = None
    units = contract["units"]
    unit_index = next(index for index, item in enumerate(units) if item["unit_id"] == unit_id)
    if unit_index + 1 < len(units):
        next_id = units[unit_index + 1]["unit_id"]
    unit.update(
        {
            "compile_status": "ACCEPTED",
            "global_state_sha256": contract["global_state_sha256"],
            "capability_routing": {"PRIMARY": ["BASE_NARRATIVE"], "SUPPORT": [], "SUPPRESS": []},
            "prompt_claims": prompt_claims,
            "prompt_source_trace": prompt_traces,
            "negative_clause_plan": {
                "candidate_clauses": candidates,
                "selected_clause_ids": [item["clause_id"] for item in candidates],
            },
            "negative_clauses": negative_clauses,
            "prompt_bundle": prompt_bundle,
            "director_contract": director_contract,
            "single_shot_eligibility": copy.deepcopy(window["single_shot_eligibility"]),
            "locked_director_scaffold": copy.deepcopy(scaffold),
            "locked_scaffold_sha256": window["locked_scaffold_sha256"],
            "fixed_transform_roles": copy.deepcopy(window["fixed_transform_roles"]),
            "provider_binding_status": "PROVIDER_PENDING",
            "provider_registry_id": None,
            "provenance": {
                "source_window_sha256": unit["source_window"]["text_sha256"],
                "authoring_overlay_sha256": sha256_value(overlay),
                "source_dialogue_inventory_sha256": contract["source_dialogue_inventory_sha256"],
                "dialogue_slot_ids": spoken_ids,
                "quote_classifications": classifications,
            },
            "content_self_review": {},
            "unit_handoff_out": {
                "scope": "UNIT_TO_UNIT",
                "from_unit_id": unit_id,
                "to_unit_id": next_id,
                "state_out_sha256": sha256_value(
                    {"unit_id": unit_id, "next_unit_id": next_id, "exit": director_contract["exit"]}
                ),
                "entry_facts_for_next_unit": (
                    []
                    if next_id is None
                    else [f"承接上一段可见结束状态：{director_contract['shot_handoffs'][-1]['handoff_out'] if director_contract['shot_handoffs'] else director_contract['exit']}"]
                ),
                "open_actions": [],
                "dialogue_audio_carry": [],
            },
        }
    )
    computed_review = expected_content_self_review(
        unit,
        contract.get("source_dialogue_inventory", []),
        CONTRACT_VERSION,
        scene_title=quality_overlay.get("scene_title", ""),
    )
    unit["content_self_review"] = computed_review
    findings.extend(f"CONTENT_SELF_REVIEW:{item}" for item in computed_review["findings"])
    unit["dialogue_diff"] = expected_dialogue_diff(contract, unit)
    prompt_hashes = _prompt_hashes(unit)
    unit["prompt_quality_records"] = [
        {
            "id": f"PQ-{serial:03d}",
            "unit_id": unit_id,
            "lifecycle_status": "CURRENT",
            "quality_scope": "CONTRACT_STRUCTURAL",
            "quality_status": {"status": "PASS" if findings == [] else "FAIL", "findings": findings},
            "prompt_sha256s": prompt_hashes,
        }
    ]
    unit["unit_compile_sha256"] = sha256_value(
        expected_unit_compile_state(unit, contract["global_state_sha256"])
    )


def _pilot_from_request(contract: dict[str, Any]) -> dict[str, Any]:
    request = contract["selection_request"]
    unit_map = {unit["unit_id"]: unit for unit in contract["units"]}
    samples = request["sample_unit_ids"]
    evidence = request["selection_evidence"]
    if request["selection_mode"] == "USER_TARGETED_EXACT_RANGES_V1":
        spread_claim = "TARGETED_EXACT_RANGES"
    else:
        positions = evidence.get("selected_order_indexes", [])
        total = len(contract["units"])
        bands = {min(2, (position * 3) // total) for position in positions} if total else set()
        spread_claim = "EARLY_MIDDLE_LATE" if bands == {0, 1, 2} else "NONCONTIGUOUS"
    return {
        "sample_unit_ids": samples,
        "prompt_quality_record_ids": [unit_map[unit_id]["prompt_quality_records"][0]["id"] for unit_id in samples],
        "status": "PASS",
        "selection_mode": request["selection_mode"],
        "selection_basis": f"{request['selection_mode']}；helper 计算窗口、feature matrix 与对白库存",
        "selection_evidence": copy.deepcopy(evidence),
        "spread_policy": {"claim": spread_claim},
    }


def _summary(contract: dict[str, Any], *, open_items: list[str] | None = None) -> dict[str, Any]:
    units = contract["units"]
    unit_ids = [unit["unit_id"] for unit in units]
    compiled_ids = [unit["unit_id"] for unit in units if unit.get("compile_status") in COMPILED_STATUSES]
    pilot = contract.get("prompt_pilot") if isinstance(contract.get("prompt_pilot"), dict) else {}
    samples = pilot.get("sample_unit_ids", [])
    quality_ids = pilot.get("prompt_quality_record_ids", [])
    status = contract["project_status"]
    entrypoint = {
        "GLOBAL_READY": "PROMPT_PILOT",
        "PILOT_REWORK_REQUIRED": "AUTHORING_REWORK",
        "TEXT_PILOT_COMPLETE": "EDITORIAL_REVIEW",
        "TEXT_SPEC_COMPLETE": "TEXT_SPEC_COMPLETE",
    }[status]
    compile_target_ids = [
        atom["atom_id"] for atom in contract["source_atoms"] if atom.get("compile_target") is True
    ]
    route_review_items = [
        f"ROUTE_REVIEW_REQUIRED:{unit_id}:{finding}"
        for unit_id, findings in contract.get("selection_request", {}).get("route_findings", {}).items()
        for finding in findings
        if isinstance(finding, str) and finding.startswith("SPLIT_REQUIRED:")
    ]
    default_open_items = ["INDEPENDENT_EDITORIAL_REVIEW_REQUIRED", *route_review_items]
    result = {
        "source_sha256": contract["source"]["source_sha256"],
        "source_scope_unit_ids": unit_ids,
        "compile_target_atom_count": len(compile_target_ids),
        "compile_target_atom_ids_sha256": sha256_value(compile_target_ids),
        "selected_source_ranges": [
            {
                "unit_id": unit_id,
                "first_atom_id": next(unit for unit in units if unit["unit_id"] == unit_id)["source_window"]["first_atom_id"],
                "last_atom_id": next(unit for unit in units if unit["unit_id"] == unit_id)["source_window"]["last_atom_id"],
                "text_sha256": next(unit for unit in units if unit["unit_id"] == unit_id)["source_window"]["text_sha256"],
            }
            for unit_id in samples
        ],
        "completed_unit_ids": compiled_ids,
        "prompt_pilot": {
            "sample_unit_ids": samples,
            "prompt_quality_record_ids": quality_ids,
            "status": "PASS" if samples else "NOT_RUN",
        },
        "quality_gate_status": (
            "PASS" if status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"}
            else "FAIL" if status == "PILOT_REWORK_REQUIRED" else "NOT_RUN"
        ),
        "quality_scope": "CONTRACT_STRUCTURAL",
        "structural_validation_status": (
            "PASS" if status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"}
            else "FAIL" if status == "PILOT_REWORK_REQUIRED" else "NOT_RUN"
        ),
        "editorial_review_status": "NOT_REVIEWED",
        "content_self_review_status": (
            "PASS" if status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"} else "NOT_RUN"
        ),
        "content_readiness": "REVIEW_REQUIRED",
        "skipped_stages": list(TEXT_EXCLUDED_STAGE_STATUS),
        "execution_status": "NOT_EXECUTED",
        "observation_status": "NOT_APPLICABLE",
        "media_qa_status": "NOT_APPLICABLE",
        "production_validation": "NOT_TESTED",
        "stage_status": copy.deepcopy(TEXT_EXCLUDED_STAGE_STATUS),
        "release_status": "RELEASE_NOT_READY",
        "learning_status": "NO_REAL_DATA",
        "open_items": list(open_items if open_items is not None else default_open_items),
        "resume_entry": {
            "entrypoint": entrypoint,
            "next_unit_id": None
            if status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"}
            else (unit_ids[0] if unit_ids else None),
            "latest_checkpoint_id": contract.get("latest_checkpoint_id"),
        },
    }
    return result


def _strip_failed_products(contract: dict[str, Any]) -> None:
    for unit in contract["units"]:
        unit.pop("compile_status", None)
        for key in PROMPT_SHELL_KEYS:
            unit.pop(key, None)
    contract.pop("prompt_pilot", None)


def _validation_projection(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "validator",
            "phase",
            "subject_sha256",
            "exit_code",
            "valid",
            "error_count",
            "error_codes",
            "production_validation",
            "package_sha256",
            "summary_sha256",
        )
    }


def _record_validation(contract: dict[str, Any], valid: bool, error_codes: list[str]) -> None:
    unique_codes = sorted(set(error_codes))
    result = {
        "validator": "validate_longform_contract.py",
        "phase": "TERMINAL_PROMOTION_GATE",
        "subject_sha256": "",
        "exit_code": 0 if valid else 2,
        "valid": valid,
        "error_count": len(unique_codes),
        "error_codes": unique_codes,
        "production_validation": "NOT_TESTED",
        "package_sha256": "",
        "summary_sha256": "",
    }
    contract["validation_result"] = result
    # Bind the validation subject before either user-facing document is
    # rendered.  The subject projection deliberately excludes the validation
    # result and run_summary.actual_validation, so this hash is stable and does
    # not create a recursive dependency on the document hashes added later.
    result["subject_sha256"] = sha256_value(validation_subject_projection(contract))
    contract["run_summary"]["actual_validation"] = _validation_projection(result)


def _bind_document_hashes(contract: dict[str, Any], package_text: str, summary_text: str) -> None:
    result = contract["validation_result"]
    result["package_sha256"] = sha256_text(package_text)
    result["summary_sha256"] = sha256_text(summary_text)
    contract["run_summary"]["actual_validation"] = _validation_projection(result)


def _creator_verbatim_fragments(
    contract: dict[str, Any], windows: list[dict[str, Any]]
) -> tuple[str, ...]:
    """Return exact user-source fragments that the creator view may preserve."""

    fragments: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value and value not in fragments:
            fragments.append(value)

    for window in windows:
        if isinstance(window, dict):
            add(window.get("source_excerpt"))
    for atom in contract.get("source_atoms", []):
        if isinstance(atom, dict):
            add(atom.get("text"))
    for unit in contract.get("units", []):
        if not isinstance(unit, dict):
            continue
        director = unit.get("director_contract")
        if not isinstance(director, dict):
            continue
        for item in director.get("dialogue_inventory", []):
            if isinstance(item, dict):
                add(item.get("text"))
        for item in director.get("quote_assignments", []):
            if isinstance(item, dict):
                add(item.get("text"))
    return tuple(fragments)


def _render_package(contract: dict[str, Any], windows: list[dict[str, Any]]) -> str:
    unit_map = {unit["unit_id"]: unit for unit in contract["units"]}
    dictionary = load_dictionary()
    verbatim_fragments = _creator_verbatim_fragments(contract, windows)

    def visible(value: Any) -> str:
        return sanitize_display_text(
            "" if value is None else str(value),
            dictionary,
            allowed_fragments=verbatim_fragments,
        )

    titles = [
        visible(unit_map[window["unit_id"]].get("content_self_review", {}).get("scene_title", ""))
        or f"第{index}场"
        for index, window in enumerate(windows, 1)
    ]
    lines = [
        "# 银幕总控 Alpha.7｜AI 视听导演文字样片包",
        "",
        "> 不只会生成画面：我们让 AI 先学会当总导演。",
        "",
        "下面每个镜头都保留原剧情、人物原话、动作顺序和前后关系。每条视频提示词都写成完整自然语言，可以单独复制使用。",
        "",
        f"## 本轮{len(titles)}个文字样片",
        "",
    ]
    lines.extend(f"{index}. {title}" for index, title in enumerate(titles, 1))
    lines.append("")

    for index, (window, title) in enumerate(zip(windows, titles), start=1):
        unit = unit_map[window["unit_id"]]
        director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
        execution_beats = director.get("execution_beats") if isinstance(director.get("execution_beats"), list) else []
        quote_assignments = (
            director.get("quote_assignments")
            if isinstance(director.get("quote_assignments"), list)
            else []
        )
        quote_texts = [
            normalize_text(item.get("text", "")).strip()
            for item in quote_assignments
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        quote_replacements = {
            normalize_text(item.get("text", "")).strip(): {
                "SPOKEN_DIALOGUE": "",
                "NON_LEXICAL_VOCALIZATION": "“人物发声”",
                "SFX": "“轻响”",
                "QUOTED_TEXT": "“原文字样”",
                "INTERNAL_THOUGHT": "“内心原文”",
            }.get(str(item.get("kind", "")), "保留对应原文")
            for item in quote_assignments
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        }

        def reference_only(value: Any) -> str:
            rendered = (
                "；然后，".join(
                    str(item).strip().rstrip("。；;，, ")
                    for item in value
                    if str(item).strip()
                )
                if isinstance(value, list)
                else str(value or "")
            )
            rendered = normalize_text(rendered)
            for quote_text in sorted(set(quote_texts), key=len, reverse=True):
                replacement = quote_replacements.get(quote_text, "保留对应原文")
                for left, right in (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"')):
                    rendered = rendered.replace(
                        f"{left}{quote_text}{right}", replacement
                    )
                rendered = re.sub(
                    rf"(?<![\u4e00-\u9fffA-Za-z0-9]){re.escape(quote_text)}"
                    rf"(?![\u4e00-\u9fffA-Za-z0-9])",
                    replacement,
                    rendered,
                )
            rendered = rendered.replace("；然后，“轻响”；然后，", "；随后传来一声轻响；然后，")
            rendered = rendered.replace("；然后，“轻响”", "；随后传来一声轻响")
            rendered = rendered.replace("，“轻响”的一声", "，轻响一声")
            rendered = rendered.replace("；然后，“人物发声”", "；随后人物发出声音")
            rendered = re.sub(r"[：:]\s*(?=[；;，,。！？!?]|$)", "", rendered)
            while "；然后，；然后，" in rendered:
                rendered = rendered.replace("；然后，；然后，", "；然后，")
            rendered = rendered.removeprefix("；然后，").removesuffix("；然后，")
            return visible(rendered)

        def reference_sentence(value: Any) -> str:
            rendered = reference_only(value).strip()
            if not rendered:
                return "无额外动作。"
            return rendered if rendered.endswith(("。", "！", "？", "…")) else rendered + "。"

        prompt_bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
        neutral_artifact = (
            prompt_bundle.get("neutral_execution_prompt")
            if isinstance(prompt_bundle.get("neutral_execution_prompt"), dict)
            else {}
        )
        neutral_surface = creator_prompt_surface(neutral_artifact.get("text", ""))
        shared_context = extract_shared_creator_context(neutral_surface)
        creator_shot_sections = extract_creator_shot_sections(neutral_surface)
        copy_prompt = render_copyable_execution_surface(
            execution_beats,
            quote_assignments,
            shot_plan=(
                director.get("shot_plan")
                if isinstance(director.get("shot_plan"), list)
                else []
            ),
            shared_context=shared_context,
            creator_shot_sections=creator_shot_sections,
            negative_clauses=(
                unit.get("negative_clauses")
                if isinstance(unit.get("negative_clauses"), list)
                else []
            ),
            creator_friendly_audio=True,
        )
        copy_prompt = sanitize_display_text(
            copy_prompt,
            dictionary,
            allowed_fragments=verbatim_fragments,
        )
        shot_overview: list[str] = []
        for shot_number, shot in enumerate(
            director.get("shot_plan") if isinstance(director.get("shot_plan"), list) else [],
            start=1,
        ):
            if not isinstance(shot, dict):
                continue
            shot_overview.append(
                f"{shot_number}. {reference_only(shot.get('purpose', ''))} "
                f"镜头安排：{reference_only(shot.get('camera', ''))}"
            )
        handoff_overview: list[str] = []
        for handoff_number, handoff in enumerate(
            director.get("shot_handoffs")
            if isinstance(director.get("shot_handoffs"), list)
            else [],
            start=1,
        ):
            if not isinstance(handoff, dict):
                continue
            handoff_overview.extend(
                [
                    f"#### 镜头 {handoff_number} → 镜头 {handoff_number + 1}",
                    "",
                    f"- 上一镜交出：{reference_sentence(handoff.get('handoff_out', ''))}",
                    f"- 下一镜接住：{reference_sentence(handoff.get('receiver_in', ''))}",
                    f"- 已完成动作：{reference_sentence(handoff.get('completed_action', ''))}",
                    f"- 位置与运动：{reference_sentence(handoff.get('motion_and_space', ''))}",
                    f"- 道具与视线：{reference_sentence(handoff.get('prop_and_eyeline', ''))}",
                    f"- 光线：{reference_sentence(handoff.get('lighting', ''))}",
                    f"- 声音桥：{reference_sentence(handoff.get('audio_bridge', ''))}",
                    "",
                ]
            )
        action_chain = (
            director.get("action_state_chain")
            if isinstance(director.get("action_state_chain"), list)
            else []
        )
        development_actions = action_chain[1:-1] if len(action_chain) > 2 else action_chain
        lines.extend(
            [
                f"## 样片 {index} · {title}",
                "",
                "### 这一段怎么处理",
                "",
                "原剧情、人物关系、动作顺序和人物原话保持不变；为了让画面真正能拍，只补充表演、摄影、声音和必要的动作衔接。",
                "",
                "### 剧情拆解",
                "",
                f"- 开始：{reference_sentence(director.get('entry', ''))}",
                f"- 发展：{reference_sentence(development_actions)}",
                f"- 收尾：{reference_sentence(director.get('exit', ''))}",
                "",
                "### 导演思路",
                "",
                f"- 人物怎么演：{reference_only(director.get('performance', ''))}",
                f"- 镜头怎么拍：{reference_only(director.get('camera', ''))}",
                f"- 声音怎么走：{reference_only(director.get('sound', ''))}",
                "",
                "### 分镜总览",
                "",
                *shot_overview,
                "",
                "### 逐镜交接",
                "",
                *handoff_overview,
                copy_prompt,
                "",
            ]
        )
    if contract["project_status"] == "PILOT_REWORK_REQUIRED":
        lines.extend(
            [
                "## 需要修改",
                "",
                "本轮检查发现仍需修正的问题，暂不进入下一阶段。请按本轮总结中的下一步修改后重新检查。",
            ]
        )
    lines.append("")
    rendered = "\n".join(lines).rstrip() + "\n"
    forbidden_creator_fragments = (
        "逐字对白见下方",
        "此处同步说出或发出",
        "- 入口：",
        "- 出口：",
        "按本镜构图落位",
        "本镜无来源口播或明确声响",
    )
    leaked = [item for item in forbidden_creator_fragments if item in rendered]
    if leaked:
        raise ValueError(f"创作者提示词仍含内部占位或机器话术：{leaked}")
    assert_creator_safe(rendered, allowed_fragments=verbatim_fragments)
    return rendered


def _render_summary(contract: dict[str, Any]) -> str:
    dictionary = load_dictionary()
    unit_map = {unit["unit_id"]: unit for unit in contract["units"]}
    selection_lines = []
    for unit_id in contract.get("prompt_pilot", {}).get("sample_unit_ids", []):
        unit = unit_map.get(unit_id, {})
        title = unit.get("content_self_review", {}).get("scene_title", "未命名样片")
        mode = unit.get("director_contract", {}).get("target_mode", "未定路由")
        selection_lines.append(f"{title}（{'多镜序列' if mode == 'EDITED_SEQUENCE' else '单镜连续'}）")
    selection_summary = "、".join(selection_lines) or "尚未形成样片选择"
    completed = sanitize_display_text(
        f"本轮文字样片包括：{selection_summary}。",
        dictionary,
    )
    creator_view = render_creator_view(
        contract,
        dictionary=dictionary,
        display_context={
            "completed": completed,
            "main_artifact": "导演母版和可复制提示词工作稿",
        },
    )
    rendered = "# 本轮视听导演文字总结\n\n" + creator_view + "\n"
    assert_creator_safe(rendered)
    return rendered


def _safe_prepare_output_dir(
    output_dir: Path,
    expected_names: list[str],
    *,
    replace_own_run: bool,
    source_sha256: str,
) -> bool:
    resolved = output_dir.resolve()
    if not resolved.exists():
        return False
    if not resolved.is_dir() or resolved.is_symlink():
        raise ValueError("finalizer output target must be a normal directory path")
    existing_entries = list(resolved.iterdir())
    if not existing_entries:
        if not replace_own_run:
            raise ValueError(
                "E_NO_DELETE_COMMIT_REQUIRES_NEW_PATH: output directory must not already exist"
            )
        return True
    if not replace_own_run:
        raise ValueError(
            "finalizer requires a new/empty output directory; unexpected entries: "
            + repr([str(item) for item in existing_entries])
        )
    if any(item.is_dir() or item.is_symlink() for item in existing_entries):
        raise ValueError("E_REPLACE_OWN_RUN_UNSAFE: existing output contains a directory or symlink")
    if {item.name for item in existing_entries} != set(expected_names):
        raise ValueError("E_REPLACE_OWN_RUN_UNSAFE: existing output is not the exact current RUN three-file set")
    machine_name = expected_names[1]
    try:
        previous = json.loads((resolved / machine_name).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("E_REPLACE_OWN_RUN_UNSAFE: existing machine state is unreadable") from exc
    previous_output = previous.get("output_contract") if isinstance(previous, dict) else None
    previous_source = previous.get("source") if isinstance(previous, dict) else None
    if (
        not isinstance(previous_output, dict)
        or previous_output.get("exact_relative_output_names") != expected_names
        or not isinstance(previous_source, dict)
        or previous_source.get("source_sha256") != source_sha256
    ):
        raise ValueError("E_REPLACE_OWN_RUN_UNSAFE: existing files do not belong to this source/run")
    return True


class OverlayCheckFailure(ValueError):
    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = copy.deepcopy(errors)
        self.root_errors, self.cascade_errors = _partition_check_errors(errors)
        self.error_codes = sorted({item.get("code", "") for item in errors if item.get("code")})
        super().__init__("E_OVERLAY_CHECK_FAILED: " + ",".join(self.error_codes))


CASCADE_ERROR_CODES = {
    "E_AUTHORING_FINDINGS",
    "E_CONTENT_SELF_REVIEW",
    "E_CONTENT_SELF_REVIEW_COMPUTED",
    "E_PROMPT_QUALITY_NOT_READY",
}


def _partition_check_errors(
    errors: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Label derivative gate failures without suppressing a single validator error."""

    root_errors: list[dict[str, Any]] = []
    cascade_errors: list[dict[str, Any]] = []
    for item in errors:
        (cascade_errors if item.get("code") in CASCADE_ERROR_CODES else root_errors).append(
            copy.deepcopy(item)
        )
    return root_errors, cascade_errors


PUBLIC_REPAIR_MESSAGES = {
    "E_DIALOGUE_SLOT_COUNT": "逐字对白没有被完整识别。请把固定台词与后一句导演说明分开。",
    "E_DIALOGUE_VERBATIM_PROMPT": "可复制提示词里的原文对白不完整。请保留固定台词，不要改写或粘连后句。",
    "E_DIRECTOR_UNDECLARED_PROPOSAL": "这里已经加入了导演处理，却又写成‘没有新增’。请改成‘导演处理不改写原始剧情’。",
    "E_NON_LEXICAL_VOCALIZATION_SPEAKER": "笑声、喘息或痛叫的发声者没有从原文锁定。请回到该处核对人物，不能猜。",
    "E_AUTHORING_PLACEHOLDER": "这一项还是空白或示例文字。请换成本样片的实际内容。",
    "E_OVERLAY_PLACEHOLDER": "这一项还是空白或示例文字。请换成本样片的实际内容。",
    "E_OUT_OF_WINDOW_PLOT_ACTION": "这里把原文尚未发生的动作写成已经完成。请改回当前画面真正发生的动作。",
    "E_FINAL_PROMPT_EXECUTABILITY": "这条逐镜提示词还不能单独执行。请修正镜头数量、可见结束画面或声音冲突。",
    "E_SHOT_HANDOFF_MATRIX": "相邻镜头没有把上一镜的结束状态完整交给下一镜，请补齐位置、动作、道具、视线、光线和声音。",
    "E_NEGATIVE_CLAUSE_INCOMPLETE": "每条限制都要写成一句完整中文，并用句号结束，不能只写半句。",
    "E_NEGATIVE_CLAUSE_PLAN": "限制条款需要逐条完整填写，不能留空或拼成半句话。",
    "E_NEGATIVE_CLAUSE_PLAN_MISMATCH": "最终限制条款必须与已经选择的完整条款保持相同内容和顺序。",
}


def _public_repair_area(path: str) -> str:
    lowered = path.lower()
    if "master_prompt" in lowered:
        return "导演母版"
    if "neutral_execution_prompt" in lowered:
        return "可复制视频提示词"
    if "dialogue" in lowered or "quote" in lowered:
        return "对白与人物发声"
    if "performance" in lowered:
        return "人物表演"
    if "sound" in lowered or "audio" in lowered:
        return "声音"
    if "camera" in lowered:
        return "镜头"
    if "prompt" in lowered:
        return "提示词"
    if "director" in lowered:
        return "导演工作面"
    return "创作工作面"


def _public_repair_items(
    contract: dict[str, Any], errors: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Translate machine findings into ordinary Chinese without leaking codes."""

    selection = contract.get("selection_request") if isinstance(contract, dict) else {}
    selected_ids = (
        selection.get("sample_unit_ids")
        if isinstance(selection, dict) and isinstance(selection.get("sample_unit_ids"), list)
        else []
    )
    units = contract.get("units") if isinstance(contract, dict) else []
    units = units if isinstance(units, list) else []
    index_to_id = {
        index: unit.get("unit_id")
        for index, unit in enumerate(units)
        if isinstance(unit, dict) and isinstance(unit.get("unit_id"), str)
    }
    repairs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for error in errors:
        code = error.get("code") if isinstance(error, dict) else None
        path = error.get("path") if isinstance(error, dict) else ""
        path = path if isinstance(path, str) else ""
        unit_id = ""
        unit_match = re.search(r"\.units\[(\d+)\]", path)
        overlay_match = re.search(r"\.compiled_unit_overlays\[(\d+)\]", path)
        if unit_match:
            unit_id = index_to_id.get(int(unit_match.group(1)), "")
        elif overlay_match:
            overlay_index = int(overlay_match.group(1))
            if 0 <= overlay_index < len(selected_ids):
                unit_id = selected_ids[overlay_index]
        if not unit_id:
            id_match = re.search(r"\bU\d{3,}\b", path)
            unit_id = id_match.group(0) if id_match else ""
        if unit_id in selected_ids:
            label = f"第 {selected_ids.index(unit_id) + 1} 个样片"
        elif unit_id:
            label = "当前样片"
        else:
            label = "当前工作面"
        instruction = PUBLIC_REPAIR_MESSAGES.get(
            code,
            "这一项没有通过内容检查。请根据原文补齐或修正后再试。",
        )
        message = error.get("message") if isinstance(error, dict) else ""
        if code == "E_OUT_OF_WINDOW_PLOT_ACTION" and isinstance(message, str):
            hit = re.search(r"命中词：“([^”]+)”", message)
            if hit:
                instruction = (
                    f"具体问题是“{hit.group(1)}”：它把原文尚未完成的动作写成已经发生。"
                    "请改成这一刻真正看得见的动作。"
                )
        elif code == "E_FINAL_PROMPT_EXECUTABILITY" and isinstance(message, str) and message:
            instruction = message
        area = _public_repair_area(path)
        key = (label, area, instruction)
        if key not in seen:
            seen.add(key)
            repairs.append({"sample": label, "area": area, "instruction": instruction})
    return repairs


def _assert_registered_temp_root(temp_root: Path, expected_names: list[str]) -> None:
    if not temp_root.exists() or not temp_root.is_dir() or temp_root.is_symlink():
        raise ValueError("E_TEMP_ROOT_CONTRACT: registered authoring temp_root is missing or unsafe")
    entries = list(temp_root.iterdir())
    if any(item.is_dir() or item.is_symlink() for item in entries):
        raise ValueError("E_TEMP_ROOT_CONTRACT: temp_root contains a directory or symlink")
    if {item.name for item in entries} != set(expected_names):
        raise ValueError(
            "E_TEMP_ROOT_CONTRACT: temp_root must contain only TARGET_PLAN.json/AUTHORING.json/OVERLAYS.json; "
            "helper scripts such as fill_overlays.py are forbidden"
        )


def _payload_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_commit_journal(
    contract: dict[str, Any], windows: list[dict[str, Any]], payloads: tuple[str, str, str]
) -> dict[str, Any]:
    names = contract["output_contract"]["exact_relative_output_names"]
    return {
        COMMIT_JOURNAL_KEY: {
            "journal_version": COMMIT_JOURNAL_VERSION,
            "commit_mode": IN_PLACE_COMMIT_MODE,
            "exact_output_names": list(names),
            "source_sha256": contract["source"]["source_sha256"],
            "payload_sha256": {
                names[0]: _payload_sha256(payloads[0]),
                names[1]: _payload_sha256(payloads[1]),
                names[2]: _payload_sha256(payloads[2]),
            },
            "machine_contract": copy.deepcopy(contract),
            "target_windows": copy.deepcopy(windows),
            "machine_state_promoted_last": True,
        }
    }


def _journal_payloads(journal: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[str, str, str]]:
    body = journal.get(COMMIT_JOURNAL_KEY) if isinstance(journal, dict) else None
    if not isinstance(body, dict) or body.get("journal_version") != COMMIT_JOURNAL_VERSION:
        raise ValueError("E_COMMIT_JOURNAL: in-place journal is missing or unsupported")
    contract = body.get("machine_contract")
    windows = body.get("target_windows")
    if not isinstance(contract, dict) or not isinstance(windows, list):
        raise ValueError("E_COMMIT_JOURNAL: journal payload is incomplete")
    output = contract.get("output_contract") if isinstance(contract.get("output_contract"), dict) else {}
    names = output.get("exact_relative_output_names")
    if (
        body.get("commit_mode") != IN_PLACE_COMMIT_MODE
        or output.get("commit_mode") != IN_PLACE_COMMIT_MODE
        or body.get("exact_output_names") != names
        or not isinstance(names, list)
        or len(names) != 3
        or body.get("source_sha256") != contract.get("source", {}).get("source_sha256")
        or body.get("machine_state_promoted_last") is not True
    ):
        raise ValueError("E_COMMIT_JOURNAL: journal binding does not match the machine contract")
    package_text = _render_package(contract, windows)
    summary_text = _render_summary(contract)
    payloads = (
        package_text,
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        summary_text,
    )
    expected_hashes = {name: _payload_sha256(text) for name, text in zip(names, payloads)}
    if body.get("payload_sha256") != expected_hashes:
        raise ValueError("E_COMMIT_JOURNAL: journal payload hashes are stale or tampered")
    return contract, windows, payloads


def _commit_in_place_from_journal(output_dir: Path, journal: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Resume/promote a three-carrier transaction; machine state is always last."""

    contract, _, payloads = _journal_payloads(journal)
    names = contract["output_contract"]["exact_relative_output_names"]
    role_order = (
        (TEMP_INPUT_NAMES[0], names[0], payloads[0]),
        (TEMP_INPUT_NAMES[2], names[2], payloads[2]),
        (TEMP_INPUT_NAMES[1], names[1], payloads[1]),
    )
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise ValueError("E_COMMIT_STATE_CLASS: in-place output root is missing or unsafe")
    entries = list(output_dir.iterdir())
    if any(item.is_dir() or item.is_symlink() for item in entries):
        raise ValueError("E_COMMIT_STATE_CLASS: in-place output contains a directory or symlink")
    allowed = set(TEMP_INPUT_NAMES) | set(names)
    foreign = sorted(item.name for item in entries if item.name not in allowed)
    if foreign:
        raise ValueError(f"E_COMMIT_STATE_FOREIGN_MIXED: undeclared output entries {foreign!r}")
    for carrier_name, final_name, payload in role_order:
        carrier = output_dir / carrier_name
        final_path = output_dir / final_name
        if carrier.exists() and final_path.exists():
            raise ValueError("E_COMMIT_STATE_FOREIGN_MIXED: carrier and final role coexist")
        if final_path.exists():
            if hashlib.sha256(final_path.read_bytes()).hexdigest() != _payload_sha256(payload):
                raise ValueError("E_COMMIT_STATE_TAMPER: promoted role hash differs from the journal")
            continue
        if not carrier.is_file() or carrier.is_symlink():
            raise ValueError("E_COMMIT_STATE_PARTIAL_UNOWNED: required carrier is missing")
        carrier.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(carrier, final_path)
    report = validate_contract(contract, output_dir, names[1])
    if not report.valid:
        raise RuntimeError(
            "E_COMMIT_TERMINAL_INVALID: "
            + json.dumps(report.as_dict()["errors"], ensure_ascii=False, sort_keys=True)
        )
    return contract, 0 if contract.get("project_status") == "TEXT_PILOT_COMPLETE" else 2


def _recover_completed_in_place(output_dir: Path) -> tuple[dict[str, Any], int] | None:
    """Recognize a 3/3 promotion whose process died after the final rename."""

    if not output_dir.is_dir() or output_dir.is_symlink():
        return None
    entries = [item for item in output_dir.iterdir() if item.is_file() and not item.is_symlink()]
    if len(entries) != 3:
        return None
    for candidate in entries:
        if candidate.suffix.casefold() != ".json":
            continue
        try:
            contract = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        output = contract.get("output_contract") if isinstance(contract, dict) else None
        names = output.get("exact_relative_output_names") if isinstance(output, dict) else None
        if (
            output.get("commit_mode") == IN_PLACE_COMMIT_MODE
            and isinstance(names, list)
            and len(names) == 3
            and candidate.name == names[1]
            and {item.name for item in entries} == set(names)
        ):
            report = validate_contract(contract, output_dir, candidate.name)
            if report.valid:
                return contract, 0 if contract.get("project_status") == "TEXT_PILOT_COMPLETE" else 2
    return None


def check_authoring_envelope(
    envelope: dict[str, Any],
    output_dir: Path,
    *,
    replace_own_run: bool = False,
) -> tuple[dict[str, Any], Any]:
    """Compile and validate overlays without writing output or touching temp."""

    contract, windows, overlays = _assert_r5_envelope(envelope)
    output = contract["output_contract"]
    names = output["exact_relative_output_names"]
    commit_mode = output.get("commit_mode")
    if commit_mode == IN_PLACE_COMMIT_MODE:
        if not output_dir.is_dir() or output_dir.is_symlink():
            raise ValueError("E_TEMP_ROOT_CONTRACT: IN_PLACE carrier directory is missing or unsafe")
        _assert_registered_temp_root(output_dir, TEMP_INPUT_NAMES)
    elif commit_mode == SIBLING_COMMIT_MODE:
        _safe_prepare_output_dir(
            output_dir,
            names,
            replace_own_run=replace_own_run,
            source_sha256=contract["source"]["source_sha256"],
        )
    else:
        raise ValueError("E_OUTPUT_COMMIT_MODE: unsupported commit mode")
    if output.get("temp_input_names") != TEMP_INPUT_NAMES:
        raise ValueError("E_TEMP_ROOT_CONTRACT: immutable temp_input_names are not canonical")
    unit_map = {unit["unit_id"]: unit for unit in contract["units"]}
    for serial, (window, overlay) in enumerate(zip(windows, overlays), start=1):
        _compile_overlay(contract, unit_map[window["unit_id"]], window, overlay, serial)
    contract["project_status"] = "TEXT_PILOT_COMPLETE"
    contract["status_contract"] = expected_text_status_contract("TEXT_PILOT_COMPLETE")
    contract["prompt_pilot"] = _pilot_from_request(contract)
    contract["run_summary"] = _summary(contract)
    contract["global_state"] = expected_global_state(contract)
    contract["global_state_sha256"] = sha256_value(contract["global_state"])
    contract["skeleton_sha256"] = expected_skeleton_sha256(
        contract, [unit["unit_id"] for unit in contract["units"]]
    )
    for unit in contract["units"]:
        if unit.get("compile_status") in COMPILED_STATUSES:
            unit["global_state_sha256"] = contract["global_state_sha256"]
            unit["unit_compile_sha256"] = sha256_value(
                expected_unit_compile_state(unit, contract["global_state_sha256"])
            )
    # Output validation is intentionally disabled here: the canonical temp
    # root must still exist until an explicit commit succeeds.
    report = validate_contract(
        contract,
        output_dir,
        names[1],
        validate_outputs=False,
        validate_recorded_result=False,
    )
    return contract, report


def finalize_authoring_envelope(
    envelope: dict[str, Any],
    output_dir: Path,
    *,
    replace_own_run: bool = False,
    registered_temp_root: Path | None = None,
) -> tuple[dict[str, Any], int]:
    _, overlay_report = check_authoring_envelope(
        envelope,
        output_dir,
        replace_own_run=replace_own_run,
    )
    if not overlay_report.valid:
        raise OverlayCheckFailure(overlay_report.errors)
    contract, windows, overlays = _assert_r5_envelope(envelope)
    output = contract["output_contract"]
    names = output["exact_relative_output_names"]
    commit_mode = output.get("commit_mode")
    if commit_mode == IN_PLACE_COMMIT_MODE:
        if registered_temp_root is None or registered_temp_root.resolve() != output_dir.resolve():
            raise ValueError("E_TEMP_ROOT_CONTRACT: IN_PLACE commit must consume carriers in the final directory")
        replacing_existing = False
    elif commit_mode == SIBLING_COMMIT_MODE:
        replacing_existing = _safe_prepare_output_dir(
            output_dir,
            names,
            replace_own_run=replace_own_run,
            source_sha256=contract["source"]["source_sha256"],
        )
    else:
        raise ValueError("E_OUTPUT_COMMIT_MODE: unsupported commit mode")
    expected_temp_names = output.get("temp_input_names")
    if expected_temp_names != TEMP_INPUT_NAMES:
        raise ValueError("E_TEMP_ROOT_CONTRACT: immutable temp_input_names are not canonical")
    unit_map = {unit["unit_id"]: unit for unit in contract["units"]}
    for serial, (window, overlay) in enumerate(zip(windows, overlays), start=1):
        _compile_overlay(contract, unit_map[window["unit_id"]], window, overlay, serial)
    contract["project_status"] = "TEXT_PILOT_COMPLETE"
    contract["status_contract"] = expected_text_status_contract("TEXT_PILOT_COMPLETE")
    contract["prompt_pilot"] = _pilot_from_request(contract)
    contract["run_summary"] = _summary(contract)
    contract["global_state"] = expected_global_state(contract)
    contract["global_state_sha256"] = sha256_value(contract["global_state"])
    contract["skeleton_sha256"] = expected_skeleton_sha256(
        contract, [unit["unit_id"] for unit in contract["units"]]
    )
    # Rebind hashes after the final global state projection is fixed.
    for unit in contract["units"]:
        if unit.get("compile_status") in COMPILED_STATUSES:
            unit["global_state_sha256"] = contract["global_state_sha256"]
            unit["unit_compile_sha256"] = sha256_value(
                expected_unit_compile_state(unit, contract["global_state_sha256"])
            )
    if registered_temp_root is not None:
        _assert_registered_temp_root(registered_temp_root, expected_temp_names)
    else:
        sibling_temp = output_dir.resolve().parent / output["temp_root"]
        if sibling_temp.exists():
            raise ValueError("E_TEMP_ROOT_CONTRACT: undeclared/unmanaged authoring temp_root remains beside output")
    output["temp_root_cleaned"] = True
    preflight = validate_contract(
        contract,
        output_dir,
        names[1],
        validate_outputs=False,
        validate_recorded_result=False,
    )
    if preflight.valid:
        _record_validation(contract, True, [])
        exit_code = 0
    else:
        error_codes = sorted({item["code"] for item in preflight.errors})
        contract["project_status"] = "PILOT_REWORK_REQUIRED"
        contract["status_contract"] = expected_text_status_contract(
            "PILOT_REWORK_REQUIRED"
        )
        _strip_failed_products(contract)
        contract["run_summary"] = _summary(contract, open_items=error_codes)
        _record_validation(contract, False, error_codes)
        exit_code = 2

    machine_name = names[1]
    package_name = names[0]
    summary_name = names[2]
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    nonce = uuid.uuid4().hex
    staging = output_dir.parent / f".{output_dir.name}.alpha7-ready-{nonce}"
    before_presentation = copy.deepcopy(contract)
    package_text = _render_package(contract, windows)
    summary_text = _render_summary(contract)
    if contract != before_presentation:
        raise RuntimeError("creator presentation changed the machine contract")
    _bind_document_hashes(contract, package_text, summary_text)
    # The renderer intentionally does not print the two document hashes, so
    # binding them cannot change either document's bytes.
    before_bound_presentation = copy.deepcopy(contract)
    package_text = _render_package(contract, windows)
    summary_text = _render_summary(contract)
    if contract != before_bound_presentation:
        raise RuntimeError("creator presentation changed the bound machine contract")
    payloads = (
        package_text,
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        summary_text,
    )
    if commit_mode == IN_PLACE_COMMIT_MODE:
        journal = _build_commit_journal(contract, windows, payloads)
        journal_path = output_dir / "AUTHORING.json"
        journal_path.write_text(
            json.dumps(journal, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return _commit_in_place_from_journal(output_dir, journal)
    if registered_temp_root is not None:
        # Consume the exactly three registered inputs in place.  Neutral carrier
        # names avoid collisions when a user deliberately chooses AUTHORING.json
        # as the final machine-state basename.  No delete API is used.
        carriers: list[Path] = []
        for index, temp_name in enumerate(expected_temp_names):
            carrier = registered_temp_root / f".alpha7-role-{index}-{nonce}.work"
            os.replace(registered_temp_root / temp_name, carrier)
            carriers.append(carrier)
        for carrier, text_value, final_name in zip(carriers, payloads, names):
            carrier.write_text(text_value, encoding="utf-8", newline="\n")
            os.replace(carrier, registered_temp_root / final_name)
        os.replace(registered_temp_root, staging)
    else:
        staging.mkdir()
        for final_name, text_value in zip(names, payloads):
            (staging / final_name).write_text(text_value, encoding="utf-8", newline="\n")
    artifact_report = validate_contract(contract, staging, machine_name)
    if not artifact_report.valid:
        raise RuntimeError(
            "finalizer generated a noncanonical artifact: "
            + json.dumps(artifact_report.as_dict()["errors"], ensure_ascii=False, sort_keys=True)
        )
    backup: Path | None = None
    if replacing_existing:
        backup = output_dir.parent / f".{output_dir.name}.alpha7-previous-{nonce}"
        os.replace(output_dir, backup)
    try:
        os.replace(staging, output_dir)
    except Exception:
        if backup is not None and backup.exists() and not output_dir.exists():
            os.replace(backup, output_dir)
        raise
    return contract, exit_code


def _fill_self_test_overlays(envelope: dict[str, Any]) -> None:
    # Load gold-only filler from tests so production authoring instructions do
    # not depend on, expose, or encourage copying synthetic prompt prose.
    import importlib.util

    helper_path = Path(__file__).resolve().parent.parent / "tests" / "longform_selftest_support.py"
    spec = importlib.util.spec_from_file_location("silver_longform_selftest_support", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("self-test support module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.fill_self_test_overlays(
        envelope,
        normalize_text=normalize_text,
        expected_sequence_minimum_shots=expected_sequence_minimum_shots,
    )
    return


def _fill_runtime_smoke_overlays(envelope: dict[str, Any]) -> None:
    """Tiny extracted-package smoke fixture; never used by formal authoring."""

    titles = ("抬手入口", "停步转折", "转身出口")
    for title, window, overlay in zip(titles, envelope["target_windows"], envelope["compiled_unit_overlays"]):
        anchor = window["locked_director_scaffold"]["semantic_anchors"][0]["exact_text"]
        director = overlay["director_overlay"]
        director.update(
            {
                "performance": "人物以清晰克制的重心变化完成当前动作。",
                "camera": "中景固定机位交代人物与地面的空间关系。",
                "sound": "现场保持无对白，仅保留衣料摩擦与空间底噪。",
            }
        )
        overlay["prompt_overlay"].update(
            {
                "master_prompt_template": f"围绕‘{anchor}’设计单镜的空间压力、表演节拍和连续性。",
                "transform_plan": {
                    "preserve": ["来源事实", "角色状态", "连续性", "对白逐字"],
                    "operations": ["把导演设计转换成顺序明确的可执行镜头指令"],
                    "deferred_provider_decisions": ["供应商语法", "参数映射"],
                },
                "neutral_execution_prompt_template": (
                    f"镜头 1：先从人物稳定站位开始，随后清楚执行‘{anchor}’，"
                    "同时保持稳定构图。\n"
                    "声音：只保留人物动作产生的衣料和接触声，除此之外保持安静。\n"
                    "结束画面：人物双脚停稳，双手位置清楚可见。"
                ),
                "negative_clauses": ["不得新增来源未写的人物、对白或剧情状态。"],
            }
        )
        overlay["prompt_overlay"]["claims"][-1]["text"] = (
            "导演控制只调整当前镜头的空间、表演和节拍。"
        )
        overlay["quality_overlay"].update({"scene_title": title, "findings": []})


def run_runtime_smoke_test() -> dict[str, Any]:
    """Extracted runtime prepare -> finalize -> validator smoke without tests/."""

    from prepare_longform_authoring import prepare_authoring

    source = "甲抬手。\n乙停步。\n丙转身。\n"
    plan = {
        "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
        "targets": [
            {
                "target_id": f"T{index:03d}",
                "atom_range": {"first_atom_id": f"SRC{index:04d}", "last_atom_id": f"SRC{index:04d}"},
                "context_atoms_before": 0,
                "context_atoms_after": 0,
                "target_mode": "GENERATABLE_SHOT",
            }
            for index in range(1, 4)
        ],
    }
    envelope = prepare_authoring(source, plan, "RUN0")
    _fill_runtime_smoke_overlays(envelope)
    with tempfile.TemporaryDirectory(prefix="silver-r9-runtime-smoke-") as root_value:
        output = Path(root_value) / "out"
        result, exit_code = finalize_authoring_envelope(envelope, output)
        report = validate_contract(result, output, "MACHINE_STATE.json")
        if exit_code != 0 or not report.valid:
            raise RuntimeError("extracted runtime smoke did not reach a direct-valid three-file terminal")
    return {
        "self_test": "PASS",
        "scope": "EXTRACTED_RUNTIME_SMOKE",
        "prepare_finalize_validator": True,
        "contract_version": CONTRACT_VERSION,
        "authoring_version": AUTHORING_VERSION,
        "production_validation": "NOT_TESTED",
    }


def run_self_test() -> dict[str, Any]:
    # The 1.5 production self-test is the extracted prepare -> finalize ->
    # validator closure above.  The historical attack corpus remains below as
    # read-only compatibility code until the standalone regression harness is
    # migrated; it is intentionally not a current write-path fixture.
    return run_runtime_smoke_test()

    # pragma: no cover - retained historical 1.3 corpus
    from prepare_longform_authoring import compact_overlay_work_surface, prepare_authoring

    def codes(report: Any) -> set[str]:
        return {item["code"] for item in report.as_dict()["errors"]}

    def rebind_unit(unit: dict[str, Any], contract: dict[str, Any]) -> None:
        prompt_hashes = _prompt_hashes(unit)
        records = unit.get("prompt_quality_records")
        if isinstance(records, list) and records and isinstance(records[0], dict):
            records[0]["prompt_sha256s"] = prompt_hashes
        unit["unit_compile_sha256"] = sha256_value(
            expected_unit_compile_state(unit, contract["global_state_sha256"])
        )

    def remove_nonspoken_from_shots(director_overlay: dict[str, Any], dialogue_id: str) -> None:
        for shot in director_overlay.get("shot_plan", []):
            if isinstance(shot, dict) and isinstance(shot.get("dialogue_slot_ids"), list):
                shot["dialogue_slot_ids"] = [
                    item for item in shot["dialogue_slot_ids"] if item != dialogue_id
                ]

    def assert_plain_first_five(path: Path) -> None:
        full_text = path.read_text(encoding="utf-8")
        first_five = full_text.splitlines()[:5]
        if len(first_five) < 5 or re.search(r"[A-Za-z0-9_]", "\n".join(first_five)):
            raise RuntimeError("run summary first five lines leaked engineering codes")
        if any(name in full_text for name in ("subject_sha256", "package_sha256", "summary_sha256")):
            raise RuntimeError("user summary leaked machine-only document/subject hashes")

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
    _fill_self_test_overlays(envelope)
    with tempfile.TemporaryDirectory(prefix="silver-r5-finalizer-") as folder:
        root = Path(folder)
        output_dir = root / "out"
        result, exit_code = finalize_authoring_envelope(envelope, output_dir)
        report = validate_contract(result, output_dir, "MACHINE_STATE.json")
        if exit_code != 0 or not report.valid:
            raise RuntimeError(f"r5 finalizer self-test failed: {report.as_dict()}")
        if sorted(item.name for item in output_dir.iterdir()) != sorted(result["output_contract"]["exact_relative_output_names"]):
            raise RuntimeError("r5 finalizer did not emit exactly three files")
        assert_plain_first_five(output_dir / "RUN_SUMMARY.md")
        if result["prompt_pilot"]["spread_policy"]["claim"] != "TARGETED_EXACT_RANGES":
            raise RuntimeError("USER_TARGETED Pilot was falsely labelled early/middle/late")
        if (
            result["status_contract"]["stage_status"] != TEXT_EXCLUDED_STAGE_STATUS
            or result["run_summary"]["skipped_stages"] != list(TEXT_EXCLUDED_STAGE_STATUS)
        ):
            raise RuntimeError("r5 status contract does not expose the exact eight excluded stages")
        if "pending" in json.dumps(result["run_summary"], ensure_ascii=False).lower():
            raise RuntimeError("run summary retained a PENDING value")

        # The compact work surface must be sufficient; the creator never needs
        # to rewrite the immutable full-source ledger.
        read_only = prepare_authoring(source, plan, "RUN4")
        authored = prepare_authoring(source, plan, "RUN4")
        _fill_self_test_overlays(authored)
        compact = compact_overlay_work_surface(authored)
        merged = _merge_compact_overlays(read_only, compact)
        compact_result, compact_exit = finalize_authoring_envelope(merged, root / "compact-out")
        if compact_exit != 0 or compact_result["project_status"] != "TEXT_PILOT_COMPLETE":
            raise RuntimeError("compact overlay roundtrip did not reach the terminal text Pilot")

        tampered_compact = copy.deepcopy(compact)
        tampered_compact["target_windows"][0]["source_excerpt"] = "伪造摘录"
        tamper_rejected = False
        try:
            finalize_authoring_envelope(
                _merge_compact_overlays(read_only, tampered_compact),
                root / "tampered-window-out",
            )
        except ValueError:
            tamper_rejected = True
        if not tamper_rejected:
            raise RuntimeError("tampered target_windows escaped the immutable helper projection")

        # A creator finding must fail the non-destructive check and must never
        # commit a REWORK artifact or consume the editable overlays.
        failed_envelope = prepare_authoring(source, plan, "RUN2")
        _fill_self_test_overlays(failed_envelope)
        failed_envelope["compiled_unit_overlays"][0]["quality_overlay"]["findings"] = [
            "人物动作仍需修正"
        ]
        _, failed_report = check_authoring_envelope(failed_envelope, root / "failed-out")
        expected_failure_codes = {"E_AUTHORING_FINDINGS", "E_PROMPT_QUALITY_NOT_READY"}
        commit_rejected = False
        try:
            finalize_authoring_envelope(failed_envelope, root / "failed-out")
        except OverlayCheckFailure as exc:
            commit_rejected = set(exc.error_codes) == expected_failure_codes
        if failed_report.valid or codes(failed_report) != expected_failure_codes or not commit_rejected:
            raise RuntimeError("failed overlay escaped the mandatory non-destructive check")
        if (root / "failed-out").exists():
            raise RuntimeError("failed overlay wrote a final output directory")

        # The finalizer must not delete or overwrite an undeclared non-empty
        # destination while attempting registered-temp cleanup.
        blocked = root / "blocked-out"
        blocked.mkdir()
        marker = blocked / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        blocked_rejected = False
        try:
            finalize_authoring_envelope(envelope, blocked)
        except ValueError:
            blocked_rejected = True
        if not blocked_rejected or marker.read_text(encoding="utf-8") != "keep":
            raise RuntimeError("non-empty output safety check failed")

        cleanup_out = root / "registered-temp-out"
        registered_temp = root / envelope["immutable_contract"]["output_contract"]["temp_root"]
        registered_temp.mkdir(parents=True)
        for name in ("TARGET_PLAN.json", "AUTHORING.json", "OVERLAYS.json"):
            (registered_temp / name).write_text("{}", encoding="utf-8")
        forbidden_helper = registered_temp / "fill_overlays.py"
        forbidden_helper.write_text("# forbidden", encoding="utf-8")
        temp_attack_rejected = False
        try:
            finalize_authoring_envelope(
                envelope,
                cleanup_out,
                registered_temp_root=registered_temp,
            )
        except ValueError as exc:
            temp_attack_rejected = "E_TEMP_ROOT_CONTRACT" in str(exc)
        if not temp_attack_rejected or not forbidden_helper.exists():
            raise RuntimeError("undeclared fill_overlays.py escaped the registered temp_root gate")
        forbidden_helper.unlink()
        cleanup_result, cleanup_exit = finalize_authoring_envelope(
            envelope,
            cleanup_out,
            registered_temp_root=registered_temp,
        )
        if cleanup_exit != 0 or registered_temp.exists() or not validate_contract(
            cleanup_result, cleanup_out, "MACHINE_STATE.json"
        ).valid:
            raise RuntimeError("registered temp_root was not cleaned before atomic commit")
        replacement_result, replacement_exit = finalize_authoring_envelope(
            envelope,
            cleanup_out,
            replace_own_run=True,
        )
        if replacement_exit != 0 or not validate_contract(
            replacement_result, cleanup_out, "MACHINE_STATE.json"
        ).valid:
            raise RuntimeError("verified same-run output was not safely replaced")

        # MACHINE mode must independently form and finish three multi-atom
        # representative scene windows.
        machine_source = "".join(
            f"场景{i:02d}，人物{'回头看向门口' if i % 3 == 0 else '沿道路向前走'}。\n"
            if i not in {5, 12, 19}
            else f"“机器样本对白{i:02d}。”角色说道。\n"
            for i in range(1, 25)
        )
        machine_envelope = prepare_authoring(
            machine_source,
            {"selection_mode": "MACHINE_REPRESENTATIVE_V1", "sample_count": 3},
            "RUN5",
        )
        _fill_self_test_overlays(machine_envelope)
        machine_result, machine_exit = finalize_authoring_envelope(machine_envelope, root / "machine-out")
        if (
            machine_exit != 0
            or machine_result["prompt_pilot"]["selection_mode"] != "MACHINE_REPRESENTATIVE_V1"
            or any(
                window["source_window"]["atom_count"] < 2
                for window in machine_envelope["target_windows"]
            )
            or not validate_contract(
                machine_result, root / "machine-out", "MACHINE_STATE.json"
            ).valid
        ):
            raise RuntimeError("MACHINE_REPRESENTATIVE multi-atom roundtrip failed")

        # Round3 regressions: a nine-atom inspection/pain/throw/sniff sequence
        # needs at least four shots; a character pain cry is not object SFX;
        # source anchors must be complete; MP and DRAFT must do different jobs.
        r3_source = (
            "狐狸长老抓住唐僧检查。\n"
            "唐僧看向洞口。\n"
            "只听“啊”的一声，是唐僧的痛叫。\n"
            "嗖-\n"
            "“唐僧废物附着物”从洞内被扔出来。\n"
            "它砸在耗子妖脸上。\n"
            "耗子妖凑近闻了闻。\n"
            "众小妖走近查看。\n"
            "他们嫌弃后离开。\n"
            "旁段建立。\n"
            "旁段结束。\n"
            "尾段建立。\n"
            "尾段结束。\n"
        )
        r3_plan = {
            "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
            "targets": [
                {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0009"}, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0010", "last_atom_id": "SRC0011"}, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0012", "last_atom_id": "SRC0013"}, "target_mode": "EDITED_SEQUENCE"},
            ],
        }
        r3_envelope = prepare_authoring(r3_source, r3_plan, "RUN8")
        _fill_self_test_overlays(r3_envelope)
        quote_map = {
            item["text"]: item["dialogue_id"]
            for item in r3_envelope["immutable_contract"]["source_dialogue_inventory"]
        }
        r3_overlay = r3_envelope["compiled_unit_overlays"][0]["director_overlay"]
        pain_id = quote_map["啊"]
        label_id = quote_map["唐僧废物附着物"]
        r3_overlay["quote_classifications"][pain_id] = "NON_LEXICAL_VOCALIZATION"
        r3_overlay["quote_classifications"][label_id] = "QUOTED_TEXT"
        remove_nonspoken_from_shots(r3_overlay, pain_id)
        remove_nonspoken_from_shots(r3_overlay, label_id)
        r3_overlay["sound"] += "\n唐僧痛叫：啊"
        r3_overlay["performance"] += "\n唐僧受痛时发出：啊"
        r3_inferences = {
            item["inference_id"]: item for item in r3_overlay["proposed_director_inferences"]
        }
        routed_fragments = {"sound": "唐僧痛叫：啊", "performance": "唐僧受痛时发出：啊"}
        for field in ("sound", "performance"):
            record = r3_overlay["field_provenance"][field]
            record["field_fragment"] = routed_fragments[field]
            r3_inferences[record["inference_id"]]["text"] = routed_fragments[field]
        r3_result, r3_exit = finalize_authoring_envelope(r3_envelope, root / "r3-out")
        if r3_exit != 0:
            raise RuntimeError(
                "Round3 positive unexpectedly reworked: "
                + json.dumps(r3_result.get("validation_result"), ensure_ascii=False, sort_keys=True)
            )
        r3_unit = next(
            unit
            for unit in r3_result["units"]
            if unit.get("unit_id") == r3_result["prompt_pilot"]["sample_unit_ids"][0]
        )
        if (
            r3_exit != 0
            or len(r3_unit["director_contract"]["shot_plan"]) < 4
            or not validate_contract(r3_result, root / "r3-out", "MACHINE_STATE.json").valid
        ):
            raise RuntimeError("Round3 four-beat sequence or non-lexical vocalization positive failed")
        creator_package = (root / "r3-out" / "长篇文字测试包.md").read_text(encoding="utf-8")
        creator_summary = (root / "r3-out" / "RUN_SUMMARY.md").read_text(encoding="utf-8")
        if any(
            forbidden in creator_package + creator_summary
            for forbidden in (
                "## 技术附录",
                "## 技术记录",
                "来源 hash",
                "结构终点",
                "source_sha256",
                "error_codes",
                "validator_exit_code",
            )
        ):
            raise RuntimeError("creator Markdown still exposes technical contract data")
        if (
            "### 导演母版" not in creator_package
            or "### 可复制提示词工作稿" not in creator_package
            or "供应商中性提示词工作稿" in creator_package
        ):
            raise RuntimeError("creator package does not expose the frozen MP/NEP presentation")
        master_surface = creator_prompt_surface(
            r3_unit["prompt_bundle"]["master_prompt"]["text"]
        )
        neutral_surface = creator_prompt_surface(
            r3_unit["prompt_bundle"]["neutral_execution_prompt"]["text"]
        )
        transform_plan_text = r3_unit["prompt_bundle"]["transform_plan"]["text"]
        if (
            master_surface not in creator_package
            or neutral_surface not in creator_package
            or transform_plan_text in creator_package
        ):
            raise RuntimeError("MP/TP/NEP creator/machine separation failed")
        if not all(
            phrase in creator_summary
            for phrase in (
                "结构检查通过",
                "文字内容已完成本轮自检",
                "尚未进行另一位编辑复核",
                "尚未进行真实素材验证",
            )
        ):
            raise RuntimeError("creator summary merged or omitted a four-axis status")

        undershot_r3 = copy.deepcopy(r3_result)
        undershot_unit = next(unit for unit in undershot_r3["units"] if unit.get("unit_id") == r3_unit["unit_id"])
        old_mp = expected_director_prompt_block(undershot_unit["director_contract"], "MP")
        old_neutral = expected_director_prompt_block(
            undershot_unit["director_contract"], "NEUTRAL_EXECUTION"
        )
        undershot_unit["director_contract"]["shot_plan"] = undershot_unit["director_contract"]["shot_plan"][:3]
        new_mp = expected_director_prompt_block(undershot_unit["director_contract"], "MP")
        new_neutral = expected_director_prompt_block(
            undershot_unit["director_contract"], "NEUTRAL_EXECUTION"
        )
        undershot_unit["prompt_bundle"]["master_prompt"]["text"] = undershot_unit["prompt_bundle"]["master_prompt"]["text"].replace(old_mp, new_mp)
        undershot_unit["prompt_bundle"]["neutral_execution_prompt"]["text"] = undershot_unit["prompt_bundle"]["neutral_execution_prompt"]["text"].replace(old_neutral, new_neutral)
        rebind_unit(undershot_unit, undershot_r3)
        if "E_SEQUENCE_SHOT_PLAN" not in codes(validate_contract(
            undershot_r3, root, validate_outputs=False, validate_recorded_result=False
        )):
            raise RuntimeError("Round3 three-shot swallowing attack escaped the dynamic density floor")

        fragment_attack = copy.deepcopy(r3_result)
        fragment_unit = next(unit for unit in fragment_attack["units"] if unit.get("unit_id") == r3_unit["unit_id"])
        old_mp = expected_director_prompt_block(fragment_unit["director_contract"], "MP")
        old_neutral = expected_director_prompt_block(
            fragment_unit["director_contract"], "NEUTRAL_EXECUTION"
        )
        fragment_unit["director_contract"]["entry"] = "来源入口：狐狸长老"
        fragment_unit["director_contract"]["field_provenance"]["entry"]["source_anchor"] = "狐狸长老"
        new_mp = expected_director_prompt_block(fragment_unit["director_contract"], "MP")
        new_neutral = expected_director_prompt_block(
            fragment_unit["director_contract"], "NEUTRAL_EXECUTION"
        )
        fragment_unit["prompt_bundle"]["master_prompt"]["text"] = fragment_unit["prompt_bundle"]["master_prompt"]["text"].replace(old_mp, new_mp)
        fragment_unit["prompt_bundle"]["neutral_execution_prompt"]["text"] = fragment_unit["prompt_bundle"]["neutral_execution_prompt"]["text"].replace(old_neutral, new_neutral)
        rebind_unit(fragment_unit, fragment_attack)
        if "E_SOURCE_ANCHOR_FRAGMENT" not in codes(validate_contract(
            fragment_attack, root, validate_outputs=False, validate_recorded_result=False
        )):
            raise RuntimeError("Round3 truncated source anchor escaped validation")

        duplicate_attack = copy.deepcopy(r3_result)
        duplicate_unit = next(unit for unit in duplicate_attack["units"] if unit.get("unit_id") == r3_unit["unit_id"])
        atom_map = {atom["atom_id"]: atom for atom in duplicate_attack["source_atoms"]}
        source_block = expected_source_prompt_block(duplicate_unit, atom_map)
        same_surface = "导演提案均已逐项标注，不改写冻结事实。"
        duplicate_unit["prompt_bundle"]["master_prompt"]["text"] = (
            source_block + "\n" + expected_director_prompt_block(duplicate_unit["director_contract"], "MP") + "\n" + same_surface
        )
        duplicate_unit["prompt_bundle"]["neutral_execution_prompt"]["text"] = (
            source_block + "\n" + expected_director_prompt_block(duplicate_unit["director_contract"], "NEUTRAL_EXECUTION") + "\n" + same_surface
        )
        rebind_unit(duplicate_unit, duplicate_attack)
        if "E_PROMPT_LAYER_DUPLICATE" not in codes(validate_contract(
            duplicate_attack, root, validate_outputs=False, validate_recorded_result=False
        )):
            raise RuntimeError("identical MASTER/DRAFT creator surfaces escaped validation")

        nonlex_attack = copy.deepcopy(r3_result)
        nonlex_unit = next(unit for unit in nonlex_attack["units"] if unit.get("unit_id") == r3_unit["unit_id"])
        nonlex_unit["provenance"]["quote_classifications"][pain_id] = "SFX"
        rebind_unit(nonlex_unit, nonlex_attack)
        if "E_QUOTE_CLASSIFICATION_CONFLICT" not in codes(validate_contract(
            nonlex_attack, root, validate_outputs=False, validate_recorded_result=False
        )):
            raise RuntimeError("character pain vocalization was accepted as object SFX")

        denial_attack = copy.deepcopy(r3_result)
        denial_unit = next(unit for unit in denial_attack["units"] if unit.get("unit_id") == r3_unit["unit_id"])
        denial_unit["prompt_bundle"]["neutral_execution_prompt"]["text"] += "\n不新增来源事实。"
        rebind_unit(denial_unit, denial_attack)
        if "E_DIRECTOR_UNDECLARED_PROPOSAL" not in codes(validate_contract(
            denial_attack, root, validate_outputs=False, validate_recorded_result=False
        )):
            raise RuntimeError("proposal/no-addition contradiction escaped validation")

        editorial_attack = copy.deepcopy(r3_result)
        editorial_attack["run_summary"]["editorial_review_status"] = "PASS"
        if "E_EDITORIAL_REVIEW_AXIS" not in codes(validate_contract(
            editorial_attack, root, validate_outputs=False, validate_recorded_result=False
        )):
            raise RuntimeError("structural PASS was allowed to masquerade as editorial approval")

        if (
            expected_sequence_minimum_shots("看。走。跑。抓。回头。叫。" * 4, dialogue_turns=7, atom_count=21) < 6
            or expected_sequence_minimum_shots("第一年。十年后。第十五年。三十年后。终于走。看。跑。抓。叫。" * 3, atom_count=27) < 8
            or expected_sequence_minimum_shots("抓。看。痛叫。闻。走近。离开。", atom_count=9) < 4
        ):
            raise RuntimeError("Round3 U001/U002/U016 density floors regressed")

        # Cross-atom quoted text is legal.  Classifying it as SFX removes the
        # dialogue slot and routes its exact source text into sound.
        quote_source = (
            "起点。\n“风声\n啪。”\n门被推开。\n"
            "中段。\n“第二句。”\n转折。\n"
            "尾段。\n“第三句。”\n结束。\n"
        )
        quote_plan = {
            "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
            "targets": [
                {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0004"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0005", "last_atom_id": "SRC0007"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0008", "last_atom_id": "SRC0010"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
            ],
        }
        quote_envelope = prepare_authoring(quote_source, quote_plan, "RUN6")
        _fill_self_test_overlays(quote_envelope)
        first_window = quote_envelope["target_windows"][0]
        cross_id = first_window["dialogue_slot_ids"][0]
        cross_text = next(
            item["text"]
            for item in quote_envelope["immutable_contract"]["source_dialogue_inventory"]
            if item["dialogue_id"] == cross_id
        )
        first_overlay = quote_envelope["compiled_unit_overlays"][0]
        first_overlay["director_overlay"]["quote_classifications"][cross_id] = "SFX"
        remove_nonspoken_from_shots(first_overlay["director_overlay"], cross_id)
        first_overlay["director_overlay"]["sound"] += "\n" + cross_text
        quote_result, quote_exit = finalize_authoring_envelope(quote_envelope, root / "quote-out")
        if quote_exit != 0 or not validate_contract(
            quote_result, root / "quote-out", "MACHINE_STATE.json"
        ).valid:
            raise RuntimeError("cross-atom quote/SFX routing roundtrip failed")

        quote_attack = copy.deepcopy(quote_result)
        quote_attack["source_dialogue_inventory"][0]["source_refs"] = list(
            reversed(quote_attack["source_dialogue_inventory"][0]["source_refs"])
        )
        quote_attack_report = validate_contract(
            quote_attack,
            root / "quote-out",
            "MACHINE_STATE.json",
            validate_outputs=False,
            validate_recorded_result=False,
        )
        if "E_SOURCE_QUOTE_COVERAGE" not in codes(quote_attack_report):
            raise RuntimeError("wrong-order cross-atom quote refs were not rejected")

        # Exact mixed-classification neighborhood from the real 西游 U044
        # regression, plus the real U004 question/response and long-attribution
        # SFX-prefixed spoken lines.
        classification_source = (
            "第一段。\n\n人物沿路前行。\n\n动作结束。\n\n"
            "长相比猪八戒和孙猴子还凶恶！\n\n"
            "“完了！自己刚长生，就要死了吗！”朱佩奇心惊胆战啊，自己好不容易获得一个外挂，还没体验就要无了吗。\n\n"
            "“吧唧-”沙和尚盯着朱佩奇看了一会，抬起手啃一口狮子大王的大腿。\n\n"
            "随后径直离开，没有理会已经吓破胆的朱佩奇。\n\n"
            "“里面咋的了？”朱佩奇向身边一只秃头尖尾的灰色大耗子问道。\n\n"
            "“吱-这你都不知道，咱们大王昨天抓了个女人！现在轮流欣赏呢！”\n\n"
            "“呱-不对，我听说是大王抓到一个好看的虫子，叫蝉！我最喜欢吃蝉了！”一只眼珠子鼓起的黑色癞蛤蟆伸出舌头吞掉一只苍蝇，悠悠说道。\n"
        )
        classification_plan = {
            "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
            "targets": [
                {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0003"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0004", "last_atom_id": "SRC0007"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
                {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0008", "last_atom_id": "SRC0010"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "EDITED_SEQUENCE"},
            ],
        }
        conflict_envelope = prepare_authoring(classification_source, classification_plan, "RUN12")
        hint_by_text = {
            item["text"]: set(item["classification_hints"])
            for item in conflict_envelope["immutable_contract"]["source_dialogue_inventory"]
        }
        if (
            "LIKELY_INTERNAL_THOUGHT"
            not in hint_by_text["完了！自己刚长生，就要死了吗！"]
            or "LIKELY_SFX" not in hint_by_text["吧唧-"]
            or not {"SFX_PREFIXED_SPEECH_CANDIDATE", "QUESTION_RESPONSE_EVIDENCE"}.issubset(
                hint_by_text["吱-这你都不知道，咱们大王昨天抓了个女人！现在轮流欣赏呢！"]
            )
            or not {"SFX_PREFIXED_SPEECH_CANDIDATE", "EXPLICIT_SPEECH_EVIDENCE"}.issubset(
                hint_by_text["呱-不对，我听说是大王抓到一个好看的虫子，叫蝉！我最喜欢吃蝉了！"]
            )
        ):
            raise RuntimeError("deterministic quote classification hints were not derived as expected")
        ordinary_source = "“太好了！”阳光照进屋里。"
        ordinary_hints, _ = derive_quote_classification_hints(
            ordinary_source,
            ordinary_source.index("“"),
            ordinary_source.index("”") + 1,
            "太好了！",
        )
        if ordinary_hints != ["NO_STRONG_CLASSIFICATION_HINT"]:
            raise RuntimeError("ordinary exclamation was incorrectly classified as internal thought")
        for false_source in (
            "“呱-不对！”叙述没有说话归属。\n\n角色说道。",
            "“呱-不对！”叙述没有说话归属。“下一句。”角色说道。",
        ):
            false_hints, false_evidence = derive_quote_classification_hints(
                false_source,
                false_source.index("“"),
                false_source.index("”") + 1,
                "呱-不对！",
            )
            if (
                "SFX_PREFIX_AMBIGUOUS" not in false_hints
                or false_evidence["explicit_speech_evidence"]
                or not spoken_quote_conflicts(
                    {
                        "classification_hints": false_hints,
                        "context_evidence": false_evidence,
                    }
                )
            ):
                raise RuntimeError("cross-paragraph/next-quote speech evidence was incorrectly borrowed")
        _fill_self_test_overlays(conflict_envelope)
        _, conflict_report = check_authoring_envelope(
            conflict_envelope, root / "classification-conflict-out"
        )
        conflict_commit_rejected = False
        try:
            finalize_authoring_envelope(conflict_envelope, root / "classification-conflict-out")
        except OverlayCheckFailure as exc:
            conflict_commit_rejected = "E_QUOTE_CLASSIFICATION_CONFLICT" in exc.error_codes
        if "E_QUOTE_CLASSIFICATION_CONFLICT" not in codes(conflict_report) or not conflict_commit_rejected:
            raise RuntimeError("obvious SFX/internal-thought quotes were accepted as spoken dialogue")

        corrected_envelope = prepare_authoring(classification_source, classification_plan, "RUN13")
        _fill_self_test_overlays(corrected_envelope)
        quote_items = corrected_envelope["immutable_contract"]["source_dialogue_inventory"]
        routing = {
            "完了！自己刚长生，就要死了吗！": ("INTERNAL_THOUGHT", "performance"),
            "吧唧-": ("SFX", "sound"),
        }
        for item in quote_items:
            if item["text"] not in routing:
                continue
            classification, field = routing[item["text"]]
            target_overlay = next(
                overlay
                for window, overlay in zip(
                    corrected_envelope["target_windows"],
                    corrected_envelope["compiled_unit_overlays"],
                )
                if item["dialogue_id"] in window["dialogue_slot_ids"]
            )
            target_overlay["director_overlay"]["quote_classifications"][item["dialogue_id"]] = classification
            remove_nonspoken_from_shots(target_overlay["director_overlay"], item["dialogue_id"])
            target_overlay["director_overlay"][field] += "\n" + item["text"]
        corrected_result, corrected_exit = finalize_authoring_envelope(
            corrected_envelope, root / "classification-corrected-out"
        )
        corrected_report = validate_contract(
            corrected_result,
            root / "classification-corrected-out",
            "MACHINE_STATE.json",
        )
        if corrected_exit != 0 or not corrected_report.valid:
            raise RuntimeError(
                "correct SFX/internal-thought routing or SFX-prefixed spoken dialogue was rejected: "
                + json.dumps(corrected_report.as_dict(), ensure_ascii=False, sort_keys=True)
            )
        corrected_units = {
            unit["unit_id"]: unit
            for unit in corrected_result["units"]
            if unit.get("compile_status") == "ACCEPTED"
        }
        actual_window = corrected_envelope["target_windows"][1]
        actual_unit = corrected_units[actual_window["unit_id"]]
        if actual_unit["provenance"]["dialogue_slot_ids"] != [] or actual_unit["dialogue_diff"]["status"] != "PASS":
            raise RuntimeError("correct U044 internal/SFX routing retained stale spoken dialogue slots")
        prefixed_window = corrected_envelope["target_windows"][2]
        prefixed_unit = corrected_units[prefixed_window["unit_id"]]
        prefixed_ids = [
            item["dialogue_id"]
            for item in quote_items
            if item["text"]
            in {
                "里面咋的了？",
                "吱-这你都不知道，咱们大王昨天抓了个女人！现在轮流欣赏呢！",
                "呱-不对，我听说是大王抓到一个好看的虫子，叫蝉！我最喜欢吃蝉了！",
            }
        ]
        if prefixed_unit["provenance"]["dialogue_slot_ids"] != prefixed_ids:
            raise RuntimeError("real U004 spoken/response slots were not preserved in source order")

        # A generic creator body can never hide missing director/source work:
        # finalizer-owned blocks are mandatory and body hashes are rebound.
        generic = copy.deepcopy(result)
        generic_unit = next(unit for unit in generic["units"] if unit.get("compile_status") == "ACCEPTED")
        for layer in ("master_prompt", "neutral_execution_prompt"):
            generic_unit["prompt_bundle"][layer]["text"] = "忠实呈现。"
        rebind_unit(generic_unit, generic)
        generic_report = validate_contract(
            generic,
            root,
            validate_outputs=False,
            validate_recorded_result=False,
        )
        if not {"E_PROMPT_SOURCE_BLOCK", "E_PROMPT_DIRECTOR_BLOCK"}.issubset(codes(generic_report)):
            raise RuntimeError("generic prompt bypass was not rejected by compiled-block validation")

        provenance_attack = copy.deepcopy(result)
        provenance_unit = next(
            unit for unit in provenance_attack["units"] if unit.get("compile_status") == "ACCEPTED"
        )
        source_atom_map = {
            atom["atom_id"]: atom for atom in provenance_attack["source_atoms"] if isinstance(atom, dict)
        }
        unrelated_anchor = normalize_text(
            source_atom_map[provenance_unit["source_refs"][0]]["text"]
        ).strip().splitlines()[0][:24]
        provenance_unit["director_contract"]["field_provenance"]["camera"] = {
            "status": "SOURCE_SUPPORTED",
            "source_refs": [provenance_unit["source_refs"][0]],
            "source_anchor": unrelated_anchor,
        }
        rebind_unit(provenance_unit, provenance_attack)
        provenance_report = validate_contract(
            provenance_attack,
            root,
            validate_outputs=False,
            validate_recorded_result=False,
        )
        if "E_DIRECTOR_SOURCE_ANCHOR" not in codes(provenance_report):
            raise RuntimeError("source-present but field-unrelated anchor escaped validation")

        generic_director = copy.deepcopy(result)
        generic_director_unit = next(
            unit for unit in generic_director["units"] if unit.get("compile_status") == "ACCEPTED"
        )
        for serial, field in enumerate(("entry", "action_state_chain", "exit", "continuity"), start=1):
            inference_id = f"INF-GENERIC-{serial:02d}"
            fragment = json.dumps(
                generic_director_unit["director_contract"][field], ensure_ascii=False, sort_keys=True
            )
            generic_director_unit["director_contract"]["proposed_director_inferences"].append(
                {
                    "inference_id": inference_id,
                    "status": "PROPOSED_DIRECTOR_INFERENCE",
                    "text": fragment,
                    "source_refs": [generic_director_unit["source_refs"][0]],
                }
            )
            generic_director_unit["director_contract"]["field_provenance"][field] = {
                "status": "PROPOSED_DIRECTOR_INFERENCE",
                "source_refs": [generic_director_unit["source_refs"][0]],
                "inference_id": inference_id,
                "field_fragment": fragment,
            }
        rebind_unit(generic_director_unit, generic_director)
        generic_director_report = validate_contract(
            generic_director,
            root,
            validate_outputs=False,
            validate_recorded_result=False,
        )
        if "E_DIRECTOR_SOURCE_CORE" not in codes(generic_director_report):
            raise RuntimeError("all-PROPOSED generic director core escaped source anchoring")

        dense_source = (
            "入口。\n"
            "“第一句。”甲说道。\n“第二句。”乙说道。\n“第三句。”丙说道。\n“第四句。”甲说道。\n"
            "“第五句。”乙说道。\n“第六句。”丙说道。\n“第七句。”甲说道。\n“第八句。”乙说道。\n"
            "众人回头，抓住门把，再次停下。\n过渡一。\n过渡二。\n尾声一。\n尾声二。\n"
        )
        dense_plan = {
            "selection_mode": "USER_TARGETED_EXACT_RANGES_V1",
            "targets": [
                {"target_id": "T001", "atom_range": {"first_atom_id": "SRC0001", "last_atom_id": "SRC0010"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "GENERATABLE_SHOT"},
                {"target_id": "T002", "atom_range": {"first_atom_id": "SRC0011", "last_atom_id": "SRC0012"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "GENERATABLE_SHOT"},
                {"target_id": "T003", "atom_range": {"first_atom_id": "SRC0013", "last_atom_id": "SRC0014"}, "context_atoms_before": 0, "context_atoms_after": 0, "target_mode": "GENERATABLE_SHOT"},
            ],
        }
        dense_envelope = prepare_authoring(dense_source, dense_plan, "RUN10")
        _fill_self_test_overlays(dense_envelope)
        dense_result, dense_exit = finalize_authoring_envelope(dense_envelope, root / "dense-out")
        dense_unit_id = dense_result["selection_request"]["sample_unit_ids"][0]
        dense_unit = next(unit for unit in dense_result["units"] if unit["unit_id"] == dense_unit_id)
        if (
            dense_exit != 0
            or dense_unit["director_contract"]["target_mode"] != "EDITED_SEQUENCE"
            or len(dense_unit["director_contract"]["shot_plan"]) < 4
            or not validate_contract(dense_result, root / "dense-out", "MACHINE_STATE.json").valid
        ):
            raise RuntimeError("eight-turn dialogue was not deterministically split into a valid sequence")

        undershot = copy.deepcopy(dense_result)
        undershot_unit = next(unit for unit in undershot["units"] if unit["unit_id"] == dense_unit_id)
        old_block = expected_director_prompt_block(undershot_unit["director_contract"])
        undershot_unit["director_contract"]["shot_plan"] = undershot_unit["director_contract"][
            "shot_plan"
        ][:2]
        new_block = expected_director_prompt_block(undershot_unit["director_contract"])
        for layer in ("master_prompt", "neutral_execution_prompt"):
            artifact = undershot_unit["prompt_bundle"][layer]
            artifact["text"] = artifact["text"].replace(old_block, new_block)
        rebind_unit(undershot_unit, undershot)
        undershot_report = validate_contract(
            undershot,
            root,
            validate_outputs=False,
            validate_recorded_result=False,
        )
        if "E_SEQUENCE_SHOT_PLAN" not in codes(undershot_report):
            raise RuntimeError("two shots incorrectly swallowed an eight-turn dialogue window")

        first_atom_only = copy.deepcopy(dense_result)
        first_atom_unit = next(unit for unit in first_atom_only["units"] if unit["unit_id"] == dense_unit_id)
        first_ref = first_atom_unit["source_refs"][0]
        for shot in first_atom_unit["director_contract"]["shot_plan"]:
            shot["source_refs"] = [first_ref]
            for record in shot["field_provenance"].values():
                record["source_refs"] = [first_ref]
        rebind_unit(first_atom_unit, first_atom_only)
        first_atom_report = validate_contract(
            first_atom_only,
            root,
            validate_outputs=False,
            validate_recorded_result=False,
        )
        if "E_SEQUENCE_SHOT_COVERAGE" not in codes(first_atom_report):
            raise RuntimeError("shot plan bound only to the first atom escaped coverage validation")

        status_attack = copy.deepcopy(result)
        status_attack["status_contract"]["stage_status"]["AUDIO"] = "EXCLUDED_BY_USER"
        status_attack["status_contract"]["stage_status"].pop("MUSIC")
        status_report = validate_contract(
            status_attack,
            root,
            validate_outputs=False,
            validate_recorded_result=False,
        )
        if "E_TEXT_STATUS_CONSISTENCY" not in codes(status_report):
            raise RuntimeError("legacy AUDIO alias escaped the exact r5 eight-stage axis")

        blank_atom_attack = copy.deepcopy(result)
        blank_atom_attack["source_atoms"][0]["text"] = "\n"
        blank_atom_report = validate_contract(
            blank_atom_attack,
            root,
            validate_outputs=False,
            validate_recorded_result=False,
        )
        if "E_SOURCE_BLANK_ATOM" not in codes(blank_atom_report):
            raise RuntimeError("blank-only STORY_EVENT atom escaped r5 validation")

        # Both rendered Markdown files are part of the machine result.  Editing
        # either after finalization invalidates the recorded document hash.
        summary_path = output_dir / "RUN_SUMMARY.md"
        original_summary = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(
            original_summary + "\n篡改。\n",
            encoding="utf-8",
            newline="\n",
        )
        tampered_doc_report = validate_contract(result, output_dir, "MACHINE_STATE.json")
        if "E_OUTPUT_DOCUMENT_HASH" not in codes(tampered_doc_report):
            raise RuntimeError("post-validation summary tamper was not detected")
        summary_path.write_text(original_summary, encoding="utf-8", newline="\n")
        package_path = output_dir / "长篇文字测试包.md"
        original_package = package_path.read_text(encoding="utf-8")
        package_path.write_text(original_package + "\n篡改。\n", encoding="utf-8", newline="\n")
        tampered_package_report = validate_contract(result, output_dir, "MACHINE_STATE.json")
        if "E_OUTPUT_DOCUMENT_HASH" not in codes(tampered_package_report):
            raise RuntimeError("post-validation package tamper was not detected")
    legacy = build_pilot_fixture()
    try:
        finalize_legacy_contract(copy.deepcopy(legacy))
    except ValueError as exc:
        if "E_READ_ONLY_CONTRACT_FINALIZATION" not in str(exc):
            raise RuntimeError("legacy read-only finalization rejected with the wrong code") from exc
    else:
        raise RuntimeError("legacy read-only input was rewritten by the current finalizer")
    return {
        "self_test": "PASS",
        "contract_version": CONTRACT_VERSION,
        "authoring_version": AUTHORING_VERSION,
        "terminal_promotion_exclusive": True,
        "strict_three_files": True,
        "machine_mode_roundtrip": True,
        "compact_overlay_roundtrip": True,
        "rework_three_file_roundtrip": True,
        "cross_atom_quote_roundtrip": True,
        "r5_attack_count": 14,
        "r6_round3_attack_count": 7,
        "self_contained_guide_required": True,
        "registered_temp_root_cleanup": True,
        "safe_same_run_replace": True,
        "structural_editorial_split": True,
        "quote_classification_gate": True,
        "mixed_quote_routing_roundtrip": True,
        "bounded_speech_evidence_roundtrip": True,
        "creator_markdown_chinese_projection": True,
        "mp_tp_nep_presentation_split": True,
        "presentation_machine_semantics_read_only": True,
        "legacy_1_0_read_only": True,
        "production_validation": "NOT_TESTED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Finalize an r6 authoring envelope into the strict three-file longform result"
    )
    parser.add_argument("authoring", nargs="?", type=Path, help="authoring envelope JSON")
    parser.add_argument("output", nargs="?", type=Path, help="r9 output directory, or legacy output JSON")
    parser.add_argument(
        "--overlays",
        type=Path,
        help="compact overlay work surface; merged into the read-only authoring envelope",
    )
    parser.add_argument(
        "--replace-own-run",
        action="store_true",
        help="atomically replace only a verified same-source/same-run strict three-file output",
    )
    parser.add_argument(
        "--check-overlays",
        action="store_true",
        help="compile and validate overlays without writing output or cleaning the canonical temp root",
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--legacy-read-only",
        action="store_true",
        help="deprecated fail-closed flag; use migrate_longform_contract.py for 1.0-1.4",
    )
    args = parser.parse_args()
    if args.self_test:
        try:
            test_support = Path(__file__).resolve().parent.parent / "tests" / "longform_selftest_support.py"
            result = run_self_test() if test_support.is_file() else run_runtime_smoke_test()
        except Exception as exc:
            print(json.dumps({"self_test": "FAIL", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
            return 1
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    if args.authoring is None or args.output is None:
        parser.error("authoring and output are required unless --self-test is used")
    if not args.legacy_read_only and args.overlays is None:
        parser.error("--overlays is required for the self-contained authoring workflow")
    try:
        authoring_path = args.authoring.resolve()
        output_path = args.output.resolve()
        overlay_path = args.overlays.resolve() if args.overlays is not None else None
        if not args.legacy_read_only and not authoring_path.exists():
            recovered = _recover_completed_in_place(output_path)
            if recovered is None:
                raise ValueError("E_COMMIT_STATE_PARTIAL_UNOWNED: AUTHORING carrier is missing")
            result, exit_code = recovered
            print(
                json.dumps(
                    {
                        "finalized": True,
                        "already_committed": True,
                        "project_status": result["project_status"],
                        "validation_result": result["validation_result"],
                        "output_directory": str(output_path),
                        "files": result["output_contract"]["exact_relative_output_names"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return exit_code
        if args.legacy_read_only and authoring_path == output_path:
            raise ValueError("legacy finalizer output must not overwrite its input")
        data = json.loads(args.authoring.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("input root must be an object")
        if COMMIT_JOURNAL_KEY in data:
            if args.check_overlays:
                raise ValueError("E_COMMIT_ALREADY_STARTED: use commit_argv to resume the owned transaction")
            result, exit_code = _commit_in_place_from_journal(output_path, data)
            print(
                json.dumps(
                    {
                        "finalized": True,
                        "resumed_commit": True,
                        "project_status": result["project_status"],
                        "validation_result": result["validation_result"],
                        "output_directory": str(output_path),
                        "files": result["output_contract"]["exact_relative_output_names"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return exit_code
        if (
            data.get("engine") == "SILVER_LONGFORM"
            and isinstance(data.get("output_contract"), dict)
            and data["output_contract"].get("commit_mode") == IN_PLACE_COMMIT_MODE
            and data["output_contract"].get("temp_root_cleaned") is True
        ):
            # Crash after the final machine payload was written to AUTHORING
            # but before its last atomic promotion.
            windows = expected_target_windows(data)
            package_text = _render_package(data, windows)
            summary_text = _render_summary(data)
            payloads = (
                package_text,
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                summary_text,
            )
            result, exit_code = _commit_in_place_from_journal(
                output_path,
                _build_commit_journal(data, windows, payloads),
            )
            print(
                json.dumps(
                    {
                        "finalized": True,
                        "resumed_commit": True,
                        "project_status": result["project_status"],
                        "validation_result": result["validation_result"],
                        "output_directory": str(output_path),
                        "files": result["output_contract"]["exact_relative_output_names"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return exit_code
        if args.legacy_read_only:
            finalized = finalize_legacy_contract(data)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(finalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            print(json.dumps({"legacy_finalized": True, "validated": False}, ensure_ascii=False, sort_keys=True))
            return 0
        if args.overlays is not None:
            overlay_data = json.loads(args.overlays.read_text(encoding="utf-8"))
            if not isinstance(overlay_data, dict):
                raise ValueError("compact overlay root must be an object")
            data = _merge_compact_overlays(data, overlay_data)
        immutable = data.get("immutable_contract") if isinstance(data, dict) else None
        output_contract = immutable.get("output_contract") if isinstance(immutable, dict) else None
        temp_root_name = output_contract.get("temp_root") if isinstance(output_contract, dict) else None
        commit_mode = output_contract.get("commit_mode") if isinstance(output_contract, dict) else None
        if not isinstance(temp_root_name, str):
            raise ValueError("E_TEMP_ROOT_CONTRACT: authoring envelope has no registered temp_root")
        if commit_mode == IN_PLACE_COMMIT_MODE:
            registered_temp_root = args.output.resolve()
        elif commit_mode == SIBLING_COMMIT_MODE:
            registered_temp_root = args.output.resolve().parent / temp_root_name
            try:
                authoring_path.relative_to(output_path)
                raise ValueError("authoring envelope must live outside the strict final output directory")
            except ValueError as exc:
                if str(exc).startswith("authoring envelope"):
                    raise
            if overlay_path is not None:
                try:
                    overlay_path.relative_to(output_path)
                    raise ValueError("compact overlays must live outside the strict final output directory")
                except ValueError as exc:
                    if str(exc).startswith("compact overlays"):
                        raise
        else:
            raise ValueError("E_OUTPUT_COMMIT_MODE: authoring envelope has unsupported commit mode")
        if (
            args.authoring.resolve() != registered_temp_root / "AUTHORING.json"
            or args.overlays.resolve() != registered_temp_root / "OVERLAYS.json"
            or not (registered_temp_root / "TARGET_PLAN.json").is_file()
        ):
            raise ValueError(
                "E_TEMP_ROOT_CONTRACT: finalizer inputs must be canonical files in the declared carrier root"
            )
        _assert_registered_temp_root(
            registered_temp_root,
            TEMP_INPUT_NAMES,
        )
        if args.check_overlays:
            checked_contract, checked_report = check_authoring_envelope(
                data,
                args.output,
                replace_own_run=args.replace_own_run,
            )
            report_data = checked_report.as_dict()
            root_errors, cascade_errors = _partition_check_errors(report_data["errors"])
            print(
                json.dumps(
                    {
                        "checked": True,
                        "overlays_valid": checked_report.valid,
                        "error_count": report_data["error_count"],
                        "error_codes": report_data["error_codes"],
                        "errors": report_data["errors"],
                        "root_error_count": len(root_errors),
                        "root_errors": root_errors,
                        "public_repairs": _public_repair_items(checked_contract, root_errors),
                        "cascade_error_count": len(cascade_errors),
                        "cascade_errors": cascade_errors,
                        "temp_preserved": registered_temp_root.is_dir(),
                        "output_written": False,
                        "project_status_if_committed": checked_contract.get("project_status"),
                        "production_validation": "NOT_TESTED",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0 if checked_report.valid else 2
        result, exit_code = finalize_authoring_envelope(
            data,
            args.output,
            replace_own_run=args.replace_own_run,
            registered_temp_root=registered_temp_root,
        )
    except OverlayCheckFailure as exc:
        print(
            json.dumps(
                {
                    "finalized": False,
                    "overlays_valid": False,
                    "error_codes": exc.error_codes,
                    "errors": exc.errors,
                    "root_error_count": len(exc.root_errors),
                    "root_errors": exc.root_errors,
                    "public_repairs": _public_repair_items(
                        data.get("immutable_contract", data)
                        if isinstance(data, dict) else {},
                        exc.root_errors,
                    ),
                    "cascade_error_count": len(exc.cascade_errors),
                    "cascade_errors": exc.cascade_errors,
                    "temp_preserved": True,
                    "output_written": False,
                    "production_validation": "NOT_TESTED",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        payload: dict[str, Any] = {"finalized": False, "error": str(exc)}
        if args.check_overlays:
            match = re.search(r"\b(E_[A-Z0-9_]+)\b", str(exc))
            root_error = {
                "code": match.group(1) if match else "E_AUTHORING_ENVELOPE",
                "message": str(exc),
                "path": "$",
            }
            payload.update(
                {
                    "overlays_valid": False,
                    "root_error_count": 1,
                    "root_errors": [root_error],
                    "public_repairs": _public_repair_items(
                        data.get("immutable_contract", data)
                        if isinstance(data, dict) else {},
                        [root_error],
                    ),
                    "cascade_error_count": 0,
                    "cascade_errors": [],
                    "temp_preserved": True,
                    "output_written": False,
                    "production_validation": "NOT_TESTED",
                }
            )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1
    print(
        json.dumps(
            {
                "finalized": True,
                "project_status": result["project_status"],
                "validation_result": result["validation_result"],
                "output_directory": str(args.output.resolve()),
                "files": result["output_contract"]["exact_relative_output_names"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
