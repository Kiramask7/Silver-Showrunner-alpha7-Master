#!/usr/bin/env python3
"""Validate the Alpha.7 Master dialogue/action/handoff/production ledger."""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

CONTRACT_VERSION = "alpha7-master-production-control-v1"
PRODUCTION_VALIDATION = "NOT_TESTED"
DELIVERY_MODES = {"ONSCREEN_LIP", "L_CUT", "VOICE_OVER", "AUDIO_POST_REQUIRED"}
MOTION_ROLES = {"MOTION", "CAMERA", "TIMING", "BLOCKING"}
MOTION_FORBIDDEN = {"identity", "wardrobe", "environment", "logo"}
PLACEHOLDERS = (
    "对白见下方",
    "此处同步说出",
    "按本镜构图落位",
    "本镜无来源口播",
    "逐字对白见下方",
)
PUNCTUATION_MS = {
    "，": 180,
    "、": 180,
    ",": 180,
    "；": 250,
    "：": 250,
    ";": 250,
    ":": 250,
    "。": 350,
    "？": 350,
    "！": 350,
    ".": 350,
    "?": 350,
    "!": 350,
}
NON_SPOKEN_RE = re.compile(r"[\s，、,；：;:。？！.?!…—\-‘’“”\"'（）()【】\[\]《》<>]")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class Report:
    def __init__(self) -> None:
        self.errors: list[dict[str, str]] = []

    def add(self, code: str, path: str, message: str, repair: str) -> None:
        self.errors.append(
            {"code": code, "path": path, "message": message, "repair": repair}
        )

    def public_repairs(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for error in self.errors:
            repair = error["repair"]
            if repair in seen:
                continue
            seen.add(repair)
            rows.append(
                {
                    "sample": "当前制作记录",
                    "area": _public_area(error["code"]),
                    "instruction": repair,
                }
            )
            if len(rows) >= 8:
                break
        return rows


def _public_area(code: str) -> str:
    if "DIALOGUE" in code or "TIMING" in code:
        return "对白与时长"
    if "ACTION" in code:
        return "动作与结束画面"
    if "REFERENCE" in code or "RIGHTS" in code:
        return "参考素材职责"
    if "HANDOFF" in code or "OBSERVED" in code:
        return "镜头衔接"
    if "ASSET" in code:
        return "素材登记"
    if "COST" in code or "ATTEMPT" in code:
        return "成本与重试"
    if "PROGRESS" in code or "STAGE" in code:
        return "项目进度"
    return "制作记录"


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def spoken_units(text: str) -> int:
    return len(NON_SPOKEN_RE.sub("", text))


def punctuation_pause_ms(text: str) -> int:
    ellipsis_pairs = text.count("……")
    em_dashes = text.count("——")
    remainder = text.replace("……", "").replace("——", "")
    return (
        ellipsis_pairs * 600
        + em_dashes * 600
        + sum(PUNCTUATION_MS.get(character, 0) for character in remainder)
    )


def computed_runtime_ms(text: str, speech_rate_cps: float, adjustment_ms: int = 0) -> int:
    if speech_rate_cps <= 0:
        return 0
    return math.ceil(spoken_units(text) / speech_rate_cps * 1000) + punctuation_pause_ms(text) + adjustment_ms


def _unique_id(
    report: Report, seen: set[str], value: Any, path: str, kind: str
) -> str | None:
    if not _is_text(value):
        report.add(
            f"PC_{kind}_ID",
            path,
            "缺少稳定编号。",
            "为这条记录补一个不会与其他记录重复的编号。",
        )
        return None
    item = value.strip()
    if item in seen:
        report.add(
            f"PC_{kind}_DUPLICATE",
            path,
            "编号重复。",
            "让每条记录使用不同编号，并保留旧编号供追溯。",
        )
        return None
    seen.add(item)
    return item


def validate_dialogues(data: dict[str, Any], report: Report) -> tuple[set[str], set[str]]:
    dialogue_ids: set[str] = set()
    fragment_ids: set[str] = set()
    shot_ids: set[str] = set()
    for index, raw in enumerate(_list(data.get("dialogue_schedule"))):
        path = f"$.dialogue_schedule[{index}]"
        row = _dict(raw)
        _unique_id(report, dialogue_ids, row.get("dialogue_id"), f"{path}.dialogue_id", "DIALOGUE")
        speaker = row.get("speaker")
        text = row.get("verbatim_text")
        if not _is_text(speaker) or not _is_text(text) or not _is_text(row.get("source_ref")):
            report.add(
                "PC_DIALOGUE_SOURCE",
                path,
                "对白缺少说话人、逐字原文或来源位置。",
                "补齐说话人、原文和来源位置，再拆镜。",
            )
            continue
        rate = row.get("speech_rate_cps")
        adjustment = row.get("delivery_adjustment_ms")
        minimum = row.get("minimum_duration_ms")
        available = row.get("available_duration_ms")
        basis = row.get("timing_basis")
        status = row.get("timing_status")
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or not 0 < float(rate) <= 5:
            report.add(
                "PC_DIALOGUE_RATE",
                f"{path}.speech_rate_cps",
                "对白语速依据不合法。",
                "使用可说明依据的自然语速，不能用异常高速把台词硬塞进镜头。",
            )
            rate = 4.0
        if not isinstance(adjustment, int) or isinstance(adjustment, bool) or adjustment < 0:
            report.add(
                "PC_DIALOGUE_ADJUSTMENT",
                f"{path}.delivery_adjustment_ms",
                "表演与呼吸附加时间不合法。",
                "把喘息、哭笑、延音或表演停顿写成非负毫秒数。",
            )
            adjustment = 0
        expected_minimum = computed_runtime_ms(str(text), float(rate), adjustment)
        if basis == "COMPUTED" and minimum != expected_minimum:
            report.add(
                "PC_DIALOGUE_TIMING_RECOMPUTE",
                f"{path}.minimum_duration_ms",
                "对白最低时长与当前原文不一致。",
                "重新按逐字原文、标点停顿和表演停顿计算最低时长。",
            )
        if status == "FIT":
            if basis not in {"COMPUTED", "MEASURED"}:
                report.add(
                    "PC_DIALOGUE_FALSE_FIT",
                    f"{path}.timing_basis",
                    "没有计算或实测依据却标成可容纳。",
                    "先运行对白时长检查；无工具时只保留保守排程，不宣称已经精算通过。",
                )
            if not isinstance(minimum, int) or not isinstance(available, int) or minimum > available:
                report.add(
                    "PC_DIALOGUE_OVERFLOW",
                    path,
                    "整句对白时长超过可用发声时间。",
                    "延长片段，或在自然语义边界拆成下一支；不要删字或加速硬塞。",
                )
        if status == "SPLIT_REQUIRED" and isinstance(minimum, int) and isinstance(available, int) and minimum <= available:
            report.add(
                "PC_DIALOGUE_STATUS_STALE",
                f"{path}.timing_status",
                "对白时长状态没有随排程更新。",
                "按最新原文和镜头时长重新计算并更新状态。",
            )

        fragments = _list(row.get("fragments"))
        if not fragments:
            report.add(
                "PC_DIALOGUE_FRAGMENT_MISSING",
                f"{path}.fragments",
                "逐字对白没有分配到具体镜头。",
                "把整句按连续文字位置分配到实际发生的镜头和时间段。",
            )
            continue
        expected_offset = 0
        reconstructed: list[str] = []
        previous_end_ms = -1
        for fragment_index, raw_fragment in enumerate(fragments):
            fragment_path = f"{path}.fragments[{fragment_index}]"
            fragment = _dict(raw_fragment)
            _unique_id(report, fragment_ids, fragment.get("fragment_id"), f"{fragment_path}.fragment_id", "FRAGMENT")
            if fragment.get("fragment_index") != fragment_index:
                report.add(
                    "PC_DIALOGUE_FRAGMENT_ORDER",
                    f"{fragment_path}.fragment_index",
                    "对白片段顺序号不连续。",
                    "从零开始按原文顺序连续编号，不要跳号或倒序。",
                )
            start_offset = fragment.get("start_offset")
            end_offset = fragment.get("end_offset")
            fragment_text = fragment.get("text")
            if not isinstance(start_offset, int) or not isinstance(end_offset, int):
                report.add(
                    "PC_DIALOGUE_CURSOR_TYPE",
                    fragment_path,
                    "对白文字位置不是整数。",
                    "重新从原句首字开始记录每段的准确起止位置。",
                )
                continue
            if start_offset != expected_offset or end_offset <= start_offset or end_offset > len(text):
                report.add(
                    "PC_DIALOGUE_CURSOR_GAP",
                    fragment_path,
                    "对白片段出现缺口、重叠或越界。",
                    "让上一段结束位置与下一段开始位置完全相接，并覆盖到原句末字。",
                )
            expected_slice = text[start_offset:end_offset] if 0 <= start_offset <= end_offset <= len(text) else ""
            if fragment_text != expected_slice:
                report.add(
                    "PC_DIALOGUE_CHANGED",
                    f"{fragment_path}.text",
                    "镜头中的台词不是来源原文对应片段。",
                    "直接复制来源原句的对应文字，不要改写、漏字或重复。",
                )
            if isinstance(fragment_text, str):
                reconstructed.append(fragment_text)
            expected_offset = end_offset
            shot_id = fragment.get("shot_id")
            if _is_text(shot_id):
                shot_ids.add(shot_id.strip())
            else:
                report.add(
                    "PC_DIALOGUE_SHOT",
                    f"{fragment_path}.shot_id",
                    "对白片段没有归属镜头。",
                    "把每段台词放进一个真实镜头，并明确声音从哪里继续。",
                )
            delivery_mode = fragment.get("delivery_mode")
            if delivery_mode not in DELIVERY_MODES:
                report.add(
                    "PC_DIALOGUE_DELIVERY",
                    f"{fragment_path}.delivery_mode",
                    "对白发声方式不明确。",
                    "明确当前是镜内口型、声音延后、来源允许的画外音，还是后期配音。",
                )
            expected_bridge = fragment_index > 0
            if fragment.get("bridge_from_previous") is not expected_bridge:
                report.add(
                    "PC_DIALOGUE_BRIDGE",
                    f"{fragment_path}.bridge_from_previous",
                    "同一句对白的声音桥设置不连续。",
                    "第一段正常起句，后续每段都承接同一句声音，不重新起句。",
                )
            start_ms = fragment.get("start_ms")
            end_ms = fragment.get("end_ms")
            if (
                not isinstance(start_ms, int)
                or not isinstance(end_ms, int)
                or start_ms < 0
                or end_ms <= start_ms
                or start_ms < previous_end_ms
            ):
                report.add(
                    "PC_DIALOGUE_FRAGMENT_TIME",
                    fragment_path,
                    "对白片段时间段无效或互相重叠。",
                    "按播放顺序填写不重叠的起止时间，并给每段留足自然发声时间。",
                )
            elif isinstance(fragment_text, str):
                fragment_minimum = computed_runtime_ms(fragment_text, float(rate), 0)
                if fragment_minimum > end_ms - start_ms:
                    report.add(
                        "PC_DIALOGUE_LOCAL_OVERFLOW",
                        fragment_path,
                        "这一镜实际分配的台词说不完。",
                        "重新调整不等长镜头边界，或把同一句自然续到下一镜。",
                    )
                previous_end_ms = end_ms
            if not _is_text(fragment.get("visual_purpose")):
                report.add(
                    "PC_DIALOGUE_VISUAL_PURPOSE",
                    f"{fragment_path}.visual_purpose",
                    "切镜没有说明新的观看任务。",
                    "说明这一镜承担的听者反应、证据、道具状态、空间信息或表演变化。",
                )
        if expected_offset != len(text) or "".join(reconstructed) != text:
            report.add(
                "PC_DIALOGUE_RECONSTRUCTION",
                path,
                "全部镜头拼接后不能逐字还原原句。",
                "从原句首字到末字重新连续分配，确保没有遗漏、重复或换序。",
            )
    return dialogue_ids, shot_ids


def validate_references(data: dict[str, Any], report: Report) -> tuple[set[str], dict[str, dict[str, Any]]]:
    reference_ids: set[str] = set()
    exact_tags: set[str] = set()
    by_tag: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_list(data.get("reference_roles"))):
        path = f"$.reference_roles[{index}]"
        row = _dict(raw)
        _unique_id(report, reference_ids, row.get("reference_id"), f"{path}.reference_id", "REFERENCE")
        tag = row.get("exact_tag")
        if not _is_text(tag):
            report.add(
                "PC_REFERENCE_TAG",
                f"{path}.exact_tag",
                "参考素材缺少原始标签。",
                "按上传界面的原样写法登记参考标签，不要改空格、大小写或编号。",
            )
            continue
        tag = tag.strip()
        if tag in exact_tags:
            report.add(
                "PC_REFERENCE_TAG_DUPLICATE",
                f"{path}.exact_tag",
                "同一参考标签登记了多次。",
                "每个参考素材只保留一条主职责记录。",
            )
        exact_tags.add(tag)
        by_tag[tag] = row
        controls = {str(item).strip().lower() for item in _list(row.get("controls")) if _is_text(item)}
        forbidden = {str(item).strip().lower() for item in _list(row.get("forbidden_transfer")) if _is_text(item)}
        if not controls:
            report.add(
                "PC_REFERENCE_CONTROLS",
                f"{path}.controls",
                "参考素材没有说明它负责什么。",
                "为这项参考指定一个主要职责，并列出真正需要继承的内容。",
            )
        if controls & forbidden:
            report.add(
                "PC_REFERENCE_ROLE_BLEED",
                path,
                "同一内容被同时写成继承和禁止继承。",
                "把参考职责拆清楚：保留项和禁止带入项不能重叠。",
            )
        if row.get("primary_role") in MOTION_ROLES:
            missing = sorted(MOTION_FORBIDDEN - forbidden)
            if missing:
                report.add(
                    "PC_REFERENCE_MOTION_BLEED",
                    f"{path}.forbidden_transfer",
                    "动作或摄影参考没有隔离人物、服装、环境和标识。",
                    "明确动作参考只传递动作或摄影，不带入人物身份、服装、环境和品牌标识。",
                )
        if row.get("rights_status") == "UNKNOWN":
            report.add(
                "PC_REFERENCE_RIGHTS_UNKNOWN",
                f"{path}.rights_status",
                "参考素材的使用权限尚未确认。",
                "先确认素材自有、已授权、已许可或属于公版，再进入真实生成。",
            )
    return exact_tags, by_tag


