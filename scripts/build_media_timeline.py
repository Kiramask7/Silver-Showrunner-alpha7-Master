#!/usr/bin/env python3
"""Build the Silver Showrunner canonical media timeline.

This script is intentionally local and deterministic.  It validates a source
manifest, resolves local asset paths, records file receipts and emits a render
contract.  It never calls FFmpeg, Remotion, Whisper, a browser or a network
service, and therefore never claims that a video has been rendered or checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "silver-showrunner/media-timeline@1"
SOURCE_SCHEMA = "silver-showrunner/media-source@1"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")

ASSET_KINDS = {"video", "audio", "image", "subtitle"}
TRACK_KINDS = {"video", "audio", "overlay", "subtitle"}
RIGHTS_STATES = {"CLEAR", "REVIEW", "BLOCK", "UNKNOWN"}
ENGINES = {"AUTO", "FFMPEG", "REMOTION"}
SUBTITLE_SOURCES = {
    "NONE",
    "SCRIPT_DRAFT",
    "PROVIDER_TIMESTAMPS",
    "WHISPER",
    "MANUAL_VERIFIED",
}
TRACK_COMPATIBILITY = {
    "video": {"video", "image"},
    "overlay": {"video", "image"},
    "audio": {"audio"},
    "subtitle": {"subtitle"},
}


class ManifestError(ValueError):
    """Raised when the source manifest cannot form a safe canonical timeline."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ManifestError(
            f"{field} 必须是 1-128 位安全 ID，只能包含字母、数字、点、冒号、下划线或连字符"
        )
    return value


