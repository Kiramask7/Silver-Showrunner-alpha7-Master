#!/usr/bin/env python3
"""Validate screenplay-to-prompt fidelity for Alpha.7 Master.

This local, deterministic preflight compares a compact source-unit inventory
with one authored screenplay slice, video Prompt, or image Prompt. It guards
coverage, verbatim dialogue, speaker/order fidelity, video timeline continuity,
full-fidelity delivery, and medium-specific prompt structure. It does not score
artistic quality or claim that a provider will obey the Prompt.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from performance_feasibility_guard import analyze_prompt as analyze_performance_feasibility


CONTRACT_VERSION = "alpha7-master-creative-preflight-v1"
MODES = {"SCRIPT", "VIDEO_PROMPT", "IMAGE_PROMPT"}
SOURCE_KINDS = {"EVENT", "DIALOGUE", "NARRATION", "NON_LEXICAL", "VISUAL_FACT"}
FIDELITY = {"VERBATIM", "SEMANTIC", "OPTIONAL"}
COMPRESSION_AUTHORITIES = {"NONE", "VERIFIED_SURFACE_LIMIT", "USER_REQUESTED"}
DELIVERY_FIDELITIES = {
    "FULL_FIDELITY",
    "SEGMENTED_FULL_FIDELITY",
    "USER_REQUESTED_COMPACT",
}
VIDEO_SECTION_KINDS = {
    "TASK",
    "REFERENCE_ASSET",
    "SCENE_STYLE_CONTINUITY",
    "DIRECTOR_TIMELINE",
    "SOUND",
    "NEGATIVE",
}
IMAGE_SECTION_KINDS = {
    "TASK",
    "REFERENCE_ASSET",
    "SCENE_STYLE_CONTINUITY",
    "STATIC_FRAME",
    "NEGATIVE",
}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def substantive(value: Any, minimum: int = 4) -> bool:
    return isinstance(value, str) and len("".join(value.split())) >= minimum


def normalized(value: Any) -> str:
    return "" if not isinstance(value, str) else " ".join(value.split())


class Report:
    def __init__(self) -> None:
        self.errors: list[dict[str, str]] = []
        self.metrics: dict[str, Any] = {}

    def error(self, code: str, message: str, path: str) -> None:
        self.errors.append({"code": code, "message": message, "path": path})

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": "PASS" if not self.errors else "FAIL",
            "errors": self.errors,
            "metrics": self.metrics,
            "production_validation": "NOT_TESTED",
        }


def source_inventory(data: dict[str, Any], report: Report) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    units = [row for row in as_list(data.get("source_units")) if isinstance(row, dict)]
    if not units:
        report.error("CF_SOURCE_EMPTY", "source_units 必须包含当前范围的来源单元", "$.source_units")
        return [], {}
    by_id: dict[str, dict[str, Any]] = {}
    orders: list[int] = []
    for index, unit in enumerate(units):
        path = f"$.source_units[{index}]"
        unit_id = unit.get("unit_id")
        kind = unit.get("kind")
        fidelity = unit.get("fidelity")
        order = unit.get("order")
        if not isinstance(unit_id, str) or not unit_id or unit_id in by_id:
            report.error("CF_SOURCE_ID", "来源单元 ID 缺失或重复", f"{path}.unit_id")
            continue
        by_id[unit_id] = unit
        if kind not in SOURCE_KINDS:
            report.error("CF_SOURCE_KIND", "来源单元 kind 无效", f"{path}.kind")
        if fidelity not in FIDELITY:
            report.error("CF_SOURCE_FIDELITY", "来源单元 fidelity 无效", f"{path}.fidelity")
        if not isinstance(order, int) or isinstance(order, bool) or order < 1:
            report.error("CF_SOURCE_ORDER", "来源顺序必须是从 1 开始的正整数", f"{path}.order")
        else:
            orders.append(order)
        if not substantive(unit.get("text"), 1):
            report.error("CF_SOURCE_TEXT", "来源单元正文不能为空", f"{path}.text")
        if kind in {"DIALOGUE", "NON_LEXICAL"} and not substantive(unit.get("speaker"), 1):
            report.error("CF_SOURCE_SPEAKER", "对白或人物发声必须绑定说话人", f"{path}.speaker")
        if kind == "DIALOGUE" and fidelity != "VERBATIM":
            report.error("CF_DIALOGUE_FIDELITY", "进入分镜/Prompt 的对白必须先冻结为 VERBATIM", f"{path}.fidelity")
    if len(orders) != len(set(orders)) or sorted(orders) != list(range(1, len(orders) + 1)):
        report.error("CF_SOURCE_ORDER", "来源顺序必须唯一且连续", "$.source_units")
    return units, by_id


def validate_delivery_policy(data: dict[str, Any], by_id: dict[str, dict[str, Any]], report: Report) -> set[str]:
    authority = data.get("compression_authority")
    fidelity = data.get("delivery_fidelity")
    evidence_refs = [str(item) for item in as_list(data.get("authority_refs")) if str(item)]
    omitted = {str(item) for item in as_list(data.get("omitted_source_unit_ids")) if str(item)}
    if authority not in COMPRESSION_AUTHORITIES:
        report.error("CF_COMPRESSION_AUTHORITY", "compression_authority 无效", "$.compression_authority")
    if fidelity not in DELIVERY_FIDELITIES:
        report.error("CF_DELIVERY_FIDELITY", "delivery_fidelity 无效", "$.delivery_fidelity")
    if omitted - set(by_id):
        report.error("CF_UNKNOWN_OMISSION", "省略列表引用了不存在的来源单元", "$.omitted_source_unit_ids")
    required_omitted = {
        unit_id for unit_id in omitted if by_id.get(unit_id, {}).get("fidelity") != "OPTIONAL"
    }
    if required_omitted:
        report.error("CF_REQUIRED_OMISSION", "必保来源单元不得被省略", "$.omitted_source_unit_ids")
    if authority == "NONE":
        if fidelity != "FULL_FIDELITY" or omitted or evidence_refs:
            report.error(
                "CF_SILENT_COMPRESSION",
                "无压缩授权时必须全量交付，且不能登记省略项或伪造授权依据",
                "$",
            )
    elif authority == "VERIFIED_SURFACE_LIMIT":
        if fidelity != "SEGMENTED_FULL_FIDELITY" or not evidence_refs or omitted:
            report.error(
                "CF_SEGMENT_INSTEAD_OF_SHRINK",
                "入口限制只能触发带依据的全量分段，不能删除来源单元",
                "$",
            )
    elif authority == "USER_REQUESTED":
        if fidelity != "USER_REQUESTED_COMPACT" or not evidence_refs:
            report.error(
                "CF_USER_COMPACT_AUTHORITY",
                "用户要求精简时必须保存明确授权引用并使用紧凑交付标记",
                "$",
            )
    return omitted


def validate_exact_source_order(
    output_unit_ids: list[str], by_id: dict[str, dict[str, Any]], report: Report, path: str
) -> None:
    ordered = [by_id[unit_id]["order"] for unit_id in output_unit_ids if unit_id in by_id]
    if ordered != sorted(ordered):
        report.error("CF_SOURCE_REORDERED", "输出改变了来源事件或发声顺序", path)


def validate_script(
    data: dict[str, Any], by_id: dict[str, dict[str, Any]], omitted: set[str], report: Report
) -> None:
    script = data.get("script") if isinstance(data.get("script"), dict) else {}
    scenes = [row for row in as_list(script.get("scenes")) if isinstance(row, dict)]
    if not scenes:
        report.error("CF_SCRIPT_EMPTY", "script.scenes 不能为空", "$.script.scenes")
        return
    covered: list[str] = []
    dialogue_rows: list[tuple[str, dict[str, Any], str]] = []
    for scene_index, scene in enumerate(scenes):
        scene_path = f"$.script.scenes[{scene_index}]"
        for field in ("scene_id", "entry_state", "objective", "conflict", "exit_state"):
            if not substantive(scene.get(field)):
                report.error("CF_SCENE_THIN", f"场景字段 {field} 过薄或缺失", f"{scene_path}.{field}")
        declared = [str(item) for item in as_list(scene.get("source_unit_ids")) if str(item)]
        if len(declared) != len(set(declared)) or set(declared) - set(by_id):
            report.error("CF_SCENE_SOURCE_BINDING", "场景来源绑定重复或不可解析", f"{scene_path}.source_unit_ids")
        beats = [row for row in as_list(scene.get("beats")) if isinstance(row, dict)]
        if not beats:
            report.error("CF_SCENE_BEATS", "场景至少需要一个可演节拍", f"{scene_path}.beats")
        derived: list[str] = []
        for beat_index, beat in enumerate(beats):
            beat_path = f"{scene_path}.beats[{beat_index}]"
            if not substantive(beat.get("beat_id")) or not substantive(beat.get("action")) or not substantive(beat.get("state_change")):
                report.error("CF_SCRIPT_BEAT_THIN", "剧本节拍必须包含 ID、可观察动作和状态变化", beat_path)
            refs = [str(item) for item in as_list(beat.get("source_unit_ids")) if str(item)]
            if not refs or set(refs) - set(by_id):
                report.error("CF_SCRIPT_BEAT_SOURCE", "剧本节拍必须回链有效来源单元", f"{beat_path}.source_unit_ids")
            derived.extend(refs)
        turns = [row for row in as_list(scene.get("dialogue_turns")) if isinstance(row, dict)]
        for turn_index, turn in enumerate(turns):
            turn_path = f"{scene_path}.dialogue_turns[{turn_index}]"
            unit_id = str(turn.get("source_unit_id", ""))
            source = by_id.get(unit_id)
            if source is None or source.get("kind") not in {"DIALOGUE", "NARRATION", "NON_LEXICAL"}:
                report.error("CF_DIALOGUE_SOURCE", "发声条目必须回链对白、旁白或人物非词汇发声", f"{turn_path}.source_unit_id")
                continue
            derived.append(unit_id)
            dialogue_rows.append((unit_id, turn, turn_path))
            if source.get("kind") in {"DIALOGUE", "NON_LEXICAL"} and turn.get("speaker") != source.get("speaker"):
                report.error("CF_SPEAKER_CHANGED", "说话人或人物发声归属发生变化", f"{turn_path}.speaker")
            if source.get("fidelity") == "VERBATIM" and turn.get("text") != source.get("text"):
                report.error("CF_DIALOGUE_CHANGED", "逐字发声内容被缩写、润色或改写", f"{turn_path}.text")
            expected_kind = source.get("kind")
            if turn.get("kind") != expected_kind:
                report.error("CF_VOICE_KIND_CHANGED", "对白、旁白与非词汇发声不能互相冒充", f"{turn_path}.kind")
        if set(declared) != set(derived):
            report.error("CF_SCENE_SOURCE_BINDING", "场景声明的来源单元与实际节拍/发声覆盖不一致", scene_path)
        covered.extend(declared)
    required = set(by_id) - omitted
    if set(covered) != required:
        report.error("CF_SOURCE_COVERAGE", "剧本没有完整覆盖当前范围的必保来源单元", "$.script")
    validate_exact_source_order([unit_id for unit_id, _, _ in dialogue_rows], by_id, report, "$.script.scenes[*].dialogue_turns")
    report.metrics.update({"scene_count": len(scenes), "source_unit_count": len(by_id), "covered_source_units": len(set(covered))})


def compile_section_text(container: dict[str, Any], expected: set[str], report: Report, path: str) -> tuple[str, dict[str, str]]:
    sections = [row for row in as_list(container.get("prompt_sections")) if isinstance(row, dict)]
    kinds: list[str] = []
    section_text: dict[str, str] = {}
    for index, section in enumerate(sections):
        kind = section.get("kind")
        body = section.get("text")
        if kind in kinds:
            report.error("CF_SECTION_DUPLICATE", "同一种最终 Prompt section 不得重复", f"{path}.prompt_sections[{index}].kind")
        kinds.append(kind)
        if not isinstance(kind, str) or not substantive(body):
            report.error("CF_SECTION_THIN", "Prompt section 类型无效或正文过薄", f"{path}.prompt_sections[{index}]")
        elif kind:
            section_text[kind] = body
    if set(kinds) != expected:
        report.error("CF_SECTION_CONTRACT", f"Prompt section 必须精确为 {sorted(expected)}", f"{path}.prompt_sections")
    separator = container.get("separator", "\n\n")
    if separator not in {"", "\n", "\n\n"}:
        report.error("CF_SECTION_SEPARATOR", "section 分隔符无效", f"{path}.separator")
        separator = "\n\n"
    compiled = separator.join(str(section.get("text", "")) for section in sections)
    if container.get("prompt_text") != compiled:
        report.error("CF_PROMPT_TEXT_MISMATCH", "prompt_text 必须由有序 sections 唯一拼接", f"{path}.prompt_text")
    return compiled, section_text


def validate_video(
    data: dict[str, Any], by_id: dict[str, dict[str, Any]], omitted: set[str], report: Report
) -> None:
    video = data.get("video_prompt") if isinstance(data.get("video_prompt"), dict) else {}
    prompt_text, section_text = compile_section_text(video, VIDEO_SECTION_KINDS, report, "$.video_prompt")
    duration = video.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        report.error("CF_VIDEO_DURATION", "视频自然时长必须为正数", "$.video_prompt.duration_seconds")
        duration = 0
    beats = [row for row in as_list(video.get("beats")) if isinstance(row, dict)]
    if not beats:
        report.error("CF_VIDEO_BEATS", "视频 Prompt 至少需要一个导演节拍", "$.video_prompt.beats")
    cursor = 0.0
    covered: list[str] = []
    first_time: dict[str, float] = {}
    for index, beat in enumerate(beats):
        beat_path = f"$.video_prompt.beats[{index}]"
        start = beat.get("start_seconds")
        end = beat.get("end_seconds")
        if (
            isinstance(start, bool) or not isinstance(start, (int, float))
            or isinstance(end, bool) or not isinstance(end, (int, float))
            or abs(float(start) - cursor) > 0.001 or float(end) <= float(start)
            or float(end) > float(duration) + 0.001
        ):
            report.error("CF_TIMELINE_GAP", "视频时间线存在空档、重叠或非法范围", beat_path)
        if isinstance(end, (int, float)) and not isinstance(end, bool):
            cursor = float(end)
        for field in (
            "beat_id", "camera", "action", "performance",
            "contact_material_environment", "dialogue_audio", "exit_state", "prompt_anchor",
        ):
            if not substantive(beat.get(field)):
                report.error("CF_VIDEO_BEAT_THIN", f"视频节拍字段 {field} 过薄或缺失", f"{beat_path}.{field}")
        refs = [str(item) for item in as_list(beat.get("source_unit_ids")) if str(item)]
        if not refs or set(refs) - set(by_id):
            report.error("CF_VIDEO_SOURCE_BINDING", "视频节拍必须回链有效来源单元", f"{beat_path}.source_unit_ids")
        for unit_id in refs:
            covered.append(unit_id)
            first_time.setdefault(unit_id, float(start) if isinstance(start, (int, float)) else 0.0)
        anchor = str(beat.get("prompt_anchor", ""))
        if anchor and prompt_text.count(anchor) != 1:
            report.error("CF_VIDEO_ANCHOR", "每个视频节拍锚必须在最终 Prompt 正向正文中恰好出现一次", f"{beat_path}.prompt_anchor")
        for field in ("camera", "action", "performance", "contact_material_environment", "dialogue_audio", "exit_state"):
            value = str(beat.get(field, ""))
            if value and value not in anchor:
                report.error("CF_VIDEO_ANCHOR_LOSS", f"最终节拍锚漏掉 {field}", f"{beat_path}.prompt_anchor")
        for unit_id in refs:
            source = by_id.get(unit_id, {})
            if source.get("kind") in {"DIALOGUE", "NON_LEXICAL"}:
                audio = str(beat.get("dialogue_audio", ""))
                if str(source.get("text", "")) not in audio:
                    report.error("CF_DIALOGUE_CHANGED", "视频时间线没有逐字保留发声内容", f"{beat_path}.dialogue_audio")
                if str(source.get("speaker", "")) not in audio:
                    report.error("CF_SPEAKER_CHANGED", "视频时间线没有明确正确说话人", f"{beat_path}.dialogue_audio")
    if beats and abs(cursor - float(duration)) > 0.001:
        report.error("CF_TIMELINE_END", "视频时间线没有连续覆盖到自然时长终点", "$.video_prompt.beats")
    required = set(by_id) - omitted
    if set(covered) != required:
        report.error("CF_SOURCE_COVERAGE", "视频 Prompt 没有完整覆盖当前范围的必保来源单元", "$.video_prompt")
    ordered_units = sorted(first_time, key=lambda unit_id: (first_time[unit_id], by_id[unit_id]["order"]))
    validate_exact_source_order(ordered_units, by_id, report, "$.video_prompt.beats")
    expected_verbatim = Counter(
        str(unit.get("text", ""))
        for unit in by_id.values()
        if unit.get("kind") in {"DIALOGUE", "NON_LEXICAL"} and unit.get("fidelity") == "VERBATIM"
        and unit.get("unit_id") not in omitted
    )
    for text_value, expected_count in expected_verbatim.items():
        if prompt_text.count(text_value) != expected_count:
            report.error("CF_DIALOGUE_OCCURRENCE", "逐字发声必须在最终 Prompt 中按来源次数出现且不重复附录", "$.video_prompt.prompt_text")
    if any(text_value and text_value in section_text.get("NEGATIVE", "") for text_value in expected_verbatim):
        report.error("CF_DIALOGUE_NEGATIVE_LEAK", "逐字对白不能被复制进负向约束", "$.video_prompt.prompt_sections")
    if not substantive(video.get("audio_responsibility")):
        report.error("CF_AUDIO_RESPONSIBILITY", "必须明确模型原生声音或后期声音责任", "$.video_prompt.audio_responsibility")
    spoken_speakers = [
        str(unit.get("speaker", "")).strip()
        for unit in by_id.values()
        if unit.get("kind") == "DIALOGUE" and str(unit.get("speaker", "")).strip()
    ]
    for finding in analyze_performance_feasibility(
        prompt_text,
        has_spoken_dialogue=bool(spoken_speakers),
        spoken_speakers=spoken_speakers,
        require_copy_endings=False,
    ):
        report.error(
            f"CF_{finding.code.removeprefix('E_')}",
            f"{finding.message} 命中：{finding.evidence}",
            "$.video_prompt.prompt_text",
        )
    for index, beat in enumerate(beats):
        beat_surface = "，".join(
            str(beat.get(field, "")).strip().rstrip("。；;，, ")
            for field in ("action", "performance", "dialogue_audio", "exit_state")
        )
        for finding in analyze_performance_feasibility(
            beat_surface,
            has_spoken_dialogue=bool(spoken_speakers),
            spoken_speakers=spoken_speakers,
            require_copy_endings=False,
        ):
            report.error(
                f"CF_{finding.code.removeprefix('E_')}",
                f"{finding.message} 命中：{finding.evidence}",
                f"$.video_prompt.beats[{index}]",
            )
    report.metrics.update({"beat_count": len(beats), "duration_seconds": duration, "source_unit_count": len(by_id), "covered_source_units": len(set(covered))})


def validate_image(
    data: dict[str, Any], by_id: dict[str, dict[str, Any]], omitted: set[str], report: Report
) -> None:
    image = data.get("image_prompt") if isinstance(data.get("image_prompt"), dict) else {}
    prompt_text, _ = compile_section_text(image, IMAGE_SECTION_KINDS, report, "$.image_prompt")
    if "duration_seconds" in image or "beats" in image:
        report.error("CF_IMAGE_DYNAMIC_LEAK", "静态图 Prompt 不得包含视频时长或时间线节拍", "$.image_prompt")
    bindings = [row for row in as_list(image.get("source_bindings")) if isinstance(row, dict)]
    covered: set[str] = set()
    for index, binding in enumerate(bindings):
        path = f"$.image_prompt.source_bindings[{index}]"
        unit_id = str(binding.get("source_unit_id", ""))
        anchor = str(binding.get("prompt_anchor", ""))
        if unit_id not in by_id:
            report.error("CF_IMAGE_SOURCE_BINDING", "静态图绑定了不存在的来源单元", f"{path}.source_unit_id")
        else:
            covered.add(unit_id)
        if not substantive(anchor) or prompt_text.count(anchor) != 1:
            report.error("CF_IMAGE_ANCHOR", "每个静态来源锚必须在最终 Prompt 中恰好出现一次", f"{path}.prompt_anchor")
    required = set(by_id) - omitted
    if covered != required:
        report.error("CF_SOURCE_COVERAGE", "静态图 Prompt 没有完整覆盖当前范围的必保来源单元", "$.image_prompt")
    report.metrics.update({"source_unit_count": len(by_id), "covered_source_units": len(covered), "section_count": len(IMAGE_SECTION_KINDS)})


def validate(data: dict[str, Any]) -> dict[str, Any]:
    report = Report()
    if data.get("contract_version") != CONTRACT_VERSION:
        report.error("CF_CONTRACT_VERSION", "creative preflight 合同版本不匹配", "$.contract_version")
    mode = data.get("mode")
    if mode not in MODES:
        report.error("CF_MODE", "mode 必须是 SCRIPT、VIDEO_PROMPT 或 IMAGE_PROMPT", "$.mode")
    _, by_id = source_inventory(data, report)
    omitted = validate_delivery_policy(data, by_id, report)
    if mode == "SCRIPT":
        validate_script(data, by_id, omitted, report)
    elif mode == "VIDEO_PROMPT":
        validate_video(data, by_id, omitted, report)
    elif mode == "IMAGE_PROMPT":
        validate_image(data, by_id, omitted, report)
    return report.as_dict()


def _base_units() -> list[dict[str, Any]]:
    return [
        {"unit_id": "SRC-01", "order": 1, "kind": "EVENT", "text": "林岚推开储物间的门。", "speaker": None, "fidelity": "SEMANTIC"},
        {"unit_id": "SRC-02", "order": 2, "kind": "DIALOGUE", "text": "你昨晚来过这里。", "speaker": "林岚", "fidelity": "VERBATIM"},
        {"unit_id": "SRC-03", "order": 3, "kind": "DIALOGUE", "text": "我没有。", "speaker": "周启", "fidelity": "VERBATIM"},
    ]


def _base() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "source_units": _base_units(),
        "compression_authority": "NONE",
        "delivery_fidelity": "FULL_FIDELITY",
        "authority_refs": [],
        "omitted_source_unit_ids": [],
    }


def _script_fixture() -> dict[str, Any]:
    return {
        **_base(),
        "mode": "SCRIPT",
        "script": {"scenes": [{
            "scene_id": "SCENE-01",
            "entry_state": "深夜，储物间门外只有林岚和周启。",
            "objective": "林岚要确认周启是否隐瞒昨夜行踪。",
            "conflict": "周启否认，门内的痕迹让他的回答失去可信度。",
            "source_unit_ids": ["SRC-01", "SRC-02", "SRC-03"],
            "beats": [{
                "beat_id": "SB-01",
                "source_unit_ids": ["SRC-01"],
                "action": "林岚压下门把，缓慢推开储物间的门。",
                "state_change": "封闭空间被打开，两人都能看见门内凌乱的地面。",
            }],
            "dialogue_turns": [
                {"source_unit_id": "SRC-02", "kind": "DIALOGUE", "speaker": "林岚", "text": "你昨晚来过这里。"},
                {"source_unit_id": "SRC-03", "kind": "DIALOGUE", "speaker": "周启", "text": "我没有。"},
            ],
            "exit_state": "门已经完全打开，周启的否认悬在可见痕迹之前。",
        }]},
    }


def _video_fixture() -> dict[str, Any]:
    beat1 = {
        "beat_id": "BT-01", "start_seconds": 0, "end_seconds": 4,
        "source_unit_ids": ["SRC-01"],
        "camera": "中景固定在门侧，轻微跟随林岚的肩线。",
        "action": "林岚压下门把，门从闭合状态缓慢打开。",
        "performance": "她屏住呼吸，视线先落在门缝再进入室内。",
        "contact_material_environment": "手掌压力带动金属把手下沉，门轴发出短促摩擦声。",
        "dialogue_audio": "此段没有人物台词，只保留门轴声和室内低噪。",
        "exit_state": "门打开到一半，室内地面首次进入画面。",
    }
    beat2 = {
        "beat_id": "BT-02", "start_seconds": 4, "end_seconds": 8,
        "source_unit_ids": ["SRC-02"],
        "camera": "镜头切到林岚近景并把周启肩部留在前景。",
        "action": "林岚停住开门动作，抬眼直视周启。",
        "performance": "她下颌收紧，句尾保持目光不移开。",
        "contact_material_environment": "门在她手中保持半开，冷光沿门边落到指节。",
        "dialogue_audio": "林岚用压低但清楚的普通话逐字说：你昨晚来过这里。",
        "exit_state": "林岚说完后保持注视，周启尚未回答。",
    }
    beat3 = {
        "beat_id": "BT-03", "start_seconds": 8, "end_seconds": 12,
        "source_unit_ids": ["SRC-03"],
        "camera": "反打周启近景，林岚的手仍在画面边缘握住门把。",
        "action": "周启先看向门内痕迹，再把视线移回林岚。",
        "performance": "他回答前停半拍，声音短促，肩膀没有放松。",
        "contact_material_environment": "门轴余振停止，走廊底噪在停顿中保持连续。",
        "dialogue_audio": "周启用普通话逐字回答：我没有。",
        "exit_state": "周启说完仍站在原地，半开的门和可见痕迹留在两人之间。",
    }
    for beat in (beat1, beat2, beat3):
        beat["prompt_anchor"] = " ".join(str(beat[field]) for field in (
            "camera", "action", "performance", "contact_material_environment", "dialogue_audio", "exit_state"
        ))
    sections = [
        {"kind": "TASK", "text": "生成一段十二秒的写实悬疑对话视频，结尾保留半开的门和对峙状态。"},
        {"kind": "REFERENCE_ASSET", "text": "保持林岚、周启的身份、服装、发型以及门和储物间几何连续。"},
        {"kind": "SCENE_STYLE_CONTINUITY", "text": "深夜狭窄走廊，室内冷光从逐渐打开的门缝进入，空间方向不跳变。"},
        {"kind": "DIRECTOR_TIMELINE", "text": "\n".join(beat["prompt_anchor"] for beat in (beat1, beat2, beat3))},
        {"kind": "SOUND", "text": "现场普通话对白；门轴摩擦与走廊低噪连续。模型不支持原生音频时按同一时间点后期配音。"},
        {"kind": "NEGATIVE", "text": "不要改变人物身份，不要增加台词，不要删除停顿，不要让听者同时开口。"},
    ]
    return {
        **_base(),
        "mode": "VIDEO_PROMPT",
        "video_prompt": {
            "duration_seconds": 12,
            "separator": "\n\n",
            "prompt_sections": sections,
            "prompt_text": "\n\n".join(section["text"] for section in sections),
            "beats": [beat1, beat2, beat3],
            "audio_responsibility": "优先由支持对白的模型生成；不支持时保留全部时间点并进入后期配音。",
        },
    }


def _image_fixture() -> dict[str, Any]:
    units = [{"unit_id": "SRC-01", "order": 1, "kind": "VISUAL_FACT", "text": "半开的储物间门把冷光切成窄条。", "speaker": None, "fidelity": "SEMANTIC"}]
    anchor = "半开的储物间门位于画面右侧，冷光沿门缝切出一条窄亮带。"
    sections = [
        {"kind": "TASK", "text": "生成悬疑场景的静态关键帧。"},
        {"kind": "REFERENCE_ASSET", "text": "保持门、走廊和储物间的空间几何与参考图一致。"},
        {"kind": "SCENE_STYLE_CONTINUITY", "text": "深夜走廊只有门缝冷光和远处弱暖灯，材质反射克制。"},
        {"kind": "STATIC_FRAME", "text": anchor},
        {"kind": "NEGATIVE", "text": "不要新增人物、文字、粒子或无法解释的光源。"},
    ]
    return {
        **_base(), "mode": "IMAGE_PROMPT", "source_units": units,
        "image_prompt": {
            "separator": "\n\n", "prompt_sections": sections,
            "prompt_text": "\n\n".join(section["text"] for section in sections),
            "source_bindings": [{"source_unit_id": "SRC-01", "prompt_anchor": anchor}],
        },
    }


def self_test() -> None:
    import copy

    cases: list[tuple[str, dict[str, Any], str | None]] = [
        ("script_positive", _script_fixture(), None),
        ("video_positive", _video_fixture(), None),
        ("image_positive", _image_fixture(), None),
    ]

    missing_event = _script_fixture()
    missing_event["script"]["scenes"][0]["beats"] = []
    missing_event["script"]["scenes"][0]["source_unit_ids"] = ["SRC-02", "SRC-03"]
    cases.append(("script_missing_event", missing_event, "CF_SOURCE_COVERAGE"))

    changed_dialogue = _script_fixture()
    changed_dialogue["script"]["scenes"][0]["dialogue_turns"][0]["text"] = "你来过。"
    cases.append(("script_changed_dialogue", changed_dialogue, "CF_DIALOGUE_CHANGED"))

    swapped_speaker = _script_fixture()
    swapped_speaker["script"]["scenes"][0]["dialogue_turns"][0]["speaker"] = "周启"
    cases.append(("script_swapped_speaker", swapped_speaker, "CF_SPEAKER_CHANGED"))

    reordered = _script_fixture()
    reordered["script"]["scenes"][0]["dialogue_turns"].reverse()
    cases.append(("script_reordered_dialogue", reordered, "CF_SOURCE_REORDERED"))

    silent_compression = _video_fixture()
    silent_compression["delivery_fidelity"] = "USER_REQUESTED_COMPACT"
    cases.append(("silent_compression", silent_compression, "CF_SILENT_COMPRESSION"))

    missing_section = _video_fixture()
    missing_section["video_prompt"]["prompt_sections"] = missing_section["video_prompt"]["prompt_sections"][:-1]
    missing_section["video_prompt"]["prompt_text"] = "\n\n".join(row["text"] for row in missing_section["video_prompt"]["prompt_sections"])
    cases.append(("video_missing_section", missing_section, "CF_SECTION_CONTRACT"))

    timeline_gap = _video_fixture()
    timeline_gap["video_prompt"]["beats"][1]["start_seconds"] = 5
    cases.append(("video_timeline_gap", timeline_gap, "CF_TIMELINE_GAP"))

    anchor_loss = _video_fixture()
    anchor_loss["video_prompt"]["beats"][1]["prompt_anchor"] = "林岚说完后保持注视。"
    cases.append(("video_anchor_loss", anchor_loss, "CF_VIDEO_ANCHOR_LOSS"))

    dialogue_duplicate = _video_fixture()
    dialogue_duplicate["video_prompt"]["prompt_sections"][-1]["text"] += " 禁止改写：你昨晚来过这里。"
    dialogue_duplicate["video_prompt"]["prompt_text"] = "\n\n".join(row["text"] for row in dialogue_duplicate["video_prompt"]["prompt_sections"])
    cases.append(("video_dialogue_duplicate", dialogue_duplicate, "CF_DIALOGUE_OCCURRENCE"))

    mouth_conflict = _video_fixture()
    bad_beat = mouth_conflict["video_prompt"]["beats"][1]
    bad_beat["action"] = "林岚嘴里叼着钥匙，仍抬眼直视周启。"
    bad_beat["prompt_anchor"] = " ".join(str(bad_beat[field]) for field in (
        "camera", "action", "performance", "contact_material_environment", "dialogue_audio", "exit_state"
    ))
    mouth_conflict["video_prompt"]["prompt_sections"][3]["text"] = "\n".join(
        beat["prompt_anchor"] for beat in mouth_conflict["video_prompt"]["beats"]
    )
    mouth_conflict["video_prompt"]["prompt_text"] = "\n\n".join(
        row["text"] for row in mouth_conflict["video_prompt"]["prompt_sections"]
    )
    cases.append(("video_mouth_occupied_speech", mouth_conflict, "CF_MOUTH_OCCUPIED_SPEECH"))

    image_dynamic = _image_fixture()
    image_dynamic["image_prompt"]["duration_seconds"] = 8
    cases.append(("image_dynamic_leak", image_dynamic, "CF_IMAGE_DYNAMIC_LEAK"))

    image_missing = _image_fixture()
    image_missing["image_prompt"]["source_bindings"] = []
    cases.append(("image_missing_source", image_missing, "CF_SOURCE_COVERAGE"))

    failures: list[str] = []
    for name, payload, expected_code in cases:
        result = validate(copy.deepcopy(payload))
        codes = {row["code"] for row in result["errors"]}
        if expected_code is None and result["status"] != "PASS":
            failures.append(f"{name}: expected PASS, got {sorted(codes)}")
        elif expected_code is not None and expected_code not in codes:
            failures.append(f"{name}: expected {expected_code}, got {sorted(codes)}")
    if failures:
        raise AssertionError("; ".join(failures))
    print(f"SELF_TEST_PASS: {len(cases)}/{len(cases)}")


def read_payload(path: Path | None) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig") if path else sys.stdin.read()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="creative preflight JSON; omit for stdin")
    parser.add_argument("--output", type=Path, help="write the full machine report to a new JSON file")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    try:
        result = validate(read_payload(args.input))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            print(json.dumps({"status": "ERROR", "message": f"refusing to overwrite: {args.output}"}, ensure_ascii=False), file=sys.stderr)
            return 2
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
