#!/usr/bin/env python3
"""Render a read-only natural-Chinese creator view from stable machine JSON.

This helper does not change, translate, or write back machine fields.  The
default creator view intentionally omits internal status codes, error codes,
IDs, hashes, JSON keys, script paths, and commands.  User-authored excerpts and
official model names may be passed separately as explicit display context.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


sys.dont_write_bytecode = True

DEFAULT_PROFILE = "CREATOR_SIMPLE"
DEFAULT_DICTIONARY = (
    Path(__file__).resolve().parents[1]
    / "schemas"
    / "user_presentation_dictionary.json"
)

STATUS_ALIASES = {
    "PASSED": "PASS",
    "VALID": "PASS",
    "SUCCEEDED": "PASS",
    "FAILED": "FAIL",
    "INVALID": "FAIL",
    "NOT_EXECUTED": "NOT_RUN",
    "QA_NOT_EXECUTED": "NOT_RUN",
}

INTERNAL_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("error_code", re.compile(r"(?<![A-Za-z0-9])E_[A-Z0-9_]+(?![A-Za-z0-9])")),
    (
        "machine_status_word",
        re.compile(
            r"(?<![A-Za-z0-9])(?:PASS|FAIL|VALID|INVALID|CURRENT|ACCEPTED|"
            r"COMMITTED|PENDING|BLOCKED|COMPLETE|NOT_RUN|NOT_TESTED|"
            r"NOT_REVIEWED|REVIEW_REQUIRED)(?![A-Za-z0-9])"
        ),
    ),
    (
        "prompt_layer_code",
        re.compile(r"(?<![A-Za-z0-9])(?:MP|TP|NEP|PP)(?![A-Za-z0-9])"),
    ),
    (
        "machine_status",
        re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?![A-Za-z0-9])"),
    ),
    (
        "internal_id",
        re.compile(
            r"(?<![A-Za-z0-9])(?:U|SRC|SC|SQ|B|MP|TP|NEP|PP|PQ|PQR|ART|"
            r"CL|TR|NEG|RISK|PSA|BT|EV|TXT|ASSET|DLG|NAR|OBS|RUN|TASK|"
            r"GATE|SHOT|SH|BEAT)[-_]?\d+(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
    ("sha256", re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")),
    (
        "json_key",
        re.compile(r"[\"'][A-Za-z_][A-Za-z0-9_.-]*[\"']\s*:"),
    ),
    (
        "machine_field",
        re.compile(r"(?<![A-Za-z0-9])[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?![A-Za-z0-9])"),
    ),
    (
        "script_path",
        re.compile(
            r"(?i)(?:(?:[A-Za-z]:)?(?:[\\/][^\s<>:\"|?*]+)*[\\/]scripts[\\/]"
            r"[^\s<>:\"|?*]+\.py|(?<![A-Za-z0-9])scripts[\\/][^\s<>:\"|?*]+\.py|"
            r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_.-]+\.py(?![A-Za-z0-9_.-]))"
        ),
    ),
)

ERROR_CATEGORY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("E_SOURCE", "source"),
    ("E_DIALOGUE", "source"),
    ("E_QUOTE", "source"),
    ("E_PROMPT", "prompt"),
    ("PQ_", "prompt"),
    ("E_OUTPUT", "output"),
    ("E_TEMP", "output"),
    ("E_RUNTIME", "runtime"),
    ("E_BUILD", "runtime"),
    ("E_EDITORIAL", "editorial"),
    ("E_CONTENT", "editorial"),
    ("E_MEDIA", "media"),
    ("E_FFMPEG", "media"),
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_dictionary(path: Path = DEFAULT_DICTIONARY) -> dict[str, Any]:
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError("presentation dictionary must be a JSON object")
    if data.get("default_profile") != DEFAULT_PROFILE:
        raise ValueError("presentation dictionary default profile is incompatible")
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or DEFAULT_PROFILE not in profiles:
        raise ValueError("presentation dictionary omits the creator-simple profile")
    return data


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalized_status(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "UNKNOWN"
    status = value.strip().upper()
    return STATUS_ALIASES.get(status, status)


def _known_axis_text(dictionary: Mapping[str, Any], axis: str, status: Any) -> str:
    axis_map = _mapping(_mapping(dictionary.get("axes")).get(axis))
    normalized = _normalized_status(status)
    value = axis_map.get(normalized, axis_map.get("UNKNOWN"))
    if not isinstance(value, str) or not value:
        raise ValueError(f"presentation dictionary omits fallback for axis {axis}")
    return value


def _collect_error_codes(machine_data: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    summary = _mapping(machine_data.get("run_summary"))
    sources: Iterable[Any] = (
        _mapping(machine_data.get("validation_result")).get("error_codes"),
        _mapping(summary.get("actual_validation")).get("error_codes"),
        summary.get("open_items"),
        machine_data.get("errors"),
    )
    for source in sources:
        for item in _sequence(source):
            if isinstance(item, str) and item:
                if item.startswith(("E_", "PQ_")):
                    result.append(item)
            elif isinstance(item, Mapping):
                code = item.get("code")
                if isinstance(code, str) and code:
                    result.append(code)
    return sorted(set(result))


def _validation_failed(machine_data: Mapping[str, Any], error_codes: Sequence[str]) -> bool:
    if error_codes:
        return True
    summary = _mapping(machine_data.get("run_summary"))
    for record in (
        _mapping(machine_data.get("validation_result")),
        _mapping(summary.get("actual_validation")),
    ):
        valid = record.get("valid")
        if valid is False:
            return True
        count = record.get("error_count")
        if isinstance(count, int) and count > 0:
            return True
    return False


def _axis_statuses(
    machine_data: Mapping[str, Any], *, validation_failed: bool
) -> dict[str, str]:
    summary = _mapping(machine_data.get("run_summary"))
    validation = _mapping(machine_data.get("validation_result"))
    actual = _mapping(summary.get("actual_validation"))

    structural = _first_string(
        summary.get("structural_validation_status"),
        machine_data.get("structural_validation_status"),
    )
    if validation_failed:
        structural = "FAIL"
    elif structural is None:
        quality_scope = _first_string(
            summary.get("quality_scope"), machine_data.get("quality_scope")
        )
        valid = actual.get("valid") if isinstance(actual.get("valid"), bool) else validation.get("valid")
        if quality_scope == "CONTRACT_STRUCTURAL" and isinstance(valid, bool):
            structural = "PASS" if valid else "FAIL"

    content_self_review = _first_string(
        summary.get("content_self_review_status"),
        machine_data.get("content_self_review_status"),
    )

    editorial = _first_string(
        summary.get("editorial_review_status"),
        machine_data.get("editorial_review_status"),
    )
    if editorial is None and _first_string(
        summary.get("content_readiness"), machine_data.get("content_readiness")
    ) == "REVIEW_REQUIRED":
        editorial = "REVIEW_REQUIRED"

    production = _first_string(
        summary.get("production_validation"),
        machine_data.get("production_validation"),
        actual.get("production_validation"),
        validation.get("production_validation"),
    )

    return {
        "structural": _normalized_status(structural),
        "content_self_review": _normalized_status(content_self_review),
        "editorial_review": _normalized_status(editorial),
        "production_validation": _normalized_status(production),
    }


def _join_chinese(items: Sequence[str]) -> str:
    unique = list(dict.fromkeys(item for item in items if item))
    if not unique:
        return ""
    if len(unique) == 1:
        return unique[0]
    return "、".join(unique[:-1]) + "和" + unique[-1]


def _excluded_scope_text(
    machine_data: Mapping[str, Any], dictionary: Mapping[str, Any]
) -> str | None:
    summary = _mapping(machine_data.get("run_summary"))
    stage_status = _mapping(summary.get("stage_status")) or _mapping(machine_data.get("stage_status"))
    labels = _mapping(dictionary.get("stage_labels"))
    excluded: list[str] = []
    for stage, status in stage_status.items():
        if status == "EXCLUDED_BY_USER":
            label = labels.get(stage)
            if isinstance(label, str) and label:
                excluded.append(label)
    if not excluded:
        return None
    prefix = _mapping(dictionary.get("fallbacks")).get("excluded_scope_prefix")
    if not isinstance(prefix, str) or not prefix:
        prefix = "按你的要求，本轮没有执行"
    return f"{prefix}{_join_chinese(excluded)}"


def _replace_sensitive_fragments(text: str, replacement: str) -> str:
    output = text
    for _, pattern in INTERNAL_LEAK_PATTERNS:
        output = pattern.sub(replacement, output)
    output = re.sub(r"[ \t\f\v]+", " ", output)
    output = re.sub(r" *\r?\n *", "\n", output).strip(" ；;，,\r\n")
    return output


def sanitize_display_text(
    text: Any,
    dictionary: Mapping[str, Any],
    *,
    allowed_fragments: Sequence[str] = (),
) -> str:
    """Clean non-verbatim display text without touching the machine record."""

    if not isinstance(text, str) or not text.strip():
        return ""
    fallbacks = _mapping(dictionary.get("fallbacks"))
    replacement = fallbacks.get("hidden_technical_detail")
    if not isinstance(replacement, str) or not replacement:
        replacement = "技术细节已放入机器记录"
    protected = text.strip()
    placeholders: list[tuple[str, str]] = []
    for index, fragment in enumerate(
        sorted(
            (item for item in allowed_fragments if isinstance(item, str) and item),
            key=len,
            reverse=True,
        )
    ):
        marker = f"\ue000{index}\ue001"
        if fragment in protected:
            protected = protected.replace(fragment, marker)
            placeholders.append((marker, fragment))
    cleaned = _replace_sensitive_fragments(protected, replacement)
    for marker, fragment in placeholders:
        cleaned = cleaned.replace(marker, fragment)
    return cleaned or replacement


def find_internal_leaks(text: str, *, allowed_fragments: Sequence[str] = ()) -> list[str]:
    """Return leak categories after masking explicitly allowed verbatim fragments."""

    masked = text
    for fragment in sorted(
        (item for item in allowed_fragments if isinstance(item, str) and item),
        key=len,
        reverse=True,
    ):
        masked = masked.replace(fragment, "《允许保留的用户文字》")
    return sorted({name for name, pattern in INTERNAL_LEAK_PATTERNS if pattern.search(masked)})


def assert_creator_safe(text: str, *, allowed_fragments: Sequence[str] = ()) -> None:
    """Fail closed when a creator-facing document exposes machine-only details."""

    leaks = find_internal_leaks(text, allowed_fragments=allowed_fragments)
    if leaks:
        raise ValueError("creator view contains hidden machine details: " + ",".join(leaks))


def _error_category_text(error_codes: Sequence[str], dictionary: Mapping[str, Any]) -> str | None:
    if not error_codes:
        return None
    categories: list[str] = []
    for code in error_codes:
        category = "generic"
        for prefix, candidate in ERROR_CATEGORY_PREFIXES:
            if code.startswith(prefix):
                category = candidate
                break
        categories.append(category)
    messages = _mapping(dictionary.get("error_categories"))
    rendered = [messages.get(category) for category in dict.fromkeys(categories)]
    natural = [item for item in rendered if isinstance(item, str) and item]
    return _join_chinese(natural) if natural else None


def _display_context(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("display context must be a JSON object")
    return value


def render_creator_simple(
    machine_data: Mapping[str, Any],
    *,
    dictionary: Mapping[str, Any] | None = None,
    display_context: Mapping[str, Any] | None = None,
) -> str:
    """Return five natural-Chinese information blocks without mutating input."""

    if not isinstance(machine_data, Mapping):
        raise ValueError("machine data must be a JSON object")
    dictionary = dictionary or load_dictionary()
    context = _display_context(display_context)
    labels = _mapping(dictionary.get("labels"))
    fallbacks = _mapping(dictionary.get("fallbacks"))
    error_codes = _collect_error_codes(machine_data)
    failed = _validation_failed(machine_data, error_codes)
    axes = _axis_statuses(machine_data, validation_failed=failed)
    project_status = _first_string(
        machine_data.get("project_status"),
        _mapping(machine_data.get("status_contract")).get("text_end_state"),
    )

    verdicts = _mapping(dictionary.get("project_verdicts"))
    completed_map = _mapping(dictionary.get("project_completed"))
    if failed:
        verdict = fallbacks.get("validation_failed")
    else:
        verdict = verdicts.get(project_status, fallbacks.get("unknown_verdict"))
    if not isinstance(verdict, str) or not verdict:
        raise ValueError("presentation dictionary omits verdict fallback")

    completed_override = sanitize_display_text(context.get("completed"), dictionary)
    completed = completed_override or completed_map.get(
        project_status, fallbacks.get("unknown_completed")
    )
    if not isinstance(completed, str) or not completed:
        raise ValueError("presentation dictionary omits completed fallback")

    axis_texts = [
        _known_axis_text(dictionary, "structural", axes["structural"]),
        _known_axis_text(
            dictionary, "content_self_review", axes["content_self_review"]
        ),
        _known_axis_text(dictionary, "editorial_review", axes["editorial_review"]),
        _known_axis_text(
            dictionary, "production_validation", axes["production_validation"]
        ),
    ]
    excluded = _excluded_scope_text(machine_data, dictionary)
    if excluded:
        axis_texts.append(excluded)
    status_text = "；".join(axis_texts) + "。"

    artifact = sanitize_display_text(context.get("main_artifact"), dictionary)
    if not artifact:
        artifact = fallbacks.get("missing_artifact")
    if not isinstance(artifact, str) or not artifact:
        raise ValueError("presentation dictionary omits artifact fallback")
    source_excerpt = context.get("user_source_excerpt")
    if isinstance(source_excerpt, str) and source_excerpt:
        artifact += f"；用户原文：“{source_excerpt}”"
    official_model = context.get("official_model_name")
    if isinstance(official_model, str) and official_model:
        artifact += f"；正式模型名称：{official_model}"
    artifact = artifact.rstrip("。") + "。"

    next_override = sanitize_display_text(context.get("next_step"), dictionary)
    if next_override:
        next_step = next_override
    elif failed or project_status == "PILOT_REWORK_REQUIRED":
        next_step = fallbacks.get("rework_next_step")
        detail = _error_category_text(error_codes, dictionary)
        if detail:
            next_step = f"{detail}；{next_step}"
    elif axes["editorial_review"] in {"NOT_REVIEWED", "REVIEW_REQUIRED", "FAIL"}:
        next_step = fallbacks.get("editorial_next_step")
    elif axes["structural"] == "UNKNOWN" or axes["production_validation"] == "UNKNOWN":
        next_step = fallbacks.get("unknown_next_step")
    elif axes["production_validation"] == "NOT_TESTED":
        next_step = fallbacks.get("production_next_step")
    else:
        next_step = fallbacks.get("continue_next_step")
    if not isinstance(next_step, str) or not next_step:
        raise ValueError("presentation dictionary omits next-step fallback")
    next_step = next_step.rstrip("。") + "。"

    lines = [
        f"{labels['verdict']}：{verdict}",
        f"{labels['completed']}：{completed}",
        f"{labels['status']}：{status_text}",
        f"{labels['artifact']}：{artifact}",
        f"{labels['next_step']}：{next_step}",
    ]
    rendered = "\n".join(lines)
    allowed_fragments = [
        value
        for value in (source_excerpt, official_model)
        if isinstance(value, str) and value
    ]
    assert_creator_safe(rendered, allowed_fragments=allowed_fragments)
    return rendered


def render_creator_view(
    machine_data: Mapping[str, Any],
    *,
    profile: str = DEFAULT_PROFILE,
    dictionary: Mapping[str, Any] | None = None,
    display_context: Mapping[str, Any] | None = None,
) -> str:
    if profile != DEFAULT_PROFILE:
        raise ValueError("only the creator-simple profile is available before integration freeze")
    return render_creator_simple(
        machine_data,
        dictionary=dictionary,
        display_context=display_context,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="machine JSON to render without modification")
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    parser.add_argument("--display-context", type=Path)
    parser.add_argument("--profile", default=DEFAULT_PROFILE, choices=(DEFAULT_PROFILE,))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    machine_data = _load_json(args.input)
    display_context = _load_json(args.display_context) if args.display_context else None
    before = copy.deepcopy(machine_data)
    rendered = render_creator_view(
        machine_data,
        profile=args.profile,
        dictionary=load_dictionary(args.dictionary),
        display_context=display_context,
    )
    if machine_data != before:
        raise RuntimeError("presentation rendering changed the machine record")
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