def validate_actions(
    data: dict[str, Any], report: Report, exact_tags: set[str]
) -> set[str]:
    action_shots: set[str] = set()
    required_text = (
        "actor_or_object",
        "setup",
        "force_or_action",
        "contact_or_release",
        "visible_consequence",
        "endpoint",
        "camera_task",
    )
    for index, raw in enumerate(_list(data.get("action_contracts"))):
        path = f"$.action_contracts[{index}]"
        row = _dict(raw)
        shot_id = _unique_id(report, action_shots, row.get("shot_id"), f"{path}.shot_id", "ACTION")
        for key in required_text:
            if not _is_text(row.get(key)):
                report.add(
                    "PC_ACTION_CAUSALITY",
                    f"{path}.{key}",
                    "动作链缺少准备、施力、接触、后果、终点或摄影任务。",
                    "把动作写成准备、发生、接触或释放、可见后果和确定结束画面，并让摄影只服务这一动作。",
                )
        tags = [item.strip() for item in _list(row.get("reference_tags")) if _is_text(item)]
        for tag in tags:
            if tag not in exact_tags:
                report.add(
                    "PC_REFERENCE_TAG_DRIFT",
                    f"{path}.reference_tags",
                    "镜头使用了没有登记或已被改写的参考标签。",
                    "直接复制参考登记里的原始标签，不要改写、翻译或重新编号。",
                )
        if shot_id and row.get("force_or_action") == row.get("camera_task"):
            report.add(
                "PC_ACTION_CAMERA_DUPLICATE",
                path,
                "摄影任务只是重复动作文字。",
                "把摄影改成观看位置、运动关系和结束构图，不要重抄动作。",
            )
    return action_shots


