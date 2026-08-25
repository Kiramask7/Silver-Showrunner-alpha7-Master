#!/usr/bin/env python3
"""Render the strict FFmpeg baseline of a Silver Showrunner media timeline.

The executor supports only a deterministic, explicitly validated linear subset:
one contiguous picture track made from video or still images, plus zero or more
audio tracks.  It refuses overlays, subtitles, transitions, effects, picture
gaps and Remotion jobs instead of silently degrading them.

Actual execution requires a matching READY PREPARE report and explicit local
FFmpeg/ffprobe executable paths.  Commands are always argv lists with
``shell=False``.  The script never installs software, accesses the network,
opens a browser, publishes, or overwrites an existing file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


TIMELINE_SCHEMA = "silver-showrunner/media-timeline@1"
PREFLIGHT_SCHEMA = "silver-showrunner/media-preflight@1"
PLAN_SCHEMA = "silver-showrunner/ffmpeg-render-plan@1"
RECEIPT_SCHEMA = "silver-showrunner/media-execution-receipt@1"
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
NEAR_SILENCE_DBFS = -70.0


class RenderContractError(ValueError):
    """The job is unsafe, stale or malformed."""


class UnsupportedTimeline(RenderContractError):
    """The timeline requires a capability outside the strict baseline."""


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_exit_code(value: int) -> int:
    """Normalize Windows' unsigned 32-bit native error codes to signed values."""

    if 0x80000000 <= value <= 0xFFFFFFFF:
        return value - 0x100000000
    return value


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderContractError(f"无法读取 {label} JSON：{path}：{exc}") from exc
    if not isinstance(value, dict):
        raise RenderContractError(f"{label} JSON 顶层必须是对象")
    return value


