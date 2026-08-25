#!/usr/bin/env python3
"""银幕总控 Alpha.7：中文文案与四重预检。

本脚本只做可复算的发布前预检，不替代平台复核、专业意见、真实媒体 QA，
也不预测播放量或“爆款概率”。内容规范与素材许可是分离阻断门；自然表达与传播
准备度只提供修订信号，不能抵消阻断项。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable


# Windows 的系统代码页可能不是 UTF-8；机器字段保持英文，用户可见说明必须稳定输出中文。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


VERSION = "1.1.3"
STAGES = {"EARLY", "IN_PROCESS", "FINAL"}
UNKNOWN_VALUES = {None, "", "UNKNOWN", "UNVERIFIED", "NOT_CHECKED", "PENDING"}

AI_STYLE_PATTERNS = (
    ("N-OPENING", r"(?:值得注意的是|不可否认的是|毋庸置疑|让我们(?:一起)?(?:来)?|众所周知)", "模板式开场或提示层", 7),
    ("N-SUMMARY", r"(?:综上所述|总而言之|归根结底|总的来说|本质上(?:而言)?|由此可见)", "空泛总结或收尾腔", 7),
    ("N-BINARY", r"不是[^。！？\n]{1,50}(?:而是|更是)", "高频二元对比骨架", 5),
    ("N-JARGON", r"(?:赋能|抓手|闭环|生态矩阵|全链路|底层逻辑|方法论|一站式)", "商业黑话或抽象包装", 6),
    ("N-INFLATION", r"(?:颠覆性|划时代|前所未有|重新定义|引领时代|震撼来袭|史诗级)", "缺少证据的意义拔高", 8),
    ("N-NOMINAL", r"(?:进行了|实现了|完成了|开展了)[^。！？\n]{0,20}(?:优化|提升|赋能|建设|升级)", "名词化动作堆叠", 4),
    ("N-SYCOPHANCY", r"(?:你问到了[^。！？\n]{0,12}(?:核心|本质)|完全不用担心|你走在正确的路上)", "替用户下结论或认证式夸奖", 8),
)

ABSOLUTE_CLAIM_PATTERN = re.compile(
    r"(?:100%|百分之百|绝对(?:不会|安全|有效|成功)|保证(?:成功|有效|收益)|零风险|全网第一|史上最|唯一(?:能够|可以)|必然(?:成功|爆火))",
    re.IGNORECASE,
)
UNSOURCED_AUTHORITY_PATTERN = re.compile(
    r"(?:研究表明|数据显示|专家(?:指出|认为)|业内人士认为|权威(?:机构|来源)(?:指出|表示)|官方说明(?:指出|表示)|studies show|experts say)",
    re.IGNORECASE,
)
FORBIDDEN_PRECISION_PATTERN = re.compile(
    r"(?:爆款概率|爆火概率|黄金时长|最佳发布时间|保证播放量|万能完播率|生死线)",
    re.IGNORECASE,
)
HIGH_RISK_TOPIC_PATTERN = re.compile(
    r"(?:未成年人|医疗诊断|治疗效果|投资回报|保本|仿冒|换脸|克隆声音|个人身份证|银行卡号|自残|危险挑战)",
    re.IGNORECASE,
)

PROTECTED_PATTERNS = (
    ("code", re.compile(r"`[^`\n]+`")),
    ("url", re.compile(r"https?://[^\s)\]}>]+", re.IGNORECASE)),
    ("quote", re.compile(r"[“\"]([^”\"\n]{1,200})[”\"]")),
    (
        "number",
        re.compile(
            r"(?<![\w.])(?:\d{4}-\d{1,2}-\d{1,2}|v?\d+\.\d+(?:\.\d+)?|\d+(?:\.\d+)?%?)"
            r"(?:\s*(?:秒|分钟|小时|天|周|月|年|元|万元|亿元|MB|GB|K|万|亿))?",
            re.IGNORECASE,
        ),
    ),
)

RIGHTS_CLEAR = {"CLEAR", "LICENSED", "USER_CREATED", "PUBLIC_DOMAIN_VERIFIED", "NOT_APPLICABLE"}
RIGHTS_HARD_FAIL = {"MISSING", "EXPIRED", "RESTRICTED", "DENIED", "OUT_OF_SCOPE"}
PERSON_KINDS = {"PORTRAIT", "VOICE", "PERSON_REFERENCE", "FACE", "DIGITAL_HUMAN", "VOICE_CLONE"}
MUSIC_DERIVATIVE_KINDS = {"COVER_MUSIC", "SAMPLED_MUSIC", "ADAPTED_MUSIC"}


def _norm(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    return str(value).strip().upper() or "UNKNOWN"


def _known(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return _norm(value) not in {str(v).upper() for v in UNKNOWN_VALUES}


def _is_true(value: Any) -> bool:
    return value is True or _norm(value) in {"YES", "TRUE", "PASS", "PASSED", "READY", "CLEAR", "ALIGNED", "VERIFIED", "NOT_APPLICABLE"}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _finding(
    finding_id: str,
    module: str,
    severity: str,
    message: str,
    action: str,
    *,
    location: str = "project",
    blocker: bool = False,
    matched: str = "",
    evidence_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "module": module,
        "severity": severity,
        "blocker": blocker,
        "location": location,
        "message_zh": message,
        "matched": matched,
        "required_action_zh": action,
        "evidence_ids": list(evidence_ids or []),
    }


def _extract_spans(text: str) -> list[tuple[str, str]]:
    spans: list[tuple[str, str]] = []
    for span_type, pattern in PROTECTED_PATTERNS:
        for match in pattern.finditer(text or ""):
            value = match.group(0)
            spans.append((span_type, value))
    return spans


def _texts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("texts") or []
    if isinstance(raw, dict):
        raw = [raw]
    result = []
    for index, item in enumerate(raw, 1):
        if isinstance(item, str):
            item = {"text_id": f"TXT-{index:03d}", "kind": "copy", "text": item}
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        normalized.setdefault("text_id", normalized.get("id") or f"TXT-{index:03d}")
        normalized.setdefault("kind", "copy")
        normalized.setdefault("text", "")
        result.append(normalized)
    return result


def audit_natural_expression(payload: dict[str, Any], stage: str) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    penalty_by_family: dict[str, int] = {}
    protected_inventory: dict[str, list[dict[str, str]]] = {}
    fidelity_review_ids: list[str] = []

    for item in _texts(payload):
        text_id = str(item["text_id"])
        text = str(item.get("text") or "")
        inventory = [{"type": t, "value": v} for t, v in _extract_spans(text)]
        protected_inventory[text_id] = inventory

        for family_id, pattern, message, penalty in AI_STYLE_PATTERNS:
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            if not matches:
                continue
            penalty_by_family[family_id] = max(penalty_by_family.get(family_id, 0), penalty)
            first = matches[0].group(0)
            findings.append(
                _finding(
                    f"{family_id}-{text_id}",
                    "natural_expression",
                    "P2",
                    message,
                    "保留事实与语域，只删除姿态层、空总结或无实质作用的包装；不要机械替换同义词。",
                    location=text_id,
                    matched=first,
                )
            )

        original = item.get("original_text")
        if isinstance(original, str):
            original_spans = _extract_spans(original)
            current_values = [value for _, value in _extract_spans(text)]
            missing = [(kind, value) for kind, value in original_spans if value not in current_values]
            for idx, (kind, value) in enumerate(missing, 1):
                must_preserve = bool(item.get("must_preserve"))
                finding_id = f"N-FIDELITY-{text_id}-{idx:02d}"
                fidelity_review_ids.append(finding_id)
                findings.append(
                    _finding(
                        finding_id,
                        "natural_expression",
                        "P0" if must_preserve else "P1",
                        f"润色后缺少受保护片段（{kind}）：{value}",
                        "核对数字、日期、引用、专名、命令及其归属；确认是有意删除还是发生事实漂移。",
                        location=text_id,
                        blocker=must_preserve and stage == "FINAL",
                        matched=value,
                    )
                )

    score = max(0, 100 - sum(penalty_by_family.values()))
    status = "REVIEW" if findings else "PASS"
    return {
        "status": status,
        "expression_score": score,
        "score_method": "HEURISTIC_STYLE_SIGNAL_V1",
        "score_notice_zh": "该分数是可解释的模板腔信号，不是作者身份判断，也不是 AI 生成概率。",
        "protected_spans": protected_inventory,
        "fidelity_review_ids": fidelity_review_ids,
        "findings": findings,
    }


def audit_compliance(
    payload: dict[str, Any],
    stage: str,
    natural_result: dict[str, Any],
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    project = payload.get("project") or {}
    distribution = payload.get("distribution") or {}

    for item in _texts(payload):
        text_id = str(item["text_id"])
        text = str(item.get("text") or "")
        evidence_ids = _as_list(item.get("source_ids") or item.get("evidence_ids"))
        for pattern_id, pattern, message, action in (
            ("C-ABSOLUTE", ABSOLUTE_CLAIM_PATTERN, "出现绝对化、保证性或零风险表达。", "删除保证性措辞；如必须保留结论，补充当前、可核验且适用的证据和限定条件。"),
            ("C-FORBIDDEN-PRECISION", FORBIDDEN_PRECISION_PATTERN, "出现未经证据支持的传播精确结论。", "改成待测试假设或传播准备度说明；不得写成爆款概率、黄金时长或最佳发布时间。"),
            ("C-HIGH-RISK-TOPIC", HIGH_RISK_TOPIC_PATTERN, "命中需要额外语义复核的内容。", "按目标范围、平台和具体语境做人工/专业复核；关键词命中本身不等于违规。"),
        ):
            match = pattern.search(text)
            if match:
                findings.append(
                    _finding(
                        f"{pattern_id}-{text_id}",
                        "compliance",
                        "P1",
                        message,
                        action,
                        location=text_id,
                        matched=match.group(0),
                        evidence_ids=evidence_ids,
                    )
                )
        authority = UNSOURCED_AUTHORITY_PATTERN.search(text)
        if authority and not evidence_ids:
            findings.append(
                _finding(
                    f"C-UNSOURCED-{text_id}",
                    "compliance",
                    "P1",
                    "使用了权威或数据引述，但当前文本没有关联来源。",
                    "补充可访问来源与归属；无法补充时删除依赖该来源才能成立的论断，不得编造来源主体、年份或数据。",
                    location=text_id,
                    matched=authority.group(0),
                )
            )

    for claim in _as_list(payload.get("claims")):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or claim.get("id") or "CLAIM-UNKNOWN")
        classification = _norm(claim.get("classification"))
        source_ids = _as_list(claim.get("source_ids") or claim.get("evidence_ids"))
        text = str(claim.get("text") or "")
        if classification in {"FACT", "VERIFIED", "VERIFIED_OFFICIAL"} and not source_ids:
            findings.append(
                _finding(
                    f"C-CLAIM-SOURCE-{claim_id}",
                    "compliance",
                    "P1",
                    "事实或已验证主张缺少来源回链。",
                    "补充来源 ID、发布者、日期与适用范围；否则将分类降为 UNKNOWN、HEURISTIC 或 SYSTEM_INFERENCE。",
                    location=claim_id,
                    matched=text[:120],
                )
            )
        if FORBIDDEN_PRECISION_PATTERN.search(text):
            findings.append(
                _finding(
                    f"C-CLAIM-PRECISION-{claim_id}",
                    "compliance",
                    "P1",
                    "主张把传播经验包装成精确成功结论。",
                    "删除精确成功承诺，保留证据、样本和推断边界。",
                    location=claim_id,
                    matched=text[:120],
                )
            )

    for finding_id in natural_result.get("fidelity_review_ids", []):
        natural_finding = next(
            (f for f in natural_result.get("findings", []) if f.get("finding_id") == finding_id),
            None,
        )
        if natural_finding and natural_finding.get("blocker"):
            findings.append(
                _finding(
                    f"C-{finding_id}",
                    "compliance",
                    "P0",
                    "受保护事实或引用在要求保真的润色中发生漂移。",
                    "恢复受保护片段及其主体—动作、数字—对象和引用—归属关系，再重新预检。",
                    location=natural_finding.get("location", "text"),
                    blocker=True,
                    matched=natural_finding.get("matched", ""),
                )
            )

    if stage == "FINAL":
        ai_used = _norm(project.get("aigc_used"))
        label_plan = _norm(project.get("aigc_label_plan"))
        if ai_used in {"YES", "TRUE", "PARTIAL"} and label_plan not in {"READY", "VERIFIED", "NOT_APPLICABLE"}:
            findings.append(
                _finding(
                    "C-FINAL-AIGC-LABEL",
                    "compliance",
                    "P0",
                    "项目使用了 AI 生成内容，但显式/隐式标识执行计划未就绪。",
                    "按目标地区和平台的当前规则完成标识计划，并保留执行证据。",
                    blocker=True,
                )
            )

        if not _is_true(project.get("real_final_media")):
            findings.append(
                _finding(
                    "C-FINAL-MEDIA",
                    "compliance",
                    "P0",
                    "缺少可访问的真实最终媒体版本。",
                    "绑定真实成片 artifact_id + version；模拟媒体、文字计划或提示词不能替代。",
                    blocker=True,
                )
            )
        if not _is_true(project.get("media_observed")):
            findings.append(
                _finding(
                    "C-FINAL-OBSERVATION",
                    "compliance",
                    "P0",
                    "最终媒体尚未经过真实观察。",
                    "对同一精确成片版本执行画面、声音、字幕和因果边界检查并记录观察证据。",
                    blocker=True,
                )
            )

        targets = _as_list(project.get("target_platforms") or distribution.get("target_platforms"))
        rule_evidence = _as_list(project.get("current_rule_evidence_ids"))
        if targets and not rule_evidence:
            findings.append(
                _finding(
                    "C-FINAL-CURRENT-RULES",
                    "compliance",
                    "P0",
                    "目标平台已有定义，但没有当前规则证据。",
                    "核查目标入口的当前官方规则，记录发布者、发布日期/生效日期、核查日期和适用范围。",
                    blocker=True,
                )
            )

        checks = (
            ("title_matches_content", "标题与成片承诺一致"),
            ("cover_matches_content", "封面与成片内容一致"),
            ("subtitle_matches_final", "字幕对应最终成片版本"),
            ("format_checked", "目标格式已经核验"),
        )
        for key, label in checks:
            value = distribution.get(key)
            if _is_true(value):
                continue
            if value is False or _norm(value) in {"NO", "FALSE", "FAILED", "MISMATCH"}:
                findings.append(
                    _finding(
                        f"C-FINAL-{key.upper()}",
                        "compliance",
                        "P0",
                        f"{label}：未通过。",
                        "修正对应成品并重新绑定最终版本。",
                        blocker=True,
                    )
                )
            else:
                findings.append(
                    _finding(
                        f"C-FINAL-{key.upper()}",
                        "compliance",
                        "P1",
                        f"{label}：尚未确认。",
                        "在最终发布包上完成检查并记录结果。",
                    )
                )

    blockers = [f for f in findings if f["blocker"]]
    status = "BLOCK" if blockers else ("REVIEW" if findings else "PASS")
    return {
        "status": status,
        "blocker_count": len(blockers),
        "notice_zh": "这是发布前自查，不能替代平台复核或专业意见。关键词命中必须结合语境判断。",
        "findings": findings,
    }


def audit_rights(payload: dict[str, Any], stage: str, evaluation_date: date) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    project = payload.get("project") or {}
    assets = [a for a in _as_list(payload.get("assets")) if isinstance(a, dict)]
    target_platforms = {str(x) for x in _as_list(project.get("target_platforms"))}
    target_regions = {str(x) for x in _as_list(project.get("target_regions"))}
    commercial = _is_true(project.get("commercial_use"))

    if stage == "FINAL" and not assets:
        findings.append(
            _finding(
                "R-FINAL-NO-ASSET-LEDGER",
                "rights",
                "P0",
                "最终发布包没有资产与来源台账。",
                "登记实际使用的图像、视频、音乐、音效、字体、肖像、声音、参考素材和生成平台凭证。",
                blocker=True,
            )
        )

    for index, asset in enumerate(assets, 1):
        asset_id = str(asset.get("asset_id") or asset.get("id") or f"ASSET-{index:03d}")
        if asset.get("used_in_final") is False:
            continue
        kind = _norm(asset.get("kind"))
        status = _norm(asset.get("license_status") or asset.get("rights_status"))
        source = asset.get("source") or asset.get("source_url") or asset.get("created_by")
        evidence_ids = _as_list(asset.get("license_evidence_ids") or asset.get("evidence_ids"))

        def add(rule: str, severity: str, message: str, action: str, *, hard: bool = False) -> None:
            findings.append(
                _finding(
                    f"{rule}-{asset_id}",
                    "rights",
                    severity,
                    message,
                    action,
                    location=asset_id,
                    blocker=hard and stage == "FINAL",
                    evidence_ids=[str(x) for x in evidence_ids],
                )
            )

        if not _known(source):
            add("R-SOURCE", "P0" if stage == "FINAL" else "P1", "资产缺少来源或创作主体记录。", "补充来源 URL/文件、作者或生成平台、取得日期和项目内版本。", hard=True)

        if status in RIGHTS_HARD_FAIL:
            add("R-LICENSE", "P0", f"素材许可状态为 {status}。", "替换资产或取得覆盖本次用途、地区、平台和期限的授权。", hard=True)
        elif status not in RIGHTS_CLEAR:
            add("R-LICENSE", "P0" if stage == "FINAL" else "P1", "素材许可状态尚未明确。", "确认许可方、用途、平台、地区、期限、署名与再分发范围并登记凭证。", hard=True)

        if status in {"CLEAR", "LICENSED", "PUBLIC_DOMAIN_VERIFIED"} and not evidence_ids:
            add("R-EVIDENCE", "P0" if stage == "FINAL" else "P1", "资产声称许可已齐备，但没有凭证回链。", "登记合同、订单、许可证、下载记录、条款快照或生成任务凭证。", hard=True)

        if kind in PERSON_KINDS:
            consent = _norm(asset.get("person_consent_status") or asset.get("consent_status"))
            if consent not in {"CLEAR", "VERIFIED", "NOT_REQUIRED"}:
                add("R-CONSENT", "P0", "涉及可识别人物、声音或数字人，但同意/授权状态未清。", "取得并登记肖像、声音、表演或克隆使用所需授权；无法取得时替换。", hard=True)

        if _is_true(asset.get("ai_generated")):
            provider_terms = _norm(asset.get("ai_provider_terms_status"))
            if provider_terms not in {"CLEAR", "VERIFIED", "NOT_APPLICABLE"}:
                add("R-AI-TERMS", "P0" if stage == "FINAL" else "P1", "AI 生成资产的商用、再分发或归属条款未确认。", "核对生成时适用的账号套餐与条款版本，保留任务、订单和条款证据。", hard=True)

        if _is_true(asset.get("attribution_required")) and not _known(asset.get("attribution_plan")):
            add("R-ATTRIBUTION", "P0" if stage == "FINAL" else "P1", "资产要求署名，但没有可执行署名计划。", "按许可证要求在片尾、简介或指定位置使用准确署名。", hard=True)

        allowed_platforms = {str(x) for x in _as_list(asset.get("allowed_platforms") or asset.get("scope_platforms"))}
        if target_platforms and allowed_platforms and not target_platforms.issubset(allowed_platforms):
            missing = sorted(target_platforms - allowed_platforms)
            add("R-PLATFORM-SCOPE", "P0", f"授权未覆盖目标平台：{', '.join(missing)}。", "扩展授权范围或从这些平台的发布包移除该资产。", hard=True)

        allowed_regions = {str(x) for x in _as_list(asset.get("allowed_regions") or asset.get("scope_regions"))}
        if target_regions and allowed_regions and not target_regions.issubset(allowed_regions):
            missing = sorted(target_regions - allowed_regions)
            add("R-REGION-SCOPE", "P0", f"授权未覆盖目标地区：{', '.join(missing)}。", "扩展地域授权或调整发行范围。", hard=True)

        if commercial and _norm(asset.get("commercial_use_allowed")) in {"NO", "FALSE", "NONCOMMERCIAL", "NC"}:
            add("R-COMMERCIAL-SCOPE", "P0", "项目为商业用途，但资产授权不允许商业使用。", "取得商用授权或替换资产。", hard=True)

        term_end = asset.get("term_end")
        if _known(term_end):
            try:
                if date.fromisoformat(str(term_end)) < evaluation_date:
                    add("R-TERM", "P0", "资产授权已经到期。", "续签至覆盖计划发行与持续传播期，或替换资产。", hard=True)
            except ValueError:
                add("R-TERM-FORMAT", "P1", "授权结束日期无法解析。", "使用 YYYY-MM-DD 并人工核对原始凭证。")

        if kind in MUSIC_DERIVATIVE_KINDS:
            work_clear = _is_true(asset.get("musical_work_cleared"))
            recording_clear = _is_true(asset.get("sound_recording_cleared"))
            if not (work_clear and recording_clear):
                add("R-MUSIC-DUAL", "P0", "翻唱、改编或采样资产的词曲/录音许可链未同时齐备。", "分别核对作品版权许可与录音制品许可；缺一项都不能进入最终发布包。", hard=True)

    blockers = [f for f in findings if f["blocker"]]
    status = "BLOCK" if blockers else ("REVIEW" if findings else "CLEAR")
    return {
        "status": status,
        "blocker_count": len(blockers),
        "notice_zh": "素材许可结论只表示项目台账的完整性与范围一致性，不验证凭证真伪，也不替代专业复核。",
        "findings": findings,
    }


def audit_propagation(payload: dict[str, Any], stage: str) -> dict[str, Any]:
    project = payload.get("project") or {}
    attention = payload.get("attention") or {}
    distribution = payload.get("distribution") or {}

    def prefer(mapping: dict[str, Any], key: str, fallback: Any) -> Any:
        """保留显式 False；不得让相邻建议覆盖已经失败的检查。"""
        return mapping[key] if key in mapping else fallback

    dimensions = {
        "audience": prefer(attention, "audience_defined", project.get("audience")),
        "promise": attention.get("core_promise"),
        "opening_hook": attention.get("opening_hook"),
        "payoff": attention.get("payoff"),
        "continuation_reason": attention.get("continuation_reason"),
        "evidence_support": prefer(attention, "proof_points", attention.get("evidence_plan")),
        "platform_fit": prefer(attention, "platform_fit", project.get("target_platforms")),
        "title_alignment": prefer(distribution, "title_matches_content", attention.get("title_content_alignment")),
        "cover_alignment": prefer(distribution, "cover_matches_content", attention.get("cover_content_alignment")),
        "format_fit": prefer(distribution, "format_checked", attention.get("format_fit")),
    }
    required_by_stage = {
        "EARLY": ("audience", "promise", "opening_hook", "payoff", "continuation_reason", "evidence_support"),
        "IN_PROCESS": ("audience", "promise", "opening_hook", "payoff", "continuation_reason", "evidence_support", "platform_fit", "title_alignment"),
        "FINAL": tuple(dimensions.keys()),
    }
    required = required_by_stage[stage]
    passed = [key for key in required if _known(dimensions[key]) and dimensions[key] is not False]
    missing = [key for key in required if key not in passed]
    score = round(len(passed) / len(required) * 100) if required else 0
    findings = [
        _finding(
            f"P-MISSING-{key.upper()}",
            "propagation_readiness",
            "P2",
            f"传播准备项尚未形成：{key}。",
            "补充与当前阶段相称的受众、承诺、钩子、兑现或包装依据；先保持为 PROPOSED。",
            location=key,
        )
        for key in missing
    ]
    return {
        "status": "READY" if not missing else "REVIEW",
        "readiness_score": score,
        "score_method": "REQUIRED_FIELD_COVERAGE_BY_STAGE_V1",
        "required_dimensions": list(required),
        "present_dimensions": passed,
        "missing_dimensions": missing,
        "score_notice_zh": "该分数只表示本阶段传播设计的结构覆盖度，不是爆款概率、播放量预测或平台推荐保证。",
        "findings": findings,
    }


def build_state_record(
    payload: dict[str, Any], result: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    """把单独预检报告转换为可写回 project_state 的严格记录。

    未提供 ``state_binding`` 时只返回人读报告。提供后，所有产物版本、哈希、
    证据和阻断项都必须由项目账本显式传入；本脚本不伪造这些关联。
    """

    binding = payload.get("state_binding")
    if binding is None:
        return None, []
    if not isinstance(binding, dict):
        return None, ["state_binding 必须是对象"]

    errors: list[str] = []

    def unique_strings(value: Any) -> list[str]:
        return list(dict.fromkeys(str(item) for item in _as_list(value)))
    preflight_id = str(binding.get("preflight_id") or "")
    if not re.fullmatch(r"PF-.+", preflight_id):
        errors.append("state_binding.preflight_id 必须以 PF- 开头")

    artifact_refs = binding.get("artifact_refs")
    if not isinstance(artifact_refs, list) or not artifact_refs:
        errors.append("state_binding.artifact_refs 至少需要一项")
        artifact_refs = []
    else:
        for index, reference in enumerate(artifact_refs):
            if not isinstance(reference, dict):
                errors.append(f"artifact_refs[{index}] 必须是对象")
                continue
            if not _known(reference.get("artifact_id")) or not _known(reference.get("version")):
                errors.append(f"artifact_refs[{index}] 缺少 artifact_id/version")
            digest = reference.get("sha256")
            if result["stage"] == "FINAL" and not re.fullmatch(r"[A-Fa-f0-9]{64}", str(digest or "")):
                errors.append(f"FINAL artifact_refs[{index}] 必须绑定 64 位 SHA-256")

    execution_mode = _norm(binding.get("execution_mode") or "REAL")
    if execution_mode not in {"REAL", "SIMULATION"}:
        errors.append("state_binding.execution_mode 只能是 REAL 或 SIMULATION")
    if result["stage"] == "FINAL" and execution_mode != "REAL":
        errors.append("FINAL 状态记录只能绑定 REAL 执行")

    check_evidence = binding.get("check_evidence_ids")
    check_blockers = binding.get("blocking_issue_ids")
    if not isinstance(check_evidence, dict):
        check_evidence = {}
    if not isinstance(check_blockers, dict):
        check_blockers = {}

    report_keys = {
        "naturalness": "natural_expression",
        "compliance": "compliance",
        "rights": "rights",
        "propagation": "propagation_readiness",
    }
    status_map = {
        "PASS": "PASS",
        "CLEAR": "PASS",
        "READY": "PASS",
        "REVIEW": "REWORK",
        "BLOCK": "BLOCKED",
    }
    checks: dict[str, Any] = {}
    for state_key, report_key in report_keys.items():
        report = result[report_key]
        status = status_map.get(str(report.get("status")), "NOT_EVALUATED")
        evidence_ids = unique_strings(check_evidence.get(state_key))
        blocker_ids = unique_strings(check_blockers.get(state_key))
        if status == "BLOCKED" and not blocker_ids:
            errors.append(f"{state_key} 为 BLOCKED 时必须提供项目 blocking_issue_ids")

        score: int | None = None
        score_basis = "NOT_SCORED"
        rubric_version: str | None = None
        if state_key == "naturalness":
            score = int(report["expression_score"])
            score_basis = "HEURISTIC"
            rubric_version = str(report["score_method"])
        elif state_key == "propagation":
            score = int(report["readiness_score"])
            score_basis = "RUBRIC"
            rubric_version = str(report["score_method"])

        findings = [
            f"{finding.get('finding_id')}: {finding.get('message_zh')}"
            for finding in _as_list(report.get("findings"))
            if isinstance(finding, dict)
        ]
        checks[state_key] = {
            "status": status,
            "score": score,
            "score_basis": score_basis,
            "rubric_version": rubric_version,
            "findings": findings,
            "evidence_ids": evidence_ids,
            "blocking_issue_ids": blocker_ids,
        }

    overall_status = str(result["overall_status"])
    if overall_status == "READY_FOR_RELEASE_READINESS_GATE":
        overall_outcome = "PASS"
    elif overall_status.startswith("BLOCKED_BY_"):
        overall_outcome = "BLOCKED"
    else:
        overall_outcome = "REWORK"

    if result["stage"] == "FINAL" and overall_outcome == "PASS":
        for name in ("compliance", "rights"):
            if not checks[name]["evidence_ids"]:
                errors.append(f"FINAL PASS 的 {name} 必须绑定项目 evidence_ids")

    global_evidence = unique_strings(binding.get("evidence_ids"))
    checker = str(binding.get("checker") or "")
    if not checker:
        errors.append("state_binding.checker 不能为空")

    if errors:
        return None, errors

    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    record = {
        "preflight_id": preflight_id,
        "checkpoint": result["stage"],
        "artifact_refs": artifact_refs,
        "target_markets": unique_strings(
            binding.get("target_markets") or project.get("target_regions")
        ),
        "target_channels": unique_strings(
            binding.get("target_channels") or project.get("target_platforms")
        ),
        "checks": checks,
        "overall_outcome": overall_outcome,
        "propagation_claim_boundary": "READINESS_NOT_OUTCOME_PROBABILITY",
        "execution_mode": execution_mode,
        "checked_at": result["evaluation_date"],
        "checker": checker,
        "evidence_ids": global_evidence,
        "analysis_limitations": unique_strings([
            "自然表达分不是作者身份或 AI 生成概率判断。",
            "内容规范预检不能替代平台复核或专业意见。",
            "素材许可预检不验证凭证真伪。",
            "传播分只表示结构覆盖，不预测播放结果。",
            *[str(value) for value in _as_list(binding.get("analysis_limitations"))],
        ]),
    }
    return record, []


def evaluate(payload: dict[str, Any], stage_override: str | None = None) -> dict[str, Any]:
    project = payload.get("project") or {}
    stage = _norm(stage_override or payload.get("stage") or project.get("stage"))
    if stage not in STAGES:
        raise ValueError("stage 必须是 EARLY、IN_PROCESS 或 FINAL")

    evaluation_date_source = "RUNTIME_DATE"
    evaluation_date = date.today()
    configured_date = project.get("release_date") or project.get("checked_at")
    if _known(configured_date):
        try:
            evaluation_date = date.fromisoformat(str(configured_date))
            evaluation_date_source = "PROJECT_RELEASE_DATE" if project.get("release_date") else "PROJECT_CHECKED_AT"
        except ValueError as exc:
            raise ValueError("project.release_date / checked_at 必须使用 YYYY-MM-DD") from exc

    natural = audit_natural_expression(payload, stage)
    compliance = audit_compliance(payload, stage, natural)
    rights = audit_rights(payload, stage, evaluation_date)
    propagation = audit_propagation(payload, stage)

    if compliance["status"] == "BLOCK" and rights["status"] == "BLOCK":
        overall = "BLOCKED_BY_COMPLIANCE_AND_RIGHTS"
    elif compliance["status"] == "BLOCK":
        overall = "BLOCKED_BY_COMPLIANCE"
    elif rights["status"] == "BLOCK":
        overall = "BLOCKED_BY_RIGHTS"
    elif stage == "FINAL" and (
        compliance["status"] == "REVIEW"
        or rights["status"] == "REVIEW"
        or natural["status"] == "REVIEW"
        or propagation["status"] == "REVIEW"
    ):
        overall = "REVIEW_REQUIRED"
    elif stage == "FINAL":
        overall = "READY_FOR_RELEASE_READINESS_GATE"
    else:
        overall = "CONTINUE_WITH_NOTES"

    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result = {
        "engine": "SILVER_SHOWRUNNER_FOURFOLD_PREFLIGHT",
        "engine_version": VERSION,
        "stage": stage,
        "evaluation_date": evaluation_date.isoformat(),
        "evaluation_date_source": evaluation_date_source,
        "input_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "overall_status": overall,
        "gate_rule_zh": "内容规范与素材许可是分离阻断门；自然表达分和传播准备度不能抵消任何阻断项。",
        "release_state_notice_zh": "READY_FOR_RELEASE_READINESS_GATE 只表示可进入现有发布准备关卡，不等于 RELEASE_READY，更不等于已经发布。",
        "natural_expression": natural,
        "compliance": compliance,
        "rights": rights,
        "propagation_readiness": propagation,
    }
    state_record, state_record_errors = build_state_record(payload, result)
    result["state_record_status"] = (
        "NOT_REQUESTED" if payload.get("state_binding") is None
        else ("READY" if state_record is not None else "BLOCKED")
    )
    result["state_record_errors"] = state_record_errors
    result["state_record"] = state_record
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 银幕总控 Alpha.7｜中文文案与四重预检",
        "",
        f"- 阶段：`{result['stage']}`",
        f"- 总体状态：`{result['overall_status']}`",
        f"- 核查日期：`{result['evaluation_date']}`（`{result['evaluation_date_source']}`）",
        f"- 输入 SHA-256：`{result['input_sha256']}`",
        "- 规则：内容规范与素材许可是分离阻断门；自然表达和传播准备度不能抵消阻断。",
        "",
        "| 模块 | 状态 | 结果 |",
        "|---|---|---|",
        f"| 自然表达 | {result['natural_expression']['status']} | {result['natural_expression']['expression_score']}/100（风格信号） |",
        f"| 内容规范 | {result['compliance']['status']} | 阻断项 {result['compliance']['blocker_count']} |",
        f"| 素材许可与来源 | {result['rights']['status']} | 阻断项 {result['rights']['blocker_count']} |",
        f"| 传播准备度 | {result['propagation_readiness']['status']} | {result['propagation_readiness']['readiness_score']}/100（结构覆盖） |",
        "",
    ]
    labels = {
        "natural_expression": "自然表达",
        "compliance": "内容规范",
        "rights": "素材许可与来源",
        "propagation_readiness": "传播准备度",
    }
    for key, label in labels.items():
        lines.extend([f"## {label}", ""])
        findings = result[key].get("findings", [])
        if not findings:
            lines.extend(["- 本轮零命中；零命中不代表平台要求、适用规则或传播结果已经验证。", ""])
            continue
        for finding in findings:
            block = "｜阻断" if finding.get("blocker") else ""
            lines.append(
                f"- `{finding['finding_id']}` [{finding['severity']}{block}] "
                f"{finding['message_zh']} 处理：{finding['required_action_zh']}"
            )
        lines.append("")
    lines.extend(
        [
            "> 本报告是项目内预检，不是 AI 检测器结论、平台复核结论、专业意见或播放量预测。",
            "",
        ]
    )
    return "\n".join(lines)


def _clean_final_payload() -> dict[str, Any]:
    return {
        "project": {
            "project_id": "P-TEST",
            "stage": "FINAL",
            "audience": "青年科普受众",
            "target_platforms": ["比赛提交页"],
            "target_regions": ["目标地区"],
            "aigc_used": True,
            "aigc_label_plan": "READY",
            "real_final_media": True,
            "media_observed": True,
            "current_rule_evidence_ids": ["EV-RULE-001"],
            "checked_at": "2026-08-14",
            "commercial_use": False,
        },
        "texts": [{"text_id": "TXT-001", "kind": "title", "text": "一块石头如何记录两亿年的海洋变化"}],
        "assets": [
            {
                "asset_id": "A-001",
                "kind": "IMAGE",
                "source": "用户原创",
                "license_status": "USER_CREATED",
                "ai_generated": False,
            }
        ],
        "distribution": {
            "title_matches_content": True,
            "cover_matches_content": True,
            "subtitle_matches_final": True,
            "format_checked": True,
        },
        "attention": {
            "audience_defined": True,
            "core_promise": "解释岩芯中的时间证据",
            "opening_hook": "同一块石头里为什么有两种海洋？",
            "payoff": "展示证据链",
            "continuation_reason": "逐层揭示年代",
            "proof_points": ["EV-SCI-001"],
            "platform_fit": True,
            "title_content_alignment": True,
            "cover_content_alignment": True,
            "format_fit": True,
        },
        "state_binding": {
            "preflight_id": "PF-TEST-001",
            "artifact_refs": [
                {
                    "artifact_id": "ART-FINAL-001",
                    "version": "v1",
                    "sha256": "a" * 64,
                }
            ],
            "target_markets": ["目标地区"],
            "target_channels": ["比赛提交页"],
            "execution_mode": "REAL",
            "checker": "fourfold_preflight.py",
            "evidence_ids": ["E-PREFLIGHT-001"],
            "check_evidence_ids": {
                "naturalness": [],
                "compliance": ["E-RULE-001"],
                "rights": ["E-RIGHTS-001"],
                "propagation": [],
            },
            "blocking_issue_ids": {},
        },
    }


def self_test() -> None:
    clean = evaluate(_clean_final_payload())
    assert clean["overall_status"] == "READY_FOR_RELEASE_READINESS_GATE", clean
    assert clean["propagation_readiness"]["readiness_score"] == 100
    assert clean["state_record_status"] == "READY", clean
    assert clean["state_record"]["overall_outcome"] == "PASS", clean

    compliance_bad = _clean_final_payload()
    compliance_bad["project"]["aigc_label_plan"] = "MISSING"
    result = evaluate(compliance_bad)
    assert result["overall_status"] == "BLOCKED_BY_COMPLIANCE", result

    rights_bad = _clean_final_payload()
    rights_bad["assets"][0]["license_status"] = "MISSING"
    result = evaluate(rights_bad)
    assert result["overall_status"] == "BLOCKED_BY_RIGHTS", result
    assert result["propagation_readiness"]["readiness_score"] == 100

    both_bad = _clean_final_payload()
    both_bad["project"]["real_final_media"] = False
    both_bad["assets"][0]["license_status"] = "EXPIRED"
    result = evaluate(both_bad)
    assert result["overall_status"] == "BLOCKED_BY_COMPLIANCE_AND_RIGHTS", result

    fidelity_bad = _clean_final_payload()
    fidelity_bad["texts"] = [
        {
            "text_id": "TXT-LOCKED",
            "kind": "description",
            "original_text": "实验在 2026-08-14 完成，误差为 0.3%。",
            "text": "实验已经完成，误差很低。",
            "must_preserve": True,
        }
    ]
    result = evaluate(fidelity_bad)
    assert result["overall_status"] == "BLOCKED_BY_COMPLIANCE", result

    early = {
        "stage": "EARLY",
        "texts": ["值得注意的是，这是一个关于古城修复的短片。"],
        "attention": {"audience_defined": True, "core_promise": "看懂修复过程"},
    }
    result = evaluate(early)
    assert result["overall_status"] == "CONTINUE_WITH_NOTES", result
    assert result["natural_expression"]["expression_score"] < 100

    precision_bad = _clean_final_payload()
    precision_bad["texts"][0]["text"] = "本片爆款概率 90%，保证播放量。"
    result = evaluate(precision_bad)
    ids = {f["finding_id"] for f in result["compliance"]["findings"]}
    assert any(fid.startswith("C-FORBIDDEN-PRECISION") for fid in ids), ids
    assert result["overall_status"] == "REVIEW_REQUIRED", result

    explicit_failure = _clean_final_payload()
    explicit_failure["distribution"]["title_matches_content"] = False
    explicit_failure["attention"]["title_content_alignment"] = True
    result = evaluate(explicit_failure)
    assert result["overall_status"] == "BLOCKED_BY_COMPLIANCE", result
    assert "title_alignment" in result["propagation_readiness"]["missing_dimensions"], result

    blocked_binding = _clean_final_payload()
    blocked_binding["project"]["aigc_label_plan"] = "MISSING"
    blocked_binding["state_binding"]["blocking_issue_ids"] = {}
    result = evaluate(blocked_binding)
    assert result["state_record_status"] == "BLOCKED", result
    assert result["state_record"] is None, result

    print("SELF_TEST_PASS: 9 scenarios")


def load_payload(path: str | None) -> dict[str, Any]:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if sys.stdin.isatty():
        raise ValueError("请使用 --input 指定 JSON 文件，或通过 stdin 传入 JSON。")
    raw = sys.stdin.buffer.read()
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return json.loads(raw.decode(encoding))
        except (UnicodeError, json.JSONDecodeError) as exc:
            last_error = exc
    raise ValueError(f"无法识别 stdin JSON 编码：{last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="银幕总控 Alpha.7 中文文案与四重预检")
    parser.add_argument("--input", help="输入 JSON；省略时从 stdin 读取")
    parser.add_argument("--stage", choices=sorted(STAGES), help="覆盖输入中的阶段")
    parser.add_argument("--out", help="写出 JSON 结果；省略时打印到 stdout")
    parser.add_argument("--report", help="另写中文 Markdown 报告")
    parser.add_argument("--self-test", action="store_true", help="运行内置回归测试")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    try:
        payload = load_payload(args.input)
        result = evaluate(payload, args.stage)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    if args.report:
        Path(args.report).write_text(render_markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
