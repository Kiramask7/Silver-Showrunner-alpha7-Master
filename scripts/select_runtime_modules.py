#!/usr/bin/env python3
"""Resolve an Alpha.7 modular runtime route from the frozen registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


sys.dont_write_bytecode = True

SELECTOR_READ_MODE = "MODULAR_ONLY"
REGISTRY_RELATIVE = "schemas/runtime_route_registry.json"
EXPECTED_REGISTRY_SCHEMA = "alpha7-master-runtime-route-registry-v1"
ONEFILE_MARKER = "SILVER_SHOWRUNNER_READ_MODE: ONEFILE_ONLY"
ONEFILE_GUARD_MARKER = "DO_NOT_LOAD_SOURCE_MODULES_WITH_THIS_ONEFILE: true"


class RouteError(ValueError):
    """A stable, machine-readable route failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def ordered_unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)
    return output


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_registry(root: Path) -> dict[str, Any]:
    path = root / REGISTRY_RELATIVE
    try:
        registry = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RouteError("E_ROUTE_REGISTRY", f"cannot load {REGISTRY_RELATIVE}: {exc}") from exc
    if not isinstance(registry, dict):
        raise RouteError("E_ROUTE_REGISTRY", "registry root must be an object")
    if registry.get("schema_version") != EXPECTED_REGISTRY_SCHEMA:
        raise RouteError(
            "E_ROUTE_REGISTRY",
            f"schema_version must be {EXPECTED_REGISTRY_SCHEMA}",
        )
    for key in ("read_mode_contract", "budget_policy", "routing", "catalogs", "entries"):
        if not isinstance(registry.get(key), dict if key != "entries" else list):
            raise RouteError("E_ROUTE_REGISTRY", f"missing or invalid registry section: {key}")
    return registry


def looks_like_onefile_content(text: str) -> bool:
    if ONEFILE_MARKER in text:
        return True
    return (
        ONEFILE_GUARD_MARKER in text
        and "Source / SHA-256 Index" in text
        and text.count("<!-- SOURCE:") >= 1
    )


def is_generated_onefile_name(path: Path) -> bool:
    return path.name == "SILVER_SHOWRUNNER_ONEFILE.md" or (
        "ONEFILE" in path.name.upper() and path.suffix.lower() == ".md"
    )


def onefile_conflicts(root: Path) -> list[str]:
    conflicts: list[str] = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            content_conflict = looks_like_onefile_content(
                path.read_text(encoding="utf-8-sig", errors="strict")
            )
        except (OSError, UnicodeError) as exc:
            raise RouteError(
                "E_READ_MODE_CONFLICT",
                f"cannot inspect Markdown read mode: {path}: {exc}",
            ) from exc
        if is_generated_onefile_name(path) or content_conflict:
            conflicts.append(path.relative_to(root).as_posix())
    return conflicts


def enforce_no_onefile_conflicts(root: Path) -> None:
    conflicts = onefile_conflicts(root)
    if conflicts:
        raise RouteError(
            "E_READ_MODE_CONFLICT",
            "modular tree contains a named or content-detected ONEFILE: "
            + ", ".join(conflicts),
        )