def write_json_new(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise RenderContractError(f"拒绝覆盖已有文件：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise RenderContractError(f"拒绝覆盖已有文件：{path}") from exc


def as_number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool):
        raise RenderContractError(f"{field} 必须是有限数字")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RenderContractError(f"{field} 必须是有限数字") from exc
    if not math.isfinite(number):
        raise RenderContractError(f"{field} 不能是 NaN 或无穷大")
    if minimum is not None and number < minimum:
        raise RenderContractError(f"{field} 不能小于 {minimum}")
    if maximum is not None and number > maximum:
        raise RenderContractError(f"{field} 不能大于 {maximum}")
    return number


def format_number(value: float) -> str:
    rendered = f"{value:.6f}".rstrip("0").rstrip(".")
    return rendered or "0"


def normalize_path(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def require_local_file(path_value: Any, field: str) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise RenderContractError(f"{field} 缺少本地文件路径")
    raw = path_value.strip()
    lowered = raw.lower()
    if lowered.startswith(("http://", "https://", "data:", "file://")):
        raise RenderContractError(f"{field} 不允许 URL")
    if raw.startswith(("\\\\", "//")):
        raise RenderContractError(f"{field} 不允许网络共享路径")
    path = Path(raw).resolve(strict=False)
    if not path.is_file():
        raise RenderContractError(f"{field} 文件不存在：{path}")
    return path


def validate_tool_executables(ffmpeg: Path, ffprobe: Path) -> None:
    if os.name == "nt" and (
        ffmpeg.suffix.lower() != ".exe" or ffprobe.suffix.lower() != ".exe"
    ):
        raise RenderContractError(
            "Windows 下只接受显式 .exe 工具路径；拒绝 .bat/.cmd/脚本包装器"
        )


def verify_timeline_integrity(timeline: dict[str, Any]) -> str:
    if timeline.get("schema") != TIMELINE_SCHEMA:
        raise RenderContractError(f"不支持的 timeline schema：{timeline.get('schema')}")
    expected = timeline.get("timeline_sha256")
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise RenderContractError("timeline_sha256 缺失或格式无效")
    body = dict(timeline)
    body.pop("timeline_sha256", None)
    actual = sha256_bytes(canonical_json(body))
    if actual.lower() != expected.lower():
        raise RenderContractError("时间线内容已改变，timeline_sha256 不匹配")
    return actual


def tool_snapshot(
    executable: Path,
    runner: Callable[[list[str], float], subprocess.CompletedProcess[str]],
) -> dict[str, Any]:
    result = runner([str(executable), "-version"], 10.0)
    output = (result.stdout or "") + "\n" + (result.stderr or "")
    first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
    returncode = normalize_exit_code(result.returncode)
    if returncode != 0 or not first_line:
        raise RenderContractError(
            f"工具不可执行：{executable}，exit={returncode}"
        )
    return {
        "path": str(executable),
        "version_line": first_line,
        "available": True,
    }


def run_command(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


def ffprobe_media(
    path: Path,
    executable: Path,
    timeout: float,
    runner: Callable[[list[str], float], subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, Any]:
    argv = [
        str(executable),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = runner(argv, timeout)
    returncode = normalize_exit_code(result.returncode)
    if returncode != 0:
        raise RenderContractError(
            f"ffprobe 失败：{path}，exit={returncode}：{(result.stderr or '').strip()}"
        )
    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError as exc:
        raise RenderContractError(f"ffprobe 未返回有效 JSON：{path}") from exc
    streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
    fmt = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    video = [item for item in streams if item.get("codec_type") == "video"]
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    try:
        duration = float(fmt.get("duration"))
    except (TypeError, ValueError):
        duration = None
    first_video = video[0] if video else {}
    return {
        "path": str(path),
        "duration": duration,
        "format_name": fmt.get("format_name"),
        "video_stream_count": len(video),
        "audio_stream_count": len(audio),
        "width": first_video.get("width"),
        "height": first_video.get("height"),
        "video_codec": first_video.get("codec_name"),
        "audio_codecs": [item.get("codec_name") for item in audio],
    }


def verify_prepare_report(
    report: dict[str, Any],
    timeline: dict[str, Any],
    ffmpeg: dict[str, Any],
    ffprobe: dict[str, Any],
) -> None:
    if report.get("schema") != PREFLIGHT_SCHEMA:
        raise RenderContractError("PREPARE report schema 无效")
    if str(report.get("mode") or "").upper() != "PREPARE":
        raise RenderContractError("执行器只接受 PREPARE 模式报告")
    if (report.get("result") or {}).get("status") != "READY":
        raise RenderContractError("PREPARE 未达到 READY，禁止执行 FFmpeg")
    report_timeline = report.get("timeline") or {}
    for key in ("timeline_id", "version", "timeline_sha256"):
        if report_timeline.get(key) != timeline.get(key):
            raise RenderContractError(f"PREPARE 未绑定当前时间线字段：{key}")
    if (report.get("workflow_status") or {}).get("execution_status") != "NOT_EXECUTED":
        raise RenderContractError("PREPARE report 的 execution_status 必须为 NOT_EXECUTED")
    report_tools = report.get("tools") or {}
    for name, current in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        recorded = report_tools.get(name) or {}
        if recorded.get("available") is not True:
            raise RenderContractError(f"PREPARE 未确认 {name} 可用")
        if normalize_path(recorded.get("path") or "") != normalize_path(current["path"]):
            raise RenderContractError(f"{name} 路径与 PREPARE 不一致")
        if recorded.get("version_line") != current.get("version_line"):
            raise RenderContractError(f"{name} 版本与 PREPARE 不一致；请重新运行 PREPARE")


def verify_assets(timeline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_assets = timeline.get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        raise RenderContractError("时间线缺少 assets[]")
    assets: dict[str, dict[str, Any]] = {}
    for index, asset in enumerate(raw_assets):
        if not isinstance(asset, dict):
            raise RenderContractError(f"assets[{index}] 必须是对象")
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id or asset_id in assets:
            raise RenderContractError(f"assets[{index}].id 缺失或重复")
        path = require_local_file(asset.get("resolved_path"), f"assets[{index}].resolved_path")
        expected = (asset.get("receipt") or {}).get("sha256")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise RenderContractError(f"资产 {asset_id} 未绑定有效 SHA-256")
        actual = sha256_file(path)
        if actual.lower() != expected.lower():
            raise RenderContractError(f"资产 {asset_id} 的 SHA-256 已改变")
        rights = str(asset.get("rights_status") or "UNKNOWN").upper()
        evidence = asset.get("rights_evidence_ids")
        if rights != "CLEAR" or not isinstance(evidence, list) or not evidence:
            raise RenderContractError(f"资产 {asset_id} 的素材许可记录未达到可执行条件")
        normalized = dict(asset)
        normalized["_path"] = path
        normalized["_sha256"] = actual
        assets[asset_id] = normalized
    return assets


def reject_item_complexity(item: dict[str, Any], field: str) -> None:
    if item.get("transition_in") or item.get("transition_out"):
        raise UnsupportedTimeline(f"UNSUPPORTED：{field} 含转场；请使用专用适配器")
    if item.get("effects"):
        raise UnsupportedTimeline(f"UNSUPPORTED：{field} 含 effects；禁止静默丢弃")


def validate_linear_subset(
    timeline: dict[str, Any], assets: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    render = timeline.get("render_job") or {}
    if str(render.get("engine") or "").upper() != "FFMPEG":
        raise UnsupportedTimeline("UNSUPPORTED：当前时间线不是 FFMPEG 引擎")
    if str(render.get("container") or "").lower() != "mp4":
        raise UnsupportedTimeline("UNSUPPORTED：线性基线当前只支持 MP4")
    if str(render.get("video_codec") or "").lower() not in {"h264", "libx264"}:
        raise UnsupportedTimeline("UNSUPPORTED：线性基线当前只支持 H.264/libx264")
    if str(render.get("audio_codec") or "").lower() != "aac":
        raise UnsupportedTimeline("UNSUPPORTED：线性基线当前只支持 AAC")

    resolution = timeline.get("resolution") or {}
    width = int(as_number(resolution.get("width"), "resolution.width", minimum=16, maximum=8192))
    height = int(as_number(resolution.get("height"), "resolution.height", minimum=16, maximum=8192))
    if width != float(resolution.get("width")) or height != float(resolution.get("height")):
        raise RenderContractError("分辨率必须是整数")
    fps = as_number((timeline.get("timebase") or {}).get("fps"), "timebase.fps", minimum=1, maximum=120)
    total = as_number(timeline.get("total_duration"), "total_duration", minimum=0.001, maximum=86400)

    tracks = timeline.get("tracks")
    if not isinstance(tracks, list):
        raise RenderContractError("时间线缺少 tracks[]")
    enabled = [track for track in tracks if isinstance(track, dict) and track.get("enabled", True)]
    video_tracks = [track for track in enabled if track.get("kind") == "video"]
    if len(video_tracks) != 1:
        raise UnsupportedTimeline("UNSUPPORTED：线性基线要求恰好一个启用的视频轨")
    for track in enabled:
        if track.get("kind") in {"overlay", "subtitle"} and track.get("items"):
            raise UnsupportedTimeline(
                f"UNSUPPORTED：{track.get('kind')} 轨需要 Remotion/字幕适配器"
            )
        if track.get("kind") not in {"video", "audio", "overlay", "subtitle"}:
            raise UnsupportedTimeline(f"UNSUPPORTED：未知轨道类型 {track.get('kind')}")

    subtitle_policy = timeline.get("subtitle_policy") or {}
    if (
        str(subtitle_policy.get("source") or "NONE").upper() != "NONE"
        and bool(subtitle_policy.get("burn_in", True))
    ):
        raise UnsupportedTimeline(
            "UNSUPPORTED：本执行器不静默烧录字幕；请先渲染锁画面版本，再对轴并使用字幕适配器"
        )

    video_items = video_tracks[0].get("items")
    if not isinstance(video_items, list) or not video_items:
        raise RenderContractError("视频轨没有项目")
    ordered_video = sorted(video_items, key=lambda item: float(item.get("start", 0)))
    cursor = 0.0
    normalized_video: list[dict[str, Any]] = []
    for index, raw in enumerate(ordered_video):
        if not isinstance(raw, dict):
            raise RenderContractError(f"video.items[{index}] 必须是对象")
        reject_item_complexity(raw, f"video.items[{index}]")
        start = as_number(raw.get("start"), f"video.items[{index}].start", minimum=0)
        duration = as_number(raw.get("duration"), f"video.items[{index}].duration", minimum=0.001)
        source_in = as_number(raw.get("source_in", 0), f"video.items[{index}].source_in", minimum=0)
        layer = as_number(raw.get("layer", 0), f"video.items[{index}].layer")
        gain = as_number(raw.get("gain_db", 0), f"video.items[{index}].gain_db", minimum=-60, maximum=24)
        if layer != 0:
            raise UnsupportedTimeline("UNSUPPORTED：线性视频轨只支持 layer=0")
        if abs(start - cursor) > 1e-6:
            raise UnsupportedTimeline("UNSUPPORTED：视频轨含空隙或重叠，不能静默补黑/裁切")
        asset_id = raw.get("asset_id")
        asset = assets.get(asset_id)
        if not asset or asset.get("kind") not in {"video", "image"}:
            raise RenderContractError(f"视频项目引用了无效资产：{asset_id}")
        if asset.get("kind") == "image":
            if source_in != 0:
                raise UnsupportedTimeline("UNSUPPORTED：静态图不支持非零 source_in")
            if asset["_path"].suffix.lower() not in IMAGE_SUFFIXES:
                raise UnsupportedTimeline("UNSUPPORTED：静态图当前只支持 PNG/JPG/JPEG")
        normalized_video.append(
            {
                "id": raw.get("id"),
                "asset_id": asset_id,
                "asset": asset,
                "start": start,
                "duration": duration,
                "source_in": source_in,
                "gain_db": gain,
            }
        )
        cursor = start + duration
    if abs(cursor - total) > 1e-6:
        raise UnsupportedTimeline("UNSUPPORTED：画面结束时间必须等于时间线总时长")

    normalized_audio: list[dict[str, Any]] = []
    for track_index, track in enumerate(enabled):
        if track.get("kind") != "audio":
            continue
        items = track.get("items")
        if not isinstance(items, list):
            raise RenderContractError(f"audio track {track_index} 的 items 必须是数组")
        for item_index, raw in enumerate(items):
            if not isinstance(raw, dict):
                raise RenderContractError("audio item 必须是对象")
            field = f"audio[{track_index}].items[{item_index}]"
            reject_item_complexity(raw, field)
            start = as_number(raw.get("start"), f"{field}.start", minimum=0)
            duration = as_number(raw.get("duration"), f"{field}.duration", minimum=0.001)
            source_in = as_number(raw.get("source_in", 0), f"{field}.source_in", minimum=0)
            gain = as_number(raw.get("gain_db", 0), f"{field}.gain_db", minimum=-60, maximum=24)
            if start + duration > total + 1e-6:
                raise UnsupportedTimeline("UNSUPPORTED：音频项目超出画面总时长")
            asset_id = raw.get("asset_id")
            asset = assets.get(asset_id)
            if not asset or asset.get("kind") != "audio":
                raise RenderContractError(f"音频项目引用了无效资产：{asset_id}")
            normalized_audio.append(
                {
                    "id": raw.get("id"),
                    "asset_id": asset_id,
                    "asset": asset,
                    "start": start,
                    "duration": duration,
                    "source_in": source_in,
                    "gain_db": gain,
                }
            )

    audio_policy = timeline.get("audio_policy") or {}
    target_lufs = as_number(audio_policy.get("target_lufs", -14), "audio_policy.target_lufs", minimum=-70, maximum=0)
    true_peak = as_number(audio_policy.get("true_peak_dbtp", -1), "audio_policy.true_peak_dbtp", minimum=-20, maximum=0)
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "total_duration": total,
        "video_items": normalized_video,
        "audio_items": normalized_audio,
        "audio_required": bool(timeline.get("audio_required", timeline.get("speech_expected", False))),
        "target_lufs": target_lufs,
        "true_peak_dbtp": true_peak,
    }


def probe_assets(
    subset: dict[str, Any],
    ffprobe: Path,
    timeout: float,
    probe_runner: Callable[[Path, Path, float], dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    required: dict[str, dict[str, Any]] = {}
    for item in [*subset["video_items"], *subset["audio_items"]]:
        required[item["asset_id"]] = item["asset"]
    probes: dict[str, dict[str, Any]] = {}
    for asset_id, asset in required.items():
        probe = probe_runner(asset["_path"], ffprobe, timeout)
        kind = asset.get("kind")
        if kind in {"video", "image"} and probe.get("video_stream_count", 0) < 1:
            raise RenderContractError(f"资产 {asset_id} 没有可用视频/图像流")
        if kind == "audio" and probe.get("audio_stream_count", 0) < 1:
            raise RenderContractError(f"资产 {asset_id} 没有可用音频流")
        probes[asset_id] = probe

    for item in subset["video_items"]:
        if item["asset"].get("kind") == "video":
            duration = probes[item["asset_id"]].get("duration")
            if duration is None or item["source_in"] + item["duration"] > duration + 0.05:
                raise RenderContractError(f"视频项目 {item['id']} 超出源素材时长")
    for item in subset["audio_items"]:
        duration = probes[item["asset_id"]].get("duration")
        if duration is None or item["source_in"] + item["duration"] > duration + 0.05:
            raise RenderContractError(f"音频项目 {item['id']} 超出源素材时长")
    return probes


def analyze_audio_activity(
    subset: dict[str, Any],
    probes: dict[str, dict[str, Any]],
    ffmpeg: Path,
    timeout: float,
    runner: Callable[[list[str], float], subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, Any]:
    """Measure selected audio ranges before choosing a loudness filter.

    FFmpeg loudnorm rejects all-silent/near-silent AAC on some builds because
    its measured loudness becomes non-finite. The analysis is read-only and
    uses the exact source ranges selected by the timeline. A conservative sum
    of per-item peaks decides whether to preserve silence or run loudnorm.
    """

    selected: list[dict[str, Any]] = []
    for item in subset["video_items"]:
        if (
            item["asset"].get("kind") == "video"
            and probes[item["asset_id"]].get("audio_stream_count", 0) > 0
        ):
            selected.append(item)
    selected.extend(subset["audio_items"])
    if not selected:
        return {
            "strategy": "NO_AUDIO",
            "near_silence_threshold_dbfs": NEAR_SILENCE_DBFS,
            "estimated_combined_peak_upper_bound_dbfs": None,
            "items": [],
        }

    entries: list[dict[str, Any]] = []
    amplitudes: list[float] = []
    volume_re = re.compile(
        r"max_volume:\s*(?P<value>-?inf|[-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*dB",
        flags=re.IGNORECASE,
    )
    for item in selected:
        argv = [
            str(ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-v",
            "info",
            "-ss",
            format_number(item["source_in"]),
            "-i",
            str(item["asset"]["_path"]),
            "-t",
            format_number(item["duration"]),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
        result = runner(argv, timeout)
        returncode = normalize_exit_code(result.returncode)
        if returncode != 0:
            raise RenderContractError(
                f"音频活动探测失败：{item['id']}，exit={returncode}：{tail(result.stderr)}"
            )
        combined_output = (result.stdout or "") + "\n" + (result.stderr or "")
        matches = list(volume_re.finditer(combined_output))
        if not matches:
            raise RenderContractError(f"音频活动探测未返回 max_volume：{item['id']}")
        measured_text = matches[-1].group("value").lower()
        if measured_text == "inf":
            raise RenderContractError(f"音频活动探测返回无效正无穷峰值：{item['id']}")
        measured = -math.inf if measured_text == "-inf" else float(measured_text)
        adjusted = measured + item["gain_db"] if math.isfinite(measured) else -math.inf
        if math.isfinite(adjusted):
            amplitudes.append(10 ** (adjusted / 20.0))
        entries.append(
            {
                "item_id": item["id"],
                "asset_id": item["asset_id"],
                "source_in": item["source_in"],
                "duration": item["duration"],
                "gain_db": item["gain_db"],
                "measured_max_volume_dbfs": measured if math.isfinite(measured) else None,
                "adjusted_max_volume_dbfs": adjusted if math.isfinite(adjusted) else None,
                "signal_state": "FINITE" if math.isfinite(adjusted) else "DIGITAL_SILENCE",
                "analysis_argv": argv,
                "shell": False,
            }
        )

    amplitude_upper_bound = sum(amplitudes)
    combined_peak = (
        20.0 * math.log10(amplitude_upper_bound) if amplitude_upper_bound > 0 else -math.inf
    )
    preserve_silence = not math.isfinite(combined_peak) or combined_peak <= NEAR_SILENCE_DBFS
    return {
        "strategy": "PRESERVE_NEAR_SILENCE" if preserve_silence else "LOUDNORM_SINGLE_PASS",
        "near_silence_threshold_dbfs": NEAR_SILENCE_DBFS,
        "estimated_combined_peak_upper_bound_dbfs": round(combined_peak, 3)
        if math.isfinite(combined_peak)
        else None,
        "items": entries,
    }


def compile_plan(
    timeline: dict[str, Any],
    subset: dict[str, Any],
    probes: dict[str, dict[str, Any]],
    ffmpeg: Path,
    ffprobe: Path,
    output: Path,
    tool_versions: dict[str, dict[str, Any]],
    audio_analysis: dict[str, Any],
) -> dict[str, Any]:
    argv: list[str] = [str(ffmpeg), "-hide_banner", "-nostdin", "-n"]
    inputs: list[dict[str, Any]] = []

    for item in subset["video_items"]:
        input_index = len(inputs)
        asset = item["asset"]
        if asset.get("kind") == "image":
            argv.extend(
                [
                    "-loop",
                    "1",
                    "-framerate",
                    format_number(subset["fps"]),
                    "-t",
                    format_number(item["duration"]),
                    "-i",
                    str(asset["_path"]),
                ]
            )
        else:
            argv.extend(["-i", str(asset["_path"])])
        item["_input_index"] = input_index
        inputs.append({"index": input_index, "asset_id": item["asset_id"], "role": "picture"})

    for item in subset["audio_items"]:
        input_index = len(inputs)
        argv.extend(["-i", str(item["asset"]["_path"])])
        item["_input_index"] = input_index
        inputs.append({"index": input_index, "asset_id": item["asset_id"], "role": "audio"})

    filters: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    for index, item in enumerate(subset["video_items"]):
        label = f"v{index}"
        trim = (
            f"trim=start={format_number(item['source_in'])}:duration={format_number(item['duration'])}"
            if item["asset"].get("kind") == "video"
            else f"trim=duration={format_number(item['duration'])}"
        )
        filters.append(
            f"[{item['_input_index']}:v:0]{trim},setpts=PTS-STARTPTS,"
            f"scale={subset['width']}:{subset['height']}:force_original_aspect_ratio=decrease,"
            f"pad={subset['width']}:{subset['height']}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={format_number(subset['fps'])},format=yuv420p[{label}]"
        )
        video_labels.append(f"[{label}]")
        probe = probes[item["asset_id"]]
        if item["asset"].get("kind") == "video" and probe.get("audio_stream_count", 0) > 0:
            audio_label = f"srca{len(audio_labels)}"
            delay_ms = round(item["start"] * 1000)
            filters.append(
                f"[{item['_input_index']}:a:0]"
                f"atrim=start={format_number(item['source_in'])}:duration={format_number(item['duration'])},"
                f"asetpts=PTS-STARTPTS,aresample=48000,adelay={delay_ms}:all=1,"
                f"volume={format_number(item['gain_db'])}dB[{audio_label}]"
            )
            audio_labels.append(f"[{audio_label}]")

    if len(video_labels) == 1:
        filters.append(f"{video_labels[0]}null[vout]")
    else:
        filters.append(f"{''.join(video_labels)}concat=n={len(video_labels)}:v=1:a=0[vout]")

    for item in subset["audio_items"]:
        audio_label = f"exta{len(audio_labels)}"
        delay_ms = round(item["start"] * 1000)
        filters.append(
            f"[{item['_input_index']}:a:0]"
            f"atrim=start={format_number(item['source_in'])}:duration={format_number(item['duration'])},"
            f"asetpts=PTS-STARTPTS,aresample=48000,adelay={delay_ms}:all=1,"
            f"volume={format_number(item['gain_db'])}dB[{audio_label}]"
        )
        audio_labels.append(f"[{audio_label}]")

    has_audio = bool(audio_labels)
    if subset["audio_required"] and not has_audio:
        raise RenderContractError("项目要求音频，但源视频和音频轨都没有可用音频流")
    if has_audio and audio_analysis.get("strategy") not in {
        "PRESERVE_NEAR_SILENCE",
        "LOUDNORM_SINGLE_PASS",
    }:
        raise RenderContractError("音频活动探测没有给出可执行的响度策略")
    if has_audio:
        if len(audio_labels) == 1:
            filters.append(f"{audio_labels[0]}anull[amixed]")
        else:
            filters.append(
                f"{''.join(audio_labels)}amix=inputs={len(audio_labels)}:duration=longest:normalize=0[amixed]"
            )
        if audio_analysis.get("strategy") == "PRESERVE_NEAR_SILENCE":
            filters.append(
                f"[amixed]atrim=duration={format_number(subset['total_duration'])},"
                "asetpts=PTS-STARTPTS[aout]"
            )
        else:
            filters.append(
                f"[amixed]loudnorm=I={format_number(subset['target_lufs'])}:"
                f"TP={format_number(subset['true_peak_dbtp'])}:LRA=11,"
                f"atrim=duration={format_number(subset['total_duration'])},"
                "asetpts=PTS-STARTPTS[aout]"
            )

    argv.extend(["-filter_complex", ";".join(filters), "-map", "[vout]"])
    if has_audio:
        argv.extend(["-map", "[aout]"])
    argv.extend(
        [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            format_number(subset["fps"]),
            "-movflags",
            "+faststart",
        ]
    )
    if has_audio:
        argv.extend(["-c:a", "aac", "-ar", "48000", "-b:a", "192k"])
    argv.extend(["-t", format_number(subset["total_duration"]), str(output)])

    return {
        "schema": PLAN_SCHEMA,
        "engine": "FFMPEG",
        "timeline_id": timeline.get("timeline_id"),
        "timeline_version": timeline.get("version"),
        "timeline_sha256": timeline.get("timeline_sha256"),
        "output_path": str(output),
        "expected": {
            "duration": subset["total_duration"],
            "width": subset["width"],
            "height": subset["height"],
            "fps": subset["fps"],
            "audio_required": subset["audio_required"],
            "audio_expected": has_audio,
            "loudness_strategy": audio_analysis.get("strategy"),
        },
        "inputs": inputs,
        "tools": tool_versions,
        "audio_analysis": audio_analysis,
        "argv": argv,
        "shell": False,
        "overwrite_existing": False,
        "network_install_allowed": False,
        "workflow_status": {
            "execution_status": "NOT_EXECUTED",
            "qa_status": "QA_NOT_EXECUTED",
            "publication_status": "RELEASE_NOT_READY",
        },
        "truth_boundary": {
            "plan_compiled": True,
            "ffmpeg_executed": False,
            "output_verified": False,
            "audio_signal_analyzed": has_audio,
            "visual_qa_executed": False,
        },
        "ffprobe_path": str(ffprobe),
    }


def validate_target_paths(
    timeline_path: Path,
    prepare_path: Path,
    timeline: dict[str, Any],
    assets: dict[str, dict[str, Any]],
    output: Path,
    plan_path: Path | None,
    receipt_path: Path | None,
    ffmpeg: Path,
    ffprobe: Path,
) -> None:
    protected = {
        normalize_path(timeline_path),
        normalize_path(prepare_path),
        normalize_path(ffmpeg),
        normalize_path(ffprobe),
        *(normalize_path(asset["_path"]) for asset in assets.values()),
    }
    targets = [output]
    if plan_path:
        targets.append(plan_path)
    if receipt_path:
        targets.append(receipt_path)
    normalized_targets = [normalize_path(path) for path in targets]
    if len(normalized_targets) != len(set(normalized_targets)):
        raise RenderContractError("输出、计划和回执路径必须彼此不同")
    for path, normalized in zip(targets, normalized_targets):
        if normalized in protected:
            raise RenderContractError(f"目标路径会覆盖输入/时间线/预检/工具：{path}")
        if path.exists():
            raise RenderContractError(f"拒绝覆盖已有目标：{path}")
    declared = (timeline.get("render_job") or {}).get("output_resolved_path")
    if not declared or normalize_path(declared) != normalize_path(output):
        raise RenderContractError("执行输出必须等于时间线的 output_resolved_path")


def validate_final_probe(
    probe: dict[str, Any], expected: dict[str, Any], tolerance: float
) -> list[str]:
    errors: list[str] = []
    if probe.get("video_stream_count", 0) < 1:
        errors.append("输出没有视频流")
    if probe.get("width") != expected["width"] or probe.get("height") != expected["height"]:
        errors.append("输出分辨率与时间线不一致")
    duration = probe.get("duration")
    if duration is None or abs(duration - expected["duration"]) > tolerance:
        errors.append("输出时长与时间线不一致")
    if expected["audio_expected"] and probe.get("audio_stream_count", 0) < 1:
        errors.append("输出缺少计划中的音频流")
    return errors


def tail(value: str | bytes | None, limit: int = 20000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-limit:]


def make_receipt(
    *,
    plan: dict[str, Any],
    status: str,
    started_at: str,
    finished_at: str,
    exit_code: int,
    output: Path,
    output_sha256: str | None,
    probe: dict[str, Any] | None,
    stdout: str | bytes | None,
    stderr: str | bytes | None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "engine": "FFMPEG",
        "timeline_sha256": plan["timeline_sha256"],
        "output_sha256": output_sha256,
        "exit_code": exit_code,
        "shell": False,
        "argv": plan["argv"],
        "executable": plan["tools"]["ffmpeg"]["path"],
        "tool_version": plan["tools"]["ffmpeg"]["version_line"],
        "ffprobe_executable": plan["tools"]["ffprobe"]["path"],
        "ffprobe_version": plan["tools"]["ffprobe"]["version_line"],
        "technical_probe_status": "PASS" if probe and not error else "FAIL",
        "started_at": started_at,
        "finished_at": finished_at,
        "output_path": str(output),
        "output_size_bytes": output.stat().st_size if output.is_file() else None,
        "technical_probe": probe,
        "audio_analysis": plan.get("audio_analysis"),
        "loudness_strategy": (plan.get("expected") or {}).get("loudness_strategy"),
        "stdout_tail": tail(stdout),
        "stderr_tail": tail(stderr),
        "error": error,
        "truth_boundary": {
            "ffmpeg_executed": True,
            "output_technically_verified": status == "EXECUTED_SUCCEEDED",
            "visual_qa_executed": False,
            "release_ready": False,
        },
    }


def execute_job(
    args: argparse.Namespace,
    *,
    command_runner: Callable[[list[str], float], subprocess.CompletedProcess[str]] = run_command,
    media_probe_runner: Callable[[Path, Path, float], dict[str, Any]] = ffprobe_media,
    tool_runner: Callable[[list[str], float], subprocess.CompletedProcess[str]] = run_command,
    audio_analysis_runner: Callable[
        [list[str], float], subprocess.CompletedProcess[str]
    ] = run_command,
) -> dict[str, Any]:
    timeline_path = args.timeline.resolve(strict=False)
    prepare_path = args.prepare_report.resolve(strict=False)
    timeline = load_json(timeline_path, "timeline")
    prepare = load_json(prepare_path, "PREPARE report")
    verify_timeline_integrity(timeline)
    assets = verify_assets(timeline)
    subset = validate_linear_subset(timeline, assets)

    ffmpeg = require_local_file(args.ffmpeg, "--ffmpeg")
    ffprobe = require_local_file(args.ffprobe, "--ffprobe")
    validate_tool_executables(ffmpeg, ffprobe)
    ffmpeg_info = tool_snapshot(ffmpeg, tool_runner)
    ffprobe_info = tool_snapshot(ffprobe, tool_runner)
    verify_prepare_report(prepare, timeline, ffmpeg_info, ffprobe_info)

    output_value = (timeline.get("render_job") or {}).get("output_resolved_path")
    if not isinstance(output_value, str) or not output_value:
        raise RenderContractError("时间线缺少 render_job.output_resolved_path")
    output = Path(output_value).resolve(strict=False)
    if output.suffix.lower() != ".mp4":
        raise UnsupportedTimeline("UNSUPPORTED：MP4 线性基线要求输出扩展名为 .mp4")
    plan_path = args.plan.resolve(strict=False) if args.plan else None
    receipt_path = args.receipt.resolve(strict=False) if args.receipt else None
    validate_target_paths(
        timeline_path,
        prepare_path,
        timeline,
        assets,
        output,
        plan_path,
        receipt_path,
        ffmpeg,
        ffprobe,
    )

    probes = probe_assets(subset, ffprobe, min(args.timeout, 60.0), media_probe_runner)
    audio_analysis = analyze_audio_activity(
        subset,
        probes,
        ffmpeg,
        min(args.timeout, 60.0),
        audio_analysis_runner,
    )
    plan = compile_plan(
        timeline,
        subset,
        probes,
        ffmpeg,
        ffprobe,
        output,
        {"ffmpeg": ffmpeg_info, "ffprobe": ffprobe_info},
        audio_analysis,
    )
    if plan_path:
        write_json_new(plan_path, plan)
    if args.dry_run:
        return {
            "mode": "DRY_RUN",
            "status": "NOT_EXECUTED",
            "plan": plan,
            "plan_path": str(plan_path) if plan_path else None,
        }

    if not receipt_path:
        raise RenderContractError("真实执行必须提供 --receipt")
    output.parent.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    try:
        result = command_runner(plan["argv"], args.timeout)
    except subprocess.TimeoutExpired as exc:
        receipt = make_receipt(
            plan=plan,
            status="EXECUTED_FAILED",
            started_at=started_at,
            finished_at=utc_now(),
            exit_code=-1,
            output=output,
            output_sha256=sha256_file(output) if output.is_file() else None,
            probe=None,
            stdout=exc.stdout,
            stderr=exc.stderr,
            error=f"FFmpeg 超时：{args.timeout} 秒",
        )
        write_json_new(receipt_path, receipt)
        return {"mode": "EXECUTE", "status": "EXECUTED_FAILED", "receipt": receipt}

    returncode = normalize_exit_code(result.returncode)
    if returncode != 0 or not output.is_file() or output.stat().st_size <= 0:
        error = (
            f"FFmpeg 返回非零退出码：{returncode}"
            if returncode != 0
            else "FFmpeg 未产生非空输出文件"
        )
        receipt = make_receipt(
            plan=plan,
            status="EXECUTED_FAILED",
            started_at=started_at,
            finished_at=utc_now(),
            exit_code=returncode,
            output=output,
            output_sha256=sha256_file(output) if output.is_file() else None,
            probe=None,
            stdout=result.stdout,
            stderr=result.stderr,
            error=error,
        )
        write_json_new(receipt_path, receipt)
        return {"mode": "EXECUTE", "status": "EXECUTED_FAILED", "receipt": receipt}

    try:
        final_probe = media_probe_runner(output, ffprobe, min(args.timeout, 60.0))
        probe_errors = validate_final_probe(
            final_probe, plan["expected"], args.duration_tolerance
        )
    except RenderContractError as exc:
        final_probe = None
        probe_errors = [str(exc)]
    output_hash = sha256_file(output)
    if probe_errors:
        receipt = make_receipt(
            plan=plan,
            status="EXECUTED_FAILED",
            started_at=started_at,
            finished_at=utc_now(),
            exit_code=returncode,
            output=output,
            output_sha256=output_hash,
            probe=final_probe,
            stdout=result.stdout,
            stderr=result.stderr,
            error="；".join(probe_errors),
        )
        write_json_new(receipt_path, receipt)
        return {"mode": "EXECUTE", "status": "EXECUTED_FAILED", "receipt": receipt}

    receipt = make_receipt(
        plan=plan,
        status="EXECUTED_SUCCEEDED",
        started_at=started_at,
        finished_at=utc_now(),
        exit_code=0,
        output=output,
        output_sha256=output_hash,
        probe=final_probe,
        stdout=result.stdout,
        stderr=result.stderr,
    )
    write_json_new(receipt_path, receipt)
    return {"mode": "EXECUTE", "status": "EXECUTED_SUCCEEDED", "receipt": receipt}


def build_fixture(root: Path) -> tuple[dict[str, Any], dict[str, Any], Path, Path, Path, Path]:
    video = root / "video.mp4"
    audio = root / "voice.wav"
    ffmpeg = root / "ffmpeg.exe"
    ffprobe = root / "ffprobe.exe"
    video.write_bytes(b"synthetic-video-fixture")
    audio.write_bytes(b"synthetic-audio-fixture")
    ffmpeg.write_bytes(b"fake-tool")
    ffprobe.write_bytes(b"fake-tool")
    output = root / "render" / "final.mp4"
    timeline: dict[str, Any] = {
        "schema": TIMELINE_SCHEMA,
        "project_id": "P-TEST",
        "timeline_id": "TL-TEST",
        "version": "v1",
        "timebase": {"fps": 25, "unit": "seconds"},
        "resolution": {"width": 1080, "height": 1920},
        "total_duration": 2.0,
        "speech_expected": True,
        "audio_required": True,
        "assets": [
            {
                "id": "VID-1",
                "kind": "video",
                "resolved_path": str(video),
                "rights_status": "CLEAR",
                "rights_evidence_ids": ["EV-1"],
                "receipt": {"sha256": sha256_file(video)},
            },
            {
                "id": "AUD-1",
                "kind": "audio",
                "resolved_path": str(audio),
                "rights_status": "CLEAR",
                "rights_evidence_ids": ["EV-2"],
                "receipt": {"sha256": sha256_file(audio)},
            },
        ],
        "tracks": [
            {
                "id": "V1",
                "kind": "video",
                "enabled": True,
                "allow_overlap": False,
                "items": [
                    {
                        "id": "C-1",
                        "asset_id": "VID-1",
                        "start": 0.0,
                        "end": 2.0,
                        "duration": 2.0,
                        "source_in": 0.0,
                        "layer": 0,
                        "gain_db": 0,
                        "transition_in": None,
                        "transition_out": None,
                        "effects": [],
                    }
                ],
            },
            {
                "id": "A1",
                "kind": "audio",
                "enabled": True,
                "allow_overlap": True,
                "items": [
                    {
                        "id": "A-1",
                        "asset_id": "AUD-1",
                        "start": 0.0,
                        "end": 2.0,
                        "duration": 2.0,
                        "source_in": 0.0,
                        "layer": 0,
                        "gain_db": -2,
                        "transition_in": None,
                        "transition_out": None,
                        "effects": [],
                    }
                ],
            },
        ],
        "subtitle_policy": {"source": "NONE", "burn_in": False},
        "audio_policy": {"target_lufs": -14, "true_peak_dbtp": -1},
        "render_job": {
            "engine": "FFMPEG",
            "output_resolved_path": str(output),
            "container": "mp4",
            "video_codec": "h264",
            "audio_codec": "aac",
        },
        "rights_summary": {"recorded_state": "CLEAR"},
    }
    timeline["timeline_sha256"] = sha256_bytes(canonical_json(timeline))
    prepare = {
        "schema": PREFLIGHT_SCHEMA,
        "mode": "PREPARE",
        "timeline": {
            "timeline_id": timeline["timeline_id"],
            "version": timeline["version"],
            "timeline_sha256": timeline["timeline_sha256"],
        },
        "result": {"status": "READY"},
        "workflow_status": {"execution_status": "NOT_EXECUTED"},
        "tools": {
            "ffmpeg": {
                "available": True,
                "path": str(ffmpeg),
                "version_line": "ffmpeg fake 1",
            },
            "ffprobe": {
                "available": True,
                "path": str(ffprobe),
                "version_line": "ffprobe fake 1",
            },
        },
    }
    return timeline, prepare, video, audio, ffmpeg, ffprobe


def run_self_test() -> int:
    checks = 0
    with tempfile.TemporaryDirectory(prefix="silver-ffmpeg-render-") as temp:
        root = Path(temp)
        timeline, prepare, video, _audio, ffmpeg, ffprobe = build_fixture(root)
        timeline_path = root / "timeline.json"
        prepare_path = root / "prepare.json"
        timeline_path.write_text(json.dumps(timeline), encoding="utf-8")
        prepare_path.write_text(json.dumps(prepare), encoding="utf-8")

        def fake_tool(argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
            line = "ffprobe fake 1" if "ffprobe" in Path(argv[0]).name else "ffmpeg fake 1"
            return subprocess.CompletedProcess(argv, 0, stdout=line + "\n", stderr="")

        def fake_audio_activity(
            argv: list[str], _timeout: float
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout="",
                stderr="[Parsed_volumedetect_0] max_volume: -18.0 dB\n",
            )

        def fake_probe(path: Path, _tool: Path, _timeout: float) -> dict[str, Any]:
            if normalize_path(path) == normalize_path(timeline["render_job"]["output_resolved_path"]):
                return {
                    "duration": 2.0,
                    "video_stream_count": 1,
                    "audio_stream_count": 1,
                    "width": 1080,
                    "height": 1920,
                    "video_codec": "h264",
                    "audio_codecs": ["aac"],
                }
            if path.suffix.lower() == ".wav":
                return {"duration": 2.0, "video_stream_count": 0, "audio_stream_count": 1}
            return {"duration": 2.0, "video_stream_count": 1, "audio_stream_count": 1}

        dry_args = SimpleNamespace(
            timeline=timeline_path,
            prepare_report=prepare_path,
            ffmpeg=str(ffmpeg),
            ffprobe=str(ffprobe),
            plan=root / "dry-plan.json",
            receipt=None,
            dry_run=True,
            timeout=30.0,
            duration_tolerance=0.25,
        )
        dry = execute_job(
            dry_args,
            media_probe_runner=fake_probe,
            tool_runner=fake_tool,
            audio_analysis_runner=fake_audio_activity,
        )
        output = Path(timeline["render_job"]["output_resolved_path"])
        assert dry["status"] == "NOT_EXECUTED"
        assert output.exists() is False
        assert dry_args.plan.is_file()
        assert isinstance(dry["plan"]["argv"], list)
        assert dry["plan"]["shell"] is False
        assert "-n" in dry["plan"]["argv"] and "-y" not in dry["plan"]["argv"]
        assert dry["plan"]["audio_analysis"]["strategy"] == "LOUDNORM_SINGLE_PASS"
        assert "loudnorm=" in dry["plan"]["argv"][dry["plan"]["argv"].index("-filter_complex") + 1]
        checks += 8

        def fake_render(argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
            Path(argv[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argv[-1]).write_bytes(b"synthetic-render-output")
            return subprocess.CompletedProcess(argv, 0, stdout="fake render", stderr="")

        run_args = SimpleNamespace(
            timeline=timeline_path,
            prepare_report=prepare_path,
            ffmpeg=str(ffmpeg),
            ffprobe=str(ffprobe),
            plan=root / "execute-plan.json",
            receipt=root / "receipt.json",
            dry_run=False,
            timeout=30.0,
            duration_tolerance=0.25,
        )
        executed = execute_job(
            run_args,
            command_runner=fake_render,
            media_probe_runner=fake_probe,
            tool_runner=fake_tool,
            audio_analysis_runner=fake_audio_activity,
        )
        assert executed["status"] == "EXECUTED_SUCCEEDED"
        assert run_args.receipt.is_file()
        receipt = json.loads(run_args.receipt.read_text(encoding="utf-8"))
        assert receipt["output_sha256"] == sha256_file(output)
        assert receipt["technical_probe_status"] == "PASS"
        assert receipt["loudness_strategy"] == "LOUDNORM_SINGLE_PASS"
        assert receipt["truth_boundary"]["visual_qa_executed"] is False
        checks += 6

        subset = validate_linear_subset(timeline, verify_assets(timeline))
        probes = probe_assets(subset, ffprobe, 30.0, fake_probe)

        def fake_silent_audio(
            argv: list[str], _timeout: float
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout="",
                stderr="[Parsed_volumedetect_0] max_volume: -91.0 dB\n",
            )

        silent_analysis = analyze_audio_activity(
            subset, probes, ffmpeg, 30.0, fake_silent_audio
        )
        silent_output = root / "silent-plan-output.mp4"
        silent_plan = compile_plan(
            timeline,
            subset,
            probes,
            ffmpeg,
            ffprobe,
            silent_output,
            {
                "ffmpeg": {"path": str(ffmpeg), "version_line": "ffmpeg fake 1"},
                "ffprobe": {"path": str(ffprobe), "version_line": "ffprobe fake 1"},
            },
            silent_analysis,
        )
        silent_filter = silent_plan["argv"][silent_plan["argv"].index("-filter_complex") + 1]
        assert silent_analysis["strategy"] == "PRESERVE_NEAR_SILENCE"
        assert "loudnorm=" not in silent_filter
        assert "[amixed]atrim=" in silent_filter
        assert normalize_exit_code(4294967274) == -22
        checks += 4

        tampered = json.loads(json.dumps(timeline))
        tampered["total_duration"] = 3.0
        try:
            verify_timeline_integrity(tampered)
        except RenderContractError:
            checks += 1
        else:
            raise AssertionError("tampered timeline was accepted")

        changed = json.loads(json.dumps(timeline))
        video.write_bytes(b"changed-after-timeline")
        try:
            verify_assets(changed)
        except RenderContractError:
            checks += 1
        else:
            raise AssertionError("asset hash mismatch was accepted")
        video.write_bytes(b"synthetic-video-fixture")

        for mutate in ("overlay", "transition", "gap", "subtitle"):
            candidate = json.loads(json.dumps(timeline))
            if mutate == "overlay":
                candidate["tracks"].append(
                    {"id": "O1", "kind": "overlay", "enabled": True, "items": [{"id": "O"}]}
                )
            elif mutate == "transition":
                candidate["tracks"][0]["items"][0]["transition_out"] = {
                    "type": "fade",
                    "duration": 0.25,
                }
            elif mutate == "gap":
                candidate["tracks"][0]["items"][0]["start"] = 0.5
            else:
                candidate["subtitle_policy"] = {"source": "WHISPER", "burn_in": True}
            candidate["timeline_sha256"] = sha256_bytes(
                canonical_json({k: v for k, v in candidate.items() if k != "timeline_sha256"})
            )
            try:
                validate_linear_subset(candidate, verify_assets(candidate))
            except UnsupportedTimeline:
                checks += 1
            else:
                raise AssertionError(f"unsupported {mutate} was accepted")

        blocked_prepare = json.loads(json.dumps(prepare))
        blocked_prepare["result"]["status"] = "BLOCK"
        try:
            verify_prepare_report(
                blocked_prepare,
                timeline,
                {"path": str(ffmpeg), "version_line": "ffmpeg fake 1"},
                {"path": str(ffprobe), "version_line": "ffprobe fake 1"},
            )
        except RenderContractError:
            checks += 1
        else:
            raise AssertionError("non-READY PREPARE was accepted")

        collision_timeline = json.loads(json.dumps(timeline))
        collision_timeline["render_job"]["output_resolved_path"] = str(video)
        collision_timeline["timeline_sha256"] = sha256_bytes(
            canonical_json(
                {k: v for k, v in collision_timeline.items() if k != "timeline_sha256"}
            )
        )
        try:
            validate_target_paths(
                timeline_path,
                prepare_path,
                collision_timeline,
                verify_assets(collision_timeline),
                video,
                root / "p.json",
                root / "r.json",
                ffmpeg,
                ffprobe,
            )
        except RenderContractError:
            checks += 1
        else:
            raise AssertionError("output/input collision was accepted")

        remote = json.loads(json.dumps(timeline))
        remote["assets"][0]["resolved_path"] = "https://example.com/video.mp4"
        try:
            verify_assets(remote)
        except RenderContractError:
            checks += 1
        else:
            raise AssertionError("remote media URL was accepted")

        if os.name == "nt":
            wrapper = root / "ffmpeg.cmd"
            wrapper.write_text("@echo off\n", encoding="utf-8")
            try:
                validate_tool_executables(wrapper, ffprobe)
            except RenderContractError:
                checks += 1
            else:
                raise AssertionError("Windows command wrapper was accepted as FFmpeg")

    print(f"PASS: render_media_ffmpeg self-test ({checks} checks; synthetic runner only)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="银幕总控 FFmpeg 严格线性基线执行器")
    parser.add_argument("--timeline", type=Path, help="标准 media-timeline JSON")
    parser.add_argument("--prepare-report", type=Path, help="匹配当前时间线的 READY PREPARE 报告")
    parser.add_argument("--ffmpeg", help="显式本地 ffmpeg 可执行文件路径")
    parser.add_argument("--ffprobe", help="显式本地 ffprobe 可执行文件路径")
    parser.add_argument("--plan", type=Path, help="写入不可覆盖的执行计划 JSON")
    parser.add_argument("--receipt", type=Path, help="真实执行回执 JSON；dry-run 禁止提供")
    parser.add_argument("--dry-run", action="store_true", help="只探测并编译计划，绝不运行 FFmpeg")
    parser.add_argument("--timeout", type=float, default=3600.0, help="FFmpeg 超时秒数")
    parser.add_argument("--duration-tolerance", type=float, default=0.25)
    parser.add_argument("--self-test", action="store_true", help="运行纯本地安全回归")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    required = (args.timeline, args.prepare_report, args.ffmpeg, args.ffprobe)
    if not all(required):
        parser.error("必须提供 --timeline、--prepare-report、--ffmpeg 与 --ffprobe")
    if args.dry_run:
        if not args.plan:
            parser.error("--dry-run 必须提供新的 --plan 路径")
        if args.receipt:
            parser.error("--dry-run 不得提供 --receipt")
    elif not args.receipt:
        parser.error("真实执行必须提供新的 --receipt 路径")
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.timeout > 86400:
        parser.error("--timeout 必须在 0 到 86400 秒之间")
    if (
        not math.isfinite(args.duration_tolerance)
        or args.duration_tolerance < 0
        or args.duration_tolerance > 10
    ):
        parser.error("--duration-tolerance 必须在 0 到 10 秒之间")

    try:
        result = execute_job(args)
    except UnsupportedTimeline as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (OSError, RenderContractError) as exc:
        print(f"BLOCK: {exc}", file=sys.stderr)
        return 2

    if result["mode"] == "DRY_RUN":
        print(
            f"NOT_EXECUTED: FFmpeg 计划已写入 {result['plan_path']}；"
            "没有生成成片或执行回执"
        )
        return 0
    receipt_path = args.receipt
    if result["status"] == "EXECUTED_SUCCEEDED":
        print(
            f"EXECUTED_SUCCEEDED: 成片已由 ffprobe 技术验证；回执 -> {receipt_path}；"
            "视觉 QA 仍为 QA_NOT_EXECUTED"
        )
        return 0
    print(f"EXECUTED_FAILED: 失败回执 -> {receipt_path}", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