def as_number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ManifestError(f"{field} 必须是数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"{field} 必须是数字") from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ManifestError(f"{field} 不能是 NaN 或无穷大")
    if minimum is not None and number < minimum:
        raise ManifestError(f"{field} 不能小于 {minimum}")
    return number


def as_integer(value: Any, field: str, *, minimum: int | None = None) -> int:
    number = as_number(value, field, minimum=minimum)
    if not number.is_integer():
        raise ManifestError(f"{field} 必须是整数")
    return int(number)


def as_string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ManifestError(f"{field} 必须是非空字符串数组")
    return list(dict.fromkeys(item.strip() for item in value))


def resolve_local_path(base: Path, raw: Any, field: str) -> tuple[str, Path]:
    if not isinstance(raw, str) or not raw.strip():
        raise ManifestError(f"{field} 必须是本地文件路径")
    declared = raw.strip()
    lowered = declared.lower()
    if "\x00" in declared:
        raise ManifestError(f"{field} 包含非法空字符")
    if lowered.startswith(("http://", "https://", "data:", "file://")):
        raise ManifestError(f"{field} 不允许 URL；请先把素材下载到本地并登记来源")
    if declared.startswith(("\\\\", "//")):
        raise ManifestError(f"{field} 不允许网络共享路径；请先复制到本地工作区")
    path = Path(declared)
    if not path.is_absolute() and not WINDOWS_DRIVE_RE.match(declared):
        path = base / path
    return declared, path.resolve(strict=False)


def normalize_transition(value: Any, field: str) -> dict[str, Any] | None:
    if value in (None, {}, "cut"):
        return None
    if isinstance(value, str):
        value = {"type": value, "duration": 0.25}
    if not isinstance(value, dict):
        raise ManifestError(f"{field} 必须是对象、字符串或 null")
    transition_type = str(value.get("type") or "cut").strip().lower()
    allowed = {"fade", "crossfade", "dip_to_black", "wipe", "cut"}
    if transition_type not in allowed:
        raise ManifestError(f"{field}.type 不支持：{transition_type}")
    if transition_type == "cut":
        return None
    duration = as_number(value.get("duration", 0.25), f"{field}.duration", minimum=0.001)
    return {"type": transition_type, "duration": round(duration, 6)}


def normalize_assets(
    assets: Any, base: Path, hash_files: bool
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(assets, list) or not assets:
        raise ManifestError("assets 必须是至少包含一项的数组")
    normalized: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(assets):
        field = f"assets[{index}]"
        if not isinstance(raw, dict):
            raise ManifestError(f"{field} 必须是对象")
        asset_id = require_id(raw.get("id"), f"{field}.id")
        if asset_id in by_id:
            raise ManifestError(f"重复资产 ID：{asset_id}")
        kind = str(raw.get("kind") or "").strip().lower()
        if kind not in ASSET_KINDS:
            raise ManifestError(f"{field}.kind 不支持：{kind}")
        declared, resolved = resolve_local_path(base, raw.get("path"), f"{field}.path")
        rights_state = str(raw.get("rights_status") or "UNKNOWN").strip().upper()
        if rights_state not in RIGHTS_STATES:
            raise ManifestError(f"{field}.rights_status 不支持：{rights_state}")
        evidence_ids = as_string_list(raw.get("rights_evidence_ids"), f"{field}.rights_evidence_ids")
        observation_ids = as_string_list(raw.get("observation_ids"), f"{field}.observation_ids")
        present = resolved.is_file()
        receipt: dict[str, Any] = {
            "file_state": "FILE_PRESENT" if present else "FILE_MISSING",
            "size_bytes": resolved.stat().st_size if present else None,
            "sha256": sha256_file(resolved) if present and hash_files else None,
            "hash_state": "CALCULATED" if present and hash_files else "NOT_REQUESTED",
        }
        asset = {
            "id": asset_id,
            "kind": kind,
            "version": str(raw.get("version") or "UNVERSIONED"),
            "declared_path": declared,
            "resolved_path": str(resolved),
            "rights_status": rights_state,
            "rights_evidence_ids": evidence_ids,
            "observation_ids": observation_ids,
            "receipt": receipt,
        }
        normalized.append(asset)
        by_id[asset_id] = asset
    return normalized, by_id


def normalize_tracks(
    tracks: Any, assets: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], float, list[str]]:
    if not isinstance(tracks, list) or not tracks:
        raise ManifestError("tracks 必须是至少包含一项的数组")
    normalized: list[dict[str, Any]] = []
    track_ids: set[str] = set()
    item_ids: set[str] = set()
    total_duration = 0.0
    warnings: list[str] = []

    for track_index, raw_track in enumerate(tracks):
        field = f"tracks[{track_index}]"
        if not isinstance(raw_track, dict):
            raise ManifestError(f"{field} 必须是对象")
        track_id = require_id(raw_track.get("id"), f"{field}.id")
        if track_id in track_ids:
            raise ManifestError(f"重复轨道 ID：{track_id}")
        track_ids.add(track_id)
        kind = str(raw_track.get("kind") or "").strip().lower()
        if kind not in TRACK_KINDS:
            raise ManifestError(f"{field}.kind 不支持：{kind}")
        items = raw_track.get("items")
        if not isinstance(items, list):
            raise ManifestError(f"{field}.items 必须是数组")
        allow_overlap = bool(raw_track.get("allow_overlap", kind in {"audio", "overlay"}))
        cursor = 0.0
        normalized_items: list[dict[str, Any]] = []
        for item_index, raw_item in enumerate(items):
            item_field = f"{field}.items[{item_index}]"
            if not isinstance(raw_item, dict):
                raise ManifestError(f"{item_field} 必须是对象")
            item_id = require_id(raw_item.get("id"), f"{item_field}.id")
            if item_id in item_ids:
                raise ManifestError(f"重复时间线项目 ID：{item_id}")
            item_ids.add(item_id)
            asset_id = require_id(raw_item.get("asset_id"), f"{item_field}.asset_id")
            if asset_id not in assets:
                raise ManifestError(f"{item_field} 引用了不存在的资产：{asset_id}")
            asset_kind = assets[asset_id]["kind"]
            if asset_kind not in TRACK_COMPATIBILITY[kind]:
                raise ManifestError(
                    f"{item_field} 的 {asset_kind} 资产不能放入 {kind} 轨道"
                )
            source_in = as_number(raw_item.get("source_in", 0), f"{item_field}.source_in", minimum=0)
            duration_raw = raw_item.get("duration")
            if duration_raw is None and raw_item.get("source_out") is not None:
                source_out = as_number(raw_item.get("source_out"), f"{item_field}.source_out", minimum=0)
                duration_raw = source_out - source_in
            duration = as_number(duration_raw, f"{item_field}.duration", minimum=0.001)
            start = as_number(raw_item.get("start", cursor), f"{item_field}.start", minimum=0)
            end = start + duration
            transition_in = normalize_transition(raw_item.get("transition_in"), f"{item_field}.transition_in")
            transition_out = normalize_transition(raw_item.get("transition_out"), f"{item_field}.transition_out")
            for transition, name in ((transition_in, "transition_in"), (transition_out, "transition_out")):
                if transition and transition["duration"] >= duration:
                    raise ManifestError(f"{item_field}.{name}.duration 必须小于项目时长")
            layer = as_integer(raw_item.get("layer", 0), f"{item_field}.layer")
            effects = raw_item.get("effects", [])
            if not isinstance(effects, list):
                raise ManifestError(f"{item_field}.effects 必须是数组")
            item = {
                "id": item_id,
                "asset_id": asset_id,
                "start": round(start, 6),
                "end": round(end, 6),
                "duration": round(duration, 6),
                "source_in": round(source_in, 6),
                "layer": layer,
                "gain_db": round(as_number(raw_item.get("gain_db", 0), f"{item_field}.gain_db"), 3),
                "transition_in": transition_in,
                "transition_out": transition_out,
                "effects": effects,
            }
            normalized_items.append(item)
            cursor = max(cursor, end)
            total_duration = max(total_duration, end)

        by_time = sorted(normalized_items, key=lambda item: (item["start"], item["end"], item["id"]))
        if not allow_overlap:
            for previous, current in zip(by_time, by_time[1:]):
                if current["start"] < previous["end"] - 1e-6:
                    raise ManifestError(
                        f"轨道 {track_id} 禁止重叠，但 {previous['id']} 与 {current['id']} 发生重叠"
                    )
        elif kind == "video" and any(
            current["start"] < previous["end"] - 1e-6
            for previous, current in zip(by_time, by_time[1:])
        ):
            warnings.append(f"视频轨道 {track_id} 含显式重叠，渲染适配器必须解析层级和转场")

        normalized.append(
            {
                "id": track_id,
                "kind": kind,
                "enabled": bool(raw_track.get("enabled", True)),
                "allow_overlap": allow_overlap,
                "items": normalized_items,
            }
        )
    return normalized, round(total_duration, 6), warnings


def choose_engine(source: dict[str, Any], tracks: list[dict[str, Any]]) -> tuple[str, str]:
    render = source.get("render") if isinstance(source.get("render"), dict) else {}
    preferred = str(render.get("preferred_engine") or "AUTO").strip().upper()
    if preferred not in ENGINES:
        raise ManifestError(f"render.preferred_engine 不支持：{preferred}")
    if preferred != "AUTO":
        return preferred, "USER_OR_PROJECT_SELECTED"
    needs_motion = bool(render.get("requires_motion_graphics"))
    if not needs_motion:
        needs_motion = any(
            item.get("effects")
            for track in tracks
            for item in track.get("items", [])
            if track.get("kind") == "overlay"
        )
    return ("REMOTION", "MOTION_GRAPHICS_REQUIRED") if needs_motion else ("FFMPEG", "LINEAR_MEDIA_BASELINE")


def build_timeline(source: dict[str, Any], source_path: Path, *, hash_files: bool = False) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise ManifestError("输入必须是 JSON 对象")
    if source.get("schema") not in (None, SOURCE_SCHEMA):
        raise ManifestError(f"不支持的输入 schema：{source.get('schema')}")
    project_id = require_id(source.get("project_id"), "project_id")
    timeline_id = require_id(source.get("timeline_id"), "timeline_id")
    version = str(source.get("version") or "v0.1")
    fps = as_number(source.get("fps", 25), "fps", minimum=1)
    resolution = source.get("resolution") or {"width": 1080, "height": 1920}
    if not isinstance(resolution, dict):
        raise ManifestError("resolution 必须是对象")
    width = as_integer(resolution.get("width"), "resolution.width", minimum=16)
    height = as_integer(resolution.get("height"), "resolution.height", minimum=16)

    assets, assets_by_id = normalize_assets(source.get("assets"), source_path.parent, hash_files)
    tracks, total_duration, track_warnings = normalize_tracks(source.get("tracks"), assets_by_id)
    if total_duration <= 0:
        raise ManifestError("时间线总时长必须大于 0")
    engine, engine_basis = choose_engine(source, tracks)

    render = source.get("render") if isinstance(source.get("render"), dict) else {}
    output_declared, output_resolved = resolve_local_path(
        source_path.parent,
        render.get("output_path") or f"renders/{project_id}_{version}.mp4",
        "render.output_path",
    )
    input_paths = {Path(asset["resolved_path"]) for asset in assets}
    if output_resolved in input_paths:
        raise ManifestError("render.output_path 不能覆盖任何输入素材")
    subtitle_policy = source.get("subtitle_policy") if isinstance(source.get("subtitle_policy"), dict) else {}
    subtitle_source = str(subtitle_policy.get("source") or "NONE").strip().upper()
    if subtitle_source not in SUBTITLE_SOURCES:
        raise ManifestError(f"subtitle_policy.source 不支持：{subtitle_source}")
    speech_expected = bool(source.get("speech_expected", False))
    audio_required = bool(source.get("audio_required", speech_expected))

    missing_assets = [asset["id"] for asset in assets if asset["receipt"]["file_state"] == "FILE_MISSING"]
    rights_blocked = [asset["id"] for asset in assets if asset["rights_status"] == "BLOCK"]
    rights_review = [
        asset["id"]
        for asset in assets
        if asset["rights_status"] in {"UNKNOWN", "REVIEW"}
        or (asset["rights_status"] == "CLEAR" and not asset["rights_evidence_ids"])
    ]
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = [{"code": "TRACK_WARNING", "message": item} for item in track_warnings]
    if missing_assets:
        blockers.append({"code": "MEDIA_FILE_MISSING", "asset_ids": missing_assets})
    if rights_blocked:
        blockers.append({"code": "RIGHTS_BLOCK", "asset_ids": rights_blocked})
    if rights_review:
        warnings.append({"code": "RIGHTS_REVIEW_REQUIRED", "asset_ids": rights_review})

    if blockers:
        render_readiness = "BLOCKED"
    elif rights_review:
        render_readiness = "INTERNAL_PREVIEW_ONLY"
    else:
        render_readiness = "READY_FOR_RENDER"

    body: dict[str, Any] = {
        "schema": SCHEMA,
        "project_id": project_id,
        "timeline_id": timeline_id,
        "version": version,
        "source_manifest": {
            "path": str(source_path.resolve(strict=False)),
            "sha256": sha256_bytes(canonical_json(source)),
        },
        "timebase": {"fps": fps, "unit": "seconds"},
        "resolution": {"width": width, "height": height},
        "total_duration": total_duration,
        "speech_expected": speech_expected,
        "audio_required": audio_required,
        "assets": assets,
        "tracks": tracks,
        "subtitle_policy": {
            "source": subtitle_source,
            "burn_in": bool(subtitle_policy.get("burn_in", True)),
            "language": str(subtitle_policy.get("language") or "zh-CN"),
            "semantic_review_required": bool(subtitle_policy.get("semantic_review_required", True)),
        },
        "audio_policy": {
            "target_lufs": as_number(
                (source.get("audio_policy") or {}).get("target_lufs", -14)
                if isinstance(source.get("audio_policy"), dict)
                else -14,
                "audio_policy.target_lufs",
            ),
            "true_peak_dbtp": as_number(
                (source.get("audio_policy") or {}).get("true_peak_dbtp", -1)
                if isinstance(source.get("audio_policy"), dict)
                else -1,
                "audio_policy.true_peak_dbtp",
            ),
        },
        "render_job": {
            "engine": engine,
            "selection_basis": engine_basis,
            "output_declared_path": output_declared,
            "output_resolved_path": str(output_resolved),
            "container": str(render.get("container") or "mp4").lower(),
            "video_codec": str(render.get("video_codec") or "h264").lower(),
            "audio_codec": str(render.get("audio_codec") or "aac").lower(),
            "execution_mode": "ARGV_ONLY_NO_SHELL",
            "execution_status": "NOT_EXECUTED",
            "execution_receipt_id": None,
        },
        "optional_editor_adapters": as_string_list(
            source.get("optional_editor_adapters"), "optional_editor_adapters"
        ),
        "dependency_contract": {
            "renderer": engine,
            "technical_probe": "FFPROBE",
            "caption_alignment": "WHISPER" if subtitle_source == "WHISPER" else subtitle_source,
            "network_install_allowed": False,
        },
        "rights_summary": {
            "recorded_state": "BLOCK" if rights_blocked else ("REVIEW" if rights_review else "CLEAR"),
            "blocked_asset_ids": rights_blocked,
            "review_asset_ids": rights_review,
            "legal_opinion_provided": False,
        },
        "readiness": {
            "timeline_spec_status": "SPEC_READY",
            "render_readiness": render_readiness,
            "blockers": blockers,
            "warnings": warnings,
        },
        "workflow_status": {
            "spec_status": "SPEC_READY",
            "execution_status": "NOT_EXECUTED",
            "observation_status": "NOT_APPLICABLE",
            "qa_status": "NOT_APPLICABLE",
            "publication_status": "RELEASE_NOT_READY",
            "learning_status": "NO_REAL_DATA",
            "status_basis": {
                "execution_artifact_ids": [],
                "observation_ids": [],
                "qa_gate_ids": [],
                "release_gate_ids": [],
                "publication_ids": [],
                "learning_ids": [],
            },
        },
        "truth_boundary": {
            "timeline_built": True,
            "media_rendered": False,
            "media_observed": False,
            "qa_executed": False,
            "release_ready": False,
        },
    }
    body["timeline_sha256"] = sha256_bytes(canonical_json(body))
    return body


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_timeline_output_path(path: Path, timeline: dict[str, Any]) -> None:
    resolved = path.resolve(strict=False)
    protected = {
        Path(str(asset.get("resolved_path") or "")).resolve(strict=False)
        for asset in timeline.get("assets", [])
    }
    render_output = (timeline.get("render_job") or {}).get("output_resolved_path")
    if render_output:
        protected.add(Path(str(render_output)).resolve(strict=False))
    if resolved in protected:
        raise ManifestError("时间线 JSON 输出不能覆盖输入素材或计划成片")


def run_self_test() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="silver-media-timeline-") as temp:
        root = Path(temp)
        (root / "media").mkdir()
        (root / "media" / "shot.mp4").write_bytes(b"not-real-media")
        source_path = root / "source.json"
        source = {
            "schema": SOURCE_SCHEMA,
            "project_id": "demo",
            "timeline_id": "TL-001",
            "version": "v0.1",
            "speech_expected": False,
            "assets": [
                {
                    "id": "VID-001",
                    "kind": "video",
                    "path": "media/shot.mp4",
                    "rights_status": "CLEAR",
                    "rights_evidence_ids": ["EV-RIGHTS-001"],
                }
            ],
            "tracks": [
                {
                    "id": "V1",
                    "kind": "video",
                    "items": [{"id": "CLIP-001", "asset_id": "VID-001", "duration": 2.0}],
                }
            ],
            "render": {"preferred_engine": "AUTO", "output_path": "renders/final.mp4"},
            "optional_editor_adapters": ["JIANYING", "VIDEOCUT"],
        }
        built = build_timeline(source, source_path, hash_files=True)
        assert built["readiness"]["render_readiness"] == "READY_FOR_RENDER"
        assert built["workflow_status"]["execution_status"] == "NOT_EXECUTED"
        assert built["truth_boundary"]["media_rendered"] is False
        assert built["assets"][0]["receipt"]["hash_state"] == "CALCULATED"
        assert built["render_job"]["engine"] == "FFMPEG"
        assert built["optional_editor_adapters"] == ["JIANYING", "VIDEOCUT"]
        try:
            validate_timeline_output_path(root / "media" / "shot.mp4", built)
        except ManifestError:
            checks += 1
        else:
            raise AssertionError("timeline JSON was allowed to overwrite an input asset")
        checks += 6

        rights_review = json.loads(json.dumps(source))
        rights_review["assets"][0]["rights_evidence_ids"] = []
        built_review = build_timeline(rights_review, source_path)
        assert built_review["readiness"]["render_readiness"] == "INTERNAL_PREVIEW_ONLY"
        assert built_review["rights_summary"]["recorded_state"] == "REVIEW"
        assert built_review["rights_summary"]["legal_opinion_provided"] is False
        checks += 3

        missing = json.loads(json.dumps(source))
        missing["assets"][0]["path"] = "media/missing.mp4"
        built_missing = build_timeline(missing, source_path)
        assert built_missing["readiness"]["render_readiness"] == "BLOCKED"
        assert built_missing["truth_boundary"]["media_rendered"] is False
        checks += 2

        remote = json.loads(json.dumps(source))
        remote["assets"][0]["path"] = "https://example.com/shot.mp4"
        try:
            build_timeline(remote, source_path)
        except ManifestError:
            checks += 1
        else:
            raise AssertionError("remote URL was not rejected")

        overlap = json.loads(json.dumps(source))
        overlap["tracks"][0]["items"].append(
            {"id": "CLIP-002", "asset_id": "VID-001", "start": 1.0, "duration": 2.0}
        )
        try:
            build_timeline(overlap, source_path)
        except ManifestError:
            checks += 1
        else:
            raise AssertionError("forbidden overlap was not rejected")

        overwrite = json.loads(json.dumps(source))
        overwrite["render"]["output_path"] = "media/shot.mp4"
        try:
            build_timeline(overwrite, source_path)
        except ManifestError:
            checks += 1
        else:
            raise AssertionError("render output was allowed to overwrite an input asset")

        invalid_effects = json.loads(json.dumps(source))
        invalid_effects["tracks"][0]["items"][0]["effects"] = "fade"
        try:
            build_timeline(invalid_effects, source_path)
        except ManifestError:
            checks += 1
        else:
            raise AssertionError("non-list effects were silently accepted")

    print(f"PASS: build_media_timeline self-test ({checks} checks)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="构建银幕总控标准媒体时间线")
    parser.add_argument("--input", type=Path, help="media-source JSON")
    parser.add_argument("--output", type=Path, help="输出 media-timeline JSON")
    parser.add_argument("--hash-files", action="store_true", help="计算现有本地素材 SHA-256")
    parser.add_argument("--strict-assets", action="store_true", help="素材缺失时写出报告后返回非零")
    parser.add_argument("--self-test", action="store_true", help="运行纯本地自测")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    if not args.input or not args.output:
        parser.error("除 --self-test 外，必须同时提供 --input 与 --output")
    if args.input.resolve(strict=False) == args.output.resolve(strict=False):
        parser.error("--output 不能覆盖 --input")
    try:
        source = json.loads(args.input.read_text(encoding="utf-8-sig"))
        timeline = build_timeline(source, args.input, hash_files=args.hash_files)
        validate_timeline_output_path(args.output, timeline)
        write_json(args.output, timeline)
    except (OSError, json.JSONDecodeError, ManifestError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    readiness = timeline["readiness"]["render_readiness"]
    print(
        f"OK: 时间线规格已生成 -> {args.output} | "
        f"render_readiness={readiness} | media_rendered=false"
    )
    if args.strict_assets and readiness == "BLOCKED":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