def validate_runtime_identity(root: Path, registry: dict[str, Any]) -> dict[str, str]:
    contract = registry["read_mode_contract"]
    manifest_path = root / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RouteError("E_READ_MODE_CONFLICT", f"cannot read MANIFEST.json: {exc}") from exc

    manifest_key = contract.get("manifest_key")
    registry_mode = contract.get("mode")
    manifest_mode = manifest.get(manifest_key) if isinstance(manifest_key, str) else None
    marker_file = contract.get("entry_marker_file")
    marker = contract.get("entry_marker")
    if not isinstance(marker_file, str) or not isinstance(marker, str):
        raise RouteError("E_READ_MODE_CONFLICT", "registry entry marker contract is invalid")
    marker_path = root / marker_file
    try:
        marker_text = marker_path.read_text(encoding="utf-8-sig", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise RouteError(
            "E_READ_MODE_CONFLICT",
            f"cannot read entry marker file {marker_file}: {exc}",
        ) from exc

    modes = {registry_mode, manifest_mode, SELECTOR_READ_MODE}
    if modes != {SELECTOR_READ_MODE} or marker not in marker_text:
        raise RouteError(
            "E_READ_MODE_CONFLICT",
            "manifest, entry marker, registry and selector must all declare MODULAR_ONLY",
        )
    if contract.get("onefile_marker") != ONEFILE_MARKER or (
        contract.get("onefile_guard_marker") != ONEFILE_GUARD_MARKER
    ):
        raise RouteError("E_READ_MODE_CONFLICT", "registry ONEFILE signature is stale")
    enforce_no_onefile_conflicts(root)
    return {
        "manifest": manifest_mode,
        "entry_marker": SELECTOR_READ_MODE,
        "registry": registry_mode,
        "selector": SELECTOR_READ_MODE,
    }


def normalize_project_types(
    project_type: str | list[str] | tuple[str, ...] | set[str],
) -> set[str]:
    return {project_type} if isinstance(project_type, str) else set(project_type)


def scope_matches(value: object, selected: set[str]) -> bool:
    if value == "*":
        return True
    return isinstance(value, list) and bool(set(value) & selected)


def rule_matches(
    rule: dict[str, Any],
    *,
    project_types: set[str],
    task: str,
    delivery_mode: str,
    active_flags: set[str],
) -> bool:
    when = rule.get("when", {})
    if not isinstance(when, dict):
        return False
    modes = when.get("delivery_modes")
    tasks = when.get("tasks")
    scoped_types = when.get("project_types")
    if not isinstance(modes, list) or delivery_mode not in modes:
        return False
    if tasks != "*" and (not isinstance(tasks, list) or task not in tasks):
        return False
    if scoped_types != "*":
        if not isinstance(scoped_types, list):
            return False
        match_mode = when.get("project_type_match", "ANY")
        scoped_set = set(scoped_types)
        if match_mode == "ALL":
            if not scoped_set <= project_types:
                return False
        elif not scoped_set & project_types:
            return False
    flags_all = when.get("flags_all", [])
    flags_none = when.get("flags_none", [])
    return (
        isinstance(flags_all, list)
        and isinstance(flags_none, list)
        and set(flags_all) <= active_flags
        and not (set(flags_none) & active_flags)
    )


def validate_mode_constraints(
    registry: dict[str, Any],
    *,
    project_types: set[str],
    task: str,
    delivery_mode: str,
    active_flags: set[str],
) -> None:
    constraints = registry["routing"].get("mode_constraints", {}).get(delivery_mode)
    if constraints is None:
        return
    required_tasks = set(constraints.get("required_tasks", []))
    required_types = set(constraints.get("required_project_types", []))
    forbidden_flags = set(constraints.get("forbidden_flags", []))
    if required_tasks and task not in required_tasks:
        raise RouteError(
            "E_ROUTE_CONSTRAINT",
            f"{delivery_mode} requires task in {sorted(required_tasks)}",
        )
    if required_types and not required_types <= project_types:
        raise RouteError(
            "E_ROUTE_CONSTRAINT",
            f"{delivery_mode} requires project types {sorted(required_types)}",
        )
    if forbidden := forbidden_flags & active_flags:
        raise RouteError(
            "E_ROUTE_CONSTRAINT",
            f"{delivery_mode} conflicts with flags {sorted(forbidden)}",
        )


def expand_dependencies(
    seed_paths: list[str],
    entries_by_path: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    modules: list[str] = []
    tool_resources: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(path: str) -> None:
        if path == "SKILL.md" or path in visited:
            return
        entry = entries_by_path.get(path)
        if entry is None:
            raise RouteError("E_ROUTE_REGISTRY", f"route references unregistered path: {path}")
        if path in visiting:
            raise RouteError("E_ROUTE_REGISTRY", f"dependency cycle reaches {path}")
        visiting.add(path)
        for dependency in entry.get("dependencies", []):
            visit(dependency)
        visiting.remove(path)
        visited.add(path)
        if entry.get("model_readable") is True:
            modules.append(path)
        else:
            tool_resources.append(path)

    for seed in seed_paths:
        visit(seed)
    return ordered_unique(modules), ordered_unique(tool_resources)


def resolve_route(
    root: Path,
    project_type: str | list[str] | tuple[str, ...] | set[str],
    task: str,
    *,
    delivery_mode: str = "MEDIA_ENABLED",
    current_facts: bool = False,
    minors: bool = False,
    needs_director_source: bool = False,
    triggers: Iterable[str] = (),
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    registry = registry or load_registry(root)
    identity = validate_runtime_identity(root, registry)
    catalogs = registry["catalogs"]
    valid_project_types = set(catalogs["project_types"])
    valid_tasks = set(catalogs["tasks"])
    valid_triggers = set(catalogs["triggers"])
    delivery_modes = set(registry["routing"]["delivery_modes"])

    project_types = normalize_project_types(project_type)
    unknown_types = project_types - valid_project_types
    if not project_types or unknown_types:
        raise RouteError(
            "E_ROUTE_INPUT",
            f"invalid project types: {sorted(unknown_types) or '<empty>'}",
        )
    if task not in valid_tasks:
        raise RouteError("E_ROUTE_INPUT", f"invalid task: {task}")
    if delivery_mode not in delivery_modes:
        raise RouteError("E_ROUTE_INPUT", f"invalid delivery mode: {delivery_mode}")
    requested_triggers = set(triggers)
    if unknown_triggers := requested_triggers - valid_triggers:
        raise RouteError("E_ROUTE_INPUT", f"invalid triggers: {sorted(unknown_triggers)}")

    active_flags = {
        flag
        for flag, enabled in (
            ("current_facts", current_facts),
            ("minors", minors),
            ("needs_director_source", needs_director_source),
        )
        if enabled
    }
    validate_mode_constraints(
        registry,
        project_types=project_types,
        task=task,
        delivery_mode=delivery_mode,
        active_flags=active_flags,
    )

    rules = sorted(
        registry["routing"]["route_rules"],
        key=lambda rule: (rule.get("priority", 0), rule.get("rule_id", "")),
    )
    matched_rules = [
        rule
        for rule in rules
        if rule_matches(
            rule,
            project_types=project_types,
            task=task,
            delivery_mode=delivery_mode,
            active_flags=active_flags,
        )
    ]
    exclusive_rules = [rule for rule in matched_rules if rule.get("exclusive") is True]
    active_rules = exclusive_rules or matched_rules
    seed_paths = ordered_unique(
        path
        for rule in active_rules
        for path in rule.get("include", [])
    )

    entries = registry["entries"]
    entries_by_path = {entry["path"]: entry for entry in entries}
    if not exclusive_rules and requested_triggers:
        for entry in entries:
            if entry.get("classification") != "TRIGGERED":
                continue
            if not requested_triggers.intersection(entry.get("triggers", [])):
                continue
            task_scope = entry.get("tasks")
            project_scope = entry.get("project_types")
            if task_scope != "*" and task not in set(task_scope):
                continue
            if not scope_matches(project_scope, project_types):
                continue
            seed_paths.append(entry["path"])

    if not seed_paths:
        raise RouteError("E_ROUTE_UNREACHABLE", "no registry rule matched the requested route")
    modules, tool_resources = expand_dependencies(seed_paths, entries_by_path)

    audit_resources: list[str] = []
    if requested_triggers and not exclusive_rules:
        for entry in entries:
            if entry.get("classification") not in {"TOOL_ONLY", "AUDIT_ONLY"}:
                continue
            if requested_triggers.intersection(entry.get("triggers", [])):
                if entry["classification"] == "TOOL_ONLY":
                    tool_resources.append(entry["path"])
                else:
                    audit_resources.append(entry["path"])
    tool_resources = ordered_unique(tool_resources)
    audit_resources = ordered_unique(audit_resources)

    forbidden_prefixes = tuple(registry["routing"]["normal_selection_forbidden_prefixes"])
    leaked = [path for path in modules if path.startswith(forbidden_prefixes)]
    if leaked:
        raise RouteError(
            "E_ROUTE_REGISTRY",
            "development files leaked into model-readable modules: " + ", ".join(leaked),
        )
    for path in modules + tool_resources + audit_resources:
        if not (root / path).is_file():
            raise RouteError("E_ROUTE_REGISTRY", f"selected path does not exist: {path}")
    if any(is_generated_onefile_name(Path(path)) for path in modules):
        raise RouteError("E_READ_MODE_CONFLICT", "ONEFILE leaked into modular selection")

    return {
        "project_types": sorted(project_types),
        "task": task,
        "delivery_mode": delivery_mode,
        "read_mode": SELECTOR_READ_MODE,
        "read_mode_identity": identity,
        "route_registry": REGISTRY_RELATIVE,
        "route_registry_schema": registry["schema_version"],
        "route_registry_sha256": digest(root / REGISTRY_RELATIVE),
        "matched_rule_ids": [rule["rule_id"] for rule in active_rules],
        "requested_triggers": sorted(requested_triggers),
        "needs_director_source": needs_director_source,
        "entry": "SKILL.md",
        "modules": modules,
        "tool_resources": tool_resources,
        "audit_resources": audit_resources,
        "selected_authority_ids": [entries_by_path[path]["authority_id"] for path in modules],
        "development_file_counts": {
            prefix.rstrip("/"): sum(path.startswith(prefix) for path in modules)
            for prefix in forbidden_prefixes
        },
    }


def select_modules(
    project_type: str | list[str] | tuple[str, ...] | set[str],
    task: str,
    *,
    root: Path | None = None,
    delivery_mode: str = "MEDIA_ENABLED",
    current_facts: bool = False,
    minors: bool = False,
    needs_director_source: bool = False,
    triggers: Iterable[str] = (),
) -> list[str]:
    resolved_root = (root or Path(__file__).resolve().parents[1]).resolve()
    return resolve_route(
        resolved_root,
        project_type,
        task,
        delivery_mode=delivery_mode,
        current_facts=current_facts,
        minors=minors,
        needs_director_source=needs_director_source,
        triggers=triggers,
    )["modules"]


def estimate_text(text: str) -> int:
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text))
    non_cjk = len(
        re.sub(r"[\s\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", "", text)
    )
    return cjk + math.ceil(non_cjk / 4)


def estimate(root: Path, modules: list[str]) -> dict[str, int]:
    characters = 0
    bytes_total = 0
    estimated_tokens = 0
    for relative in modules:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        text = path.read_text(encoding="utf-8-sig", errors="strict")
        characters += len(text)
        bytes_total += path.stat().st_size
        estimated_tokens += estimate_text(text)
    return {
        "module_count": len(modules),
        "source_bytes": bytes_total,
        "source_characters": characters,
        "estimated_tokens": estimated_tokens,
    }


def estimate_visible_files(paths: Iterable[Path]) -> dict[str, int]:
    unique_paths = list(dict.fromkeys(path.resolve() for path in paths))
    characters = 0
    bytes_total = 0
    estimated_tokens = 0
    for path in unique_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        text = path.read_text(encoding="utf-8-sig", errors="strict")
        characters += len(text)
        bytes_total += path.stat().st_size
        estimated_tokens += estimate_text(text)
    return {
        "file_count": len(unique_paths),
        "source_bytes": bytes_total,
        "source_characters": characters,
        "estimated_tokens": estimated_tokens,
    }


def execute_budget(
    registry: dict[str, Any],
    *,
    profile: str,
    entry_tokens: int,
    module_tokens: int,
    source_tokens: int,
    state_tokens: int,
) -> dict[str, Any]:
    policy = registry["budget_policy"]
    profiles = policy["profiles"]
    requested_profile = profile
    normalized_profile = profile.strip().upper()
    fallback_profile = policy["unknown_profile_fallback"]
    resolved_profile = (
        normalized_profile if normalized_profile in profiles else fallback_profile
    )
    components = {
        "entry_tokens": entry_tokens,
        "module_tokens": module_tokens,
        "source_tokens": source_tokens,
        "state_tokens": state_tokens,
    }
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in components.values()):
        raise RouteError("E_BUDGET_INPUT", "all visible token counts must be nonnegative integers")
    profile_policy = profiles[resolved_profile]
    context_window = profile_policy["context_window_tokens"]
    input_cap = profile_policy["input_cap_tokens"]
    rule_cap = profile_policy["rule_cap_tokens"]
    source_state_cap = profile_policy["source_state_cap_tokens"]
    output_reserve = profile_policy["output_reserve_tokens"]
    minimum_host_reserve_ratio = policy["minimum_host_reserve_ratio"]
    minimum_host_reserve = math.ceil(context_window * minimum_host_reserve_ratio)
    host_input_capacity = max(
        0,
        context_window - minimum_host_reserve - output_reserve,
    )
    rule_tokens = entry_tokens + module_tokens
    source_state_tokens = source_tokens + state_tokens
    total_visible = rule_tokens + source_state_tokens
    input_overflow = max(0, total_visible - input_cap)
    rule_overflow = max(0, rule_tokens - rule_cap)
    source_state_overflow = max(0, source_state_tokens - source_state_cap)
    host_reserve_shortfall = max(0, total_visible - host_input_capacity)
    split_required = any(
        overflow > 0
        for overflow in (
            input_overflow,
            rule_overflow,
            source_state_overflow,
            host_reserve_shortfall,
        )
    )
    status = policy["overflow_status"] if split_required else policy["within_status"]
    batch_counts = {
        "input": max(1, math.ceil(total_visible / input_cap)),
        "rules": max(1, math.ceil(rule_tokens / rule_cap)),
        "source_state": max(1, math.ceil(source_state_tokens / source_state_cap)),
        "host_reserve": (
            max(1, math.ceil(total_visible / host_input_capacity))
            if host_input_capacity
            else max(1, total_visible)
        ),
    }
    minimum_batches = max(batch_counts.values())
    available_host_reserve = max(
        0,
        context_window - total_visible - output_reserve,
    )
    return {
        "profile_requested": requested_profile,
        "profile": resolved_profile,
        "profile_fallback_applied": normalized_profile not in profiles,
        "context_window_tokens": context_window,
        "minimum_host_reserve_ratio": minimum_host_reserve_ratio,
        "minimum_host_reserve_tokens": minimum_host_reserve,
        "available_host_reserve_tokens": available_host_reserve,
        "host_reserve_requirement_met": host_reserve_shortfall == 0,
        "output_reserve_tokens": output_reserve,
        "input_cap_tokens": input_cap,
        "rule_cap_tokens": rule_cap,
        "source_state_cap_tokens": source_state_cap,
        "host_input_capacity_tokens": host_input_capacity,
        **components,
        "rule_tokens": rule_tokens,
        "source_state_tokens": source_state_tokens,
        "total_visible_tokens": total_visible,
        "total_controllable_input_tokens": total_visible,
        "input_overflow_tokens": input_overflow,
        "rule_overflow_tokens": rule_overflow,
        "source_state_overflow_tokens": source_state_overflow,
        "host_reserve_shortfall_tokens": host_reserve_shortfall,
        "overflow_tokens": max(
            input_overflow,
            rule_overflow,
            source_state_overflow,
            host_reserve_shortfall,
        ),
        "minimum_split_batches": minimum_batches,
        "split_batch_factors": batch_counts,
        "checkpoint_required": split_required,
        "checkpoint_plan": {
            "strategy": "SEQUENTIAL_CAPABILITY_PRESERVING",
            "minimum_batches": minimum_batches,
            "checkpoint_between_batches": split_required,
            "carry_forward": [
                "global_truth_hash",
                "source_cursor",
                "state_slice_hash",
                "selected_capability_ids",
                "open_findings",
            ],
        },
        "status": status,
        "split_required": split_required,
        "capability_policy": policy["capability_policy"],
        "selected_capabilities_removed": 0,
    }