def validate_handoffs(
    data: dict[str, Any], report: Report, action_shots: set[str], exact_tags: set[str]
) -> None:
    boundary_ids: set[str] = set()
    required_anchors = (
        "identity_wardrobe",
        "position_screen_direction",
        "gaze_eyeline",
        "pose_action_phase",
        "prop_ownership_contact",
        "mouth_hand_occupancy",
        "open_motion",
        "camera_axis_phase",
        "lighting_state",
        "audio_state",
        "dialogue_cursor",
        "edit_boundary",
    )
    pairs: set[tuple[str, str]] = set()
    for index, raw in enumerate(_list(data.get("shot_handoffs"))):
        path = f"$.shot_handoffs[{index}]"
        row = _dict(raw)
        _unique_id(report, boundary_ids, row.get("boundary_id"), f"{path}.boundary_id", "HANDOFF")
        source = row.get("from_shot_id")
        target = row.get("to_shot_id")
        if not _is_text(source) or not _is_text(target) or source == target:
            report.add(
                "PC_HANDOFF_PAIR",
                path,
                "镜头交接缺少有效的前后镜头。",
                "为每条交接写清楚上一镜和下一镜，二者不能相同。",
            )
        else:
            pair = (source.strip(), target.strip())
            if pair in pairs:
                report.add(
                    "PC_HANDOFF_DUPLICATE",
                    path,
                    "同一对镜头登记了多条交接。",
                    "合并成一条权威交接记录，其他方案放到备用切法。",
                )
            pairs.add(pair)
            for shot in pair:
                if shot not in action_shots:
                    report.add(
                        "PC_HANDOFF_UNKNOWN_SHOT",
                        path,
                        "交接引用了没有动作合同的镜头。",
                        "先为前后镜头补齐动作与结束画面，再设计交接。",
                    )
        if not _is_text(row.get("baton_out")) or row.get("receiver_in") != row.get("baton_out"):
            report.add(
                "PC_HANDOFF_BATON",
                path,
                "上一镜交出的接力物与下一镜接收内容没有闭合。",
                "使用同一个明确的动作、视线、道具、构图、遮挡或声音线索连接前后镜头。",
            )
        anchors = _dict(row.get("anchors"))
        for key in required_anchors:
            if not _is_text(anchors.get(key)):
                report.add(
                    "PC_HANDOFF_ANCHOR",
                    f"{path}.anchors.{key}",
                    "镜头交接缺少一项连续性事实。",
                    "补齐人物、位置、视线、动作阶段、道具、手口占用、摄影、光线、声音和对白进度。",
                )
        take_status = row.get("source_take_status")
        observed = row.get("observed_end_state")
        authority = row.get("authoritative_end_state")
        if take_status == "ACCEPTED":
            if not _is_text(observed) or authority != "OBSERVED_ACCEPTED":
                report.add(
                    "PC_OBSERVED_STATE_PRIORITY",
                    path,
                    "已接受素材没有把真实结束状态设为后续依据。",
                    "记录成片真实末态，并让它覆盖原先计划后再编译下一镜。",
                )
        elif take_status == "NO_MEDIA":
            if observed is not None or authority != "PLANNED":
                report.add(
                    "PC_OBSERVED_STATE_INVENTED",
                    path,
                    "没有回传素材却登记了真实观察状态。",
                    "无真实素材时只保留计划状态，并明确尚未观察。",
                )
        elif take_status == "REJECTED" and authority != "PLANNED":
            report.add(
                "PC_OBSERVED_REJECTED_CANON",
                path,
                "被拒绝素材被错误地当成后续依据。",
                "移除被拒绝素材的连续性权威，下一镜从计划或重新锚定的参考开始。",
            )
        for tag in [item.strip() for item in _list(row.get("reference_tags")) if _is_text(item)]:
            if tag not in exact_tags:
                report.add(
                    "PC_REFERENCE_TAG_DRIFT",
                    f"{path}.reference_tags",
                    "交接使用了没有登记或已被改写的参考标签。",
                    "直接复制参考登记里的原始标签，不要改写、翻译或重新编号。",
                )
        for key in ("audio_bridge", "edit_type", "fallback_cut", "planned_end_state"):
            if not _is_text(row.get(key)):
                report.add(
                    "PC_HANDOFF_EDIT_PLAN",
                    f"{path}.{key}",
                    "交接缺少声音、剪辑、备用切法或计划终态。",
                    "为这对镜头写出主剪法、声音桥、备用切法和上一镜可见终态。",
                )


