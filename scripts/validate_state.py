#!/usr/bin/env python3
"""Validate Alpha.7 Silver project-state invariants with the standard library."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CJK_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]*\b")
MEDIA_GATE_TYPES = {
    "ASSET_GATE",
    "SHOT_GATE",
    "SEQUENCE_CONTINUITY_GATE",
    "FINAL_ARTIFACT_GATE",
}
APPROVED_DECISION_STATUSES = {"USER_APPROVED", "LOCKED"}
TERMINAL_MARKERS = {"REAL_PRODUCTION_COMPLETE"}
ALPHA7_SCHEMA_VERSION = "3.0.0-alpha.7"
PRE_QUALITY_IDENTIFIER_MAP = {
    "".join(chr(point) for point in (65, 76, 80, 72, 65, 55, 82, 50, 45, 80, 81, 83, 45, 49)):
        "ALPHA7-PQS-1",
    "".join(chr(point) for point in (65, 76, 80, 72, 65, 55, 82, 50, 45, 50, 80, 65, 83, 83, 45, 49)):
        "ALPHA7-2PASS-1",
}
GENERATION_TASK_TYPES = {
    "IMAGE_GENERATION", "VIDEO_GENERATION", "IMAGE_TO_VIDEO", "VIDEO_TO_VIDEO",
}
EXECUTABLE_GENERATION_STATUSES = {
    "READY", "RUNNING", "EXECUTED_FAILED", "EXECUTED_SUCCEEDED",
}
PRODUCTION_MEDIA_TASK_TYPES = GENERATION_TASK_TYPES | {
    "AUDIO_GENERATION", "VOICE_SYNTHESIS", "RENDER", "EXPORT",
}
LOCAL_VALIDATION_TASK_TYPES = {"ANALYZE", "RESEARCH", "MEDIA_QA", "PREFLIGHT"}
LOCAL_TEXT_TOOL_TASK_TYPES = {"WRITE", "TRANSCRIPTION", "SUBTITLE", "EDIT_TIMELINE"}
QUALIFIED_EXACT_DURATION_EVIDENCE = {
    "VERIFIED_OFFICIAL", "VERIFIED_PRIMARY_RESEARCH", "PLATFORM_SAMPLE",
}
PROMPT_SECTION_KINDS = {
    "TASK", "REFERENCE_ASSET", "SCENE_STYLE_CONTINUITY", "DIRECTOR_TIMELINE",
    "STATIC_FRAME", "SOUND", "NEGATIVE", "TRANSFORM_PLAN",
}
IMAGE_ONLY_GENERATION_ROLES = {
    "SHOT_KEYFRAME", "SHOT_START_FRAME", "SHOT_END_FRAME", "SHOT_COMPOSITE_LAYER",
}
VIDEO_ONLY_GENERATION_ROLES = {"SHOT_MOTION", "ASSET_MOTION_REFERENCE"}
PROMPT_REQUIRED_VIDEO_SECTIONS = {
    "TASK", "REFERENCE_ASSET", "SCENE_STYLE_CONTINUITY", "DIRECTOR_TIMELINE",
    "SOUND", "NEGATIVE",
}
PROMPT_REQUIRED_IMAGE_SECTIONS = {
    "TASK", "REFERENCE_ASSET", "SCENE_STYLE_CONTINUITY", "STATIC_FRAME", "NEGATIVE",
}
PROMPT_ALLOWED_IMAGE_SECTIONS = PROMPT_REQUIRED_IMAGE_SECTIONS
PROMPT_SOUL_ARTIFACT_TYPES = {
    "production_text_spec", "prompt_soul", "global_truth", "story_bible",
    "creative_bible", "world_bible", "style_bible", "visual_bible", "director_bible",
    "script", "screenplay", "character_bible", "sound_bible",
}
PROMPT_SOUL_ARTIFACT_STATUSES = {
    "SPEC_READY", "TEXT_SPEC_COMPLETE", "USER_APPROVED", "VALIDATED", "LOCKED",
}
LONGFORM_SOURCE_REGISTRY_TYPES = {
    "longform_source_atom_registry", "longform_prompt_source_trace",
}
VERIFIED_FACT_EVIDENCE_CLASSES = {
    "VERIFIED_OFFICIAL", "VERIFIED_PRIMARY_RESEARCH",
}
STATIC_DYNAMIC_LANGUAGE_RE = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*(?:s|sec|secs|second|seconds)\b|"
    r"\b(?:soundtrack|audio|speaks?|dialogue|voice[- ]?over)\b|"
    r"\bcamera\s+(?:push(?:es)?|pull(?:s)?|pan(?:s)?|tilt(?:s)?|doll(?:y|ies)|"
    r"track(?:s)?|move(?:s)?)\b|"
    r"\d+(?:\.\d+)?\s*秒|配乐|音轨|对白|旁白|开口说话|镜头(?:推进|拉远|摇摄|平移|运动))",
    flags=re.IGNORECASE,
)
PROMPT_PROFILE_BASE_DIMENSIONS = {
    "MANGA_CORE": {
        "DURATION", "EVENT_ORDER", "ACTION_ENDPOINT", "PERFORMANCE", "CAMERA",
        "SOUND", "CONTINUITY", "MATERIAL_LIGHT_ENVIRONMENT",
    },
    "CINEMATIC_GENERAL": {
        "DURATION", "EVENT_ORDER", "ACTION_ENDPOINT", "CAMERA", "SOUND",
        "CONTINUITY", "MATERIAL_LIGHT_ENVIRONMENT",
    },
    "NONFICTION_VISUAL": {
        "DURATION", "EVENT_ORDER", "CAMERA", "SOUND", "CONTINUITY",
        "PROTECTED_BOUNDARY",
    },
    "BRAND_PROMO": {
        "DURATION", "EVENT_ORDER", "ACTION_ENDPOINT", "CAMERA", "SOUND",
        "CONTINUITY", "MATERIAL_LIGHT_ENVIRONMENT", "PROTECTED_BOUNDARY",
    },
    "BRAND_NONFICTION": {
        "DURATION", "EVENT_ORDER", "ACTION_ENDPOINT", "CAMERA", "SOUND",
        "CONTINUITY", "MATERIAL_LIGHT_ENVIRONMENT", "PROTECTED_BOUNDARY",
    },
}
PROMPT_INTERNAL_LEAK_RE = re.compile(
    r"\b(?:MP|PD|PP|PQ|PSA|BT|SEC|CHK|RCP|TSK)-[A-Z0-9_-]+\b|"
    r"\b[A-Fa-f0-9]{64}\b|Generation Readiness Gate|prompt_quality_records?|"
    r"source_spec_version|state_cleanup|Context Firewall|内部路由|恢复卡",
    flags=re.IGNORECASE,
)
PROJECT_STATE_SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "project_state.schema.json"
SYSTEM_INVARIANT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "schemas" / "system_invariant_registry.json"
)


def _load_system_invariant_registry() -> set[str]:
    """Load the sole maintained allowlist for SYSTEM_INVARIANT requirement sources."""

    try:
        document = json.loads(SYSTEM_INVARIANT_REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {
        str(item.get("invariant_id"))
        for item in document.get("invariants", [])
        if isinstance(item, dict) and str(item.get("invariant_id", "")).startswith("INV-")
    }


SYSTEM_INVARIANT_REGISTRY = _load_system_invariant_registry()


def _json_equal(left: Any, right: Any) -> bool:
    """Compare values using JSON semantics (so true is not equal to 1)."""

    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=False
    )


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _resolve_local_ref(root_schema: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        raise ValueError(f"only local JSON Schema references are supported: {ref}")
    node: Any = root_schema
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"unresolvable JSON Schema reference: {ref}")
        node = node[part]
    return node


def _schema_errors(
    value: Any,
    schema: Any,
    root_schema: dict[str, Any],
    path: str,
) -> list[str]:
    """Validate the JSON Schema subset used by this package, without dependencies."""

    if schema is True:
        return []
    if schema is False:
        return [f"{path}: value is forbidden by schema"]
    if not isinstance(schema, dict):
        return [f"{path}: invalid schema node"]

    errors: list[str] = []
    ref = schema.get("$ref")
    if isinstance(ref, str):
        try:
            errors.extend(_schema_errors(value, _resolve_local_ref(root_schema, ref), root_schema, path))
        except ValueError as exc:
            errors.append(f"{path}: {exc}")

    expected_types = schema.get("type")
    if expected_types is not None:
        types = expected_types if isinstance(expected_types, list) else [expected_types]
        if not any(isinstance(item, str) and _schema_type_matches(value, item) for item in types):
            return [f"{path}: expected type {types}, got {type(value).__name__}"] + errors

    if "const" in schema and not _json_equal(value, schema["const"]):
        errors.append(f"{path}: expected constant {schema['const']!r}, got {value!r}")
    if "enum" in schema and not any(_json_equal(value, item) for item in schema["enum"]):
        errors.append(f"{path}: value {value!r} is not in enum {schema['enum']!r}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{path}: string length {len(value)} is below minLength {min_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.search(pattern, value) is None:
                    errors.append(f"{path}: value {value!r} does not match pattern {pattern!r}")
            except re.error as exc:
                errors.append(f"{path}: invalid schema pattern {pattern!r}: {exc}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}: value {value} is below minimum {minimum}")
        exclusive_minimum = schema.get("exclusiveMinimum")
        if isinstance(exclusive_minimum, (int, float)) and value <= exclusive_minimum:
            errors.append(
                f"{path}: value {value} is not above exclusiveMinimum {exclusive_minimum}"
            )
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{path}: value {value} exceeds maximum {maximum}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path}: item count {len(value)} is below minItems {min_items}")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path}: item count {len(value)} exceeds maxItems {max_items}")
        if schema.get("uniqueItems") is True:
            encoded = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: array items must be unique")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                errors.extend(_schema_errors(item, item_schema, root_schema, f"{path}[{index}]"))
        if "contains" in schema and not any(
            not _schema_errors(item, schema["contains"], root_schema, f"{path}[{index}]")
            for index, item in enumerate(value)
        ):
            errors.append(f"{path}: no array item satisfies contains")

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for field in required:
                if field not in value:
                    errors.append(f"{path}: missing required property {field!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for field, field_schema in properties.items():
                if field in value:
                    errors.extend(
                        _schema_errors(value[field], field_schema, root_schema, f"{path}.{field}")
                    )
            if schema.get("additionalProperties") is False:
                for field in value.keys() - properties.keys():
                    errors.append(f"{path}: additional property {field!r} is not allowed")
        min_properties = schema.get("minProperties")
        if isinstance(min_properties, int) and len(value) < min_properties:
            errors.append(f"{path}: property count {len(value)} is below minProperties {min_properties}")

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for index, branch in enumerate(all_of):
            errors.extend(_schema_errors(value, branch, root_schema, f"{path}<allOf:{index}>"))

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        match_count = sum(
            not _schema_errors(value, branch, root_schema, path) for branch in one_of
        )
        if match_count != 1:
            errors.append(f"{path}: oneOf requires exactly one matching branch; got {match_count}")

    if "not" in schema and not _schema_errors(value, schema["not"], root_schema, path):
        errors.append(f"{path}: value matches a forbidden schema")

    condition = schema.get("if")
    if condition is not None:
        condition_matches = not _schema_errors(value, condition, root_schema, path)
        selected = schema.get("then") if condition_matches else schema.get("else")
        if selected is not None:
            branch_name = "then" if condition_matches else "else"
            errors.extend(_schema_errors(value, selected, root_schema, f"{path}<{branch_name}>"))

    return errors


def normalize_pre_quality_identifiers(value: Any) -> Any:
    """Map serialized pre-quality identifiers to neutral current aliases."""

    if isinstance(value, dict):
        return {
            key: normalize_pre_quality_identifiers(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [normalize_pre_quality_identifiers(child) for child in value]
    if isinstance(value, str):
        return PRE_QUALITY_IDENTIFIER_MAP.get(value, value)
    return copy.deepcopy(value)


def validate_structure(
    state: dict[str, Any], schema_path: Path = PROJECT_STATE_SCHEMA, *,
    allow_pre_quality_import: bool = False,
) -> list[str]:
    """Return structural errors, widening only the explicit earlier-generation import boundary."""

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"schema loader: cannot read {schema_path}: {exc}"]
    if not isinstance(schema, dict):
        return [f"schema loader: top-level schema must be an object: {schema_path}"]
    validation_state = (
        normalize_pre_quality_identifiers(state) if allow_pre_quality_import else state
    )
    if allow_pre_quality_import and validation_state.get("schema_version") == ALPHA7_SCHEMA_VERSION:
        if isinstance(schema.get("required"), list):
            for field in ("prompt_quality_records",):
                if field in schema["required"]:
                    schema["required"].remove(field)

        def relax_pre_quality_prompt_fields(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                required = node.get("required")
                if isinstance(required, list):
                    if "prompt_sections" in required:
                        required.remove("prompt_sections")
                    if isinstance(properties, dict) and {
                        "shot_id", "duration_seconds", "generation_required"
                    } <= set(properties):
                        for field in ("state_in", "required_event", "planned_state_out"):
                            if field in required:
                                required.remove(field)
                    if isinstance(properties, dict) and "prompt_layer" in properties:
                        for field in (
                            "target_type", "target_id", "generation_role", "generation_medium",
                            "execution_contract",
                        ):
                            if field in required:
                                required.remove(field)
                    if isinstance(properties, dict) and {
                        "task_id", "task_type", "provider_prompt_ids"
                    } <= set(properties) and "generation_targets" in required:
                        required.remove("generation_targets")
                    if isinstance(properties, dict) and {
                        "pilot_id", "scope", "provider_registry_ids"
                    } <= set(properties):
                        for field in ("asset_ids", "prompt_ids", "generation_targets"):
                            if field in required:
                                required.remove(field)
                for child in node.values():
                    relax_pre_quality_prompt_fields(child)
            elif isinstance(node, list):
                for child in node:
                    relax_pre_quality_prompt_fields(child)

        relax_pre_quality_prompt_fields(schema)
    if validation_state.get("schema_version") is None:
        # earlier-generation fixtures remain migration inputs, but TEXT_SPEC_COMPLETE is not part
        # of the Alpha.7 machine contract. Widen only spec_status while importing.
        def widen_legacy_generation_spec_status(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    spec_schema = properties.get("spec_status")
                    if isinstance(spec_schema, dict):
                        enum = spec_schema.get("enum")
                        if isinstance(enum, list) and "TEXT_SPEC_COMPLETE" not in enum:
                            enum.append("TEXT_SPEC_COMPLETE")
                        if spec_schema.get("const") == "SPEC_READY":
                            spec_schema["const"] = "TEXT_SPEC_COMPLETE"
                    if {"stage", "result", "workflow_status", "terminal_markers"} <= set(properties):
                        properties.setdefault(
                            "completion_status",
                            {
                                "enum": [
                                    "NOT_STARTED", "SPEC_DRAFT", "TEXT_SPEC_COMPLETE",
                                    "EXECUTION_PENDING", "SIMULATED_ONLY", "QA_NOT_EXECUTED",
                                    "VALIDATED", "LOCKED", "ACCEPTED_WITH_DEBT", "BLOCKED",
                                ]
                            },
                        )
                        properties.setdefault("gate", {"type": "string"})
                        properties.setdefault("evidence", {"type": "array"})
                for child in node.values():
                    widen_legacy_generation_spec_status(child)
            elif isinstance(node, list):
                for child in node:
                    widen_legacy_generation_spec_status(child)

        widen_legacy_generation_spec_status(schema)
        for field in (
            "schema_version", "master_prompts", "provider_neutral_drafts",
            "reference_registry", "spec_completion_records",
            "format_profiles", "output_complexity_profile", "project_route", "task_graph",
            "execution_receipts", "fourfold_preflight_records", "minor_safety_profiles",
            "dialogue_inventory", "tts_coverage_records", "subtitle_cues",
            "prompt_quality_records",
        ):
            if isinstance(schema.get("required"), list) and field in schema["required"]:
                schema["required"].remove(field)

        def relax_legacy_generation_compiled_prompt(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                required = node.get("required")
                if (
                    isinstance(properties, dict)
                    and {"id", "provider", "shot_id", "prompt_text"} <= set(properties)
                    and "master_prompt_id" in properties
                    and isinstance(required, list)
                ):
                    for field in (
                        "prompt_layer", "master_prompt_id", "provider_neutral_draft_id",
                        "target_type", "target_id", "generation_role", "generation_medium",
                        "provider_registry_id", "provider_snapshot_id", "reference_ids",
                        "minor_safety_profile_ids", "source_spec_version",
                        "capability_evidence_ids", "requested_output_duration_seconds",
                        "editorial_target_duration_seconds", "trim_to_editorial",
                        "execution_contract",
                    ):
                        if field in required:
                            required.remove(field)
                    # earlier-generation compiled prompts predate both the PD backlink and
                    # the current TP/NEP chain.  Keep the locale branch, but do
                    # not apply the mutually-exclusive Alpha.7 chain selector
                    # while validating this explicit import surface.
                    all_of = node.get("allOf")
                    if isinstance(all_of, list):
                        node["allOf"] = [
                            branch
                            for branch in all_of
                            if not (isinstance(branch, dict) and "oneOf" in branch)
                        ]
                for child in node.values():
                    relax_legacy_generation_compiled_prompt(child)
            elif isinstance(node, list):
                for child in node:
                    relax_legacy_generation_compiled_prompt(child)

        relax_legacy_generation_compiled_prompt(schema)

        def relax_legacy_generation_gate(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                required = node.get("required")
                if (
                    isinstance(properties, dict)
                    and {"gate_id", "gate_type", "evaluation_status", "outcome"} <= set(properties)
                ):
                    properties["evaluation_status"] = {"enum": ["NOT_EXECUTED", "EXECUTED"]}
                    properties["outcome"] = {
                        "enum": [
                            "UNKNOWN", "PASSED", "FAILED", "BLOCKED",
                            "ACCEPTED_WITH_DEBT", "NOT_APPLICABLE",
                        ]
                    }
                    requirement_ids_schema = properties.get("requirement_ids")
                    if isinstance(requirement_ids_schema, dict):
                        requirement_ids_schema.pop("minItems", None)
                    requirement_results_schema = properties.get("requirement_results")
                    if isinstance(requirement_results_schema, dict):
                        requirement_results_schema.pop("minItems", None)
                    if isinstance(required, list) and "scope_bindings" in required:
                        required.remove("scope_bindings")
                for child in node.values():
                    relax_legacy_generation_gate(child)
            elif isinstance(node, list):
                for child in node:
                    relax_legacy_generation_gate(child)

        relax_legacy_generation_gate(schema)

        def relax_legacy_generation_current_only_fields(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                required = node.get("required")
                if isinstance(properties, dict) and isinstance(required, list):
                    if {
                        "provider_id", "provider", "model", "version", "region",
                        "project_pilot_status",
                    } <= set(properties):
                        for field in (
                            "display_name", "marketing_aliases", "surface", "api_model_id",
                            "snapshot_id", "availability_kind",
                        ):
                            if field in required:
                                required.remove(field)
                    if {"task_id", "task_type", "provider_prompt_ids"} <= set(properties):
                        if "provider_neutral_draft_ids" in required:
                            required.remove("provider_neutral_draft_ids")
                        if "generation_targets" in required:
                            required.remove("generation_targets")
                    if {"pilot_id", "scope", "provider_registry_ids"} <= set(properties):
                        for field in ("asset_ids", "prompt_ids", "generation_targets"):
                            if field in required:
                                required.remove(field)
                    if {"receipt_id", "task_id", "executor"} <= set(properties):
                        for field in ("provider_snapshot_id", "provider_prompt_ids"):
                            if field in required:
                                required.remove(field)
                    if {"shot_id", "duration_seconds", "generation_required"} <= set(properties):
                        for field in (
                            "state_in", "required_event", "planned_state_out",
                            "duration_semantics", "duration_source_or_evidence_ids",
                            "duration_provider_registry_id", "provider_neutral_draft_ids",
                            "master_prompt_ids", "dialogue_ids", "minor_adult_same_shot",
                            "minor_adult_same_shot_strategy", "decomposition_shot_ids",
                            "composite_plan_artifact_id",
                        ):
                            if field in required:
                                required.remove(field)
                    if {"id", "asset_type", "shot_refs"} <= set(properties):
                        for field in ("subject_age_class", "minor_safety_profile_id"):
                            if field in required:
                                required.remove(field)
                    if "prompt_sections" in required:
                        required.remove("prompt_sections")
                    if {
                        "spec_status", "execution_status", "observation_status", "qa_status",
                        "publication_status", "learning_status",
                    } <= set(properties) and "status_basis" in required:
                        required.remove("status_basis")
                    if {
                        "observation_id", "artifact_id", "media_accessible", "ncs", "nrs",
                    } <= set(properties) and "artifact_version" in required:
                        required.remove("artifact_version")
                    if {"stage", "result", "workflow_status", "terminal_markers"} <= set(properties):
                        if "snapshot_kind" in required:
                            required.remove("snapshot_kind")
                    if {"audit_status", "validation_attempts", "correction_records"} <= set(properties):
                        properties["audit_status"] = {"enum": ["NOT_EXECUTED", "EXECUTED"]}
                        properties["history_completeness"] = {
                            "enum": ["COMPLETE", "LEGACY_UNKNOWN"]
                        }
                        properties["final_validation_attempt_id"] = {
                            "type": ["string", "null"], "pattern": "^VA-"
                        }
                        properties.setdefault("errors_found", {"type": "array"})
                        properties.setdefault("errors_fixed", {"type": "array"})
                        properties.setdefault(
                            "unresolved_issue_ids",
                            {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                        )
                        for field in (
                            "history_completeness", "validation_attempts", "correction_records",
                            "unresolved_violation_ids", "final_validation_attempt_id",
                        ):
                            if field in required:
                                required.remove(field)
                for child in node.values():
                    relax_legacy_generation_current_only_fields(child)
            elif isinstance(node, list):
                for child in node:
                    relax_legacy_generation_current_only_fields(child)

        relax_legacy_generation_current_only_fields(schema)

        def relax_legacy_generation_truth_fields(node: Any) -> None:
            if isinstance(node, dict):
                condition = node.get("if")
                then = node.get("then")
                if isinstance(condition, dict) and isinstance(then, dict):
                    condition_properties = condition.get("properties")
                    if isinstance(condition_properties, dict):
                        status = condition_properties.get("status")
                        if (
                            isinstance(status, dict)
                            and isinstance(status.get("enum"), list)
                            and "REAL_ARTIFACT_AVAILABLE" in status["enum"]
                            and isinstance(then.get("required"), list)
                            and "content_locator" in then["required"]
                        ):
                            then["required"].remove("content_locator")
                        accessible = condition_properties.get("media_accessible")
                        if (
                            isinstance(accessible, dict)
                            and accessible.get("const") is True
                            and isinstance(then.get("required"), list)
                            and "artifact_version" in then["required"]
                        ):
                            then["required"].remove("artifact_version")
                        artifact_class = condition_properties.get("artifact_class")
                        if (
                            isinstance(artifact_class, dict)
                            and artifact_class.get("const") == "TEXT_SPEC"
                        ):
                            node["then"] = {}
                for child in node.values():
                    relax_legacy_generation_truth_fields(child)
            elif isinstance(node, list):
                for child in node:
                    relax_legacy_generation_truth_fields(child)

        relax_legacy_generation_truth_fields(schema)
    structure_errors = _schema_errors(validation_state, schema, schema, "$")
    rendered: list[str] = []
    for error in structure_errors:
        if "stage_results" in error and any(
            f"additional property '{field}'" in error
            for field in ("completion_status", "gate", "evidence")
        ):
            rendered.append(f"schema E_STAGE_LEGACY_FIELD {error}")
        else:
            rendered.append(f"schema {error}")
    return rendered


def contains_cjk(value: Any) -> bool:
    return isinstance(value, str) and bool(CJK_RE.search(value))


def is_zh_locale(value: Any) -> bool:
    return isinstance(value, str) and bool(re.match(r"^zh(?:-|$)", value, flags=re.IGNORECASE))


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def records_by(items: list[Any], key: str) -> dict[str, dict[str, Any]]:
    return {
        str(item[key]): item
        for item in items
        if isinstance(item, dict) and item.get(key) is not None
    }


def index_unique(
    items: list[Any], key: str, label: str, errors: list[str]
) -> dict[str, dict[str, Any]]:
    """Index a ledger only after reporting missing and duplicate stable IDs."""

    index: dict[str, dict[str, Any]] = {}
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        raw_id = item.get(key)
        if raw_id is None or not str(raw_id).strip():
            errors.append(
                f"E_LEDGER_MISSING_ID {label}: record at index {position} requires non-empty {key}"
            )
            continue
        record_id = str(raw_id)
        if record_id in index:
            errors.append(f"E_LEDGER_DUPLICATE_ID {label}: duplicate {key} {record_id}")
            continue
        index[record_id] = item
    return index


def evidence_scope(record: dict[str, Any]) -> dict[str, Any]:
    scope = record.get("scope")
    return scope if isinstance(scope, dict) else {}


def scope_list(scope: dict[str, Any], field: str) -> set[str]:
    return set(map(str, as_list(scope.get(field))))


def evidence_applies_to_provider(
    record: dict[str, Any], provider_id: str, provider: dict[str, Any]
) -> bool:
    """Require the immutable provider snapshot ID and reject conflicting legacy details."""

    scope = evidence_scope(record)
    if provider_id not in scope_list(scope, "provider_registry_ids"):
        return False
    field_map = {
        "provider": "provider",
        "model": "model",
        "version": "version",
        "region": "region",
        "surface": "surface",
        "snapshot_id": "snapshot_id",
        "provider_checked_at": "checked_at",
    }
    for field, provider_field in field_map.items():
        if field in scope and str(scope.get(field)) != str(provider.get(provider_field)):
            return False
    return True


def versioned_refs(value: Any) -> set[tuple[str, str]]:
    """Return immutable (artifact_id, version) pairs from a typed scope."""

    return {
        (str(item.get("artifact_id")), str(item.get("version")))
        for item in as_list(value)
        if isinstance(item, dict)
        and nonempty(item.get("artifact_id"))
        and nonempty(item.get("version"))
    }


def evidence_covers_gate_scope(record: dict[str, Any], binding: dict[str, Any]) -> bool:
    """Return whether one evidence record covers every non-empty Gate scope dimension."""

    scope = evidence_scope(record)
    for field in (
        "asset_ids", "provider_registry_ids", "pilot_ids", "shot_plan_ids",
        "format_variant_ids", "task_types", "prompt_ids", "observation_ids",
    ):
        required = scope_list(binding, field)
        if required and not required <= scope_list(scope, field):
            return False
    required_artifact_ids = scope_list(binding, "artifact_ids")
    evidence_artifact_refs = versioned_refs(scope.get("artifact_refs"))
    if required_artifact_ids and not required_artifact_ids <= {
        artifact_id for artifact_id, _version in evidence_artifact_refs
    }:
        return False
    evidence_package_refs = versioned_refs(scope.get("package_refs"))
    required_versions = versioned_refs(binding.get("artifact_versions"))
    if required_versions and not required_versions <= evidence_artifact_refs | evidence_package_refs:
        return False
    required_packages = scope_list(binding, "release_package_ids")
    evidence_packages = scope_list(scope, "release_package_ids") | {
        artifact_id for artifact_id, _version in evidence_package_refs
    }
    if required_packages and not required_packages <= evidence_packages:
        return False
    for field in ("task_scope", "format_scope"):
        required_value = binding.get(field)
        if nonempty(required_value) and str(scope.get(field, "")) != str(required_value):
            return False
    version_scope = binding.get("version_scope")
    if nonempty(version_scope) and str(
        scope.get("version_scope", scope.get("source_spec_version", ""))
    ) != str(version_scope):
        return False
    return True


def state_subject_digest(state: dict[str, Any]) -> str:
    """Digest the validated subject without its self-referential cleanup history."""

    subject = json.loads(json.dumps(state, ensure_ascii=False))
    cleanup = subject.get("state_cleanup")
    if isinstance(cleanup, dict):
        for field in (
            "validation_attempts", "correction_records", "final_validation_attempt_id",
            "checked_at",
        ):
            cleanup.pop(field, None)
    encoded = json.dumps(
        subject, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ids(items: list[Any], key: str) -> set[str]:
    return set(records_by(items, key))


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalized_prompt_text(value: Any) -> str:
    """Normalize only representation noise; never rewrite creative semantics."""

    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip().casefold()


def substantive_prompt_text(value: Any) -> bool:
    """Reject one-token placeholders without imposing a cross-provider word quota."""

    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKC", value).strip()
    units = re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFF]|[A-Za-z]+|\d+", normalized)
    compact = "".join(units).casefold()
    return len(units) >= 2 and len(set(compact)) >= 2


DIRECTOR_GENERIC_FILLER_RE = re.compile(
    r"(?:自然真实|真实自然|保持自然|保持真实|电影感| cinematic |cinematic|高质量|"
    r"精美画面|画面精美|细节丰富|氛围感|高级感|专业感|保持明确|状态明确|"
    r"动作自然|镜头自然|合理顺畅|清晰稳定|realistic|natural|high quality|"
    r"beautiful|detailed|smooth|professional)",
    re.I,
)


def substantive_director_source(value: Any) -> bool:
    """Reject attractive filler while keeping genre/profile language unconstrained."""

    if not substantive_prompt_text(value):
        return False
    residual = DIRECTOR_GENERIC_FILLER_RE.sub(" ", unicodedata.normalize("NFKC", str(value)))
    residual = re.sub(r"\b(?:S|SHOT|BEAT|镜头|第)\s*[-_]?\d+\b|第\s*\d+\s*拍", " ", residual, flags=re.I)
    units = re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFF]|[A-Za-z]+|\d+", residual)
    return len(units) >= 2 and len(set("".join(units).casefold())) >= 2


def director_signature_text(value: Any) -> str:
    """Compare beat substance without treating ordinal labels as creative variation."""

    normalized = normalized_prompt_text(value)
    normalized = re.sub(r"第\s*\d+\s*拍|\b(?:beat|shot)[-_ ]*\d+\b|\d+", " ", normalized, flags=re.I)
    return re.sub(r"\s+", " ", normalized).strip()


def prompt_density_anchor(duration_seconds: Any) -> tuple[str, int | None, int | None]:
    """Return the Alpha.7 Master dynamic beat band; the band is an anchor, not a text quota."""

    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)):
        return "INVALID", None, None
    duration = float(duration_seconds)
    if duration <= 0:
        return "INVALID", None, None
    anchor_second = math.ceil(duration)
    if anchor_second < 4:
        return "SHORT_INSERT", 1, 2
    if anchor_second <= 7:
        return "D04_07", 2, 3
    if anchor_second <= 12:
        return "D08_12", 3, 5
    if anchor_second <= 18:
        return "D13_18", 4, 6
    if anchor_second <= 24:
        return "D19_24", 6, 8
    if anchor_second <= 30:
        return "D25_30", 8, 10
    return "SPLIT_REQUIRED", None, None


def prompt_soul_digest(artifact_ids: Any, artifact_by_id: dict[str, dict[str, Any]]) -> str | None:
    """Hash the exact text-spec id/version/content-hash set behind a prompt soul."""

    rows: list[dict[str, str]] = []
    ids = list(map(str, as_list(artifact_ids)))
    if not ids or len(ids) != len(set(ids)):
        return None
    for artifact_id in sorted(ids):
        artifact = artifact_by_id.get(artifact_id)
        locator = artifact.get("content_locator") if isinstance(artifact, dict) else None
        sha256 = locator.get("sha256") if isinstance(locator, dict) else None
        version = artifact.get("version") if isinstance(artifact, dict) else None
        artifact_type = re.sub(r"[-\s]+", "_", str(artifact.get("type", "")).strip().lower())
        if (
            not artifact or artifact.get("artifact_class") != "TEXT_SPEC"
            or artifact_type not in PROMPT_SOUL_ARTIFACT_TYPES
            or artifact.get("status") not in PROMPT_SOUL_ARTIFACT_STATUSES
            or not nonempty(version) or not isinstance(sha256, str)
            or re.fullmatch(r"[A-Fa-f0-9]{64}", sha256) is None
        ):
            return None
        rows.append(
            {
                "artifact_id": artifact_id,
                "version": str(version),
                "content_sha256": sha256.lower(),
            }
        )
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def exact_text_sha256(value: Any) -> str:
    """Hash the exact Unicode Prompt body; whitespace and punctuation are evidence."""

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def reference_delta_digest(value: Any) -> str | None:
    """Hash one normalized reference change contract for review invalidation."""

    if not isinstance(value, dict):
        return None
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_atom_inventory_digest(source_atom_ids: Any) -> str | None:
    ids = sorted(map(str, as_list(source_atom_ids)))
    if not ids or len(ids) != len(set(ids)) or any(
        re.fullmatch(r"SRC\d{4,}", source_id) is None for source_id in ids
    ):
        return None
    canonical = json.dumps(ids, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def positive_anchor_occurs(fragment: str, anchor: str) -> bool:
    """Require an anchor as a positive instruction, not merely inside a negation."""

    if not anchor:
        return False
    cursor = 0
    while True:
        index = fragment.find(anchor, cursor)
        if index < 0:
            return False
        prefix = re.split(r"[。！？；;,.!?\n\r]", fragment[max(0, index - 64):index])[-1]
        if re.search(
            r"(?:不要|不得|禁止|避免|不能|不可|并非|没有|切勿|别|严禁|勿|杜绝|"
            r"not|never|without|\bno\b)",
            prefix,
            re.I,
        ) is None:
            return True
        cursor = index + max(1, len(anchor))


def prompt_target_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record.get("target_type", "")),
        str(record.get("target_id", "")),
        str(record.get("source_spec_version", "")),
        str(record.get("generation_role", "")),
    )


def generation_role_matches_medium(role: Any, medium: Any) -> bool:
    role_text = str(role)
    medium_text = str(medium)
    if role_text in IMAGE_ONLY_GENERATION_ROLES:
        return medium_text == "IMAGE"
    if role_text in VIDEO_ONLY_GENERATION_ROLES:
        return medium_text == "VIDEO"
    if role_text == "ASSET_REFERENCE":
        return medium_text == "IMAGE"
    return role_text == "CUSTOM" and medium_text in {"IMAGE", "VIDEO"}


def inspect_prompt_sections(
    *, label: str, text: Any, sections: Any, atom_ids: set[str], beat_ids: set[str]
) -> tuple[list[str], dict[str, dict[str, Any]], set[str], set[str], set[str]]:
    """Validate no-copy code-point spans and return their resolved coverage."""

    findings: list[str] = []
    section_by_id: dict[str, dict[str, Any]] = {}
    covered_atoms: set[str] = set()
    covered_beats: set[str] = set()
    kinds: set[str] = set()
    if not substantive_prompt_text(text):
        findings.append(
            f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: Prompt正文没有足够的可执行语义"
        )
    if not isinstance(text, str) or not isinstance(sections, list) or not sections:
        findings.append(
            f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: prompt_sections 必须覆盖唯一正文"
        )
        return findings, section_by_id, covered_atoms, covered_beats, kinds

    cursor = 0
    normalized_slices: set[str] = set()
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            findings.append(
                f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: section {index} 必须是对象"
            )
            continue
        section_id = str(section.get("section_id", ""))
        if not section_id or section_id in section_by_id:
            findings.append(
                f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: section_id 缺失或重复 {section_id!r}"
            )
        else:
            section_by_id[section_id] = section
        if section.get("order") != index:
            findings.append(
                f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: section order 必须从1连续排列"
            )
        start = section.get("start_char")
        end = section.get("end_char")
        if (
            isinstance(start, bool) or not isinstance(start, int)
            or isinstance(end, bool) or not isinstance(end, int)
            or start != cursor or end <= start or end > len(text)
        ):
            findings.append(
                f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: section {section_id or index} "
                "未按Unicode索引连续覆盖正文"
            )
            if isinstance(end, int) and not isinstance(end, bool):
                cursor = max(cursor, end)
            continue
        fragment = text[start:end]
        cursor = end
        normalized = normalized_prompt_text(fragment)
        if not substantive_prompt_text(fragment):
            findings.append(
                f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: section {section_id} 是空壳"
            )
        elif normalized in normalized_slices:
            findings.append(
                f"PQ_BEAT_CONTRACT_THIN {label}: section {section_id} 重复正文以凑结构"
            )
        normalized_slices.add(normalized)
        kind = str(section.get("kind", ""))
        if kind not in PROMPT_SECTION_KINDS:
            findings.append(f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: section kind 无效 {kind!r}")
        kinds.add(kind)
        section_atoms = set(map(str, as_list(section.get("atom_ids"))))
        section_beats = set(map(str, as_list(section.get("beat_ids"))))
        if section_atoms - atom_ids:
            findings.append(
                f"PQ_ASSET_OR_REFERENCE_DRIFT {label}: section {section_id} 引用未知atom"
            )
        if section_beats - beat_ids:
            findings.append(
                f"PQ_BEAT_CONTRACT_THIN {label}: section {section_id} 引用未知beat"
            )
        covered_atoms |= section_atoms
        covered_beats |= section_beats
    if cursor != len(text):
        findings.append(
            f"PQ_TRIVIAL_OR_SUMMARY_ONLY {label}: sections 未精确结束于正文长度 {len(text)}"
        )
    return findings, section_by_id, covered_atoms, covered_beats, kinds


def parse_iso_timestamp(value: Any) -> datetime | None:
    """Parse a date or ISO-8601 timestamp into UTC for deterministic freshness checks."""

    if not nonempty(value):
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def inferred_execution_domain(task: dict[str, Any]) -> str:
    """Infer legacy receipts without letting media tasks masquerade as local checks."""

    task_type = str(task.get("task_type", ""))
    if task_type in PRODUCTION_MEDIA_TASK_TYPES:
        return "PRODUCTION_MEDIA"
    if task_type in LOCAL_VALIDATION_TASK_TYPES or task.get("domain") in {
        "EVIDENCE", "OBSERVATION", "QA", "FOURFOLD_PREFLIGHT",
    }:
        return "LOCAL_VALIDATION"
    return "LOCAL_TEXT_TOOL"


def effective_execution_domain(
    receipt: dict[str, Any], task: dict[str, Any]
) -> str:
    """Use the explicit earlier current-schema domain, with a narrow legacy inference fallback."""

    value = receipt.get("execution_domain")
    return str(value) if nonempty(value) else inferred_execution_domain(task)


def english_only_paragraphs(value: Any) -> list[str]:
    """Find substantial English-only creator-facing paragraphs, ignoring machine-like lines."""

    if not isinstance(value, str):
        return []
    findings: list[str] = []
    for paragraph in re.split(r"\n\s*\n|(?<=\.)\s{2,}", value):
        plain = paragraph.strip().lstrip("#>-* ")
        if not plain or CJK_RE.search(plain):
            continue
        words = LATIN_WORD_RE.findall(plain)
        machine_tokens = re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b|https?://\S+|`[^`]+`", plain)
        if len(words) >= 6 and len(machine_tokens) < len(words) / 2:
            findings.append(plain[:120])
    return findings


def gate_passed(gates: list[Any], gate_type: str) -> bool:
    return any(
        isinstance(gate, dict)
        and gate.get("gate_type") == gate_type
        and gate.get("evaluation_status") == "EXECUTED"
        and gate.get("outcome") in {"PASSED", "ACCEPTED_WITH_DEBT"}
        for gate in gates
    )


def validate(
    state: dict[str, Any], *, allow_legacy_import: bool = False,
    allow_pre_quality_import: bool = False,
) -> list[str]:
    if allow_pre_quality_import:
        state = normalize_pre_quality_identifiers(state)
    errors: list[str] = []
    legacy_generation = isinstance(state.get("workflow_status"), dict)
    alpha7 = state.get("schema_version") == ALPHA7_SCHEMA_VERSION
    current_quality_contract = alpha7 and not allow_pre_quality_import
    if state.get("schema_version") is not None and not alpha7:
        errors.append(
            f"schema_version: unsupported strict state version {state.get('schema_version')!r}"
        )
    if not legacy_generation and not allow_legacy_import:
        errors.append(
            "workflow_status: missing six-axis earlier-generation state; use --allow-legacy-import only during migration"
        )

    language_policy = state.get("language_policy")
    if language_policy is None:
        effective_output_locale = "zh-CN"
        if not allow_legacy_import:
            errors.append("language_policy: missing; migrate legacy state before strict validation")
    elif not isinstance(language_policy, dict):
        errors.append("language_policy: must be an object")
        effective_output_locale = "zh-CN"
    else:
        effective_output_locale = language_policy.get("effective_output_locale", "zh-CN")
        language_source = language_policy.get("source", "DEFAULT")
        if language_source == "DEFAULT" and effective_output_locale != "zh-CN":
            errors.append("language_policy: DEFAULT must resolve to zh-CN")
        if language_source == "USER_EXPLICIT" and not nonempty(language_policy.get("user_quote")):
            errors.append("language_policy: USER_EXPLICIT requires user_quote")
        if language_source not in {"DEFAULT", "USER_EXPLICIT"}:
            errors.append("language_policy: source must be DEFAULT or USER_EXPLICIT")

    language_profile = state.get("language_profile")
    if isinstance(language_profile, dict):
        interaction_language = language_profile.get("interaction_language")
        if interaction_language and interaction_language != effective_output_locale:
            errors.append("language_profile: interaction_language does not match effective_output_locale")

    workflow = state.get("workflow_status") if legacy_generation else {}
    terminal_markers = set(map(str, as_list(state.get("terminal_markers"))))
    if terminal_markers - TERMINAL_MARKERS:
        errors.append(f"terminal_markers: unknown values {sorted(terminal_markers - TERMINAL_MARKERS)}")
    if len(terminal_markers) > 1:
        errors.append("terminal_markers: simulation and real-production terminals are mutually exclusive")
    if "REAL_PRODUCTION_COMPLETE" in terminal_markers:
        expected = {
            "execution_status": {"EXECUTED_SUCCEEDED"},
            "observation_status": {"OBSERVED"},
            "qa_status": {"QA_PASSED", "QA_ACCEPTED_WITH_DEBT"},
            "publication_status": {"RELEASE_READY", "PUBLISH_PENDING", "PUBLISHED"},
        }
        if state.get("execution_mode") != "REAL":
            errors.append("REAL_PRODUCTION_COMPLETE requires execution_mode=REAL")
        for field, allowed in expected.items():
            if workflow.get(field) not in allowed:
                errors.append(f"REAL_PRODUCTION_COMPLETE: {field}={workflow.get(field)!r} is impossible")

    for stage_result in as_list(state.get("stage_results")):
        if not isinstance(stage_result, dict):
            errors.append("stage result must be an object")
            continue
        stage_name = stage_result.get("stage", "<stage>")
        output_locale = stage_result.get("output_locale", effective_output_locale)
        if output_locale != effective_output_locale:
            errors.append(f"{stage_name}: output_locale does not match effective_output_locale")
        if is_zh_locale(output_locale):
            for field in ("result", "recommendation", "insight", "next_action"):
                value = stage_result.get(field)
                if value is not None and str(value).strip() and not contains_cjk(value):
                    errors.append(f"{stage_name}: creator-facing field {field} must contain Chinese text for zh-CN")
        stage_workflow = stage_result.get("workflow_status")
        if not isinstance(stage_workflow, dict):
            if legacy_generation:
                errors.append(f"{stage_name}: stage_result requires six-axis workflow_status")
        elif stage_result.get("execution_mode") == "SIMULATION":
            if stage_workflow.get("observation_status") == "OBSERVED":
                errors.append(f"{stage_name}: simulated stage cannot claim OBSERVED")
            if stage_workflow.get("qa_status") in {"QA_PASSED", "QA_ACCEPTED_WITH_DEBT"}:
                errors.append(f"{stage_name}: simulated stage cannot claim media QA success")
            if stage_workflow.get("publication_status") == "PUBLISHED":
                errors.append(f"{stage_name}: simulated stage cannot claim PUBLISHED")
        for field in ("result", "recommendation", "insight", "next_action"):
            for paragraph in english_only_paragraphs(stage_result.get(field)):
                errors.append(f"{stage_name}: creator-facing field {field} contains English-only paragraph: {paragraph!r}")

    decisions = as_list(state.get("decisions"))
    approvals = as_list(state.get("approval_events"))
    evidence = as_list(state.get("evidence_registry"))
    artifacts = as_list(state.get("artifacts"))
    issues = as_list(state.get("open_issues"))
    protected_unknowns = as_list(state.get("protected_unknowns"))
    quantities = as_list(state.get("quantity_semantics"))
    causal_boundaries = as_list(state.get("causal_boundaries"))
    baselines = as_list(state.get("baseline_specs"))
    pilot_assessments = as_list(state.get("pilot_assessments"))
    reference_registry = as_list(state.get("reference_registry"))
    master_prompts = as_list(state.get("master_prompts"))
    provider_neutral_drafts = as_list(state.get("provider_neutral_drafts"))
    transform_plans = as_list(state.get("transform_plans"))
    neutral_execution_prompts = as_list(state.get("neutral_execution_prompts"))
    prompt_contract_version = state.get("prompt_contract_version")
    four_layer_prompt_contract = prompt_contract_version == "4.0"
    if prompt_contract_version not in {None, "4.0"}:
        errors.append(
            f"E_PROMPT_LAYER_CONTRACT prompt_contract_version: unsupported value "
            f"{prompt_contract_version!r}"
        )
    if not four_layer_prompt_contract and (
        "transform_plans" in state or "neutral_execution_prompts" in state
    ):
        errors.append(
            "E_PROMPT_LAYER_CONTRACT prompt_contract_version=4.0 is required before "
            "four-layer fields may be written"
        )
    spec_completion_records = as_list(state.get("spec_completion_records"))
    format_profiles = as_list(state.get("format_profiles"))
    project_route = state.get("project_route")
    task_graph = as_list(state.get("task_graph"))
    execution_receipts = as_list(state.get("execution_receipts"))
    fourfold_preflight_records = as_list(state.get("fourfold_preflight_records"))
    minor_safety_profiles = as_list(state.get("minor_safety_profiles"))
    dialogue_inventory = as_list(state.get("dialogue_inventory"))
    tts_coverage_records = as_list(state.get("tts_coverage_records"))
    subtitle_cues = as_list(state.get("subtitle_cues"))
    prompt_quality_records = as_list(state.get("prompt_quality_records"))
    if current_quality_contract:
        for required_field in (
            "master_prompts", "provider_neutral_drafts", "reference_registry",
            "spec_completion_records", "format_profiles", "task_graph",
            "execution_receipts", "fourfold_preflight_records", "minor_safety_profiles",
            "dialogue_inventory", "tts_coverage_records", "subtitle_cues",
            "prompt_quality_records",
        ):
            if not isinstance(state.get(required_field), list):
                errors.append(f"{required_field}: Alpha.7 requires an explicit array")
        if four_layer_prompt_contract:
            for required_field in ("transform_plans", "neutral_execution_prompts"):
                if not isinstance(state.get(required_field), list):
                    errors.append(
                        f"E_PROMPT_LAYER_CONTRACT {required_field}: four-layer contract "
                        "requires an explicit array"
                    )
            if provider_neutral_drafts:
                errors.append(
                    "E_LEGACY_PROMPT_LAYER_READ_ONLY provider_neutral_drafts: "
                    "PROVIDER_NEUTRAL_DRAFT is accepted only by the legacy read path"
                )
        if not isinstance(state.get("output_complexity_profile"), dict):
            errors.append("output_complexity_profile: Alpha.7 requires an explicit object")
        if not isinstance(project_route, dict):
            errors.append("project_route: Alpha.7 requires an explicit object")
    approval_by_id = index_unique(approvals, "id", "approval_events", errors)
    decision_by_id = index_unique(decisions, "id", "decisions", errors)
    evidence_by_id = index_unique(evidence, "evidence_id", "evidence_registry", errors)
    artifact_by_id = index_unique(artifacts, "id", "artifacts", errors)
    issue_by_id = index_unique(issues, "id", "open_issues", errors)
    unknown_by_id = index_unique(protected_unknowns, "unknown_id", "protected_unknowns", errors)
    quantity_by_id = index_unique(quantities, "quantity_id", "quantity_semantics", errors)
    boundary_by_id = index_unique(causal_boundaries, "boundary_id", "causal_boundaries", errors)
    baseline_by_id = index_unique(baselines, "baseline_id", "baseline_specs", errors)
    pilot_by_id = index_unique(pilot_assessments, "pilot_id", "pilot_assessments", errors)
    reference_by_id = index_unique(
        reference_registry, "reference_id", "reference_registry", errors
    )
    master_prompt_by_id = index_unique(master_prompts, "id", "master_prompts", errors)
    neutral_draft_by_id = index_unique(
        provider_neutral_drafts, "id", "provider_neutral_drafts", errors
    )
    transform_plan_by_id = index_unique(
        transform_plans, "id", "transform_plans", errors
    )
    neutral_execution_prompt_by_id = index_unique(
        neutral_execution_prompts, "id", "neutral_execution_prompts", errors
    )
    spec_completion_by_id = index_unique(
        spec_completion_records, "completion_id", "spec_completion_records", errors
    )
    format_by_id = index_unique(format_profiles, "format_id", "format_profiles", errors)
    task_by_id = index_unique(task_graph, "task_id", "task_graph", errors)
    receipt_by_id = index_unique(
        execution_receipts, "receipt_id", "execution_receipts", errors
    )
    preflight_by_id = index_unique(
        fourfold_preflight_records, "preflight_id", "fourfold_preflight_records", errors
    )
    minor_profile_by_id = index_unique(
        minor_safety_profiles, "profile_id", "minor_safety_profiles", errors
    )
    dialogue_by_id = index_unique(
        dialogue_inventory, "dialogue_id", "dialogue_inventory", errors
    )
    tts_coverage_by_id = index_unique(
        tts_coverage_records, "coverage_id", "tts_coverage_records", errors
    )
    subtitle_by_id = index_unique(subtitle_cues, "cue_id", "subtitle_cues", errors)
    prompt_quality_by_id = index_unique(
        prompt_quality_records, "id", "prompt_quality_records", errors
    )
    if alpha7:
        index_unique(as_list(state.get("flow_events")), "id", "flow_events", errors)
        for format_profile in format_profiles:
            if not isinstance(format_profile, dict):
                continue
            format_id = str(format_profile.get("format_id", "<format>"))
            format_evidence = set(map(str, as_list(format_profile.get("evidence_ids"))))
            if format_evidence - set(evidence_by_id):
                errors.append(
                    f"E_FORMAT_PROFILE_INVALID {format_id}: references unknown evidence"
                )
            source_decision_id = format_profile.get("source_decision_id")
            if source_decision_id is not None and str(source_decision_id) not in decision_by_id:
                errors.append(
                    f"E_FORMAT_PROFILE_INVALID {format_id}: source_decision_id is unresolved"
                )
            if format_profile.get("status") == "VALIDATED" and not format_evidence:
                errors.append(
                    f"E_FORMAT_PROFILE_INVALID {format_id}: VALIDATED format requires evidence"
                )
    open_blocking_ids = {
        str(item.get("id"))
        for item in issues
        if isinstance(item, dict)
        and item.get("status", "OPEN") == "OPEN"
        and item.get("severity") == "BLOCKING"
    }

    for approval in approvals:
        if not isinstance(approval, dict):
            errors.append("approval event must be an object")
            continue
        aid = approval.get("id", "<missing>")
        if approval.get("actor") != "USER" or approval.get("explicit") is not True:
            errors.append(f"{aid}: approval must be explicit and USER-authored")
        if not nonempty(approval.get("user_quote")):
            errors.append(f"{aid}: approval must preserve a user quote")
        if not as_list(approval.get("approved_decision_ids")) and not as_list(approval.get("approved_fields")):
            errors.append(f"{aid}: approval scope is empty")

    for decision in decisions:
        if not isinstance(decision, dict):
            errors.append("decision must be an object")
            continue
        did = decision.get("id", "<missing>")
        status = decision.get("status")
        approval_id = decision.get("approval_event_id")
        linked_evidence = set(map(str, as_list(decision.get("evidence_ids"))))
        blockers = set(map(str, as_list(decision.get("open_blocking_issue_ids"))))
        if status in {"USER_APPROVED", "LOCKED"} and approval_id not in approval_by_id:
            errors.append(f"{did}: {status} requires a valid approval_event_id")
        if status in {"VALIDATED", "LOCKED"}:
            if not linked_evidence:
                errors.append(f"{did}: {status} requires evidence_ids")
            missing = linked_evidence - set(evidence_by_id)
            if missing:
                errors.append(f"{did}: missing evidence records {sorted(missing)}")
            if not as_list(decision.get("validation_basis")):
                errors.append(f"{did}: {status} requires validation_basis")
        if status == "LOCKED":
            if not decision.get("lock_event_id") or not decision.get("lock_scope"):
                errors.append(f"{did}: LOCKED requires lock_event_id and lock_scope")
            if blockers or blockers.intersection(open_blocking_ids):
                errors.append(f"{did}: LOCKED while blocking issues remain")

    for stage_result in as_list(state.get("stage_results")):
        if not isinstance(stage_result, dict):
            continue
        visible_text = "\n".join(
            str(stage_result.get(field, ""))
            for field in ("result", "recommendation", "insight", "next_action")
        )
        locked_ids = set(map(str, as_list(stage_result.get("locked_decision_ids"))))
        if re.search(r"已锁定|正式锁定|\bLOCKED\b", visible_text, flags=re.IGNORECASE):
            if not locked_ids:
                errors.append(f"{stage_result.get('stage', '<stage>')}: visible lock claim requires locked_decision_ids")
            for decision_id in locked_ids:
                if decision_by_id.get(decision_id, {}).get("status") != "LOCKED":
                    errors.append(f"{stage_result.get('stage', '<stage>')}: visible lock claim references non-LOCKED decision {decision_id}")
        elif locked_ids:
            for decision_id in locked_ids:
                if decision_by_id.get(decision_id, {}).get("status") != "LOCKED":
                    errors.append(f"{stage_result.get('stage', '<stage>')}: locked_decision_ids contains non-LOCKED decision {decision_id}")

    for record in evidence:
        if not isinstance(record, dict):
            errors.append("evidence record must be an object")
            continue
        eid = record.get("evidence_id", "<evidence>")
        if legacy_generation:
            for field in (
                "claim_class", "claim_kind", "classification", "source", "published_at", "effective_at",
                "checked_at", "scope", "basis", "metric_definition", "sample_or_base", "limitations",
            ):
                if field not in record:
                    errors.append(f"{eid}: earlier-generation evidence missing {field}")
        precision = record.get("precision")
        if precision is not None:
            if not isinstance(precision, dict):
                errors.append(f"{eid}: precision must be an object or null")
            else:
                for field in ("quantity_id", "value", "unit", "basis", "source_or_evidence_ids", "precision_status"):
                    if field not in precision:
                        errors.append(f"{eid}: precision missing {field}")
                quantity_id = str(precision.get("quantity_id", ""))
                if quantity_id not in quantity_by_id:
                    errors.append(f"{eid}: precision references unknown quantity semantics {quantity_id!r}")
                if precision.get("precision_status") == "VERIFIED" and not as_list(precision.get("source_or_evidence_ids")):
                    errors.append(f"{eid}: VERIFIED precision requires source_or_evidence_ids")
                if precision.get("precision_status") == "VERIFIED":
                    precision_refs = set(map(str, as_list(precision.get("source_or_evidence_ids"))))
                    unknown_precision_refs = {
                        ref for ref in precision_refs if ref.startswith("E-") and ref not in evidence_by_id
                    }
                    if unknown_precision_refs:
                        errors.append(f"{eid}: VERIFIED precision references unknown evidence {sorted(unknown_precision_refs)}")
        if record.get("claim_kind") == "LEGAL_OR_PLATFORM":
            for field in ("actor", "duty", "trigger", "exceptions_or_conditions"):
                if not nonempty(record.get(field)):
                    errors.append(f"{eid}: legal/platform claim missing {field}")
        if record.get("claim_kind") == "PRECISION_METRIC" and not isinstance(precision, dict):
            errors.append(f"{eid}: precision metric requires structured precision")
        if record.get("classification") in {"VERIFIED_OFFICIAL", "VERIFIED_PRIMARY_RESEARCH"}:
            source = record.get("source")
            if not isinstance(source, dict) or source.get("url") in {None, "", "UNKNOWN"}:
                errors.append(f"{eid}: verified evidence requires a real source URL")
            if record.get("checked_at") in {None, "", "UNKNOWN"}:
                errors.append(f"{eid}: verified evidence requires a real checked_at value")

    known_quantity_sources = set(evidence_by_id) | set(decision_by_id) | set(approval_by_id)
    for baseline in baselines:
        if not isinstance(baseline, dict):
            errors.append("baseline spec must be an object")
            continue
        bid = str(baseline.get("baseline_id", "<baseline>"))
        linked = set(map(str, as_list(baseline.get("evidence_ids"))))
        if linked - set(evidence_by_id):
            errors.append(f"{bid}: baseline references unknown evidence {sorted(linked - set(evidence_by_id))}")
        if baseline.get("status") == "USER_APPROVED" and baseline.get("approval_event_id") not in approval_by_id:
            errors.append(f"{bid}: USER_APPROVED baseline requires a valid approval event")
        if baseline.get("status") == "VERIFIED" and not linked:
            errors.append(f"{bid}: VERIFIED baseline requires evidence")

    for quantity in quantities:
        if not isinstance(quantity, dict):
            errors.append("quantity semantics record must be an object")
            continue
        qid = str(quantity.get("quantity_id", "<quantity>"))
        linked = set(map(str, as_list(quantity.get("source_or_evidence_ids"))))
        if linked - known_quantity_sources:
            errors.append(f"{qid}: quantity references unknown source IDs {sorted(linked - known_quantity_sources)}")
        if quantity.get("precision_status") == "VERIFIED" and not linked:
            errors.append(f"{qid}: VERIFIED quantity requires source_or_evidence_ids")
        baseline_id = quantity.get("baseline_id")
        if baseline_id is not None and str(baseline_id) not in baseline_by_id:
            errors.append(f"{qid}: quantity references unknown baseline {baseline_id}")
        if quantity.get("precision_status") == "VERIFIED" and baseline_id is not None:
            if baseline_by_id.get(str(baseline_id), {}).get("status") != "VERIFIED":
                errors.append(f"{qid}: VERIFIED comparison quantity requires a VERIFIED baseline")
        if quantity.get("quantity_type") == "RATE" and (
            as_list(quantity.get("used_in_shot_ids")) or as_list(quantity.get("used_in_prompt_ids"))
        ):
            mapping = quantity.get("display_mapping")
            if not isinstance(mapping, dict):
                errors.append(f"{qid}: RATE used on screen requires explicit display_mapping")
            elif not nonempty(mapping.get("derivation")) or not as_list(mapping.get("source_or_evidence_ids")):
                errors.append(f"{qid}: RATE display mapping requires derivation and sources")

    execution_mode = state.get("execution_mode")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            errors.append("artifact must be an object")
            continue
        aid = artifact.get("id", "<missing>")
        status = artifact.get("status")
        real = artifact.get("real_artifact_present") is True
        linked_evidence = set(map(str, as_list(artifact.get("evidence_ids"))))
        blockers = set(map(str, as_list(artifact.get("open_blocking_issue_ids"))))
        artifact_mode = artifact.get("execution_mode", execution_mode)
        if status == "USER_APPROVED" and artifact.get("approval_event_id") not in approval_by_id:
            errors.append(f"{aid}: USER_APPROVED requires a valid approval_event_id")
        truth_claiming_statuses = {"REAL_ARTIFACT_AVAILABLE", "OBSERVED", "VALIDATED", "LOCKED"}
        if status in truth_claiming_statuses and not real:
            errors.append(f"E_REAL_ARTIFACT_CONTRADICTION {aid}: {status} requires a real artifact")
        if status in truth_claiming_statuses and not linked_evidence:
            errors.append(f"E_REAL_ARTIFACT_CONTRADICTION {aid}: {status} requires evidence_ids")
        if linked_evidence - set(evidence_by_id):
            errors.append(f"{aid}: references unknown evidence IDs")
        if status == "LOCKED" and (blockers or blockers.intersection(open_blocking_ids)):
            errors.append(f"{aid}: LOCKED while blocking issues remain")
        if artifact_mode == "SIMULATION" and status in truth_claiming_statuses:
            errors.append(f"E_REAL_ARTIFACT_CONTRADICTION {aid}: simulation cannot claim {status}")
        if alpha7 and real:
            locator = artifact.get("content_locator")
            if not isinstance(locator, dict) or not nonempty(locator.get("uri")) or not nonempty(locator.get("media_type")):
                errors.append(
                    f"E_REAL_ARTIFACT_CONTRADICTION {aid}: real artifact requires content_locator"
                )
            if not nonempty(artifact.get("version")):
                errors.append(f"E_REAL_ARTIFACT_CONTRADICTION {aid}: real artifact requires version")
            if artifact_mode != "REAL":
                errors.append(
                    f"E_REAL_ARTIFACT_CONTRADICTION {aid}: real artifact requires execution_mode=REAL"
                )
            artifact_ref = (str(aid), str(artifact.get("version")))
            if artifact.get("artifact_class") != "TEXT_SPEC" and not any(
                artifact_ref in versioned_refs(evidence_scope(evidence_by_id.get(eid, {})).get("artifact_refs"))
                for eid in linked_evidence
            ):
                errors.append(
                    f"E_REAL_ARTIFACT_CONTRADICTION {aid}: evidence must cover this artifact/version tuple"
                )
        missing_unknowns = set(map(str, as_list(artifact.get("protected_unknown_ids")))) - set(unknown_by_id)
        missing_quantities = set(map(str, as_list(artifact.get("quantity_ids")))) - set(quantity_by_id)
        missing_boundaries = set(map(str, as_list(artifact.get("causal_boundary_ids")))) - set(boundary_by_id)
        if missing_unknowns:
            errors.append(f"{aid}: references unknown protected_unknown_ids {sorted(missing_unknowns)}")
        if missing_quantities:
            errors.append(f"{aid}: references unknown quantity_ids {sorted(missing_quantities)}")
        if missing_boundaries:
            errors.append(f"{aid}: references unknown causal_boundary_ids {sorted(missing_boundaries)}")
        if artifact.get("artifact_class") == "BENCHMARK_ONLY" and not nonempty(artifact.get("benchmark_case_id")):
            errors.append(f"{aid}: BENCHMARK_ONLY artifact requires benchmark_case_id")

    benchmark_artifact_ids = {
        str(item.get("id")) for item in artifacts
        if isinstance(item, dict) and item.get("artifact_class") == "BENCHMARK_ONLY"
    }
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("artifact_class") == "BENCHMARK_ONLY":
            continue
        leaked = set(map(str, as_list(artifact.get("dependencies")))) & benchmark_artifact_ids
        if leaked:
            errors.append(f"{artifact.get('id', '<artifact>')}: production artifact depends on BENCHMARK_ONLY artifacts {sorted(leaked)}")

    capacity = state.get("capacity_snapshot")
    if isinstance(capacity, dict) and capacity.get("scope_or_cadence_locked") is True:
        if not as_list(capacity.get("pilot_evidence_ids")):
            errors.append("capacity: locked scope/cadence requires representative pilot evidence")

    gate_requirements = as_list(state.get("gate_requirements"))
    gates = as_list(state.get("gate_evaluations"))
    requirement_by_id = index_unique(
        gate_requirements, "requirement_id", "gate_requirements", errors
    )
    gate_by_id = index_unique(gates, "gate_id", "gate_evaluations", errors)
    for requirement in gate_requirements:
        if not isinstance(requirement, dict):
            errors.append("gate requirement must be an object")
            continue
        rid = requirement.get("requirement_id", "<requirement>")
        source_type = requirement.get("requirement_source")
        source_id = str(requirement.get("source_id", ""))
        gate_id = str(requirement.get("gate_id", ""))
        if gate_id not in gate_by_id:
            errors.append(f"{rid}: references unknown gate {gate_id}")
        if source_type == "USER_APPROVED_DECISION":
            decision = decision_by_id.get(source_id)
            if not decision or decision.get("status") not in APPROVED_DECISION_STATUSES:
                errors.append(f"{rid}: PROPOSED/UNKNOWN decision cannot become a gate requirement")
        elif source_type in {"VERIFIED_EVIDENCE", "APPLICABLE_RULE"}:
            record = evidence_by_id.get(source_id)
            if not record:
                errors.append(f"{rid}: references unknown evidence {source_id}")
                continue
            if source_type == "VERIFIED_EVIDENCE" and record.get("classification") in {
                "SYSTEM_INFERENCE", "HEURISTIC", "UNKNOWN"
            }:
                errors.append(f"{rid}: unverified inference cannot become VERIFIED_EVIDENCE requirement")
            if source_type == "APPLICABLE_RULE":
                if record.get("classification") != "VERIFIED_OFFICIAL":
                    errors.append(f"{rid}: applicable rule must use VERIFIED_OFFICIAL evidence")
                for field in ("actor", "duty", "trigger", "exceptions_or_conditions"):
                    if not nonempty(record.get(field)):
                        errors.append(f"{rid}: applicable rule evidence missing {field}")
                if record.get("status") not in {"EFFECTIVE", "PLATFORM_SPECIFIC"}:
                    errors.append(f"{rid}: DRAFT/UNKNOWN rule cannot become an applicable requirement")
                source = record.get("source")
                if not isinstance(source, dict) or not nonempty(source.get("url")):
                    errors.append(f"{rid}: applicable rule requires a source URL")
                if not nonempty(record.get("checked_at")):
                    errors.append(f"{rid}: applicable rule requires checked_at")
        elif source_type == "SYSTEM_INVARIANT":
            invariant_id = str(requirement.get("invariant_id", ""))
            if source_id != invariant_id:
                errors.append(f"{rid}: SYSTEM_INVARIANT source_id must equal invariant_id")
            if invariant_id not in SYSTEM_INVARIANT_REGISTRY:
                errors.append(f"{rid}: unknown SYSTEM_INVARIANT {invariant_id!r}")
        else:
            errors.append(f"{rid}: invalid requirement_source {source_type!r}")

    for gate in gates:
        if not isinstance(gate, dict):
            errors.append("gate must be an object")
            continue
        gid = gate.get("gate_id", "<gate>")
        evaluation = gate.get("evaluation_status")
        outcome = gate.get("outcome")
        linked_evidence = set(map(str, as_list(gate.get("evidence_ids"))))
        blockers = set(map(str, as_list(gate.get("blocking_issue_ids"))))
        if alpha7:
            if evaluation != "EXECUTED":
                errors.append(
                    f"E_GATE_UNEXECUTED {gid}: Alpha.7 stores only executed gate evaluations"
                )
            if not isinstance(gate.get("scope_bindings"), dict):
                errors.append(f"E_GATE_SCOPE_MISSING {gid}: Alpha.7 requires typed scope_bindings")
        if evaluation == "NOT_EXECUTED":
            if outcome != "UNKNOWN":
                errors.append(f"{gid}: NOT_EXECUTED must use outcome=UNKNOWN, not failure/pass")
            if linked_evidence:
                errors.append(f"{gid}: NOT_EXECUTED gate cannot claim evaluation evidence")
        elif evaluation == "EXECUTED":
            if outcome == "UNKNOWN":
                errors.append(f"{gid}: EXECUTED gate cannot keep outcome=UNKNOWN")
            if not nonempty(gate.get("evaluated_at")):
                errors.append(f"{gid}: EXECUTED gate requires evaluated_at")
        else:
            errors.append(f"{gid}: invalid evaluation_status {evaluation!r}")
        if outcome == "PASSED":
            if not linked_evidence:
                errors.append(f"{gid}: PASSED requires evidence_ids")
            if blockers:
                errors.append(f"{gid}: PASSED while blocking issues remain")
        if outcome == "FAILED" and not linked_evidence:
            errors.append(f"{gid}: FAILED requires evaluation evidence")
        if outcome == "BLOCKED" and not blockers:
            errors.append(f"{gid}: BLOCKED requires blocking_issue_ids")
        if not alpha7 and outcome == "NOT_APPLICABLE" and as_list(gate.get("requirement_ids")):
            errors.append(f"{gid}: required gate cannot use NOT_APPLICABLE while requirement_ids exist")
        if linked_evidence - set(evidence_by_id):
            errors.append(f"{gid}: references unknown evidence IDs {sorted(linked_evidence - set(evidence_by_id))}")
        if outcome in {"PASSED", "ACCEPTED_WITH_DEBT"}:
            weak = {
                eid
                for eid in linked_evidence
                if evidence_by_id.get(eid, {}).get("claim_class") in {"SYSTEM_INFERENCE", "HEURISTIC", "UNKNOWN"}
                or evidence_by_id.get(eid, {}).get("classification") in {"SYSTEM_INFERENCE", "HEURISTIC", "UNKNOWN"}
            }
            if weak:
                errors.append(f"{gid}: gate pass cannot rely on inference/heuristic/unknown evidence {sorted(weak)}")
        for rid in map(str, as_list(gate.get("requirement_ids"))):
            requirement = requirement_by_id.get(rid)
            if not requirement:
                errors.append(f"{gid}: references unknown requirement {rid}")
            elif str(requirement.get("gate_id")) != str(gid):
                errors.append(f"{gid}: requirement {rid} belongs to another gate")
        requirement_ids = set(map(str, as_list(gate.get("requirement_ids"))))
        requirement_results = as_list(gate.get("requirement_results"))
        if alpha7 and not requirement_ids:
            errors.append(
                f"E_GATE_EMPTY_REQUIREMENTS {gid}: every persisted evaluation requires applicability requirements"
            )
        if alpha7 and outcome == "NOT_APPLICABLE" and not linked_evidence:
            errors.append(
                f"E_GATE_APPLICABILITY_EVIDENCE {gid}: NOT_APPLICABLE requires evidence"
            )
        result_by_id: dict[str, dict[str, Any]] = {}
        for result in requirement_results:
            if not isinstance(result, dict):
                errors.append(f"{gid}: requirement result must be an object")
                continue
            result_id = str(result.get("requirement_id", ""))
            if result_id in result_by_id:
                errors.append(f"{gid}: duplicate requirement result {result_id}")
            result_by_id[result_id] = result
            if result_id not in requirement_ids:
                errors.append(f"{gid}: requirement result {result_id} is not listed in requirement_ids")
            result_evidence = set(map(str, as_list(result.get("evidence_ids"))))
            missing_result_evidence = result_evidence - set(evidence_by_id)
            if missing_result_evidence:
                errors.append(f"{gid}: requirement result {result_id} references unknown evidence {sorted(missing_result_evidence)}")
            if result_evidence - linked_evidence:
                errors.append(f"{gid}: requirement result {result_id} evidence_ids must be a subset of gate evidence_ids")
            requirement = requirement_by_id.get(result_id, {})
            if requirement.get("requirement_source") in {"VERIFIED_EVIDENCE", "APPLICABLE_RULE"}:
                source_id = str(requirement.get("source_id", ""))
                if source_id not in result_evidence:
                    errors.append(f"{gid}: requirement result {result_id} must include its source evidence {source_id}")
        if evaluation == "EXECUTED" and set(result_by_id) != requirement_ids:
            errors.append(f"{gid}: executed gate must map every requirement_id exactly once")
        if alpha7 and outcome == "NOT_APPLICABLE":
            invalid_applicability_results = {
                rid
                for rid in requirement_ids
                if result_by_id.get(rid, {}).get("result") != "NOT_APPLICABLE"
                or not as_list(result_by_id.get(rid, {}).get("evidence_ids"))
            }
            if invalid_applicability_results:
                errors.append(
                    f"E_GATE_APPLICABILITY_EVIDENCE {gid}: NOT_APPLICABLE requires every "
                    f"requirement result to be NOT_APPLICABLE with evidence {sorted(invalid_applicability_results)}"
                )
        if outcome == "PASSED":
            unsatisfied = {
                rid for rid in requirement_ids
                if result_by_id.get(rid, {}).get("result") != "SATISFIED"
            }
            if unsatisfied:
                errors.append(f"{gid}: PASSED requires all mandatory requirements SATISFIED {sorted(unsatisfied)}")
        if outcome == "ACCEPTED_WITH_DEBT":
            debt = gate.get("acceptance_debt")
            if not isinstance(debt, dict) or debt.get("approval_event_id") not in approval_by_id:
                errors.append(f"{gid}: ACCEPTED_WITH_DEBT requires a valid approval event")
        if execution_mode == "SIMULATION" and gate.get("gate_type") in MEDIA_GATE_TYPES and outcome in {"PASSED", "ACCEPTED_WITH_DEBT"}:
            errors.append(f"{gid}: simulated media gate cannot pass")
        if gate.get("gate_type") == "RELEASE_READINESS_GATE":
            for rid in map(str, as_list(gate.get("requirement_ids"))):
                description = str(requirement_by_id.get(rid, {}).get("description", "")).lower()
                if any(token in description for token in ("public url", "published link", "post id", "content id", "公开链接", "发布链接")):
                    errors.append(f"{gid}: publication evidence cannot be a pre-publication release-readiness requirement")
        if (
            gate.get("gate_type") == "GENERATION_READINESS_GATE"
            and gate.get("readiness_scope") == "BATCH_PRODUCTION"
            and outcome in {"PASSED", "ACCEPTED_WITH_DEBT"}
        ):
            if not state.get("canonical_duration") or not as_list(state.get("shot_plans")):
                errors.append(f"{gid}: BATCH_PRODUCTION readiness requires canonical duration and shot plans")
            if not as_list(state.get("asset_registry")) or not as_list(state.get("provider_prompts")):
                errors.append(f"{gid}: BATCH_PRODUCTION readiness requires asset registry and prompt coverage")
            if not any(
                isinstance(pilot, dict) and pilot.get("status") == "PASSED"
                for pilot in pilot_assessments
            ):
                errors.append(f"{gid}: BATCH_PRODUCTION readiness requires a passed representative pilot assessment")
            if open_blocking_ids:
                errors.append(f"{gid}: BATCH_PRODUCTION readiness cannot pass with open blocking issues")

    observations = as_list(state.get("observations"))
    observation_by_id = index_unique(
        observations, "observation_id", "observations", errors
    )
    for observation in observations:
        if not isinstance(observation, dict):
            errors.append("observation must be an object")
            continue
        oid = observation.get("observation_id", "<observation>")
        artifact_id = str(observation.get("artifact_id", ""))
        media_accessible = observation.get("media_accessible") is True
        observation_evidence = set(map(str, as_list(observation.get("evidence_ids"))))
        if artifact_id not in artifact_by_id:
            errors.append(f"{oid}: references unknown artifact {artifact_id}")
        missing_observation_evidence = observation_evidence - set(evidence_by_id)
        if missing_observation_evidence:
            errors.append(
                f"{oid}: references unknown evidence {sorted(missing_observation_evidence)}"
            )
        if not media_accessible:
            if observation.get("ncs") != "NOT_SCORED" or observation.get("nrs") != "NOT_SCORED":
                errors.append(f"{oid}: no accessible media requires NCS/NRS=NOT_SCORED")
            if observation.get("basis") != "USER_REPORTED":
                errors.append(f"{oid}: inaccessible media cannot be a system observation")
        else:
            artifact = artifact_by_id.get(artifact_id, {})
            if observation.get("basis") not in {"DIRECT_MEDIA_ACCESS", "MEASURED_DATA"}:
                errors.append(f"E_OBSERVATION_BASIS {oid}: accessible media cannot use USER_REPORTED basis")
            if artifact.get("real_artifact_present") is not True:
                errors.append(f"{oid}: direct media observation requires a real artifact")
            if not observation_evidence:
                errors.append(f"{oid}: direct media observation requires evidence_ids")
            if alpha7:
                if not nonempty(observation.get("artifact_version")):
                    errors.append(f"E_OBSERVATION_BASIS {oid}: Alpha.7 accessible observation requires artifact_version")
                elif str(observation.get("artifact_version")) != str(artifact.get("version")):
                    errors.append(f"E_OBSERVATION_BASIS {oid}: artifact_version does not match observed artifact")
                artifact_evidence = set(map(str, as_list(artifact.get("evidence_ids"))))
                if not observation_evidence.intersection(artifact_evidence):
                    errors.append(f"E_OBSERVATION_BASIS {oid}: observation evidence must bind to the same artifact")
                artifact_ref = (artifact_id, str(observation.get("artifact_version")))
                if not any(
                    artifact_ref
                    in versioned_refs(evidence_scope(evidence_by_id.get(eid, {})).get("artifact_refs"))
                    for eid in observation_evidence
                ):
                    errors.append(
                        f"E_OBSERVATION_BASIS {oid}: observation evidence scope must cover artifact/version"
                    )
        for score_name in ("ncs", "nrs"):
            score = observation.get(score_name)
            if isinstance(score, dict):
                score_evidence = set(map(str, as_list(score.get("evidence_ids"))))
                if score_evidence - set(evidence_by_id):
                    errors.append(f"{oid}: {score_name.upper()} references unknown evidence")
                if score_evidence - observation_evidence:
                    errors.append(
                        f"{oid}: {score_name.upper()} evidence must be a subset of observation evidence"
                    )
                if alpha7:
                    score_ref = (artifact_id, str(observation.get("artifact_version")))
                    if not score_evidence or any(
                        score_ref
                        not in versioned_refs(
                            evidence_scope(evidence_by_id.get(eid, {})).get("artifact_refs")
                        )
                        for eid in score_evidence
                    ):
                        errors.append(
                            f"E_OBSERVATION_BASIS {oid}: {score_name.upper()} evidence must cover "
                            "the observed artifact/version"
                        )

    accessible_observations = [
        item for item in observations if isinstance(item, dict) and item.get("media_accessible") is True
    ]
    for gate in gates:
        if not isinstance(gate, dict) or gate.get("outcome") not in {"PASSED", "ACCEPTED_WITH_DEBT"}:
            continue
        gid = gate.get("gate_id", "<gate>")
        gate_type = gate.get("gate_type")
        gate_evidence = set(map(str, as_list(gate.get("evidence_ids"))))
        if gate_type in MEDIA_GATE_TYPES:
            if not any(gate_evidence.intersection(map(str, as_list(obs.get("evidence_ids")))) for obs in accessible_observations):
                errors.append(f"{gid}: media gate pass requires accessible-media observation evidence")
        if gate_type == "FINAL_ARTIFACT_GATE" and not any(
            isinstance(item, dict)
            and item.get("artifact_class") == "MEDIA"
            and item.get("real_artifact_present") is True
            for item in artifacts
        ):
            errors.append(f"{gid}: final artifact gate pass requires real media")
        if gate_type == "RELEASE_READINESS_GATE":
            if not any(
                isinstance(item, dict)
                and item.get("artifact_class") == "MEDIA"
                and item.get("real_artifact_present") is True
                for item in artifacts
            ):
                errors.append(f"{gid}: release readiness pass requires real final media")
            if not any(
                isinstance(item, dict)
                and item.get("artifact_class") in {"PACKAGE", "RELEASE"}
                and item.get("real_artifact_present") is True
                for item in artifacts
            ):
                errors.append(f"{gid}: release readiness pass requires a real release package")

    repairs = as_list(state.get("repair_records"))
    repair_by_id = index_unique(repairs, "repair_id", "repair_records", errors)
    for repair in repairs:
        if not isinstance(repair, dict):
            errors.append("repair record must be an object")
            continue
        rid = repair.get("repair_id", "<repair>")
        status = repair.get("status")
        missing_diagnostic = set(map(str, as_list(repair.get("diagnostic_evidence_ids")))) - set(evidence_by_id)
        if missing_diagnostic:
            errors.append(f"{rid}: references unknown diagnostic evidence {sorted(missing_diagnostic)}")
        missing_sources = set(map(str, as_list(repair.get("source_artifact_ids")))) - set(artifact_by_id)
        if missing_sources:
            errors.append(f"{rid}: references unknown source artifacts {sorted(missing_sources)}")
        new_artifacts = set(map(str, as_list(repair.get("new_artifact_ids"))))
        new_observations = set(map(str, as_list(repair.get("new_observation_ids"))))
        re_gates = set(map(str, as_list(repair.get("re_evaluated_gate_ids"))))
        closure_links = as_list(repair.get("closure_links"))
        if status in {"REPAIR_EXECUTED", "REPAIR_VERIFIED"} and not new_artifacts:
            errors.append(f"{rid}: executed repair requires a new artifact")
        if status in {"REPAIR_EXECUTED", "REPAIR_VERIFIED"}:
            for aid in new_artifacts:
                artifact = artifact_by_id.get(aid)
                if not artifact or artifact.get("real_artifact_present") is not True:
                    errors.append(f"{rid}: executed repair references missing/non-real new artifact {aid}")
        if status == "REPAIR_VERIFIED":
            if not new_observations or not re_gates:
                errors.append(f"{rid}: verified repair requires new observation and re-evaluated gate")
            if not closure_links:
                errors.append(f"{rid}: REPAIR_VERIFIED requires at least one closure_links triple")
            for aid in new_artifacts:
                if artifact_by_id.get(aid, {}).get("real_artifact_present") is not True:
                    errors.append(f"{rid}: repair verification references missing/non-real artifact {aid}")
            for oid in new_observations:
                if observation_by_id.get(oid, {}).get("media_accessible") is not True:
                    errors.append(f"{rid}: repair verification references missing/non-media observation {oid}")
            for gid in re_gates:
                if gate_by_id.get(gid, {}).get("evaluation_status") != "EXECUTED":
                    errors.append(f"{rid}: repair verification references non-executed gate {gid}")
            for index, link in enumerate(closure_links):
                if not isinstance(link, dict):
                    errors.append(f"{rid}: closure_links[{index}] must be an object")
                    continue
                aid = str(link.get("new_artifact_id", ""))
                oid = str(link.get("new_observation_id", ""))
                gid = str(link.get("re_evaluated_gate_id", ""))
                if aid not in new_artifacts or oid not in new_observations or gid not in re_gates:
                    errors.append(f"{rid}: closure_links[{index}] IDs must appear in the corresponding repair arrays")
                observation = observation_by_id.get(oid, {})
                if str(observation.get("artifact_id", "")) != aid:
                    errors.append(f"{rid}: closure_links[{index}] observation must point to the linked new artifact")
                gate = gate_by_id.get(gid, {})
                if not (
                    gate.get("evaluation_status") == "EXECUTED"
                    and gate.get("outcome") in {"PASSED", "ACCEPTED_WITH_DEBT"}
                ):
                    errors.append(f"{rid}: closure_links[{index}] gate must be executed and passed")
                observation_evidence = set(map(str, as_list(observation.get("evidence_ids"))))
                gate_evidence = set(map(str, as_list(gate.get("evidence_ids"))))
                if not observation_evidence.intersection(gate_evidence):
                    errors.append(f"{rid}: closure_links[{index}] gate and observation evidence must intersect")

    provider_registry = as_list(state.get("provider_registry"))
    provider_by_id = index_unique(
        provider_registry, "provider_id", "provider_registry", errors
    )
    cleanup_record = state.get("state_cleanup")
    validation_checked_at = parse_iso_timestamp(
        cleanup_record.get("checked_at") if isinstance(cleanup_record, dict) else None
    )
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        provider_id = observation.get("provider_registry_id")
        if provider_id is not None and str(provider_id) not in provider_by_id:
            errors.append(
                f"{observation.get('observation_id', '<observation>')}: references unknown provider {provider_id}"
            )
    provider_keys: set[tuple[str, str, str, str, str, str]] = set()
    for provider in provider_registry:
        if not isinstance(provider, dict):
            errors.append("provider registry entry must be an object")
            continue
        pid = provider.get("provider_id", "<provider>")
        provider_required_fields = [
            "provider", "model", "version", "region", "access", "access_source_ids",
            "price", "source", "checked_at", "project_pilot_status",
        ]
        if alpha7:
            provider_required_fields.extend(["surface", "snapshot_id"])
        for field in provider_required_fields:
            if field not in provider:
                errors.append(f"{pid}: provider registry missing {field}")
        key_fields = (
            ("provider", "model", "version", "region", "surface", "snapshot_id")
            if alpha7
            else ("provider", "model", "version", "region", "", "")
        )
        key = tuple(
            str(provider.get(field, ""))
            for field in key_fields
        )
        if key in provider_keys:
            errors.append(f"{pid}: duplicate provider/model/version/region/surface/snapshot record")
        provider_keys.add(key)
        source = provider.get("source")
        if not isinstance(source, dict) or any(not nonempty(source.get(field)) for field in ("publisher", "title", "url", "source_type")):
            errors.append(f"{pid}: provider source requires publisher/title/url/source_type")
        elif provider.get("classification") == "VERIFIED_OFFICIAL" and source.get("source_type") != "OFFICIAL":
            errors.append(f"{pid}: third-party or user source cannot be VERIFIED_OFFICIAL")
        missing_access_evidence = set(map(str, as_list(provider.get("access_source_ids")))) - set(evidence_by_id)
        if missing_access_evidence:
            errors.append(f"{pid}: access_source_ids reference unknown evidence {sorted(missing_access_evidence)}")
        if provider.get("access") in {"AVAILABLE", "LIMITED", "NOT_AVAILABLE"} and provider.get("classification") == "VERIFIED_OFFICIAL" and not as_list(provider.get("access_source_ids")):
            errors.append(f"{pid}: verified access claim requires access_source_ids")
        for capability in as_list(provider.get("capabilities")):
            if not isinstance(capability, dict):
                errors.append(f"{pid}: capability record must be an object")
                continue
            capability_sources = set(map(str, as_list(capability.get("source_or_evidence_ids"))))
            if capability_sources - set(evidence_by_id):
                errors.append(f"{pid}: capability {capability.get('capability_id')} references unknown evidence")
            if capability.get("status") == "VERIFIED" and not capability_sources:
                errors.append(f"{pid}: VERIFIED capability {capability.get('capability_id')} requires per-provider evidence")
            if alpha7 and capability.get("status") == "VERIFIED":
                if (
                    str(capability.get("version_scope")) != str(provider.get("version"))
                    or str(capability.get("region_scope")) != str(provider.get("region"))
                    or str(capability.get("surface_scope")) != str(provider.get("surface"))
                    or str(capability.get("checked_at")) != str(provider.get("checked_at"))
                ):
                    errors.append(
                        f"E_PROVIDER_EVIDENCE_SCOPE {pid}: capability version/region/surface/checked_at "
                        "scope does not match provider snapshot"
                    )
                if any(
                    not evidence_applies_to_provider(evidence_by_id.get(eid, {}), str(pid), provider)
                    for eid in capability_sources
                ):
                    errors.append(
                        f"E_PROVIDER_EVIDENCE_SCOPE {pid}: capability evidence does not cover provider snapshot"
                    )
            if capability.get("claim_kind") == "EXACT_DURATION":
                duration = capability.get("exact_duration_seconds")
                if (
                    capability.get("status") != "VERIFIED"
                    or not isinstance(duration, (int, float))
                    or isinstance(duration, bool)
                    or duration <= 0
                    or not capability_sources
                ):
                    errors.append(
                        f"E_DURATION_EVIDENCE_INVALID {pid}: exact duration capability requires "
                        "a positive measured duration and VERIFIED evidence"
                    )
                if capability.get("status") == "VERIFIED" and capability_sources:
                    provider_checked_at = parse_iso_timestamp(provider.get("checked_at"))
                    capability_checked_at = parse_iso_timestamp(capability.get("checked_at"))
                    for evidence_id in capability_sources:
                        source_record = evidence_by_id.get(evidence_id, {})
                        scope = evidence_scope(source_record)
                        freshness = source_record.get("freshness")
                        required_scope = {
                            "provider": provider.get("provider"),
                            "model": provider.get("model"),
                            "version": provider.get("version"),
                            "region": provider.get("region"),
                            "surface": provider.get("surface"),
                            "snapshot_id": provider.get("snapshot_id"),
                            "provider_checked_at": provider.get("checked_at"),
                        }
                        scope_is_exact = (
                            str(pid) in scope_list(scope, "provider_registry_ids")
                            and all(
                                field in scope
                                and str(scope.get(field)) == str(expected)
                                for field, expected in required_scope.items()
                            )
                        )
                        evidence_checked_at = parse_iso_timestamp(source_record.get("checked_at"))
                        fresh_from = parse_iso_timestamp(
                            freshness.get("valid_from") if isinstance(freshness, dict) else None
                        )
                        fresh_until = parse_iso_timestamp(
                            freshness.get("valid_until") if isinstance(freshness, dict) else None
                        )
                        freshness_is_current = (
                            isinstance(freshness, dict)
                            and freshness.get("status") == "CURRENT"
                            and provider_checked_at is not None
                            and capability_checked_at is not None
                            and evidence_checked_at is not None
                            and validation_checked_at is not None
                            and fresh_from is not None
                            and fresh_until is not None
                            and provider_checked_at == capability_checked_at == evidence_checked_at
                            and fresh_from <= evidence_checked_at <= fresh_until
                            and validation_checked_at <= fresh_until
                        )
                        classification_is_qualified = (
                            source_record.get("classification")
                            in QUALIFIED_EXACT_DURATION_EVIDENCE
                            and source_record.get("claim_class")
                            in {"FACT", "SAMPLE_OBSERVATION"}
                            and source_record.get("status") == "EFFECTIVE"
                        )
                        if not (
                            scope_is_exact
                            and classification_is_qualified
                            and freshness_is_current
                        ):
                            errors.append(
                                f"E_PROVIDER_VERIFIED_EVIDENCE {pid}: exact-duration evidence "
                                f"{evidence_id} must be qualified, current, and explicitly bound to "
                                "the provider/model/version/region/surface/snapshot/checked_at"
                            )
        if provider.get("project_pilot_status") in {"RUN_PARTIAL", "PASSED", "FAILED", "INCONCLUSIVE"} and not as_list(provider.get("project_observations")):
            errors.append(f"{pid}: project pilot result requires project_observations")
        for observation_id in map(str, as_list(provider.get("project_observations"))):
            if observation_id not in observation_by_id:
                errors.append(f"{pid}: references unknown project observation {observation_id}")
        if provider.get("project_pilot_status") == "PASSED":
            for observation_id in map(str, as_list(provider.get("project_observations"))):
                observation = observation_by_id.get(observation_id)
                if not observation:
                    continue
                artifact = artifact_by_id.get(str(observation.get("artifact_id", "")), {})
                if observation.get("media_accessible") is not True or artifact.get("real_artifact_present") is not True:
                    errors.append(f"{pid}: PASSED pilot requires accessible observation of a real artifact")
                if observation.get("basis") not in {"DIRECT_MEDIA_ACCESS", "MEASURED_DATA"}:
                    errors.append(f"{pid}: PASSED pilot observation cannot use USER_REPORTED basis")
                if observation.get("provider_registry_id") != pid:
                    errors.append(f"{pid}: PASSED pilot observation must bind to the same provider_registry_id")
                if not nonempty(observation.get("task_scope")):
                    errors.append(f"{pid}: PASSED pilot observation requires a non-empty task_scope")
                if not nonempty(observation.get("observed_at")):
                    errors.append(f"{pid}: PASSED pilot observation requires observed_at")
        price = provider.get("price")
        if isinstance(price, dict) and price.get("status") == "VERIFIED_CURRENT":
            if price.get("precision_status") != "VERIFIED" or not as_list(price.get("source_or_evidence_ids")):
                errors.append(f"{pid}: VERIFIED_CURRENT price requires VERIFIED precision and source IDs")
            if provider.get("checked_at") in {None, "", "UNKNOWN"}:
                errors.append(f"{pid}: VERIFIED_CURRENT price requires a real checked_at value")
            if alpha7:
                price_sources = set(map(str, as_list(price.get("source_or_evidence_ids"))))
                if any(eid not in evidence_by_id for eid in price_sources) or any(
                    not evidence_applies_to_provider(evidence_by_id.get(eid, {}), str(pid), provider)
                    for eid in price_sources
                ):
                    errors.append(
                        f"E_PROVIDER_EVIDENCE_SCOPE {pid}: verified price evidence does not cover provider snapshot"
                    )

    for pilot in pilot_assessments:
        if not isinstance(pilot, dict):
            errors.append("pilot assessment must be an object")
            continue
        pilot_id = str(pilot.get("pilot_id", "<pilot>"))
        if current_quality_contract:
            for field in (
                "source_spec_version", "shot_plan_ids", "asset_ids", "prompt_ids",
                "generation_targets", "format_variant_ids", "task_types",
            ):
                missing = field not in pilot
                if field in {
                    "source_spec_version", "prompt_ids", "generation_targets",
                    "format_variant_ids", "task_types",
                }:
                    missing = missing or (
                        not nonempty(pilot.get(field))
                        if field == "source_spec_version" else not as_list(pilot.get(field))
                    )
                if missing:
                    errors.append(f"E_PILOT_SCOPE_MISMATCH {pilot_id}: missing typed {field}")
        missing_providers = set(map(str, as_list(pilot.get("provider_registry_ids")))) - set(provider_by_id)
        missing_artifacts = set(map(str, as_list(pilot.get("artifact_ids")))) - set(artifact_by_id)
        missing_observations = set(map(str, as_list(pilot.get("observation_ids")))) - set(observation_by_id)
        if missing_providers:
            errors.append(f"{pilot_id}: references unknown providers {sorted(missing_providers)}")
        if missing_artifacts:
            errors.append(f"{pilot_id}: references unknown artifacts {sorted(missing_artifacts)}")
        if missing_observations:
            errors.append(f"{pilot_id}: references unknown observations {sorted(missing_observations)}")
        if pilot.get("status") == "PASSED":
            pilot_evidence = set(map(str, as_list(pilot.get("evidence_ids"))))
            retell = pilot.get("unprompted_retell") if isinstance(pilot.get("unprompted_retell"), dict) else {}
            retell_evidence = set(map(str, as_list(retell.get("evidence_ids"))))
            if not pilot_evidence or not retell_evidence:
                errors.append(f"{pilot_id}: PASSED pilot requires production and unprompted-retell evidence")
            if (pilot_evidence | retell_evidence) - set(evidence_by_id):
                errors.append(f"{pilot_id}: PASSED pilot references unknown evidence")
            for observation_id in map(str, as_list(pilot.get("observation_ids"))):
                observation = observation_by_id.get(observation_id, {})
                artifact = artifact_by_id.get(str(observation.get("artifact_id", "")), {})
                if observation.get("media_accessible") is not True or artifact.get("real_artifact_present") is not True:
                    errors.append(f"{pilot_id}: PASSED pilot requires accessible observations of real artifacts")
            if alpha7:
                expected_providers = set(map(str, as_list(pilot.get("provider_registry_ids"))))
                expected_plans = set(map(str, as_list(pilot.get("shot_plan_ids"))))
                expected_assets = set(map(str, as_list(pilot.get("asset_ids"))))
                expected_prompts = set(map(str, as_list(pilot.get("prompt_ids"))))
                expected_task_types = set(map(str, as_list(pilot.get("task_types"))))
                expected_formats = set(map(str, as_list(pilot.get("format_variant_ids"))))
                for evidence_id in pilot_evidence | retell_evidence:
                    scope = evidence_scope(evidence_by_id.get(evidence_id, {}))
                    if (
                        not expected_providers <= scope_list(scope, "provider_registry_ids")
                        or str(pilot_id) not in scope_list(scope, "pilot_ids")
                        or not expected_plans <= scope_list(scope, "shot_plan_ids")
                        or not expected_assets <= scope_list(scope, "asset_ids")
                        or not expected_prompts <= scope_list(scope, "prompt_ids")
                        or not expected_task_types <= scope_list(scope, "task_types")
                        or str(scope.get("task_scope", "")) != str(pilot.get("scope"))
                        or not expected_formats <= (
                            scope_list(scope, "format_variant_ids")
                            | ({str(scope.get("format_scope"))} if nonempty(scope.get("format_scope")) else set())
                        )
                    ):
                        errors.append(
                            f"E_PILOT_SCOPE_MISMATCH {pilot_id}: evidence {evidence_id} does not cover "
                            "the Pilot provider/target/plan/asset/prompt/format/task scope"
                        )

    publication_records = as_list(state.get("publication_records"))
    publication_by_id = index_unique(
        publication_records, "publication_id", "publication_records", errors
    )
    for publication in publication_records:
        if not isinstance(publication, dict):
            errors.append("publication record must be an object")
            continue
        pub_id = publication.get("publication_id", "<publication>")
        artifact_id = str(publication.get("artifact_id", ""))
        release_package_id = str(publication.get("release_package_id", ""))
        artifact = artifact_by_id.get(artifact_id)
        release_package = artifact_by_id.get(release_package_id)
        if not artifact or artifact.get("real_artifact_present") is not True:
            errors.append(f"{pub_id}: publication requires a real final artifact")
        elif str(artifact.get("version")) != str(publication.get("artifact_version")):
            errors.append(f"{pub_id}: artifact_version does not match published artifact")
        if not release_package or release_package.get("real_artifact_present") is not True:
            errors.append(f"{pub_id}: publication requires a real release package")
        readiness_gate_id = str(publication.get("release_readiness_gate_id", ""))
        readiness_gate = gate_by_id.get(readiness_gate_id, {})
        if not (
            readiness_gate.get("gate_type") == "RELEASE_READINESS_GATE"
            and readiness_gate.get("evaluation_status") == "EXECUTED"
            and readiness_gate.get("outcome") in {"PASSED", "ACCEPTED_WITH_DEBT"}
        ):
            errors.append(f"{pub_id}: publication requires a passed release-readiness gate")
        linked = set(map(str, as_list(publication.get("evidence_ids"))))
        if not linked or linked - set(evidence_by_id):
            errors.append(f"{pub_id}: publication evidence_ids are missing or unknown")
        if publication.get("url") in {None, "", "UNKNOWN"} or publication.get("content_or_post_id") in {None, "", "UNKNOWN"}:
            errors.append(f"{pub_id}: publication requires real URL and content/post ID")
        if alpha7 and linked:
            publication_ref = (artifact_id, str(publication.get("artifact_version")))
            package_ref = (release_package_id, str(release_package.get("version")) if release_package else "")
            if not any(
                str(pub_id) in scope_list(evidence_scope(evidence_by_id.get(eid, {})), "publication_ids")
                and publication_ref
                in versioned_refs(evidence_scope(evidence_by_id.get(eid, {})).get("artifact_refs"))
                and (
                    package_ref
                    in versioned_refs(evidence_scope(evidence_by_id.get(eid, {})).get("package_refs"))
                    or release_package_id
                    in scope_list(
                        evidence_scope(evidence_by_id.get(eid, {})), "release_package_ids"
                    )
                )
                for eid in linked
            ):
                errors.append(
                    f"E_RELEASE_SCOPE_MISMATCH {pub_id}: publication evidence must cover its publication, "
                    "artifact/version, and release package"
                )

    for gate in gates:
        if not isinstance(gate, dict):
            continue
        gid = gate.get("gate_id", "<gate>")
        linked_publications = set(map(str, as_list(gate.get("publication_ids"))))
        if linked_publications - set(publication_by_id):
            errors.append(f"{gid}: references unknown publication IDs {sorted(linked_publications - set(publication_by_id))}")
        if gate.get("gate_type") == "PUBLICATION_EVIDENCE_GATE" and gate.get("outcome") == "PASSED" and not linked_publications:
            errors.append(f"{gid}: passed publication gate requires publication_ids")

    passed_publication_ids = {
        str(publication_id)
        for gate in gates
        if isinstance(gate, dict)
        and gate.get("gate_type") == "PUBLICATION_EVIDENCE_GATE"
        and gate.get("evaluation_status") == "EXECUTED"
        and gate.get("outcome") == "PASSED"
        for publication_id in as_list(gate.get("publication_ids"))
    }

    registry = as_list(state.get("asset_registry"))
    asset_by_id = index_unique(registry, "id", "asset_registry", errors)
    declared_asset_count = state.get("declared_asset_count")
    if isinstance(declared_asset_count, int) and declared_asset_count != len(asset_by_id):
        errors.append(f"assets: declared {declared_asset_count}, registry contains {len(asset_by_id)} unique IDs")

    provider_prompts = as_list(state.get("provider_prompts"))
    prompt_by_id = index_unique(provider_prompts, "id", "provider_prompts", errors)
    manual_copy_prompt_ids = {
        prompt_id
        for prompt_id, prompt in prompt_by_id.items()
        if prompt.get("execution_contract") == "MANUAL_COPY_TEXT_SPEC_ONLY"
    }
    all_shot_ids: set[str] = set()
    generation_shot_ids: set[str] = set()
    no_generation_shot_ids: set[str] = set()
    shot_to_prompts: dict[str, set[str]] = {}
    shot_to_masters: dict[str, set[str]] = {}
    shot_to_drafts: dict[str, set[str]] = {}
    shot_to_transform_plans: dict[str, set[str]] = {}
    shot_to_neutral_execution_prompts: dict[str, set[str]] = {}
    shot_by_id: dict[str, dict[str, Any]] = {}
    shot_plan_for_shot: dict[str, str] = {}
    shot_intervals: dict[str, tuple[float, float]] = {}
    shot_plans = as_list(state.get("shot_plans"))
    shot_plan_by_id = index_unique(shot_plans, "id", "shot_plans", errors)
    canonical = state.get("canonical_duration")
    known_precision_sources = set(evidence_by_id) | set(decision_by_id) | set(approval_by_id)
    for plan in shot_plans:
        if not isinstance(plan, dict):
            errors.append("shot plan must be an object")
            continue
        pid = plan.get("id", "<shot-plan>")
        if not legacy_generation:
            legacy_durations = [
                shot.get("duration_seconds")
                for shot in as_list(plan.get("shots"))
                if isinstance(shot, dict) and isinstance(shot.get("duration_seconds"), (int, float))
            ]
            legacy_target = plan.get("target_duration_seconds")
            if isinstance(legacy_target, (int, float)) and legacy_durations:
                legacy_total = sum(legacy_durations)
                legacy_tolerance = plan.get("duration_tolerance_ratio", 0)
                if abs(legacy_total - legacy_target) > legacy_target * legacy_tolerance + 1e-9:
                    errors.append(
                        f"{pid}: shot total {legacy_total:g}s does not reconcile with target {legacy_target:g}s"
                    )
            if plan.get("reuse_mode") == "CROP_REFRAME_ONLY" and plan.get("format_variants_require_different_camera") is True:
                errors.append(f"{pid}: crop/reframe-only conflicts with different camera variants")
            continue
        plan_format_ids = set(map(str, as_list(plan.get("format_variant_ids"))))
        if alpha7:
            if not plan_format_ids:
                errors.append(f"E_SAFE_ZONE_EVIDENCE_INVALID {pid}: Alpha.7 shot plan requires format_variant_ids")
            missing_formats = plan_format_ids - set(format_by_id)
            if missing_formats:
                errors.append(
                    f"E_SAFE_ZONE_EVIDENCE_INVALID {pid}: unknown format variants {sorted(missing_formats)}"
                )
            for format_id in plan_format_ids - missing_formats:
                if format_by_id[format_id].get("status") not in {"USER_APPROVED", "VALIDATED"}:
                    errors.append(
                        f"E_SAFE_ZONE_EVIDENCE_INVALID {pid}: format {format_id} is not approved or validated"
                    )
        durations: list[float] = []
        timeline_cursor = 0.0
        for shot in as_list(plan.get("shots")):
            if not isinstance(shot, dict):
                errors.append(f"{pid}: shot must be an object")
                continue
            shot_id = str(shot.get("shot_id", ""))
            if not shot_id:
                errors.append(f"{pid}: every shot requires stable shot_id")
                continue
            if shot_id in all_shot_ids:
                errors.append(f"E_LEDGER_DUPLICATE_ID {pid}: duplicate shot_id {shot_id}")
            all_shot_ids.add(shot_id)
            shot_by_id[shot_id] = shot
            shot_plan_for_shot[shot_id] = str(pid)
            if current_quality_contract:
                director_source_fields = [
                    shot.get("state_in"), shot.get("required_event"), shot.get("planned_state_out")
                ]
                if any(not substantive_director_source(value) for value in director_source_fields):
                    errors.append(
                        f"PQ_BEAT_CONTRACT_THIN {shot_id}: state_in/required_event/planned_state_out "
                        "must be substantive director source"
                    )
                if len({normalized_prompt_text(value) for value in director_source_fields}) != 3:
                    errors.append(
                        f"PQ_BEAT_CONTRACT_THIN {shot_id}: director source fields must describe distinct states/events"
                    )
            duration = shot.get("duration_seconds")
            if isinstance(duration, (int, float)):
                durations.append(float(duration))
                shot_intervals[shot_id] = (timeline_cursor, timeline_cursor + float(duration))
                timeline_cursor += float(duration)
            missing_assets = set(map(str, as_list(shot.get("asset_ids")))) - set(asset_by_id)
            if missing_assets:
                errors.append(f"{shot_id}: unregistered asset references {sorted(missing_assets)}")
            for asset_id in set(map(str, as_list(shot.get("asset_ids")))) - missing_assets:
                asset = asset_by_id[asset_id]
                if shot_id not in set(map(str, as_list(asset.get("shot_refs")))):
                    errors.append(f"{shot_id}: asset {asset_id} does not declare this shot in shot_refs")
                if str(asset.get("source_spec_version")) != str(plan.get("source_spec_version")):
                    errors.append(f"{shot_id}: asset {asset_id} source spec version mismatch")
                if asset.get("benchmark_case_id") is not None:
                    errors.append(f"{shot_id}: production shot cannot reference BENCHMARK_ONLY asset {asset_id}")
            prompt_ids = set(map(str, as_list(shot.get("provider_prompt_ids"))))
            draft_ids = set(map(str, as_list(shot.get("provider_neutral_draft_ids"))))
            transform_plan_ids = set(map(str, as_list(shot.get("transform_plan_ids"))))
            neutral_execution_prompt_ids = set(
                map(str, as_list(shot.get("neutral_execution_prompt_ids")))
            )
            master_ids = set(map(str, as_list(shot.get("master_prompt_ids"))))
            shot_to_prompts[shot_id] = prompt_ids
            shot_to_drafts[shot_id] = draft_ids
            shot_to_transform_plans[shot_id] = transform_plan_ids
            shot_to_neutral_execution_prompts[shot_id] = neutral_execution_prompt_ids
            shot_to_masters[shot_id] = master_ids
            if four_layer_prompt_contract:
                for field in ("transform_plan_ids", "neutral_execution_prompt_ids"):
                    if field not in shot:
                        errors.append(
                            f"E_PROMPT_LAYER_CONTRACT {shot_id}: four-layer shot missing {field}"
                        )
                if draft_ids:
                    errors.append(
                        f"E_LEGACY_PROMPT_LAYER_READ_ONLY {shot_id}: current shot cannot bind "
                        "provider_neutral_draft_ids"
                    )
            if shot.get("generation_required") is True:
                generation_shot_ids.add(shot_id)
                if not alpha7 and not prompt_ids:
                    errors.append(f"{shot_id}: generation-required shot lacks provider prompt coverage")
                if shot.get("no_generation_reason") is not None:
                    errors.append(f"{shot_id}: generation-required shot cannot use no_generation_reason")
            else:
                no_generation_shot_ids.add(shot_id)
                if (
                    prompt_ids or draft_ids or transform_plan_ids
                    or neutral_execution_prompt_ids or master_ids
                ):
                    errors.append(f"{shot_id}: NO_GENERATION_REQUIRED shot cannot carry prompt coverage")
                if not nonempty(shot.get("no_generation_reason")):
                    errors.append(f"{shot_id}: non-generation shot requires explicit no_generation_reason")
                elif re.search(r"类推|同上|参考前镜|沿用前述|etc\.?$", str(shot.get("no_generation_reason")), flags=re.IGNORECASE):
                    errors.append(f"{shot_id}: no_generation_reason cannot use shorthand or analogy in place of coverage")
            missing_unknowns = set(map(str, as_list(shot.get("protected_unknown_ids")))) - set(unknown_by_id)
            missing_quantities = set(map(str, as_list(shot.get("quantity_ids")))) - set(quantity_by_id)
            missing_boundaries = set(map(str, as_list(shot.get("causal_boundary_ids")))) - set(boundary_by_id)
            if missing_unknowns:
                errors.append(f"{shot_id}: references unknown protected_unknown_ids {sorted(missing_unknowns)}")
            if missing_quantities:
                errors.append(f"{shot_id}: references unknown quantity_ids {sorted(missing_quantities)}")
            if missing_boundaries:
                errors.append(f"{shot_id}: references unknown causal_boundary_ids {sorted(missing_boundaries)}")
            for prompt_id in prompt_ids:
                prompt = prompt_by_id.get(prompt_id)
                if not prompt:
                    errors.append(f"{shot_id}: references unknown provider prompt {prompt_id}")
                elif str(prompt.get("shot_id")) != shot_id:
                    errors.append(f"{shot_id}: provider prompt {prompt_id} points to another shot")
            for master_id in master_ids:
                master = master_prompt_by_id.get(master_id)
                if not master:
                    errors.append(f"{shot_id}: references unknown MASTER prompt {master_id}")
                elif str(master.get("shot_id")) != shot_id:
                    errors.append(f"{shot_id}: MASTER prompt {master_id} points to another shot")
            for draft_id in draft_ids:
                draft = neutral_draft_by_id.get(draft_id)
                if not draft:
                    errors.append(f"{shot_id}: references unknown neutral DRAFT prompt {draft_id}")
                elif str(draft.get("shot_id")) != shot_id:
                    errors.append(f"{shot_id}: neutral DRAFT prompt {draft_id} points to another shot")
            for transform_plan_id in transform_plan_ids:
                transform_plan = transform_plan_by_id.get(transform_plan_id)
                if not transform_plan:
                    errors.append(
                        f"{shot_id}: references unknown TRANSFORM_PLAN {transform_plan_id}"
                    )
                elif str(transform_plan.get("shot_id")) != shot_id:
                    errors.append(
                        f"{shot_id}: TRANSFORM_PLAN {transform_plan_id} points to another shot"
                    )
            for neutral_execution_prompt_id in neutral_execution_prompt_ids:
                neutral_execution_prompt = neutral_execution_prompt_by_id.get(
                    neutral_execution_prompt_id
                )
                if not neutral_execution_prompt:
                    errors.append(
                        f"{shot_id}: references unknown NEUTRAL_EXECUTION_PROMPT "
                        f"{neutral_execution_prompt_id}"
                    )
                elif str(neutral_execution_prompt.get("shot_id")) != shot_id:
                    errors.append(
                        f"{shot_id}: NEUTRAL_EXECUTION_PROMPT "
                        f"{neutral_execution_prompt_id} points to another shot"
                    )

            duration_semantics = shot.get("duration_semantics")
            duration_sources = set(
                map(str, as_list(shot.get("duration_source_or_evidence_ids")))
            )
            if duration_semantics == "EXACT_PROVIDER_BOUND":
                provider_id = str(shot.get("duration_provider_registry_id"))
                provider = provider_by_id.get(provider_id)
                if not provider or not duration_sources:
                    errors.append(
                        f"E_DURATION_EVIDENCE_INVALID {shot_id}: exact duration needs a bound "
                        "provider snapshot and evidence"
                    )
                elif not any(
                    capability.get("claim_kind") == "EXACT_DURATION"
                    and capability.get("status") == "VERIFIED"
                    and float(capability.get("exact_duration_seconds", -1)) == float(duration)
                    and duration_sources
                    <= set(map(str, as_list(capability.get("source_or_evidence_ids"))))
                    for capability in as_list(provider.get("capabilities"))
                    if isinstance(capability, dict)
                ):
                    errors.append(
                        f"E_DURATION_EVIDENCE_INVALID {shot_id}: no matching VERIFIED exact-duration "
                        "capability covers the declared evidence"
                    )
            elif duration_semantics == "TARGET" and shot.get(
                "duration_provider_registry_id"
            ) is not None:
                errors.append(
                    f"E_DURATION_EVIDENCE_INVALID {shot_id}: TARGET duration cannot claim a provider binding"
                )
        if isinstance(canonical, dict) and durations:
            if plan.get("canonical_duration_version") != canonical.get("version"):
                errors.append(f"{pid}: canonical duration version mismatch")
            total = sum(durations)
            target = canonical.get("value")
            if isinstance(target, (int, float)):
                gap = abs(total - float(target))
                tolerance = plan.get("duration_tolerance")
                allowed = 0.0
                if isinstance(tolerance, dict):
                    amount = tolerance.get("value")
                    if isinstance(amount, (int, float)):
                        allowed = float(amount) * float(target) if tolerance.get("unit") == "ratio" else float(amount)
                    if tolerance.get("precision_status") not in {"USER_STATED", "VERIFIED", "EXPERIMENT_DESIGN"} or not as_list(tolerance.get("source_or_evidence_ids")):
                        errors.append(f"{pid}: duration tolerance lacks approved/evidenced basis")
                    tolerance_sources = set(
                        map(str, as_list(tolerance.get("source_or_evidence_ids")))
                    )
                    missing_tolerance_sources = tolerance_sources - known_precision_sources
                    if missing_tolerance_sources:
                        errors.append(
                            f"E_DURATION_EVIDENCE_INVALID {pid}: duration tolerance references unknown sources "
                            f"{sorted(missing_tolerance_sources)}"
                        )
                    if alpha7 and tolerance.get("precision_status") == "VERIFIED":
                        for evidence_id in tolerance_sources & set(evidence_by_id):
                            scoped_plan_ids = scope_list(
                                evidence_scope(evidence_by_id[evidence_id]), "shot_plan_ids"
                            )
                            if str(pid) not in scoped_plan_ids:
                                errors.append(
                                    f"E_DURATION_EVIDENCE_INVALID {pid}: VERIFIED tolerance evidence "
                                    f"{evidence_id} does not cover this shot plan"
                                )
                if gap > allowed + 1e-9:
                    errors.append(f"{pid}: shot total {total:g}s does not reconcile with canonical duration {float(target):g}s")
        elif durations and legacy_generation:
            errors.append(f"{pid}: shot plan requires one canonical_duration")
        if plan.get("reuse_mode") == "CROP_REFRAME_ONLY" and plan.get("format_variants_require_different_camera") is True:
            errors.append(f"{pid}: crop/reframe-only conflicts with different camera variants")
        if plan.get("reuse_mode") == "TESTED_COMMON_SAFE_ZONE" and not as_list(plan.get("safe_zone_evidence_ids")):
            errors.append(f"{pid}: tested common safe zone requires evidence")
        if alpha7 and plan.get("reuse_mode") == "TESTED_COMMON_SAFE_ZONE":
            safe_evidence_ids = set(map(str, as_list(plan.get("safe_zone_evidence_ids"))))
            missing_safe_evidence = safe_evidence_ids - set(evidence_by_id)
            if missing_safe_evidence:
                errors.append(
                    f"E_SAFE_ZONE_EVIDENCE_INVALID {pid}: unknown safe-zone evidence "
                    f"{sorted(missing_safe_evidence)}"
                )
            for evidence_id in safe_evidence_ids - missing_safe_evidence:
                scope = evidence_scope(evidence_by_id[evidence_id])
                if str(pid) not in scope_list(scope, "shot_plan_ids") or not plan_format_ids <= scope_list(
                    scope, "format_variant_ids"
                ):
                    errors.append(
                        f"E_SAFE_ZONE_EVIDENCE_INVALID {pid}: evidence {evidence_id} does not cover "
                        "this plan and all format variants"
                    )

    for asset in registry:
        if not isinstance(asset, dict):
            errors.append("asset registry entry must be an object")
            continue
        asset_id = str(asset.get("id", "<asset>"))
        asset_evidence = set(map(str, as_list(asset.get("evidence_ids"))))
        missing_asset_evidence = asset_evidence - set(evidence_by_id)
        if missing_asset_evidence:
            errors.append(f"{asset_id}: references unknown evidence {sorted(missing_asset_evidence)}")
        if alpha7 and asset.get("status") == "REAL_ARTIFACT_AVAILABLE":
            artifact_id = str(asset.get("artifact_id", ""))
            bound_artifact = artifact_by_id.get(artifact_id)
            if (
                not bound_artifact
                or bound_artifact.get("real_artifact_present") is not True
                or str(bound_artifact.get("version")) != str(asset.get("version"))
                or not nonempty(asset.get("real_file_location"))
                or not asset_evidence
            ):
                errors.append(
                    f"E_REAL_ARTIFACT_CONTRADICTION {asset_id}: real asset status requires a matching "
                    "versioned real artifact, file location, and evidence"
                )
        for shot_ref in map(str, as_list(asset.get("shot_refs"))):
            if shot_ref not in all_shot_ids:
                errors.append(f"{asset_id}: asset registry references unknown shot {shot_ref}")
        for dependency_id in map(str, as_list(asset.get("dependency_ids"))):
            if dependency_id not in asset_by_id:
                errors.append(f"{asset_id}: asset registry references unknown dependency {dependency_id}")
        for observation_id in map(str, as_list(asset.get("observation_ids"))):
            if observation_id not in observation_by_id:
                errors.append(f"{asset_id}: asset registry references unknown observation {observation_id}")
        missing_unknowns = set(map(str, as_list(asset.get("protected_unknown_ids")))) - set(unknown_by_id)
        missing_quantities = set(map(str, as_list(asset.get("quantity_ids")))) - set(quantity_by_id)
        missing_boundaries = set(map(str, as_list(asset.get("causal_boundary_ids")))) - set(boundary_by_id)
        if missing_unknowns:
            errors.append(f"{asset_id}: references unknown protected_unknown_ids {sorted(missing_unknowns)}")
        if missing_quantities:
            errors.append(f"{asset_id}: references unknown quantity_ids {sorted(missing_quantities)}")
        if missing_boundaries:
            errors.append(f"{asset_id}: references unknown causal_boundary_ids {sorted(missing_boundaries)}")
        if asset.get("benchmark_case_id") is not None:
            if as_list(asset.get("shot_refs")):
                errors.append(f"{asset_id}: BENCHMARK_ONLY asset cannot enter production shot_refs")

    known_age_sources = set(evidence_by_id) | set(decision_by_id) | set(approval_by_id)
    profile_asset_ids: set[str] = set()
    for profile_id, profile in minor_profile_by_id.items():
        asset_id = str(profile.get("asset_id"))
        asset = asset_by_id.get(asset_id)
        profile_asset_ids.add(asset_id)
        if (
            not asset
            or asset.get("asset_type") != "CHARACTER"
            or asset.get("subject_age_class") != "MINOR"
            or str(asset.get("minor_safety_profile_id")) != profile_id
        ):
            errors.append(
                f"E_MINOR_SAFETY_BINDING {profile_id}: profile must bind exactly one MINOR character asset"
            )
        if profile.get("is_minor") is not True:
            errors.append(f"E_MINOR_SAFETY_BINDING {profile_id}: is_minor must remain true")
        age = profile.get("age_years")
        majority_age = profile.get("majority_age_years")
        if isinstance(age, int) and isinstance(majority_age, int) and age >= majority_age:
            errors.append(
                f"E_MINOR_AGE_ADULTIZED {profile_id}: source age must remain below the applicable majority age"
            )
        for source_field in ("age_source_ids", "age_rule_source_or_evidence_ids"):
            source_ids = set(map(str, as_list(profile.get(source_field))))
            unresolved = source_ids - known_age_sources
            if unresolved:
                errors.append(
                    f"E_MINOR_SAFETY_BINDING {profile_id}: unresolved {source_field} {sorted(unresolved)}"
                )
        mode = profile.get("minor_compilation_mode")
        if mode == "EXACT" and (
            not isinstance(age, int) or profile.get("compiled_age_years") != age
        ):
            errors.append(
                f"E_MINOR_AGE_ADULTIZED {profile_id}: EXACT compilation must preserve age_years exactly"
            )
        if mode == "LIFE_STAGE":
            compiled_stage = profile.get("compiled_life_stage")
            source_stage = profile.get("source_life_stage")
            if compiled_stage not in {
                "INFANT", "CHILD", "EARLY_ADOLESCENT", "LATE_ADOLESCENT"
            } or source_stage == "UNKNOWN" or compiled_stage != source_stage:
                errors.append(
                    f"E_MINOR_AGE_ADULTIZED {profile_id}: LIFE_STAGE compilation cannot change the source life stage"
                )
        if mode == "REFERENCE_BOUND":
            missing_refs = set(map(str, as_list(profile.get("reference_asset_ids")))) - set(
                asset_by_id
            )
            if missing_refs:
                errors.append(
                    f"E_MINOR_SAFETY_BINDING {profile_id}: unknown reference assets {sorted(missing_refs)}"
                )
        alternative = profile.get("compatibility_alternative")
        if isinstance(alternative, dict) and (
            alternative.get("preserves_source_age_fact") is not True
            or alternative.get("review_bypass_forbidden") is not True
            or alternative.get("review_status") not in {"REQUIRED", "PASSED"}
            or (
                alternative.get("used_in_compilation") is True
                and alternative.get("review_status") != "PASSED"
            )
        ):
            errors.append(
                f"E_MINOR_REVIEW_BYPASS {profile_id}: compatibility alternative cannot bypass age safety review"
            )

    for asset_id, asset in asset_by_id.items():
        age_class = asset.get("subject_age_class")
        profile_id = asset.get("minor_safety_profile_id")
        if asset.get("asset_type") == "CHARACTER":
            if age_class == "MINOR" and str(profile_id) not in minor_profile_by_id:
                errors.append(
                    f"E_MINOR_SAFETY_BINDING {asset_id}: MINOR character requires a resolved minor profile"
                )
            if age_class != "MINOR" and profile_id is not None:
                errors.append(
                    f"E_MINOR_SAFETY_BINDING {asset_id}: non-minor character cannot bind a minor profile"
                )
        elif alpha7 and (age_class != "NOT_APPLICABLE" or profile_id is not None):
            errors.append(
                f"E_MINOR_SAFETY_BINDING {asset_id}: non-character age fields must be NOT_APPLICABLE/null"
            )
    expected_profile_assets = {
        asset_id
        for asset_id, asset in asset_by_id.items()
        if asset.get("asset_type") == "CHARACTER" and asset.get("subject_age_class") == "MINOR"
    }
    if profile_asset_ids != expected_profile_assets:
        errors.append(
            "E_MINOR_SAFETY_BINDING minor_safety_profiles: profile assets must exactly match MINOR assets"
        )

    for shot_id, shot in shot_by_id.items():
        shot_assets = {
            asset_id
            for asset_id in map(str, as_list(shot.get("asset_ids")))
            if asset_id in asset_by_id
        }
        has_minor = any(
            asset_by_id[asset_id].get("subject_age_class") == "MINOR"
            for asset_id in shot_assets
        )
        has_adult = any(
            asset_by_id[asset_id].get("subject_age_class") == "ADULT"
            for asset_id in shot_assets
        )
        declared_dual = shot.get("minor_adult_same_shot") is True
        strategy = shot.get("minor_adult_same_shot_strategy")
        if has_minor and has_adult:
            if not declared_dual or strategy not in {"COMPOSITE", "DECOMPOSITION"}:
                errors.append(
                    f"E_MINOR_ADULT_SAME_SHOT_UNDECLARED {shot_id}: minor/adult same-shot work "
                    "requires COMPOSITE or DECOMPOSITION"
                )
            elif (
                shot.get("generation_required") is not False
                or any(
                    as_list(shot.get(field))
                    for field in (
                        "master_prompt_ids", "provider_neutral_draft_ids",
                        "transform_plan_ids", "neutral_execution_prompt_ids",
                        "provider_prompt_ids",
                    )
                )
            ):
                errors.append(
                    f"E_MINOR_ADULT_SAME_SHOT_UNDECLARED {shot_id}: dual-age aggregate shot is a "
                    "non-generation composite/decomposition target and cannot carry executable Prompts"
                )
            elif strategy == "COMPOSITE":
                artifact = artifact_by_id.get(str(shot.get("composite_plan_artifact_id")))
                locator = artifact.get("content_locator") if isinstance(artifact, dict) else None
                if (
                    not artifact
                    or artifact.get("artifact_class") != "TEXT_SPEC"
                    or not isinstance(locator, dict)
                    or not nonempty(locator.get("sha256"))
                ):
                    errors.append(
                        f"E_MINOR_ADULT_SAME_SHOT_UNDECLARED {shot_id}: COMPOSITE requires a hashed TEXT_SPEC plan"
                    )
            elif strategy == "DECOMPOSITION":
                component_ids = set(map(str, as_list(shot.get("decomposition_shot_ids"))))
                component_shots = [shot_by_id.get(component_id) for component_id in component_ids]
                invalid_components = (
                    len(component_ids) < 2
                    or shot_id in component_ids
                    or component_ids - all_shot_ids
                    or any(
                        shot_plan_for_shot.get(component_id) != shot_plan_for_shot.get(shot_id)
                        for component_id in component_ids
                    )
                )
                for component in component_shots:
                    if not isinstance(component, dict):
                        continue
                    component_assets = {
                        asset_id
                        for asset_id in map(str, as_list(component.get("asset_ids")))
                        if asset_id in asset_by_id
                    }
                    component_has_minor = any(
                        asset_by_id[asset_id].get("subject_age_class") == "MINOR"
                        for asset_id in component_assets
                    )
                    component_has_adult = any(
                        asset_by_id[asset_id].get("subject_age_class") == "ADULT"
                        for asset_id in component_assets
                    )
                    invalid_components = invalid_components or (
                        component_has_minor and component_has_adult
                    )
                if invalid_components:
                    errors.append(
                        f"E_MINOR_ADULT_SAME_SHOT_UNDECLARED {shot_id}: DECOMPOSITION requires at least two "
                        "same-plan components, each containing no minor/adult co-presence"
                    )
        elif declared_dual or strategy is not None:
            errors.append(
                f"E_MINOR_ADULT_SAME_SHOT_UNDECLARED {shot_id}: dual-age strategy declared without both age classes"
            )

    dialogue_ids_by_shot: dict[str, set[str]] = {}
    for dialogue_id, dialogue in dialogue_by_id.items():
        shot_id = str(dialogue.get("shot_id"))
        plan_id = str(dialogue.get("shot_plan_id"))
        dialogue_ids_by_shot.setdefault(shot_id, set()).add(dialogue_id)
        plan = shot_plan_by_id.get(plan_id)
        if not plan or shot_plan_for_shot.get(shot_id) != plan_id:
            errors.append(
                f"E_DIALOGUE_SCOPE {dialogue_id}: dialogue must resolve to its declared shot and plan"
            )
        elif str(dialogue.get("source_spec_version")) != str(
            plan.get("source_spec_version")
        ):
            errors.append(
                f"E_DIALOGUE_SCOPE {dialogue_id}: source spec version does not match shot plan"
            )
        speaker_id = dialogue.get("speaker_asset_id")
        if speaker_id is not None and (
            str(speaker_id) not in asset_by_id
            or asset_by_id[str(speaker_id)].get("asset_type") != "CHARACTER"
            or str(speaker_id)
            not in set(map(str, as_list(shot_by_id.get(shot_id, {}).get("asset_ids"))))
        ):
            errors.append(
                f"E_DIALOGUE_SCOPE {dialogue_id}: speaker must be a character asset in the shot"
            )
    for shot_id, shot in shot_by_id.items():
        if set(map(str, as_list(shot.get("dialogue_ids")))) != dialogue_ids_by_shot.get(
            shot_id, set()
        ):
            errors.append(
                f"E_DIALOGUE_SCOPE {shot_id}: shot dialogue_ids must exactly match dialogue inventory"
            )

    cue_dialogue_ids: list[str] = []
    for cue_id, cue in subtitle_by_id.items():
        dialogue_id = str(cue.get("dialogue_id"))
        dialogue = dialogue_by_id.get(dialogue_id)
        cue_dialogue_ids.append(dialogue_id)
        if not dialogue:
            errors.append(f"E_SUBTITLE_BACKLINK {cue_id}: unknown dialogue_id {dialogue_id}")
            continue
        shot_id = str(cue.get("shot_id"))
        plan_id = str(cue.get("shot_plan_id"))
        plan = shot_plan_by_id.get(plan_id, {})
        if (
            shot_id != str(dialogue.get("shot_id"))
            or plan_id != str(dialogue.get("shot_plan_id"))
            or str(cue.get("source_spec_version"))
            != str(dialogue.get("source_spec_version"))
            or str(cue.get("timing_spec_version"))
            != str(plan.get("canonical_duration_version"))
        ):
            errors.append(
                f"E_SUBTITLE_STALE_TIMECODE {cue_id}: dialogue/shot/plan/spec timing backlinks diverge"
            )
        expected_hash = hashlib.sha256(str(dialogue.get("text", "")).encode("utf-8")).hexdigest()
        if str(cue.get("dialogue_text_sha256", "")).lower() != expected_hash:
            errors.append(
                f"E_SUBTITLE_STALE_TIMECODE {cue_id}: dialogue text digest is stale"
            )
        if str(cue.get("text", "")) != str(dialogue.get("text", "")):
            errors.append(
                f"E_SUBTITLE_TEXT_MISMATCH {cue_id}: subtitle text must exactly match its dialogue"
            )
        start = cue.get("start_seconds")
        end = cue.get("end_seconds")
        interval = shot_intervals.get(shot_id)
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
            or float(end) <= float(start)
            or not interval
            or float(start) < interval[0] - 1e-9
            or float(end) > interval[1] + 1e-9
        ):
            errors.append(
                f"E_SUBTITLE_STALE_TIMECODE {cue_id}: cue must fall inside the linked shot interval"
            )
    required_subtitle_ids = {
        dialogue_id
        for dialogue_id, dialogue in dialogue_by_id.items()
        if dialogue.get("subtitle_required") is True
    }
    if set(cue_dialogue_ids) != required_subtitle_ids or len(cue_dialogue_ids) != len(
        set(cue_dialogue_ids)
    ):
        errors.append(
            "E_SUBTITLE_COVERAGE subtitle_cues: required dialogue coverage must be exact and unique; "
            f"missing={sorted(required_subtitle_ids - set(cue_dialogue_ids))}, "
            f"extra={sorted(set(cue_dialogue_ids) - required_subtitle_ids)}"
        )

    required_tts_ids = {
        dialogue_id
        for dialogue_id, dialogue in dialogue_by_id.items()
        if dialogue.get("tts_required") is True
    }
    tts_scope_occurrences: list[str] = []
    for coverage_id, coverage in tts_coverage_by_id.items():
        plan_ids = set(map(str, as_list(coverage.get("scope_shot_plan_ids"))))
        if plan_ids - set(shot_plan_by_id):
            errors.append(
                f"E_TTS_COVERAGE {coverage_id}: unresolved shot plans {sorted(plan_ids - set(shot_plan_by_id))}"
            )
        expected_scope = {
            dialogue_id
            for dialogue_id, dialogue in dialogue_by_id.items()
            if dialogue.get("tts_required") is True
            and str(dialogue.get("shot_plan_id")) in plan_ids
        }
        scope_ids = set(map(str, as_list(coverage.get("scope_dialogue_ids"))))
        tts_scope_occurrences.extend(scope_ids)
        covered_ids = set(map(str, as_list(coverage.get("covered_dialogue_ids"))))
        if scope_ids != expected_scope:
            errors.append(
                f"E_TTS_COVERAGE {coverage_id}: scope_dialogue_ids must equal required speech units"
            )
        if covered_ids - scope_ids:
            errors.append(f"E_TTS_COVERAGE {coverage_id}: covered dialogue is outside scope")
        status = coverage.get("tts_coverage_status")
        if (
            (status == "NOT_APPLICABLE" and (scope_ids or covered_ids))
            or (status == "NONE" and (not scope_ids or covered_ids))
            or (status == "PARTIAL" and (not covered_ids or covered_ids == scope_ids))
            or (status == "FULL" and (not scope_ids or covered_ids != scope_ids))
        ):
            errors.append(
                f"E_TTS_COVERAGE {coverage_id}: tts_coverage_status contradicts scope/covered sets"
            )

        bindings = [
            binding
            for binding in as_list(coverage.get("dialogue_audio_bindings"))
            if isinstance(binding, dict)
        ]
        binding_ids = [str(binding.get("dialogue_id")) for binding in bindings]
        if len(binding_ids) != len(set(binding_ids)) or set(binding_ids) != covered_ids:
            errors.append(
                f"E_TTS_AUDIO_BINDING {coverage_id}: covered dialogue needs one exact audio binding each"
            )
        binding_refs: set[tuple[str, str]] = set()
        derived_measured: set[str] = set()
        derived_duration = 0.0
        coverage_evidence = set(map(str, as_list(coverage.get("evidence_ids"))))
        unknown_coverage_evidence = coverage_evidence - set(evidence_by_id)
        if unknown_coverage_evidence:
            errors.append(
                f"E_TTS_AUDIO_BINDING {coverage_id}: unresolved evidence IDs "
                f"{sorted(unknown_coverage_evidence)}"
            )
        for binding in bindings:
            dialogue_id = str(binding.get("dialogue_id"))
            artifact_id = str(binding.get("artifact_id"))
            version = str(binding.get("artifact_version"))
            artifact = artifact_by_id.get(artifact_id)
            if (
                not artifact
                or str(artifact.get("version")) != version
                or artifact.get("artifact_class") != "MEDIA"
            ):
                errors.append(
                    f"E_TTS_AUDIO_BINDING {coverage_id}: binding requires a MEDIA artifact "
                    f"{artifact_id}@{version}"
                )
            binding_refs.add((artifact_id, version))
            measured = binding.get("measured_duration_seconds")
            if isinstance(measured, (int, float)) and not isinstance(measured, bool):
                derived_measured.add(dialogue_id)
                derived_duration += float(measured)
                locator = artifact.get("content_locator") if isinstance(artifact, dict) else None
                artifact_evidence = set(
                    map(str, as_list(artifact.get("evidence_ids")))
                ) if isinstance(artifact, dict) else set()
                if (
                    float(measured) <= 0
                    or not artifact
                    or artifact.get("artifact_class") != "MEDIA"
                    or artifact.get("real_artifact_present") is not True
                    or artifact.get("execution_mode") != "REAL"
                    or not isinstance(locator, dict)
                    or not nonempty(locator.get("sha256"))
                    or not artifact_evidence
                    or not coverage_evidence
                    or not (artifact_evidence & coverage_evidence)
                ):
                    errors.append(
                        f"E_TTS_MEASUREMENT {coverage_id}: measured dialogue {dialogue_id} requires "
                        "positive duration and a real, hashed MEDIA artifact with matching evidence"
                    )
        declared_refs = versioned_refs(coverage.get("output_artifact_refs"))
        if declared_refs != binding_refs:
            errors.append(
                f"E_TTS_AUDIO_BINDING {coverage_id}: output_artifact_refs must exactly match bindings"
            )
        measured_ids = set(map(str, as_list(coverage.get("measured_dialogue_ids"))))
        if measured_ids != derived_measured or measured_ids - scope_ids:
            errors.append(
                f"E_TTS_MEASUREMENT {coverage_id}: measured dialogue set contradicts bindings/scope"
            )
        measurement_status = coverage.get("measurement_coverage_status")
        if (
            (measurement_status == "NONE" and measured_ids)
            or (measurement_status == "PARTIAL" and (not measured_ids or measured_ids == scope_ids))
            or (
                measurement_status == "FULL"
                and (not scope_ids or measured_ids != scope_ids)
            )
        ):
            errors.append(
                f"E_TTS_MEASUREMENT {coverage_id}: measurement coverage status contradicts measured set"
            )
        aggregate = coverage.get("measured_duration_seconds")
        if measurement_status == "NONE":
            if aggregate is not None:
                errors.append(
                    f"E_TTS_MEASUREMENT {coverage_id}: NONE measurement cannot carry aggregate duration"
                )
        elif (
            not isinstance(aggregate, (int, float))
            or isinstance(aggregate, bool)
            or abs(float(aggregate) - derived_duration) > 1e-9
        ):
            errors.append(
                f"E_TTS_MEASUREMENT {coverage_id}: aggregate duration must equal measured bindings"
            )
        if measurement_status != "FULL" and any(
            coverage_id
            in set(map(str, as_list(shot.get("duration_source_or_evidence_ids"))))
            for shot in shot_by_id.values()
        ):
            errors.append(
                f"E_TTS_PARTIAL_DURATION_BASIS {coverage_id}: partial measurement cannot support full-shot duration"
            )

    if (
        set(tts_scope_occurrences) != required_tts_ids
        or len(tts_scope_occurrences) != len(set(tts_scope_occurrences))
    ):
        errors.append(
            "E_TTS_COVERAGE tts_coverage_records: every tts_required dialogue must occur in exactly "
            "one coverage scope"
        )

    for master in master_prompts:
        if not isinstance(master, dict):
            errors.append("MASTER prompt must be an object")
            continue
        master_id = str(master.get("id", "<master-prompt>"))
        if alpha7 and master.get("prompt_layer") != "PROVIDER_NEUTRAL_MASTER":
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {master_id}: prompt_layer must be PROVIDER_NEUTRAL_MASTER"
            )
        if not nonempty(master.get("intent_summary_zh")) or not contains_cjk(
            master.get("intent_summary_zh")
        ):
            errors.append(f"{master_id}: MASTER requires Chinese intent_summary_zh")
        target_type = str(master.get("target_type", ""))
        target_id = str(master.get("target_id", ""))
        role = str(master.get("generation_role", ""))
        medium = str(master.get("generation_medium", ""))
        shot_id = str(master.get("shot_id", ""))
        if current_quality_contract:
            if not generation_role_matches_medium(role, medium):
                errors.append(f"E_PROMPT_MEDIUM_MISMATCH {master_id}: generation role/medium conflict")
            if target_type == "SHOT":
                if target_id not in generation_shot_ids or shot_id != target_id:
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {master_id}: SHOT target must bind a generation shot and matching shot_id"
                    )
                if role in {"ASSET_REFERENCE", "ASSET_MOTION_REFERENCE"}:
                    errors.append(f"E_PROVIDER_PROMPT_UNBOUND {master_id}: asset-reference roles cannot target SHOT")
            elif target_type == "ASSET":
                if target_id not in asset_by_id or master.get("shot_id") is not None:
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {master_id}: ASSET target must bind a real asset and null shot_id"
                    )
                if role not in {"ASSET_REFERENCE", "ASSET_MOTION_REFERENCE", "CUSTOM"}:
                    errors.append(f"E_PROVIDER_PROMPT_UNBOUND {master_id}: shot role cannot target ASSET")
            else:
                errors.append(f"E_PROVIDER_PROMPT_UNBOUND {master_id}: target_type must be ASSET or SHOT")
        elif shot_id not in generation_shot_ids:
            errors.append(f"{master_id}: MASTER may only cover a generation-required shot")
        master_assets = set(map(str, as_list(master.get("asset_ids"))))
        if master_assets - set(asset_by_id):
            errors.append(f"{master_id}: references unregistered assets {sorted(master_assets - set(asset_by_id))}")
        missing_unknowns = set(map(str, as_list(master.get("protected_unknown_ids")))) - set(unknown_by_id)
        missing_quantities = set(map(str, as_list(master.get("quantity_ids")))) - set(quantity_by_id)
        missing_boundaries = set(map(str, as_list(master.get("causal_boundary_ids")))) - set(boundary_by_id)
        if missing_unknowns or missing_quantities or missing_boundaries:
            errors.append(f"{master_id}: MASTER references unresolved protected constraints")
        target_asset_ids = (
            set(map(str, as_list(shot_by_id.get(target_id, {}).get("asset_ids"))))
            if current_quality_contract and target_type == "SHOT"
            else ({target_id} if current_quality_contract and target_type == "ASSET" else set(
                map(str, as_list(shot_by_id.get(shot_id, {}).get("asset_ids")))
            ))
        )
        if current_quality_contract and target_type == "ASSET" and target_id not in master_assets:
            errors.append(f"E_PROVIDER_PROMPT_UNBOUND {master_id}: ASSET target must occur in asset_ids")
        expected_minor_profiles = {
            str(asset_by_id[asset_id].get("minor_safety_profile_id"))
            for asset_id in target_asset_ids
            if asset_id in asset_by_id
            and asset_by_id[asset_id].get("subject_age_class") == "MINOR"
        }
        if set(map(str, as_list(master.get("minor_safety_profile_ids")))) != expected_minor_profiles:
            errors.append(
                f"E_MINOR_PROMPT_SCOPE {master_id}: minor profile backlinks must exactly match the shot"
            )
        master_reference_ids = set(map(str, as_list(master.get("reference_ids"))))
        unknown_reference_ids = master_reference_ids - set(reference_by_id)
        if unknown_reference_ids:
            errors.append(
                f"E_REFERENCE_UNKNOWN {master_id}: unknown reference IDs {sorted(unknown_reference_ids)}"
            )
        for reference_id in master_reference_ids - unknown_reference_ids:
            reference = reference_by_id[reference_id]
            asset = asset_by_id.get(str(reference.get("asset_id")))
            if (
                not asset
                or str(reference.get("version")) != str(asset.get("version"))
                or str(reference.get("asset_id")) not in master_assets
            ):
                errors.append(
                    f"E_REFERENCE_UNKNOWN {master_id}: reference {reference_id} is not bound to a "
                    "matching versioned MASTER asset"
                )
        for plan in shot_plans:
            plan_shots = {
                str(shot.get("shot_id"))
                for shot in as_list(plan.get("shots"))
                if isinstance(shot, dict)
            } if isinstance(plan, dict) else set()
            if target_type == "SHOT" and target_id in plan_shots and str(master.get("source_spec_version")) != str(
                plan.get("source_spec_version")
            ):
                errors.append(f"{master_id}: source spec version does not match shot plan")
        if (
            current_quality_contract and target_type == "ASSET" and target_id in asset_by_id
            and str(master.get("source_spec_version")) != str(asset_by_id[target_id].get("source_spec_version"))
        ):
            errors.append(f"{master_id}: source spec version does not match asset registry")

    for draft in provider_neutral_drafts:
        if not isinstance(draft, dict):
            errors.append("provider-neutral DRAFT prompt must be an object")
            continue
        draft_id = str(draft.get("id", "<neutral-draft>"))
        if draft.get("prompt_layer") != "PROVIDER_NEUTRAL_DRAFT":
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {draft_id}: prompt_layer must be PROVIDER_NEUTRAL_DRAFT"
            )
        if not nonempty(draft.get("intent_summary_zh")) or not contains_cjk(
            draft.get("intent_summary_zh")
        ):
            errors.append(f"{draft_id}: neutral DRAFT requires Chinese intent_summary_zh")
        master = master_prompt_by_id.get(str(draft.get("master_prompt_id")))
        if not master or master.get("prompt_layer") != "PROVIDER_NEUTRAL_MASTER":
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {draft_id}: master_prompt_id must resolve to MASTER"
            )
            continue
        scalar_fields = (
            "shot_id", "target_type", "target_id", "generation_role", "generation_medium",
            "source_spec_version",
        ) if current_quality_contract else ("shot_id", "source_spec_version")
        array_fields = (
            "asset_ids", "reference_ids", "minor_safety_profile_ids",
            "protected_unknown_ids", "quantity_ids", "causal_boundary_ids",
        )
        if any(str(draft.get(field)) != str(master.get(field)) for field in scalar_fields) or any(
            set(map(str, as_list(draft.get(field))))
            != set(map(str, as_list(master.get(field))))
            for field in array_fields
        ):
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {draft_id}: neutral DRAFT scope diverges from MASTER"
            )

    prompt_scope_scalar_fields = (
        "shot_id", "target_type", "target_id", "generation_role", "generation_medium",
        "source_spec_version",
    ) if current_quality_contract else ("shot_id", "source_spec_version")
    prompt_scope_array_fields = (
        "asset_ids", "reference_ids", "minor_safety_profile_ids",
        "protected_unknown_ids", "quantity_ids", "causal_boundary_ids",
    )

    def prompt_scope_diverges(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return any(
            str(left.get(field)) != str(right.get(field))
            for field in prompt_scope_scalar_fields
        ) or any(
            set(map(str, as_list(left.get(field))))
            != set(map(str, as_list(right.get(field))))
            for field in prompt_scope_array_fields
        )

    for transform_plan in transform_plans:
        if not isinstance(transform_plan, dict):
            errors.append("TRANSFORM_PLAN must be an object")
            continue
        transform_plan_id = str(transform_plan.get("id", "<transform-plan>"))
        if transform_plan.get("prompt_layer") != "TRANSFORM_PLAN":
            errors.append(
                f"E_PROMPT_LAYER_CONTRACT {transform_plan_id}: prompt_layer must be TRANSFORM_PLAN"
            )
        if not nonempty(transform_plan.get("intent_summary_zh")) or not contains_cjk(
            transform_plan.get("intent_summary_zh")
        ):
            errors.append(
                f"{transform_plan_id}: TRANSFORM_PLAN requires Chinese intent_summary_zh"
            )
        master = master_prompt_by_id.get(str(transform_plan.get("master_prompt_id")))
        if not master or master.get("prompt_layer") != "PROVIDER_NEUTRAL_MASTER":
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {transform_plan_id}: master_prompt_id must resolve to MASTER"
            )
            continue
        if prompt_scope_diverges(transform_plan, master):
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {transform_plan_id}: TRANSFORM_PLAN scope diverges from MASTER"
            )
        section_kinds = {
            str(section.get("kind"))
            for section in as_list(transform_plan.get("prompt_sections"))
            if isinstance(section, dict)
        }
        if section_kinds != {"TRANSFORM_PLAN"}:
            errors.append(
                f"E_PROMPT_LAYER_ROLE_CONFLICT {transform_plan_id}: TRANSFORM_PLAN sections "
                "must be planning-only"
            )

    for neutral_execution_prompt in neutral_execution_prompts:
        if not isinstance(neutral_execution_prompt, dict):
            errors.append("NEUTRAL_EXECUTION_PROMPT must be an object")
            continue
        neutral_execution_prompt_id = str(
            neutral_execution_prompt.get("id", "<neutral-execution-prompt>")
        )
        if neutral_execution_prompt.get("prompt_layer") != "NEUTRAL_EXECUTION_PROMPT":
            errors.append(
                f"E_PROMPT_LAYER_CONTRACT {neutral_execution_prompt_id}: prompt_layer must be "
                "NEUTRAL_EXECUTION_PROMPT"
            )
        if not nonempty(neutral_execution_prompt.get("intent_summary_zh")) or not contains_cjk(
            neutral_execution_prompt.get("intent_summary_zh")
        ):
            errors.append(
                f"{neutral_execution_prompt_id}: NEUTRAL_EXECUTION_PROMPT requires Chinese intent_summary_zh"
            )
        master = master_prompt_by_id.get(
            str(neutral_execution_prompt.get("master_prompt_id"))
        )
        transform_plan = transform_plan_by_id.get(
            str(neutral_execution_prompt.get("transform_plan_id"))
        )
        if not master or master.get("prompt_layer") != "PROVIDER_NEUTRAL_MASTER":
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {neutral_execution_prompt_id}: "
                "master_prompt_id must resolve to MASTER"
            )
        if (
            not transform_plan
            or transform_plan.get("prompt_layer") != "TRANSFORM_PLAN"
            or str(transform_plan.get("master_prompt_id"))
            != str(neutral_execution_prompt.get("master_prompt_id"))
        ):
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {neutral_execution_prompt_id}: transform_plan_id "
                "must resolve to the bound MASTER"
            )
        if master and prompt_scope_diverges(neutral_execution_prompt, master):
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {neutral_execution_prompt_id}: "
                "NEUTRAL_EXECUTION_PROMPT scope diverges from MASTER"
            )
        if transform_plan and prompt_scope_diverges(neutral_execution_prompt, transform_plan):
            errors.append(
                f"E_PROVIDER_PROMPT_UNBOUND {neutral_execution_prompt_id}: "
                "NEUTRAL_EXECUTION_PROMPT scope diverges from TRANSFORM_PLAN"
            )
        if transform_plan and normalized_prompt_text(
            neutral_execution_prompt.get("neutral_execution_prompt_text")
        ) == normalized_prompt_text(transform_plan.get("transform_plan_text")):
            errors.append(
                f"E_PROMPT_LAYER_ROLE_CONFLICT {neutral_execution_prompt_id}: executable-neutral "
                "Prompt cannot be a renamed TRANSFORM_PLAN"
            )
        if any(
            isinstance(section, dict) and section.get("kind") == "TRANSFORM_PLAN"
            for section in as_list(neutral_execution_prompt.get("prompt_sections"))
        ):
            errors.append(
                f"E_PROMPT_LAYER_ROLE_CONFLICT {neutral_execution_prompt_id}: "
                "NEUTRAL_EXECUTION_PROMPT cannot contain planning-only sections"
            )

    for prompt in provider_prompts:
        if not isinstance(prompt, dict):
            errors.append("provider prompt must be an object")
            continue
        prompt_id = prompt.get("id", "<provider-prompt>")
        prompt_locale = prompt.get("prompt_locale")
        if not nonempty(prompt_locale):
            errors.append(f"{prompt_id}: prompt_locale is required")
        summary = prompt.get("intent_summary_zh")
        if not nonempty(summary) or not contains_cjk(summary):
            errors.append(f"{prompt_id}: every provider prompt requires Chinese intent_summary_zh")
        shot_id = prompt.get("shot_id")
        target_type = str(prompt.get("target_type", ""))
        target_id = str(prompt.get("target_id", ""))
        role = str(prompt.get("generation_role", ""))
        declared_medium = str(prompt.get("generation_medium", ""))
        if current_quality_contract:
            if not generation_role_matches_medium(role, declared_medium):
                errors.append(f"E_PROMPT_MEDIUM_MISMATCH {prompt_id}: generation role/medium conflict")
            if target_type == "SHOT":
                if target_id not in generation_shot_ids or str(shot_id) != target_id:
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: SHOT target must bind a generation shot and matching shot_id"
                    )
                if role in {"ASSET_REFERENCE", "ASSET_MOTION_REFERENCE"}:
                    errors.append(f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: asset-reference roles cannot target SHOT")
            elif target_type == "ASSET":
                if target_id not in asset_by_id or shot_id is not None:
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: ASSET target must bind a real asset and null shot_id"
                    )
                if role not in {"ASSET_REFERENCE", "ASSET_MOTION_REFERENCE", "CUSTOM"}:
                    errors.append(f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: shot role cannot target ASSET")
            else:
                errors.append(f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: target_type must be ASSET or SHOT")
        elif shot_id is None or str(shot_id) not in all_shot_ids:
            errors.append(f"{prompt_id}: references unknown shot {shot_id}")
        elif str(shot_id) not in generation_shot_ids:
            errors.append(f"{prompt_id}: provider prompt may only cover a generation-required shot")
        missing_assets = set(map(str, as_list(prompt.get("asset_ids")))) - set(asset_by_id)
        if missing_assets:
            errors.append(f"{prompt_id}: references unregistered assets {sorted(missing_assets)}")
        registry_id = prompt.get("provider_registry_id")
        if registry_id is not None and str(registry_id) not in provider_by_id:
            errors.append(f"{prompt_id}: references unknown provider registry entry {registry_id}")
        if alpha7:
            prompt_layer = prompt.get("prompt_layer")
            prompt_chain_fields = (
                ("transform_plan_id", "neutral_execution_prompt_id")
                if four_layer_prompt_contract else ("provider_neutral_draft_id",)
            )
            for field in (
                "prompt_layer", "master_prompt_id",
                "target_type", "target_id", "generation_role", "generation_medium",
                "provider_registry_id", "provider_snapshot_id", "capability_evidence_ids",
                "reference_ids", "minor_safety_profile_ids", "source_spec_version",
                "requested_output_duration_seconds", "editorial_target_duration_seconds",
                "trim_to_editorial", "execution_contract",
            ) + prompt_chain_fields:
                if field not in prompt:
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: Alpha.7 prompt missing {field}"
                    )
            if four_layer_prompt_contract and "provider_neutral_draft_id" in prompt:
                errors.append(
                    f"E_LEGACY_PROMPT_LAYER_READ_ONLY {prompt_id}: current compiled Prompt cannot "
                    "bind provider_neutral_draft_id"
                )
            if not four_layer_prompt_contract and any(
                field in prompt for field in ("transform_plan_id", "neutral_execution_prompt_id")
            ):
                errors.append(
                    f"E_PROMPT_LAYER_CONTRACT {prompt_id}: legacy compiled Prompt cannot mix "
                    "four-layer chain fields"
                )
            if prompt_layer == "PROVIDER_COMPILED":
                bound_provider = provider_by_id.get(str(registry_id))
                source_prompt = master_prompt_by_id.get(str(prompt.get("master_prompt_id")))
                source_draft = neutral_draft_by_id.get(
                    str(prompt.get("provider_neutral_draft_id"))
                )
                source_transform_plan = transform_plan_by_id.get(
                    str(prompt.get("transform_plan_id"))
                )
                source_neutral_execution_prompt = neutral_execution_prompt_by_id.get(
                    str(prompt.get("neutral_execution_prompt_id"))
                )
                if (
                    not bound_provider
                    or not nonempty(prompt.get("provider"))
                    or str(prompt.get("provider")) != str(bound_provider.get("provider"))
                    or str(prompt.get("provider_snapshot_id"))
                    != str(bound_provider.get("snapshot_id"))
                ):
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: PROVIDER_COMPILED prompt must bind "
                        "the matching provider registry snapshot"
                    )
                if not source_prompt or source_prompt.get("prompt_layer") != "PROVIDER_NEUTRAL_MASTER":
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: master_prompt_id must resolve to a neutral MASTER"
                    )
                else:
                    if prompt_scope_diverges(prompt, source_prompt):
                        errors.append(
                            f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: compiled prompt scope diverges from its MASTER"
                        )
                if four_layer_prompt_contract:
                    if (
                        not source_transform_plan
                        or source_transform_plan.get("prompt_layer") != "TRANSFORM_PLAN"
                        or str(source_transform_plan.get("master_prompt_id"))
                        != str(prompt.get("master_prompt_id"))
                    ):
                        errors.append(
                            f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: transform_plan_id must resolve "
                            "to the bound MASTER"
                        )
                    elif prompt_scope_diverges(prompt, source_transform_plan):
                        errors.append(
                            f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: compiled prompt scope diverges "
                            "from TRANSFORM_PLAN"
                        )
                    if (
                        not source_neutral_execution_prompt
                        or source_neutral_execution_prompt.get("prompt_layer")
                        != "NEUTRAL_EXECUTION_PROMPT"
                        or str(source_neutral_execution_prompt.get("master_prompt_id"))
                        != str(prompt.get("master_prompt_id"))
                        or str(source_neutral_execution_prompt.get("transform_plan_id"))
                        != str(prompt.get("transform_plan_id"))
                    ):
                        errors.append(
                            f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: neutral_execution_prompt_id "
                            "must resolve through the bound TRANSFORM_PLAN and MASTER"
                        )
                    elif prompt_scope_diverges(prompt, source_neutral_execution_prompt):
                        errors.append(
                            f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: compiled prompt scope diverges "
                            "from NEUTRAL_EXECUTION_PROMPT"
                        )
                else:
                    if (
                        not source_draft
                        or source_draft.get("prompt_layer") != "PROVIDER_NEUTRAL_DRAFT"
                        or str(source_draft.get("master_prompt_id"))
                        != str(prompt.get("master_prompt_id"))
                    ):
                        errors.append(
                            f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: provider_neutral_draft_id must resolve "
                            "to the bound MASTER"
                        )
                    elif prompt_scope_diverges(prompt, source_draft):
                        errors.append(
                            f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: compiled prompt scope diverges from neutral DRAFT"
                        )

                shot = shot_by_id.get(target_id if current_quality_contract and target_type == "SHOT" else str(shot_id), {})
                editorial_duration = prompt.get("editorial_target_duration_seconds")
                requested_duration = prompt.get("requested_output_duration_seconds")
                trim_to_editorial = prompt.get("trim_to_editorial")
                medium = declared_medium if current_quality_contract else "VIDEO"
                execution_contract = str(prompt.get("execution_contract", ""))
                manual_copy_only = execution_contract == "MANUAL_COPY_TEXT_SPEC_ONLY"
                if execution_contract not in {
                    "MANUAL_COPY_TEXT_SPEC_ONLY", "GENERATION_EXECUTABLE",
                }:
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: execution_contract is invalid"
                    )
                if manual_copy_only:
                    provider_source = (
                        bound_provider.get("source")
                        if isinstance(bound_provider, dict)
                        and isinstance(bound_provider.get("source"), dict)
                        else {}
                    )
                    access_evidence_ids = set(
                        map(str, as_list((bound_provider or {}).get("access_source_ids")))
                    )
                    access_evidence_valid = bool(access_evidence_ids) and all(
                        evidence_id in evidence_by_id
                        and evidence_by_id[evidence_id].get("classification") == "USER_REPORTED"
                        and evidence_by_id[evidence_id].get("status") == "EFFECTIVE"
                        and evidence_applies_to_provider(
                            evidence_by_id[evidence_id], str(registry_id), bound_provider or {}
                        )
                        for evidence_id in access_evidence_ids
                    )
                    if (
                        not isinstance(bound_provider, dict)
                        or bound_provider.get("classification") != "USER_REPORTED"
                        or provider_source.get("source_type") != "USER_REPORTED"
                        or bound_provider.get("availability_kind") != "SURFACE_ONLY"
                        or bound_provider.get("access") not in {"AVAILABLE", "LIMITED"}
                        or bound_provider.get("model") != "SURFACE_MANAGED_UNKNOWN"
                        or bound_provider.get("version") != "SURFACE_MANAGED_UNKNOWN"
                        or bound_provider.get("project_pilot_status") != "NOT_RUN"
                        or not access_evidence_valid
                    ):
                        errors.append(
                            f"E_TEXT_SPEC_ONLY_PROVIDER_INVALID {prompt_id}: manual-copy Prompt "
                            "requires an effective USER_REPORTED SURFACE_ONLY snapshot with "
                            "SURFACE_MANAGED_UNKNOWN model/version and NOT_RUN Pilot"
                        )
                    if (
                        as_list((bound_provider or {}).get("capabilities"))
                        or as_list(prompt.get("capability_evidence_ids"))
                    ):
                        errors.append(
                            f"E_TEXT_SPEC_ONLY_CAPABILITY_CLAIM {prompt_id}: manual-copy Prompt "
                            "cannot claim provider capabilities or bind capability evidence"
                        )
                if medium == "IMAGE":
                    if (
                        requested_duration is not None
                        or editorial_duration is not None
                        or trim_to_editorial is not False
                    ):
                        errors.append(
                            f"E_DURATION_EVIDENCE_INVALID {prompt_id}: IMAGE prompt requires null durations, "
                            "and trim_to_editorial=false"
                        )
                    capability_evidence = set(
                        map(str, as_list(prompt.get("capability_evidence_ids")))
                    )
                    if capability_evidence:
                        matching_image_capabilities = [
                            capability
                            for capability in as_list(bound_provider.get("capabilities"))
                            if isinstance(capability, dict)
                            and capability.get("claim_kind") == "GENERAL"
                            and capability.get("status") in {"VERIFIED", "USER_REPORTED"}
                            and capability_evidence
                            <= set(map(str, as_list(capability.get("source_or_evidence_ids"))))
                        ] if bound_provider else []
                        if (
                            capability_evidence - set(evidence_by_id)
                            or "IMAGE_GENERATION" not in set(map(str, as_list((bound_provider or {}).get("modalities"))))
                            or not matching_image_capabilities
                        ):
                            errors.append(
                                f"E_PROVIDER_EVIDENCE_SCOPE {prompt_id}: IMAGE capability evidence must "
                                "resolve to this provider snapshot's IMAGE_GENERATION capability"
                            )
                elif medium == "VIDEO":
                    if not isinstance(editorial_duration, (int, float)) or isinstance(
                        editorial_duration, bool
                    ) or (
                        target_type == "SHOT"
                        and role == "SHOT_MOTION"
                        and float(editorial_duration) != float(shot.get("duration_seconds", -1))
                    ):
                        errors.append(
                            f"E_DURATION_EVIDENCE_INVALID {prompt_id}: editorial target must equal shot duration"
                        )
                    if manual_copy_only and (
                        requested_duration is not None or trim_to_editorial is not False
                    ):
                        errors.append(
                            f"E_TEXT_SPEC_ONLY_CAPABILITY_CLAIM {prompt_id}: manual-copy VIDEO Prompt "
                            "requires requested_output_duration_seconds=null and trim_to_editorial=false"
                        )
                    if (
                        isinstance(requested_duration, (int, float))
                        and not isinstance(requested_duration, bool)
                        and isinstance(editorial_duration, (int, float))
                    ):
                        needs_trim = float(requested_duration) != float(editorial_duration)
                        if trim_to_editorial is not needs_trim:
                            errors.append(
                                f"E_DURATION_EVIDENCE_INVALID {prompt_id}: trim_to_editorial contradicts requested/editorial durations"
                            )
                    capability_evidence = set(
                        map(str, as_list(prompt.get("capability_evidence_ids")))
                    )
                    matching_capabilities = [
                        capability
                        for capability in as_list(bound_provider.get("capabilities"))
                        if isinstance(capability, dict)
                        and capability.get("claim_kind") == "EXACT_DURATION"
                        and capability.get("status") == "VERIFIED"
                        and isinstance(capability.get("exact_duration_seconds"), (int, float))
                        and isinstance(requested_duration, (int, float))
                        and float(capability.get("exact_duration_seconds"))
                        == float(requested_duration)
                        and capability_evidence
                        <= set(map(str, as_list(capability.get("source_or_evidence_ids"))))
                    ] if bound_provider else []
                    if (
                        not manual_copy_only
                        and (
                            not capability_evidence
                            or capability_evidence - set(evidence_by_id)
                            or not matching_capabilities
                        )
                    ):
                        errors.append(
                            f"E_DURATION_EVIDENCE_INVALID {prompt_id}: requested duration lacks matching "
                            "provider snapshot capability evidence"
                        )
                else:
                    errors.append(
                        f"E_PROMPT_QUALITY_MISSING {prompt_id}: CURRENT quality record must declare IMAGE or VIDEO"
                    )
                unpassed_minor_profiles = {
                    profile_id
                    for profile_id in map(
                        str, as_list(prompt.get("minor_safety_profile_ids"))
                    )
                    if minor_profile_by_id.get(profile_id, {}).get("safety_review_status")
                    != "PASSED"
                }
                if unpassed_minor_profiles:
                    errors.append(
                        f"E_MINOR_REVIEW_BYPASS {prompt_id}: compiled Prompt references unpassed "
                        f"minor profiles {sorted(unpassed_minor_profiles)}"
                    )
                unpassed_alternatives = {
                    profile_id
                    for profile_id in map(
                        str, as_list(prompt.get("minor_safety_profile_ids"))
                    )
                    if isinstance(
                        minor_profile_by_id.get(profile_id, {}).get(
                            "compatibility_alternative"
                        ),
                        dict,
                    )
                    and minor_profile_by_id[profile_id]["compatibility_alternative"].get(
                        "review_status"
                    )
                    != "PASSED"
                }
                if unpassed_alternatives:
                    errors.append(
                        f"E_MINOR_REVIEW_BYPASS {prompt_id}: compiled Prompt references unpassed "
                        f"compatibility alternatives {sorted(unpassed_alternatives)}"
                    )
                unknown_age_characters = {
                    asset_id
                    for asset_id in map(str, as_list(prompt.get("asset_ids")))
                    if asset_by_id.get(asset_id, {}).get("asset_type") == "CHARACTER"
                    and asset_by_id.get(asset_id, {}).get("subject_age_class")
                    not in {"MINOR", "ADULT"}
                }
                if unknown_age_characters:
                    errors.append(
                        f"E_MINOR_AGE_UNKNOWN_COMPILED {prompt_id}: executable Prompt cannot treat "
                        f"unknown-age characters as adults {sorted(unknown_age_characters)}"
                    )
            else:
                errors.append(
                    f"E_PROVIDER_PROMPT_UNBOUND {prompt_id}: prompt_layer must be PROVIDER_COMPILED"
                )
            prompt_reference_ids = set(map(str, as_list(prompt.get("reference_ids"))))
            unknown_reference_ids = prompt_reference_ids - set(reference_by_id)
            if unknown_reference_ids:
                errors.append(
                    f"E_REFERENCE_UNKNOWN {prompt_id}: unknown reference IDs {sorted(unknown_reference_ids)}"
                )
            for reference_id in prompt_reference_ids - unknown_reference_ids:
                reference = reference_by_id[reference_id]
                asset = asset_by_id.get(str(reference.get("asset_id")))
                if (
                    not asset
                    or str(reference.get("version")) != str(asset.get("version"))
                    or str(reference.get("asset_id")) not in set(map(str, as_list(prompt.get("asset_ids"))))
                ):
                    errors.append(
                        f"E_REFERENCE_UNKNOWN {prompt_id}: reference {reference_id} is not bound to a "
                        "matching versioned prompt asset"
                    )
                if set(map(str, as_list(reference.get("controls")))) & set(
                    map(str, as_list(reference.get("must_not_control")))
                ):
                    errors.append(
                        f"E_REFERENCE_UNKNOWN {reference_id}: controls and must_not_control must be disjoint"
                    )
        missing_unknowns = set(map(str, as_list(prompt.get("protected_unknown_ids")))) - set(unknown_by_id)
        missing_quantities = set(map(str, as_list(prompt.get("quantity_ids")))) - set(quantity_by_id)
        missing_boundaries = set(map(str, as_list(prompt.get("causal_boundary_ids")))) - set(boundary_by_id)
        if missing_unknowns:
            errors.append(f"{prompt_id}: references unknown protected_unknown_ids {sorted(missing_unknowns)}")
        if missing_quantities:
            errors.append(f"{prompt_id}: references unknown quantity_ids {sorted(missing_quantities)}")
        if missing_boundaries:
            errors.append(f"{prompt_id}: references unknown causal_boundary_ids {sorted(missing_boundaries)}")
        for asset_id in map(str, as_list(prompt.get("asset_ids"))):
            if asset_by_id.get(asset_id, {}).get("benchmark_case_id") is not None:
                errors.append(f"{prompt_id}: production prompt cannot reference BENCHMARK_ONLY asset {asset_id}")
        if shot_id is not None:
            for plan in shot_plans:
                if isinstance(plan, dict) and str(prompt.get("source_spec_version")) != str(plan.get("source_spec_version")):
                    if str(shot_id) in {
                        str(shot.get("shot_id")) for shot in as_list(plan.get("shots")) if isinstance(shot, dict)
                    }:
                        errors.append(f"{prompt_id}: source spec version does not match shot plan")

    prompt_covered_shots = {
        str(prompt.get("target_id")) if current_quality_contract else str(prompt.get("shot_id"))
        for prompt in provider_prompts
        if isinstance(prompt, dict)
        and (
            prompt.get("target_type") == "SHOT" if current_quality_contract
            else prompt.get("shot_id") is not None
        )
    }
    if not alpha7 and prompt_covered_shots != generation_shot_ids:
        errors.append(
            "prompt coverage: planned generation shot IDs must exactly equal covered shot IDs; "
            f"missing={sorted(generation_shot_ids - prompt_covered_shots)}, "
            f"extra={sorted(prompt_covered_shots - generation_shot_ids)}"
        )
    if alpha7:
        master_covered_shots = {
            str(master.get("target_id")) if current_quality_contract else str(master.get("shot_id"))
            for master in master_prompts
            if isinstance(master, dict)
            and (
                master.get("target_type") == "SHOT" if current_quality_contract
                else master.get("shot_id") is not None
            )
        }
        master_coverage_required = (
            bool(
                provider_prompts or provider_neutral_drafts or transform_plans
                or neutral_execution_prompts
            )
            or any(
                isinstance(completion, dict)
                and completion.get("scope_type") == "MASTER_PROMPT_PACKAGE"
                for completion in spec_completion_records
            )
            or any(
                isinstance(gate, dict)
                and gate.get("gate_type") == "GENERATION_READINESS_GATE"
                for gate in gates
            )
        )
        missing_master_coverage = (
            generation_shot_ids - master_covered_shots if master_coverage_required else set()
        )
        if missing_master_coverage and not current_quality_contract:
            errors.append(
                "E_PROMPT_BACKLINK_MISMATCH required MASTER coverage is incomplete; "
                f"missing={sorted(missing_master_coverage)}"
            )
        draft_covered_shots = {
            str(draft.get("target_id")) if current_quality_contract else str(draft.get("shot_id"))
            for draft in provider_neutral_drafts
            if isinstance(draft, dict)
            and (
                draft.get("target_type") == "SHOT" if current_quality_contract
                else draft.get("shot_id") is not None
            )
        }
        draft_coverage_required = bool(provider_prompts) or any(
            isinstance(completion, dict)
            and completion.get("scope_type") == "PROVIDER_NEUTRAL_DRAFT_PROMPT_PACKAGE"
            for completion in spec_completion_records
        )
        if draft_coverage_required and generation_shot_ids - draft_covered_shots and not current_quality_contract:
            errors.append(
                "E_PROMPT_BACKLINK_MISMATCH required neutral DRAFT coverage is incomplete; "
                f"missing={sorted(generation_shot_ids - draft_covered_shots)}"
            )
        transform_plan_covered_shots = {
            str(plan.get("target_id"))
            for plan in transform_plans
            if isinstance(plan, dict) and plan.get("target_type") == "SHOT"
        }
        neutral_execution_covered_shots = {
            str(prompt.get("target_id"))
            for prompt in neutral_execution_prompts
            if isinstance(prompt, dict) and prompt.get("target_type") == "SHOT"
        }
        if four_layer_prompt_contract:
            if provider_prompts and generation_shot_ids - transform_plan_covered_shots:
                errors.append(
                    "E_PROMPT_BACKLINK_MISMATCH required TRANSFORM_PLAN coverage is incomplete; "
                    f"missing={sorted(generation_shot_ids - transform_plan_covered_shots)}"
                )
            if provider_prompts and generation_shot_ids - neutral_execution_covered_shots:
                errors.append(
                    "E_PROMPT_BACKLINK_MISMATCH required NEUTRAL_EXECUTION_PROMPT coverage is incomplete; "
                    f"missing={sorted(generation_shot_ids - neutral_execution_covered_shots)}"
                )
        for shot_id in generation_shot_ids:
            actual_master_ids = {
                str(master.get("id"))
                for master in master_prompts
                if isinstance(master, dict) and (
                    str(master.get("target_id")) == shot_id and master.get("target_type") == "SHOT"
                    if current_quality_contract else str(master.get("shot_id")) == shot_id
                )
            }
            if shot_to_masters.get(shot_id, set()) != actual_master_ids:
                errors.append(
                    f"E_PROMPT_BACKLINK_MISMATCH {shot_id}: shot master_prompt_ids must exactly equal "
                    f"MASTER backlinks; declared={sorted(shot_to_masters.get(shot_id, set()))}, "
                    f"actual={sorted(actual_master_ids)}"
                )
            actual_draft_ids = {
                str(draft.get("id"))
                for draft in provider_neutral_drafts
                if isinstance(draft, dict) and (
                    str(draft.get("target_id")) == shot_id and draft.get("target_type") == "SHOT"
                    if current_quality_contract else str(draft.get("shot_id")) == shot_id
                )
            }
            if shot_to_drafts.get(shot_id, set()) != actual_draft_ids:
                errors.append(
                    f"E_PROMPT_BACKLINK_MISMATCH {shot_id}: shot provider_neutral_draft_ids must "
                    f"exactly equal DRAFT backlinks; declared={sorted(shot_to_drafts.get(shot_id, set()))}, "
                    f"actual={sorted(actual_draft_ids)}"
                )
            actual_transform_plan_ids = {
                str(plan.get("id"))
                for plan in transform_plans
                if isinstance(plan, dict)
                and plan.get("target_type") == "SHOT"
                and str(plan.get("target_id")) == shot_id
            }
            actual_neutral_execution_prompt_ids = {
                str(prompt.get("id"))
                for prompt in neutral_execution_prompts
                if isinstance(prompt, dict)
                and prompt.get("target_type") == "SHOT"
                and str(prompt.get("target_id")) == shot_id
            }
            if (
                four_layer_prompt_contract
                and shot_to_transform_plans.get(shot_id, set())
                != actual_transform_plan_ids
            ):
                errors.append(
                    f"E_PROMPT_BACKLINK_MISMATCH {shot_id}: shot transform_plan_ids must "
                    f"exactly equal TRANSFORM_PLAN backlinks; "
                    f"declared={sorted(shot_to_transform_plans.get(shot_id, set()))}, "
                    f"actual={sorted(actual_transform_plan_ids)}"
                )
            if (
                four_layer_prompt_contract
                and shot_to_neutral_execution_prompts.get(shot_id, set())
                != actual_neutral_execution_prompt_ids
            ):
                errors.append(
                    f"E_PROMPT_BACKLINK_MISMATCH {shot_id}: shot "
                    "neutral_execution_prompt_ids must exactly equal "
                    f"NEUTRAL_EXECUTION_PROMPT backlinks; declared="
                    f"{sorted(shot_to_neutral_execution_prompts.get(shot_id, set()))}, "
                    f"actual={sorted(actual_neutral_execution_prompt_ids)}"
                )
            actual_prompt_ids = {
                str(prompt.get("id"))
                for prompt in provider_prompts
                if isinstance(prompt, dict) and (
                    str(prompt.get("target_id")) == shot_id and prompt.get("target_type") == "SHOT"
                    if current_quality_contract else str(prompt.get("shot_id")) == shot_id
                )
            }
            if shot_to_prompts.get(shot_id, set()) != actual_prompt_ids:
                errors.append(
                    f"E_PROMPT_BACKLINK_MISMATCH {shot_id}: shot provider_prompt_ids must exactly equal "
                    f"prompt backlinks; declared={sorted(shot_to_prompts.get(shot_id, set()))}, "
                    f"actual={sorted(actual_prompt_ids)}"
                )
        used_reference_ids = {
            str(reference_id)
            for prompt in (
                provider_prompts + provider_neutral_drafts + master_prompts
                + transform_plans + neutral_execution_prompts
            )
            if isinstance(prompt, dict)
            for reference_id in as_list(prompt.get("reference_ids"))
        }
        if used_reference_ids != set(reference_by_id):
            errors.append(
                "E_REFERENCE_UNKNOWN reference_registry: registered reference IDs must exactly match "
                f"prompt use; unused={sorted(set(reference_by_id) - used_reference_ids)}, "
                f"missing={sorted(used_reference_ids - set(reference_by_id))}"
            )

    quality_for_prompt_id: dict[str, dict[str, Any]] = {}
    quality_pass_prompt_ids: set[str] = set()
    review_pass_prompt_ids: set[str] = set()
    review_scope_by_prompt_id: dict[str, str] = {}
    if current_quality_contract:
        quality_by_target: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        prompt_targets: set[tuple[str, str, str, str]] = set()
        for prompt_record in (
            master_prompts + provider_neutral_drafts + transform_plans
            + neutral_execution_prompts + provider_prompts
        ):
            if isinstance(prompt_record, dict):
                prompt_targets.add(prompt_target_key(prompt_record))

        global_beat_ids: set[str] = set()
        global_atom_ids: set[str] = set()
        global_section_ids: set[str] = set()
        global_prompt_review_ids: set[str] = set()
        for quality in prompt_quality_records:
            if not isinstance(quality, dict):
                errors.append("prompt quality record must be an object")
                continue
            record_error_start = len(errors)
            quality_id = str(quality.get("id", "<prompt-quality>"))
            target_key = (
                str(quality.get("target_type", "")),
                str(quality.get("target_id", "")),
                str(quality.get("source_spec_version", "")),
                str(quality.get("generation_role", "")),
            )
            lifecycle_status = quality.get("lifecycle_status")
            if lifecycle_status != "CURRENT":
                errors.append(
                    f"E_PROMPT_QUALITY_NOT_READY {quality_id}: active state keeps only CURRENT quality; "
                    "archive stale/deprecated records as versioned audit artifacts"
                )
                continue
            if target_key in quality_by_target:
                errors.append(
                    f"E_PROMPT_QUALITY_MISSING {quality_id}: target/spec/role {target_key} has more than one CURRENT quality record"
                )
            else:
                quality_by_target[target_key] = quality

            target_type, target_id, source_spec_version, generation_role = target_key
            medium = str(quality.get("generation_medium", ""))
            if not generation_role_matches_medium(generation_role, medium):
                errors.append(
                    f"E_PROMPT_MEDIUM_MISMATCH {quality_id}: generation role/medium conflict"
                )
            shot = shot_by_id.get(target_id) if target_type == "SHOT" else None
            target_asset = asset_by_id.get(target_id) if target_type == "ASSET" else None
            if target_type == "SHOT":
                if (
                    not shot or target_id not in generation_shot_ids
                    or generation_role in {"ASSET_REFERENCE", "ASSET_MOTION_REFERENCE"}
                ):
                    errors.append(
                        f"E_PROMPT_QUALITY_MISSING {quality_id}: SHOT quality must bind a generation shot and shot role"
                    )
            elif target_type == "ASSET":
                if not target_asset or generation_role not in {
                    "ASSET_REFERENCE", "ASSET_MOTION_REFERENCE", "CUSTOM",
                }:
                    errors.append(
                        f"E_PROMPT_QUALITY_MISSING {quality_id}: ASSET quality must bind a real asset and asset role"
                    )
            else:
                errors.append(f"E_PROMPT_QUALITY_MISSING {quality_id}: target_type must be ASSET or SHOT")
            plan = shot_plan_by_id.get(shot_plan_for_shot.get(target_id, ""), {}) if shot else {}
            expected_source_version = (
                str(plan.get("source_spec_version", ""))
                if shot else str((target_asset or {}).get("source_spec_version", ""))
            )
            if expected_source_version != source_spec_version:
                errors.append(
                    f"E_PROMPT_QUALITY_MISSING {quality_id}: source_spec_version does not match target"
                )

            master_id = quality.get("master_prompt_id")
            draft_id = quality.get("provider_neutral_draft_id")
            transform_plan_id = quality.get("transform_plan_id")
            neutral_execution_prompt_id = quality.get("neutral_execution_prompt_id")
            quality_evaluation_scope = quality.get("quality_evaluation_scope")
            compiled_ids = set(map(str, as_list(quality.get("provider_prompt_ids"))))
            master = master_prompt_by_id.get(str(master_id)) if master_id is not None else None
            draft = neutral_draft_by_id.get(str(draft_id)) if draft_id is not None else None
            transform_plan = transform_plan_by_id.get(
                str(transform_plan_id)
            ) if transform_plan_id is not None else None
            neutral_execution_prompt = neutral_execution_prompt_by_id.get(
                str(neutral_execution_prompt_id)
            ) if neutral_execution_prompt_id is not None else None
            actual_compiled_ids = {
                prompt_id
                for prompt_id, prompt in prompt_by_id.items()
                if prompt_target_key(prompt) == target_key
            }
            actual_master_ids = {
                prompt_id
                for prompt_id, prompt in master_prompt_by_id.items()
                if prompt_target_key(prompt) == target_key
            }
            actual_draft_ids = {
                prompt_id
                for prompt_id, prompt in neutral_draft_by_id.items()
                if prompt_target_key(prompt) == target_key
            }
            actual_transform_plan_ids = {
                prompt_id
                for prompt_id, prompt in transform_plan_by_id.items()
                if prompt_target_key(prompt) == target_key
            }
            actual_neutral_execution_prompt_ids = {
                prompt_id
                for prompt_id, prompt in neutral_execution_prompt_by_id.items()
                if prompt_target_key(prompt) == target_key
            }
            if actual_master_ids and ({str(master_id)} if master_id is not None else set()) != actual_master_ids:
                errors.append(
                    f"E_PROMPT_QUALITY_MISSING {quality_id}: master_prompt_id must exactly bind this shot/spec"
                )
            if (
                not four_layer_prompt_contract and actual_draft_ids
                and ({str(draft_id)} if draft_id is not None else set()) != actual_draft_ids
            ):
                errors.append(
                    f"E_PROMPT_QUALITY_MISSING {quality_id}: provider_neutral_draft_id must exactly bind this shot/spec"
                )
            if four_layer_prompt_contract:
                if draft_id is not None:
                    errors.append(
                        f"E_LEGACY_PROMPT_LAYER_READ_ONLY {quality_id}: current quality cannot bind legacy DRAFT"
                    )
                if ({str(transform_plan_id)} if transform_plan_id is not None else set()) != actual_transform_plan_ids:
                    errors.append(
                        f"E_PROMPT_QUALITY_MISSING {quality_id}: transform_plan_id must exactly bind this shot/spec"
                    )
                if ({str(neutral_execution_prompt_id)} if neutral_execution_prompt_id is not None else set()) != actual_neutral_execution_prompt_ids:
                    errors.append(
                        f"E_PROMPT_QUALITY_MISSING {quality_id}: neutral_execution_prompt_id must exactly bind this shot/spec"
                    )
                if quality_evaluation_scope not in {
                    "NEUTRAL_EXECUTION", "PROVIDER_COMPILED",
                }:
                    errors.append(
                        f"E_PROMPT_QUALITY_MISSING {quality_id}: current quality requires quality_evaluation_scope"
                    )
            if (
                quality_evaluation_scope == "PROVIDER_COMPILED"
                or not four_layer_prompt_contract
            ) and compiled_ids != actual_compiled_ids:
                errors.append(
                    f"E_PROMPT_QUALITY_MISSING {quality_id}: provider_prompt_ids must exactly bind this shot/spec"
                )
            if (
                four_layer_prompt_contract
                and quality_evaluation_scope == "NEUTRAL_EXECUTION"
                and (compiled_ids or actual_compiled_ids)
            ):
                errors.append(
                    f"E_PROMPT_QUALITY_MISSING {quality_id}: neutral quality is valid only before provider compilation"
                )
            if master and (
                prompt_target_key(master) != target_key
                or str(master.get("generation_medium")) != medium
            ):
                errors.append(f"E_PROMPT_QUALITY_MISSING {quality_id}: MASTER scope mismatch")
            if draft and (
                prompt_target_key(draft) != target_key
                or str(draft.get("generation_medium")) != medium
                or str(draft.get("master_prompt_id")) != str(master_id)
            ):
                errors.append(f"E_PROMPT_QUALITY_MISSING {quality_id}: DRAFT scope mismatch")
            if transform_plan and (
                prompt_target_key(transform_plan) != target_key
                or str(transform_plan.get("generation_medium")) != medium
                or str(transform_plan.get("master_prompt_id")) != str(master_id)
            ):
                errors.append(f"E_PROMPT_QUALITY_MISSING {quality_id}: TRANSFORM_PLAN scope mismatch")
            if neutral_execution_prompt and (
                prompt_target_key(neutral_execution_prompt) != target_key
                or str(neutral_execution_prompt.get("generation_medium")) != medium
                or str(neutral_execution_prompt.get("master_prompt_id")) != str(master_id)
                or str(neutral_execution_prompt.get("transform_plan_id"))
                != str(transform_plan_id)
            ):
                errors.append(
                    f"E_PROMPT_QUALITY_MISSING {quality_id}: NEUTRAL_EXECUTION_PROMPT scope mismatch"
                )
            for prompt_id in compiled_ids:
                prompt = prompt_by_id.get(prompt_id)
                if not prompt or (
                    prompt_target_key(prompt) != target_key
                    or str(prompt.get("generation_medium")) != medium
                    or str(prompt.get("master_prompt_id")) != str(master_id)
                    or (
                        str(prompt.get("transform_plan_id")) != str(transform_plan_id)
                        or str(prompt.get("neutral_execution_prompt_id"))
                        != str(neutral_execution_prompt_id)
                        if four_layer_prompt_contract
                        else str(prompt.get("provider_neutral_draft_id")) != str(draft_id)
                    )
                ):
                    errors.append(
                        f"E_PROMPT_QUALITY_MISSING {quality_id}: compiled Prompt {prompt_id} scope mismatch"
                    )
                elif prompt_id in quality_for_prompt_id:
                    errors.append(
                        f"E_PROMPT_QUALITY_MISSING {quality_id}: compiled Prompt {prompt_id} has multiple quality records"
                    )
                else:
                    quality_for_prompt_id[prompt_id] = quality

            expected_prompt_soul_version = (
                "ALPHA7-PQS-2" if four_layer_prompt_contract else "ALPHA7-PQS-1"
            )
            if quality.get("prompt_soul_version") != expected_prompt_soul_version:
                errors.append(
                    f"PQ_BEAT_CONTRACT_THIN {quality_id}: unsupported prompt_soul_version"
                )
            soul_artifact_ids = as_list(quality.get("prompt_soul_artifact_ids"))
            expected_soul_sha = prompt_soul_digest(soul_artifact_ids, artifact_by_id)
            if expected_soul_sha is None:
                errors.append(
                    f"PQ_BEAT_CONTRACT_THIN {quality_id}: prompt soul needs at least one resolved TEXT_SPEC artifact"
                )
            elif str(quality.get("prompt_soul_sha256", "")).lower() != expected_soul_sha:
                errors.append(
                    f"PQ_BEAT_CONTRACT_THIN {quality_id}: prompt_soul_sha256 is stale or fabricated"
                )
            profile = str(quality.get("prompt_quality_profile", ""))
            if profile not in PROMPT_PROFILE_BASE_DIMENSIONS:
                errors.append(f"PQ_BEAT_CONTRACT_THIN {quality_id}: unknown quality profile")
            route_types = set(map(str, as_list(project_route.get("project_types")))) if isinstance(
                project_route, dict
            ) else set()
            truth_mode = str(project_route.get("content_truth_mode", "")) if isinstance(
                project_route, dict
            ) else ""
            nonfiction_routes = {
                "SCIENCE_RESEARCH_EXPLAINER", "EDUCATION_PUBLIC_INTEREST",
                "CULTURE_HERITAGE", "DOCUMENTARY_NONFICTION",
            }
            nonfiction_required = bool(
                route_types & nonfiction_routes or truth_mode in {"NONFICTION", "MIXED"}
            )
            brand_required = "BRAND_PRODUCT" in route_types
            expected_route_profile = (
                "BRAND_NONFICTION" if nonfiction_required and brand_required
                else "NONFICTION_VISUAL" if nonfiction_required
                else "BRAND_PROMO" if brand_required
                else None
            )
            if expected_route_profile is not None and profile != expected_route_profile:
                errors.append(
                    f"PQ_BOUNDARY_VIOLATION {quality_id}: route requires {expected_route_profile}"
                )
            sequence_mode = str(quality.get("sequence_mode", ""))

            capsules = [
                item for item in as_list(quality.get("active_asset_capsule"))
                if isinstance(item, dict)
            ]
            capsule_asset_ids = {str(item.get("asset_id")) for item in capsules}
            expected_asset_ids = (
                set(map(str, as_list((shot or {}).get("asset_ids"))))
                if target_type == "SHOT" else {target_id}
            )
            if capsule_asset_ids != expected_asset_ids or len(capsules) != len(capsule_asset_ids):
                errors.append(
                    f"PQ_ASSET_OR_REFERENCE_DRIFT {quality_id}: active asset capsule must exactly cover shot assets"
                )
            capsule_reference_ids: set[str] = set()
            for capsule in capsules:
                asset_id = str(capsule.get("asset_id"))
                asset = asset_by_id.get(asset_id)
                if not asset or str(capsule.get("asset_version")) != str(asset.get("version")):
                    errors.append(
                        f"PQ_ASSET_OR_REFERENCE_DRIFT {quality_id}: stale asset capsule {asset_id}"
                    )
                reference_ids = set(map(str, as_list(capsule.get("reference_ids"))))
                capsule_reference_ids |= reference_ids
                for reference_id in reference_ids:
                    if str(reference_by_id.get(reference_id, {}).get("asset_id")) != asset_id:
                        errors.append(
                            f"PQ_ASSET_OR_REFERENCE_DRIFT {quality_id}: reference {reference_id} does not belong to {asset_id}"
                        )
                facts = as_list(capsule.get("generation_essential_facts"))
                if not facts or any(not substantive_prompt_text(item) for item in facts):
                    errors.append(
                        f"PQ_ASSET_OR_REFERENCE_DRIFT {quality_id}: asset {asset_id} lacks substantive generation facts"
                    )
            expected_reference_ids = set(map(str, as_list(master.get("reference_ids")))) if master else set()
            if capsule_reference_ids != expected_reference_ids:
                errors.append(
                    f"PQ_ASSET_OR_REFERENCE_DRIFT {quality_id}: asset capsule reference coverage drifted"
                )
            reference_delta = quality.get("reference_delta")
            delta_mapping_prompt_ids = {
                str(adapter.get("provider_prompt_id", ""))
                for adapter in as_list(quality.get("adapter_integrity"))
                if isinstance(adapter, dict)
                and any(
                    isinstance(operation, dict)
                    and operation.get("kind") == "REFERENCE_DELTA_MAPPING"
                    for operation in as_list(adapter.get("adapter_operations"))
                )
            }
            reference_delta_element_ids: set[str] = set()
            reference_source_element_ids: set[str] = set()
            if reference_delta is None:
                if delta_mapping_prompt_ids or (
                    expected_reference_ids
                    and generation_role in {"SHOT_COMPOSITE_LAYER", "CUSTOM"}
                ):
                    errors.append(
                        f"PQ_REFERENCE_DELTA_INVALID {quality_id}: reference edit/derived role or "
                        "adapter mapping lacks a reference_delta contract"
                    )
            elif not isinstance(reference_delta, dict):
                errors.append(
                    f"PQ_REFERENCE_DELTA_INVALID {quality_id}: reference_delta must be null or an object"
                )
            else:
                source_reference_ids = set(map(str, as_list(
                    reference_delta.get("source_reference_ids")
                )))
                preserve_element_ids = set(map(str, as_list(
                    reference_delta.get("preserve_element_ids")
                )))
                change_element_ids = set(map(str, as_list(
                    reference_delta.get("change_element_ids")
                )))
                add_element_ids = set(map(str, as_list(
                    reference_delta.get("add_element_ids")
                )))
                output_element_ids = set(map(str, as_list(
                    reference_delta.get("output_element_ids")
                )))
                reference_delta_element_ids = (
                    preserve_element_ids | change_element_ids | add_element_ids
                    | output_element_ids
                )
                if (
                    not source_reference_ids
                    or source_reference_ids - expected_reference_ids
                    or delta_mapping_prompt_ids != compiled_ids
                ):
                    errors.append(
                        f"PQ_REFERENCE_DELTA_INVALID {quality_id}: reference edit/derivation must "
                        "bind registered source references and one REFERENCE_DELTA_MAPPING per PP"
                    )
                for reference_id in source_reference_ids:
                    reference = reference_by_id.get(reference_id, {})
                    reference_source_element_ids |= {
                        str(item) for item in as_list(reference.get("controls"))
                        if isinstance(item, str) and item.strip()
                    }
                    source_asset = asset_by_id.get(str(reference.get("asset_id", "")), {})
                    for field in ("locked_features", "variable_features"):
                        reference_source_element_ids |= {
                            str(item) for item in as_list(source_asset.get(field))
                            if isinstance(item, str) and item.strip()
                        }
                if (
                    preserve_element_ids - reference_source_element_ids
                    or change_element_ids - reference_source_element_ids
                ):
                    errors.append(
                        f"PQ_REFERENCE_DELTA_INVALID {quality_id}: preserved/changed elements must "
                        "resolve from the cited reference or upstream asset state"
                    )
                if (
                    preserve_element_ids & change_element_ids
                    or preserve_element_ids & add_element_ids
                    or change_element_ids & add_element_ids
                    or add_element_ids & reference_source_element_ids
                ):
                    errors.append(
                        f"PQ_REFERENCE_DELTA_INVALID {quality_id}: preserve, change, and add sets "
                        "must be mutually consistent"
                    )
                if output_element_ids != (
                    preserve_element_ids | change_element_ids | add_element_ids
                ):
                    errors.append(
                        f"PQ_REFERENCE_DELTA_INVALID {quality_id}: output elements must exactly equal "
                        "the declared preserve/change/add result"
                    )
                if reference_delta.get("allow_new_elements") is not True and (
                    add_element_ids or output_element_ids - reference_source_element_ids
                ):
                    errors.append(
                        f"PQ_REFERENCE_DELTA_INVALID {quality_id}: new output elements are forbidden "
                        "unless allow_new_elements is true"
                    )
            for continuity in as_list(quality.get("continuity_capsule")):
                if not isinstance(continuity, dict) or any(
                    not substantive_prompt_text(continuity.get(field))
                    for field in ("topic", "entry_state", "exit_state")
                ):
                    errors.append(
                        f"PQ_BEAT_CONTRACT_THIN {quality_id}: continuity capsule is empty or generic"
                    )

            duration = quality.get("natural_duration_seconds")
            density = quality.get("density") if isinstance(quality.get("density"), dict) else {}
            exception = density.get("exception")
            valid_exception = (
                isinstance(exception, dict)
                and substantive_prompt_text(exception.get("reason"))
                and exception.get("user_authorized") is True
                and bool(as_list(exception.get("evidence_ids")))
                and not (set(map(str, as_list(exception.get("evidence_ids")))) - set(evidence_by_id))
            )

            beats = [
                item for item in as_list(quality.get("director_beats"))
                if isinstance(item, dict)
            ]
            beat_by_id: dict[str, dict[str, Any]] = {}
            for beat in beats:
                beat_id = str(beat.get("beat_id", ""))
                if not beat_id or beat_id in beat_by_id or beat_id in global_beat_ids:
                    errors.append(
                        f"PQ_BEAT_CONTRACT_THIN {quality_id}: beat_id missing or duplicated {beat_id!r}"
                    )
                beat_by_id[beat_id] = beat
                global_beat_ids.add(beat_id)
            if density.get("planned_beat_count") != len(beats):
                errors.append(
                    f"PQ_DENSITY_MISSING {quality_id}: planned beat count differs from director_beats"
                )
            hero_ids = set(map(str, as_list(density.get("hero_beat_ids"))))
            if hero_ids - set(beat_by_id) or any(
                beat_by_id[beat_id].get("priority") != "HERO" for beat_id in hero_ids & set(beat_by_id)
            ):
                errors.append(
                    f"PQ_BEAT_CONTRACT_THIN {quality_id}: hero_beat_ids must resolve to HERO beats"
                )
            actual_hero_ids = {
                beat_id for beat_id, beat in beat_by_id.items() if beat.get("priority") == "HERO"
            }
            if hero_ids != actual_hero_ids or (beats and not hero_ids):
                errors.append(
                    f"PQ_BEAT_CONTRACT_THIN {quality_id}: HERO beat coverage must be exact and non-empty"
                )

            cursor = 0.0
            previous_exit: str | None = None
            beat_signatures: list[tuple[str, str, str]] = []
            contact_required = False
            lip_sync_required = False
            identity_closeup = False
            if medium == "IMAGE":
                if (
                    sequence_mode != "STATIC_IMAGE" or duration is not None
                    or density.get("band") != "STATIC_IMAGE" or len(beats) != 1
                    or density.get("short_insert_reason") is not None
                ):
                    errors.append(
                        f"PQ_DENSITY_MISSING {quality_id}: IMAGE requires STATIC_IMAGE, null duration, "
                        "STATIC_IMAGE band, and exactly one visual beat"
                    )
                for beat in beats:
                    beat_id = str(beat.get("beat_id", "<beat>"))
                    if str(beat.get("target_id")) != target_id or beat.get("time_range") is not None:
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}: static beat must bind the shot and have null time_range"
                        )
                    if any(
                        beat.get(field) is not None
                        for field in ("entry_state", "dialogue_audio", "exit_state")
                    ) or as_list(beat.get("compiled_anchors")):
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}: static beat cannot fabricate entry/audio/exit "
                            "or compiled motion anchors"
                        )
                    for field in (
                        "camera", "space", "performance", "contact_material_environment_vfx",
                    ):
                        if not substantive_director_source(beat.get(field)):
                            errors.append(
                                f"PQ_BEAT_CONTRACT_THIN {quality_id}: {beat_id}.{field} is too thin for a static frame"
                            )
                    high_risk = beat.get("high_risk_event")
                    if high_risk != "NONE" and beat.get("risk_load") == "LOW":
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}: {beat_id} high-risk event cannot be LOW"
                        )
                    contact_required = high_risk in {
                        "PRECISION_HAND_CONTACT", "MULTI_SUBJECT_CONTACT", "CLOTHING_CHANGE",
                        "MECHANICAL_TRANSFORMATION", "LIQUID_OR_DENSE_VFX",
                    }
                    identity_closeup = high_risk == "IDENTITY_CLOSEUP"
            elif medium == "VIDEO":
                if sequence_mode not in {"EDITED_SEQUENCE", "CONTINUOUS_TAKE", "HYBRID"}:
                    errors.append(f"PQ_DENSITY_MISSING {quality_id}: VIDEO sequence_mode is invalid")
                if (
                    isinstance(duration, bool) or not isinstance(duration, (int, float))
                    or (
                        target_type == "SHOT" and generation_role == "SHOT_MOTION"
                        and abs(float(duration) - float((shot or {}).get("duration_seconds", -1))) > 1e-9
                    )
                ):
                    errors.append(
                        f"PQ_DENSITY_MISSING {quality_id}: VIDEO natural duration must equal shot duration"
                    )
                band, minimum_beats, maximum_beats = prompt_density_anchor(duration)
                if density.get("band") != band:
                    errors.append(
                        f"PQ_DENSITY_MISSING {quality_id}: density band {density.get('band')!r} does not match {band}"
                    )
                if band == "SHORT_INSERT":
                    if not substantive_prompt_text(density.get("short_insert_reason")):
                        errors.append(
                            f"PQ_DENSITY_MISSING {quality_id}: SHORT_INSERT needs a concrete editorial reason"
                        )
                elif density.get("short_insert_reason") is not None:
                    errors.append(
                        f"PQ_DENSITY_MISSING {quality_id}: non-short video cannot carry short_insert_reason"
                    )
                if (
                    isinstance(minimum_beats, int) and isinstance(maximum_beats, int)
                    and not minimum_beats <= len(beats) <= maximum_beats
                    and not valid_exception
                ):
                    errors.append(
                        f"PQ_DENSITY_MISSING {quality_id}: {duration}s needs {minimum_beats}-{maximum_beats} beats"
                    )
                if band == "INVALID" or (
                    band in {"MERGE_REQUIRED", "SPLIT_REQUIRED"}
                    and quality.get("quality_status", {}).get("status") == "PASS"
                ):
                    errors.append(
                        f"PQ_DENSITY_MISSING {quality_id}: duration must be replanned or segmented before PASS"
                    )
                for beat in beats:
                    beat_id = str(beat.get("beat_id", "<beat>"))
                    if str(beat.get("target_id")) != target_id:
                        errors.append(f"PQ_BEAT_CONTRACT_THIN {quality_id}: {beat_id} points to another target")
                    time_range = beat.get("time_range") if isinstance(beat.get("time_range"), dict) else {}
                    start = time_range.get("start_seconds")
                    end = time_range.get("end_seconds")
                    if (
                        isinstance(start, bool) or not isinstance(start, (int, float))
                        or isinstance(end, bool) or not isinstance(end, (int, float))
                        or abs(float(start) - cursor) > 0.001 or float(end) <= float(start)
                        or (isinstance(duration, (int, float)) and float(end) > float(duration) + 0.001)
                    ):
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}: {beat_id} has a gap, overlap, or invalid range"
                        )
                    if isinstance(end, (int, float)) and not isinstance(end, bool):
                        cursor = float(end)
                    for field in (
                        "entry_state", "camera", "space", "action_physics", "performance",
                        "contact_material_environment_vfx", "dialogue_audio", "exit_state",
                    ):
                        field_value_ok = (
                            substantive_prompt_text(beat.get(field))
                            if field == "dialogue_audio"
                            else substantive_director_source(beat.get(field))
                        )
                        if not field_value_ok:
                            errors.append(
                                f"PQ_BEAT_CONTRACT_THIN {quality_id}: {beat_id}.{field} is too thin to direct"
                            )
                    entry = normalized_prompt_text(beat.get("entry_state"))
                    exit_state = normalized_prompt_text(beat.get("exit_state"))
                    if previous_exit is not None and entry != previous_exit:
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}: {beat_id} does not inherit prior exit state"
                        )
                    previous_exit = exit_state
                    beat_signatures.append(
                        (
                            director_signature_text(beat.get("camera")),
                            director_signature_text(beat.get("action_physics")),
                            director_signature_text(beat.get("exit_state")),
                        )
                    )
                    high_risk = beat.get("high_risk_event")
                    if high_risk != "NONE" and beat.get("risk_load") == "LOW":
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}: {beat_id} high-risk event cannot be LOW"
                        )
                    contact_required = contact_required or high_risk in {
                        "PRECISION_HAND_CONTACT", "MULTI_SUBJECT_CONTACT", "CLOTHING_CHANGE",
                        "MECHANICAL_TRANSFORMATION", "LIQUID_OR_DENSE_VFX",
                    }
                    lip_sync_required = lip_sync_required or high_risk == "VISIBLE_LIP_SYNC"
                    identity_closeup = identity_closeup or high_risk == "IDENTITY_CLOSEUP"
                if isinstance(duration, (int, float)) and abs(cursor - float(duration)) > 0.001:
                    errors.append(
                        f"PQ_BEAT_CONTRACT_THIN {quality_id}: director timeline does not end at natural duration"
                    )
                if len(beat_signatures) >= 3 and len(set(beat_signatures)) < math.ceil(
                    len(beat_signatures) / 2
                ):
                    errors.append(
                        f"PQ_BEAT_CONTRACT_THIN {quality_id}: repeated camera/action/exit templates pad beat count"
                    )
            else:
                errors.append(f"PQ_DENSITY_MISSING {quality_id}: generation_medium must be IMAGE or VIDEO")

            atoms = [
                item for item in as_list(quality.get("semantic_atoms"))
                if isinstance(item, dict)
            ]
            authoritative_source_refs = (
                set(decision_by_id) | set(approval_by_id) | set(evidence_by_id)
                | set(artifact_by_id) | set(asset_by_id) | set(reference_by_id)
                | set(shot_by_id) | set(shot_plan_by_id) | set(dialogue_by_id)
                | set(unknown_by_id) | set(quantity_by_id) | set(boundary_by_id)
                | set(baseline_by_id) | set(format_by_id) | SYSTEM_INVARIANT_REGISTRY
                | reference_source_element_ids | reference_delta_element_ids
            )
            longform_bindings = [
                row for row in as_list(quality.get("longform_source_bindings"))
                if isinstance(row, dict)
            ]
            binding_by_source: dict[str, dict[str, Any]] = {}
            for binding in longform_bindings:
                source_atom_id = str(binding.get("source_atom_id", ""))
                if not source_atom_id or source_atom_id in binding_by_source:
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}: longform source bindings must be unique"
                    )
                    continue
                binding_by_source[source_atom_id] = binding
                artifact = artifact_by_id.get(str(binding.get("registry_artifact_id", "")))
                locator = artifact.get("content_locator") if isinstance(artifact, dict) else None
                source_atom_ids = as_list((artifact or {}).get("source_atom_ids"))
                expected_inventory_sha = source_atom_inventory_digest(source_atom_ids)
                artifact_type = re.sub(
                    r"[-\s]+", "_", str((artifact or {}).get("type", "")).strip().lower()
                )
                if (
                    not artifact
                    or artifact_type not in LONGFORM_SOURCE_REGISTRY_TYPES
                    or artifact.get("artifact_class") not in {"TEXT_SPEC", "DATA"}
                    or artifact.get("status") not in PROMPT_SOUL_ARTIFACT_STATUSES
                    or str(artifact.get("version", ""))
                    != str(binding.get("registry_artifact_version", ""))
                    or not isinstance(locator, dict)
                    or str(locator.get("sha256", "")).lower()
                    != str(binding.get("registry_artifact_sha256", "")).lower()
                    or source_atom_id not in set(map(str, source_atom_ids))
                    or expected_inventory_sha is None
                    or str((artifact or {}).get("source_atom_inventory_sha256", "")).lower()
                    != expected_inventory_sha
                ):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}: {source_atom_id} has no current hashed "
                        "Longform source/trace registry"
                    )
            atom_by_id: dict[str, dict[str, Any]] = {}
            referenced_longform_sources: set[str] = set()
            for atom in atoms:
                atom_id = str(atom.get("atom_id", ""))
                if not atom_id or atom_id in atom_by_id or atom_id in global_atom_ids:
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}: atom_id missing or duplicated {atom_id!r}"
                    )
                atom_by_id[atom_id] = atom
                global_atom_ids.add(atom_id)
                if not substantive_prompt_text(atom.get("canonical_claim")):
                    errors.append(
                        f"PQ_TRIVIAL_OR_SUMMARY_ONLY {quality_id}: atom {atom_id} has no substantive claim"
                    )
                source_refs = set(map(str, as_list(atom.get("source_or_state_refs"))))
                referenced_longform_sources |= {
                    source_ref for source_ref in source_refs
                    if re.fullmatch(r"SRC\d{4,}", source_ref) is not None
                }
                unresolved_source_refs = {
                    source_ref for source_ref in source_refs
                    if source_ref not in authoritative_source_refs
                    and source_ref not in binding_by_source
                }
                if atom.get("priority") == "MUST" and not source_refs:
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}: MUST atom {atom_id} lacks source/state refs"
                    )
                if unresolved_source_refs:
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}: atom {atom_id} has unresolved source/state refs "
                        f"{sorted(unresolved_source_refs)}"
                    )
                if atom.get("priority") == "MUST" and not substantive_prompt_text(
                    atom.get("master_anchor")
                ):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}: MUST atom {atom_id} lacks a MASTER anchor"
                    )
                compiled_anchors = [
                    row for row in as_list(atom.get("compiled_anchors")) if isinstance(row, dict)
                ]
                compiled_anchor_ids = [str(row.get("provider_prompt_id")) for row in compiled_anchors]
                if set(compiled_anchor_ids) != compiled_ids or len(compiled_anchor_ids) != len(
                    set(compiled_anchor_ids)
                ):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}: atom {atom_id} needs one compiled anchor per provider Prompt"
                    )
                if atom.get("priority") == "MUST" and any(
                    not substantive_prompt_text(row.get("output_anchor")) for row in compiled_anchors
                ):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}: MUST atom {atom_id} has an empty compiled anchor"
                    )
            if referenced_longform_sources != set(binding_by_source):
                errors.append(
                    f"PQ_ADAPTER_LOSS {quality_id}: Longform bindings must exactly cover referenced source atoms"
                )
            if isinstance(reference_delta, dict):
                delta_atom_refs = set().union(
                    *(
                        set(map(str, as_list(atom.get("source_or_state_refs"))))
                        for atom in atoms
                        if atom.get("priority") == "MUST"
                        and atom.get("dimension") in {"ASSET_STATE", "REFERENCE_RESPONSIBILITY"}
                    ),
                    set(),
                )
                if reference_delta_element_ids - delta_atom_refs:
                    errors.append(
                        f"PQ_REFERENCE_DELTA_INVALID {quality_id}: every reference delta element must "
                        "be bound by a MUST ASSET_STATE/REFERENCE_RESPONSIBILITY atom"
                    )

            primary_source_ids = set(map(str, as_list(
                project_route.get("primary_source_artifact_ids")
                if isinstance(project_route, dict) else []
            )))
            verified_fact_evidence_ids = {
                evidence_id for evidence_id, evidence_row in evidence_by_id.items()
                if evidence_row.get("status") in {"EFFECTIVE", "PLATFORM_SPECIFIC"}
                and evidence_row.get("classification") in VERIFIED_FACT_EVIDENCE_CLASSES
                and (not isinstance(evidence_row.get("freshness"), dict)
                     or evidence_row.get("freshness", {}).get("status") == "CURRENT")
            }
            approved_claim_ids = {
                decision_id for decision_id, decision in decision_by_id.items()
                if decision.get("status") in APPROVED_DECISION_STATUSES
            }
            boundary_source_ids = primary_source_ids | verified_fact_evidence_ids
            if profile in {"NONFICTION_VISUAL", "BRAND_NONFICTION"}:
                for atom in atoms:
                    if atom.get("priority") == "MUST" and atom.get("dimension") == "PROTECTED_BOUNDARY":
                        if not set(map(str, as_list(atom.get("source_or_state_refs")))) & boundary_source_ids:
                            errors.append(
                                f"PQ_BOUNDARY_VIOLATION {quality_id}: factual boundary MUST atom must cite "
                                "a primary source artifact or current verified evidence"
                            )
            if profile in {"BRAND_PROMO", "BRAND_NONFICTION"}:
                brand_claim_sources = boundary_source_ids | approved_claim_ids
                for atom in atoms:
                    if atom.get("priority") == "MUST" and atom.get("dimension") == "PROTECTED_BOUNDARY":
                        if not set(map(str, as_list(atom.get("source_or_state_refs")))) & brand_claim_sources:
                            errors.append(
                                f"PQ_BOUNDARY_VIOLATION {quality_id}: brand claim boundary MUST atom must cite "
                                "an approved decision, primary source, or current verified evidence"
                            )
            atom_dimensions = {str(atom.get("dimension")) for atom in atoms}
            expected_dimensions = (
                {"SPACE", "CAMERA", "MATERIAL_LIGHT_ENVIRONMENT"}
                if medium == "IMAGE"
                else set(PROMPT_PROFILE_BASE_DIMENSIONS.get(profile, set())) | {"SPACE"}
            )
            if medium == "IMAGE" and profile in {
                "NONFICTION_VISUAL", "BRAND_PROMO", "BRAND_NONFICTION",
            }:
                expected_dimensions.add("PROTECTED_BOUNDARY")
            if expected_asset_ids:
                expected_dimensions.add("ASSET_STATE")
            character_assets = {
                asset_id for asset_id in expected_asset_ids
                if asset_by_id.get(asset_id, {}).get("asset_type") == "CHARACTER"
            }
            if character_assets or identity_closeup:
                expected_dimensions.add("IDENTITY")
                if medium == "IMAGE":
                    expected_dimensions.add("PERFORMANCE")
            if expected_reference_ids:
                expected_dimensions.add("REFERENCE_RESPONSIBILITY")
            expected_dialogue_ids = (
                set() if medium == "IMAGE" or target_type != "SHOT" or generation_role != "SHOT_MOTION"
                else set(map(str, as_list((shot or {}).get("dialogue_ids"))))
            )
            if expected_dialogue_ids:
                expected_dimensions.add("VERBATIM_DIALOGUE")
            if contact_required:
                expected_dimensions.add("CONTACT_PHYSICS")
            if (
                as_list((shot or {}).get("protected_unknown_ids"))
                or as_list((shot or {}).get("causal_boundary_ids"))
            ):
                expected_dimensions.add("PROTECTED_BOUNDARY")
            if as_list((shot or {}).get("quantity_ids")):
                expected_dimensions.update({"COUNT", "PROTECTED_BOUNDARY"})
            missing_dimensions = expected_dimensions - atom_dimensions
            if missing_dimensions:
                errors.append(
                    f"PQ_ADAPTER_LOSS {quality_id}: missing applicable semantic dimensions {sorted(missing_dimensions)}"
                )
            must_dimensions_present = {
                str(atom.get("dimension")) for atom in atoms if atom.get("priority") == "MUST"
            }
            non_must_required_dimensions = expected_dimensions - must_dimensions_present
            if non_must_required_dimensions:
                errors.append(
                    f"PQ_ADAPTER_LOSS {quality_id}: applicable dimensions need at least one MUST atom "
                    f"{sorted(non_must_required_dimensions)}"
                )
            if medium == "VIDEO" and target_type == "SHOT" and generation_role == "SHOT_MOTION":
                director_source_bindings = {
                    "EVENT_ORDER": "required_event",
                    "ACTION_ENDPOINT": "planned_state_out",
                    "CONTINUITY": "state_in",
                }
                for dimension, shot_field in director_source_bindings.items():
                    source_value = str((shot or {}).get(shot_field, ""))
                    candidates = [
                        atom for atom in atoms
                        if atom.get("priority") == "MUST" and atom.get("dimension") == dimension
                    ]
                    if not any(
                        target_id in set(map(str, as_list(atom.get("source_or_state_refs"))))
                        and str(atom.get("master_anchor", "")) == source_value
                        and source_value in str(atom.get("canonical_claim", ""))
                        for atom in candidates
                    ):
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}: {dimension} MUST atom must bind "
                            f"{target_id}.{shot_field} exactly"
                        )

            dialogue_fit = quality.get("dialogue_fit") if isinstance(
                quality.get("dialogue_fit"), dict
            ) else {}
            declared_dialogue_ids = set(map(str, as_list(dialogue_fit.get("dialogue_ids"))))
            fragments = [
                item for item in as_list(dialogue_fit.get("fragments"))
                if isinstance(item, dict)
            ]
            if declared_dialogue_ids != expected_dialogue_ids:
                errors.append(
                    f"PQ_DIALOGUE_LOSS {quality_id}: dialogue_fit scope must exactly match shot dialogue"
                )
            if not expected_dialogue_ids:
                if dialogue_fit.get("status") != "NOT_APPLICABLE" or fragments:
                    errors.append(
                        f"PQ_DIALOGUE_LOSS {quality_id}: dialogue-free shot must be NOT_APPLICABLE"
                    )
            else:
                if quality.get("quality_status", {}).get("status") == "PASS" and dialogue_fit.get(
                    "status"
                ) != "FIT":
                    errors.append(f"PQ_DIALOGUE_LOSS {quality_id}: PASS requires dialogue FIT")
                fragments_by_dialogue: dict[str, list[dict[str, Any]]] = {}
                for fragment in fragments:
                    dialogue_id = str(fragment.get("dialogue_id", ""))
                    fragments_by_dialogue.setdefault(dialogue_id, []).append(fragment)
                    start = fragment.get("start_seconds")
                    end = fragment.get("end_seconds")
                    if (
                        isinstance(start, bool) or not isinstance(start, (int, float))
                        or isinstance(end, bool) or not isinstance(end, (int, float))
                        or float(start) < 0 or float(end) <= float(start)
                        or not isinstance(duration, (int, float)) or float(end) > float(duration) + 0.001
                    ):
                        errors.append(
                            f"PQ_DIALOGUE_LOSS {quality_id}: dialogue fragment has invalid timing"
                        )
                for dialogue_id in expected_dialogue_ids:
                    dialogue = dialogue_by_id.get(dialogue_id, {})
                    rows = sorted(
                        fragments_by_dialogue.get(dialogue_id, []),
                        key=lambda item: int(item.get("fragment_index", 0)),
                    )
                    if [row.get("fragment_index") for row in rows] != list(
                        range(1, len(rows) + 1)
                    ) or not rows:
                        errors.append(
                            f"PQ_DIALOGUE_LOSS {quality_id}: {dialogue_id} fragment indexes are incomplete"
                        )
                        continue
                    if unicodedata.normalize("NFC", "".join(
                        str(row.get("verbatim_text", "")) for row in rows
                    )) != unicodedata.normalize("NFC", str(dialogue.get("text", ""))):
                        errors.append(
                            f"PQ_DIALOGUE_LOSS {quality_id}: {dialogue_id} does not reconstruct verbatim"
                        )
                    if any(
                        row.get("speaker_asset_id") != dialogue.get("speaker_asset_id") for row in rows
                    ):
                        errors.append(
                            f"PQ_DIALOGUE_LOSS {quality_id}: {dialogue_id} speaker changed"
                        )
                    if rows[0].get("bridge_from_previous") is not False or any(
                        row.get("bridge_from_previous") is not True for row in rows[1:]
                    ):
                        errors.append(
                            f"PQ_DIALOGUE_LOSS {quality_id}: {dialogue_id} bridge flags are invalid"
                        )
                if lip_sync_required and not any(
                    fragment.get("delivery_mode") == "ONSCREEN_LIP" for fragment in fragments
                ):
                    errors.append(
                        f"PQ_DIALOGUE_LOSS {quality_id}: visible lip sync lacks ONSCREEN_LIP fragment"
                    )

            must_atom_ids = {
                atom_id for atom_id, atom in atom_by_id.items() if atom.get("priority") == "MUST"
            }
            must_dimensions = {
                str(atom.get("dimension")) for atom in atoms if atom.get("priority") == "MUST"
            }
            beat_ids = set(beat_by_id)
            layer_sections: dict[str, dict[str, dict[str, Any]]] = {}

            def inspect_layer(
                record: dict[str, Any] | None, record_id: str, text_field: str, layer: str
            ) -> tuple[set[str], set[str], set[str]]:
                if not record:
                    return set(), set(), set()
                layer_errors, section_map, covered_atoms, covered_beats, kinds = inspect_prompt_sections(
                    label=f"{quality_id}/{record_id}",
                    text=record.get(text_field),
                    sections=record.get("prompt_sections"),
                    atom_ids=set(atom_by_id),
                    beat_ids=beat_ids,
                )
                errors.extend(layer_errors)
                layer_sections[record_id] = section_map
                overlap = global_section_ids & set(section_map)
                if overlap:
                    errors.append(
                        f"PQ_TRIVIAL_OR_SUMMARY_ONLY {quality_id}: section IDs reused across layers {sorted(overlap)}"
                    )
                global_section_ids.update(section_map)
                if must_atom_ids - covered_atoms:
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{record_id}: MUST atoms are not fully mapped"
                    )
                if layer in {"MASTER", "NEUTRAL_EXECUTION", "COMPILED"}:
                    required_final_sections = (
                        PROMPT_REQUIRED_IMAGE_SECTIONS
                        if medium == "IMAGE" else PROMPT_REQUIRED_VIDEO_SECTIONS
                    )
                    if required_final_sections - kinds:
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}/{record_id}: missing final section kinds "
                            f"{sorted(required_final_sections - kinds)}"
                        )
                    if covered_beats != beat_ids:
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}/{record_id}: director beat coverage is incomplete"
                        )
                    if medium == "IMAGE" and kinds - PROMPT_ALLOWED_IMAGE_SECTIONS:
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}/{record_id}: static IMAGE contains "
                            f"dynamic section kinds {sorted(kinds - PROMPT_ALLOWED_IMAGE_SECTIONS)}"
                        )
                    if "TRANSFORM_PLAN" in kinds:
                        errors.append(
                            f"E_PROMPT_LAYER_ROLE_CONFLICT {quality_id}/{record_id}: executable-text "
                            "layer contains planning-only sections"
                        )
                elif layer in {"DRAFT", "TRANSFORM_PLAN"} and kinds != {"TRANSFORM_PLAN"}:
                    errors.append(
                        f"E_PROMPT_LAYER_ROLE_CONFLICT {quality_id}/{record_id}: planning layer "
                        "must contain only TRANSFORM_PLAN sections"
                    )
                record_text = str(record.get(text_field, ""))
                static_positive_text = "\n".join(
                    record_text[
                        int(section.get("start_char", 0)):int(section.get("end_char", 0))
                    ]
                    for section in section_map.values()
                    if section.get("kind") not in {"NEGATIVE", "TRANSFORM_PLAN"}
                )
                if medium == "IMAGE" and STATIC_DYNAMIC_LANGUAGE_RE.search(static_positive_text):
                    errors.append(
                        f"PQ_BEAT_CONTRACT_THIN {quality_id}/{record_id}: static IMAGE Prompt contains "
                        "timeline, dialogue, sound, or camera-motion language"
                    )
                return covered_atoms, covered_beats, kinds

            inspect_layer(master, str(master_id), "master_prompt_text", "MASTER")
            if four_layer_prompt_contract:
                inspect_layer(
                    transform_plan, str(transform_plan_id), "transform_plan_text",
                    "TRANSFORM_PLAN",
                )
                inspect_layer(
                    neutral_execution_prompt, str(neutral_execution_prompt_id),
                    "neutral_execution_prompt_text", "NEUTRAL_EXECUTION",
                )
            else:
                inspect_layer(draft, str(draft_id), "draft_prompt_text", "DRAFT")
            for prompt_id in compiled_ids:
                prompt = prompt_by_id.get(prompt_id)
                inspect_layer(prompt, prompt_id, "prompt_text", "COMPILED")
                if prompt and PROMPT_INTERNAL_LEAK_RE.search(str(prompt.get("prompt_text", ""))):
                    errors.append(
                        f"PQ_INTERNAL_LEAKAGE {quality_id}/{prompt_id}: internal machine details leaked into execution text"
                    )
                source_execution_text = (
                    (neutral_execution_prompt or {}).get("neutral_execution_prompt_text")
                    if four_layer_prompt_contract else (draft or {}).get("draft_prompt_text")
                )
                if (
                    prompt and source_execution_text is not None
                    and prompt.get("execution_contract") == "GENERATION_EXECUTABLE"
                    and normalized_prompt_text(prompt.get("prompt_text"))
                    == normalized_prompt_text(source_execution_text)
                ):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: executable compiled Prompt is an "
                        "unchanged neutral execution Prompt"
                    )
                if prompt:
                    prompt_text = str(prompt.get("prompt_text", ""))
                    prompt_sections = layer_sections.get(prompt_id, {})
                    for atom_id in must_atom_ids:
                        atom = atom_by_id[atom_id]
                        anchor_rows = [
                            row for row in as_list(atom.get("compiled_anchors"))
                            if isinstance(row, dict)
                            and str(row.get("provider_prompt_id")) == prompt_id
                        ]
                        output_anchor = str(anchor_rows[0].get("output_anchor", "")) if len(anchor_rows) == 1 else ""
                        positive_sections = [
                            section for section in prompt_sections.values()
                            if section.get("kind") != "NEGATIVE"
                            and atom_id in set(map(str, as_list(section.get("atom_ids"))))
                        ]
                        if not positive_sections or not any(
                            positive_anchor_occurs(prompt_text[
                                int(section.get("start_char", 0)):int(section.get("end_char", 0))
                            ], output_anchor)
                            for section in positive_sections
                        ):
                            errors.append(
                                f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: MUST compiled anchor {atom_id} "
                                "must occur in its mapped non-NEGATIVE section"
                            )
                if prompt and expected_dialogue_ids:
                    compiled_text = str(prompt.get("prompt_text", ""))
                    for fragment in fragments:
                        fragment_text = str(fragment.get("verbatim_text", ""))
                        if fragment_text and compiled_text.count(fragment_text) != 1:
                            errors.append(
                                f"PQ_DIALOGUE_LOSS {quality_id}/{prompt_id}: dialogue fragment must appear exactly once"
                            )
            if master:
                master_text = str(master.get("master_prompt_text", ""))
                master_sections = layer_sections.get(str(master_id), {})
                for atom_id in must_atom_ids:
                    anchor = atom_by_id[atom_id].get("master_anchor")
                    positive_sections = [
                        section for section in master_sections.values()
                        if section.get("kind") != "NEGATIVE"
                        and atom_id in set(map(str, as_list(section.get("atom_ids"))))
                    ]
                    if nonempty(anchor) and (
                        not positive_sections or not any(
                            positive_anchor_occurs(
                                master_text[
                                    int(section.get("start_char", 0)):int(section.get("end_char", 0))
                                ],
                                str(anchor),
                            )
                            for section in positive_sections
                        )
                    ):
                        errors.append(
                            f"PQ_ADAPTER_LOSS {quality_id}/{master_id}: MUST anchor {atom_id} must occur "
                            "positively in its mapped non-NEGATIVE MASTER section"
                        )

            translated_prompt_ids = {
                str(adapter.get("provider_prompt_id", ""))
                for adapter in as_list(quality.get("adapter_integrity"))
                if isinstance(adapter, dict)
                and any(
                    isinstance(operation, dict)
                    and operation.get("kind") == "LANGUAGE_TRANSLATION"
                    for operation in as_list(adapter.get("adapter_operations"))
                )
            }
            if medium == "VIDEO":
                master_text = str((master or {}).get("master_prompt_text", ""))
                master_section_map = layer_sections.get(str(master_id), {})
                compiled_anchor_spans: dict[str, list[tuple[int, int, str]]] = {
                    prompt_id: [] for prompt_id in compiled_ids
                }
                compiled_execution_values: dict[str, set[str]] = {
                    prompt_id: set() for prompt_id in compiled_ids
                }
                for beat in beats:
                    beat_id = str(beat.get("beat_id", ""))
                    master_timeline_sections = [
                        section for section in master_section_map.values()
                        if section.get("kind") == "DIRECTOR_TIMELINE"
                        and beat_id in set(map(str, as_list(section.get("beat_ids"))))
                    ]
                    for field in ("camera", "action_physics", "exit_state"):
                        canonical_value = str(beat.get(field, ""))
                        if not master_timeline_sections or not any(
                            positive_anchor_occurs(
                                master_text[
                                    int(section.get("start_char", 0)):
                                    int(section.get("end_char", 0))
                                ],
                                canonical_value,
                            )
                            for section in master_timeline_sections
                        ):
                            errors.append(
                                f"PQ_BEAT_CONTRACT_THIN {quality_id}/{master_id}: {beat_id}.{field} "
                                "must occur positively in its MASTER director timeline"
                            )

                    anchor_rows = [
                        row for row in as_list(beat.get("compiled_anchors"))
                        if isinstance(row, dict)
                    ]
                    anchor_prompt_ids = [str(row.get("provider_prompt_id", "")) for row in anchor_rows]
                    if set(anchor_prompt_ids) != compiled_ids or len(anchor_prompt_ids) != len(
                        set(anchor_prompt_ids)
                    ):
                        errors.append(
                            f"PQ_BEAT_CONTRACT_THIN {quality_id}: {beat_id} needs one execution anchor "
                            "per compiled Prompt"
                        )
                    for row in anchor_rows:
                        prompt_id = str(row.get("provider_prompt_id", ""))
                        prompt = prompt_by_id.get(prompt_id, {})
                        prompt_text = str(prompt.get("prompt_text", ""))
                        section_id = str(row.get("section_id", ""))
                        section = layer_sections.get(prompt_id, {}).get(section_id)
                        execution_anchor = str(row.get("execution_anchor", ""))
                        camera_anchor = str(row.get("camera_anchor", ""))
                        action_anchor = str(row.get("action_anchor", ""))
                        exit_anchor = str(row.get("exit_anchor", ""))
                        output_cues = (camera_anchor, action_anchor, exit_anchor)
                        canonical_cues = (
                            str(beat.get("camera", "")),
                            str(beat.get("action_physics", "")),
                            str(beat.get("exit_state", "")),
                        )
                        if (
                            prompt_id not in compiled_ids
                            or not isinstance(section, dict)
                            or section.get("kind") != "DIRECTOR_TIMELINE"
                            or beat_id not in set(map(str, as_list(section.get("beat_ids"))))
                            or not substantive_director_source(execution_anchor)
                            or any(not substantive_director_source(cue) for cue in output_cues)
                            or len({normalized_prompt_text(cue) for cue in output_cues}) != 3
                            or any(cue not in execution_anchor for cue in output_cues)
                        ):
                            errors.append(
                                f"PQ_BEAT_CONTRACT_THIN {quality_id}/{prompt_id}: {beat_id} compiled "
                                "execution anchor does not bind its camera, action, and exit"
                            )
                            continue
                        if prompt_id not in translated_prompt_ids and output_cues != canonical_cues:
                            errors.append(
                                f"PQ_BEAT_CONTRACT_THIN {quality_id}/{prompt_id}: {beat_id} same-language "
                                "compiled camera, action, and exit anchors must equal the canonical beat"
                            )
                            continue
                        section_start = int(section.get("start_char", 0))
                        section_end = int(section.get("end_char", 0))
                        section_text = prompt_text[section_start:section_end]
                        local_index = section_text.find(execution_anchor)
                        if (
                            local_index < 0
                            or section_text.count(execution_anchor) != 1
                            or not positive_anchor_occurs(section_text, execution_anchor)
                        ):
                            errors.append(
                                f"PQ_BEAT_CONTRACT_THIN {quality_id}/{prompt_id}: {beat_id} execution "
                                "anchor must occur exactly once and positively in its mapped timeline section"
                            )
                            continue
                        normalized_execution = normalized_prompt_text(execution_anchor)
                        if normalized_execution in compiled_execution_values.setdefault(prompt_id, set()):
                            errors.append(
                                f"PQ_BEAT_CONTRACT_THIN {quality_id}/{prompt_id}: director beats cannot "
                                "reuse one compiled execution fragment"
                            )
                        compiled_execution_values[prompt_id].add(normalized_execution)
                        absolute_span = (
                            section_start + local_index,
                            section_start + local_index + len(execution_anchor),
                            beat_id,
                        )
                        for prior_start, prior_end, prior_beat in compiled_anchor_spans.setdefault(
                            prompt_id, []
                        ):
                            if absolute_span[0] < prior_end and prior_start < absolute_span[1]:
                                errors.append(
                                    f"PQ_BEAT_CONTRACT_THIN {quality_id}/{prompt_id}: {beat_id} and "
                                    f"{prior_beat} execution anchors overlap"
                                )
                        compiled_anchor_spans[prompt_id].append(absolute_span)

            adapter_rows = [
                item for item in as_list(quality.get("adapter_integrity"))
                if isinstance(item, dict)
            ]
            adapter_ids = [str(item.get("provider_prompt_id")) for item in adapter_rows]
            if set(adapter_ids) != compiled_ids or len(adapter_ids) != len(set(adapter_ids)):
                errors.append(
                    f"PQ_ADAPTER_LOSS {quality_id}: every compiled Prompt needs exactly one adapter integrity record"
                )
            for adapter in adapter_rows:
                prompt_id = str(adapter.get("provider_prompt_id"))
                if four_layer_prompt_contract and str(
                    adapter.get("neutral_execution_prompt_id", "")
                ) != str(neutral_execution_prompt_id):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: adapter source must be the "
                        "bound NEUTRAL_EXECUTION_PROMPT"
                    )
                operations = [
                    item for item in as_list(adapter.get("adapter_operations"))
                    if isinstance(item, dict)
                ]
                if prompt_id in compiled_ids and not operations:
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: adapter operations cannot be empty"
                    )
                prompt_locale = str(prompt_by_id.get(prompt_id, {}).get("prompt_locale", ""))
                if (
                    prompt_locale
                    and re.match(r"^[zZ][hH](?:-|$)", prompt_locale) is None
                    and not any(operation.get("kind") == "LANGUAGE_TRANSLATION" for operation in operations)
                ):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: non-Chinese provider locale requires "
                        "an explicit LANGUAGE_TRANSLATION adapter operation"
                    )
                source_sections = (
                    set(layer_sections.get(str(neutral_execution_prompt_id), {}))
                    if four_layer_prompt_contract
                    else set(layer_sections.get(str(master_id), {}))
                    | set(layer_sections.get(str(draft_id), {}))
                )
                output_sections = set(layer_sections.get(prompt_id, {}))
                changed_operation = False
                operation_evidence: set[str] = set()
                for operation in operations:
                    source_ids = set(map(str, as_list(operation.get("source_section_ids"))))
                    output_ids = set(map(str, as_list(operation.get("output_section_ids"))))
                    evidence_ids = set(map(str, as_list(operation.get("evidence_ids"))))
                    operation_evidence |= evidence_ids
                    if source_ids - source_sections or output_ids - output_sections:
                        errors.append(
                            f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: adapter operation has unresolved sections"
                        )
                    if evidence_ids - set(evidence_by_id):
                        errors.append(
                            f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: adapter operation has unknown evidence"
                        )
                    legacy_source_texts = {
                        normalized_prompt_text(
                            (master or {}).get("master_prompt_text", "")[
                                layer_sections.get(str(master_id), {}).get(section_id, {}).get("start_char", 0):
                                layer_sections.get(str(master_id), {}).get(section_id, {}).get("end_char", 0)
                            ]
                        )
                        for section_id in source_ids & set(layer_sections.get(str(master_id), {}))
                    } | {
                        normalized_prompt_text(
                            (draft or {}).get("draft_prompt_text", "")[
                                layer_sections.get(str(draft_id), {}).get(section_id, {}).get("start_char", 0):
                                layer_sections.get(str(draft_id), {}).get(section_id, {}).get("end_char", 0)
                            ]
                        )
                        for section_id in source_ids & set(layer_sections.get(str(draft_id), {}))
                    }
                    neutral_source_texts = {
                        normalized_prompt_text(
                            (neutral_execution_prompt or {}).get(
                                "neutral_execution_prompt_text", ""
                            )[
                                layer_sections.get(
                                    str(neutral_execution_prompt_id), {}
                                ).get(section_id, {}).get("start_char", 0):
                                layer_sections.get(
                                    str(neutral_execution_prompt_id), {}
                                ).get(section_id, {}).get("end_char", 0)
                            ]
                        )
                        for section_id in source_ids
                        & set(layer_sections.get(str(neutral_execution_prompt_id), {}))
                    }
                    source_texts = (
                        neutral_source_texts
                        if four_layer_prompt_contract else legacy_source_texts
                    )
                    prompt_text = str(prompt_by_id.get(prompt_id, {}).get("prompt_text", ""))
                    output_texts = {
                        normalized_prompt_text(
                            prompt_text[
                                layer_sections.get(prompt_id, {}).get(section_id, {}).get("start_char", 0):
                                layer_sections.get(prompt_id, {}).get(section_id, {}).get("end_char", 0)
                            ]
                        )
                        for section_id in output_ids & output_sections
                    }
                    if source_texts != output_texts:
                        changed_operation = True
                if (
                    operations and not changed_operation
                    and prompt_by_id.get(prompt_id, {}).get("execution_contract")
                    != "MANUAL_COPY_TEXT_SPEC_ONLY"
                ):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: adapter operations describe no real text change"
                    )
                if adapter.get("compression_authority") != "NONE" and not operation_evidence:
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: compression authority lacks evidence"
                    )
                if adapter.get("adapter_mode") == "SEGMENT_WITH_HANDOFF":
                    if not as_list(adapter.get("segment_handoff_ids")) or not any(
                        operation.get("kind") == "DURATION_SEGMENTATION" for operation in operations
                    ):
                        errors.append(
                            f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: segmented adapter lacks handoff contract"
                        )
                elif as_list(adapter.get("segment_handoff_ids")):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: non-segment adapter cannot claim handoffs"
                    )
                if not must_dimensions <= set(map(str, as_list(adapter.get("preserved_dimensions")))):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: adapter did not preserve all MUST dimensions"
                    )
                if adapter.get("status") == "PASS" and as_list(adapter.get("loss_findings")):
                    errors.append(
                        f"PQ_ADAPTER_LOSS {quality_id}/{prompt_id}: PASS adapter retains loss findings"
                    )

            review_rows = [
                item for item in as_list(quality.get("two_pass_reviews"))
                if isinstance(item, dict)
            ]
            expected_reference_delta_sha = reference_delta_digest(reference_delta)
            review_prompt_ids: list[str] = []
            valid_review_prompt_ids: set[str] = set()
            for review in review_rows:
                review_id = str(review.get("review_id", ""))
                prompt_id = str(review.get("provider_prompt_id", ""))
                review_prompt_ids.append(prompt_id)
                if not review_id or review_id in global_prompt_review_ids:
                    errors.append(
                        f"PQ_REVIEW_MISSING_OR_STALE {quality_id}: review_id missing or reused {review_id!r}"
                    )
                global_prompt_review_ids.add(review_id)
                prompt = prompt_by_id.get(prompt_id, {})
                current_master_sha = exact_text_sha256((master or {}).get("master_prompt_text", ""))
                current_transform_plan_sha = exact_text_sha256(
                    (transform_plan or {}).get("transform_plan_text", "")
                )
                current_neutral_execution_prompt_sha = exact_text_sha256(
                    (neutral_execution_prompt or {}).get(
                        "neutral_execution_prompt_text", ""
                    )
                )
                current_prompt_sha = exact_text_sha256(prompt.get("prompt_text", ""))
                review_checks_pass = all(
                    review.get(field) == "PASS"
                    for field in (
                        "omission_check", "injection_check", "specificity_check",
                        "adapter_value_check",
                    )
                )
                delta_review_valid = (
                    (
                        expected_reference_delta_sha is None
                        and review.get("reference_delta_sha256") is None
                        and review.get("reference_delta_check") == "NOT_APPLICABLE"
                    )
                    or (
                        expected_reference_delta_sha is not None
                        and str(review.get("reference_delta_sha256", "")).lower()
                        == expected_reference_delta_sha
                        and review.get("reference_delta_check") == "PASS"
                    )
                )
                review_invalid = (
                    prompt_id not in compiled_ids
                    or review.get("review_protocol_version")
                    != (
                        "ALPHA7-4LAYER-2PASS-2"
                        if four_layer_prompt_contract else "ALPHA7-2PASS-1"
                    )
                    or review.get("first_pass_status") != "COMPLETED"
                    or review.get("second_pass_mode") != "INDEPENDENT_READ_ONLY"
                    or str(review.get("master_prompt_sha256", "")).lower() != current_master_sha
                    or (
                        four_layer_prompt_contract
                        and str(review.get("transform_plan_sha256", "")).lower()
                        != current_transform_plan_sha
                    )
                    or (
                        four_layer_prompt_contract
                        and str(
                            review.get("neutral_execution_prompt_sha256", "")
                        ).lower() != current_neutral_execution_prompt_sha
                    )
                    or str(review.get("provider_prompt_sha256", "")).lower() != current_prompt_sha
                    or str(review.get("reviewed_prompt_soul_sha256", "")).lower()
                    != str(quality.get("prompt_soul_sha256", "")).lower()
                    or review.get("status") != "PASS"
                    or not review_checks_pass
                    or not delta_review_valid
                    or as_list(review.get("findings"))
                    or not nonempty(review.get("reviewed_at"))
                )
                if review_invalid:
                    errors.append(
                        f"PQ_REVIEW_MISSING_OR_STALE {quality_id}/{prompt_id}: two-pass review is "
                        "missing, failed, or stale against the current four-layer chain/Soul"
                    )
                else:
                    valid_review_prompt_ids.add(prompt_id)
                if medium == "VIDEO":
                    expected_event = (
                        str((shot or {}).get("required_event", ""))
                        if target_type == "SHOT" and generation_role == "SHOT_MOTION"
                        else ""
                    )
                    expected_exit = (
                        str((shot or {}).get("planned_state_out", ""))
                        if target_type == "SHOT" and generation_role == "SHOT_MOTION"
                        else str(beats[-1].get("exit_state", "")) if beats else ""
                    )
                    event_reconstruction = str(review.get("event_order_reconstruction", ""))
                    if (
                        review.get("static_state_reconstruction") is not None
                        or (expected_event and event_reconstruction != expected_event)
                        or (not expected_event and not substantive_director_source(event_reconstruction))
                        or str(review.get("visible_exit_state_reconstruction", "")) != expected_exit
                    ):
                        errors.append(
                            f"PQ_REVIEW_MISSING_OR_STALE {quality_id}/{prompt_id}: read-only review did not "
                            "reconstruct the current event order and visible exit"
                        )
                        valid_review_prompt_ids.discard(prompt_id)
                    else:
                        valid_review_prompt_ids.add(prompt_id)
                elif medium == "IMAGE":
                    if (
                        review.get("event_order_reconstruction") is not None
                        or review.get("visible_exit_state_reconstruction") is not None
                        or not substantive_director_source(review.get("static_state_reconstruction"))
                    ):
                        errors.append(
                            f"PQ_REVIEW_MISSING_OR_STALE {quality_id}/{prompt_id}: static review must "
                            "reconstruct only the visible static state"
                        )
                        valid_review_prompt_ids.discard(prompt_id)
            if len(review_prompt_ids) != len(set(review_prompt_ids)) or set(review_prompt_ids) - compiled_ids:
                errors.append(
                    f"PQ_REVIEW_MISSING_OR_STALE {quality_id}: reviews must be unique and bind this "
                    "quality record's compiled Prompts"
                )
            high_risk_quality = any(
                beat.get("risk_load") == "HIGH" or beat.get("high_risk_event") != "NONE"
                for beat in beats
            )
            if high_risk_quality and compiled_ids - valid_review_prompt_ids:
                errors.append(
                    f"PQ_REVIEW_MISSING_OR_STALE {quality_id}: high-risk Prompt requires current "
                    f"two-pass review {sorted(compiled_ids - valid_review_prompt_ids)}"
                )
            if isinstance(reference_delta, dict) and compiled_ids - valid_review_prompt_ids:
                errors.append(
                    f"PQ_REVIEW_MISSING_OR_STALE {quality_id}: reference-delta Prompt requires "
                    "a current read-only review of source/preserve/change/add/output text alignment "
                    f"{sorted(compiled_ids - valid_review_prompt_ids)}"
                )
            review_pass_prompt_ids |= valid_review_prompt_ids
            for review in review_rows:
                prompt_id = str(review.get("provider_prompt_id", ""))
                if prompt_id in valid_review_prompt_ids:
                    review_scope_by_prompt_id[prompt_id] = str(review.get("review_scope", ""))

            quality_status = quality.get("quality_status") if isinstance(
                quality.get("quality_status"), dict
            ) else {}
            status = quality_status.get("status")
            if status == "PASS":
                current_neutral_pass = (
                    four_layer_prompt_contract
                    and quality_evaluation_scope == "NEUTRAL_EXECUTION"
                    and bool(master and transform_plan and neutral_execution_prompt)
                    and not compiled_ids and not adapter_rows and not review_rows
                )
                compiled_pass = (
                    bool(master and compiled_ids)
                    and (
                        bool(transform_plan and neutral_execution_prompt)
                        if four_layer_prompt_contract else bool(draft)
                    )
                    and all(adapter.get("status") == "PASS" for adapter in adapter_rows)
                    and set(adapter_ids) == compiled_ids
                )
                if (
                    not (current_neutral_pass or compiled_pass)
                    or dialogue_fit.get("status") not in {"FIT", "NOT_APPLICABLE"}
                    or as_list(quality_status.get("fail_codes"))
                    or len(errors) > record_error_start
                ):
                    errors.append(
                        f"E_PROMPT_QUALITY_NOT_READY {quality_id}: PASS contradicts unresolved prompt quality state"
                    )
                elif compiled_pass:
                    quality_pass_prompt_ids |= compiled_ids
            elif status == "FAIL" and not as_list(quality_status.get("fail_codes")):
                errors.append(
                    f"E_PROMPT_QUALITY_NOT_READY {quality_id}: FAIL requires fail_codes"
                )
            elif status == "NOT_RUN" and as_list(quality_status.get("fail_codes")):
                errors.append(
                    f"E_PROMPT_QUALITY_NOT_READY {quality_id}: NOT_RUN cannot claim fail_codes"
                )

        missing_quality_targets = prompt_targets - set(quality_by_target)
        if missing_quality_targets:
            errors.append(
                f"E_PROMPT_QUALITY_MISSING prompt_quality_records: missing target/spec/role records "
                f"{sorted(missing_quality_targets)}"
            )
        unbound_compiled = set(prompt_by_id) - set(quality_for_prompt_id)
        if unbound_compiled:
            errors.append(
                f"E_PROMPT_QUALITY_MISSING prompt_quality_records: compiled Prompts lack quality records {sorted(unbound_compiled)}"
            )

    # A Pilot is scoped by the same generation-target contract as execution.  An
    # asset-reference Pilot is intentionally legal before any shot plan exists;
    # SHOT targets, by contrast, must resolve to their exact containing plans.
    if current_quality_contract:
        for pilot in pilot_assessments:
            if not isinstance(pilot, dict):
                continue
            pilot_id = str(pilot.get("pilot_id", "<pilot>"))
            declared_spec = str(pilot.get("source_spec_version", ""))
            declared_prompts = set(map(str, as_list(pilot.get("prompt_ids"))))
            declared_assets = set(map(str, as_list(pilot.get("asset_ids"))))
            declared_plans = set(map(str, as_list(pilot.get("shot_plan_ids"))))
            declared_providers = set(map(str, as_list(pilot.get("provider_registry_ids"))))
            declared_task_types = set(map(str, as_list(pilot.get("task_types"))))
            rows = [
                row for row in as_list(pilot.get("generation_targets"))
                if isinstance(row, dict)
            ]
            row_keys: list[tuple[str, str, str, str]] = []
            row_prompt_ids: set[str] = set()
            expected_assets: set[str] = set()
            expected_plans: set[str] = set()
            expected_providers: set[str] = set()
            media_seen: set[str] = set()
            for row in rows:
                key = prompt_target_key(row)
                row_keys.append(key)
                target_type, target_id, source_spec_version, generation_role = key
                medium = str(row.get("generation_medium", ""))
                media_seen.add(medium)
                prompt_ids = set(map(str, as_list(row.get("provider_prompt_ids"))))
                row_prompt_ids |= prompt_ids
                if source_spec_version != declared_spec:
                    errors.append(
                        f"E_PILOT_SCOPE_MISMATCH {pilot_id}: generation target source version disagrees with Pilot"
                    )
                if not generation_role_matches_medium(generation_role, medium):
                    errors.append(
                        f"E_PILOT_SCOPE_MISMATCH {pilot_id}: generation role/medium conflict for {key}"
                    )
                if target_type == "ASSET":
                    if target_id not in asset_by_id:
                        errors.append(
                            f"E_PILOT_SCOPE_MISMATCH {pilot_id}: unresolved ASSET target {target_id}"
                        )
                    else:
                        expected_assets.add(target_id)
                        if str(asset_by_id[target_id].get("source_spec_version")) != declared_spec:
                            errors.append(
                                f"E_PILOT_SCOPE_MISMATCH {pilot_id}: ASSET target version is stale"
                            )
                elif target_type == "SHOT":
                    if target_id not in shot_by_id:
                        errors.append(
                            f"E_PILOT_SCOPE_MISMATCH {pilot_id}: unresolved SHOT target {target_id}"
                        )
                    else:
                        expected_plans.add(shot_plan_for_shot[target_id])
                        expected_assets |= set(map(str, as_list(shot_by_id[target_id].get("asset_ids"))))
                        plan = shot_plan_by_id.get(shot_plan_for_shot[target_id], {})
                        if str(plan.get("source_spec_version")) != declared_spec:
                            errors.append(
                                f"E_PILOT_SCOPE_MISMATCH {pilot_id}: SHOT target plan version is stale"
                            )
                else:
                    errors.append(
                        f"E_PILOT_SCOPE_MISMATCH {pilot_id}: unknown generation target type {target_type!r}"
                    )
                for prompt_id in prompt_ids:
                    prompt = prompt_by_id.get(prompt_id)
                    if not prompt:
                        errors.append(
                            f"E_PILOT_SCOPE_MISMATCH {pilot_id}: unresolved compiled Prompt {prompt_id}"
                        )
                        continue
                    if prompt_target_key(prompt) != key or str(prompt.get("generation_medium")) != medium:
                        errors.append(
                            f"E_PILOT_SCOPE_MISMATCH {pilot_id}: Prompt {prompt_id} disagrees with generation target"
                        )
                    expected_assets |= set(map(str, as_list(prompt.get("asset_ids"))))
                    expected_providers.add(str(prompt.get("provider_registry_id")))
            if len(row_keys) != len(set(row_keys)):
                errors.append(f"E_PILOT_SCOPE_MISMATCH {pilot_id}: duplicate generation target")
            if row_prompt_ids != declared_prompts:
                errors.append(
                    f"E_PILOT_SCOPE_MISMATCH {pilot_id}: prompt_ids must equal the target Prompt union"
                )
            if expected_assets != declared_assets:
                errors.append(
                    f"E_PILOT_SCOPE_MISMATCH {pilot_id}: asset_ids must exactly cover target assets"
                )
            if expected_plans != declared_plans:
                errors.append(
                    f"E_PILOT_SCOPE_MISMATCH {pilot_id}: shot_plan_ids must exactly cover SHOT targets"
                )
            if expected_providers != declared_providers:
                errors.append(
                    f"E_PILOT_SCOPE_MISMATCH {pilot_id}: provider_registry_ids must exactly cover target Prompts"
                )
            if "IMAGE" in media_seen and "IMAGE_GENERATION" not in declared_task_types:
                errors.append(
                    f"E_PILOT_SCOPE_MISMATCH {pilot_id}: IMAGE targets require IMAGE_GENERATION task type"
                )
            if "VIDEO" in media_seen and not declared_task_types.intersection(
                {"VIDEO_GENERATION", "IMAGE_TO_VIDEO", "VIDEO_TO_VIDEO"}
            ):
                errors.append(
                    f"E_PILOT_SCOPE_MISMATCH {pilot_id}: VIDEO targets require a video generation task type"
                )
            if declared_prompts - quality_pass_prompt_ids:
                errors.append(
                    f"E_PROMPT_QUALITY_NOT_READY {pilot_id}: Pilot uses non-PASS quality Prompts "
                    f"{sorted(declared_prompts - quality_pass_prompt_ids)}"
                )
            if pilot.get("status") == "PASSED" and declared_prompts - review_pass_prompt_ids:
                errors.append(
                    f"PQ_REVIEW_MISSING_OR_STALE {pilot_id}: passed Pilot needs current two-pass review "
                    f"for every sampled Prompt {sorted(declared_prompts - review_pass_prompt_ids)}"
                )

    all_prompt_records = (
        provider_prompts + provider_neutral_drafts + master_prompts
        + transform_plans + neutral_execution_prompts
    )
    all_prompt_ids = (
        set(prompt_by_id) | set(neutral_draft_by_id) | set(master_prompt_by_id)
        | set(transform_plan_by_id) | set(neutral_execution_prompt_by_id)
    )
    for unknown in protected_unknowns:
        if not isinstance(unknown, dict):
            errors.append("protected unknown must be an object")
            continue
        uid = str(unknown.get("unknown_id", "<unknown>"))
        affected_artifacts = set(map(str, as_list(unknown.get("affected_artifact_ids"))))
        affected_shots = set(map(str, as_list(unknown.get("affected_shot_ids"))))
        affected_prompts = set(map(str, as_list(unknown.get("affected_prompt_ids"))))
        referenced_artifacts = {
            str(item.get("id")) for item in artifacts
            if isinstance(item, dict) and uid in set(map(str, as_list(item.get("protected_unknown_ids"))))
        }
        referenced_shots = {
            str(shot.get("shot_id")) for plan in shot_plans if isinstance(plan, dict)
            for shot in as_list(plan.get("shots")) if isinstance(shot, dict)
            and uid in set(map(str, as_list(shot.get("protected_unknown_ids"))))
        }
        referenced_prompts = {
            str(item.get("id")) for item in all_prompt_records
            if isinstance(item, dict) and uid in set(map(str, as_list(item.get("protected_unknown_ids"))))
        }
        if affected_artifacts != referenced_artifacts or affected_shots != referenced_shots or affected_prompts != referenced_prompts:
            errors.append(f"{uid}: affected output sets must exactly match output backlinks")
        if affected_artifacts - set(artifact_by_id) or affected_shots - all_shot_ids or affected_prompts - all_prompt_ids:
            errors.append(f"{uid}: affected outputs contain unresolved IDs")
        if unknown.get("status") == "RESOLVED":
            if unknown.get("resolution_basis") == "USER_APPROVAL" and unknown.get("approval_event_id") not in approval_by_id:
                errors.append(f"{uid}: resolved-by-approval unknown requires a valid approval event")
            if unknown.get("resolution_basis") == "VERIFIED_EVIDENCE":
                linked = set(map(str, as_list(unknown.get("evidence_ids"))))
                if not linked or linked - set(evidence_by_id):
                    errors.append(f"{uid}: resolved-by-evidence unknown requires valid evidence")
        if unknown.get("audit_status") == "PASSED":
            if set(map(str, as_list(unknown.get("audited_artifact_ids")))) != affected_artifacts:
                errors.append(f"{uid}: PASSED audit must cover every affected artifact exactly")
            if set(map(str, as_list(unknown.get("audited_shot_ids")))) != affected_shots:
                errors.append(f"{uid}: PASSED audit must cover every affected shot exactly")
            if set(map(str, as_list(unknown.get("audited_prompt_ids")))) != affected_prompts:
                errors.append(f"{uid}: PASSED audit must cover every affected prompt exactly")
        if workflow.get("spec_status") == "TEXT_SPEC_COMPLETE" and (
            affected_artifacts or affected_shots or affected_prompts
        ) and unknown.get("audit_status") != "PASSED":
            errors.append(f"{uid}: TEXT_SPEC_COMPLETE requires a passed protected-unknown audit")

    for boundary in causal_boundaries:
        if not isinstance(boundary, dict):
            errors.append("causal boundary must be an object")
            continue
        bid = str(boundary.get("boundary_id", "<boundary>"))
        affected_artifacts = set(map(str, as_list(boundary.get("affected_artifact_ids"))))
        affected_shots = set(map(str, as_list(boundary.get("affected_shot_ids"))))
        affected_prompts = set(map(str, as_list(boundary.get("affected_prompt_ids"))))
        referenced_artifacts = {
            str(item.get("id")) for item in artifacts
            if isinstance(item, dict) and bid in set(map(str, as_list(item.get("causal_boundary_ids"))))
        }
        referenced_shots = {
            str(shot.get("shot_id")) for plan in shot_plans if isinstance(plan, dict)
            for shot in as_list(plan.get("shots")) if isinstance(shot, dict)
            and bid in set(map(str, as_list(shot.get("causal_boundary_ids"))))
        }
        referenced_prompts = {
            str(item.get("id")) for item in all_prompt_records
            if isinstance(item, dict) and bid in set(map(str, as_list(item.get("causal_boundary_ids"))))
        }
        if affected_artifacts != referenced_artifacts or affected_shots != referenced_shots or affected_prompts != referenced_prompts:
            errors.append(f"{bid}: affected output sets must exactly match causal-boundary backlinks")
        checks = boundary.get("implication_checks") if isinstance(boundary.get("implication_checks"), dict) else {}
        if boundary.get("audit_status") == "PASSED" and "VIOLATION" in checks.values():
            errors.append(f"{bid}: PASSED causality audit cannot contain a VIOLATION")
        if boundary.get("audit_status") == "PASSED":
            if set(map(str, as_list(boundary.get("audited_artifact_ids")))) != affected_artifacts:
                errors.append(f"{bid}: PASSED audit must cover every affected artifact exactly")
            if set(map(str, as_list(boundary.get("audited_shot_ids")))) != affected_shots:
                errors.append(f"{bid}: PASSED audit must cover every affected shot exactly")
            if set(map(str, as_list(boundary.get("audited_prompt_ids")))) != affected_prompts:
                errors.append(f"{bid}: PASSED audit must cover every affected prompt exactly")
        if workflow.get("spec_status") == "TEXT_SPEC_COMPLETE" and (
            affected_artifacts or affected_shots or affected_prompts
        ) and boundary.get("audit_status") != "PASSED":
            errors.append(f"{bid}: TEXT_SPEC_COMPLETE requires a passed causality-implication audit")

    for quantity in quantities:
        if not isinstance(quantity, dict):
            continue
        qid = str(quantity.get("quantity_id", "<quantity>"))
        referenced_artifacts = {
            str(item.get("id")) for item in artifacts
            if isinstance(item, dict) and qid in set(map(str, as_list(item.get("quantity_ids"))))
        }
        referenced_shots = {
            str(shot.get("shot_id")) for plan in shot_plans if isinstance(plan, dict)
            for shot in as_list(plan.get("shots")) if isinstance(shot, dict)
            and qid in set(map(str, as_list(shot.get("quantity_ids"))))
        }
        referenced_prompts = {
            str(item.get("id")) for item in all_prompt_records
            if isinstance(item, dict) and qid in set(map(str, as_list(item.get("quantity_ids"))))
        }
        if set(map(str, as_list(quantity.get("used_in_artifact_ids")))) != referenced_artifacts:
            errors.append(f"{qid}: used_in_artifact_ids must exactly match artifact backlinks")
        if set(map(str, as_list(quantity.get("used_in_shot_ids")))) != referenced_shots:
            errors.append(f"{qid}: used_in_shot_ids must exactly match shot backlinks")
        if set(map(str, as_list(quantity.get("used_in_prompt_ids")))) != referenced_prompts:
            errors.append(f"{qid}: used_in_prompt_ids must exactly match prompt backlinks")

    for pilot in pilot_assessments:
        if not isinstance(pilot, dict):
            continue
        retell = pilot.get("unprompted_retell") if isinstance(pilot.get("unprompted_retell"), dict) else {}
        sample_quantity_id = retell.get("sample_quantity_id")
        if sample_quantity_id is not None and str(sample_quantity_id) not in quantity_by_id:
            errors.append(f"{pilot.get('pilot_id', '<pilot>')}: unprompted retell references unknown sample quantity")

    if legacy_generation and workflow.get("spec_status") == "TEXT_SPEC_COMPLETE" and (shot_plans or provider_prompts):
        if not isinstance(canonical, dict):
            errors.append("upstream completeness: TEXT_SPEC_COMPLETE production plan requires canonical_duration")
        if open_blocking_ids:
            errors.append("upstream completeness: TEXT_SPEC_COMPLETE cannot override open blocking issues")
    if isinstance(canonical, dict):
        known_precision_sources = set(evidence_by_id) | set(decision_by_id) | set(approval_by_id)
        missing_sources = set(map(str, as_list(canonical.get("source_or_evidence_ids")))) - known_precision_sources
        if missing_sources:
            errors.append(f"canonical_duration: unknown source IDs {sorted(missing_sources)}")

    learning_records = as_list(state.get("learning_records"))
    learning_by_id = index_unique(learning_records, "learning_id", "learning_records", errors)
    for learning in learning_records:
        if not isinstance(learning, dict):
            errors.append("learning record must be an object")
            continue
        lid = learning.get("learning_id", "<learning>")
        if learning.get("status") == "LEARNING_VALIDATED":
            linked = set(map(str, as_list(learning.get("real_data_evidence_ids"))))
            if not linked or linked - set(evidence_by_id):
                errors.append(f"{lid}: validated learning requires real data evidence")
            if not isinstance(learning.get("context"), dict) or not learning.get("context"):
                errors.append(f"{lid}: validated learning requires context")
            if not isinstance(learning.get("sample"), dict) or not learning.get("sample"):
                errors.append(f"{lid}: validated learning requires sample")
            if not isinstance(learning.get("outcome"), dict) or not learning.get("outcome"):
                errors.append(f"{lid}: validated learning requires real outcome")
            linked_publications = set(map(str, as_list(learning.get("publication_ids"))))
            if not linked_publications or linked_publications - set(publication_by_id):
                errors.append(f"{lid}: validated learning requires real publication records")
            if linked_publications - passed_publication_ids:
                errors.append(f"{lid}: validated learning publications must belong to a passed publication gate")
            analytics_ids = set(map(str, as_list(learning.get("analytics_artifact_ids"))))
            if not analytics_ids:
                errors.append(f"{lid}: validated learning requires analytics artifacts")
            for artifact_id in analytics_ids:
                artifact = artifact_by_id.get(artifact_id)
                if not artifact or artifact.get("artifact_class") != "DATA" or artifact.get("real_artifact_present") is not True:
                    errors.append(f"{lid}: analytics artifact {artifact_id} must be real DATA")
                elif not linked.intersection(map(str, as_list(artifact.get("evidence_ids")))):
                    errors.append(f"{lid}: analytics DATA evidence must intersect real_data_evidence_ids")
            matching_learning_gates = [
                gate
                for gate in gates
                if isinstance(gate, dict)
                and gate.get("gate_type") == "LEARNING_GATE"
                and gate.get("evaluation_status") == "EXECUTED"
                and gate.get("outcome") == "PASSED"
                and lid in set(map(str, as_list(gate.get("learning_ids"))))
            ]
            if not matching_learning_gates:
                errors.append(f"{lid}: validated learning requires a passed Learning Gate that explicitly references it")
            elif not any(
                linked_publications <= set(map(str, as_list(gate.get("publication_ids"))))
                and linked <= set(map(str, as_list(gate.get("evidence_ids"))))
                for gate in matching_learning_gates
            ):
                errors.append(f"{lid}: passed Learning Gate must cover its publications and real-data evidence")

    cleanup_attempt_by_id: dict[str, dict[str, Any]] = {}
    final_cleanup_attempt_id: str | None = None
    if alpha7:
        cleanup = state.get("state_cleanup")
        if not isinstance(cleanup, dict):
            errors.append("E_CLEANUP_VIOLATION_MISMATCH state_cleanup: Alpha.7 requires cleanup history")
        else:
            legacy_cleanup_fields = {"errors_found", "errors_fixed", "unresolved_issue_ids"} & set(cleanup)
            if legacy_cleanup_fields:
                errors.append(
                    "E_CLEANUP_VIOLATION_MISMATCH state_cleanup: Alpha.7 forbids legacy count-only fields "
                    f"{sorted(legacy_cleanup_fields)}"
                )
            if cleanup.get("audit_status") != "EXECUTED" or cleanup.get("history_completeness") != "COMPLETE":
                errors.append(
                    "E_CLEANUP_VIOLATION_MISMATCH state_cleanup: current Alpha.7 state requires "
                    "EXECUTED, COMPLETE history"
                )
            attempts = as_list(cleanup.get("validation_attempts"))
            corrections = as_list(cleanup.get("correction_records"))
            cleanup_attempt_by_id = index_unique(
                attempts, "attempt_id", "state_cleanup.validation_attempts", errors
            )
            correction_by_id = index_unique(
                corrections, "correction_id", "state_cleanup.correction_records", errors
            )
            del correction_by_id
            ordered_attempts = sorted(
                (item for item in attempts if isinstance(item, dict)),
                key=lambda item: item.get("sequence") if isinstance(item.get("sequence"), int) else 10**9,
            )
            sequences = [item.get("sequence") for item in ordered_attempts]
            if sequences != list(range(1, len(ordered_attempts) + 1)):
                errors.append(
                    "E_CLEANUP_VIOLATION_MISMATCH state_cleanup: attempt sequences must be unique and contiguous"
                )
            rejected_pairs: set[tuple[str, str]] = set()
            rejected_violations: set[str] = set()
            for attempt in ordered_attempts:
                attempt_id = str(attempt.get("attempt_id", "<attempt>"))
                violation_ids = set(map(str, as_list(attempt.get("violation_ids"))))
                if attempt.get("outcome") == "REJECTED":
                    if not violation_ids:
                        errors.append(
                            f"E_CLEANUP_VIOLATION_MISMATCH {attempt_id}: REJECTED attempt needs stable violation IDs"
                        )
                    rejected_violations |= violation_ids
                    rejected_pairs |= {(attempt_id, violation_id) for violation_id in violation_ids}
                elif attempt.get("outcome") == "PASSED":
                    if violation_ids:
                        errors.append(
                            f"E_CLEANUP_VIOLATION_MISMATCH {attempt_id}: PASSED attempt cannot retain violations"
                        )
                else:
                    errors.append(
                        f"E_CLEANUP_VIOLATION_MISMATCH {attempt_id}: unknown cleanup outcome"
                    )
            corrected_violations: set[str] = set()
            for correction in corrections:
                if not isinstance(correction, dict):
                    errors.append("E_CLEANUP_VIOLATION_MISMATCH state_cleanup: correction must be an object")
                    continue
                violation_id = str(correction.get("violation_id", ""))
                rejected_attempt_id = str(correction.get("rejected_attempt_id", ""))
                verified_attempt_id = str(correction.get("verified_by_attempt_id", ""))
                rejected_attempt = cleanup_attempt_by_id.get(rejected_attempt_id)
                verified_attempt = cleanup_attempt_by_id.get(verified_attempt_id)
                if (rejected_attempt_id, violation_id) not in rejected_pairs:
                    errors.append(
                        f"E_CLEANUP_VIOLATION_MISMATCH {correction.get('correction_id', '<correction>')}: "
                        "correction violation does not belong to its rejected attempt"
                    )
                if violation_id in corrected_violations:
                    errors.append(
                        f"E_CLEANUP_VIOLATION_MISMATCH {correction.get('correction_id', '<correction>')}: "
                        "each stable violation ID may have only one correction record"
                    )
                rejected_sequence = rejected_attempt.get("sequence") if rejected_attempt else None
                verified_sequence = verified_attempt.get("sequence") if verified_attempt else None
                if (
                    not isinstance(rejected_sequence, int)
                    or not isinstance(verified_sequence, int)
                    or verified_sequence <= rejected_sequence
                    or verified_attempt.get("outcome") != "PASSED"
                ):
                    errors.append(
                        f"E_CLEANUP_VIOLATION_MISMATCH {correction.get('correction_id', '<correction>')}: "
                        "correction must be closed by a later PASSED attempt"
                    )
                corrected_violations.add(violation_id)
            unresolved_violations = set(map(str, as_list(cleanup.get("unresolved_violation_ids"))))
            if corrected_violations & unresolved_violations:
                errors.append(
                    "E_CLEANUP_VIOLATION_MISMATCH state_cleanup: corrected and unresolved violation sets overlap"
                )
            if rejected_violations != corrected_violations | unresolved_violations:
                errors.append(
                    "E_CLEANUP_VIOLATION_MISMATCH state_cleanup: rejected violations must equal corrected "
                    "plus unresolved identities"
                )
            final_cleanup_attempt_id = str(cleanup.get("final_validation_attempt_id", ""))
            final_attempt = cleanup_attempt_by_id.get(final_cleanup_attempt_id)
            last_attempt = ordered_attempts[-1] if ordered_attempts else None
            if (
                not final_attempt
                or final_attempt is not last_attempt
                or final_attempt.get("outcome") != "PASSED"
                or unresolved_violations
            ):
                errors.append(
                    "E_CLEANUP_VIOLATION_MISMATCH state_cleanup: final attempt must be the last PASSED "
                    "attempt with no unresolved violations"
                )
            elif str(final_attempt.get("subject_digest", "")).lower() != state_subject_digest(state):
                errors.append(
                    "E_CLEANUP_SUBJECT_DIGEST state_cleanup: final attempt digest does not match current subject"
                )

        if workflow.get("spec_status") == "TEXT_SPEC_COMPLETE":
            errors.append(
                "E_SPEC_PROJECT_OVERCLAIM workflow_status: Alpha.7 uses scoped completion records; "
                "project-level TEXT_SPEC_COMPLETE is forbidden"
            )
        common_exclusions = {
            "MEDIA_EXECUTION", "MEDIA_OBSERVATION", "MEDIA_QA", "PUBLICATION", "LEARNING"
        }
        review_exclusions = {
            "PROVIDER_COMPILATION", "REAL_INPUT_AVAILABILITY", "GENERATION_READINESS"
        }
        for completion in spec_completion_records:
            if not isinstance(completion, dict):
                errors.append("E_SPEC_SCOPE_OVERCLAIM spec completion record must be an object")
                continue
            completion_id = str(completion.get("completion_id", "<completion>"))
            scope_type = completion.get("scope_type")
            scope_ids = set(map(str, as_list(completion.get("scope_ids"))))
            exclusions = set(map(str, as_list(completion.get("does_not_claim"))))
            if not common_exclusions <= exclusions:
                errors.append(
                    f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: completion must exclude downstream real-work states"
                )
            if scope_type in {
                "REVIEW_PACKAGE_ARTIFACT", "MASTER_PROMPT_PACKAGE",
                "PROVIDER_NEUTRAL_DRAFT_PROMPT_PACKAGE",
                "TRANSFORM_PLAN_PACKAGE", "NEUTRAL_EXECUTION_PROMPT_PACKAGE",
            } and not review_exclusions <= exclusions:
                errors.append(
                    f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: review/source completion needs provider, input, "
                    "and readiness exclusions"
                )
            if completion.get("open_blocking_issue_ids"):
                errors.append(
                    f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: completion cannot retain blocking issues"
                )
            if set(map(str, as_list(completion.get("protected_unknown_ids")))) - set(unknown_by_id):
                errors.append(f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: unknown protected-unknown IDs")
            if str(completion.get("validation_attempt_id")) != str(final_cleanup_attempt_id):
                errors.append(
                    f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: completion must bind the final PASSED validation attempt"
                )

            if scope_type in {"REVIEW_PACKAGE_ARTIFACT", "STORY_ARTIFACT", "RELEASE_SPEC_ARTIFACT"}:
                resolved = artifact_by_id
                expected_prompt_layer = None
            elif scope_type == "ASSET_REGISTRY_SPEC":
                resolved = asset_by_id
                expected_prompt_layer = None
            elif scope_type == "SHOT_PLAN":
                resolved = shot_plan_by_id
                expected_prompt_layer = None
            elif scope_type == "MASTER_PROMPT_PACKAGE":
                resolved = master_prompt_by_id
                expected_prompt_layer = "PROVIDER_NEUTRAL_MASTER"
            elif scope_type == "PROVIDER_NEUTRAL_DRAFT_PROMPT_PACKAGE":
                resolved = neutral_draft_by_id
                expected_prompt_layer = "PROVIDER_NEUTRAL_DRAFT"
                if four_layer_prompt_contract:
                    errors.append(
                        f"E_LEGACY_PROMPT_LAYER_READ_ONLY {completion_id}: current completion "
                        "cannot use legacy DRAFT scope"
                    )
            elif scope_type == "TRANSFORM_PLAN_PACKAGE":
                resolved = transform_plan_by_id
                expected_prompt_layer = "TRANSFORM_PLAN"
            elif scope_type == "NEUTRAL_EXECUTION_PROMPT_PACKAGE":
                resolved = neutral_execution_prompt_by_id
                expected_prompt_layer = "NEUTRAL_EXECUTION_PROMPT"
            elif scope_type == "PROVIDER_COMPILED_PROMPT_PACKAGE":
                resolved = prompt_by_id
                expected_prompt_layer = "PROVIDER_COMPILED"
            else:
                resolved = {}
                expected_prompt_layer = None
                errors.append(f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: unknown scope_type {scope_type!r}")
            if not scope_ids or scope_ids - set(resolved):
                errors.append(
                    f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: unresolved completion scope IDs "
                    f"{sorted(scope_ids - set(resolved))}"
                )
            for scope_id in scope_ids & set(resolved):
                scoped_record = resolved[scope_id]
                scoped_version_field = (
                    "version"
                    if scope_type
                    in {"REVIEW_PACKAGE_ARTIFACT", "STORY_ARTIFACT", "RELEASE_SPEC_ARTIFACT"}
                    else "source_spec_version"
                )
                if str(scoped_record.get(scoped_version_field)) != str(
                    completion.get("source_spec_version")
                ):
                    errors.append(
                        f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: {scope_id} source spec version mismatch"
                    )
                if expected_prompt_layer and scoped_record.get("prompt_layer") != expected_prompt_layer:
                    errors.append(
                        f"E_SPEC_SCOPE_OVERCLAIM {completion_id}: {scope_id} has the wrong prompt layer"
                    )
            artifact_scope = scope_type in {
                "REVIEW_PACKAGE_ARTIFACT", "STORY_ARTIFACT", "RELEASE_SPEC_ARTIFACT"
            }
            if artifact_scope:
                completion_hash = completion.get("content_sha256")
                scoped_hashes = {
                    str(artifact_by_id[scope_id].get("content_locator", {}).get("sha256", "")).lower()
                    for scope_id in scope_ids & set(artifact_by_id)
                    if isinstance(artifact_by_id[scope_id].get("content_locator"), dict)
                }
                if (
                    len(scope_ids) != 1
                    or not nonempty(completion_hash)
                    or scoped_hashes != {str(completion_hash).lower()}
                ):
                    errors.append(
                        f"E_SPEC_ARTIFACT_HASH_MISMATCH {completion_id}: artifact completion must bind "
                        "one exact content hash"
                    )
            elif completion.get("content_sha256") is not None:
                errors.append(
                    f"E_SPEC_ARTIFACT_HASH_MISMATCH {completion_id}: non-artifact completion cannot carry content hash"
                )
        for artifact in artifacts:
            if not isinstance(artifact, dict) or artifact.get("status") != "TEXT_SPEC_COMPLETE":
                continue
            artifact_id = str(artifact.get("id"))
            matches = [
                completion
                for completion in spec_completion_records
                if isinstance(completion, dict)
                and artifact_id in set(map(str, as_list(completion.get("scope_ids"))))
                and completion.get("scope_type")
                in {"REVIEW_PACKAGE_ARTIFACT", "STORY_ARTIFACT", "RELEASE_SPEC_ARTIFACT"}
            ]
            if len(matches) != 1:
                errors.append(
                    f"E_SPEC_SCOPE_OVERCLAIM {artifact_id}: TEXT_SPEC_COMPLETE requires exactly one scoped completion record"
                )

        output_profile = state.get("output_complexity_profile")
        if isinstance(output_profile, dict):
            primary_ids = set(map(str, as_list(output_profile.get("primary_artifact_ids"))))
            appendix_ids = set(map(str, as_list(output_profile.get("appendix_artifact_ids"))))
            if output_profile.get("source") == "USER_EXPLICIT" and not nonempty(
                output_profile.get("user_quote")
            ):
                errors.append("E_OUTPUT_PRIMARY_MISSING output profile: explicit choice requires user_quote")
            if primary_ids & appendix_ids or (primary_ids | appendix_ids) - set(artifact_by_id):
                errors.append(
                    "E_OUTPUT_PRIMARY_MISSING output profile: primary/appendix must be disjoint resolved artifacts"
                )
            if not primary_ids or any(
                artifact_by_id.get(artifact_id, {}).get("artifact_class") == "BENCHMARK_ONLY"
                for artifact_id in primary_ids
            ):
                errors.append(
                    "E_OUTPUT_PRIMARY_MISSING output profile: ordinary users require a non-benchmark primary artifact"
                )
            if (
                output_profile.get("tier") == "CREATOR_SIMPLE"
                and output_profile.get("inline_machine_detail") == "FULL"
            ):
                errors.append(
                    "E_OUTPUT_COMPLEXITY_CONFLICT output profile: CREATOR_SIMPLE cannot inline full machine detail"
                )

        required_scope_fields = {
            "artifact_ids", "asset_ids", "release_package_ids", "provider_registry_ids", "pilot_ids",
            "shot_plan_ids", "format_variant_ids", "task_types", "prompt_ids", "observation_ids", "artifact_versions",
            "task_scope", "format_scope", "version_scope",
        }
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            gate_id = str(gate.get("gate_id", "<gate>"))
            binding = gate.get("scope_bindings")
            if not isinstance(binding, dict):
                continue
            missing_scope_fields = required_scope_fields - set(binding)
            if missing_scope_fields:
                errors.append(
                    f"E_GATE_SCOPE_MISSING {gate_id}: missing typed scope fields {sorted(missing_scope_fields)}"
                )
            artifact_ids = scope_list(binding, "artifact_ids")
            scoped_asset_ids = scope_list(binding, "asset_ids")
            package_ids = scope_list(binding, "release_package_ids")
            provider_ids = scope_list(binding, "provider_registry_ids")
            pilot_ids = scope_list(binding, "pilot_ids")
            plan_ids = scope_list(binding, "shot_plan_ids")
            format_ids = scope_list(binding, "format_variant_ids")
            task_types = scope_list(binding, "task_types")
            prompt_ids = scope_list(binding, "prompt_ids")
            scoped_observation_ids = scope_list(binding, "observation_ids")
            artifact_versions = versioned_refs(binding.get("artifact_versions"))
            linked_publication_ids = set(map(str, as_list(gate.get("publication_ids"))))
            linked_learning_ids = set(map(str, as_list(gate.get("learning_ids"))))

            resolvers = (
                (artifact_ids, artifact_by_id, "artifact"),
                (scoped_asset_ids, asset_by_id, "asset"),
                (package_ids, artifact_by_id, "release package"),
                (provider_ids, provider_by_id, "provider"),
                (pilot_ids, pilot_by_id, "pilot"),
                (plan_ids, shot_plan_by_id, "shot plan"),
                (format_ids, format_by_id, "format variant"),
                (prompt_ids, prompt_by_id, "compiled prompt"),
                (scoped_observation_ids, observation_by_id, "observation"),
            )
            for scoped_ids, resolver, label in resolvers:
                missing_ids = scoped_ids - set(resolver)
                if missing_ids:
                    errors.append(
                        f"E_GATE_SCOPE_UNRESOLVED {gate_id}: unknown {label} IDs {sorted(missing_ids)}"
                    )
            for artifact_id, version in artifact_versions:
                artifact = artifact_by_id.get(artifact_id)
                if not artifact or str(artifact.get("version")) != version:
                    errors.append(
                        f"E_GATE_SCOPE_UNRESOLVED {gate_id}: unknown artifact/version {artifact_id}@{version}"
                    )
            if (artifact_ids | package_ids) - {artifact_id for artifact_id, _version in artifact_versions}:
                errors.append(
                    f"E_GATE_SCOPE_UNRESOLVED {gate_id}: every scoped artifact/package needs an exact version tuple"
                )
            for package_id in package_ids & set(artifact_by_id):
                if artifact_by_id[package_id].get("artifact_class") not in {"PACKAGE", "RELEASE"}:
                    errors.append(
                        f"E_GATE_SCOPE_UNRESOLVED {gate_id}: {package_id} is not a release package"
                    )
            if linked_publication_ids - set(publication_by_id):
                errors.append(
                    f"E_GATE_SCOPE_UNRESOLVED {gate_id}: unknown publication IDs "
                    f"{sorted(linked_publication_ids - set(publication_by_id))}"
                )
            if linked_learning_ids - set(learning_by_id):
                errors.append(
                    f"E_GATE_SCOPE_UNRESOLVED {gate_id}: unknown learning IDs "
                    f"{sorted(linked_learning_ids - set(learning_by_id))}"
                )
            for prompt_id in prompt_ids & set(prompt_by_id):
                if prompt_by_id[prompt_id].get("prompt_layer") != "PROVIDER_COMPILED":
                    errors.append(
                        f"E_PROVIDER_PROMPT_UNBOUND {gate_id}: only PROVIDER_COMPILED prompts may enter Gate scope"
                    )

            scoped_prompt_assets: set[str] = set()
            scoped_prompt_plans: set[str] = set()
            scoped_prompt_providers: set[str] = set()
            scoped_prompt_versions: set[str] = set()
            scoped_prompt_media: set[str] = set()
            scoped_prompt_targets: set[tuple[str, str, str, str]] = set()
            for prompt_id in prompt_ids & set(prompt_by_id):
                prompt = prompt_by_id[prompt_id]
                target_key = prompt_target_key(prompt)
                target_type, target_id, source_version, _generation_role = target_key
                scoped_prompt_targets.add(target_key)
                scoped_prompt_versions.add(source_version)
                scoped_prompt_media.add(str(prompt.get("generation_medium", "")))
                scoped_prompt_assets |= set(map(str, as_list(prompt.get("asset_ids"))))
                scoped_prompt_providers.add(str(prompt.get("provider_registry_id")))
                if target_type == "ASSET":
                    scoped_prompt_assets.add(target_id)
                elif target_type == "SHOT" and target_id in shot_plan_for_shot:
                    scoped_prompt_plans.add(shot_plan_for_shot[target_id])

            applicable = gate.get("outcome") != "NOT_APPLICABLE"
            gate_type = gate.get("gate_type")
            missing_minimum = False
            if applicable and gate_type == "GENERATION_READINESS_GATE":
                missing_minimum = not (
                    provider_ids
                    and task_types
                    and prompt_ids
                    and nonempty(binding.get("task_scope"))
                    and nonempty(binding.get("version_scope"))
                )
                if prompt_ids:
                    if scoped_asset_ids != scoped_prompt_assets:
                        errors.append(
                            f"E_GATE_SCOPE_MISSING {gate_id}: asset_ids must exactly cover scoped Prompt targets"
                        )
                    if plan_ids != scoped_prompt_plans:
                        errors.append(
                            f"E_GATE_SCOPE_MISSING {gate_id}: shot_plan_ids must exactly cover scoped SHOT targets"
                        )
                    if provider_ids != scoped_prompt_providers:
                        errors.append(
                            f"E_GATE_SCOPE_MISSING {gate_id}: provider IDs must exactly cover scoped Prompts"
                        )
                    if scoped_prompt_versions != {str(binding.get("version_scope", ""))}:
                        errors.append(
                            f"E_GATE_SCOPE_MISSING {gate_id}: version_scope must exactly match scoped Prompts"
                        )
                    if "IMAGE" in scoped_prompt_media and "IMAGE_GENERATION" not in task_types:
                        errors.append(
                            f"E_GATE_SCOPE_MISSING {gate_id}: IMAGE Prompt targets require IMAGE_GENERATION"
                        )
                    if "VIDEO" in scoped_prompt_media and not task_types.intersection(
                        {"VIDEO_GENERATION", "IMAGE_TO_VIDEO", "VIDEO_TO_VIDEO"}
                    ):
                        errors.append(
                            f"E_GATE_SCOPE_MISSING {gate_id}: VIDEO Prompt targets require a video generation task"
                        )
                if gate.get("readiness_scope") == "BATCH_PRODUCTION":
                    missing_minimum = missing_minimum or not (
                        pilot_ids and plan_ids and format_ids and nonempty(binding.get("format_scope"))
                    )
            elif applicable and gate_type == "ASSET_GATE":
                missing_minimum = not (artifact_ids and artifact_versions and scoped_observation_ids)
            elif applicable and gate_type in {"SHOT_GATE", "SEQUENCE_CONTINUITY_GATE"}:
                missing_minimum = not (
                    artifact_ids and artifact_versions and plan_ids and scoped_observation_ids
                )
            elif applicable and gate_type == "FINAL_ARTIFACT_GATE":
                missing_minimum = not (artifact_ids and artifact_versions and scoped_observation_ids)
            elif applicable and gate_type == "RELEASE_READINESS_GATE":
                missing_minimum = not (
                    artifact_ids
                    and package_ids
                    and artifact_versions
                    and nonempty(binding.get("format_scope"))
                )
            elif applicable and gate_type == "PUBLICATION_EVIDENCE_GATE":
                missing_minimum = not linked_publication_ids
            elif applicable and gate_type == "LEARNING_GATE":
                missing_minimum = not (linked_publication_ids and linked_learning_ids)
            if missing_minimum:
                errors.append(
                    f"E_GATE_SCOPE_MISSING {gate_id}: {gate_type} lacks its minimum typed scope"
                )
            if (
                gate_type == "GENERATION_READINESS_GATE"
                and gate.get("outcome") in {"PASSED", "ACCEPTED_WITH_DEBT"}
                and prompt_ids - quality_pass_prompt_ids
            ):
                errors.append(
                    f"E_PROMPT_QUALITY_NOT_READY {gate_id}: readiness Gate cannot pass non-PASS "
                    f"quality Prompts {sorted(prompt_ids - quality_pass_prompt_ids)}"
                )
            if (
                gate_type == "GENERATION_READINESS_GATE"
                and gate.get("outcome") in {"PASSED", "ACCEPTED_WITH_DEBT"}
                and prompt_ids.intersection(manual_copy_prompt_ids)
            ):
                errors.append(
                    f"E_TEXT_SPEC_ONLY_EXECUTION_FORBIDDEN {gate_id}: manual-copy TEXT_SPEC_ONLY "
                    "Prompts cannot unlock Generation Readiness "
                    f"{sorted(prompt_ids.intersection(manual_copy_prompt_ids))}"
                )

            gate_evidence_ids = set(map(str, as_list(gate.get("evidence_ids"))))
            if applicable and gate_evidence_ids and not any(
                evidence_covers_gate_scope(evidence_by_id.get(evidence_id, {}), binding)
                for evidence_id in gate_evidence_ids
            ):
                errors.append(
                    f"E_GATE_EVIDENCE_SCOPE {gate_id}: no Gate evidence covers its complete typed scope"
                )
            if linked_publication_ids and not any(
                linked_publication_ids
                <= scope_list(evidence_scope(evidence_by_id.get(evidence_id, {})), "publication_ids")
                for evidence_id in gate_evidence_ids
            ):
                errors.append(
                    f"E_GATE_EVIDENCE_SCOPE {gate_id}: evidence does not cover publication scope"
                )
            if linked_learning_ids and not any(
                linked_learning_ids
                <= scope_list(evidence_scope(evidence_by_id.get(evidence_id, {})), "learning_ids")
                for evidence_id in gate_evidence_ids
            ):
                errors.append(f"E_GATE_EVIDENCE_SCOPE {gate_id}: evidence does not cover learning scope")

            if (
                gate_type == "GENERATION_READINESS_GATE"
                and gate.get("readiness_scope") == "BATCH_PRODUCTION"
                and gate.get("outcome") in {"PASSED", "ACCEPTED_WITH_DEBT"}
            ):
                sampled_prompt_ids: set[str] = set()
                sampled_provider_ids: set[str] = set()
                sampled_format_ids: set[str] = set()
                sampled_task_types: set[str] = set()
                eligible_pilot_found = False
                for pilot_id in pilot_ids:
                    pilot = pilot_by_id.get(pilot_id, {})
                    pilot_prompt_ids = set(map(str, as_list(pilot.get("prompt_ids"))))
                    pilot_asset_ids = set(map(str, as_list(pilot.get("asset_ids"))))
                    pilot_plan_ids = set(map(str, as_list(pilot.get("shot_plan_ids"))))
                    pilot_provider_ids = set(map(str, as_list(pilot.get("provider_registry_ids"))))
                    pilot_formats = set(map(str, as_list(pilot.get("format_variant_ids"))))
                    pilot_task_types = set(map(str, as_list(pilot.get("task_types"))))
                    if (
                        pilot.get("status") == "PASSED"
                        and bool(pilot_prompt_ids)
                        and pilot_prompt_ids <= prompt_ids
                        and pilot_asset_ids <= scoped_asset_ids
                        and pilot_plan_ids <= plan_ids
                        and pilot_provider_ids <= provider_ids
                        and str(binding.get("version_scope")) == str(pilot.get("source_spec_version"))
                        and pilot_task_types <= task_types
                        and pilot_formats <= format_ids
                    ):
                        eligible_pilot_found = True
                        sampled_prompt_ids |= pilot_prompt_ids
                        sampled_provider_ids |= pilot_provider_ids
                        sampled_format_ids |= pilot_formats
                        sampled_task_types |= pilot_task_types

                def prompt_family(prompt_id: str) -> tuple[str, str, str, str, str]:
                    prompt = prompt_by_id.get(prompt_id, {})
                    quality = quality_for_prompt_id.get(prompt_id, {})
                    adapter_mode = next(
                        (
                            str(row.get("adapter_mode", ""))
                            for row in as_list(quality.get("adapter_integrity"))
                            if isinstance(row, dict)
                            and str(row.get("provider_prompt_id")) == prompt_id
                        ),
                        "",
                    )
                    return (
                        str(prompt.get("provider_registry_id", "")),
                        str(prompt.get("provider_snapshot_id", "")),
                        str(prompt.get("generation_medium", "")),
                        str(prompt.get("generation_role", "")),
                        f"{quality.get('prompt_quality_profile', '')}/{adapter_mode}",
                    )

                def prompt_risk_families(prompt_id: str) -> set[str]:
                    quality = quality_for_prompt_id.get(prompt_id, {})
                    return {
                        str(beat.get("high_risk_event"))
                        for beat in as_list(quality.get("director_beats"))
                        if isinstance(beat, dict) and beat.get("high_risk_event") != "NONE"
                    }

                required_families = {prompt_family(prompt_id) for prompt_id in prompt_ids}
                sampled_families = {prompt_family(prompt_id) for prompt_id in sampled_prompt_ids}
                required_risks = set().union(
                    *(prompt_risk_families(prompt_id) for prompt_id in prompt_ids)
                ) if prompt_ids else set()
                sampled_risks = set().union(
                    *(prompt_risk_families(prompt_id) for prompt_id in sampled_prompt_ids)
                ) if sampled_prompt_ids else set()
                high_risk_prompt_ids = {
                    prompt_id for prompt_id in prompt_ids if prompt_risk_families(prompt_id)
                }
                ordinary_prompt_ids = prompt_ids - high_risk_prompt_ids
                batch_sample_reviews = {
                    prompt_id for prompt_id in ordinary_prompt_ids
                    if prompt_id in review_pass_prompt_ids
                    and review_scope_by_prompt_id.get(prompt_id) == "BATCH_SAMPLE"
                }
                if (
                    not eligible_pilot_found
                    or sampled_provider_ids != provider_ids
                    or sampled_format_ids != format_ids
                    or sampled_task_types != task_types
                    or required_families - sampled_families
                    or required_risks - sampled_risks
                    or sampled_prompt_ids - review_pass_prompt_ids
                    or (ordinary_prompt_ids and not batch_sample_reviews)
                ):
                    errors.append(
                        f"E_PILOT_SCOPE_MISMATCH {gate_id}: representative Pilot sample must be a "
                        "non-empty batch subset covering provider/snapshot, format, task, medium/role, "
                        "quality/adapter, and high-risk families; one ordinary BATCH_SAMPLE review is required"
                    )

        for publication in publication_records:
            if not isinstance(publication, dict):
                continue
            publication_id = str(publication.get("publication_id", "<publication>"))
            release_gate = gate_by_id.get(str(publication.get("release_readiness_gate_id")), {})
            binding = release_gate.get("scope_bindings")
            if not isinstance(binding, dict):
                errors.append(
                    f"E_RELEASE_SCOPE_MISMATCH {publication_id}: release Gate has no typed scope"
                )
                continue
            artifact_id = str(publication.get("artifact_id"))
            artifact_version = str(publication.get("artifact_version"))
            package_id = str(publication.get("release_package_id"))
            package = artifact_by_id.get(package_id, {})
            bound_versions = versioned_refs(binding.get("artifact_versions"))
            if (
                artifact_id not in scope_list(binding, "artifact_ids")
                or package_id not in scope_list(binding, "release_package_ids")
                or (artifact_id, artifact_version) not in bound_versions
                or (package_id, str(package.get("version"))) not in bound_versions
            ):
                errors.append(
                    f"E_RELEASE_SCOPE_MISMATCH {publication_id}: publication artifact/package/version "
                    "is outside its release-readiness Gate"
                )

        status_basis = workflow.get("status_basis")
        if not isinstance(status_basis, dict):
            errors.append("E_STATUS_BASIS_MISSING workflow_status: Alpha.7 requires status_basis")
            status_basis = {}
        execution_basis_ids = scope_list(status_basis, "execution_artifact_ids")
        observation_basis_ids = scope_list(status_basis, "observation_ids")
        qa_basis_ids = scope_list(status_basis, "qa_gate_ids")
        release_basis_ids = scope_list(status_basis, "release_gate_ids")
        publication_basis_ids = scope_list(status_basis, "publication_ids")
        learning_basis_ids = scope_list(status_basis, "learning_ids")
        for basis_ids, resolver, label in (
            (execution_basis_ids, artifact_by_id, "execution artifact"),
            (observation_basis_ids, observation_by_id, "observation"),
            (qa_basis_ids, gate_by_id, "QA Gate"),
            (release_basis_ids, gate_by_id, "release Gate"),
            (publication_basis_ids, publication_by_id, "publication"),
            (learning_basis_ids, learning_by_id, "learning"),
        ):
            missing_basis_ids = basis_ids - set(resolver)
            if missing_basis_ids:
                errors.append(
                    f"E_STATUS_BASIS_MISSING workflow_status: unknown {label} IDs {sorted(missing_basis_ids)}"
                )

        if workflow.get("execution_status") == "EXECUTED_SUCCEEDED":
            valid_execution_artifacts = {
                artifact_id
                for artifact_id in execution_basis_ids
                if artifact_by_id.get(artifact_id, {}).get("real_artifact_present") is True
                and artifact_by_id.get(artifact_id, {}).get("artifact_class")
                not in {"TEXT_SPEC", "BENCHMARK_ONLY"}
                and artifact_by_id.get(artifact_id, {}).get("execution_mode") == "REAL"
                and isinstance(artifact_by_id.get(artifact_id, {}).get("content_locator"), dict)
                and bool(as_list(artifact_by_id.get(artifact_id, {}).get("evidence_ids")))
            }
            if not execution_basis_ids or valid_execution_artifacts != execution_basis_ids:
                errors.append(
                    "E_EXECUTION_BASIS_MISSING workflow_status: EXECUTED_SUCCEEDED requires only "
                    "versioned real non-text execution artifacts"
                )
        elif workflow.get("execution_status") in {"NOT_EXECUTED", "SIMULATED_ONLY"} and execution_basis_ids:
            errors.append(
                "E_EXECUTION_BASIS_MISSING workflow_status: unexecuted/simulated state cannot cite real execution basis"
            )
        if workflow.get("execution_status") in {"EXECUTING", "EXECUTED_FAILED"}:
            expected_receipt_result = (
                "RUNNING" if workflow.get("execution_status") == "EXECUTING" else "FAILED"
            )
            matching_production_receipts = [
                receipt
                for receipt in receipt_by_id.values()
                if receipt.get("result") == expected_receipt_result
                and receipt.get("execution_mode") == "REAL"
                and effective_execution_domain(
                    receipt,
                    task_by_id.get(str(receipt.get("task_id")), {}),
                )
                == "PRODUCTION_MEDIA"
            ]
            if not matching_production_receipts:
                errors.append(
                    "E_EXECUTION_BASIS_MISSING workflow_status: "
                    f"{workflow.get('execution_status')} requires a real "
                    f"{expected_receipt_result} production-media receipt"
                )

        if workflow.get("observation_status") == "OBSERVED":
            valid_observations = {
                observation_id
                for observation_id in observation_basis_ids
                if observation_by_id.get(observation_id, {}).get("media_accessible") is True
                and observation_by_id.get(observation_id, {}).get("basis")
                in {"DIRECT_MEDIA_ACCESS", "MEASURED_DATA"}
                and str(observation_by_id.get(observation_id, {}).get("artifact_id"))
                in execution_basis_ids
            }
            if not observation_basis_ids or valid_observations != observation_basis_ids:
                errors.append(
                    "E_OBSERVATION_BASIS workflow_status: OBSERVED requires accessible observations "
                    "of its execution artifacts"
                )

        if workflow.get("qa_status") in {"QA_PASSED", "QA_ACCEPTED_WITH_DEBT"}:
            valid_qa_gates: set[str] = set()
            for gate_id in qa_basis_ids:
                gate = gate_by_id.get(gate_id, {})
                binding = gate.get("scope_bindings")
                if not isinstance(binding, dict):
                    continue
                if (
                    gate.get("gate_type") in MEDIA_GATE_TYPES
                    and gate.get("evaluation_status") == "EXECUTED"
                    and gate.get("outcome")
                    in (
                        {"PASSED"}
                        if workflow.get("qa_status") == "QA_PASSED"
                        else {"PASSED", "ACCEPTED_WITH_DEBT"}
                    )
                    and execution_basis_ids <= scope_list(binding, "artifact_ids")
                    and observation_basis_ids <= scope_list(binding, "observation_ids")
                ):
                    valid_qa_gates.add(gate_id)
            if (
                not qa_basis_ids
                or valid_qa_gates != qa_basis_ids
                or not observation_basis_ids
            ):
                errors.append(
                    "E_QA_BASIS_MISSING workflow_status: passed QA requires passed typed media Gates "
                    "covering the execution artifacts and observations"
                )

        if workflow.get("learning_status") in {
            "DATA_AVAILABLE", "LEARNING_DRAFT", "LEARNING_VALIDATED"
        }:
            valid_learning_ids: set[str] = set()
            for learning_id in learning_basis_ids:
                learning = learning_by_id.get(learning_id, {})
                analytics_ids = set(map(str, as_list(learning.get("analytics_artifact_ids"))))
                real_data_evidence = set(map(str, as_list(learning.get("real_data_evidence_ids"))))
                if (
                    learning.get("status")
                    in {"DATA_AVAILABLE", "LEARNING_DRAFT", "LEARNING_VALIDATED"}
                    and analytics_ids
                    and real_data_evidence
                    and all(
                        artifact_by_id.get(artifact_id, {}).get("artifact_class") == "DATA"
                        and artifact_by_id.get(artifact_id, {}).get("real_artifact_present") is True
                        and bool(
                            real_data_evidence
                            & set(
                                map(
                                    str,
                                    as_list(artifact_by_id.get(artifact_id, {}).get("evidence_ids")),
                                )
                            )
                        )
                        for artifact_id in analytics_ids
                    )
                ):
                    valid_learning_ids.add(learning_id)
            if not learning_basis_ids or valid_learning_ids != learning_basis_ids:
                errors.append(
                    "E_LEARNING_DATA_BASIS workflow_status: data/learning state requires real DATA "
                    "artifacts and matching evidence"
                )

        if workflow.get("publication_status") in {"RELEASE_READY", "PUBLISH_PENDING", "PUBLISHED"}:
            valid_release_gate_ids = {
                gate_id
                for gate_id in release_basis_ids
                if gate_by_id.get(gate_id, {}).get("gate_type") == "RELEASE_READINESS_GATE"
                and gate_by_id.get(gate_id, {}).get("evaluation_status") == "EXECUTED"
                and gate_by_id.get(gate_id, {}).get("outcome") in {"PASSED", "ACCEPTED_WITH_DEBT"}
            }
            if not release_basis_ids or valid_release_gate_ids != release_basis_ids:
                errors.append(
                    "E_RELEASE_SCOPE_MISMATCH workflow_status: release/publication state requires passed release Gate basis"
                )
        if workflow.get("publication_status") == "PUBLISHED" and not publication_basis_ids:
            errors.append(
                "E_RELEASE_SCOPE_MISMATCH workflow_status: PUBLISHED requires publication basis IDs"
            )

        real_artifact_count = sum(
            1
            for artifact in artifacts
            if isinstance(artifact, dict) and artifact.get("real_artifact_present") is True
        )
        locked_decision_ids = {
            decision_id
            for decision_id, decision in decision_by_id.items()
            if decision.get("status") == "LOCKED"
        }
        for stage_result in as_list(state.get("stage_results")):
            if not isinstance(stage_result, dict):
                continue
            stage_name = str(stage_result.get("stage", "<stage>"))
            legacy_fields = {"completion_status", "gate", "evidence"} & set(stage_result)
            if legacy_fields:
                errors.append(
                    f"E_STAGE_LEGACY_FIELD {stage_name}: Alpha.7 Stage Result forbids {sorted(legacy_fields)}"
                )
            if stage_result.get("snapshot_kind") != "PROJECT_STATE_SNAPSHOT":
                errors.append(
                    f"E_STAGE_SNAPSHOT_KIND {stage_name}: Alpha.7 requires PROJECT_STATE_SNAPSHOT"
                )
            if stage_result.get("execution_mode") != state.get("execution_mode") or not _json_equal(
                stage_result.get("workflow_status"), workflow
            ):
                errors.append(
                    f"E_STAGE_STATUS_MISMATCH {stage_name}: Stage execution/workflow snapshot must equal project state"
                )
            if set(map(str, as_list(stage_result.get("terminal_markers")))) != terminal_markers:
                errors.append(
                    f"E_STAGE_TERMINAL_MISMATCH {stage_name}: Stage terminal markers must exactly equal project markers"
                )
            if stage_result.get("real_artifact_count") != real_artifact_count:
                errors.append(
                    f"E_STAGE_ARTIFACT_COUNT_MISMATCH {stage_name}: declared "
                    f"{stage_result.get('real_artifact_count')!r}, actual {real_artifact_count}"
                )
            stage_evidence_ids = set(map(str, as_list(stage_result.get("evidence_ids"))))
            stage_gate_ids = set(map(str, as_list(stage_result.get("gate_ids"))))
            if stage_evidence_ids - set(evidence_by_id):
                errors.append(f"E_STAGE_SNAPSHOT_ID {stage_name}: unresolved evidence IDs")
            if stage_gate_ids - set(gate_by_id) or any(
                gate_by_id.get(gate_id, {}).get("evaluation_status") != "EXECUTED"
                for gate_id in stage_gate_ids
            ):
                errors.append(f"E_STAGE_SNAPSHOT_ID {stage_name}: gate IDs must resolve to executed evaluations")
            if set(map(str, as_list(stage_result.get("locked_decision_ids")))) != locked_decision_ids:
                errors.append(f"E_STAGE_SNAPSHOT_ID {stage_name}: locked decisions are not a current snapshot")
            if set(map(str, as_list(stage_result.get("open_blocking_issue_ids")))) != open_blocking_ids:
                errors.append(f"E_STAGE_SNAPSHOT_ID {stage_name}: blocking issue IDs are not a current snapshot")

        # Alpha.7 integrated orchestration, external execution, and fourfold preflight.
        if isinstance(project_route, dict):
            route_id = str(project_route.get("route_id", "<route>"))
            route_sources = set(map(str, as_list(project_route.get("primary_source_artifact_ids"))))
            route_evidence = set(map(str, as_list(project_route.get("evidence_ids"))))
            if route_sources - set(artifact_by_id):
                errors.append(
                    f"E_ROUTE_SOURCE_UNKNOWN {route_id}: unknown source artifacts "
                    f"{sorted(route_sources - set(artifact_by_id))}"
                )
            if route_evidence - set(evidence_by_id):
                errors.append(f"E_ROUTE_EVIDENCE_UNKNOWN {route_id}: unresolved evidence IDs")
            route_decision_id = project_route.get("source_decision_id")
            if project_route.get("status") == "USER_APPROVED" and (
                str(route_decision_id) not in decision_by_id
                or decision_by_id.get(str(route_decision_id), {}).get("status")
                not in APPROVED_DECISION_STATUSES
            ):
                errors.append(
                    f"E_ROUTE_APPROVAL_MISSING {route_id}: USER_APPROVED route requires an approved decision"
                )
            if (
                project_route.get("content_truth_mode") in {"NONFICTION", "MIXED"}
                and project_route.get("source_fidelity_required") is not True
            ):
                errors.append(
                    f"E_SOURCE_FIDELITY_DISABLED {route_id}: non-fiction or mixed work requires source fidelity"
                )

        def checked_artifact_refs(value: Any, label: str) -> set[tuple[str, str]]:
            resolved: set[tuple[str, str]] = set()
            for item in as_list(value):
                if not isinstance(item, dict):
                    continue
                artifact_id = str(item.get("artifact_id"))
                version = str(item.get("version"))
                artifact = artifact_by_id.get(artifact_id)
                if not artifact:
                    errors.append(f"E_TASK_ARTIFACT_UNKNOWN {label}: unknown artifact {artifact_id}")
                    continue
                if str(artifact.get("version")) != version:
                    errors.append(
                        f"E_TASK_ARTIFACT_VERSION {label}: {artifact_id}@{version} does not match registry"
                    )
                    continue
                resolved.add((artifact_id, version))
            return resolved

        for task_id, task in task_by_id.items():
            dependencies = set(map(str, as_list(task.get("depends_on_task_ids"))))
            if task_id in dependencies:
                errors.append(f"E_TASK_DEPENDENCY_CYCLE {task_id}: task depends on itself")
            if dependencies - set(task_by_id):
                errors.append(
                    f"E_TASK_DEPENDENCY_UNKNOWN {task_id}: unknown tasks "
                    f"{sorted(dependencies - set(task_by_id))}"
                )
            input_refs = checked_artifact_refs(task.get("input_artifact_refs"), task_id)
            output_refs = checked_artifact_refs(task.get("output_artifact_refs"), task_id)
            required_decisions = set(map(str, as_list(task.get("required_decision_ids"))))
            missing_decisions = required_decisions - set(decision_by_id)
            if missing_decisions:
                errors.append(
                    f"E_TASK_DECISION_UNKNOWN {task_id}: unknown decisions {sorted(missing_decisions)}"
                )
            if task.get("status") in {
                "READY", "RUNNING", "EXECUTED_FAILED", "EXECUTED_SUCCEEDED",
            }:
                unapproved = {
                    decision_id
                    for decision_id in required_decisions
                    if decision_by_id.get(decision_id, {}).get("status")
                    not in APPROVED_DECISION_STATUSES
                }
                if unapproved:
                    errors.append(
                        f"E_TASK_DECISION_UNAPPROVED {task_id}: required decisions are not approved "
                        f"{sorted(unapproved)}"
                    )
            provider_ids = set(map(str, as_list(task.get("provider_registry_ids"))))
            master_ids = set(map(str, as_list(task.get("master_prompt_ids"))))
            draft_ids = set(map(str, as_list(task.get("provider_neutral_draft_ids"))))
            transform_plan_ids = set(map(str, as_list(task.get("transform_plan_ids"))))
            neutral_execution_prompt_ids = set(
                map(str, as_list(task.get("neutral_execution_prompt_ids")))
            )
            compiled_ids = set(map(str, as_list(task.get("provider_prompt_ids"))))
            task_shot_ids = set(map(str, as_list(task.get("shot_ids"))))
            generation_targets = [
                row for row in as_list(task.get("generation_targets")) if isinstance(row, dict)
            ]
            if provider_ids - set(provider_by_id):
                errors.append(f"E_TASK_PROVIDER_UNKNOWN {task_id}: unresolved provider IDs")
            if master_ids - set(master_prompt_by_id):
                errors.append(f"E_TASK_PROMPT_UNKNOWN {task_id}: unresolved MASTER Prompt IDs")
            if draft_ids - set(neutral_draft_by_id):
                errors.append(f"E_TASK_PROMPT_UNKNOWN {task_id}: unresolved neutral DRAFT Prompt IDs")
            if transform_plan_ids - set(transform_plan_by_id):
                errors.append(
                    f"E_TASK_PROMPT_UNKNOWN {task_id}: unresolved TRANSFORM_PLAN IDs"
                )
            if neutral_execution_prompt_ids - set(neutral_execution_prompt_by_id):
                errors.append(
                    f"E_TASK_PROMPT_UNKNOWN {task_id}: unresolved NEUTRAL_EXECUTION_PROMPT IDs"
                )
            if four_layer_prompt_contract:
                for field in ("transform_plan_ids", "neutral_execution_prompt_ids"):
                    if field not in task:
                        errors.append(
                            f"E_PROMPT_LAYER_CONTRACT {task_id}: four-layer task missing {field}"
                        )
                if draft_ids:
                    errors.append(
                        f"E_LEGACY_PROMPT_LAYER_READ_ONLY {task_id}: current task cannot bind legacy DRAFT IDs"
                    )
            if compiled_ids - set(prompt_by_id):
                errors.append(f"E_TASK_PROMPT_UNKNOWN {task_id}: unresolved compiled Prompt IDs")
            if current_quality_contract and task.get("task_type") in GENERATION_TASK_TYPES:
                target_keys: list[tuple[str, str, str, str]] = []
                target_prompt_ids: set[str] = set()
                target_mediums: set[str] = set()
                derived_shot_ids: set[str] = set()
                for target in generation_targets:
                    target_key = (
                        str(target.get("target_type", "")),
                        str(target.get("target_id", "")),
                        str(target.get("source_spec_version", "")),
                        str(target.get("generation_role", "")),
                    )
                    target_keys.append(target_key)
                    target_ids = set(map(str, as_list(target.get("provider_prompt_ids"))))
                    target_prompt_ids |= target_ids
                    target_medium = str(target.get("generation_medium", ""))
                    target_mediums.add(target_medium)
                    if target_key[0] == "SHOT":
                        derived_shot_ids.add(target_key[1])
                    if not generation_role_matches_medium(target_key[3], target_medium):
                        errors.append(
                            f"E_PROMPT_MEDIUM_MISMATCH {task_id}: generation target role/medium conflict"
                        )
                    for prompt_id in target_ids & set(prompt_by_id):
                        prompt = prompt_by_id[prompt_id]
                        if prompt_target_key(prompt) != target_key or str(
                            prompt.get("generation_medium", "")
                        ) != target_medium:
                            errors.append(
                                f"E_TASK_SHOT_SCOPE_MISMATCH {task_id}: generation target disagrees with {prompt_id}"
                            )
                if len(target_keys) != len(set(target_keys)):
                    errors.append(f"E_TASK_SHOT_SCOPE_MISMATCH {task_id}: duplicate generation target")
                if target_prompt_ids != compiled_ids:
                    errors.append(
                        f"E_TASK_SHOT_SCOPE_MISMATCH {task_id}: generation_targets Prompt union must exactly "
                        "equal provider_prompt_ids"
                    )
                if task_shot_ids != derived_shot_ids:
                    errors.append(
                        f"E_TASK_SHOT_SCOPE_MISMATCH {task_id}: shot_ids must be the exact SHOT-target projection"
                    )
                prompt_mediums = {
                    str(quality_for_prompt_id.get(prompt_id, {}).get("generation_medium", ""))
                    for prompt_id in compiled_ids & set(prompt_by_id)
                }
                expected_medium = (
                    "IMAGE" if task.get("task_type") == "IMAGE_GENERATION" else "VIDEO"
                )
                if prompt_mediums != {expected_medium} or target_mediums != {expected_medium}:
                    errors.append(
                        f"E_PROMPT_MEDIUM_MISMATCH {task_id}: {task.get('task_type')} requires "
                        f"only {expected_medium} quality records; got {sorted(prompt_mediums)}"
                    )
            if (
                task.get("task_type") in GENERATION_TASK_TYPES
                and task.get("status") in EXECUTABLE_GENERATION_STATUSES
            ):
                text_spec_only_ids = compiled_ids.intersection(manual_copy_prompt_ids)
                if text_spec_only_ids:
                    errors.append(
                        f"E_TEXT_SPEC_ONLY_EXECUTION_FORBIDDEN {task_id}: READY or executing "
                        "generation cannot bind manual-copy TEXT_SPEC_ONLY Prompts "
                        f"{sorted(text_spec_only_ids)}"
                    )
                # The structured execution object is the exact shot set bound by
                # the task's compiled Prompts. task_scope is descriptive text and
                # must never grant or widen execution authorization.
                compiled_shot_ids = {
                    str(prompt_by_id[prompt_id].get("target_id"))
                    for prompt_id in compiled_ids & set(prompt_by_id)
                    if prompt_by_id[prompt_id].get("target_type") == "SHOT"
                }
                if not current_quality_contract and not task_shot_ids:
                    errors.append(
                        f"E_TASK_SHOT_SCOPE_MISSING {task_id}: executable generation "
                        "requires non-empty structured shot_ids"
                    )
                if task_shot_ids != compiled_shot_ids:
                    errors.append(
                        f"E_TASK_SHOT_SCOPE_MISMATCH {task_id}: shot_ids must exactly match "
                        "the shot IDs bound by provider_prompt_ids; "
                        f"declared={sorted(task_shot_ids)}, compiled={sorted(compiled_shot_ids)}"
                    )
                if compiled_ids - quality_pass_prompt_ids:
                    errors.append(
                        f"E_PROMPT_QUALITY_NOT_READY {task_id}: executable generation requires "
                        f"CURRENT PASS quality for {sorted(compiled_ids - quality_pass_prompt_ids)}"
                    )
                if task.get("task_type") == "IMAGE_TO_VIDEO":
                    prompts_without_input_mapping = {
                        prompt_id for prompt_id in compiled_ids
                        if not any(
                            operation.get("kind") == "INPUT_RELATION_MAPPING"
                            for adapter in as_list(
                                quality_for_prompt_id.get(prompt_id, {}).get("adapter_integrity")
                            )
                            if isinstance(adapter, dict)
                            and str(adapter.get("provider_prompt_id")) == prompt_id
                            for operation in as_list(adapter.get("adapter_operations"))
                            if isinstance(operation, dict)
                        )
                    }
                    if prompts_without_input_mapping:
                        errors.append(
                            f"PQ_ADAPTER_LOSS {task_id}: IMAGE_TO_VIDEO compiled Prompt must preserve "
                            f"first-frame input responsibility {sorted(prompts_without_input_mapping)}"
                        )
                    upstream_image_refs = {
                        ref
                        for dependency_id in dependencies
                        if task_by_id.get(dependency_id, {}).get("task_type") == "IMAGE_GENERATION"
                        for ref in versioned_refs(
                            task_by_id.get(dependency_id, {}).get("output_artifact_refs")
                        )
                    }
                    bound_first_frame_refs = input_refs & upstream_image_refs
                    if not bound_first_frame_refs:
                        errors.append(
                            f"E_I2V_FIRST_FRAME_MISSING {task_id}: IMAGE_TO_VIDEO requires a versioned "
                            "input artifact produced by an upstream IMAGE_GENERATION task"
                        )
                    motion_target_ids = {
                        str(target.get("target_id"))
                        for target in generation_targets
                        if target.get("target_type") == "SHOT"
                        and target.get("generation_role") == "SHOT_MOTION"
                    }
                    upstream_start_frame_target_ids: set[str] = set()
                    for dependency_id in dependencies:
                        upstream_task = task_by_id.get(dependency_id, {})
                        if upstream_task.get("task_type") != "IMAGE_GENERATION":
                            continue
                        upstream_output_refs = versioned_refs(
                            upstream_task.get("output_artifact_refs")
                        )
                        if not (upstream_output_refs & bound_first_frame_refs):
                            continue
                        for upstream_target in as_list(upstream_task.get("generation_targets")):
                            if (
                                isinstance(upstream_target, dict)
                                and upstream_target.get("target_type") == "SHOT"
                                and upstream_target.get("generation_role")
                                in {"SHOT_KEYFRAME", "SHOT_START_FRAME"}
                                and upstream_target.get("generation_medium") == "IMAGE"
                            ):
                                upstream_start_frame_target_ids.add(
                                    str(upstream_target.get("target_id"))
                                )
                    if not motion_target_ids or motion_target_ids - upstream_start_frame_target_ids:
                        errors.append(
                            f"E_I2V_FIRST_FRAME_MISSING {task_id}: every SHOT_MOTION target needs an "
                            "upstream IMAGE SHOT_KEYFRAME or SHOT_START_FRAME for the same shot"
                        )
                    if any(
                        artifact_by_id.get(artifact_id, {}).get("artifact_class") != "MEDIA"
                        for artifact_id, _version in bound_first_frame_refs
                    ):
                        errors.append(
                            f"E_I2V_FIRST_FRAME_MISSING {task_id}: first-frame input must be a MEDIA artifact"
                        )
                    if task.get("status") in {"RUNNING", "EXECUTED_FAILED", "EXECUTED_SUCCEEDED"} and any(
                        artifact_by_id.get(artifact_id, {}).get("real_artifact_present") is not True
                        or artifact_by_id.get(artifact_id, {}).get("execution_mode") != "REAL"
                        or not isinstance(artifact_by_id.get(artifact_id, {}).get("content_locator"), dict)
                        for artifact_id, _version in bound_first_frame_refs
                    ):
                        errors.append(
                            f"E_I2V_FIRST_FRAME_MISSING {task_id}: running/executed I2V requires a real accessible first frame"
                        )
                    if task.get("status") in {"RUNNING", "EXECUTED_FAILED", "EXECUTED_SUCCEEDED"}:
                        succeeded_image_refs = {
                            ref
                            for dependency_id in dependencies
                            if task_by_id.get(dependency_id, {}).get("task_type") == "IMAGE_GENERATION"
                            and task_by_id.get(dependency_id, {}).get("status") == "EXECUTED_SUCCEEDED"
                            for ref in versioned_refs(
                                task_by_id.get(dependency_id, {}).get("output_artifact_refs")
                            )
                        }
                        if not bound_first_frame_refs or bound_first_frame_refs - succeeded_image_refs:
                            errors.append(
                                f"E_I2V_FIRST_FRAME_MISSING {task_id}: running/executed I2V first frame "
                                "must be an output of an EXECUTED_SUCCEEDED upstream IMAGE task"
                            )
                    motion_prompts = [
                        prompt_by_id[prompt_id]
                        for prompt_id in compiled_ids & set(prompt_by_id)
                        if prompt_by_id[prompt_id].get("generation_role") == "SHOT_MOTION"
                    ]
                    if motion_prompts and not bound_first_frame_refs and any(
                        not as_list(prompt.get("reference_ids")) for prompt in motion_prompts
                    ):
                        errors.append(
                            f"E_I2V_FIRST_FRAME_MISSING {task_id}: SHOT_MOTION lacks first-frame responsibility"
                        )
            if (
                task.get("task_type") in GENERATION_TASK_TYPES
                and task.get("status") in EXECUTABLE_GENERATION_STATUSES
                and (
                    not compiled_ids
                    or master_ids
                    or draft_ids
                    or transform_plan_ids
                    or neutral_execution_prompt_ids
                    or any(
                        prompt_by_id.get(prompt_id, {}).get("prompt_layer")
                        != "PROVIDER_COMPILED"
                        for prompt_id in compiled_ids
                    )
                )
            ):
                errors.append(
                    f"E_TASK_EXECUTABLE_PROMPT_LAYER {task_id}: executable generation accepts only compiled Prompt IDs"
                )
            if task.get("approval_required") is True and str(task.get("approval_event_id")) not in approval_by_id:
                errors.append(f"E_TASK_AUTHORIZATION_MISSING {task_id}: required approval is unresolved")
            receipt_ids = set(map(str, as_list(task.get("receipt_ids"))))
            if receipt_ids - set(receipt_by_id):
                errors.append(f"E_TASK_RECEIPT_UNKNOWN {task_id}: unresolved receipt IDs")
            if any(
                receipt_by_id.get(receipt_id, {}).get("task_id") != task_id
                for receipt_id in receipt_ids & set(receipt_by_id)
            ):
                errors.append(f"E_TASK_RECEIPT_MISMATCH {task_id}: receipt belongs to another task")
            external_route = task.get("execution_route") in {
                "LOCAL_TOOL", "BROWSER", "API", "MANUAL"
            }
            executing_generation_statuses = {
                "RUNNING": "RUNNING",
                "EXECUTED_FAILED": "FAILED",
                "EXECUTED_SUCCEEDED": "SUCCEEDED",
            }
            task_status = str(task.get("status"))
            if (
                task.get("task_type") in GENERATION_TASK_TYPES
                and task_status in executing_generation_statuses
            ):
                compiled_provider_ids = {
                    str(prompt_by_id[prompt_id].get("provider_registry_id"))
                    for prompt_id in compiled_ids & set(prompt_by_id)
                }
                if not external_route:
                    errors.append(
                        f"E_TASK_EXECUTION_RECEIPT_MISSING {task_id}: executing generation "
                        "requires a real external route"
                    )
                if not provider_ids or provider_ids != compiled_provider_ids:
                    errors.append(
                        f"E_TASK_EXECUTION_BINDING {task_id}: executing generation provider IDs "
                        "must exactly match its compiled Prompts"
                    )
                expected_result = executing_generation_statuses[task_status]
                matching_generation_receipts = [
                    receipt_by_id[receipt_id]
                    for receipt_id in receipt_ids & set(receipt_by_id)
                    if receipt_by_id[receipt_id].get("result") == expected_result
                    and receipt_by_id[receipt_id].get("execution_mode") == "REAL"
                    and effective_execution_domain(receipt_by_id[receipt_id], task)
                    == "PRODUCTION_MEDIA"
                ]
                if not matching_generation_receipts:
                    errors.append(
                        f"E_TASK_EXECUTION_RECEIPT_MISSING {task_id}: {task_status} generation "
                        f"requires a real {expected_result} production-media receipt"
                    )
            if task.get("status") == "EXECUTED_SUCCEEDED" and external_route:
                matching_receipts = [
                    receipt_by_id[receipt_id]
                    for receipt_id in receipt_ids & set(receipt_by_id)
                    if receipt_by_id[receipt_id].get("result") == "SUCCEEDED"
                    and receipt_by_id[receipt_id].get("execution_mode") == "REAL"
                ]
                if not matching_receipts:
                    errors.append(
                        f"E_TASK_EXECUTION_RECEIPT_MISSING {task_id}: external success requires a real success receipt"
                    )
            if (
                task.get("status") == "EXECUTED_SUCCEEDED"
                and task.get("task_type") in PRODUCTION_MEDIA_TASK_TYPES
            ):
                if not output_refs or any(
                    artifact_by_id.get(artifact_id, {}).get("real_artifact_present") is not True
                    or artifact_by_id.get(artifact_id, {}).get("execution_mode") != "REAL"
                    or artifact_by_id.get(artifact_id, {}).get("artifact_class")
                    not in {"MEDIA", "PACKAGE"}
                    for artifact_id, _version in output_refs
                ):
                    errors.append(
                        f"E_TASK_REAL_OUTPUT_MISSING {task_id}: successful media execution requires real outputs"
                    )
            if task.get("status") == "SIMULATED_ONLY" and any(
                artifact_by_id.get(artifact_id, {}).get("real_artifact_present") is True
                for artifact_id, _version in output_refs
            ):
                errors.append(f"E_SIMULATION_REAL_OUTPUT {task_id}: simulation cannot produce real artifacts")

        # Detect dependency cycles after all task IDs have been resolved.
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit_task(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                errors.append(f"E_TASK_DEPENDENCY_CYCLE {task_id}: cyclic task graph")
                return
            visiting.add(task_id)
            for dependency in as_list(task_by_id.get(task_id, {}).get("depends_on_task_ids")):
                dependency_id = str(dependency)
                if dependency_id in task_by_id:
                    visit_task(dependency_id)
            visiting.discard(task_id)
            visited.add(task_id)

        for task_id in task_by_id:
            visit_task(task_id)

        for receipt_id, receipt in receipt_by_id.items():
            task_id = str(receipt.get("task_id"))
            task = task_by_id.get(task_id)
            if not task:
                errors.append(f"E_RECEIPT_TASK_UNKNOWN {receipt_id}: unresolved task {task_id}")
                continue
            if receipt_id not in set(map(str, as_list(task.get("receipt_ids")))):
                errors.append(f"E_TASK_RECEIPT_MISMATCH {receipt_id}: task has no receipt backlink")
            if receipt.get("execution_route") != task.get("execution_route"):
                errors.append(f"E_TASK_RECEIPT_MISMATCH {receipt_id}: execution route differs from task")
            receipt_domain = effective_execution_domain(receipt, task)
            task_type = str(task.get("task_type", ""))
            if task_type in PRODUCTION_MEDIA_TASK_TYPES and receipt_domain != "PRODUCTION_MEDIA":
                errors.append(
                    f"E_RECEIPT_DOMAIN_MISMATCH {receipt_id}: {task_type} must use "
                    "execution_domain=PRODUCTION_MEDIA"
                )
            if task_type in LOCAL_VALIDATION_TASK_TYPES and receipt_domain != "LOCAL_VALIDATION":
                errors.append(
                    f"E_RECEIPT_DOMAIN_MISMATCH {receipt_id}: {task_type} must use "
                    "execution_domain=LOCAL_VALIDATION"
                )
            if task_type in LOCAL_TEXT_TOOL_TASK_TYPES and receipt_domain != "LOCAL_TEXT_TOOL":
                errors.append(
                    f"E_RECEIPT_DOMAIN_MISMATCH {receipt_id}: {task_type} must use "
                    "execution_domain=LOCAL_TEXT_TOOL"
                )
            checked_artifact_refs(receipt.get("input_artifact_refs"), receipt_id)
            receipt_outputs = checked_artifact_refs(receipt.get("output_artifact_refs"), receipt_id)
            receipt_evidence = set(map(str, as_list(receipt.get("evidence_ids"))))
            if receipt_evidence - set(evidence_by_id):
                errors.append(f"E_RECEIPT_EVIDENCE_UNKNOWN {receipt_id}: unresolved evidence IDs")
            provider_id = receipt.get("provider_registry_id")
            if provider_id is not None and str(provider_id) not in provider_by_id:
                errors.append(f"E_RECEIPT_PROVIDER_UNKNOWN {receipt_id}: unresolved provider")
            receipt_prompt_ids = set(map(str, as_list(receipt.get("provider_prompt_ids"))))
            if receipt_prompt_ids - set(prompt_by_id) or any(
                prompt_by_id.get(prompt_id, {}).get("prompt_layer") != "PROVIDER_COMPILED"
                for prompt_id in receipt_prompt_ids
            ):
                errors.append(
                    f"E_TASK_EXECUTABLE_PROMPT_LAYER {receipt_id}: receipt may bind only compiled Prompt IDs"
                )
            if provider_id is not None:
                provider = provider_by_id.get(str(provider_id), {})
                if str(receipt.get("provider_snapshot_id")) != str(provider.get("snapshot_id")):
                    errors.append(
                        f"E_RECEIPT_PROVIDER_UNKNOWN {receipt_id}: provider snapshot does not match registry"
                    )
            if task_type in GENERATION_TASK_TYPES and receipt.get("result") in {
                "RUNNING", "FAILED", "SUCCEEDED",
            }:
                if receipt_prompt_ids - quality_pass_prompt_ids:
                    errors.append(
                        f"E_PROMPT_QUALITY_NOT_READY {receipt_id}: generation receipt cannot bind "
                        f"non-PASS quality Prompts {sorted(receipt_prompt_ids - quality_pass_prompt_ids)}"
                    )
                task_prompt_ids = set(map(str, as_list(task.get("provider_prompt_ids"))))
                task_provider_ids = set(map(str, as_list(task.get("provider_registry_ids"))))
                receipt_versions = set(
                    map(str, as_list(receipt.get("source_spec_versions")))
                )
                prompt_versions = {
                    str(prompt_by_id[prompt_id].get("source_spec_version"))
                    for prompt_id in receipt_prompt_ids & set(prompt_by_id)
                }
                provider = provider_by_id.get(str(provider_id), {})
                prompt_binding_invalid = (
                    receipt_domain != "PRODUCTION_MEDIA"
                    or receipt.get("execution_mode") != "REAL"
                    or provider_id is None
                    or str(provider_id) not in task_provider_ids
                    or not receipt_prompt_ids
                    or not receipt_prompt_ids <= task_prompt_ids
                    or not receipt_versions
                    or receipt_versions != prompt_versions
                    or any(
                        str(prompt_by_id.get(prompt_id, {}).get("provider_registry_id"))
                        != str(provider_id)
                        or str(prompt_by_id.get(prompt_id, {}).get("provider_snapshot_id"))
                        != str(receipt.get("provider_snapshot_id"))
                        for prompt_id in receipt_prompt_ids
                    )
                    or str(receipt.get("provider_snapshot_id"))
                    != str(provider.get("snapshot_id"))
                )
                if prompt_binding_invalid:
                    errors.append(
                        f"E_TASK_EXECUTION_BINDING {receipt_id}: generation attempt must bind "
                        "its task, route, provider snapshot, compiled Prompts, and source-spec versions"
                    )
                if receipt.get("result") == "FAILED" and (
                    not receipt_evidence or not nonempty(receipt.get("blocked_reason"))
                ):
                    errors.append(
                        f"E_TASK_EXECUTION_RECEIPT_MISSING {receipt_id}: failed generation "
                        "requires failure evidence and a recorded reason"
                    )
            if receipt.get("result") == "SUCCEEDED":
                if not receipt_outputs and not receipt_evidence:
                    errors.append(
                        f"E_RECEIPT_OUTPUT_MISSING {receipt_id}: real success needs output or execution evidence"
                    )
                if receipt.get("authorization_class") != "NONE" and receipt.get("authorization_status") != "GRANTED":
                    errors.append(
                        f"E_RECEIPT_AUTHORIZATION_MISSING {receipt_id}: protected action was not authorized"
                    )
                if receipt.get("execution_mode") != "REAL":
                    errors.append(f"E_RECEIPT_TRUTH_CONTRADICTION {receipt_id}: success must be REAL")
            if (
                receipt_domain == "PRODUCTION_MEDIA"
                and receipt.get("execution_mode") == "REAL"
                and receipt.get("result") in {"RUNNING", "FAILED", "SUCCEEDED"}
                and state.get("execution_mode") != "REAL"
            ):
                errors.append(
                    f"E_RECEIPT_TRUTH_CONTRADICTION {receipt_id}: real production-media "
                    "receipt requires project REAL mode"
                )
            if receipt_domain == "PRODUCTION_MEDIA" and receipt.get("result") == "SUCCEEDED":
                if not receipt_outputs or any(
                    artifact_by_id.get(artifact_id, {}).get("real_artifact_present") is not True
                    or artifact_by_id.get(artifact_id, {}).get("execution_mode") != "REAL"
                    or artifact_by_id.get(artifact_id, {}).get("artifact_class")
                    not in {"MEDIA", "PACKAGE"}
                    for artifact_id, _version in receipt_outputs
                ):
                    errors.append(
                        f"E_RECEIPT_OUTPUT_MISSING {receipt_id}: production-media success "
                        "requires real MEDIA/PACKAGE output versions"
                    )
            if receipt_domain in {"LOCAL_VALIDATION", "LOCAL_TEXT_TOOL"} and any(
                artifact_by_id.get(artifact_id, {}).get("artifact_class") in {"MEDIA", "PACKAGE"}
                for artifact_id, _version in receipt_outputs
            ):
                errors.append(
                    f"E_RECEIPT_DOMAIN_OUTPUT {receipt_id}: local validation/text tooling "
                    "cannot claim production MEDIA/PACKAGE output"
                )
            if receipt.get("authorization_status") == "GRANTED" and str(receipt.get("approval_event_id")) not in approval_by_id:
                errors.append(
                    f"E_RECEIPT_AUTHORIZATION_MISSING {receipt_id}: granted authorization lacks approval event"
                )
            if receipt.get("result") == "SIMULATED_ONLY" and any(
                artifact_by_id.get(artifact_id, {}).get("real_artifact_present") is True
                for artifact_id, _version in receipt_outputs
            ):
                errors.append(f"E_SIMULATION_REAL_OUTPUT {receipt_id}: simulated receipt cites real output")

        passed_final_preflights: list[dict[str, Any]] = []
        for preflight_id, preflight in preflight_by_id.items():
            preflight_refs: set[tuple[str, str]] = set()
            for reference in as_list(preflight.get("artifact_refs")):
                if not isinstance(reference, dict):
                    continue
                artifact_id = str(reference.get("artifact_id"))
                version = str(reference.get("version"))
                artifact = artifact_by_id.get(artifact_id)
                if not artifact or str(artifact.get("version")) != version:
                    errors.append(
                        f"E_PREFLIGHT_ARTIFACT_SCOPE {preflight_id}: unresolved {artifact_id}@{version}"
                    )
                    continue
                preflight_refs.add((artifact_id, version))
                claimed_hash = reference.get("sha256")
                locator = artifact.get("content_locator")
                actual_hash = locator.get("sha256") if isinstance(locator, dict) else None
                if claimed_hash is not None and str(claimed_hash).lower() != str(actual_hash).lower():
                    errors.append(
                        f"E_PREFLIGHT_DIGEST_MISMATCH {preflight_id}: {artifact_id}@{version} hash differs"
                    )
                if preflight.get("checkpoint") == "FINAL" and (
                    artifact.get("real_artifact_present") is not True
                    or artifact.get("execution_mode") != "REAL"
                    or not nonempty(actual_hash)
                ):
                    errors.append(
                        f"E_FINAL_PREFLIGHT_NOT_REAL {preflight_id}: final check requires exact real artifacts"
                    )
            global_evidence = set(map(str, as_list(preflight.get("evidence_ids"))))
            if global_evidence - set(evidence_by_id):
                errors.append(f"E_PREFLIGHT_EVIDENCE_UNKNOWN {preflight_id}: unresolved evidence IDs")
            checks = preflight.get("checks") if isinstance(preflight.get("checks"), dict) else {}
            check_statuses: dict[str, Any] = {}
            check_objects: dict[str, dict[str, Any]] = {}
            for check_name in ("naturalness", "compliance", "rights", "propagation"):
                check = checks.get(check_name) if isinstance(checks.get(check_name), dict) else {}
                check_objects[check_name] = check
                check_statuses[check_name] = check.get("status")
                check_evidence = set(map(str, as_list(check.get("evidence_ids"))))
                check_blockers = set(map(str, as_list(check.get("blocking_issue_ids"))))
                if check_evidence - set(evidence_by_id):
                    errors.append(
                        f"E_PREFLIGHT_EVIDENCE_UNKNOWN {preflight_id}: {check_name} has unresolved evidence"
                    )
                if check_blockers - set(issue_by_id):
                    errors.append(
                        f"E_PREFLIGHT_BLOCKER_UNKNOWN {preflight_id}: {check_name} has unresolved blockers"
                    )
                if check.get("status") == "BLOCKED" and not check_blockers:
                    errors.append(
                        f"E_PREFLIGHT_BLOCKER_MISSING {preflight_id}: blocked {check_name} needs blocker IDs"
                    )
                if check.get("status") == "PASS" and check_blockers:
                    errors.append(
                        f"E_PREFLIGHT_OUTCOME_CONTRADICTION {preflight_id}: passed {check_name} retains blockers"
                    )
                if check_name in {"compliance", "rights"} and (
                    check.get("score") is not None or check.get("score_basis") != "NOT_SCORED"
                ):
                    errors.append(
                        f"E_PREFLIGHT_BLOCKER_NOT_SCORE {preflight_id}: {check_name} cannot be reduced to a score"
                    )
                if check.get("score") is None and check.get("score_basis") != "NOT_SCORED":
                    errors.append(
                        f"E_PREFLIGHT_SCORE_BASIS {preflight_id}: missing score must use NOT_SCORED"
                    )
                if check.get("score") is not None and not nonempty(check.get("rubric_version")):
                    errors.append(
                        f"E_PREFLIGHT_SCORE_BASIS {preflight_id}: scored check requires rubric_version"
                    )
                if check.get("score_basis") == "MEASURED" and not check_evidence:
                    errors.append(
                        f"E_PREFLIGHT_SCORE_BASIS {preflight_id}: measured score requires evidence"
                    )
            if preflight.get("overall_outcome") == "PASS" and any(
                check_statuses.get(name) != "PASS"
                for name in ("naturalness", "compliance", "rights", "propagation")
            ):
                errors.append(
                    f"E_PREFLIGHT_OUTCOME_CONTRADICTION {preflight_id}: overall PASS requires four PASS checks"
                )
            if any(check_statuses.get(name) == "BLOCKED" for name in ("compliance", "rights")) and preflight.get("overall_outcome") != "BLOCKED":
                errors.append(
                    f"E_PREFLIGHT_BLOCKER_OVERRIDE {preflight_id}: propagation cannot offset compliance or rights"
                )
            if preflight.get("checkpoint") == "FINAL" and preflight.get("overall_outcome") == "PASS":
                if preflight.get("execution_mode") != "REAL":
                    errors.append(f"E_FINAL_PREFLIGHT_NOT_REAL {preflight_id}: final PASS cannot be simulated")
                if not check_objects["compliance"].get("evidence_ids") or not check_objects["rights"].get("evidence_ids"):
                    errors.append(
                        f"E_FINAL_PREFLIGHT_EVIDENCE_MISSING {preflight_id}: final compliance and rights need evidence"
                    )
                passed_final_preflights.append(preflight)

        if workflow.get("publication_status") in {"RELEASE_READY", "PUBLISH_PENDING", "PUBLISHED"}:
            passed_release_gates = [
                gate
                for gate in gates
                if isinstance(gate, dict)
                and gate.get("gate_type") == "RELEASE_READINESS_GATE"
                and gate.get("evaluation_status") == "EXECUTED"
                and gate.get("outcome") in {"PASSED", "ACCEPTED_WITH_DEBT"}
            ]
            covered = False
            for gate in passed_release_gates:
                binding = gate.get("scope_bindings") if isinstance(gate.get("scope_bindings"), dict) else {}
                required_ids = scope_list(binding, "artifact_ids") | scope_list(
                    binding, "release_package_ids"
                )
                required_versions = versioned_refs(binding.get("artifact_versions"))
                for preflight in passed_final_preflights:
                    refs = versioned_refs(preflight.get("artifact_refs"))
                    if required_ids <= {artifact_id for artifact_id, _version in refs} and required_versions <= refs:
                        covered = True
                        break
                if covered:
                    break
            if not covered:
                errors.append(
                    "E_FINAL_PREFLIGHT_MISSING workflow_status: release state requires a passed exact-artifact fourfold preflight"
                )

    if legacy_generation:
        required_media_work = bool(shot_plans or provider_prompts) or any(
            isinstance(item, dict) and item.get("artifact_class") == "MEDIA"
            for item in artifacts
        )
        if required_media_work and workflow.get("observation_status") == "NOT_APPLICABLE":
            errors.append("workflow_status: required media work cannot mark observation NOT_APPLICABLE")
        if required_media_work and workflow.get("qa_status") == "NOT_APPLICABLE":
            errors.append("workflow_status: required media work cannot mark QA NOT_APPLICABLE")
        cleanup = state.get("state_cleanup")
        if workflow.get("spec_status") == "TEXT_SPEC_COMPLETE":
            if not isinstance(cleanup, dict) or cleanup.get("audit_status") != "EXECUTED":
                errors.append("state_cleanup: TEXT_SPEC_COMPLETE requires an executed final-state cleanup")
            else:
                found = as_list(cleanup.get("errors_found"))
                fixed = as_list(cleanup.get("errors_fixed"))
                unresolved = as_list(cleanup.get("unresolved_issue_ids"))
                if len(found) > len(fixed) + len(unresolved):
                    errors.append("state_cleanup: every found error must be recorded as fixed or unresolved")
        if workflow.get("observation_status") == "OBSERVED" and not any(
            isinstance(item, dict) and item.get("media_accessible") is True for item in observations
        ):
            errors.append("workflow_status: OBSERVED requires at least one accessible-media observation")
        if workflow.get("publication_status") == "RELEASE_READY" and not gate_passed(gates, "RELEASE_READINESS_GATE"):
            errors.append("workflow_status: RELEASE_READY requires passed RELEASE_READINESS_GATE")
        if workflow.get("publication_status") == "PUBLISHED" and not gate_passed(gates, "PUBLICATION_EVIDENCE_GATE"):
            errors.append("workflow_status: PUBLISHED requires passed PUBLICATION_EVIDENCE_GATE")
        if workflow.get("publication_status") == "PUBLISHED" and not gate_passed(gates, "RELEASE_READINESS_GATE"):
            errors.append("workflow_status: PUBLISHED requires prior passed RELEASE_READINESS_GATE")
        if workflow.get("publication_status") == "PUBLISHED":
            passed_publication_ids = {
                str(pub_id)
                for gate in gates
                if isinstance(gate, dict)
                and gate.get("gate_type") == "PUBLICATION_EVIDENCE_GATE"
                and gate.get("evaluation_status") == "EXECUTED"
                and gate.get("outcome") == "PASSED"
                for pub_id in as_list(gate.get("publication_ids"))
            }
            if not passed_publication_ids.intersection(publication_by_id):
                errors.append("workflow_status: PUBLISHED and publication gate must reference the same valid publication record")
        if workflow.get("learning_status") == "LEARNING_VALIDATED":
            if not gate_passed(gates, "LEARNING_GATE"):
                errors.append("workflow_status: LEARNING_VALIDATED requires passed LEARNING_GATE")
            if not any(isinstance(item, dict) and item.get("status") == "LEARNING_VALIDATED" for item in learning_records):
                errors.append("workflow_status: LEARNING_VALIDATED requires a validated learning record")
        if "REAL_PRODUCTION_COMPLETE" in terminal_markers:
            for required_gate in (
                "ASSET_GATE", "SHOT_GATE", "SEQUENCE_CONTINUITY_GATE",
                "FINAL_ARTIFACT_GATE", "RELEASE_READINESS_GATE",
            ):
                if not gate_passed(gates, required_gate):
                    errors.append(f"REAL_PRODUCTION_COMPLETE requires passed {required_gate}")
            if not any(
                isinstance(item, dict)
                and item.get("artifact_class") == "MEDIA"
                and item.get("real_artifact_present") is True
                for item in artifacts
            ):
                errors.append("REAL_PRODUCTION_COMPLETE requires a real final media artifact")
            if not any(
                isinstance(item, dict)
                and item.get("artifact_class") in {"PACKAGE", "RELEASE"}
                and item.get("real_artifact_present") is True
                for item in artifacts
            ):
                errors.append("REAL_PRODUCTION_COMPLETE requires a real release package")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path, help="Path to a Silver project-state JSON file")
    parser.add_argument(
        "--allow-legacy-import",
        action="store_true",
        help="Permit an older unversioned state only for import or migration; it does not satisfy the current contract.",
    )
    parser.add_argument(
        "--allow-prior-generation-import",
        action="store_true",
        help="Validate an earlier structured state only as migration input; it is not a current Alpha.7 state.",
    )
    parser.add_argument(
        "--allow-pre-quality-import",
        action="store_true",
        help="Validate a pre-quality-contract Alpha.7 state only as migration input; it cannot authorize generation.",
    )
    args = parser.parse_args()
    try:
        state = json.loads(args.state.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read state: {exc}", file=sys.stderr)
        return 2
    if not isinstance(state, dict):
        print("FAIL: top-level state must be an object", file=sys.stderr)
        return 2
    if state.get("schema_version") != ALPHA7_SCHEMA_VERSION and not (
        args.allow_prior_generation_import or args.allow_legacy_import
    ):
        print(
            "FAIL: current state requires schema_version=3.0.0-alpha.7; "
            "use --allow-prior-generation-import only for migration input",
            file=sys.stderr,
        )
        return 2
    legacy_boundary = args.allow_legacy_import and not isinstance(state.get("workflow_status"), dict)
    structure_errors = [] if legacy_boundary else validate_structure(
        state, allow_pre_quality_import=args.allow_pre_quality_import
    )
    if structure_errors:
        print(f"FAIL: {len(structure_errors)} structural/schema violation(s)")
        for error in structure_errors:
            print(f"- {error}")
        print("Invariant validation was not run because structure validation failed.")
        return 1
    errors = validate(
        state,
        allow_legacy_import=args.allow_legacy_import,
        allow_pre_quality_import=args.allow_pre_quality_import,
    )
    if errors:
        print(f"FAIL: {len(errors)} invariant violation(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    if not isinstance(state.get("workflow_status"), dict):
        label = "legacy import boundary"
    elif state.get("schema_version") == ALPHA7_SCHEMA_VERSION and args.allow_pre_quality_import:
        label = "pre-quality current-schema migration input"
    elif state.get("schema_version") == ALPHA7_SCHEMA_VERSION:
        label = "Alpha.7"
    else:
        label = "earlier-generation migration input"
    print(f"PASS: {label} state invariants satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
