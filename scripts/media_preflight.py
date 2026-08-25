#!/usr/bin/env python3
"""Run local prepare/final preflight for the Silver media timeline.

The script may call local executables only with argv lists and ``shell=False``.
It never installs software, opens a browser, renders media, transcribes audio or
publishes anything.  A final report can technically inspect a real file with
ffprobe. Imported receipt/review JSON is treated as self-asserted: the script
can verify structure and exact-content bindings, but cannot claim pipeline
provenance, human observation, subjective QA or release readiness without an
external trust anchor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


TIMELINE_SCHEMA = "silver-showrunner/media-timeline@1"
REPORT_SCHEMA = "silver-showrunner/media-preflight@1"
CAPTION_REVIEW_SCHEMA = "silver-showrunner/caption-review-record@1"
VISUAL_QA_REVIEW_SCHEMA = "silver-showrunner/media-qa-review-record@1"
TIME_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})([,.]\d{1,3})?")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
REVIEW_ID_RE = re.compile(r"^REV-[A-Za-z0-9._:-]+$")
OBSERVATION_ID_RE = re.compile(r"^OBS-[A-Za-z0-9._:-]+$")
GATE_ID_RE = re.compile(r"^G-[A-Za-z0-9._:-]+$")


class PreflightError(ValueError):
    """Raised when the preflight input is malformed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def review_record_sha256(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("review_record_sha256", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def is_aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def normalize_semantic_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"无法读取 JSON：{path}：{exc}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"JSON 顶层必须是对象：{path}")
    return value


def discover_executable(explicit: str | None, name: str) -> str | None:
    if explicit:
        path = Path(explicit).resolve(strict=False)
        return str(path) if path.is_file() else None
    return shutil.which(name)


def command_version(executable: str | None, args: list[str]) -> dict[str, Any]:
    if not executable:
        return {"available": False, "path": None, "version_line": None, "probe_error": None}
    try:
        result = subprocess.run(
            [executable, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            shell=False,
            check=False,
        )
        first_line = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
        return {
            "available": result.returncode == 0,
            "path": executable,
            "version_line": first_line or None,
            "probe_error": None if result.returncode == 0 else f"exit={result.returncode}",
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "path": executable,
            "version_line": None,
            "probe_error": f"{type(exc).__name__}: {exc}",
        }


def remotion_snapshot(
    project: Path | None,
    node_path: str | None,
    pnpm_path: str | None,
    license_evidence: Path | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "project_path": str(project.resolve(strict=False)) if project else None,
        "package_json_present": False,
        "dependency_declared": False,
        "cli_installed": False,
        "license_review_evidence": None,
        "ready": False,
    }
    if not project:
        return result
    package_path = project / "package.json"
    result["package_json_present"] = package_path.is_file()
    if package_path.is_file():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8-sig"))
            dependencies: dict[str, Any] = {}
            for key in ("dependencies", "devDependencies", "optionalDependencies"):
                if isinstance(package.get(key), dict):
                    dependencies.update(package[key])
            result["dependency_declared"] = any(
                name == "remotion" or name.startswith("@remotion/") for name in dependencies
            )
        except (OSError, json.JSONDecodeError):
            pass
    candidates = (
        project / "node_modules" / ".bin" / "remotion.cmd",
        project / "node_modules" / ".bin" / "remotion",
        project / "node_modules" / "@remotion" / "cli" / "package.json",
    )
    result["cli_installed"] = any(path.exists() for path in candidates)
    if license_evidence and license_evidence.is_file():
        result["license_review_evidence"] = {
            "path": str(license_evidence.resolve(strict=False)),
            "sha256": sha256_file(license_evidence),
        }
    result["ready"] = bool(
        result["package_json_present"]
        and result["dependency_declared"]
        and result["cli_installed"]
        and node_path
        and pnpm_path
    )
    return result


def collect_tool_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    ffmpeg = discover_executable(args.ffmpeg, "ffmpeg")
    ffprobe = discover_executable(args.ffprobe, "ffprobe")
    node = discover_executable(args.node, "node")
    pnpm = discover_executable(args.pnpm, "pnpm")
    whisper = discover_executable(args.whisper, "whisper")
    snapshot = {
        "ffmpeg": command_version(ffmpeg, ["-version"]),
        "ffprobe": command_version(ffprobe, ["-version"]),
        "node": command_version(node, ["--version"]),
        "pnpm": command_version(pnpm, ["--version"]),
        "whisper": command_version(whisper, ["--help"]),
    }
    snapshot["remotion"] = remotion_snapshot(
        args.remotion_project,
        node if snapshot["node"]["available"] else None,
        pnpm if snapshot["pnpm"]["available"] else None,
        getattr(args, "remotion_license_evidence", None),
    )
    return snapshot


def ffprobe_media(path: Path, executable: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PreflightError(f"ffprobe 执行失败：{exc}") from exc
    if result.returncode != 0:
        raise PreflightError(f"ffprobe 返回 {result.returncode}：{result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PreflightError("ffprobe 未返回有效 JSON") from exc
    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        duration = None
    first_video = video_streams[0] if video_streams else {}
    return {
        "duration": duration,
        "format_name": fmt.get("format_name"),
        "bit_rate": fmt.get("bit_rate"),
        "video_stream_count": len(video_streams),
        "audio_stream_count": len(audio_streams),
        "width": first_video.get("width"),
        "height": first_video.get("height"),
        "video_codec": first_video.get("codec_name"),
        "pixel_format": first_video.get("pix_fmt"),
        "audio_codecs": [stream.get("codec_name") for stream in audio_streams],
    }


def parse_timecode(value: str) -> float:
    match = TIME_RE.fullmatch(value.strip())
    if not match:
        raise PreflightError(f"无法解析时间码：{value}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    fraction = match.group(4)
    fraction_value = float("0." + fraction[1:]) if fraction else 0.0
    return hours * 3600 + minutes * 60 + seconds + fraction_value


def parse_caption_artifact(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = load_json(path)
        raw_segments = payload.get("segments")
        if raw_segments is None and isinstance(payload.get("subtitles"), list):
            raw_segments = payload["subtitles"]
        if not isinstance(raw_segments, list):
            raise PreflightError("字幕 JSON 缺少 segments[] 或 subtitles[]")
        segments = []
        for index, item in enumerate(raw_segments):
            if not isinstance(item, dict):
                raise PreflightError(f"字幕段 {index} 必须是对象")
            try:
                start = float(item.get("start"))
                end = float(item.get("end"))
            except (TypeError, ValueError) as exc:
                raise PreflightError(f"字幕段 {index} 缺少有效 start/end") from exc
            segments.append({"start": start, "end": end, "text": str(item.get("text") or "").strip()})
        return segments
    if suffix not in {".srt", ".vtt"}:
        raise PreflightError("字幕产物仅支持 .json、.srt 或 .vtt")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    timing_re = re.compile(
        r"(?P<start>(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*"
        r"(?P<end>(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3})"
    )
    lines = text.splitlines()
    segments: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = timing_re.search(lines[index])
        if not match:
            index += 1
            continue
        start = parse_timecode(match.group("start"))
        end = parse_timecode(match.group("end"))
        index += 1
        content: list[str] = []
        while index < len(lines) and lines[index].strip():
            content.append(lines[index].strip())
            index += 1
        segments.append({"start": start, "end": end, "text": " ".join(content).strip()})
    if not segments:
        raise PreflightError("字幕文件中没有可解析的时间段")
    return segments


def validate_caption_segments(
    segments: list[dict[str, Any]], media_duration: float | None, tolerance: float
) -> dict[str, Any]:
    errors: list[str] = []
    previous_start = -1.0
    covered = 0.0
    for index, segment in enumerate(segments):
        start = segment["start"]
        end = segment["end"]
        if start < 0 or end <= start:
            errors.append(f"第 {index + 1} 段时间范围无效")
        if start < previous_start:
            errors.append(f"第 {index + 1} 段开始时间逆序")
        if not segment["text"]:
            errors.append(f"第 {index + 1} 段文本为空")
        if media_duration is not None and end > media_duration + tolerance:
            errors.append(f"第 {index + 1} 段超出成片时长")
        previous_start = start
        covered += max(0.0, end - start)
    return {
        "segment_count": len(segments),
        "first_start": segments[0]["start"] if segments else None,
        "last_end": segments[-1]["end"] if segments else None,
        "covered_seconds": round(covered, 3),
        "coverage_ratio": round(covered / media_duration, 4) if media_duration and media_duration > 0 else None,
        "timecode_status": "PASS" if not errors else "FAIL",
        "semantic_accuracy_status": "NOT_VERIFIED",
        "errors": errors,
    }


def validate_caption_source_text(
    path: Path | None, segments: list[dict[str, Any]]
) -> dict[str, Any]:
    """Deterministically compare cue text with a supplied canonical text artifact.

    This proves only content equality after NFKC/case/punctuation/whitespace
    normalization.  It does not prove that either text matches the spoken audio.
    """

    if not path:
        return {
            "status": "NOT_PROVIDED",
            "machine_verifiable": False,
            "source_path": None,
            "source_sha256": None,
            "errors": [],
        }
    if not path.is_file():
        return {
            "status": "INVALID",
            "machine_verifiable": False,
            "source_path": str(path.resolve(strict=False)),
            "source_sha256": None,
            "errors": ["canonical 字幕源文本文件不存在"],
        }
    try:
        if path.suffix.lower() == ".json":
            payload = load_json(path)
            raw_text = payload.get("text", payload.get("transcript"))
            if raw_text is None and isinstance(payload.get("lines"), list):
                raw_text = "\n".join(str(item) for item in payload["lines"])
            if not isinstance(raw_text, str):
                raise PreflightError("canonical 字幕源 JSON 缺少 text、transcript 或 lines[]")
            source_text = raw_text
        else:
            source_text = path.read_text(encoding="utf-8-sig", errors="strict")
    except (OSError, UnicodeError, PreflightError) as exc:
        return {
            "status": "INVALID",
            "machine_verifiable": False,
            "source_path": str(path.resolve(strict=False)),
            "source_sha256": sha256_file(path),
            "errors": [str(exc)],
        }

    caption_text = "\n".join(str(segment.get("text") or "") for segment in segments)
    normalized_caption = normalize_semantic_text(caption_text)
    normalized_source = normalize_semantic_text(source_text)
    errors: list[str] = []
    if not normalized_caption:
        errors.append("字幕规范化文本为空")
    if not normalized_source:
        errors.append("canonical 字幕源规范化文本为空")
    matches = bool(not errors and normalized_caption == normalized_source)
    return {
        "status": "PASS" if matches else ("MISMATCH" if not errors else "INVALID"),
        "machine_verifiable": not errors,
        "source_path": str(path.resolve(strict=False)),
        "source_sha256": sha256_file(path),
        "normalization": "UNICODE_NFKC_CASEFOLD_ALNUM",
        "caption_normalized_sha256": hashlib.sha256(
            normalized_caption.encode("utf-8")
        ).hexdigest(),
        "source_normalized_sha256": hashlib.sha256(
            normalized_source.encode("utf-8")
        ).hexdigest(),
        "errors": errors,
    }


def validate_review_record_common(
    payload: dict[str, Any],
    *,
    expected_schema: str,
    artifact_sha256: str | None,
    artifact_id: str | None,
    artifact_version: str | None,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if payload.get("schema") != expected_schema:
        errors.append(f"review record schema 必须为 {expected_schema}")
    review_id = payload.get("review_record_id")
    if not isinstance(review_id, str) or not REVIEW_ID_RE.fullmatch(review_id):
        errors.append("review_record_id 缺失或格式无效")
    declared_digest = payload.get("review_record_sha256")
    actual_digest = review_record_sha256(payload)
    if not isinstance(declared_digest, str) or not SHA256_RE.fullmatch(declared_digest):
        errors.append("review_record_sha256 缺失或格式无效")
    elif declared_digest.lower() != actual_digest:
        errors.append("review record 内容已改变，review_record_sha256 不匹配")

    reviewer = payload.get("reviewer")
    if not isinstance(reviewer, dict):
        reviewer = {}
        errors.append("reviewer 必须是对象")
    actor_id = reviewer.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id.strip():
        errors.append("reviewer.actor_id 缺失")
    if reviewer.get("actor_type") not in {"HUMAN", "EXTERNAL_REVIEWER"}:
        errors.append("reviewer.actor_type 必须为 HUMAN 或 EXTERNAL_REVIEWER")
    if reviewer.get("provenance") not in {
        "DIRECT_MEDIA_REVIEW",
        "INDEPENDENT_REVIEW_SERVICE",
    }:
        errors.append("reviewer.provenance 未声明来自本轮制作者之外的媒体复核者")
    if not is_aware_timestamp(payload.get("reviewed_at")):
        errors.append("reviewed_at 必须是带时区的 ISO-8601 时间")
    scope = payload.get("scope")
    if not isinstance(scope, list) or not scope or not all(
        isinstance(item, str) and item.strip() for item in scope
    ):
        errors.append("scope 必须是非空字符串数组")
        scope = []
    elif len(scope) != len(set(scope)):
        errors.append("scope 不得包含重复项")

    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
        errors.append("inputs 必须是对象")
    rendered = inputs.get("rendered")
    if not isinstance(rendered, dict):
        rendered = {}
        errors.append("inputs.rendered 必须是对象")
    if not artifact_sha256 or rendered.get("sha256") != artifact_sha256:
        errors.append("review record 未绑定当前成片 SHA-256")
    if not artifact_id or rendered.get("artifact_id") != artifact_id:
        errors.append("review record 未绑定当前成片 artifact_id")
    if not artifact_version or rendered.get("version") != artifact_version:
        errors.append("review record 未绑定当前时间线版本")

    return errors, {
        "review_record_id": review_id,
        "review_record_sha256": declared_digest,
        "reviewer": reviewer,
        "reviewed_at": payload.get("reviewed_at"),
        "scope": scope,
        "inputs": inputs,
    }


def validate_visual_qa(
    path: Path | None,
    artifact_sha256: str | None,
    artifact_id: str | None,
    artifact_version: str | None,
) -> dict[str, Any]:
    base = {
        "status": "QA_NOT_EXECUTED",
        "evidence_path": None,
        "evidence_class": "NONE",
        "machine_verification_status": "NOT_EXECUTED",
        "attestation_status": "NOT_VERIFIED",
        "can_promote_workflow": False,
        "valid": False,
        "errors": [],
        "observation_ids": [],
        "qa_gate_id": None,
    }
    if not path:
        return base
    base["evidence_path"] = str(path.resolve(strict=False))
    base["evidence_class"] = "IMPORTED_SELF_ASSERTED"
    try:
        payload = load_json(path)
    except PreflightError as exc:
        base["errors"] = [str(exc)]
        base["machine_verification_status"] = "FAIL"
        return base

    status = str(payload.get("qa_status") or "").upper()
    errors, common = validate_review_record_common(
        payload,
        expected_schema=VISUAL_QA_REVIEW_SCHEMA,
        artifact_sha256=artifact_sha256,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
    )
    if status not in {"QA_PASSED", "QA_FAILED", "QA_ACCEPTED_WITH_DEBT"}:
        errors.append("qa_status 无效")

    observations = payload.get("observations")
    observation_ids: list[str] = []
    if not isinstance(observations, list) or not observations:
        errors.append("visual QA record 必须内嵌非空 observations[]")
        observations = []
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            errors.append(f"observations[{index}] 必须是对象")
            continue
        observation_id = observation.get("observation_id")
        if not isinstance(observation_id, str) or not OBSERVATION_ID_RE.fullmatch(
            observation_id
        ):
            errors.append(f"observations[{index}].observation_id 无效")
        elif observation_id in observation_ids:
            errors.append("observations[] 含重复 observation_id")
        else:
            observation_ids.append(observation_id)
        if observation.get("artifact_sha256") != artifact_sha256:
            errors.append(f"observations[{index}] 未绑定当前成片 SHA-256")
        if observation.get("artifact_version") != artifact_version:
            errors.append(f"observations[{index}] 未绑定当前时间线版本")
        if observation.get("observer_actor_id") != (common["reviewer"] or {}).get(
            "actor_id"
        ):
            errors.append(f"observations[{index}] 的 observer 与 reviewer 不一致")
        if observation.get("basis") != "DIRECT_MEDIA_ACCESS":
            errors.append(f"observations[{index}].basis 必须为 DIRECT_MEDIA_ACCESS")
        if not is_aware_timestamp(observation.get("observed_at")):
            errors.append(f"observations[{index}].observed_at 无效")
        if not isinstance(observation.get("findings"), list):
            errors.append(f"observations[{index}].findings 必须是数组")

    gate = payload.get("qa_gate")
    if not isinstance(gate, dict):
        gate = {}
        errors.append("visual QA record 必须内嵌 qa_gate")
    gate_id = gate.get("gate_id")
    if not isinstance(gate_id, str) or not GATE_ID_RE.fullmatch(gate_id):
        errors.append("qa_gate.gate_id 无效")
    if gate.get("evaluation_status") != "EXECUTED":
        errors.append("qa_gate.evaluation_status 必须为 EXECUTED")
    expected_outcome = {
        "QA_PASSED": "PASSED",
        "QA_FAILED": "FAILED",
        "QA_ACCEPTED_WITH_DEBT": "ACCEPTED_WITH_DEBT",
    }.get(status)
    if expected_outcome and gate.get("outcome") != expected_outcome:
        errors.append("qa_gate.outcome 与 qa_status 不一致")
    if gate.get("artifact_sha256") != artifact_sha256:
        errors.append("qa_gate 未绑定当前成片 SHA-256")
    if gate.get("artifact_version") != artifact_version:
        errors.append("qa_gate 未绑定当前时间线版本")
    gate_observation_ids = gate.get("observation_ids")
    if (
        not isinstance(gate_observation_ids, list)
        or not all(isinstance(item, str) for item in gate_observation_ids)
        or set(gate_observation_ids) != set(observation_ids)
    ):
        errors.append("qa_gate.observation_ids 未解析到内嵌 observations[]")
    if not is_aware_timestamp(gate.get("evaluated_at")):
        errors.append("qa_gate.evaluated_at 无效")

    return {
        "status": status or "QA_NOT_EXECUTED",
        "evidence_path": str(path.resolve(strict=False)),
        "evidence_sha256": sha256_file(path),
        "evidence_class": "IMPORTED_SELF_ASSERTED",
        "machine_verification_status": "STRUCTURE_AND_BINDINGS_PASS"
        if not errors
        else "FAIL",
        "attestation_status": "NOT_VERIFIED",
        "can_promote_workflow": False,
        "valid": not errors,
        "errors": errors,
        "observation_ids": observation_ids if not errors else [],
        "qa_gate_id": gate_id if not errors else None,
        **common,
    }


def validate_caption_review(
    path: Path | None,
    caption_sha256: str | None,
    artifact_sha256: str | None,
    artifact_id: str | None,
    artifact_version: str | None,
) -> dict[str, Any]:
    base = {
        "status": "NOT_REVIEWED",
        "evidence_path": None,
        "evidence_class": "NONE",
        "machine_verification_status": "NOT_EXECUTED",
        "attestation_status": "NOT_VERIFIED",
        "can_promote_workflow": False,
        "valid": False,
        "errors": [],
    }
    if not path:
        return base
    base["evidence_path"] = str(path.resolve(strict=False))
    base["evidence_class"] = "IMPORTED_SELF_ASSERTED"
    try:
        payload = load_json(path)
    except PreflightError as exc:
        base["errors"] = [str(exc)]
        base["machine_verification_status"] = "FAIL"
        return base

    status = str(payload.get("status") or "").upper()
    errors, common = validate_review_record_common(
        payload,
        expected_schema=CAPTION_REVIEW_SCHEMA,
        artifact_sha256=artifact_sha256,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
    )
    if status not in {"PASS", "REVIEW", "BLOCK"}:
        errors.append("字幕复核 status 无效")
    caption_input = (common.get("inputs") or {}).get("caption")
    if not isinstance(caption_input, dict):
        caption_input = {}
        errors.append("inputs.caption 必须是对象")
    if not caption_sha256 or caption_input.get("sha256") != caption_sha256:
        errors.append("字幕复核未绑定当前字幕 SHA-256")
    if not isinstance(caption_input.get("version"), str) or not caption_input.get(
        "version"
    ).strip():
        errors.append("inputs.caption.version 缺失")
    return {
        "status": status or "NOT_REVIEWED",
        "evidence_path": str(path.resolve(strict=False)),
        "evidence_sha256": sha256_file(path),
        "evidence_class": "IMPORTED_SELF_ASSERTED",
        "machine_verification_status": "STRUCTURE_AND_BINDINGS_PASS"
        if not errors
        else "FAIL",
        "attestation_status": "NOT_VERIFIED",
        "can_promote_workflow": False,
        "valid": not errors,
        "errors": errors,
        **common,
    }


def validate_execution_receipt(
    path: Path | None,
    timeline: dict[str, Any],
    artifact_sha256: str | None,
    engine: str,
    rendered_path: Path | None,
) -> dict[str, Any]:
    """Validate provenance for an external FFmpeg/Remotion render.

    The receipt is written by the renderer adapter, not by this preflight.  A
    real media file can still be probed without it, but pipeline execution is
    not considered proven merely because an imported JSON binds the exact
    timeline/output hashes.  Without a caller-supplied trust anchor, this
    function can prove consistency only, not that the claimed process ran.
    """

    if not path:
        return {
            "status": "MISSING",
            "evidence_path": None,
            "valid": False,
            "evidence_class": "NONE",
            "consistency_status": "NOT_EXECUTED",
            "attestation_status": "NOT_VERIFIED",
            "can_prove_execution": False,
            "errors": [],
        }
    try:
        payload = load_json(path)
    except PreflightError as exc:
        return {
            "status": "INVALID",
            "evidence_path": str(path.resolve(strict=False)),
            "valid": False,
            "evidence_class": "IMPORTED_SELF_ASSERTED",
            "consistency_status": "FAIL",
            "attestation_status": "NOT_VERIFIED",
            "can_prove_execution": False,
            "errors": [str(exc)],
        }

    errors: list[str] = []
    if payload.get("schema") != "silver-showrunner/media-execution-receipt@1":
        errors.append("execution receipt schema 无效")
    if str(payload.get("engine") or "").upper() != engine:
        errors.append("execution receipt 的 engine 与时间线不一致")
    if payload.get("timeline_sha256") != timeline.get("timeline_sha256"):
        errors.append("execution receipt 未绑定当前时间线 SHA-256")
    if not artifact_sha256 or payload.get("output_sha256") != artifact_sha256:
        errors.append("execution receipt 未绑定当前成片 SHA-256")
    if payload.get("exit_code") != 0:
        errors.append("execution receipt 未记录成功退出码 0")
    if payload.get("status") != "EXECUTED_SUCCEEDED":
        errors.append("execution receipt 未记录 EXECUTED_SUCCEEDED")
    if payload.get("technical_probe_status") != "PASS":
        errors.append("execution receipt 未通过渲染后的技术探测")
    if payload.get("shell") is not False:
        errors.append("execution receipt 必须明确 shell=false")
    argv = payload.get("argv")
    argv_valid = isinstance(argv, list) and bool(argv) and all(
        isinstance(item, str) and item for item in argv
    )
    if not argv_valid:
        errors.append("execution receipt 缺少非空 argv[]")
    for field in ("executable", "tool_version", "started_at", "finished_at"):
        if not isinstance(payload.get(field), str) or not payload.get(field).strip():
            errors.append(f"execution receipt 缺少 {field}")
    if not is_aware_timestamp(payload.get("started_at")) or not is_aware_timestamp(
        payload.get("finished_at")
    ):
        errors.append("execution receipt 时间必须是带时区的 ISO-8601")
    else:
        started = datetime.fromisoformat(payload["started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(payload["finished_at"].replace("Z", "+00:00"))
        if finished < started:
            errors.append("execution receipt 的 finished_at 早于 started_at")
    if not rendered_path:
        errors.append("无法绑定 execution receipt 的实际输出路径")
    else:
        resolved_rendered = str(rendered_path.resolve(strict=False))
        recorded_output = payload.get("output_path")
        if not isinstance(recorded_output, str) or str(
            Path(recorded_output).resolve(strict=False)
        ).lower() != resolved_rendered.lower():
            errors.append("execution receipt 的 output_path 与当前成片不一致")
        if payload.get("output_size_bytes") != rendered_path.stat().st_size:
            errors.append("execution receipt 的 output_size_bytes 与当前成片不一致")
        if argv_valid:
            if str(Path(argv[-1]).resolve(strict=False)).lower() != resolved_rendered.lower():
                errors.append("execution receipt argv[] 的输出路径与当前成片不一致")
    if argv_valid and isinstance(payload.get("executable"), str):
        if str(Path(argv[0]).resolve(strict=False)).lower() != str(
            Path(payload["executable"]).resolve(strict=False)
        ).lower():
            errors.append("execution receipt argv[0] 与 executable 不一致")

    return {
        "status": "CONSISTENT" if not errors else "INVALID",
        "evidence_path": str(path.resolve(strict=False)),
        "receipt_sha256": sha256_file(path),
        "valid": not errors,
        "evidence_class": "IMPORTED_SELF_ASSERTED",
        "consistency_status": "PASS" if not errors else "FAIL",
        "attestation_status": "NOT_VERIFIED",
        "can_prove_execution": False,
        "errors": errors,
        "engine": payload.get("engine"),
        "tool_version": payload.get("tool_version"),
    }


def add_issue(target: list[dict[str, Any]], code: str, message: str, **details: Any) -> None:
    issue = {"code": code, "message": message}
    issue.update(details)
    target.append(issue)


def evaluate(
    timeline: dict[str, Any],
    timeline_path: Path,
    options: argparse.Namespace,
    tools: dict[str, Any],
    probe_runner: Callable[[Path, str], dict[str, Any]] = ffprobe_media,
) -> dict[str, Any]:
    if timeline.get("schema") != TIMELINE_SCHEMA:
        raise PreflightError(f"不支持的时间线 schema：{timeline.get('schema')}")
    if options.mode not in {"prepare", "final"}:
        raise PreflightError(f"不支持的 mode：{options.mode}")
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    assets = timeline.get("assets") if isinstance(timeline.get("assets"), list) else []
    missing = []
    hash_missing = []
    hash_mismatch = []
    for asset in assets:
        path = Path(str(asset.get("resolved_path") or ""))
        if not path.is_file():
            missing.append(asset.get("id"))
            continue
        expected_hash = (asset.get("receipt") or {}).get("sha256")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            hash_missing.append(asset.get("id"))
            continue
        actual_hash = sha256_file(path)
        if actual_hash.lower() != expected_hash.lower():
            hash_mismatch.append(asset.get("id"))
    if missing:
        add_issue(blockers, "MEDIA_FILE_MISSING", "时间线引用的本地素材缺失", asset_ids=missing)
    if hash_missing:
        add_issue(
            blockers,
            "ASSET_HASH_MISSING",
            "素材未绑定 SHA-256；请用 build_media_timeline.py --hash-files 重新构建执行版时间线",
            asset_ids=hash_missing,
        )
    if hash_mismatch:
        add_issue(
            blockers,
            "ASSET_HASH_MISMATCH",
            "本地素材内容已不同于时间线登记版本",
            asset_ids=hash_mismatch,
        )
    checks.append(
        {
            "name": "local_assets",
            "status": "FAIL" if missing or hash_missing or hash_mismatch else "PASS",
            "asset_count": len(assets),
            "missing_asset_ids": missing,
            "hash_missing_asset_ids": hash_missing,
            "hash_mismatch_asset_ids": hash_mismatch,
        }
    )

    engine = str((timeline.get("render_job") or {}).get("engine") or "FFMPEG").upper()
    if engine == "FFMPEG":
        if not tools["ffmpeg"]["available"]:
            add_issue(blockers, "FFMPEG_MISSING", "FFmpeg 不可用，不能执行真实导出")
        if not tools["ffprobe"]["available"]:
            add_issue(blockers, "FFPROBE_MISSING", "ffprobe 不可用，不能验证输入和成片")
    elif engine == "REMOTION":
        if not tools["remotion"]["ready"]:
            add_issue(
                blockers,
                "REMOTION_NOT_READY",
                "Remotion 项目、依赖或本地 CLI 未就绪；禁止通过 npx 临时联网安装后冒充稳定环境",
            )
        if not tools["ffprobe"]["available"]:
            add_issue(blockers, "FFPROBE_MISSING", "ffprobe 不可用，不能验证 Remotion 成片")
        if tools["remotion"].get("ready") and not tools["remotion"].get("license_review_evidence"):
            add_issue(
                warnings,
                "REMOTION_LICENSE_REVIEW",
                "未提供 Remotion 许可复核证据；请按当前主体资格核对官方许可",
            )
    else:
        add_issue(blockers, "RENDER_ENGINE_INVALID", f"不支持的渲染引擎：{engine}")

    subtitle_source = str((timeline.get("subtitle_policy") or {}).get("source") or "NONE").upper()
    if subtitle_source == "WHISPER":
        if not tools["whisper"]["available"]:
            add_issue(blockers, "WHISPER_MISSING", "时间线指定 Whisper 对轴，但本机 Whisper CLI 不可用")
        if not tools["ffmpeg"]["available"]:
            add_issue(blockers, "WHISPER_FFMPEG_MISSING", "Whisper 依赖 FFmpeg 解码媒体，但本机 FFmpeg 不可用")

    declared_rights_state = str(
        (timeline.get("rights_summary") or {}).get("recorded_state") or "REVIEW"
    ).upper()
    rights_blocked_assets: list[Any] = []
    rights_review_assets: list[Any] = []
    for asset in assets:
        state = str(asset.get("rights_status") or "UNKNOWN").upper()
        evidence_ids = asset.get("rights_evidence_ids")
        if state == "BLOCK":
            rights_blocked_assets.append(asset.get("id"))
        elif state != "CLEAR" or not isinstance(evidence_ids, list) or not evidence_ids:
            rights_review_assets.append(asset.get("id"))
    if declared_rights_state == "BLOCK" or rights_blocked_assets:
        rights_state = "BLOCK"
        add_issue(
            blockers,
            "RIGHTS_BLOCK",
            "时间线含素材许可阻断项",
            asset_ids=rights_blocked_assets,
        )
    elif declared_rights_state != "CLEAR" or rights_review_assets:
        rights_state = "REVIEW"
        add_issue(
            warnings,
            "RIGHTS_REVIEW",
            "素材许可链尚未完整登记；仅可内部预览",
            asset_ids=rights_review_assets,
        )
    else:
        rights_state = "CLEAR"
    checks.append(
        {
            "name": "rights_record",
            "status": rights_state,
            "declared_status": declared_rights_state,
            "blocked_asset_ids": rights_blocked_assets,
            "review_asset_ids": rights_review_assets,
            "legal_opinion": False,
        }
    )

    rendered_receipt: dict[str, Any] | None = None
    execution_receipt: dict[str, Any] | None = None
    media_probe: dict[str, Any] | None = None
    artifact_sha256: str | None = None
    execution_status = "NOT_EXECUTED"
    observation_status = "NOT_APPLICABLE"
    qa_status = "NOT_APPLICABLE"
    observation_ids: list[str] = []
    qa_gate_ids: list[str] = []

    if options.mode == "final":
        if not options.rendered or not options.rendered.is_file():
            add_issue(blockers, "RENDER_OUTPUT_MISSING", "final 模式必须提供真实存在的成片文件")
            execution_status = "NOT_EXECUTED"
            observation_status = "OBSERVATION_PENDING"
            qa_status = "QA_NOT_EXECUTED"
        else:
            artifact_sha256 = sha256_file(options.rendered)
            rendered_receipt = {
                "path": str(options.rendered.resolve(strict=False)),
                "size_bytes": options.rendered.stat().st_size,
                "sha256": artifact_sha256,
                "artifact_id": f"MEDIA-{artifact_sha256[:16]}",
                "provenance": "LOCAL_OUTPUT_OR_IMPORTED_FILE",
            }
            if rendered_receipt["size_bytes"] <= 0:
                add_issue(blockers, "RENDER_OUTPUT_EMPTY", "成片文件为空")
                execution_status = "EXECUTION_PENDING"
            elif tools["ffprobe"]["available"]:
                try:
                    media_probe = probe_runner(options.rendered, tools["ffprobe"]["path"])
                    execution_status = "EXECUTION_PENDING"
                except PreflightError as exc:
                    add_issue(blockers, "FFPROBE_FAILED", str(exc))
                    execution_status = "EXECUTION_PENDING"
            else:
                execution_status = "EXECUTION_PENDING"

            execution_receipt = validate_execution_receipt(
                getattr(options, "execution_receipt", None),
                timeline,
                artifact_sha256,
                engine,
                options.rendered,
            )
            if execution_receipt["valid"] and media_probe is not None:
                execution_status = "EXECUTION_PENDING"
                add_issue(
                    warnings,
                    "EXECUTION_RECEIPT_ASSERTED_ONLY",
                    "导入回执的结构、哈希和输出绑定一致，但没有包外信任锚；只能记为 SELF_ASSERTED_NOT_PROVEN，不能证明本管线已执行",
                )
            elif execution_receipt["status"] == "MISSING":
                add_issue(
                    warnings,
                    "EXECUTION_RECEIPT_MISSING",
                    "成片文件存在且可做技术检查，但缺少绑定时间线与输出哈希的真实导出回执；不得宣称本管线已执行成功",
                )
            else:
                add_issue(
                    blockers,
                    "EXECUTION_RECEIPT_INVALID",
                    "真实导出回执无效或未绑定当前版本",
                    errors=execution_receipt["errors"],
                )

            observation_status = "OBSERVATION_PENDING"
            qa_status = "QA_NOT_EXECUTED"
            if media_probe:
                expected_duration = float(timeline.get("total_duration") or 0)
                actual_duration = media_probe.get("duration")
                if media_probe.get("video_stream_count", 0) < 1:
                    add_issue(blockers, "VIDEO_STREAM_MISSING", "成片没有可用视频流")
                if actual_duration is None or abs(actual_duration - expected_duration) > options.duration_tolerance:
                    add_issue(
                        blockers,
                        "DURATION_MISMATCH",
                        "成片时长与标准时间线不一致",
                        expected=expected_duration,
                        actual=actual_duration,
                        tolerance=options.duration_tolerance,
                    )
                expected_resolution = timeline.get("resolution") or {}
                if (
                    media_probe.get("width") != expected_resolution.get("width")
                    or media_probe.get("height") != expected_resolution.get("height")
                ):
                    add_issue(
                        blockers,
                        "RESOLUTION_MISMATCH",
                        "成片分辨率与标准时间线不一致",
                        expected=expected_resolution,
                        actual={"width": media_probe.get("width"), "height": media_probe.get("height")},
                    )
                if timeline.get("audio_required") and media_probe.get("audio_stream_count", 0) < 1:
                    add_issue(blockers, "AUDIO_STREAM_MISSING", "项目要求音频，但成片没有音频流")

        caption_result: dict[str, Any] = {
            "source": (timeline.get("subtitle_policy") or {}).get("source", "NONE"),
            "artifact": None,
            "validation": None,
            "canonical_text_comparison": {
                "status": "NOT_PROVIDED",
                "machine_verifiable": False,
                "source_path": None,
                "source_sha256": None,
                "errors": [],
            },
            "review": {"status": "NOT_REVIEWED", "valid": False, "errors": []},
        }
        caption_source = str(caption_result["source"]).upper()
        caption_expected = caption_source != "NONE"
        if caption_expected:
            if not options.caption_artifact or not options.caption_artifact.is_file():
                add_issue(blockers, "CAPTION_ARTIFACT_MISSING", "时间线要求字幕，但未提供实际字幕/ASR产物")
            else:
                try:
                    segments = parse_caption_artifact(options.caption_artifact)
                    caption_sha256 = sha256_file(options.caption_artifact)
                    validation = validate_caption_segments(
                        segments,
                        media_probe.get("duration") if media_probe else None,
                        options.duration_tolerance,
                    )
                    caption_result["artifact"] = {
                        "path": str(options.caption_artifact.resolve(strict=False)),
                        "sha256": caption_sha256,
                    }
                    caption_result["validation"] = validation
                    if validation["timecode_status"] != "PASS":
                        add_issue(blockers, "CAPTION_TIMECODE_FAILED", "字幕时间码校验失败", errors=validation["errors"])
                    comparison = validate_caption_source_text(
                        getattr(options, "caption_source_text", None), segments
                    )
                    caption_result["canonical_text_comparison"] = comparison
                    if comparison["status"] == "MISMATCH":
                        add_issue(
                            blockers,
                            "CAPTION_CANONICAL_TEXT_MISMATCH",
                            "字幕文本与提供的 canonical dialogue/transcript 不一致",
                        )
                    elif comparison["status"] == "INVALID":
                        add_issue(
                            blockers,
                            "CAPTION_CANONICAL_TEXT_INVALID",
                            "无法验证 canonical dialogue/transcript",
                            errors=comparison["errors"],
                        )
                    review = validate_caption_review(
                        options.caption_review_evidence,
                        caption_sha256,
                        artifact_sha256,
                        rendered_receipt.get("artifact_id") if rendered_receipt else None,
                        str(timeline.get("version") or "") or None,
                    )
                    caption_result["review"] = review
                    if (timeline.get("subtitle_policy") or {}).get("semantic_review_required", True):
                        if review["valid"] and review["status"] == "BLOCK":
                            add_issue(
                                blockers,
                                "CAPTION_SEMANTIC_REVIEW_BLOCK",
                                "绑定当前成片与字幕的语义复核未通过",
                            )
                        elif review["valid"] and review["status"] == "PASS":
                            validation["semantic_accuracy_status"] = "REVIEW_REQUIRED"
                            add_issue(
                                warnings,
                                "CAPTION_SEMANTIC_REVIEW_ASSERTED_ONLY",
                                "导入的字幕人审记录字段与哈希一致，但未通过包外信任锚验签；不能自动证明语义正确",
                            )
                        else:
                            add_issue(
                                warnings,
                                "CAPTION_SEMANTIC_REVIEW_PENDING",
                                "Whisper/时间码通过不等于文本准确；当前字幕尚未完成绑定成片版本的语义复核",
                            )
                    if caption_source == "SCRIPT_DRAFT":
                        add_issue(
                            warnings,
                            "SCRIPT_CAPTION_TIMES_PROVISIONAL",
                            "剧本估算字幕不是实际音频对轴证据，应使用供应商时间戳或 Whisper 复核",
                        )
                except (OSError, PreflightError) as exc:
                    add_issue(blockers, "CAPTION_PARSE_FAILED", str(exc))
        else:
            caption_result["validation"] = {"timecode_status": "NOT_APPLICABLE"}

        visual_qa = validate_visual_qa(
            options.visual_qa_evidence,
            artifact_sha256,
            rendered_receipt.get("artifact_id") if rendered_receipt else None,
            str(timeline.get("version") or "") or None,
        )
        if visual_qa["valid"]:
            if visual_qa["status"] == "QA_FAILED":
                add_issue(
                    blockers,
                    "VISUAL_QA_REPORTED_FAILURE",
                    "导入复核记录报告视觉 QA 失败；保守阻断，但不把未验签记录升级为已执行 QA",
                )
            else:
                add_issue(
                    warnings,
                    "VISUAL_QA_ASSERTED_ONLY",
                    "导入 QA 记录的结构、内嵌 Observation/Gate 和版本绑定一致，但未通过包外信任锚验签；保持 OBSERVATION_PENDING / QA_NOT_EXECUTED",
                )
        else:
            if visual_qa["errors"]:
                add_issue(warnings, "VISUAL_QA_EVIDENCE_INVALID", "视觉 QA 证据无效", errors=visual_qa["errors"])
            add_issue(
                warnings,
                "VISUAL_QA_NOT_EXECUTED",
                "ffprobe 只验证技术元数据，不能代替逐帧视觉、连续性、节奏和声音检查",
            )
        checks.append({"name": "captions", **caption_result})
        checks.append({"name": "visual_qa", **visual_qa})

    if blockers:
        result_status = "BLOCK"
    elif warnings:
        result_status = "REVIEW"
    else:
        result_status = "PASS" if options.mode == "final" else "READY"

    execution_artifact_ids = (
        [rendered_receipt["artifact_id"]]
        if rendered_receipt and execution_status == "EXECUTED_SUCCEEDED"
        else []
    )
    report = {
        "schema": REPORT_SCHEMA,
        "mode": options.mode.upper(),
        "timeline": {
            "path": str(timeline_path.resolve(strict=False)),
            "timeline_id": timeline.get("timeline_id"),
            "version": timeline.get("version"),
            "timeline_sha256": timeline.get("timeline_sha256"),
        },
        "result": {
            "status": result_status,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "blockers": blockers,
            "warnings": warnings,
        },
        "tools": tools,
        "checks": checks,
        "rendered_artifact": rendered_receipt,
        "execution_receipt": execution_receipt,
        "technical_probe": media_probe,
        "workflow_status": {
            "spec_status": "SPEC_READY",
            "execution_status": execution_status,
            "observation_status": observation_status,
            "qa_status": qa_status,
            "publication_status": "RELEASE_NOT_READY",
            "learning_status": "NO_REAL_DATA",
            "status_basis": {
                "execution_artifact_ids": execution_artifact_ids,
                "observation_ids": observation_ids,
                "qa_gate_ids": qa_gate_ids,
                "release_gate_ids": [],
                "publication_ids": [],
                "learning_ids": [],
            },
        },
        "truth_boundary": {
            "technical_media_probe_executed": media_probe is not None,
            "execution_receipt_consistent": bool(
                execution_receipt and execution_receipt.get("consistency_status") == "PASS"
            ),
            "pipeline_execution_proven": False,
            "visual_observation_executed": observation_status == "OBSERVED",
            "qa_executed": qa_status not in {"NOT_APPLICABLE", "QA_NOT_EXECUTED"},
            "subjective_review_machine_verified": False,
            "external_attestation_verification_supported": False,
            "overall_release_status": "NOT_DETERMINED_BY_MEDIA_PREFLIGHT",
            "legal_clearance_provided": False,
            "publication_executed": False,
        },
        "next_jobs": {
            "render": None
            if options.mode == "final"
            else {
                "engine": engine,
                "execution": "EXTERNAL_ADAPTER_MUST_USE_ARGV_NO_SHELL",
                "receipt_required": True,
            },
            "whisper": None
            if not timeline.get("speech_expected")
            else {
                "required_when": "provider timestamps unavailable or verification requested",
                "output_formats": ["json", "srt", "vtt"],
                "actual_execution_status": "NOT_EXECUTED_BY_THIS_SCRIPT",
            },
        },
    }
    return report


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fake_tools() -> dict[str, Any]:
    available = {"available": True, "path": "fake", "version_line": "fake 1", "probe_error": None}
    return {
        "ffmpeg": dict(available),
        "ffprobe": dict(available),
        "node": dict(available),
        "pnpm": dict(available),
        "whisper": dict(available),
        "remotion": {
            "project_path": "fake",
            "package_json_present": True,
            "dependency_declared": True,
            "cli_installed": True,
            "license_review_evidence": {"path": "fake", "sha256": "fake"},
            "ready": True,
        },
    }


def run_self_test() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="silver-media-preflight-") as temp:
        root = Path(temp)
        media = root / "clip.mp4"
        media.write_bytes(b"input")
        timeline_path = root / "timeline.json"
        timeline = {
            "schema": TIMELINE_SCHEMA,
            "timeline_id": "TL-001",
            "version": "v1",
            "timeline_sha256": "abc",
            "total_duration": 2.0,
            "resolution": {"width": 1080, "height": 1920},
            "speech_expected": False,
            "audio_required": False,
            "assets": [
                {
                    "id": "VID-1",
                    "resolved_path": str(media),
                    "rights_status": "CLEAR",
                    "rights_evidence_ids": ["EV-RIGHTS-001"],
                    "receipt": {"sha256": sha256_file(media)},
                }
            ],
            "render_job": {"engine": "FFMPEG"},
            "rights_summary": {"recorded_state": "CLEAR"},
            "subtitle_policy": {"source": "NONE", "semantic_review_required": True},
        }
        timeline_path.write_text(json.dumps(timeline), encoding="utf-8")
        prepare_options = SimpleNamespace(
            mode="prepare",
            rendered=None,
            caption_artifact=None,
            caption_review_evidence=None,
            visual_qa_evidence=None,
            duration_tolerance=0.25,
        )
        prepared = evaluate(timeline, timeline_path, prepare_options, fake_tools())
        assert prepared["result"]["status"] == "READY"
        assert prepared["workflow_status"]["execution_status"] == "NOT_EXECUTED"
        assert prepared["truth_boundary"]["visual_observation_executed"] is False
        checks += 3

        rights_missing = json.loads(json.dumps(timeline))
        rights_missing["assets"][0]["rights_evidence_ids"] = []
        rights_review = evaluate(
            rights_missing,
            timeline_path,
            prepare_options,
            fake_tools(),
        )
        assert rights_review["result"]["status"] == "REVIEW"
        assert rights_review["checks"][1]["legal_opinion"] is False
        checks += 2

        whisper_timeline = json.loads(json.dumps(timeline))
        whisper_timeline["speech_expected"] = True
        whisper_timeline["subtitle_policy"]["source"] = "WHISPER"
        tools_without_whisper = fake_tools()
        tools_without_whisper["whisper"] = {
            "available": False,
            "path": None,
            "version_line": None,
            "probe_error": None,
        }
        whisper_blocked = evaluate(
            whisper_timeline,
            timeline_path,
            prepare_options,
            tools_without_whisper,
        )
        assert whisper_blocked["result"]["status"] == "BLOCK"
        assert any(
            item["code"] == "WHISPER_MISSING"
            for item in whisper_blocked["result"]["blockers"]
        )
        checks += 2

        missing_timeline = json.loads(json.dumps(timeline))
        missing_timeline["assets"][0]["resolved_path"] = str(root / "missing.mp4")
        blocked = evaluate(missing_timeline, timeline_path, prepare_options, fake_tools())
        assert blocked["result"]["status"] == "BLOCK"
        assert blocked["workflow_status"]["execution_status"] == "NOT_EXECUTED"
        checks += 2

        changed_media = root / "changed.mp4"
        changed_media.write_bytes(b"changed-input")
        hash_changed_timeline = json.loads(json.dumps(timeline))
        hash_changed_timeline["assets"][0]["resolved_path"] = str(changed_media)
        hash_changed = evaluate(
            hash_changed_timeline,
            timeline_path,
            prepare_options,
            fake_tools(),
        )
        assert hash_changed["result"]["status"] == "BLOCK"
        assert any(
            item["code"] == "ASSET_HASH_MISMATCH"
            for item in hash_changed["result"]["blockers"]
        )
        checks += 2

        rendered = root / "final.mp4"
        rendered.write_bytes(b"rendered")
        final_options = SimpleNamespace(
            mode="final",
            rendered=rendered,
            execution_receipt=None,
            caption_artifact=None,
            caption_review_evidence=None,
            visual_qa_evidence=None,
            duration_tolerance=0.25,
        )

        def synthetic_probe(_path: Path, _executable: str) -> dict[str, Any]:
            return {
                "duration": 2.0,
                "format_name": "mov,mp4",
                "bit_rate": "1000",
                "video_stream_count": 1,
                "audio_stream_count": 0,
                "width": 1080,
                "height": 1920,
                "video_codec": "h264",
                "pixel_format": "yuv420p",
                "audio_codecs": [],
            }

        unproven_report = evaluate(
            timeline, timeline_path, final_options, fake_tools(), probe_runner=synthetic_probe
        )
        assert unproven_report["workflow_status"]["execution_status"] == "EXECUTION_PENDING"
        assert unproven_report["truth_boundary"]["pipeline_execution_proven"] is False
        assert unproven_report["result"]["status"] == "REVIEW"
        checks += 3

        rendered_sha256 = sha256_file(rendered)
        rendered_artifact_id = f"MEDIA-{rendered_sha256[:16]}"
        fake_executable = str((root / "ffmpeg").resolve(strict=False))
        receipt = root / "execution-receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema": "silver-showrunner/media-execution-receipt@1",
                    "engine": "FFMPEG",
                    "timeline_sha256": timeline["timeline_sha256"],
                    "output_sha256": rendered_sha256,
                    "status": "EXECUTED_SUCCEEDED",
                    "technical_probe_status": "PASS",
                    "exit_code": 0,
                    "shell": False,
                    "argv": [fake_executable, "-i", str(media), str(rendered)],
                    "executable": fake_executable,
                    "tool_version": "fake 1",
                    "started_at": "2026-08-14T00:00:00Z",
                    "finished_at": "2026-08-14T00:00:02Z",
                    "output_path": str(rendered),
                    "output_size_bytes": rendered.stat().st_size,
                }
            ),
            encoding="utf-8",
        )
        final_options.execution_receipt = receipt
        final_report = evaluate(
            timeline, timeline_path, final_options, fake_tools(), probe_runner=synthetic_probe
        )
        assert final_report["workflow_status"]["execution_status"] == "EXECUTION_PENDING"
        assert final_report["truth_boundary"]["execution_receipt_consistent"] is True
        assert final_report["truth_boundary"]["pipeline_execution_proven"] is False
        assert final_report["workflow_status"]["qa_status"] == "QA_NOT_EXECUTED"
        assert final_report["result"]["status"] == "REVIEW"
        checks += 5

        valid_receipt = json.loads(receipt.read_text(encoding="utf-8"))
        failed_receipt = json.loads(json.dumps(valid_receipt))
        failed_receipt["status"] = "EXECUTED_FAILED"
        failed_receipt["technical_probe_status"] = "FAIL"
        receipt.write_text(json.dumps(failed_receipt), encoding="utf-8")
        failed_report = evaluate(
            timeline, timeline_path, final_options, fake_tools(), probe_runner=synthetic_probe
        )
        assert failed_report["result"]["status"] == "BLOCK"
        assert failed_report["workflow_status"]["execution_status"] == "EXECUTION_PENDING"
        checks += 2

        bad_receipt = json.loads(json.dumps(valid_receipt))
        bad_receipt["output_sha256"] = "0" * 64
        receipt.write_text(json.dumps(bad_receipt), encoding="utf-8")
        bad_report = evaluate(
            timeline, timeline_path, final_options, fake_tools(), probe_runner=synthetic_probe
        )
        assert bad_report["result"]["status"] == "BLOCK"
        assert bad_report["workflow_status"]["execution_status"] == "EXECUTION_PENDING"
        checks += 2

        qa_path = root / "media-qa.json"
        qa_path.write_text(
            json.dumps(
                {
                    "qa_status": "QA_PASSED",
                    "artifact_sha256": "f" * 64,
                    "observation_ids": ["OBS-001"],
                    "qa_gate_id": "GATE-QA-001",
                }
            ),
            encoding="utf-8",
        )
        qa_mismatch = validate_visual_qa(
            qa_path,
            rendered_sha256,
            rendered_artifact_id,
            timeline["version"],
        )
        assert qa_mismatch["valid"] is False
        assert any("SHA-256" in item for item in qa_mismatch["errors"])
        checks += 2

        srt = root / "captions.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,500\n你好\n", encoding="utf-8")
        segments = parse_caption_artifact(srt)
        validated = validate_caption_segments(segments, 2.0, 0.25)
        assert validated["timecode_status"] == "PASS"
        assert validated["semantic_accuracy_status"] == "NOT_VERIFIED"
        checks += 2

        canonical = root / "canonical.txt"
        canonical.write_text("这才是真实对白", encoding="utf-8")
        comparison = validate_caption_source_text(canonical, segments)
        assert comparison["status"] == "MISMATCH"
        canonical.write_text("你好！", encoding="utf-8")
        comparison = validate_caption_source_text(canonical, segments)
        assert comparison["status"] == "PASS"
        assert comparison["machine_verifiable"] is True
        checks += 3

        # A syntactically complete, content-addressed but self-authored review
        # record still cannot prove that a human actually watched/heard media.
        wrong_srt = root / "forged-wrong-caption.srt"
        wrong_srt.write_text(
            "1\n00:00:00,000 --> 00:00:01,500\nTHIS IS NOT THE DIALOGUE\n",
            encoding="utf-8",
        )
        wrong_caption_sha = sha256_file(wrong_srt)
        caption_review_path = root / "forged-caption-review.json"
        caption_review_payload = {
            "schema": CAPTION_REVIEW_SCHEMA,
            "review_record_id": "REV-CAPTION-ATTACK",
            "status": "PASS",
            "reviewer": {
                "actor_id": "ATTACKER-SELF-ASSERTION",
                "actor_type": "HUMAN",
                "provenance": "DIRECT_MEDIA_REVIEW",
            },
            "reviewed_at": "2026-08-14T00:00:03Z",
            "scope": ["CAPTION_SEMANTICS"],
            "inputs": {
                "rendered": {
                    "artifact_id": rendered_artifact_id,
                    "sha256": rendered_sha256,
                    "version": timeline["version"],
                },
                "caption": {
                    "sha256": wrong_caption_sha,
                    "version": f"sha256:{wrong_caption_sha}",
                },
            },
        }
        caption_review_payload["review_record_sha256"] = review_record_sha256(
            caption_review_payload
        )
        caption_review_path.write_text(json.dumps(caption_review_payload), encoding="utf-8")

        visual_review_path = root / "forged-visual-review.json"
        visual_review_payload = {
            "schema": VISUAL_QA_REVIEW_SCHEMA,
            "review_record_id": "REV-VISUAL-ATTACK",
            "qa_status": "QA_PASSED",
            "reviewer": {
                "actor_id": "ATTACKER-SELF-ASSERTION",
                "actor_type": "HUMAN",
                "provenance": "DIRECT_MEDIA_REVIEW",
            },
            "reviewed_at": "2026-08-14T00:00:04Z",
            "scope": ["VISUAL_INTEGRITY", "AUDIO_INTEGRITY", "CONTINUITY_AND_PACING"],
            "inputs": {
                "rendered": {
                    "artifact_id": rendered_artifact_id,
                    "sha256": rendered_sha256,
                    "version": timeline["version"],
                }
            },
            "observations": [
                {
                    "observation_id": "OBS-ATTACK",
                    "artifact_sha256": rendered_sha256,
                    "artifact_version": timeline["version"],
                    "observer_actor_id": "ATTACKER-SELF-ASSERTION",
                    "basis": "DIRECT_MEDIA_ACCESS",
                    "observed_at": "2026-08-14T00:00:04Z",
                    "findings": [],
                }
            ],
            "qa_gate": {
                "gate_id": "G-ATTACK",
                "evaluation_status": "EXECUTED",
                "outcome": "PASSED",
                "artifact_sha256": rendered_sha256,
                "artifact_version": timeline["version"],
                "observation_ids": ["OBS-ATTACK"],
                "evaluated_at": "2026-08-14T00:00:05Z",
            },
        }
        visual_review_payload["review_record_sha256"] = review_record_sha256(
            visual_review_payload
        )
        visual_review_path.write_text(json.dumps(visual_review_payload), encoding="utf-8")

        receipt.write_text(json.dumps(valid_receipt), encoding="utf-8")
        review_timeline = json.loads(json.dumps(timeline))
        review_timeline["subtitle_policy"] = {
            "source": "MANUAL_VERIFIED",
            "semantic_review_required": True,
        }
        final_options.caption_artifact = wrong_srt
        final_options.caption_review_evidence = caption_review_path
        final_options.visual_qa_evidence = visual_review_path
        final_options.caption_source_text = None
        attack_report = evaluate(
            review_timeline,
            timeline_path,
            final_options,
            fake_tools(),
            probe_runner=synthetic_probe,
        )
        warning_codes = {item["code"] for item in attack_report["result"]["warnings"]}
        assert attack_report["result"]["status"] == "REVIEW"
        assert attack_report["workflow_status"]["execution_status"] == "EXECUTION_PENDING"
        assert attack_report["workflow_status"]["observation_status"] == "OBSERVATION_PENDING"
        assert attack_report["workflow_status"]["qa_status"] == "QA_NOT_EXECUTED"
        assert attack_report["truth_boundary"]["pipeline_execution_proven"] is False
        assert attack_report["truth_boundary"]["visual_observation_executed"] is False
        assert attack_report["truth_boundary"]["qa_executed"] is False
        assert attack_report["checks"][2]["review"]["valid"] is True
        assert attack_report["checks"][2]["review"]["can_promote_workflow"] is False
        assert attack_report["checks"][3]["valid"] is True
        assert attack_report["checks"][3]["can_promote_workflow"] is False
        assert {
            "EXECUTION_RECEIPT_ASSERTED_ONLY",
            "CAPTION_SEMANTIC_REVIEW_ASSERTED_ONLY",
            "VISUAL_QA_ASSERTED_ONLY",
        }.issubset(warning_codes)
        checks += 12

    print(f"PASS: media_preflight self-test ({checks} checks)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="银幕总控媒体准备/成片技术预检")
    parser.add_argument("--timeline", type=Path, help="标准 media-timeline JSON")
    parser.add_argument("--mode", choices=("prepare", "final"), default="prepare")
    parser.add_argument("--rendered", type=Path, help="final 模式的真实成片")
    parser.add_argument("--execution-receipt", type=Path, help="渲染适配器写出的真实导出回执 JSON")
    parser.add_argument("--caption-artifact", type=Path, help="Whisper/供应商/人工字幕 JSON、SRT 或 VTT")
    parser.add_argument(
        "--caption-source-text",
        type=Path,
        help="可选 canonical dialogue/transcript 文本或 JSON；只做确定性文本一致性比较",
    )
    parser.add_argument("--caption-review-evidence", type=Path, help="绑定字幕与成片哈希的语义复核 JSON")
    parser.add_argument("--visual-qa-evidence", type=Path, help="绑定成片哈希的视觉 QA JSON")
    parser.add_argument("--remotion-project", type=Path, help="本地 Remotion 项目目录")
    parser.add_argument("--remotion-license-evidence", type=Path, help="Remotion 官方许可复核证据文件")
    parser.add_argument("--duration-tolerance", type=float, default=0.25)
    parser.add_argument("--ffmpeg", help="ffmpeg 可执行文件路径")
    parser.add_argument("--ffprobe", help="ffprobe 可执行文件路径")
    parser.add_argument("--node", help="node 可执行文件路径")
    parser.add_argument("--pnpm", help="pnpm 可执行文件路径")
    parser.add_argument("--whisper", help="whisper 可执行文件路径")
    parser.add_argument("--out", type=Path, help="输出预检报告 JSON")
    parser.add_argument("--self-test", action="store_true", help="运行纯本地自测")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    if not args.timeline or not args.out:
        parser.error("除 --self-test 外，必须同时提供 --timeline 与 --out")
    if args.duration_tolerance < 0:
        parser.error("--duration-tolerance 不能小于 0")
    try:
        timeline = load_json(args.timeline)
        tools = collect_tool_snapshot(args)
        report = evaluate(timeline, args.timeline, args, tools)
        write_json(args.out, report)
    except (OSError, PreflightError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    status = report["result"]["status"]
    print(
        f"{status}: 媒体预检 -> {args.out} | "
        f"execution={report['workflow_status']['execution_status']} | "
        f"qa={report['workflow_status']['qa_status']} | release=NOT_DETERMINED"
    )
    return 0 if status in {"READY", "PASS"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