def validate_assets(data: dict[str, Any], report: Report) -> None:
    asset_ids: set[str] = set()
    for index, raw in enumerate(_list(data.get("assets"))):
        path = f"$.assets[{index}]"
        row = _dict(raw)
        _unique_id(report, asset_ids, row.get("asset_id"), f"{path}.asset_id", "ASSET")
        status = row.get("status")
        evidence = [item for item in _list(row.get("evidence")) if _is_text(item)]
        file_path = row.get("file_path")
        digest = row.get("sha256")
        if status == "ACCEPTED" and not evidence:
            report.add(
                "PC_ASSET_ACCEPTED_NO_EVIDENCE",
                path,
                "素材被标为已接受，但没有批准或检查证据。",
                "补上实际文件、用户批准或检查记录；否则把状态退回待检查。",
            )
        if status in {"GENERATED_UNREVIEWED", "ACCEPTED"} and row.get("source_level") == "GENERATED_OUTPUT":
            if not _is_text(file_path) or not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                report.add(
                    "PC_ASSET_FILE_PROOF",
                    path,
                    "已生成素材缺少可访问文件位置或校验值。",
                    "登记真实文件位置和 SHA-256；聊天预览或计划名称不能冒充已交付文件。",
                )
        if _is_text(file_path) and (not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None):
            report.add(
                "PC_ASSET_HASH",
                f"{path}.sha256",
                "已登记文件没有有效的 SHA-256。",
                "从实际文件计算并登记 64 位小写 SHA-256。",
            )


