#!/usr/bin/env python3
"""Migrate a read-only Alpha.7 longform contract into a fresh 1.5 authoring run.

The source contract is never rewritten.  Migration deliberately resets compiled
quality: legacy prompt artifacts contribute only ID/role/hash evidence, while
all creative prompts, quote assignments, execution beats, and review states
must be re-authored or re-derived under 1.5 before finalizing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from prepare_longform_authoring import (
    AUTHORING_GUIDE_VERSION,
    AUTHORING_VERSION,
    IN_PLACE_COMMIT_MODE,
    build_target_plan,
    compact_overlay_work_surface,
    prepare_authoring,
)
from validate_longform_contract import (
    CONTRACT_VERSION,
    READ_ONLY_CONTRACT_VERSIONS,
    load_source_text,
    validate_contract,
)


MIGRATION_VERSION = "alpha7-longform-migration-1.1"
OUTPUT_NAMES = ("TARGET_PLAN.json", "AUTHORING.json", "OVERLAYS.json")


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def legacy_prompt_evidence(source: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for unit in source.get("units", []):
        if not isinstance(unit, dict):
            continue
        bundle = unit.get("prompt_bundle") if isinstance(
            unit.get("prompt_bundle"), dict
        ) else {}
        artifact = None
        artifact_role = None
        for role in ("neutral_execution_prompt", "draft_prompt"):
            candidate = bundle.get(role)
            if isinstance(candidate, dict):
                artifact = candidate
                artifact_role = role
                break
        if artifact is None:
            continue
        text = artifact.get("text")
        evidence.append(
            {
                "source_artifact_id": artifact.get("artifact_id"),
                "source_role": artifact.get("layer") or artifact_role,
                "source_text_sha256": hashlib.sha256(
                    str(text).encode("utf-8")
                ).hexdigest(),
            }
        )
    return evidence


def assert_fresh_v15_migration(
    envelope: dict[str, Any], compact: dict[str, Any]
) -> None:
    """Fail closed if migration inherits approval or creative 1.0--1.4 products."""

    contract = envelope.get("immutable_contract")
    if not isinstance(contract, dict) or (
        contract.get("contract_version") != CONTRACT_VERSION
        or contract.get("authoring_version") != AUTHORING_VERSION
        or contract.get("validation_result") is not None
        or contract.get("project_status") != "GLOBAL_READY"
        or contract.get("production_validation") != "NOT_TESTED"
    ):
        raise ValueError("E_MIGRATION_STATUS_INHERITANCE: target must be a fresh unapproved 1.5 run")
    forbidden_unit_products = {
        "compile_status", "director_contract", "prompt_bundle", "prompt_quality_records",
        "content_self_review", "dialogue_diff", "validation_result", "unit_compile_sha256",
        "quote_assignments", "execution_beats",
    }
    if any(
        isinstance(unit, dict) and forbidden_unit_products.intersection(unit)
        for unit in contract.get("units", [])
    ):
        raise ValueError("E_MIGRATION_STATUS_INHERITANCE: compiled/PASS Unit products cannot cross migration")
    windows = compact.get("target_windows") if isinstance(compact, dict) else None
    overlays = compact.get("compiled_unit_overlays") if isinstance(compact, dict) else None
    if not isinstance(windows, list) or not windows or not isinstance(overlays, list) or len(overlays) != len(windows):
        raise ValueError("E_MIGRATION_V15_SCAFFOLD: target windows/overlays are incomplete")
    for index, (window, overlay) in enumerate(zip(windows, overlays)):
        scaffold = window.get("locked_director_scaffold") if isinstance(window, dict) else None
        if (
            not isinstance(scaffold, dict)
            or scaffold.get("scaffold_version") != "alpha7-director-scaffold-1.1"
            or scaffold.get("derivation") != "HELPER_DERIVED"
            or window.get("locked_scaffold_sha256") != canonical_sha256(scaffold)
            or not isinstance(window.get("single_shot_eligibility"), dict)
            or window.get("fixed_transform_roles") != {
                "source_role": "PROVIDER_NEUTRAL_MASTER",
                "target_role": "NEUTRAL_EXECUTION_PROMPT",
                "derivation": "HELPER_DERIVED",
            }
        ):
            raise ValueError(f"E_MIGRATION_V15_SCAFFOLD: window {index} lacks a canonical helper lock")
        director = overlay.get("director_overlay") if isinstance(overlay, dict) else None
        prompt = overlay.get("prompt_overlay") if isinstance(overlay, dict) else None
        shot_creative = director.get("shot_creative") if isinstance(director, dict) else None
        if (
            not isinstance(director, dict)
            or any(director.get(field) not in ("", None) for field in ("performance", "camera", "sound"))
            or not isinstance(shot_creative, list)
            or any(
                not isinstance(shot, dict)
                or shot.get("purpose") != ""
                or shot.get("camera") != ""
                or shot.get("action_additions") != []
                for shot in shot_creative
            )
            or not isinstance(prompt, dict)
            or prompt.get("neutral_execution_prompt_template") != ""
        ):
            raise ValueError(
                f"E_MIGRATION_CREATIVE_INHERITANCE: overlay {index} must not inherit purpose/camera/NEP"
            )


def migrate_contract(
    source: dict[str, Any], *, source_base: Path, output_dir: Path, run_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_version = source.get("contract_version")
    if source_version not in READ_ONLY_CONTRACT_VERSIONS:
        raise ValueError(
            "E_MIGRATION_SOURCE_VERSION: source must be read-only alpha7-longform-1.0 through 1.4"
        )
    report = validate_contract(
        source,
        source_base,
        validate_outputs=False,
        validate_recorded_result=False,
    )
    if not report.valid:
        codes = sorted({item["code"] for item in report.errors})
        raise ValueError(
            "E_MIGRATION_SOURCE_INVALID: read-only source failed validation: "
            + ",".join(codes)
        )
    source_text = load_source_text(source, source_base, report)
    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("E_MIGRATION_SOURCE_UNAVAILABLE: source text cannot be resolved")
    plan = build_target_plan("MACHINE_REPRESENTATIVE_V1", 3)
    envelope = prepare_authoring(
        source_text,
        plan,
        run_id,
        output_dir=output_dir,
        commit_mode=IN_PLACE_COMMIT_MODE,
        sample_count=3,
    )
    mapping = legacy_prompt_evidence(source)
    migration_record = {
        "migration_version": MIGRATION_VERSION,
        "source_contract_version": source_version,
        "source_artifact_sha256": canonical_sha256(source),
        "target_contract_version": CONTRACT_VERSION,
        "target_authoring_version": AUTHORING_VERSION,
        "target_guide_version": AUTHORING_GUIDE_VERSION,
        "mapping_profile": "READ_ONLY_PROMPT_EVIDENCE_TO_1_5_REAUTHOR",
        "legacy_prompt_role_mapping": mapping,
        "lossy_fields": [
            "compiled_quality_reset",
            "provider_binding_requires_revalidation",
            "legacy_transform_plan_was_not_evidenced",
            "quote_assignments_rederived_from_source",
            "execution_beats_rederived_from_source",
            "visible_quote_routes_rebuilt",
        ],
        "review_required": True,
        "reauthor_required": True,
    }
    envelope["immutable_contract"]["migration_record"] = migration_record
    compact = compact_overlay_work_surface(envelope)
    assert_fresh_v15_migration(envelope, compact)
    return plan, envelope, compact


def write_new_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_machine_state", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--to", default=CONTRACT_VERSION, choices=[CONTRACT_VERSION])
    parser.add_argument("--run-id", default="RUN13")
    args = parser.parse_args()
    if not re.fullmatch(r"RUN\d+", args.run_id):
        parser.error("--run-id must match RUN followed by digits")
    source_path = args.input_machine_state.resolve()
    output_dir = args.output_dir.resolve()
    try:
        source_bytes_before = source_path.read_bytes()
        source = json.loads(source_bytes_before.decode("utf-8-sig"))
        if not isinstance(source, dict):
            raise ValueError("input root must be an object")
        if output_dir == source_path.parent or source_path == output_dir:
            raise ValueError("E_MIGRATION_OUTPUT_SCOPE: output must not overlap the source path")
        if output_dir.exists():
            if not output_dir.is_dir() or output_dir.is_symlink() or any(output_dir.iterdir()):
                raise ValueError("E_MIGRATION_OUTPUT_SCOPE: output directory must be new or empty")
        else:
            output_dir.mkdir(parents=True, exist_ok=False)
        plan, envelope, compact = migrate_contract(
            source,
            source_base=source_path.parent,
            output_dir=output_dir,
            run_id=args.run_id,
        )
        for name, value in zip(OUTPUT_NAMES, (plan, envelope, compact)):
            write_new_json(output_dir / name, value)
        if source_path.read_bytes() != source_bytes_before:
            raise RuntimeError("E_MIGRATION_SOURCE_MUTATED: source bytes changed")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "migrated": True,
                "source_contract_version": source.get("contract_version"),
                "target_contract_version": CONTRACT_VERSION,
                "output_dir": str(output_dir),
                "output_files": list(OUTPUT_NAMES),
                "review_required": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