def self_test(root: Path) -> int:
    registry = load_registry(root)
    validate_runtime_identity(root, registry)
    cases = [
        (("NARRATIVE_SHORT",), "DISCOVER", "MEDIA_ENABLED", False, False, False),
        (("NARRATIVE_SHORT",), "PROMPT", "MEDIA_ENABLED", False, True, False),
        (("NARRATIVE_SHORT",), "PROMPT", "MEDIA_ENABLED", False, False, True),
        (("SERIES_LONGFORM",), "STORY", "MEDIA_ENABLED", False, False, False),
        (("SCIENCE_RESEARCH_EXPLAINER",), "STORY", "MEDIA_ENABLED", False, False, False),
        (("SCIENCE_RESEARCH_EXPLAINER",), "GREENLIGHT", "MEDIA_ENABLED", True, False, False),
        (("BRAND_PRODUCT",), "FINAL_PREFLIGHT", "MEDIA_ENABLED", True, False, False),
        (("CULTURE_HERITAGE", "BRAND_PRODUCT"), "PROMPT", "MEDIA_ENABLED", False, False, False),
        (("EDUCATION_PUBLIC_INTEREST",), "EDIT", "MEDIA_ENABLED", False, False, False),
        (("SERIES_LONGFORM",), "PROMPT", "TEXT_ONLY_ECO_TEST", False, False, False),
    ]
    for project_types, task, delivery_mode, current_facts, minors, needs_director_source in cases:
        route = resolve_route(
            root,
            project_types,
            task,
            delivery_mode=delivery_mode,
            current_facts=current_facts,
            minors=minors,
            needs_director_source=needs_director_source,
            registry=registry,
        )
        modules = route["modules"]
        if route["development_file_counts"] != {"scripts": 0, "tests": 0, "schemas": 0}:
            raise AssertionError("normal creative route leaked development files")
        if any("ONEFILE" in Path(module).name.upper() for module in modules):
            raise AssertionError("ONEFILE must never appear in a modular runtime selection")
        if set(project_types) == {"NARRATIVE_SHORT"} and not current_facts:
            if "references/ON_DEMAND_RESEARCH_ROUTER.md" in modules:
                raise AssertionError("auxiliary research leaked into the default manga route")
        if task == "PROMPT":
            director_module = "phases/10_DIRECTOR_FINE_STORYBOARD.md"
            expected_director = needs_director_source and delivery_mode == "MEDIA_ENABLED"
            if (director_module in modules) != expected_director:
                raise AssertionError("director phase must load only when its source is missing")
        rich_copy_module = "references/SCRIPT_AND_DIALOGUE_WRITING_ENGINE.md"
        expected_rich_copy = (
            task == "STORY"
            and delivery_mode == "MEDIA_ENABLED"
            and bool(set(project_types) & {"NARRATIVE_SHORT", "SERIES_LONGFORM", "HYBRID"})
        )
        if (rich_copy_module in modules) != expected_rich_copy:
            raise AssertionError(
                "narrative copywriting guidance must load only for narrative STORY routes"
            )
        if delivery_mode == "TEXT_ONLY_ECO_TEST" and modules != [
            "references/TEXT_ONLY_ECO_WORKFLOW.md"
        ]:
            raise AssertionError("text-only ECO must route to the self-contained contract only")
        estimate(root, modules)

    incompatible_cases = (
        (("SERIES_LONGFORM",), "EDIT", False, False),
        (("SERIES_LONGFORM",), "PROMPT", True, False),
        (("SERIES_LONGFORM",), "PROMPT", False, True),
        (("NARRATIVE_SHORT",), "PROMPT", False, False),
    )
    for project_types, task, current_facts, needs_director_source in incompatible_cases:
        try:
            resolve_route(
                root,
                project_types,
                task,
                delivery_mode="TEXT_ONLY_ECO_TEST",
                current_facts=current_facts,
                needs_director_source=needs_director_source,
                registry=registry,
            )
        except RouteError as exc:
            if exc.code != "E_ROUTE_CONSTRAINT":
                raise
        else:
            raise AssertionError("incompatible text-only ECO route was not rejected")

    eco_modules = resolve_route(
        root,
        ("SERIES_LONGFORM",),
        "PROMPT",
        delivery_mode="TEXT_ONLY_ECO_TEST",
        registry=registry,
    )["modules"]
    entry_tokens = estimate(root, ["SKILL.md"])["estimated_tokens"]
    eco_module_tokens = estimate(root, eco_modules)["estimated_tokens"]
    within = execute_budget(
        registry,
        profile="STANDARD",
        entry_tokens=1000,
        module_tokens=4000,
        source_tokens=3000,
        state_tokens=2000,
    )
    overflow = execute_budget(
        registry,
        profile="RESTRICTED",
        entry_tokens=entry_tokens,
        module_tokens=eco_module_tokens,
        source_tokens=1000,
        state_tokens=1000,
    )
    unknown = execute_budget(
        registry,
        profile="UNDECLARED_PROFILE",
        entry_tokens=1000,
        module_tokens=1000,
        source_tokens=1000,
        state_tokens=1000,
    )
    if (
        within["status"] != "WITHIN_BUDGET"
        or within["minimum_host_reserve_ratio"] != 0.25
        or not within["host_reserve_requirement_met"]
    ):
        raise AssertionError("STANDARD budget did not retain the hard caps and 25% host reserve")
    if (
        overflow["status"] != "SPLIT_REQUIRED"
        or overflow["selected_capabilities_removed"] != 0
        or not overflow["checkpoint_required"]
        or overflow["minimum_split_batches"] < 2
    ):
        raise AssertionError("overflow must split without deleting selected capabilities")
    if unknown["profile"] != "RESTRICTED" or not unknown["profile_fallback_applied"]:
        raise AssertionError("unknown budget profiles must fall back to RESTRICTED")
    with tempfile.TemporaryDirectory(prefix="alpha7-master-read-mode-") as temp_dir:
        disguised = Path(temp_dir) / "ordinary-notes.md"
        disguised.write_text(
            "<!-- SILVER_SHOWRUNNER_READ_MODE: ONEFILE_ONLY -->\nrenamed.md\n",
            encoding="utf-8",
        )
        try:
            enforce_no_onefile_conflicts(Path(temp_dir))
        except RouteError as exc:
            if exc.code != "E_READ_MODE_CONFLICT":
                raise
        else:
            raise AssertionError("content-detected disguised ONEFILE was not rejected")

    checked = len(cases) + len(incompatible_cases) + 4
    print(
        f"SELF_TEST_PASS: {checked}/{checked}; registry={registry['schema_version']}; "
        "normal development files scripts/tests/schemas=0; hard budget caps active; "
        "host reserve>=25%; overflow=SPLIT_REQUIRED with checkpoint; "
        "unknown profile=RESTRICTED; disguised ONEFILE=E_READ_MODE_CONFLICT"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--project-type",
        action="append",
        dest="project_types",
        help="Repeat for a genuine combined route, for example culture plus brand.",
    )
    parser.add_argument("--task")
    parser.add_argument(
        "--delivery-mode",
        default="MEDIA_ENABLED",
        help="Use TEXT_ONLY_ECO_TEST for the self-contained low-context text pilot route.",
    )
    parser.add_argument("--current-facts", action="store_true")
    parser.add_argument("--minors", action="store_true")
    parser.add_argument("--needs-director-source", action="store_true")
    parser.add_argument("--trigger", action="append", dest="triggers", default=[])
    parser.add_argument(
        "--budget-profile",
        default="STANDARD",
        help="RESTRICTED, STANDARD, or ENHANCED; definitions come from the registry.",
    )
    parser.add_argument("--source-visible-tokens", type=int, default=0)
    parser.add_argument("--state-visible-tokens", type=int, default=0)
    parser.add_argument("--source-visible-file", type=Path, action="append", default=[])
    parser.add_argument("--state-visible-file", type=Path, action="append", default=[])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()

    try:
        if args.self_test:
            return self_test(root)
        if not args.project_types or not args.task:
            parser.error("--project-type and --task are required unless --self-test is used")
        if args.source_visible_tokens < 0 or args.state_visible_tokens < 0:
            raise RouteError("E_BUDGET_INPUT", "visible token counts cannot be negative")

        registry = load_registry(root)
        route = resolve_route(
            root,
            args.project_types,
            args.task,
            delivery_mode=args.delivery_mode,
            current_facts=args.current_facts,
            minors=args.minors,
            needs_director_source=args.needs_director_source,
            triggers=args.triggers,
            registry=registry,
        )
        entry_estimate = estimate(root, [route["entry"]])
        module_estimate = estimate(root, route["modules"])
        source_file_estimate = estimate_visible_files(args.source_visible_file)
        state_file_estimate = estimate_visible_files(args.state_visible_file)
        source_tokens = args.source_visible_tokens + source_file_estimate["estimated_tokens"]
        state_tokens = args.state_visible_tokens + state_file_estimate["estimated_tokens"]
        budget = execute_budget(
            registry,
            profile=args.budget_profile,
            entry_tokens=entry_estimate["estimated_tokens"],
            module_tokens=module_estimate["estimated_tokens"],
            source_tokens=source_tokens,
            state_tokens=state_tokens,
        )
    except (RouteError, FileNotFoundError, OSError, UnicodeError) as exc:
        parser.error(str(exc))

    route.update(
        {
            "onefile_policy": "DO_NOT_LOAD_WITH_MODULES",
            "entry_estimate": entry_estimate,
            "module_estimate": module_estimate,
            "source_visible_file_estimate": source_file_estimate,
            "state_visible_file_estimate": state_file_estimate,
            "combined_estimate": {
                "module_count": entry_estimate["module_count"]
                + module_estimate["module_count"],
                "source_bytes": entry_estimate["source_bytes"]
                + module_estimate["source_bytes"],
                "source_characters": entry_estimate["source_characters"]
                + module_estimate["source_characters"],
                "estimated_tokens": entry_estimate["estimated_tokens"]
                + module_estimate["estimated_tokens"],
            },
            "budget": budget,
        }
    )
    print(json.dumps(route, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