def validate_progress_cost_attempts(
    data: dict[str, Any], report: Report, action_shots: set[str]
) -> None:
    stage_ids: set[str] = set()
    in_progress: list[str] = []
    current_stage = data.get("current_stage")
    current_matches = False
    for index, raw in enumerate(_list(data.get("progress"))):
        path = f"$.progress[{index}]"
        row = _dict(raw)
        stage_id = _unique_id(report, stage_ids, row.get("stage_id"), f"{path}.stage_id", "PROGRESS")
        status = row.get("status")
        if stage_id == current_stage or row.get("name") == current_stage:
            current_matches = True
        if status == "IN_PROGRESS" and stage_id:
            in_progress.append(stage_id)
        if status == "COMPLETE" and not any(_is_text(item) for item in _list(row.get("completion_evidence"))):
            report.add(
                "PC_PROGRESS_COMPLETE_NO_EVIDENCE",
                path,
                "阶段标成完成，但没有完成证据。",
                "补上实际文件、批准记录或检查结果；否则把阶段退回进行中。",
            )
        if status == "BLOCKED" and not _is_text(row.get("blocker")):
            report.add(
                "PC_PROGRESS_BLOCKER",
                path,
                "阶段标成受阻，但没有写明阻断原因。",
                "写清楚唯一阻断点和恢复后从哪里继续。",
            )
        if not _is_text(row.get("resume_from")):
            report.add(
                "PC_PROGRESS_RESUME",
                f"{path}.resume_from",
                "阶段缺少恢复入口。",
                "用一句自然中文写清楚下次从哪个已保存结果继续。",
            )
    if len(in_progress) > 1:
        report.add(
            "PC_PROGRESS_MULTI_ACTIVE",
            "$.progress",
            "同时有多个阶段被标成正在进行。",
            "只保留一个当前阶段，其他阶段改成未开始、受阻或已完成。",
        )
    if _list(data.get("progress")) and not current_matches:
        report.add(
            "PC_CURRENT_STAGE_STALE",
            "$.current_stage",
            "当前阶段与进度表对不上。",
            "把当前阶段改成进度表中真实正在处理或刚完成的阶段。",
        )

    cost_ids: set[str] = set()
    for index, raw in enumerate(_list(data.get("cost_ledger"))):
        path = f"$.cost_ledger[{index}]"
        row = _dict(raw)
        _unique_id(report, cost_ids, row.get("cost_id"), f"{path}.cost_id", "COST")
        amount = row.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            report.add(
                "PC_COST_AMOUNT",
                f"{path}.amount",
                "成本金额不合法。",
                "金额使用非负数字；不知道价格时先不登记金额并标明尚未核实。",
            )
        if row.get("kind") == "ACTUAL":
            if not any(_is_text(item) for item in _list(row.get("evidence"))) or not _is_text(row.get("verified_at")):
                report.add(
                    "PC_COST_ACTUAL_NO_EVIDENCE",
                    path,
                    "实际成本没有账单、回执或核验时间。",
                    "把估计和实际分开；实际发生金额必须附依据和核验时间。",
                )

    attempt_shots: set[str] = set()
    for index, raw in enumerate(_list(data.get("attempt_budgets"))):
        path = f"$.attempt_budgets[{index}]"
        row = _dict(raw)
        shot_id = row.get("shot_id")
        if not _is_text(shot_id) or shot_id not in action_shots:
            report.add(
                "PC_ATTEMPT_UNKNOWN_SHOT",
                f"{path}.shot_id",
                "重试上限没有绑定真实镜头。",
                "把每条尝试预算绑定到已有镜头。",
            )
        elif shot_id in attempt_shots:
            report.add(
                "PC_ATTEMPT_DUPLICATE",
                f"{path}.shot_id",
                "同一镜头有多条重试上限。",
                "合并成一条当前尝试预算并保留历史记录。",
            )
        else:
            attempt_shots.add(shot_id)
        maximum = row.get("max_attempts")
        used = row.get("used_attempts")
        if (
            isinstance(maximum, bool)
            or isinstance(used, bool)
            or not isinstance(maximum, int)
            or not isinstance(used, int)
            or maximum < 1
            or used < 0
            or used > maximum
        ):
            report.add(
                "PC_ATTEMPT_BUDGET",
                path,
                "尝试次数没有合法上限，或已经超过上限。",
                "生成前设定明确的最大次数和停止条件，达到上限就改方案。",
            )
        if row.get("retry_policy") != "ONE_VARIABLE":
            report.add(
                "PC_ATTEMPT_POLICY",
                f"{path}.retry_policy",
                "重试没有遵守单变量原则。",
                "每次只改提示词一处、随机种子、生成方式或一项参考。",
            )
        if row.get("external_paid") is True and row.get("user_approved") is not True:
            report.add(
                "PC_ATTEMPT_PAID_APPROVAL",
                path,
                "付费外部生成没有用户批准。",
                "先说明预计调用次数、费用依据和停止条件，取得用户确认后再执行。",
            )


def validate(data: Any) -> dict[str, Any]:
    report = Report()
    if not isinstance(data, dict):
        report.add(
            "PC_ROOT",
            "$",
            "制作记录不是一个完整对象。",
            "使用制作记录模板重新保存为 JSON 对象。",
        )
        document: dict[str, Any] = {}
    else:
        document = data
    if document.get("contract_version") != CONTRACT_VERSION:
        report.add(
            "PC_CONTRACT_VERSION",
            "$.contract_version",
            "制作记录版本不匹配。",
            "把记录转换为当前 v1 制作合同后再检查。",
        )
    if not _is_text(document.get("project_id")):
        report.add(
            "PC_PROJECT_ID",
            "$.project_id",
            "项目缺少稳定名称或编号。",
            "为项目填写一个固定且不会随批次改变的编号。",
        )
    if document.get("production_validation") != PRODUCTION_VALIDATION:
        report.add(
            "PC_PRODUCTION_VALIDATION",
            "$.production_validation",
            "文字制作检查不能证明真实素材已经通过。",
            "在没有真实生成、观看和媒体质量检查前，保持为尚未进行真实素材验证。",
        )
    if not _is_text(document.get("current_stage")):
        report.add(
            "PC_CURRENT_STAGE",
            "$.current_stage",
            "项目没有当前阶段。",
            "填写当前正在处理的阶段，并与进度表保持一致。",
        )
    for key in (
        "dialogue_schedule",
        "action_contracts",
        "reference_roles",
        "shot_handoffs",
        "assets",
        "progress",
        "cost_ledger",
        "attempt_budgets",
    ):
        if not isinstance(document.get(key), list):
            report.add(
                "PC_COLLECTION",
                f"$.{key}",
                "制作记录缺少一组必要清单。",
                "按当前模板补齐对白、动作、参考、交接、素材、进度、成本和重试清单；没有内容时使用空列表。",
            )

    _dialogue_ids, dialogue_shots = validate_dialogues(document, report)
    exact_tags, _reference_by_tag = validate_references(document, report)
    action_shots = validate_actions(document, report, exact_tags)
    missing_action_shots = sorted(dialogue_shots - action_shots)
    if missing_action_shots:
        report.add(
            "PC_DIALOGUE_ACTION_LINK",
            "$.action_contracts",
            "含对白的镜头缺少动作与摄影合同。",
            "为每个对白镜头补齐准备、动作、可见后果、结束画面和摄影任务。",
        )
    validate_handoffs(document, report, action_shots, exact_tags)
    validate_assets(document, report)
    validate_progress_cost_attempts(document, report, action_shots)

    return {
        "contract_version": CONTRACT_VERSION,
        "valid": not report.errors,
        "root_error_count": len(report.errors),
        "errors": report.errors,
        "public_repairs": report.public_repairs(),
        "production_validation": PRODUCTION_VALIDATION,
    }


def _action(shot_id: str, reference_tags: list[str] | None = None) -> dict[str, Any]:
    return {
        "shot_id": shot_id,
        "actor_or_object": "表演者",
        "setup": "动作开始前重心稳定，关键道具位置清楚。",
        "force_or_action": "表演者只完成当前镜头的一个主要动作。",
        "contact_or_release": "接触发生在画面可见位置，随后明确释放或稳定持有。",
        "visible_consequence": "受力、衣料和道具位置发生与动作一致的变化。",
        "endpoint": "镜头停在动作已经完成且可供下一镜承接的画面。",
        "camera_task": "镜头保持动作轴线，并在动作完成时停稳。",
        "reference_tags": reference_tags or [],
    }


def _anchors(cursor: str) -> dict[str, str]:
    return {
        "identity_wardrobe": "同一人物与服装保持不变。",
        "position_screen_direction": "主体保持由左向右的画面方向。",
        "gaze_eyeline": "视线继续指向画面右侧目标。",
        "pose_action_phase": "承接上一镜动作完成后的稳定姿态。",
        "prop_ownership_contact": "道具仍由同一人物持有，接触点不变。",
        "mouth_hand_occupancy": "嘴部与双手占用状态明确且不冲突。",
        "open_motion": "没有未说明的开放动作。",
        "camera_axis_phase": "保持同一空间轴线，下一镜可有意切换景别。",
        "lighting_state": "主光仍来自画面左侧。",
        "audio_state": "环境底声连续。",
        "dialogue_cursor": cursor,
        "edit_boundary": "在动作完成并停稳后切换。",
    }


def _base(project_id: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "project_id": project_id,
        "production_validation": PRODUCTION_VALIDATION,
        "current_stage": "分镜与提示词",
        "dialogue_schedule": [],
        "action_contracts": [],
        "reference_roles": [],
        "shot_handoffs": [],
        "assets": [],
        "progress": [
            {
                "stage_id": "STAGE-STORYBOARD",
                "name": "分镜与提示词",
                "status": "IN_PROGRESS",
                "completion_evidence": [],
                "blocker": None,
                "resume_from": "从当前已保存的镜头交接表继续。",
            }
        ],
        "cost_ledger": [],
        "attempt_budgets": [],
    }


def _dialogue_fixture() -> dict[str, Any]:
    data = _base("TEST-DIALOGUE")
    text = "我不是来求你原谅的，我只是想让你知道，那封信我一直没有拆。"
    cuts = (0, 11, 24, len(text))
    fragments = []
    start_ms = 0
    for index, shot_id in enumerate(("SH001", "SH002", "SH003")):
        fragment_text = text[cuts[index] : cuts[index + 1]]
        duration = computed_runtime_ms(fragment_text, 4.0) + 500
        fragments.append(
            {
                "fragment_id": f"FRAG-{index + 1:03d}",
                "fragment_index": index,
                "shot_id": shot_id,
                "start_offset": cuts[index],
                "end_offset": cuts[index + 1],
                "text": fragment_text,
                "start_ms": start_ms,
                "end_ms": start_ms + duration,
                "delivery_mode": "ONSCREEN_LIP" if index == 0 else "L_CUT",
                "bridge_from_previous": index > 0,
                "visual_purpose": "建立说话人。" if index == 0 else "让听者反应承担话外含义。",
            }
        )
        start_ms += duration
    minimum = computed_runtime_ms(text, 4.0, 300)
    data["dialogue_schedule"] = [
        {
            "dialogue_id": "DLG-001",
            "speaker": "林砚",
            "verbatim_text": text,
            "source_ref": "测试原文第一段",
            "speech_rate_cps": 4.0,
            "delivery_adjustment_ms": 300,
            "minimum_duration_ms": minimum,
            "available_duration_ms": start_ms,
            "timing_basis": "COMPUTED",
            "timing_status": "FIT",
            "fragments": fragments,
        }
    ]
    data["action_contracts"] = [_action("SH001"), _action("SH002"), _action("SH003")]
    for index, pair in enumerate((("SH001", "SH002"), ("SH002", "SH003")), start=1):
        baton = "同一句对白声音连续，画面切到听者反应。"
        data["shot_handoffs"].append(
            {
                "boundary_id": f"BOUND-{index:03d}",
                "from_shot_id": pair[0],
                "to_shot_id": pair[1],
                "continuity_mode": "EDITABLE_CUT",
                "receiver_in": baton,
                "baton_out": baton,
                "planned_end_state": "说话声未断，听者开始接收信息。",
                "observed_end_state": None,
                "source_take_status": "NO_MEDIA",
                "authoritative_end_state": "PLANNED",
                "anchors": _anchors(f"DLG-001 片段 {index} 已完成，下一片段连续。"),
                "reference_tags": [],
                "audio_bridge": "同一句声音延后切入下一画面，不重新起句。",
                "edit_type": "声音延后切镜",
                "fallback_cut": "保持同机位并转移焦点。",
            }
        )
    return data


def _reference_fixture() -> dict[str, Any]:
    data = _base("TEST-REFERENCE-ACTION")
    data["reference_roles"] = [
        {
            "reference_id": "REF-IDENTITY",
            "exact_tag": "@Image1",
            "media_type": "IMAGE",
            "primary_role": "IDENTITY",
            "controls": ["identity", "wardrobe"],
            "forbidden_transfer": ["motion", "camera"],
            "rights_status": "OWNED",
            "source": "用户提供的原创角色标准图",
        },
        {
            "reference_id": "REF-MOTION",
            "exact_tag": "@Video1",
            "media_type": "VIDEO",
            "primary_role": "MOTION",
            "controls": ["motion rhythm"],
            "forbidden_transfer": ["identity", "wardrobe", "environment", "logo"],
            "rights_status": "LICENSED",
            "source": "已许可的动作参考",
        },
    ]
    data["action_contracts"] = [_action("SH010", ["@Image1", "@Video1"])]
    data["attempt_budgets"] = [
        {
            "shot_id": "SH010",
            "max_attempts": 3,
            "used_attempts": 0,
            "retry_policy": "ONE_VARIABLE",
            "stop_condition": "连续两次出现同一缺陷就停止重抽并修改动作方案。",
            "external_paid": False,
            "user_approved": False,
        }
    ]
    return data


def _resume_fixture() -> dict[str, Any]:
    data = _base("TEST-RESUME")
    data["action_contracts"] = [_action("SH020"), _action("SH021")]
    baton = "人物停在门内侧，右手仍握门把，视线看向走廊。"
    data["shot_handoffs"] = [
        {
            "boundary_id": "BOUND-RESUME",
            "from_shot_id": "SH020",
            "to_shot_id": "SH021",
            "continuity_mode": "SEAMLESS_CONTINUATION",
            "receiver_in": baton,
            "baton_out": baton,
            "planned_end_state": "人物原计划站在门外。",
            "observed_end_state": baton,
            "source_take_status": "ACCEPTED",
            "authoritative_end_state": "OBSERVED_ACCEPTED",
            "anchors": _anchors("本镜无对白，上一句已经说完。"),
            "reference_tags": [],
            "audio_bridge": "走廊空调低鸣连续，门轴余响自然衰减。",
            "edit_type": "连续动作承接",
            "fallback_cut": "切门把手特写后从走廊反打重锚。",
        }
    ]
    data["assets"] = [
        {
            "asset_id": "ASSET-TAKE-020",
            "name": "第二十镜已接受样片",
            "kind": "VIDEO",
            "version": "v1",
            "source_level": "GENERATED_OUTPUT",
            "rights_status": "OWNED",
            "status": "ACCEPTED",
            "use_scope": ["SH021 连续性入口"],
            "file_path": "media/SH020-v1.mp4",
            "sha256": "a" * 64,
            "evidence": ["用户已确认保留该样片。"],
            "updated_at": "2026-08-23T10:00:00+12:00",
        }
    ]
    data["cost_ledger"] = [
        {
            "cost_id": "COST-EST-020",
            "scope": "SH020 三次以内尝试",
            "kind": "ESTIMATE",
            "currency": "CNY",
            "amount": 9.0,
            "basis": "用户提供的平台单次价格乘以三次上限。",
            "evidence": ["用户提供当前单次价格。"],
            "verified_at": "2026-08-23T09:00:00+12:00",
        },
        {
            "cost_id": "COST-ACT-020",
            "scope": "SH020 实际一次生成",
            "kind": "ACTUAL",
            "currency": "CNY",
            "amount": 3.0,
            "basis": "平台账单的一次生成记录。",
            "evidence": ["账单记录编号 BILL-020。"],
            "verified_at": "2026-08-23T10:05:00+12:00",
        },
    ]
    data["attempt_budgets"] = [
        {
            "shot_id": "SH020",
            "max_attempts": 3,
            "used_attempts": 1,
            "retry_policy": "ONE_VARIABLE",
            "stop_condition": "主动作或人物身份失败时才重试，次要色差交给后期。",
            "external_paid": True,
            "user_approved": True,
        }
    ]
    return data


def self_test() -> None:
    fixtures = (_dialogue_fixture(), _reference_fixture(), _resume_fixture())
    for index, fixture in enumerate(fixtures, start=1):
        result = validate(fixture)
        if not result["valid"]:
            raise AssertionError(f"positive fixture {index} failed: {result['errors']}")

    broken_dialogue = _dialogue_fixture()
    broken_dialogue["dialogue_schedule"][0]["fragments"][1]["start_offset"] += 1
    result = validate(broken_dialogue)
    if result["valid"] or not any(error["code"] == "PC_DIALOGUE_CURSOR_GAP" for error in result["errors"]):
        raise AssertionError("dialogue cursor regression was not rejected")

    role_bleed = _reference_fixture()
    role_bleed["reference_roles"][1]["forbidden_transfer"] = ["logo"]
    result = validate(role_bleed)
    if result["valid"] or not any(error["code"] == "PC_REFERENCE_MOTION_BLEED" for error in result["errors"]):
        raise AssertionError("reference-role bleed was not rejected")

    stale_resume = _resume_fixture()
    stale_resume["shot_handoffs"][0]["authoritative_end_state"] = "PLANNED"
    result = validate(stale_resume)
    if result["valid"] or not any(error["code"] == "PC_OBSERVED_STATE_PRIORITY" for error in result["errors"]):
        raise AssertionError("accepted observed state did not override the plan")

    false_actual = _resume_fixture()
    false_actual["cost_ledger"][1]["evidence"] = []
    result = validate(false_actual)
    if result["valid"] or not any(error["code"] == "PC_COST_ACTUAL_NO_EVIDENCE" for error in result["errors"]):
        raise AssertionError("unsupported actual cost was not rejected")

    print("PASS: 3 natural-language production-control scenarios and 4 negative guards")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.input is None:
        parser.error("input is required unless --self-test is used")
    try:
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "valid": False,
            "root_error_count": 1,
            "errors": [
                {
                    "code": "PC_INPUT_READ",
                    "path": "$",
                    "message": str(exc),
                    "repair": "确认制作记录文件存在，并保存为有效的 UTF-8 JSON。",
                }
            ],
            "public_repairs": [
                {
                    "sample": "当前制作记录",
                    "area": "文件读取",
                    "instruction": "确认制作记录文件存在，并保存为有效的 UTF-8 JSON。",
                }
            ],
            "production_validation": PRODUCTION_VALIDATION,
        }
    else:
        payload = validate(data)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if payload["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
