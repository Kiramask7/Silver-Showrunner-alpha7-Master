#!/usr/bin/env python3
"""Validate the Alpha.7 longform compilation and resume contract.

This validator deliberately covers the integration slice only. It does not
inspect or grade generated media and can never unlock Production Validation.
It uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import math
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

from performance_feasibility_guard import analyze_prompt as analyze_performance_feasibility


CONTRACT_VERSION = "alpha7-longform-1.5"
V14_CONTRACT_VERSION = "alpha7-longform-1.4"
R9_CONTRACT_VERSION = "alpha7-longform-1.3"
R8_CONTRACT_VERSION = "alpha7-longform-1.2"
R7_CONTRACT_VERSION = "alpha7-longform-1.1"
LEGACY_CONTRACT_VERSION = "alpha7-longform-1.0"
READ_ONLY_CONTRACT_VERSIONS = {
    LEGACY_CONTRACT_VERSION, R7_CONTRACT_VERSION, R8_CONTRACT_VERSION,
    R9_CONTRACT_VERSION, V14_CONTRACT_VERSION,
}
ACCEPTED_CONTRACT_VERSIONS = READ_ONLY_CONTRACT_VERSIONS | {CONTRACT_VERSION}
LOCKED_SCAFFOLD_CONTRACT_VERSIONS = {V14_CONTRACT_VERSION, CONTRACT_VERSION}
DIRECTOR_SCAFFOLD_VERSION = "alpha7-director-scaffold-1.1"
V14_DIRECTOR_SCAFFOLD_VERSION = "alpha7-director-scaffold-1.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UNIT_ID_RE = re.compile(r"^U\d{3,}$")
BATCH_ID_RE = re.compile(r"^B\d{3,}$")
INTERNAL_ID_RE = re.compile(
    r"(?i)(?:\b(?:SRC\d{4,}|U\d{3,}|SC\d{3,}|SQ\d{3,}|B\d{3,})\b|"
    r"\b(?:checkpoint_id|source_refs|handoff_out|batch_id|unit_id)\b)"
)
UNIT_HANDOFF_FORBIDDEN_KEYS = {
    "batch_id",
    "checkpoint_id",
    "next_batch_id",
    "resume_instruction",
    "portable_checkpoint",
    "checkpoint_sha256",
}
UNIT_HANDOFF_FORBIDDEN_TEXT = re.compile(
    r"(?i)(?:\bB\d{3,}\b|checkpoint|portable\s+resume|resume_instruction|续接下一批|检查点)"
)
TERMINAL_PUNCTUATION = ("。", "！", "？", ".", "!", "?", "；", ";")
MODE_ALIASES = {
    "FULL_PROJECT": "FULL_EXPORT",
    "FULL_EXPORT": "FULL_EXPORT",
    "ONEFILE_SAFE_BATCH": "ONEFILE_SAFE_BATCH",
    "SAFE_BATCH": "ONEFILE_SAFE_BATCH",
    "CHAT_BATCH": "ONEFILE_SAFE_BATCH",
}
DELIVERY_MODES = {"TEXT_ONLY_ECO_TEST", "MEDIA_ENABLED"}
TEXT_PROJECT_STATUSES = {
    "GLOBAL_READY",
    "PILOT_REWORK_REQUIRED",
    "TEXT_PILOT_COMPLETE",
    "TEXT_SPEC_COMPLETE",
}
MEDIA_PROJECT_STATUSES = {"GLOBAL_READY", "IN_PROGRESS", "COMPLETE"}
TEXT_STOP_CONDITIONS = [
    "SOURCE_AMBIGUITY_AFFECTS_MEANING",
    "P0_BLOCKER",
    "CONTEXT_INSUFFICIENT",
]
TEXT_SKIPPED_STAGES = ["IMAGE", "VIDEO", "AUDIO", "EDIT"]
LEGACY_TEXT_STATUS_AXES = {
    "excluded_step_status": "EXCLUDED_BY_USER",
    "execution_status": "NOT_EXECUTED",
    "observation_status": "NOT_EXECUTED",
    "media_qa_status": "QA_NOT_EXECUTED",
    "production_validation": "NOT_TESTED",
    "ncs_status": "NOT_SCORED",
    "nrs_status": "NOT_SCORED",
}
TEXT_EXCLUDED_STAGE_STATUS = {
    "IMAGE": "EXCLUDED_BY_USER",
    "VIDEO": "EXCLUDED_BY_USER",
    "VOICE": "EXCLUDED_BY_USER",
    "MUSIC": "EXCLUDED_BY_USER",
    "SUBTITLE_ALIGNMENT": "EXCLUDED_BY_USER",
    "EDIT": "EXCLUDED_BY_USER",
    "MEDIA_QA": "EXCLUDED_BY_USER",
    "PUBLISH": "EXCLUDED_BY_USER",
}
R5_TEXT_SKIPPED_STAGES = list(TEXT_EXCLUDED_STAGE_STATUS)
TEXT_STATUS_AXES = {
    "excluded_step_status": "EXCLUDED_BY_USER",
    "execution_status": "NOT_EXECUTED",
    "observation_status": "NOT_EXECUTED",
    "media_qa_status": "QA_NOT_EXECUTED",
    "production_validation": "NOT_TESTED",
    "ncs_status": "NOT_SCORED",
    "nrs_status": "NOT_SCORED",
    "stage_status": TEXT_EXCLUDED_STAGE_STATUS,
    "release_status": "RELEASE_NOT_READY",
    "learning_status": "NO_REAL_DATA",
}
TEXT_SPEC_STATUS_BY_END_STATE = {
    "GLOBAL_READY": "SPEC_DRAFT",
    "PILOT_REWORK_REQUIRED": "SPEC_DRAFT",
    "TEXT_PILOT_COMPLETE": "SPEC_DRAFT",
    "TEXT_SPEC_COMPLETE": "SPEC_READY",
}


def expected_workflow_status(text_end_state: str | None) -> dict[str, Any]:
    return {
        "spec_status": TEXT_SPEC_STATUS_BY_END_STATE.get(text_end_state, "SPEC_DRAFT"),
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
    }


def expected_text_status_contract(text_end_state: str | None) -> dict[str, Any]:
    return {
        "text_end_state": text_end_state,
        "workflow_status": expected_workflow_status(text_end_state),
        "stage_status": TEXT_EXCLUDED_STAGE_STATUS,
        "production_validation": "NOT_TESTED",
        "ncs_status": "NOT_SCORED",
        "nrs_status": "NOT_SCORED",
    }
DIRECTOR_TARGET_MODES = {"EDITED_SEQUENCE", "GENERATABLE_SHOT"}
DIALOGUE_KINDS = {"VERBATIM_DIALOGUE", "NARRATION_AS_PROPOSED_VOICE_OVER"}
PILOT_SPREAD_CLAIMS = {"NONCONTIGUOUS", "EARLY_MIDDLE_LATE", "TARGETED_EXACT_RANGES"}
ACTION_REACTION_RE = re.compile(
    r"(?:走|跑|冲|抓|咬|吃|看|望|听|闻|说|问|答|喊|叫|回头|转身|发现|惊|躲|趴|起身|离开|进入|追|停)"
)
TIME_JUMP_RE = re.compile(
    r"(?:第?[一二三四五六七八九十百千万两\d]+(?:年|个月|月|日|天|个年头)(?:后|前|时间里|过去|以来)?|"
    r"多年(?:后|前)?|数年(?:后|前)?|后来|起初|一开始|最终|终于)"
)
SFX_TOKENS = ("吧唧", "嗖", "砰", "啪", "咔", "轰", "吱", "呱", "啾")
SFX_TOKEN_RE = re.compile("|".join(map(re.escape, SFX_TOKENS)))
SFX_PREFIX_RE = re.compile(
    rf"^\s*(?P<token>{'|'.join(map(re.escape, SFX_TOKENS))})(?P=token){{0,3}}\s*[—–－-]+\s*(?P<remainder>.+)$"
)
SPEECH_VERBS = (
    "低声说道",
    "大声说道",
    "开口说道",
    "自语道",
    "嘀咕道",
    "回答道",
    "反问道",
    "说道",
    "问道",
    "答道",
    "喊道",
    "叫道",
    "吼道",
    "笑道",
    "骂道",
    "喝道",
    "开口说",
    "低声说",
    "大声说",
    "回应",
    "反驳",
    "嘀咕",
    "说",
    "问",
    "答",
    "喊",
    "叫",
    "吼",
)
SPEECH_VERB_PATTERN = "|".join(map(re.escape, SPEECH_VERBS))
BEFORE_SPEECH_RE = re.compile(rf"(?:{SPEECH_VERB_PATTERN})\s*[：:,，]?\s*$")
AFTER_SPEECH_RE = re.compile(
    rf"(?P<verb>{SPEECH_VERB_PATTERN})\s*[。！？!?]?\s*$"
)
QUESTION_ATTRIBUTION_RE = re.compile(r"(?:询问道?|追问道?|发问|反问道?|问道)\s*[。！？!?]?\s*$")
PARAGRAPH_BREAK_RE = re.compile(r"\n[ \t]*\n")
THOUGHT_MARKERS = ("内心", "心中", "想到", "暗想", "心想", "自语", "心里", "思忖", "琢磨")
EMOTION_THOUGHT_MARKERS = (
    "心惊胆战",
    "惊恐",
    "恐惧",
    "害怕",
    "吓坏",
    "吓尿",
    "发慌",
    "忐忑",
    "绝望",
    "后悔",
    "担心",
    "疑惑",
    "纳闷",
)
V14_NON_LEXICAL_VOCAL_TOKENS = (
    "啊", "呀", "哎", "唉", "呃", "嗯", "哦", "嗷", "呜", "哈",
)
NON_LEXICAL_VOCAL_TOKENS = V14_NON_LEXICAL_VOCAL_TOKENS + (
    "唔", "嘶", "呵", "噗嗤", "扑哧", "哈哈", "呵呵", "嘿嘿", "嘻嘻",
)
NON_LEXICAL_VOCAL_RE = re.compile(
    rf"^(?:{'|'.join(map(re.escape, NON_LEXICAL_VOCAL_TOKENS))}){{1,4}}[!！?？。…~～—–－-]*$"
)
V14_NON_LEXICAL_VOCAL_RE = re.compile(
    rf"^(?:{'|'.join(map(re.escape, V14_NON_LEXICAL_VOCAL_TOKENS))}){{1,4}}[!！?？。…~～-]*$"
)
GENERIC_SHOT_FILLER_RE = re.compile(
    r"(?:第\s*\d+\s*镜\s*(?:按来源顺序推进|保持主体动作可辨)|"
    r"按来源顺序推进|保持主体动作可辨|忠实呈现当前冻结来源窗口)"
)
GENERIC_PROMPT_FILLER_PHRASES = (
    "忠实呈现冻结来源",
    "按来源顺序执行",
    "保持人物与空间连续",
    "所有导演提案均已逐项标注，不改写冻结事实",
)
PUNCTUATION_COLLISION_RE = re.compile(r"[。！？!?]\s*[；;，,]")
UNCONFIRMED_INTERPRETATION_RE = re.compile(
    r"(?:[\u4e00-\u9fff]{1,12}\s*(?:即指|实指|应为)\s*[\u4e00-\u9fff]{1,12}|"
    r"(?:音近|谐音).{0,8}(?:笔误|错字|应为)|(?:笔误|错字).{0,8}(?:应为|实指))"
)
PLOT_ACTION_GROUPS = {
    "PICK_UP": re.compile(r"(?:拾起|捡起|拿起|收入掌中|握入手中)"),
    "HIDE_OR_STORE": re.compile(r"(?:藏起|藏入怀里|收入怀中|收起|揣入怀中)"),
}
POV_OBSERVER_CONFLICT_RE = re.compile(
    r"(?:(?:POV|主观镜头|第一人称视角).{0,36}(?:观察者|视角主体|镜头主人|本人).{0,12}(?:入画|可见|出现)|"
    r"(?:观察者|视角主体|镜头主人|本人).{0,12}(?:入画|可见|出现).{0,36}(?:POV|主观镜头|第一人称视角))",
    re.IGNORECASE,
)
FIXED_CAMERA_RE = re.compile(r"(?:固定机位|机位固定|静止机位|锁定机位)")
MOVING_CAMERA_RE = re.compile(r"(?:跟随|跟拍|摇摄|摇镜|推轨|轨道移动|移动机位|横移|环绕)")
UNSOURCED_VOICE_RE = re.compile(r"(?:内心独白|画外音|旁白)")
UNSOURCED_VOICE_CLAUSE_SPLIT_RE = re.compile(r"[，,;；。！？!\?\n]+")
UNSOURCED_VOICE_NEGATION_RE = re.compile(
    r"(?:不要|不得|禁止|避免|不设|不使用|无新增|不增加|不添加|没有|无)"
)
UNSOURCED_VOICE_REVERSAL_RE = re.compile(
    r"(?:但(?:是)?|而是|而|却|转而|改为|改用|仍(?:然)?|依然)"
)
PROPOSAL_CATEGORIES = {
    "CAMERA",
    "PERFORMANCE",
    "SOUND",
    "BLOCKING",
    "CONTINUITY",
    "TRANSITION",
    "PACING",
    "OTHER_VISUAL",
}
SOURCE_ACTION_LOCKS = (
    "猴子还时不时用手里的棒子翘着头上那紧箍。",
)
VOCALIZATION_CONTEXT_RE = re.compile(
    r"(?:痛叫|惨叫|惊叫|尖叫|叫声|喊声|哭声|呻吟|哀嚎|嚎叫|发出.{0,6}(?:声|叫)|"
    r"(?:疼|痛|惊|吓|哭|笑).{0,4}(?:叫|喊|出声))"
)
V15_VOCALIZATION_CONTEXT_RE = re.compile(
    r"(?:痛叫|惨叫|惊叫|尖叫|叫声|喊声|哭声|呻吟|哀嚎|嚎叫|"
    r"闷哼|哼出|倒吸(?:了)?一口凉气|发出.{0,8}(?:声|叫)|"
    r"呼出(?:了)?(?:(?:短促|低沉|轻微|轻轻|低低|急促|微弱)的?)?"
    r"(?:一|两|几)?声|"
    r"(?:惊得|痛得|吓得).{0,8}(?:一|两|几)?声|"
    r"(?:疼|痛|惊|吓|哭|笑).{0,6}(?:叫|喊|出声))"
)
QUOTE_CONTEXT_RADIUS = 64
OUTPUT_ROLE_EXTENSIONS = (".md", ".json", ".md")
INVALID_WINDOWS_BASENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
INVISIBLE_FILENAME_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
WINDOWS_RESERVED_BASENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
IN_PLACE_COMMIT_MODE = "IN_PLACE_THREE_CARRIER_V1"
SIBLING_COMMIT_MODE = "SIBLING_THREE_CARRIER_V1"
COMMIT_MODES = {IN_PLACE_COMMIT_MODE, SIBLING_COMMIT_MODE}
TEMP_INPUT_NAMES = ["TARGET_PLAN.json", "AUTHORING.json", "OVERLAYS.json"]
PROMPT_SHELL_KEYS = {
    "capability_routing",
    "prompt_claims",
    "prompt_source_trace",
    "negative_clause_plan",
    "negative_clauses",
    "prompt_bundle",
    "prompt_quality_records",
    "director_contract",
    "dialogue_diff",
    "provenance",
    "provider_binding_status",
    "provider_registry_id",
    "provider_prompt",
    "unit_handoff_out",
    "unit_compile_sha256",
    "global_state_sha256",
    "content_self_review",
}
CONTENT_SELF_REVIEW_CHECK_KEYS = {
    "scene_title_is_specific",
    "prompt_working_draft_present",
    "facts_proposals_separated",
    "shots_have_dramatic_beats",
    "sound_is_unambiguous",
}
RENDERABLE_KINDS = {
    "SCENE_HEADING",
    "STORY_EVENT",
    "EVENT",
    "ACTION",
    "DIALOGUE",
    "NARRATION",
    "TRANSITION",
    "STATE_CHANGE",
}
METADATA_KINDS = {
    "PROJECT_TITLE",
    "VERSION_METADATA",
    "EPISODE_RUNTIME_GUIDANCE",
    "DELIVERY_NOTE",
}
CONTROL_KINDS = {"GLOBAL_RULE", "GLOBAL_DIRECTOR_NOTE", "FORMAT_INSTRUCTION"}
TRACE_RELATIONS = {
    "VERBATIM",
    "FAITHFUL_PARAPHRASE",
    "VISUALIZATION",
    "CONTINUITY_CARRY",
    "PROJECT_CONTROL",
    "DIRECTORIAL_CONTROL",
}
STORY_TRACE_RELATIONS = {"VERBATIM", "FAITHFUL_PARAPHRASE", "VISUALIZATION"}
SEMANTIC_GATE_VERSION = "alpha7-semantic-gate-1.0"
SEMANTIC_CAMERA_GENERIC_TERMS = {
    "镜头", "画面", "近景", "中景", "远景", "全景", "特写", "微距",
    "固定机位", "移动机位", "跟拍", "摇摄", "推轨", "横移", "环绕",
    "构图", "焦点", "景深", "光线", "轴线", "视角", "机位",
}
# Deliberately small and mechanical.  These are observable transitive plot
# relations, not a claim that the validator understands arbitrary Chinese.
SEMANTIC_PLOT_VERB_GROUPS = (
    ("TAKE_OUT", ("取出来", "拿出来", "抽出来", "拔出来", "取出", "拿出", "抽出", "拔出", "掏出")),
    ("PICK_UP", ("拾起来", "捡起来", "拿起来", "抓起来", "拾起", "捡起", "拿起", "抓起")),
    ("PUT", ("放进去", "装进去", "塞进去", "藏进去", "放入", "装入", "塞入", "藏入", "收进", "放回", "平码", "摆放")),
    ("HAND_OVER", ("递给", "交给", "推给")),
    ("OPEN", ("拉开", "打开", "揭开", "拆开")),
    ("CLOSE", ("关上", "关闭", "扣紧", "封进")),
    ("CONTACT", ("触碰", "接触", "碰过", "碰")),
    ("INSTALL", ("安装", "装机", "插入")),
    ("MOVE", ("移到", "移开", "移入", "推到", "搬到")),
    ("PRESS", ("按下", "按住")),
    ("ROTATE", ("转动", "转过", "转回", "旋转")),
    ("WEAR", ("戴上",)),
    ("WRITE", ("写下",)),
    ("PHOTOGRAPH", ("拍下", "拍摄")),
)
SEMANTIC_HANDLING_GROUPS = {
    "TAKE_OUT", "PICK_UP", "PUT", "HAND_OVER", "OPEN", "CLOSE",
    "INSTALL", "MOVE", "PRESS", "ROTATE", "WEAR",
}
SEMANTIC_NEGATION_RE = re.compile(r"(?:从未|没有|未曾|未|不再|不|别|勿)[^，。；！？!?\n]{0,4}$")
SEMANTIC_GENERIC_OBJECTS = {
    "动作", "身体", "画面", "镜头", "构图", "焦点", "机位", "节奏",
    "结果", "位置", "空间", "环境", "现场", "状态", "关系", "变化",
}
SEMANTIC_ACTOR_STOPWORDS = {
    "人物", "主体", "镜头", "画面", "摄影", "机位", "动作", "两人",
    "众人", "有人", "无人", "自己", "对方", "其中", "随后", "然后",
    "右手", "左手", "双手", "手指", "亲自", "而是", "谁也",
}
ALLOWED_EXCEPTION_CODES = {
    "NATURAL_BOUNDARY",
    "FINAL_REMAINDER",
    "HIGH_COMPLEXITY",
    "CAPACITY_LIMIT",
    "LOW_DENSITY_UNITS",
}
CONTINUITY_SNAPSHOT_KEYS = {
    "identity_versions",
    "wardrobe_versions",
    "spatial_state",
    "injuries_and_surface_state",
    "prop_ownership",
    "motion_vectors",
    "camera_state",
    "environment_state",
    "open_actions",
    "observed_state_authority",
}


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


SEMANTIC_DEFAULT_IGNORABLE_RANGES = (
    (0x034F, 0x034F),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)


def _semantic_is_default_ignorable(char: str) -> bool:
    codepoint = ord(char)
    return unicodedata.category(char) == "Cf" or any(
        start <= codepoint <= end
        for start, end in SEMANTIC_DEFAULT_IGNORABLE_RANGES
    )


def semantic_compare_text(value: str) -> str:
    """Normalize only a semantic-comparison copy, never stored source/user text."""

    normalized = unicodedata.normalize("NFC", value)
    return "".join(
        char for char in normalized if not _semantic_is_default_ignorable(char)
    )


def _semantic_compare_projection(value: str) -> tuple[str, list[tuple[int, int]]]:
    """Return comparison text plus original-code-point spans for each kept char."""

    normalized = unicodedata.normalize("NFC", value)
    source_nfd_positions: list[int] = []
    source_nfd_chars: list[str] = []
    for source_index, char in enumerate(value):
        decomposed = unicodedata.normalize("NFD", char)
        source_nfd_chars.extend(decomposed)
        source_nfd_positions.extend([source_index] * len(decomposed))
    normalized_nfd = unicodedata.normalize("NFD", normalized)
    if "".join(source_nfd_chars) != normalized_nfd:
        raise ValueError("semantic NFC projection could not preserve source cp mapping")

    normalized_spans: list[tuple[int, int]] = []
    cursor = 0
    for char in normalized:
        width = len(unicodedata.normalize("NFD", char))
        positions = source_nfd_positions[cursor : cursor + width]
        cursor += width
        if positions:
            normalized_spans.append((min(positions), max(positions) + 1))
        else:
            normalized_spans.append((0, 0))

    kept_chars: list[str] = []
    kept_spans: list[tuple[int, int]] = []
    for char, span in zip(normalized, normalized_spans):
        if _semantic_is_default_ignorable(char):
            continue
        kept_chars.append(char)
        kept_spans.append(span)
    return "".join(kept_chars), kept_spans


def normalized_real_strings(value: Any) -> list[str]:
    """Return only real string leaves, normalized and stripped.

    Provenance checks must never succeed because a JSON key, quote, comma, or
    list serialization happened to contain an anchor.  Walk the authored
    value itself and compare its actual string leaves instead.
    """

    if isinstance(value, str):
        normalized = normalize_text(value).strip()
        return [normalized] if normalized else []
    if isinstance(value, list):
        return [text for item in value for text in normalized_real_strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in normalized_real_strings(item)]
    return []


def normalized_value_contains_exact_string(value: Any, expected: str) -> bool:
    target = normalize_text(expected).strip()
    return bool(target) and target in normalized_real_strings(value)


SEMANTIC_SENTENCE_TERMINATORS = frozenset("。！？!?；;")
SEMANTIC_SENTENCE_CLOSERS = frozenset("”’\"'」』》】）)]")
SEMANTIC_SENTENCE_OPENERS = {
    "“": "”",
    "‘": "’",
    "「": "」",
    "『": "』",
    "《": "》",
    "【": "】",
    "（": "）",
    "(": ")",
    "[": "]",
}


def semantic_sentence_spans_v14(text: str, *, base_cp: int = 0) -> list[dict[str, Any]]:
    """Return complete, exact, sentence-level spans over normalized source text.

    Commas and colons remain inside the sentence.  Sentence punctuation closes
    the sentence and immediately adjacent closing quotes/brackets travel with
    it.  Leading/trailing whitespace is excluded without losing absolute cp
    offsets, and a final non-punctuated source sentence remains one whole span.
    """

    normalized = normalize_text(text)
    content_start = len(normalized) - len(normalized.lstrip())
    content_end = len(normalized.rstrip())
    if content_start >= content_end:
        return []
    spans: list[dict[str, Any]] = []
    segment_start = content_start
    cursor = content_start
    closer_stack: list[str] = []
    while cursor < content_end:
        char = normalized[cursor]
        if char in SEMANTIC_SENTENCE_OPENERS:
            closer_stack.append(SEMANTIC_SENTENCE_OPENERS[char])
        elif char == '"':
            if closer_stack and closer_stack[-1] == char:
                closer_stack.pop()
            else:
                closer_stack.append(char)
        elif closer_stack and char == closer_stack[-1]:
            closer_stack.pop()
        if char in SEMANTIC_SENTENCE_TERMINATORS:
            segment_end = cursor + 1
            # Consume the whole adjacent sentence tail, including punctuation
            # outside a just-closed quotation/bracket.  Without this second
            # terminator pass, text such as `“对白！”。` produced a useful
            # dialogue anchor followed by a bogus punctuation-only anchor.
            while segment_end < content_end:
                tail_char = normalized[segment_end]
                if tail_char in SEMANTIC_SENTENCE_CLOSERS:
                    if closer_stack and tail_char == closer_stack[-1]:
                        closer_stack.pop()
                    segment_end += 1
                    continue
                if tail_char in SEMANTIC_SENTENCE_TERMINATORS:
                    segment_end += 1
                    continue
                break
            # A sentence mark inside an open quotation is not a safe semantic
            # boundary.  Keep scanning until the quotation/bracket closes, so
            # helper-owned anchors never become dangling halves of dialogue.
            if closer_stack:
                cursor = segment_end
                continue
            left = segment_start
            while left < segment_end and normalized[left].isspace():
                left += 1
            right = segment_end
            while right > left and normalized[right - 1].isspace():
                right -= 1
            if left < right and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", normalized[left:right]):
                spans.append(
                    {
                        "start_cp": base_cp + left,
                        "end_cp": base_cp + right,
                        "exact_text": normalized[left:right],
                    }
                )
            segment_start = segment_end
            cursor = segment_end
            continue
        cursor += 1
    left = segment_start
    while left < content_end and normalized[left].isspace():
        left += 1
    if left < content_end and re.search(
        r"[\u4e00-\u9fffA-Za-z0-9]", normalized[left:content_end]
    ):
        spans.append(
            {
                "start_cp": base_cp + left,
                "end_cp": base_cp + content_end,
                "exact_text": normalized[left:content_end],
            }
        )
    return spans


QUOTE_ATTRIBUTION_TAIL_RE = re.compile(
    r"^(?:一声|两声|几声|一下)(?:[，,、。；;！？!?]|$)"
)
QUOTE_TERMINAL_CLOSE_RE = re.compile(r"[！？!?…][”’」』》】）)\]]$")


def semantic_sentence_spans(text: str, *, base_cp: int = 0) -> list[dict[str, Any]]:
    """Return 1.5 sentence spans while preserving quote-attribution tails.

    Version 1.4 ended a span immediately after punctuation inside a closing
    quote.  That split grammatical units such as ``“嘶！”一声，手掌……``.  The
    1.5 derivation merges only a directly attached sound/count attribution
    tail; ordinary text such as ``“停！”她转身。`` remains two spans.  The frozen
    1.4 implementation above is retained for read-only historical contracts.
    """

    normalized = normalize_text(text)
    legacy = semantic_sentence_spans_v14(normalized, base_cp=base_cp)
    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(legacy):
        current = legacy[index]
        if index + 1 < len(legacy):
            following = legacy[index + 1]
            if (
                QUOTE_TERMINAL_CLOSE_RE.search(current["exact_text"])
                and QUOTE_ATTRIBUTION_TAIL_RE.match(following["exact_text"])
            ):
                local_start = current["start_cp"] - base_cp
                local_end = following["end_cp"] - base_cp
                merged.append(
                    {
                        "start_cp": current["start_cp"],
                        "end_cp": following["end_cp"],
                        "exact_text": normalized[local_start:local_end],
                    }
                )
                index += 2
                continue
        merged.append(current)
        index += 1
    return _split_duration_repeat_transition_spans(merged)


def semantic_span_containing_quote(
    source_text: str, quote_start_cp: int, quote_end_cp: int
) -> dict[str, Any] | None:
    """Return the one current-1.5 semantic anchor that owns a quoted span."""

    if (
        not isinstance(quote_start_cp, int)
        or isinstance(quote_start_cp, bool)
        or not isinstance(quote_end_cp, int)
        or isinstance(quote_end_cp, bool)
        or not (0 <= quote_start_cp < quote_end_cp <= len(source_text))
    ):
        return None
    matches = [
        span
        for span in semantic_sentence_spans(source_text)
        if span["start_cp"] <= quote_start_cp
        and quote_end_cp <= span["end_cp"]
    ]
    return matches[0] if len(matches) == 1 else None


def has_affirmative_unsourced_voice(text: str) -> bool:
    """Return True only for an affirmative voice addition in a clause.

    Creator-facing fields commonly say `不要旁白` or `不增加画外音` as a
    negative direction.  A raw keyword search inverted that intent.  Negation
    is scoped to the same punctuation-delimited clause and stops at an explicit
    reversal such as `但`/`而`/`改用`, so affirmative additions still fail closed.
    """

    normalized = normalize_text(text)
    for clause in UNSOURCED_VOICE_CLAUSE_SPLIT_RE.split(normalized):
        if not clause:
            continue
        for voice_match in UNSOURCED_VOICE_RE.finditer(clause):
            prefix = clause[: voice_match.start()]
            negations = list(UNSOURCED_VOICE_NEGATION_RE.finditer(prefix))
            if not negations:
                return True
            nearest_negation = negations[-1]
            if UNSOURCED_VOICE_REVERSAL_RE.search(prefix[nearest_negation.end() :]):
                return True
    return False


def _complete_source_anchor_candidates(
    bound_text: str, span_deriver: Any
) -> list[str]:
    normalized = normalize_text(bound_text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    candidates: list[str] = list(lines)
    candidates.extend(
        span["exact_text"] for span in span_deriver(normalized)
    )
    for line in lines:
        candidates.extend(
            item.strip()
            for item in re.findall(r"[^，,；;。！？!?：:\n]+[，,；;。！？!?：:]?", line)
            if item.strip()
        )
    return list(dict.fromkeys(candidates))


def complete_source_anchor_candidates_v14(bound_text: str) -> list[str]:
    return _complete_source_anchor_candidates(bound_text, semantic_sentence_spans_v14)


def complete_source_anchor_candidates(bound_text: str) -> list[str]:
    return _complete_source_anchor_candidates(bound_text, semantic_sentence_spans)


def source_anchor_is_complete(anchor: Any, bound_text: str) -> bool:
    """Accept a whole source line or a whole punctuation-delimited clause.

    A substring is not enough: arbitrary 24-character prefixes/suffixes made
    Round3 technically traceable while being useless as an editorial anchor.
    """

    if not nonempty_string(anchor):
        return False
    normalized_anchor = normalize_text(anchor).strip()
    semantic_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", normalized_anchor)
    lines = [line.strip() for line in normalize_text(bound_text).splitlines() if line.strip()]
    if normalized_anchor in lines and semantic_chars:
        return True
    if len(semantic_chars) < 2:
        return False
    return normalized_anchor in complete_source_anchor_candidates(bound_text)


def source_anchor_is_complete_v14(anchor: Any, bound_text: str) -> bool:
    if not nonempty_string(anchor):
        return False
    normalized_anchor = normalize_text(anchor).strip()
    semantic_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", normalized_anchor)
    lines = [line.strip() for line in normalize_text(bound_text).splitlines() if line.strip()]
    if normalized_anchor in lines and semantic_chars:
        return True
    if len(semantic_chars) < 2:
        return False
    return normalized_anchor in complete_source_anchor_candidates_v14(bound_text)


def source_anchor_is_complete_for_version(
    anchor: Any, bound_text: str, contract_version: str
) -> bool:
    if contract_version in READ_ONLY_CONTRACT_VERSIONS:
        return source_anchor_is_complete_v14(anchor, bound_text)
    return source_anchor_is_complete(anchor, bound_text)


SOURCE_FIELD_LABEL_RE = re.compile(
    r"^(?:来源入口|来源动作|来源出口|下一镜延续这个来源出口|原文事实|来源事实)\s*[：:]\s*"
)


def source_supported_value_is_exact(value: Any, anchor: str) -> bool:
    """Reject a source fact field that appends unregistered interpretation."""

    expected = normalize_text(anchor).strip()

    def clean(item: str) -> str:
        text = normalize_text(item).strip()
        return SOURCE_FIELD_LABEL_RE.sub("", text).strip()

    leaves = normalized_real_strings(value)
    return bool(leaves) and all(clean(item) == expected for item in leaves)


def expected_sequence_minimum_shots(
    source_text: str,
    *,
    dialogue_turns: int = 0,
    atom_count: int = 0,
) -> int:
    """Compute a bounded density floor for an EDITED_SEQUENCE.

    The floor covers dialogue exchange, visible action/reaction density,
    explicit time jumps, and very wide source windows.  It is intentionally
    capped so the deterministic guard remains a floor, not automatic editing.
    """

    normalized = normalize_text(source_text)
    action_signals = len(ACTION_REACTION_RE.findall(normalized))
    time_jumps = len(TIME_JUMP_RE.findall(normalized))
    action_floor = (
        6 if action_signals >= 15
        else 5 if action_signals >= 9
        else 4 if action_signals >= 5
        else 3 if action_signals >= 3
        else 2
    )
    return max(
        2,
        min(8, (dialogue_turns + 1) // 2) if dialogue_turns >= 4 else 2,
        action_floor,
        min(8, atom_count) if atom_count >= 3 else 2,
        min(8, time_jumps + 1) if time_jumps >= 2 else 2,
    )


VOCAL_SPEAKER_BOUNDARY = (
    r"(?:^|这时|此时|只见|只听|听见|听到|[\s，,、]|的)"
)
VOCAL_SPEAKER_ADVERB = (
    r"(?:(?:猛地|忽然|顿时|一下|不由得?|轻轻地?|低低地?|痛苦地?))?"
)
VOCAL_BREATH_DESCRIPTOR = (
    r"(?:(?:短促|低沉|轻微|轻轻|低低|急促|微弱)的?)?"
)
VOCAL_BREATH_PREDICATE = (
    rf"呼出(?:了)?{VOCAL_BREATH_DESCRIPTOR}(?:一|两|几)?声"
)
VOCAL_AIR_SOUND_PREDICATE = (
    rf"发出(?:了)?(?:一|两|几)?声{VOCAL_BREATH_DESCRIPTOR}气音"
)
VOCAL_PREDICATE = (
    rf"(?:(?:疼得|痛得|惊得|吓得)(?:{VOCAL_AIR_SOUND_PREDICATE}|发出(?:一|两|几)?声|"
    r"喊(?:了)?(?:一|两|几)?声|叫(?:了)?(?:一|两|几)?声)?|"
    rf"{VOCAL_AIR_SOUND_PREDICATE}|发出(?:一|两|几)?声|"
    r"喊(?:了)?(?:一|两|几)?声|叫(?:了)?(?:一|两|几)?声|"
    r"闷哼(?:了)?(?:一|两|几)?声|哼出(?:一|两|几)?声|"
    rf"{VOCAL_BREATH_PREDICATE}|倒吸(?:了)?一口凉气)"
)
VOCAL_SPEAKER_BEFORE_RE = re.compile(
    rf"{VOCAL_SPEAKER_BOUNDARY}(?P<speaker>[\u4e00-\u9fff]{{1,4}}?)"
    rf"{VOCAL_SPEAKER_ADVERB}{VOCAL_PREDICATE}\s*[：:]?\s*$"
)
VOCAL_SPEAKER_BEFORE_EMISSION_QUOTE_RE = re.compile(
    rf"{VOCAL_SPEAKER_BOUNDARY}(?P<speaker>[\u4e00-\u9fff]{{1,4}}?)"
    rf"{VOCAL_SPEAKER_ADVERB}发出\s*$"
)
VOCAL_SPEAKER_BEFORE_BREATH_QUOTE_RE = re.compile(
    rf"{VOCAL_SPEAKER_BOUNDARY}(?P<speaker>[\u4e00-\u9fff]{{1,4}}?)"
    rf"{VOCAL_SPEAKER_ADVERB}呼出(?:了)?{VOCAL_BREATH_DESCRIPTOR}\s*$"
)
VOCAL_SPEAKER_BEFORE_QUOTE_RE = re.compile(
    rf"{VOCAL_SPEAKER_BOUNDARY}(?P<speaker>[\u4e00-\u9fff]{{1,4}}?)"
    rf"{VOCAL_SPEAKER_ADVERB}\s*$"
)
VOCAL_SPEAKER_AFTER_DIRECT_RE = re.compile(
    rf"^\s*(?P<speaker>[\u4e00-\u9fff]{{1,4}}?){VOCAL_SPEAKER_ADVERB}"
    r"(?:闷哼|哼出|发出|呼出|痛叫|惊叫|喊|叫)"
)
VOCAL_SPEAKER_AFTER_ATTRIBUTION_RE = re.compile(
    r"^(?:的)?(?:(?:了)?(?:一|两|几)?声|一下)?[\s，,、]*"
    r"(?:是|由|来自)(?P<speaker>[\u4e00-\u9fff]{1,4}?)(?:的)?"
    r"(?:喊|叫|发出|痛叫|惊叫|闷哼)"
)
DIRECT_EMISSION_AFTER_SPEAKER_RE = re.compile(
    rf"^{VOCAL_SPEAKER_ADVERB}发出(?:一|两|几)?声\s*[：:]?\s*$"
)
POST_QUOTE_VOCAL_SUFFIX_RE = re.compile(
    r"^\s*(?:了)?(?:一|两|几)声(?:[，,。！？!?；;]|$)"
)
POST_QUOTE_VOCAL_ACTION_RE = re.compile(
    r"^\s*(?:笑|哭)(?:了)?(?:一|两|几)?(?:声)?(?:出声|起来|出来)"
)
PRE_QUOTE_SUPPRESSED_LAUGHTER_SUBJECT_RE = re.compile(
    r"^(?P<speaker>[\u4e00-\u9fff]{2,4})"
    r"(?:憋了.{1,8}[，,])?(?:实在)?没忍住[，,][“「『\"]?$"
)
VOCAL_SPEAKER_WRAPPER_RE = re.compile(
    r"^(?:(?:这时|此时|随后|忽然|顿时|只见|只听|听见|听到|"
    r"不知(?:是)?|是|由|来自))+"
)
UNKNOWN_VOCAL_SPEAKER_RE = re.compile(
    r"^(?:谁|某人|有人|不知谁|未知(?:人物|主体)?|什么人)$"
)
NON_PERSON_SPEAKER_RE = re.compile(
    r"^(?:一旁|旁边|附近|远处|近处|年轻|年长|柜台|门口|窗边|墙边|"
    r"屋内|屋外|门外|走廊|老人|青年|少年|少女|男孩|女孩|男人|女人|"
    r"店员|女工|男工|医生|护士|师傅|老板)$"
)
PERSON_ROLE_PREFIX_RE = re.compile(
    r"^(?:店员|女工|男工|医生|护士|警员|师傅|老板|青年|老人|女孩|男孩)"
    r"(?=[\u4e00-\u9fff]{2,3}$)"
)
NON_VOCAL_SOUND_OWNER_RE = re.compile(
    r"(?:门锁|门铃|木门|铁门|房门|大门|门|桌角|水壶|石头|马达|马车|马桶|"
    r"杨树|柳树|王冠|钱币|陈皮|金属|陶罐|玻璃|机器|设备|手机|钟表?|风|雨|雷|汽车|引擎|"
    r"轮胎|地板|木板|屏幕|扬声器|喇叭|阀门|止回阀|阀|走廊|门外|屋内|远处|近处|"
    r"柜台|桌子|椅子|墙壁|窗户|水管|管道)"
    r"(?:的)?(?:发出|呼出|响起|传来|声响|声音)"
)
CHINESE_SURNAME_PATTERN = (
    r"(?:[赵钱孙李周吴郑王冯陈蒋沈韩杨朱秦许何吕张孔曹严华金魏陶姜谢邹苏潘葛范彭"
    r"鲁韦马苗方俞任袁柳史唐薛雷贺倪汤罗毕郝安常傅齐康伍余顾孟黄萧尹姚邵汪毛"
    r"戴宋熊纪舒项董梁杜阮蓝席季贾江童郭梅盛林钟徐高夏蔡田樊胡霍万卢莫房石崔"
    r"程陆翁段白龙叶黎冉曾]|"
    r"欧阳|司马|上官|诸葛|夏侯|皇甫|尉迟|公孙|慕容|令狐|宇文|长孙|司徒|司空|独孤)"
)
PERSON_NAME_PATTERN = rf"{CHINESE_SURNAME_PATTERN}[\u4e00-\u9fff]{{1,2}}?"
AMBIGUOUS_VOCAL_OWNER_RE = re.compile(
    rf"^(?:我|你|他|她|其|我们|你们|他们|她们|猫|狗|犬|小猫|小狗|幼猫|幼犬|"
    rf"{PERSON_NAME_PATTERN})$"
)
VOCAL_PRONOUNS = {"她", "他", "其"}
PERSON_NAME_SUBJECT_RE = re.compile(
    rf"(?P<name>{PERSON_NAME_PATTERN})(?="
    r"被|把|向|对|朝|从|在|正|仍|已|没有|未|忽然|突然|随后|继续|开始|停|"
    r"抬|低|转|回|看|望|盯|听|说|问|答|喊|叫|走|跑|站|坐|蹲|伸|收|松|"
    r"握|拿|放|推|拉|按|摇|点|笑|哭|皱|吸|呼|惊|疼|痛|保持|发现|确认|"
    r"检查|离开|进入|靠近|跟|扶|抱|拍|写|读|戴|取|移|用)"
)
PERSON_NAME_OBJECT_RE = re.compile(
    rf"(?:看着|望向|盯着|对着|朝向|扶住|抓住|遇见|看见|听见|问|给|递给|交给|让)"
    rf"(?P<name>{PERSON_NAME_PATTERN})(?=$|[，,、])"
)
STRICT_PERSON_NAME_PATTERN = rf"{CHINESE_SURNAME_PATTERN}[\u4e00-\u9fff]{{1,2}}"
SPOKEN_ENTITY_PATTERN = (
    rf"(?:{PERSON_NAME_PATTERN}|她|他|其|猫|狗|犬|小猫|小狗|幼猫|幼犬)"
)
SPOKEN_CONTROLLED_MODIFIER_PATTERN = (
    r"(?:立即|立刻|随后|接着|低声|大声|轻声|慢慢|急忙|忽然|回头|"
    r"听完|听罢|闻言|看完(?:后)?|读完(?:后)?|一起|同时|异口同声|共同|一同)"
)
ATTRIBUTION_HORIZONTAL_SPACE = r"[^\S\r\n]*"
STRICT_ATTRIBUTION_ACTOR_PATTERN = (
    r"(?P<speaker>她|他|其|猫|狗|犬|小猫|小狗|幼猫|幼犬|[\u4e00-\u9fff]{2,4}?)"
)
SPOKEN_ATTRIBUTION_VERB_PATTERN = rf"(?:{SPEECH_VERB_PATTERN}|回答|补充)"
SPOKEN_DIRECT_ATTRIBUTION_RE = re.compile(
    rf"^{STRICT_ATTRIBUTION_ACTOR_PATTERN}"
    rf"(?:(?:{SPOKEN_CONTROLLED_MODIFIER_PATTERN}){ATTRIBUTION_HORIZONTAL_SPACE})*"
    rf"{SPOKEN_ATTRIBUTION_VERB_PATTERN}{ATTRIBUTION_HORIZONTAL_SPACE}[：:]$"
)
SPOKEN_VOICE_OWNER_RE = re.compile(
    rf"^{STRICT_ATTRIBUTION_ACTOR_PATTERN}的[^。！？!?；;\n“”]{{0,12}}"
    rf"(?:声音|声线|嗓音){ATTRIBUTION_HORIZONTAL_SPACE}[：:]$"
)
SPOKEN_ACTION_ATTRIBUTION_RE = re.compile(
    rf"^{STRICT_ATTRIBUTION_ACTOR_PATTERN}"
    r"(?:沉默(?:了)?(?:片刻|一下)?|点(?:了)?点头|点头|"
    r"摇(?:了)?摇头|摇头|抬手又放下|"
    r"拉开(?:朝右的)?(?:拉链|抽屉|门|帘|柜|箱|袋|盖))"
    rf"{ATTRIBUTION_HORIZONTAL_SPACE}[：:]$"
)
SPOKEN_SUBJECT_NAME_RE = re.compile(
    rf"(?P<name>{PERSON_NAME_PATTERN})(?="
    r"的[^。！？!?；;\n“”]{0,12}(?:声音|声线|嗓音)|"
    r"没有说话|未说话|说|问|答|回答|回应|反问|喊|叫|补充|沉默|点|摇|抬|"
    r"听|闻|读|看|望|盯|指|拉|推|把|向|对|朝|冲|跟|同|陪|让|给|递|交|扶|抓|请|"
    r"从|在|正|仍|已|未|忽然|随后|"
    r"继续|开始|停|转|回|走|站|坐|伸|收|松|握|拿|放|按|发现|确认|检查)"
)
SPOKEN_MODIFIED_SUBJECT_NAME_RE = re.compile(
    rf"(?P<name>{PERSON_NAME_PATTERN})(?="
    rf"(?:{SPOKEN_CONTROLLED_MODIFIER_PATTERN}\s*)+"
    rf"(?:{SPEECH_VERB_PATTERN}|回答|补充))"
)
SPOKEN_OBJECT_NAME_RE = re.compile(
    rf"(?:看着|看向|望向|盯着|对着|朝向|陪着|陪同|扶着|拉着|挽着|带着|靠着|"
    rf"对|向|朝|冲|跟|同|陪|请|叫|扶住|抓住|遇见|看见|听见|问|给|推给|递给|交给|让)"
    rf"(?P<name>{PERSON_NAME_PATTERN})(?="
    rf"(?:{SPOKEN_CONTROLLED_MODIFIER_PATTERN}\s*)*(?:{SPEECH_VERB_PATTERN}|回答|补充)|"
    r"$|[\s，,、：:。！？!?；;])"
)
SPOKEN_BESIDE_NAME_RE = re.compile(
    rf"站在(?P<name>{PERSON_NAME_PATTERN})(?:的)?旁边"
)
COORDINATED_PERSON_CONNECTOR_RE = re.compile(
    r"(?:以及|、|，|,|和|与|同|跟|及|\s+)"
)
COORDINATED_PERSON_GROUP_RE = re.compile(
    rf"(?P<group>{PERSON_NAME_PATTERN}"
    rf"(?:(?:以及|、|，|,|和|与|同|跟|及|\s+){PERSON_NAME_PATTERN})+)"
)
COORDINATED_ATTRIBUTION_TAIL_RE = re.compile(
    rf"^(?:{SPOKEN_CONTROLLED_MODIFIER_PATTERN}\s*)*"
    rf"(?:{SPEECH_VERB_PATTERN}|回答|补充)\s*[：:]\s*$"
)
COORDINATED_VOICE_TAIL_RE = re.compile(
    r"^的[^。！？!?；;\n“”]{0,12}(?:声音|声线|嗓音)\s*[：:]\s*$"
)
COORDINATED_OBJECT_PREFIX_RE = re.compile(
    r"(?:看着|看向|望向|盯着|对着|朝向|陪着|陪同|扶着|拉着|挽着|带着|靠着|"
    r"对|向|朝|冲|跟|同|陪|请|叫|扶住|抓住|遇见|看见|听见|问|给|推给|"
    r"递给|交给|让)\s*$"
)
PERSON_REGISTRY_EVIDENCE_RE = re.compile(
    rf"(?P<name>{PERSON_NAME_PATTERN})(?="
    rf"(?:{SPOKEN_CONTROLLED_MODIFIER_PATTERN}\s*)*"
    r"(?:说|问|答|回答|回应|没有说话|未说话|沉默|闷哼|哼出|痛叫|惊叫|"
    r"倒吸(?:了)?一口凉气))"
)
LOCAL_PRONOUN_RE = re.compile(
    r"(?:^|[\s，,。！？!?；;：:、])(?P<actor>她|他|其)(?="
    r"的|把|被|向|对|朝|从|在|正|仍|已|未|忽然|随后|继续|开始|停|转|回|"
    r"看|听|说|问|答|喊|叫|走|跑|站|坐|伸|收|松|握|拿|放|推|拉|扶|呼|发)"
)
LOCAL_ANIMAL_RE = re.compile(
    r"(?:^|[\s，,。！？!?；;：:、])(?:一只|一条|一头)?"
    r"(?P<actor>小猫|小狗|幼猫|幼犬|猫|狗|犬)"
)
LOCAL_UNKNOWN_LIVING_RE = re.compile(
    r"(?P<actor>某人|有人|不知谁|陌生人|未知人物|另一个人|"
    r"(?:老|小|阿)[\u4e00-\u9fff]{1,2}|"
    r"店员|掌柜|医生|护士|警员|师傅|老板|工人|女工|男工|服务员|售货员|"
    r"老人|青年|少年|少女|男孩|女孩|男人|女人)"
)
POST_ATTRIBUTION_PARAGRAPH_BREAK_RE = re.compile(r"\r?\n[ \t]*\r?\n")
ALLOWED_ANIMAL_ACTORS = frozenset({"猫", "狗", "犬", "小猫", "小狗", "幼猫", "幼犬"})
VISIBLE_TEXT_LABEL_RE = re.compile(
    r"【(?:画面文字|字幕|文字标签|录音转写|转写文字|屏幕文字)"
    r"(?:\s*[，,]\s*不朗读)?】"
)
AUDIO_DIALOGUE_LABEL_RE = re.compile(
    r"【(?:录音内现场对白|录音内对白|录音内口播|音频内现场对白|同期录音对白)】"
)
VISIBLE_TEXT_CARRIER_RE = re.compile(
    r"(?:^|[。！？!?；;\n])[^。！？!?；;\n“”]{0,24}?"
    r"(?:画面文字|牌子|标签|表格|屏幕|记录卡|字幕|录音转写|转写文本|转写|展板|封条)"
    r"[^。！？!?；;\n“”]{0,10}?(?:写着|写有|显示|印着|标着|列着|呈现)"
    r"\s*[：:]\s*[^。！？!?；;\n“”]{0,24}$"
)
HUMAN_SPECIFIC_VOCAL_RE = re.compile(
    r"(?:疼得|痛得|惊得|吓得|闷哼|哼出|痛叫|惊叫|惨叫|尖叫|倒吸(?:了)?一口凉气)"
)
SPOKEN_PURE_POST_ATTRIBUTION_RE = re.compile(
    rf"^{STRICT_ATTRIBUTION_ACTOR_PATTERN}"
    rf"(?:(?:{SPOKEN_CONTROLLED_MODIFIER_PATTERN}){ATTRIBUTION_HORIZONTAL_SPACE})*"
    rf"{SPOKEN_ATTRIBUTION_VERB_PATTERN}{ATTRIBUTION_HORIZONTAL_SPACE}[。！？!?]?$"
)
NO_SUBJECT_VOCAL_MANNER_RE = re.compile(
    rf"^(?:(?:随后|接着|忽然|顿时|只)\s*)?"
    rf"(?:从(?:喉间|喉咙|鼻腔|胸腔)\s*)?{VOCAL_SPEAKER_ADVERB}"
    rf"(?:{VOCAL_PREDICATE})\s*[：:]?\s*$"
)
PERSON_SUBJECT_LEFT_BOUNDARY_RE = re.compile(
    r"(?:^|[\s，,。！？!?；;：:、【】（）()]|这时|此时|随后|接着|忽然|顿时|"
    r"只见|只听|听见|听到|一旁的|年轻的|柜台后的)$"
)
SPEAKER_CANDIDATE_GRAMMAR_SUFFIX_RE = re.compile(
    r"(?:低声说道|大声说道|开口说道|回答道|反问道|问道|答道|喊道|叫道|"
    r"说道|回答|回应|补充|反问|追问|询问|开口|发出|呼出|哼出|闷哼|"
    r"痛叫|惊叫|沉默|点头|摇头|说|问|答|喊|叫|吼|道|回|看|望|听|"
    r"拉|推|拿|放|写|读|站|坐|走|跑|停|倒|吸|呼|发|哼|闷|疼|痛|惊|吓)$"
)
BARE_PERSON_NAME_RE = re.compile(rf"(?P<name>{PERSON_NAME_PATTERN})")


def _normalize_vocal_speaker_candidate(value: Any) -> str:
    """Remove grammar wrappers while rejecting unknown or non-vocal owners."""

    candidate = normalize_text(value).strip() if isinstance(value, str) else ""
    candidate = VOCAL_SPEAKER_WRAPPER_RE.sub("", candidate).strip()
    candidate = re.sub(r"的$", "", candidate).strip()
    candidate = PERSON_ROLE_PREFIX_RE.sub("", candidate).strip()
    if (
        not re.fullmatch(r"[\u4e00-\u9fff]{1,4}", candidate)
        or UNKNOWN_VOCAL_SPEAKER_RE.fullmatch(candidate)
        or NON_PERSON_SPEAKER_RE.fullmatch(candidate)
        or NON_VOCAL_SOUND_OWNER_RE.search(candidate + "发出")
    ):
        return "SOURCE_UNSPECIFIED"
    return candidate


def _normalize_ambiguous_vocal_owner(value: Any) -> str:
    """Accept only explicit pronouns, finite animal nouns, or name-like owners.

    Bare ``发出`` and ``人物“嘶”了一声`` shapes are grammatically available to
    both living subjects and objects.  They therefore need a stricter owner
    test than human-only predicates such as ``闷哼`` or ``倒吸一口凉气``.
    """

    candidate = _normalize_vocal_speaker_candidate(value)
    if (
        candidate == "SOURCE_UNSPECIFIED"
        or not AMBIGUOUS_VOCAL_OWNER_RE.fullmatch(candidate)
    ):
        return "SOURCE_UNSPECIFIED"
    return candidate


def _strict_source_speaker_candidate(value: Any) -> str:
    """Accept only an explicit name, pronoun, or finite allowed animal noun."""

    candidate = _normalize_ambiguous_vocal_owner(value)
    if candidate == "SOURCE_UNSPECIFIED":
        return candidate
    if SPEAKER_CANDIDATE_GRAMMAR_SUFFIX_RE.search(candidate):
        return "SOURCE_UNSPECIFIED"
    if candidate in VOCAL_PRONOUNS or candidate in {
        "猫", "狗", "犬", "小猫", "小狗", "幼猫", "幼犬",
    }:
        return candidate
    return (
        candidate
        if re.fullmatch(STRICT_PERSON_NAME_PATTERN, candidate)
        else "SOURCE_UNSPECIFIED"
    )


def _strip_quoted_source(text: str) -> str:
    """Remove quote payloads before actor scans inspect attribution grammar."""

    return re.sub(r"“[^”]*”|「[^」]*」|『[^』]*』", " ", normalize_text(text))


def _visible_text_carrier_prefix(prefix: str) -> bool:
    """Return whether a visible-text carrier directly governs the current quote."""

    normalized = normalize_text(prefix)
    last_closed_quote = max(
        (normalized.rfind(token) for token in ("”", "」", "』", '"')),
        default=-1,
    )
    if last_closed_quote >= 0:
        trailing = normalized[last_closed_quote + 1 :]
        # One visible carrier may govern an adjacent list of quoted fields, but
        # it must not bleed through a later live-speech attribution.
        trailing_attribution = trailing.lstrip(" \t，,；;")
        if BEFORE_SPEECH_RE.search(trailing) or any(
            pattern.fullmatch(trailing_attribution)
            for pattern in (
                SPOKEN_DIRECT_ATTRIBUTION_RE,
                SPOKEN_VOICE_OWNER_RE,
                SPOKEN_ACTION_ATTRIBUTION_RE,
            )
        ):
            return False
    visible_labels = list(VISIBLE_TEXT_LABEL_RE.finditer(normalized))
    audio_labels = list(AUDIO_DIALOGUE_LABEL_RE.finditer(normalized))
    if audio_labels and (
        not visible_labels or audio_labels[-1].start() > visible_labels[-1].start()
    ):
        return False
    return bool(visible_labels or VISIBLE_TEXT_CARRIER_RE.search(normalized))


def _quote_has_visible_text_carrier(
    source_text: str, quote_start_cp: int, quote_end_cp: int
) -> bool:
    span = semantic_span_containing_quote(source_text, quote_start_cp, quote_end_cp)
    if span is None:
        return False
    local_quote_start = quote_start_cp - span["start_cp"]
    return _visible_text_carrier_prefix(span["exact_text"][:local_quote_start])


STRICT_ATTRIBUTION_FORBIDDEN_ACTOR_RE = re.compile(
    r"(?:以及|和|与|同|跟|陪|及|让|请|叫|对|向|朝|面|、|，|,|"
    r"^(?:只|从|是|由|来自)|的$|喉间|喉咙|鼻腔|胸腔)"
)
ATTRIBUTION_COMPOUND_SURNAMES = (
    "欧阳", "司马", "上官", "诸葛", "夏侯", "皇甫", "尉迟", "公孙",
    "慕容", "令狐", "宇文", "长孙", "司徒", "司空", "独孤", "闻人",
    "南宫", "东方", "西门", "端木", "轩辕", "申屠", "百里", "东郭",
    "南门", "第五",
)
STRICT_ATTRIBUTION_ACTION_SUFFIX_RE = re.compile(
    r"(?:转身|起身|拿起|拉开|抬手|站起|坐下|后退|低头|推门|关门|"
    r"放下|走开|递出|接过|皱眉|反问|追问|转|起|拿|拉|抬|站|坐|"
    r"退|低|推|关|放|走|递|接|皱|看|望|听|闻|读|写|停|回|点|摇|"
    r"伸|收|握|扶|抓|拍|开|闭|蹲|跪|趴|躲|追|冲|跑|笑|哭|叹|怒|"
    r"怔|愣|喊|问|答|说|叫|吼|咬|吃|惊|疼|痛|吸|呼|哼|闷|指|抢|"
    r"忙|反|补|又|再|仍|还|已|正|先|后|才|便|就|也|忽|猛|急|慢|"
    r"轻|高|大|小|冷|立|随|沉|默|着|了|过)$"
)
CONTROLLED_ATTRIBUTION_PREFIX_RE = re.compile(
    r"^(?:原子(?:\d+|[零〇一二两三四五六七八九十百千万]+)[^\S\r\n]+|"
    r"(?:随后|接着|这时|此时)[，,][^\S\r\n]*)"
)
SOURCE_QUOTE_RE = re.compile(r"“[^”]*”|「[^」]*」|『[^』]*』")
SEMANTIC_QUOTED_PAYLOAD_RE = re.compile(
    r"“[^”]*(?:”|$)|「[^」]*(?:」|$)|『[^』]*(?:』|$)|"
    r'"[^"\r\n]*(?:"|$)'
)
SEMANTIC_OBJECT_BOUNDARY_RE = re.compile(r"[，。；！？!?\n：:“”‘’「」『』\"]")
SEMANTIC_QUOTE_PAIRS = {"“": "”", "「": "」", "『": "』", '"': '"'}
HUMAN_REGISTRY_EVIDENCE_RE = re.compile(
    rf"^{STRICT_ATTRIBUTION_ACTOR_PATTERN}"
    r"(?:没有说话|未说话|沉默(?:了)?(?:片刻|一下)?|"
    r"闷哼(?:了)?(?:一|两|几)?声?|哼出(?:了)?(?:一|两|几)?声?|"
    r"(?:疼得|痛得|惊得|吓得)(?:发出(?:一|两|几)?声|"
    r"喊(?:了)?(?:一|两|几)?声|叫(?:了)?(?:一|两|几)?声)?|"
    r"痛叫|惊叫|惨叫|尖叫|倒吸(?:了)?一口凉气)$"
)


def _strict_attribution_actor_candidate(value: Any) -> str:
    """Validate the actor captured by a zero-remainder attribution grammar."""

    candidate = normalize_text(value).strip() if isinstance(value, str) else ""
    if not re.fullmatch(r"[\u4e00-\u9fff]{1,4}", candidate):
        return "SOURCE_UNSPECIFIED"
    if len(candidate) == 4 and not candidate.startswith(ATTRIBUTION_COMPOUND_SURNAMES):
        return "SOURCE_UNSPECIFIED"
    if UNKNOWN_VOCAL_SPEAKER_RE.fullmatch(candidate):
        return "SOURCE_UNSPECIFIED"
    if STRICT_ATTRIBUTION_FORBIDDEN_ACTOR_RE.search(candidate):
        return "SOURCE_UNSPECIFIED"
    if SPEAKER_CANDIDATE_GRAMMAR_SUFFIX_RE.search(candidate):
        return "SOURCE_UNSPECIFIED"
    action_suffix = STRICT_ATTRIBUTION_ACTION_SUFFIX_RE.search(candidate)
    if action_suffix and len(candidate[: action_suffix.start()]) >= 2:
        return "SOURCE_UNSPECIFIED"
    return candidate


def _strip_controlled_attribution_prefix(value: str) -> str:
    """Remove only source-structure wrappers, never arbitrary narrative text."""

    fragment = normalize_text(value).strip()
    while fragment:
        previous = fragment
        fragment = CONTROLLED_ATTRIBUTION_PREFIX_RE.sub("", fragment, count=1).strip()
        fragment = AUDIO_DIALOGUE_LABEL_RE.sub("", fragment, count=1).strip()
        if fragment == previous:
            break
    return fragment


def _strict_attribution_actor(value: str, *, post: bool = False) -> str:
    """Return one actor only when a controlled attribution consumes everything."""

    fragment = _strip_controlled_attribution_prefix(value)
    patterns = (SPOKEN_PURE_POST_ATTRIBUTION_RE,) if post else (
        SPOKEN_DIRECT_ATTRIBUTION_RE,
        SPOKEN_VOICE_OWNER_RE,
        SPOKEN_ACTION_ATTRIBUTION_RE,
    )
    for pattern in patterns:
        match = pattern.fullmatch(fragment)
        if match:
            return _strict_attribution_actor_candidate(match.group("speaker"))
    return "SOURCE_UNSPECIFIED"


def _strict_human_registry_actor(value: str) -> str:
    fragment = _strip_controlled_attribution_prefix(value).strip(" \t。！？!?")
    match = HUMAN_REGISTRY_EVIDENCE_RE.fullmatch(fragment)
    if not match:
        return "SOURCE_UNSPECIFIED"
    return _strict_attribution_actor_candidate(match.group("speaker"))


@lru_cache(maxsize=32)
def _source_person_registry(source_text: str) -> frozenset[str]:
    """Register actors proved by one fully consumed human attribution."""

    registry: set[str] = set()
    for span in semantic_sentence_spans(source_text):
        exact = span["exact_text"]
        candidates: set[str] = set()
        for quote in SOURCE_QUOTE_RE.finditer(exact):
            prefix = exact[: quote.start()]
            if _visible_text_carrier_prefix(prefix):
                continue
            candidate = _strict_attribution_actor(prefix)
            if candidate != "SOURCE_UNSPECIFIED":
                candidates.add(candidate)
        if not SOURCE_QUOTE_RE.search(exact):
            post_candidate = _strict_attribution_actor(exact, post=True)
            if post_candidate != "SOURCE_UNSPECIFIED":
                candidates.add(post_candidate)
        unquoted = _strip_quoted_source(exact)
        for clause in re.split(r"[，,。！？!?；;\n]+", unquoted):
            candidate = _strict_human_registry_actor(clause)
            if candidate != "SOURCE_UNSPECIFIED":
                candidates.add(candidate)
        candidates.difference_update(VOCAL_PRONOUNS)
        candidates.difference_update(ALLOWED_ANIMAL_ACTORS)
        if len(candidates) == 1:
            registry.update(candidates)
    return frozenset(registry)


def _local_actor_ledger(source_text: str, fragment: str) -> dict[str, Any]:
    """Return the shared local living-actor ledger for spoken and NONLEX paths."""

    attribution = _strip_quoted_source(fragment)
    registry = _source_person_registry(normalize_text(source_text))
    names = {name for name in registry if name in attribution}
    pronouns = {match.group("actor") for match in LOCAL_PRONOUN_RE.finditer(attribution)}
    animals = {match.group("actor") for match in LOCAL_ANIMAL_RE.finditer(attribution)}
    unknown_living = {
        match.group("actor")
        for match in LOCAL_UNKNOWN_LIVING_RE.finditer(attribution)
        if match.group("actor") not in registry
        and match.group("actor") not in ALLOWED_ANIMAL_ACTORS
    }
    return {
        "registry": registry,
        "names": names,
        "pronouns": pronouns,
        "animals": animals,
        "unknown_living": unknown_living,
    }


def _local_semantic_bounds(
    source_text: str,
    quote_start_cp: int,
    quote_end_cp: int,
    semantic_start_cp: int | None,
    semantic_end_cp: int | None,
) -> tuple[int, int] | None:
    span = semantic_span_containing_quote(source_text, quote_start_cp, quote_end_cp)
    if span is None:
        return None
    expected = (span["start_cp"], span["end_cp"])
    supplied = (semantic_start_cp, semantic_end_cp)
    if all(isinstance(value, int) and not isinstance(value, bool) for value in supplied):
        if supplied != expected:
            return None
    return expected


def infer_spoken_speaker_hint(
    source_text: str,
    quote_start_cp: int,
    quote_end_cp: int,
    *,
    contract_version: str = CONTRACT_VERSION,
) -> str:
    """Infer a conservative read-only speaker hint for current 1.5 quotes.

    The hint is never an authoring lock.  It accepts one explicit named owner
    inside the quote's semantic anchor, or one immediately following pure
    attribution anchor.  Pronouns and competing named people remain unknown.
    """

    if contract_version in READ_ONLY_CONTRACT_VERSIONS:
        return "SOURCE_UNSPECIFIED"
    spans = semantic_sentence_spans(source_text)
    owning = [
        (index, span)
        for index, span in enumerate(spans)
        if span["start_cp"] <= quote_start_cp
        and quote_end_cp <= span["end_cp"]
    ]
    if len(owning) != 1:
        return "SOURCE_UNSPECIFIED"
    anchor_index, anchor = owning[0]
    local_quote_start = quote_start_cp - anchor["start_cp"]
    prefix = anchor["exact_text"][:local_quote_start]
    if _visible_text_carrier_prefix(prefix):
        return "SOURCE_UNSPECIFIED"

    pre_candidate = "SOURCE_UNSPECIFIED"
    parsed_pre = _strict_attribution_actor(prefix)
    if parsed_pre != "SOURCE_UNSPECIFIED":
        if parsed_pre in VOCAL_PRONOUNS:
            return "SOURCE_UNSPECIFIED"
        registry = _source_person_registry(normalize_text(source_text))
        if parsed_pre in ALLOWED_ANIMAL_ACTORS or parsed_pre in registry:
            pre_candidate = parsed_pre

    post_candidate = "SOURCE_UNSPECIFIED"
    if anchor_index + 1 < len(spans):
        following = spans[anchor_index + 1]
        raw_following_start = source_text.find(
            following["exact_text"], quote_end_cp
        )
        between = (
            source_text[quote_end_cp:raw_following_start]
            if raw_following_start >= quote_end_cp
            else source_text[anchor["end_cp"]:following["start_cp"]]
        )
        post_match = None
        if (
            not between.strip()
            and not POST_ATTRIBUTION_PARAGRAPH_BREAK_RE.search(between)
            and not _visible_text_carrier_prefix(prefix)
        ):
            post_match = _strict_attribution_actor(
                following["exact_text"], post=True
            )
        if post_match and post_match != "SOURCE_UNSPECIFIED":
            registry = _source_person_registry(normalize_text(source_text))
            if (
                post_match not in VOCAL_PRONOUNS
                and (
                    post_match in ALLOWED_ANIMAL_ACTORS
                    or post_match in registry
                )
            ):
                post_candidate = post_match
    if (
        pre_candidate != "SOURCE_UNSPECIFIED"
        and post_candidate != "SOURCE_UNSPECIFIED"
        and pre_candidate != post_candidate
    ):
        return "SOURCE_UNSPECIFIED"
    if pre_candidate != "SOURCE_UNSPECIFIED":
        return pre_candidate
    return post_candidate


def _pronoun_gender_conflicts(pronoun: str, name: str, sentence: str) -> bool:
    """Reject an explicit local gender marker that contradicts the pronoun."""

    escaped = re.escape(name)
    male = re.search(
        rf"(?:男(?:人|孩|性|士)|先生|父亲|哥哥|弟弟|丈夫).{{0,4}}{escaped}|"
        rf"{escaped}.{{0,4}}(?:男(?:人|孩|性|士)|先生|父亲|哥哥|弟弟|丈夫)",
        sentence,
    )
    female = re.search(
        rf"(?:女(?:人|孩|性|士)|女士|母亲|姐姐|妹妹|妻子).{{0,4}}{escaped}|"
        rf"{escaped}.{{0,4}}(?:女(?:人|孩|性|士)|女士|母亲|姐姐|妹妹|妻子)",
        sentence,
    )
    return bool((pronoun == "她" and male) or (pronoun == "他" and female))


def _canonicalize_vocal_pronoun(
    candidate: str,
    source_text: str,
    quote_start_cp: int,
    *,
    semantic_start_cp: int | None = None,
    semantic_end_cp: int | None = None,
) -> str:
    """Resolve a direct vocal pronoun from one local or adjacent named owner."""

    if candidate not in VOCAL_PRONOUNS:
        return candidate
    bounds = _local_semantic_bounds(
        source_text,
        quote_start_cp,
        quote_start_cp + 1,
        semantic_start_cp,
        semantic_end_cp,
    )
    if bounds is None:
        return "SOURCE_UNSPECIFIED"
    lower, upper = bounds
    prefix = source_text[lower:quote_start_cp]
    if "\n" in prefix:
        prefix = prefix.rsplit("\n", 1)[-1]
    ledger = _local_actor_ledger(source_text, prefix)
    names = set(ledger["names"])
    evidence_text = prefix
    other_pronouns = set(ledger["pronouns"]) - {candidate}
    if (
        len(names) > 1
        or other_pronouns
        or ledger["animals"]
        or ledger["unknown_living"]
    ):
        return "SOURCE_UNSPECIFIED"
    if not names:
        spans = semantic_sentence_spans(source_text)
        current_indexes = [
            index
            for index, span in enumerate(spans)
            if span["start_cp"] == lower and span["end_cp"] == upper
        ]
        if len(current_indexes) != 1 or current_indexes[0] == 0:
            return "SOURCE_UNSPECIFIED"
        previous = spans[current_indexes[0] - 1]
        gap = source_text[previous["end_cp"]:lower]
        if "\n" in gap:
            return "SOURCE_UNSPECIFIED"
        evidence_text = previous["exact_text"]
        previous_ledger = _local_actor_ledger(source_text, evidence_text)
        names = set(previous_ledger["names"])
        if (
            previous_ledger["pronouns"]
            or previous_ledger["animals"]
            or previous_ledger["unknown_living"]
        ):
            return "SOURCE_UNSPECIFIED"
    if len(names) != 1:
        return "SOURCE_UNSPECIFIED"
    name = next(iter(names))
    if name not in _source_person_registry(normalize_text(source_text)):
        return "SOURCE_UNSPECIFIED"
    if _pronoun_gender_conflicts(candidate, name, evidence_text):
        return "SOURCE_UNSPECIFIED"
    return name


def _canonical_vocal_speaker(
    candidate: str,
    source_text: str,
    quote_start_cp: int,
    *,
    semantic_start_cp: int | None = None,
    semantic_end_cp: int | None = None,
    fragment: str | None = None,
    generic_ambiguous: bool = False,
) -> str:
    if candidate == "SOURCE_UNSPECIFIED":
        return candidate
    if candidate in VOCAL_PRONOUNS:
        return _canonicalize_vocal_pronoun(
            candidate,
            source_text,
            quote_start_cp,
            semantic_start_cp=semantic_start_cp,
            semantic_end_cp=semantic_end_cp,
        )
    bounds = _local_semantic_bounds(
        source_text,
        quote_start_cp,
        quote_start_cp + 1,
        semantic_start_cp,
        semantic_end_cp,
    )
    if bounds is None:
        return "SOURCE_UNSPECIFIED"
    lower, _ = bounds
    attribution = fragment if fragment is not None else source_text[lower:quote_start_cp]
    ledger = _local_actor_ledger(source_text, attribution)
    if candidate in ALLOWED_ANIMAL_ACTORS:
        living = set(ledger["names"]) | set(ledger["animals"]) | {candidate}
        if ledger["pronouns"] or ledger["unknown_living"] or living != {candidate}:
            return "SOURCE_UNSPECIFIED"
        return candidate
    names = set(ledger["names"])
    names.add(candidate)
    if (
        names != {candidate}
        or ledger["pronouns"]
        or ledger["animals"]
        or ledger["unknown_living"]
    ):
        return "SOURCE_UNSPECIFIED"
    if generic_ambiguous and candidate not in ledger["registry"]:
        return "SOURCE_UNSPECIFIED"
    return candidate


def _speaker_tail(match: re.Match[str]) -> str:
    return match.group(0)[match.end("speaker") - match.start():]


def _has_explicit_vocal_candidate(value: Any) -> bool:
    candidate = normalize_text(value).strip() if isinstance(value, str) else ""
    candidate = VOCAL_SPEAKER_WRAPPER_RE.sub("", candidate).strip()
    return bool(re.sub(r"的$", "", candidate).strip())


def _ambiguous_owner_was_rejected(
    source_text: str,
    quote_start_cp: int,
    quote_end_cp: int,
    *,
    semantic_start_cp: int | None = None,
    semantic_end_cp: int | None = None,
) -> bool:
    """Tell classification to fail closed for an explicit non-person emitter."""

    bounds = _local_semantic_bounds(
        source_text,
        quote_start_cp,
        quote_end_cp,
        semantic_start_cp,
        semantic_end_cp,
    )
    if bounds is None:
        return False
    lower, upper = bounds
    before = source_text[lower:quote_start_cp]
    if "\n" in before:
        before = before.rsplit("\n", 1)[-1]
    before_clause = re.split(r"[。！？；;\n，,]", before)[-1]
    after = source_text[quote_end_cp:upper]

    match = VOCAL_SPEAKER_BEFORE_RE.search(before_clause)
    if match:
        if DIRECT_EMISSION_AFTER_SPEAKER_RE.fullmatch(_speaker_tail(match)):
            return bool(
                _has_explicit_vocal_candidate(match.group("speaker"))
                and _normalize_ambiguous_vocal_owner(match.group("speaker"))
                == "SOURCE_UNSPECIFIED"
            )
        # A human-specific predicate such as 闷哼/惊得/倒吸一口凉气 is
        # already stronger evidence than the ambiguous post-quote 一声 tail.
        return False

    for pattern in (VOCAL_SPEAKER_AFTER_DIRECT_RE, VOCAL_SPEAKER_AFTER_ATTRIBUTION_RE):
        match = pattern.search(after)
        if match and match.group(0).rstrip().endswith("发出"):
            return bool(
                _has_explicit_vocal_candidate(match.group("speaker"))
                and _normalize_ambiguous_vocal_owner(match.group("speaker"))
                == "SOURCE_UNSPECIFIED"
            )

    if POST_QUOTE_VOCAL_SUFFIX_RE.search(after):
        match = VOCAL_SPEAKER_BEFORE_EMISSION_QUOTE_RE.search(before_clause)
        if match:
            return bool(
                _has_explicit_vocal_candidate(match.group("speaker"))
                and _normalize_ambiguous_vocal_owner(match.group("speaker"))
                == "SOURCE_UNSPECIFIED"
            )
        match = VOCAL_SPEAKER_BEFORE_BREATH_QUOTE_RE.search(before_clause)
        if match:
            return bool(
                _has_explicit_vocal_candidate(match.group("speaker"))
                and _normalize_vocal_speaker_candidate(match.group("speaker"))
                == "SOURCE_UNSPECIFIED"
            )
        match = VOCAL_SPEAKER_BEFORE_QUOTE_RE.search(before_clause)
        if match:
            return bool(
                _has_explicit_vocal_candidate(match.group("speaker"))
                and _normalize_ambiguous_vocal_owner(match.group("speaker"))
                == "SOURCE_UNSPECIFIED"
            )
    return False


def infer_non_lexical_speaker(
    source_text: str,
    quote_start_cp: int,
    quote_end_cp: int,
    *,
    semantic_start_cp: int | None = None,
    semantic_end_cp: int | None = None,
) -> str:
    """Resolve only a grammatically explicit nearby vocalization owner."""

    bounds = _local_semantic_bounds(
        source_text,
        quote_start_cp,
        quote_end_cp,
        semantic_start_cp,
        semantic_end_cp,
    )
    if bounds is None:
        return "SOURCE_UNSPECIFIED"
    lower, upper = bounds
    before = source_text[lower:quote_start_cp]
    if "\n" in before:
        before = before.rsplit("\n", 1)[-1]
    before_clause = re.split(r"[。！？；;\n，,]", before)[-1]
    match = VOCAL_SPEAKER_BEFORE_RE.search(before_clause)
    if match:
        direct_emission = bool(
            DIRECT_EMISSION_AFTER_SPEAKER_RE.fullmatch(_speaker_tail(match))
        )
        generic_ambiguous = bool(
            "发出" in match.group(0)
            and HUMAN_SPECIFIC_VOCAL_RE.search(match.group(0)) is None
        )
        candidate = (
            _strict_source_speaker_candidate(match.group("speaker"))
        )
        if candidate != "SOURCE_UNSPECIFIED":
            return _canonical_vocal_speaker(
                candidate,
                source_text,
                quote_start_cp,
                semantic_start_cp=semantic_start_cp,
                semantic_end_cp=semantic_end_cp,
                fragment=before,
                generic_ambiguous=generic_ambiguous,
            )
        if direct_emission:
            return "SOURCE_UNSPECIFIED"
    after = source_text[quote_end_cp:upper]
    for pattern in (
        VOCAL_SPEAKER_AFTER_DIRECT_RE,
        VOCAL_SPEAKER_AFTER_ATTRIBUTION_RE,
    ):
        match = pattern.search(after)
        if match:
            direct_emission = match.group(0).rstrip().endswith("发出")
            candidate = _strict_source_speaker_candidate(match.group("speaker"))
            if candidate != "SOURCE_UNSPECIFIED":
                return _canonical_vocal_speaker(
                    candidate,
                    source_text,
                    quote_start_cp,
                    semantic_start_cp=semantic_start_cp,
                    semantic_end_cp=semantic_end_cp,
                    fragment=after,
                    generic_ambiguous=bool(
                        "发出" in match.group(0)
                        and HUMAN_SPECIFIC_VOCAL_RE.search(match.group(0)) is None
                    ),
                )
            if direct_emission:
                return "SOURCE_UNSPECIFIED"
    if POST_QUOTE_VOCAL_ACTION_RE.search(after):
        # Strictly support prose such as `绫花……“噗嗤”笑出声`: the vocal
        # action is explicit after the quote, while its only named owner appears
        # earlier in the same semantic sentence. Competing actors fail closed.
        explicit_subject = PRE_QUOTE_SUPPRESSED_LAUGHTER_SUBJECT_RE.fullmatch(before)
        if explicit_subject:
            candidate = _strict_attribution_actor_candidate(
                explicit_subject.group("speaker")
            )
            if candidate not in VOCAL_PRONOUNS | {"SOURCE_UNSPECIFIED"}:
                return candidate
        ledger = _local_actor_ledger(source_text, before)
        names = set(ledger["names"])
        if (
            len(names) == 1
            and not ledger["pronouns"]
            and not ledger["animals"]
            and not ledger["unknown_living"]
        ):
            candidate = next(iter(names))
            if candidate in ledger["registry"]:
                return candidate
    if POST_QUOTE_VOCAL_SUFFIX_RE.search(after):
        emission_match = VOCAL_SPEAKER_BEFORE_EMISSION_QUOTE_RE.search(before_clause)
        if emission_match:
            # `人物发出“唔”一声` is a valid direct owner pattern, but `发出`
            # itself must never be swallowed into the speaker.  If the captured
            # owner is a known sound-producing object, fail closed here instead
            # of retrying the looser bare-owner pattern below.
            return _canonical_vocal_speaker(
                _strict_source_speaker_candidate(emission_match.group("speaker")),
                source_text,
                quote_start_cp,
                semantic_start_cp=semantic_start_cp,
                semantic_end_cp=semantic_end_cp,
                fragment=before,
                generic_ambiguous=True,
            )
        breath_match = VOCAL_SPEAKER_BEFORE_BREATH_QUOTE_RE.search(before_clause)
        if breath_match:
            return _canonical_vocal_speaker(
                _strict_source_speaker_candidate(breath_match.group("speaker")),
                source_text,
                quote_start_cp,
                semantic_start_cp=semantic_start_cp,
                semantic_end_cp=semantic_end_cp,
                fragment=before,
            )
        match = VOCAL_SPEAKER_BEFORE_QUOTE_RE.search(before_clause)
        if match:
            return _canonical_vocal_speaker(
                _strict_source_speaker_candidate(match.group("speaker")),
                source_text,
                quote_start_cp,
                semantic_start_cp=semantic_start_cp,
                semantic_end_cp=semantic_end_cp,
                fragment=before,
                generic_ambiguous=True,
            )
    if NO_SUBJECT_VOCAL_MANNER_RE.fullmatch(before_clause):
        ledger = _local_actor_ledger(source_text, before)
        names = set(ledger["names"])
        if (
            len(names) == 1
            and not ledger["pronouns"]
            and not ledger["animals"]
            and not ledger["unknown_living"]
        ):
            candidate = next(iter(names))
            if candidate in ledger["registry"]:
                return candidate
    return "SOURCE_UNSPECIFIED"


def derive_quote_classification_hints(
    source_text: str,
    quote_start_cp: int,
    quote_end_cp: int,
    quote_text: str,
    *,
    contract_version: str = CONTRACT_VERSION,
    semantic_start_cp: int | None = None,
    semantic_end_cp: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Return deterministic hints without making the author's final classification."""

    normalized = normalize_text(quote_text).strip()
    frozen_quote_hints = contract_version in READ_ONLY_CONTRACT_VERSIONS
    visible_text_carrier = bool(
        not frozen_quote_hints
        and _quote_has_visible_text_carrier(source_text, quote_start_cp, quote_end_cp)
    )
    before_start = max(0, quote_start_cp - QUOTE_CONTEXT_RADIUS)
    after_end = min(len(source_text), quote_end_cp + QUOTE_CONTEXT_RADIUS)
    before = source_text[before_start:quote_start_cp]
    after = source_text[quote_end_cp:after_end]

    source_before = source_text[:quote_start_cp]
    prior_breaks = list(PARAGRAPH_BREAK_RE.finditer(source_before))
    current_paragraph_start = prior_breaks[-1].end() if prior_breaks else 0
    before_scope = source_text[current_paragraph_start:quote_start_cp]

    source_after = source_text[quote_end_cp:]
    boundary_offsets = [len(source_after)]
    next_break = (
        PARAGRAPH_BREAK_RE.search(source_after)
        if frozen_quote_hints
        else POST_ATTRIBUTION_PARAGRAPH_BREAK_RE.search(source_after)
    )
    if next_break:
        boundary_offsets.append(next_break.start())
    next_quote = source_after.find("“")
    if next_quote >= 0:
        boundary_offsets.append(next_quote)
    ownership_after = source_after[: min(boundary_offsets)]

    before_speech = BEFORE_SPEECH_RE.search(before_scope)
    after_speech = AFTER_SPEECH_RE.search(ownership_after)
    speech_markers = [
        marker
        for marker in (
            before_speech.group(0).strip() if before_speech else None,
            after_speech.group(0).strip() if after_speech else None,
        )
        if marker
    ]
    if visible_text_carrier:
        speech_markers = []
    direct_speech = bool(speech_markers) and not visible_text_carrier

    sfx_compact = re.sub(r"[\s—–－\-!！?？。…~～]+", "", normalized)
    sfx_tokens = SFX_TOKEN_RE.findall(sfx_compact)
    full_sfx = bool(
        sfx_compact
        and sfx_tokens
        and len(sfx_tokens) <= 4
        and "".join(sfx_tokens) == sfx_compact
    )
    prefix_match = SFX_PREFIX_RE.match(normalized)
    prefix_token = prefix_match.group("token") if prefix_match else None
    prefix_remainder = prefix_match.group("remainder").strip() if prefix_match else ""
    substantive_prefix_remainder = len(
        re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", prefix_remainder)
    ) >= 2

    previous_paragraph = ""
    if prior_breaks:
        previous_end = prior_breaks[-1].start()
        previous_prefix = source_text[:previous_end]
        earlier_breaks = list(PARAGRAPH_BREAK_RE.finditer(previous_prefix))
        previous_start = earlier_breaks[-1].end() if earlier_breaks else 0
        previous_paragraph = source_text[previous_start:previous_end]
    previous_quotes = list(re.finditer(r"“([^”]+)”", previous_paragraph))
    previous_question = previous_quotes[-1] if previous_quotes else None
    previous_question_tail = (
        previous_paragraph[previous_question.end() :] if previous_question else ""
    )
    question_attribution = (
        QUESTION_ATTRIBUTION_RE.search(previous_question_tail) if previous_question else None
    )
    question_response = bool(
        prefix_match
        and substantive_prefix_remainder
        and not before_scope.strip()
        and previous_question
        and re.search(r"[？?]\s*$", previous_question.group(1))
        and question_attribution
    )
    if visible_text_carrier:
        question_response = False
    explicit_speech = (direct_speech or question_response) and not visible_text_carrier

    context = before_scope + ownership_after
    thought_markers = [marker for marker in THOUGHT_MARKERS if marker in context]
    emotion_markers = [marker for marker in EMOTION_THOUGHT_MARKERS if marker in context]
    self_or_rhetorical = bool(
        re.search(r"(?:自己|我|咱|难道|怎么|怎么办)", normalized)
        or "？" in normalized
        or "?" in normalized
        or "吗" in normalized
    )
    likely_internal = bool(thought_markers or (emotion_markers and self_or_rhetorical))
    vocal_re = V14_NON_LEXICAL_VOCAL_RE if frozen_quote_hints else NON_LEXICAL_VOCAL_RE
    vocal_context_re = VOCALIZATION_CONTEXT_RE if frozen_quote_hints else V15_VOCALIZATION_CONTEXT_RE
    vocal_context = before + after
    if not frozen_quote_hints:
        # A nearby vocalization on a previous/next sentence must not lend its
        # owner to a standalone quoted token.  Keep 1.4's broad context frozen,
        # but scope 1.5 evidence to the quote's own punctuation-delimited unit.
        semantic_bounds = _local_semantic_bounds(
            source_text,
            quote_start_cp,
            quote_end_cp,
            semantic_start_cp,
            semantic_end_cp,
        )
        if semantic_bounds is None:
            before_vocal_scope = ""
            after_vocal_scope = ""
        else:
            semantic_lower, semantic_upper = semantic_bounds
            before_vocal_scope = source_text[semantic_lower:quote_start_cp]
            after_vocal_scope = source_text[quote_end_cp:semantic_upper]
            if "\n" in before_vocal_scope:
                before_vocal_scope = before_vocal_scope.rsplit("\n", 1)[-1]
            if "\n" in after_vocal_scope:
                after_vocal_scope = after_vocal_scope.split("\n", 1)[0]
        vocal_context = before_vocal_scope + after_vocal_scope
    resolved_vocal_speaker = (
        infer_non_lexical_speaker(
            source_text,
            quote_start_cp,
            quote_end_cp,
            semantic_start_cp=semantic_start_cp,
            semantic_end_cp=semantic_end_cp,
        )
        if not frozen_quote_hints and not visible_text_carrier
        else "SOURCE_UNSPECIFIED"
    )
    explicit_post_quote_vocalization = bool(
        POST_QUOTE_VOCAL_SUFFIX_RE.search(after_vocal_scope)
        and resolved_vocal_speaker != "SOURCE_UNSPECIFIED"
    )
    ambiguous_vocal_owner_rejected = (
        not frozen_quote_hints
        and _ambiguous_owner_was_rejected(
            source_text,
            quote_start_cp,
            quote_end_cp,
            semantic_start_cp=semantic_start_cp,
            semantic_end_cp=semantic_end_cp,
        )
    )
    non_lexical_vocalization = bool(
        not visible_text_carrier
        and
        vocal_re.fullmatch(normalized)
        and (
            vocal_context_re.search(vocal_context)
            or explicit_post_quote_vocalization
        )
        and (
            frozen_quote_hints
            or NON_VOCAL_SOUND_OWNER_RE.search(vocal_context) is None
        )
        and not ambiguous_vocal_owner_rejected
    )
    vocalization_speaker_hint = (
        resolved_vocal_speaker
        if non_lexical_vocalization and not frozen_quote_hints
        else "SOURCE_UNSPECIFIED"
    )

    hints: list[str] = []
    if visible_text_carrier:
        hints.append("LIKELY_QUOTED_TEXT")
    elif non_lexical_vocalization:
        hints.append("LIKELY_NON_LEXICAL_VOCALIZATION")
    elif full_sfx:
        hints.append("LIKELY_SFX")
    elif prefix_match and substantive_prefix_remainder:
        hints.append(
            "SFX_PREFIXED_SPEECH_CANDIDATE"
            if explicit_speech
            else "SFX_PREFIX_AMBIGUOUS"
        )
    if likely_internal:
        hints.append("LIKELY_INTERNAL_THOUGHT")
    if explicit_speech:
        hints.append(
            "EXPLICIT_SPEECH_EVIDENCE"
            if direct_speech
            else "QUESTION_RESPONSE_EVIDENCE"
        )
    if not hints:
        hints.append("NO_STRONG_CLASSIFICATION_HINT")
    evidence = {
        "before_start_cp": before_start,
        "after_end_cp": after_end,
        "before": before,
        "after": after,
        "speech_markers": speech_markers,
        "explicit_speech_evidence": explicit_speech,
        "direct_speech_evidence": direct_speech,
        "question_response_evidence": question_response,
        "question_response_marker": (
            question_attribution.group(0).strip() if question_attribution else None
        ),
        "ownership_after": ownership_after,
        "ownership_after_end_cp": quote_end_cp + len(ownership_after),
        "thought_markers": thought_markers,
        "emotion_thought_markers": emotion_markers,
        "sfx_full_match": full_sfx,
        "sfx_prefix_token": prefix_token,
        "sfx_prefix_remainder": prefix_remainder,
        "non_lexical_vocalization_evidence": non_lexical_vocalization,
    }
    if not frozen_quote_hints:
        evidence["visible_text_carrier_evidence"] = visible_text_carrier
        evidence["vocalization_speaker_hint"] = vocalization_speaker_hint
    return hints, evidence


def spoken_quote_conflicts(item: dict[str, Any]) -> list[str]:
    hints = item.get("classification_hints") if isinstance(item.get("classification_hints"), list) else []
    evidence = item.get("context_evidence") if isinstance(item.get("context_evidence"), dict) else {}
    if evidence.get("explicit_speech_evidence") is True:
        return []
    conflicts: list[str] = []
    if "LIKELY_SFX" in hints:
        conflicts.append("LIKELY_SFX_WITHOUT_SPEECH_EVIDENCE")
    if "SFX_PREFIX_AMBIGUOUS" in hints:
        conflicts.append("SFX_PREFIX_WITHOUT_SPEECH_EVIDENCE")
    if "LIKELY_INTERNAL_THOUGHT" in hints:
        conflicts.append("LIKELY_INTERNAL_THOUGHT_WITHOUT_SPEECH_EVIDENCE")
    if "LIKELY_QUOTED_TEXT" in hints:
        conflicts.append("VISIBLE_TEXT_CARRIER_IS_NOT_LIVE_SPEECH")
    if "LIKELY_NON_LEXICAL_VOCALIZATION" in hints:
        conflicts.append("NON_LEXICAL_VOCALIZATION_IS_NOT_LEXICAL_DIALOGUE")
    return conflicts


def normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in value.items()}
    return value


def canonical_json_bytes(value: Any) -> bytes:
    normalized = normalize_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()


def _semantic_source_text(data: dict[str, Any]) -> str:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    if isinstance(source.get("normalized_text"), str):
        return normalize_text(source["normalized_text"])
    return normalize_text(
        "".join(
            item.get("text", "")
            for item in data.get("source_atoms", [])
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    )


def _semantic_atom_for_cp(data: dict[str, Any], cp: int) -> str | None:
    for atom in data.get("source_atoms", []):
        if not isinstance(atom, dict):
            continue
        start, end = atom.get("start_cp"), atom.get("end_cp")
        if isinstance(start, int) and isinstance(end, int) and start <= cp < end:
            atom_id = atom.get("atom_id")
            return atom_id if isinstance(atom_id, str) else None
    return None


def _semantic_phrase_is_generic(phrase: str) -> bool:
    compact = re.sub(r"[\s，。；！？、：“”‘’（）()…]+", "", semantic_compare_text(phrase))
    if not compact:
        return True
    return compact in SEMANTIC_CAMERA_GENERIC_TERMS or all(
        term in SEMANTIC_CAMERA_GENERIC_TERMS
        for term in re.split(r"[/+与和]", compact)
        if term
    )


def build_semantic_phrase_ledger(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a conservative first-visible-source ledger from the full source.

    This intentionally covers only mechanically recognizable quoted text,
    serial-marked names, and quantified physical state terms.  It is not a
    general Chinese entity recognizer.
    """

    candidates: list[tuple[int, int, str, str, str | None]] = []
    patterns = (
        (re.compile(r"“(?P<phrase>[^”\n]{2,48})”"), "QUOTED_TEXT"),
        (re.compile(r"「(?P<phrase>[^」\n]{2,48})」"), "QUOTED_TEXT"),
        (
            re.compile(
                r"(?:[一二两三四五六七八九十百千万\d]+)"
                r"(?:道|处|条|块|枚|个|只|张|段|点|层|片|根|扇|圈)"
                r"(?P<phrase>(?:新|旧|陈旧|新增|褪色|断裂|破损|锈蚀|潮湿|"
                r"干涸|空白|缺失|残留|磨损|发暗|完整)?[\u4e00-\u9fff]{0,6}?"
                r"(?:划痕|痕迹|锈斑|色斑|裂纹|裂缝|缺口|污渍|凹槽|孔洞|印记|伤口|红线|封条))"
            ),
            "QUANTIFIED_STATE_TERM",
        ),
        (
            re.compile(
                r"(?<![A-Za-z0-9\u4e00-\u9fff])(?P<phrase>"
                r"(?:第?[一二两三四五六七八九十百千万\d]+号[\u4e00-\u9fff]{1,6}|"
                r"[A-Z0-9]{1,8}-[A-Z0-9]{1,8}))(?![A-Za-z0-9\u4e00-\u9fff])"
            ),
            "SERIAL_NAMED_TERM",
        ),
    )
    atoms = [item for item in data.get("source_atoms", []) if isinstance(item, dict)]
    segments: list[tuple[str, int, str | None]] = []
    for atom in atoms:
        text = atom.get("text")
        start_cp = atom.get("start_cp")
        if isinstance(text, str) and isinstance(start_cp, int):
            atom_id = atom.get("atom_id")
            span_rows = semantic_sentence_spans_v14(text, base_cp=start_cp)
            for span in span_rows:
                exact_text = span.get("exact_text")
                span_start = span.get("start_cp")
                if isinstance(exact_text, str) and isinstance(span_start, int):
                    segments.append(
                        (
                            exact_text,
                            span_start,
                            atom_id if isinstance(atom_id, str) else None,
                        )
                    )
    if not segments:
        segments.append((_semantic_source_text(data), 0, None))

    for source_segment, base_cp, atom_id in segments:
        compare_segment, cp_spans = _semantic_compare_projection(source_segment)
        for pattern, kind in patterns:
            for match in pattern.finditer(compare_segment):
                phrase = semantic_compare_text(match.group("phrase")).strip()
                # Very short quoted Chinese words (e.g. ``保留``) are routinely
                # reused as ordinary directing verbs.  Without a tokenizer or a
                # visible-text carrier lock, treating them as story-specific would
                # create deterministic false positives.  Four code points is the
                # conservative minimum; serial/state patterns have their own rules.
                if (
                    len(phrase) < 2
                    or (kind == "QUOTED_TEXT" and len(phrase) < 4)
                    or _semantic_phrase_is_generic(phrase)
                ):
                    continue
                start_index, end_index = match.start("phrase"), match.end("phrase")
                if start_index >= len(cp_spans) or end_index <= start_index:
                    continue
                original_start = base_cp + cp_spans[start_index][0]
                original_end = base_cp + cp_spans[end_index - 1][1]
                candidates.append(
                    (original_start, original_end, phrase, kind, atom_id)
                )
    first_by_phrase: dict[str, tuple[int, int, str, str | None]] = {}
    for start, end, phrase, kind, atom_id in sorted(
        candidates, key=lambda item: (item[0], item[1], item[2])
    ):
        first_by_phrase.setdefault(phrase, (start, end, kind, atom_id))
    return [
        {
            "phrase": phrase,
            "kind": values[2],
            "first_start_cp": values[0],
            "first_end_cp": values[1],
            "first_source_ref": values[3] or _semantic_atom_for_cp(data, values[0]),
            "phrase_sha256": sha256_text(phrase),
        }
        for phrase, values in sorted(first_by_phrase.items(), key=lambda item: (item[1][0], item[0]))
    ]


def _semantic_actor_candidates(source_text: str) -> list[str]:
    # Character names are admitted only from actor-specific syntax.  Plot
    # verbs such as ``取出`` are intentionally excluded here: otherwise a
    # sentence-initial adverb, hand, or prop can be mistaken for a person and
    # poison every downstream subject lock.  A silent/ambiguous character is
    # therefore left unlocked and routed to REVIEW_REQUIRED.
    source_text = semantic_compare_text(source_text)
    cue_terms = sorted(
        {
            "说", "答", "问", "喊", "叫", "回答", "追问", "抬头", "低头",
            "抬手", "转身", "停步", "后退", "骑着", "盯着", "看向", "望向",
            "蹲到", "俯身", "摇头", "点头", "伸手", "收回", "独自",
        },
        key=len,
        reverse=True,
    )
    cue = "|".join(map(re.escape, cue_terms))
    pattern = re.compile(
        rf"(?:^|[。！？!?；;，,\n])[”’\"'」』》】）)]*\s*(?:年轻的?|年迈的?|老|小)?"
        rf"(?P<actor>[\u4e00-\u9fff]{{2,4}}?)(?=(?:又|先|再|随后|立即|独自|"
        rf"同时|仍|已经|明确|亲自|只|便|也|才|正|没有|未曾|不再|不)?(?:{cue}))"
    )
    result: list[str] = []
    for match in pattern.finditer(source_text):
        actor = match.group("actor")
        if (
            actor in SEMANTIC_ACTOR_STOPWORDS
            or actor.startswith(("把", "将"))
            or actor[0] in "他她它这那其"
            or actor[-1] in "说答问看望把将从用沿拿取拉推按戴移放装插检发抬低停骑进离回"
            or any(actor.startswith(item) or actor.endswith(item) for item in result)
        ):
            continue
        if actor not in result:
            result.append(actor)
    return result


def _semantic_verb_matches(text: str) -> list[tuple[int, int, str, str]]:
    text = semantic_compare_text(text)
    matches: list[tuple[int, int, str, str]] = []
    # Quoted payload can contain ordinary plot verbs (for example ``放回``)
    # that belong to dialogue, not to the narrated action relation.  Reserve
    # those code-point positions while keeping the original offsets intact.
    occupied: set[int] = {
        index
        for quote in SEMANTIC_QUOTED_PAYLOAD_RE.finditer(text)
        for index in range(quote.start(), quote.end())
    }
    aliases = sorted(
        (
            (alias, canonical)
            for canonical, group_aliases in SEMANTIC_PLOT_VERB_GROUPS
            for alias in group_aliases
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias, canonical in aliases:
        for match in re.finditer(re.escape(alias), text):
            if any(index in occupied for index in range(match.start(), match.end())):
                continue
            occupied.update(range(match.start(), match.end()))
            matches.append((match.start(), match.end(), canonical, alias))
    return sorted(matches)


def _semantic_split_outside_quotes(
    text: str,
    delimiters: set[str],
    *,
    keep_delimiters: bool = False,
    split_after: bool = False,
) -> list[str]:
    """Split narration delimiters without opening a quoted dialogue span."""

    parts: list[str] = []
    start = 0
    active_close: str | None = None
    for index, char in enumerate(text):
        if active_close is not None:
            if char == active_close:
                active_close = None
            continue
        if char in SEMANTIC_QUOTE_PAIRS:
            active_close = SEMANTIC_QUOTE_PAIRS[char]
            continue
        if char not in delimiters:
            continue
        end = index + 1 if split_after else index
        if end > start:
            parts.append(text[start:end])
        if keep_delimiters:
            parts.append(char)
        start = index + 1
    if start < len(text):
        parts.append(text[start:])
    return parts


def _semantic_clean_object(raw: str) -> str:
    value = semantic_compare_text(raw).strip(" \t\r\n，。；！？!?、：:‘’“”()（）")
    value = re.split(r"(?:并且|并|随后|然后|同时|而且|但是|但|却|且|再|才)", value, maxsplit=1)[0]
    value = re.split(r"(?:从|在|向|往|到|至|给)", value, maxsplit=1)[0]
    value = re.sub(
        r"^(?:了|过|着|这|那|该|其|一个|一只|一张|一块|一枚|一条|一段|一道|一处|"
        r"两只|两张|两块|两枚|两条|几只|几张|几块|几枚|几条)+",
        "",
        value,
    )
    value = value.strip(" \t\r\n，。；！？!?、：:‘’“”()（）")
    if not (1 < len(value) <= 18) or value in SEMANTIC_GENERIC_OBJECTS:
        return ""
    if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", value) is None:
        return ""
    return value


def _semantic_subject_before(
    text: str, verb_start: int, actor_candidates: list[str]
) -> str | None:
    text = semantic_compare_text(text)
    prefix = text[:verb_start]
    found: list[tuple[int, str]] = []
    for actor in actor_candidates:
        position = prefix.rfind(actor)
        if position >= 0:
            found.append((position, actor))
    if not found:
        return None
    position, actor = max(found)
    # A distant name in a different clause is not a mechanically safe subject.
    if re.search(r"[。！？!?；;\n]", prefix[position + len(actor) :]):
        return None
    return actor


def _semantic_asserted_object(
    text: str,
    verb_start: int,
    verb_end: int,
    actor: str | None,
) -> str:
    text = semantic_compare_text(text)
    prefix = text[:verb_start]
    suffix = text[verb_end:]
    if actor:
        passive = re.search(
            rf"(?P<object>[\u4e00-\u9fffA-Za-z0-9-]{{2,18}})由{re.escape(actor)}"
            rf"[^，。；！？!?\n]{{0,24}}$",
            prefix,
        )
        if passive:
            return _semantic_clean_object(passive.group("object"))
    ba_positions = [prefix.rfind(marker) for marker in ("把", "将")]
    ba_position = max(ba_positions)
    # ``把`` belongs to this predicate only when no earlier plot predicate
    # already consumed it (e.g. ``把盒子推到…且没有触碰铜片``).
    if ba_position >= 0 and not _semantic_verb_matches(prefix[ba_position + 1 :]):
        value = _semantic_clean_object(prefix[ba_position + 1 :])
        if value:
            return value
    # A colon/opening quote hands control to dialogue.  The quote payload must
    # never become part of the object or any derived object alias.
    suffix = SEMANTIC_OBJECT_BOUNDARY_RE.split(suffix, maxsplit=1)[0]
    following_verbs = _semantic_verb_matches(suffix)
    if following_verbs:
        suffix = suffix[: following_verbs[0][0]]
    return _semantic_clean_object(suffix)


def _semantic_asserted_tool(text: str, verb_start: int, actor: str | None) -> str | None:
    """Return only an explicit ``用/使用/借助 + tool`` phrase."""

    text = semantic_compare_text(text)
    prefix = text[:verb_start]
    if actor:
        actor_position = prefix.rfind(actor)
        if actor_position >= 0:
            prefix = prefix[actor_position + len(actor) :]
    positions = [
        (prefix.rfind(marker), marker)
        for marker in ("借助", "使用", "用")
        if prefix.rfind(marker) >= 0
    ]
    if not positions:
        return None
    position, marker = max(positions, key=lambda item: item[0])
    raw = prefix[position + len(marker) :]
    raw = re.split(r"(?:从|在|向|往|把|将)", raw, maxsplit=1)[0]
    tool = _semantic_clean_object(raw)
    return tool or None


def _semantic_is_subsequence(shorter: str, longer: str) -> bool:
    iterator = iter(longer)
    return all(any(char == candidate for candidate in iterator) for char in shorter)


def _semantic_objects_related(left: str, right: str) -> bool:
    left = semantic_compare_text(left)
    right = semantic_compare_text(right)
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 2 and shorter[-1] == longer[-1] and _semantic_is_subsequence(shorter, longer)


def build_high_confidence_action_locks(
    data: dict[str, Any], unit: dict[str, Any], anchors: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Extract only explicit/current-window subject-verb-object relations."""

    if anchors is None:
        scaffold = unit.get("locked_director_scaffold")
        anchors = scaffold.get("semantic_anchors") if isinstance(scaffold, dict) else []
    anchors = anchors if isinstance(anchors, list) else []
    source_text = _semantic_source_text(data)
    actors = _semantic_actor_candidates(source_text)
    anchor_candidates = [item for item in anchors if isinstance(item, dict)]
    atom_map = {
        atom.get("atom_id"): atom
        for atom in data.get("source_atoms", [])
        if isinstance(atom, dict) and isinstance(atom.get("atom_id"), str)
    }
    locks: list[dict[str, Any]] = []
    for source_ref in unit.get("source_refs", []):
        atom = atom_map.get(source_ref)
        if not isinstance(atom, dict) or not isinstance(atom.get("text"), str):
            continue
        for sentence in _semantic_split_outside_quotes(
            semantic_compare_text(atom["text"]), set("。！？!?\n"), split_after=True
        ):
            if not sentence.strip():
                continue
            carried_subject: str | None = None
            sentence_subjects: list[str] = []
            offset = 0
            for clause in _semantic_split_outside_quotes(
                sentence, set("，,；;"), keep_delimiters=True
            ):
                if clause in {"，", ",", "；", ";"}:
                    offset += len(clause)
                    continue
                verb_matches = _semantic_verb_matches(clause)
                if not verb_matches:
                    offset += len(clause)
                    continue
                first_verb = verb_matches[0][0]
                explicit = _semantic_subject_before(clause, first_verb, actors)
                if explicit:
                    carried_subject = explicit
                    if explicit not in sentence_subjects:
                        sentence_subjects.append(explicit)
                subject = explicit or (carried_subject if len(sentence_subjects) <= 1 else None)
                for start, end, canonical, alias in verb_matches:
                    # A later person name may be an object/destination
                    # (``韩策把盒子推到苏禾面前且没有触碰铜片``).  Commas and
                    # semicolons already delimit subject changes above, so the
                    # first explicit clause subject owns every predicate here.
                    local_subject = subject
                    if not local_subject:
                        continue
                    object_text = _semantic_asserted_object(clause, start, end, local_subject)
                    if not object_text:
                        continue
                    polarity = "NEGATED" if SEMANTIC_NEGATION_RE.search(clause[:start]) else "AFFIRMED"
                    tool = _semantic_asserted_tool(clause, start, local_subject)
                    anchor_id = next(
                        (
                            item.get("anchor_id")
                            for item in anchor_candidates
                            if item.get("source_ref") == source_ref
                            and isinstance(item.get("exact_text"), str)
                            and alias in item["exact_text"]
                            and any(char in item["exact_text"] for char in object_text[-2:])
                        ),
                        None,
                    )
                    lock = {
                        "lock_id": f"AL-{unit.get('unit_id', 'UNKNOWN')}-{len(locks) + 1:03d}",
                        "anchor_id": anchor_id,
                        "source_ref": source_ref,
                        "subject": local_subject,
                        "predicate": canonical,
                        "source_verb": alias,
                        "object": object_text,
                        "object_aliases": [],
                        "polarity": polarity,
                        "tool": tool,
                    }
                    locks.append(lock)
                offset += len(clause)
    object_values = [item["object"] for item in locks]
    for lock in locks:
        aliases = [lock["object"]]
        reduced = re.sub(r"^.*的", "", lock["object"])
        if 1 < len(reduced) <= len(lock["object"]):
            aliases.append(reduced)
        aliases.extend(
            candidate
            for candidate in object_values
            if _semantic_objects_related(lock["object"], candidate)
        )
        for length in range(2, min(8, len(lock["object"])) + 1):
            suffix = lock["object"][-length:]
            if source_text.count(suffix) >= 2:
                aliases.append(suffix)
        lock["object_aliases"] = list(dict.fromkeys(aliases))
    return locks


def expected_authoring_claim_slots(
    unit: dict[str, Any], scaffold: dict[str, Any]
) -> list[dict[str, Any]]:
    anchors = scaffold.get("semantic_anchors") if isinstance(scaffold, dict) else []
    slots = [
        {
            "text": anchor.get("exact_text"),
            "relation": "VERBATIM",
            "source_refs": [anchor.get("source_ref")],
        }
        for anchor in anchors
        if isinstance(anchor, dict)
        and isinstance(anchor.get("exact_text"), str)
        and isinstance(anchor.get("source_ref"), str)
    ]
    slots.append(
        {
            "text": "",
            "relation": "DIRECTORIAL_CONTROL",
            "source_refs": list(unit.get("source_refs", [])),
        }
    )
    return slots


def expected_semantic_gate(
    data: dict[str, Any], unit: dict[str, Any], scaffold: dict[str, Any]
) -> dict[str, Any]:
    projection = {
        "gate_version": SEMANTIC_GATE_VERSION,
        "phrase_ledger": build_semantic_phrase_ledger(data),
        "action_locks": build_high_confidence_action_locks(
            data, unit, scaffold.get("semantic_anchors", [])
        ),
        "claim_slots": expected_authoring_claim_slots(unit, scaffold),
    }
    projection["gate_sha256"] = sha256_value(projection)
    return projection


def semantic_overlay_surfaces(overlay: dict[str, Any]) -> list[dict[str, str]]:
    surfaces: list[dict[str, str]] = []

    def add(path: str, value: Any) -> None:
        if isinstance(value, str) and value.strip():
            surfaces.append({"path": path, "text": semantic_compare_text(value)})
        elif isinstance(value, list):
            for index, item in enumerate(value):
                add(f"{path}/{index}", item)
        elif isinstance(value, dict):
            for key, item in value.items():
                add(f"{path}/{key}", item)

    director = overlay.get("director_overlay") if isinstance(overlay.get("director_overlay"), dict) else {}
    for field in ("performance", "camera", "sound"):
        add(f"/director_overlay/{field}", director.get(field))
    shots = director.get("shot_creative") if isinstance(director.get("shot_creative"), list) else []
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        for field in ("purpose", "camera", "action_additions"):
            add(f"/director_overlay/shot_creative/{index}/{field}", shot.get(field))
    prompt = overlay.get("prompt_overlay") if isinstance(overlay.get("prompt_overlay"), dict) else {}
    add("/prompt_overlay/master_prompt_template", prompt.get("master_prompt_template"))
    add("/prompt_overlay/transform_plan", prompt.get("transform_plan"))
    add("/prompt_overlay/neutral_execution_prompt_template", prompt.get("neutral_execution_prompt_template"))
    claims = prompt.get("claims") if isinstance(prompt.get("claims"), list) else []
    for index, claim in enumerate(claims):
        if isinstance(claim, dict) and claim.get("relation") == "DIRECTORIAL_CONTROL":
            add(f"/prompt_overlay/claims/{index}/text", claim.get("text"))
    add("/prompt_overlay/negative_clauses", prompt.get("negative_clauses"))
    quality = overlay.get("quality_overlay") if isinstance(overlay.get("quality_overlay"), dict) else {}
    add("/quality_overlay/scene_title", quality.get("scene_title"))
    add("/quality_overlay/findings", quality.get("findings"))
    return surfaces


def semantic_unit_surfaces(unit: dict[str, Any], unit_path: str) -> list[dict[str, str]]:
    surfaces: list[dict[str, str]] = []

    def add(path: str, value: Any) -> None:
        if isinstance(value, str) and value.strip():
            surfaces.append({"path": path, "text": semantic_compare_text(value)})
        elif isinstance(value, list):
            for index, item in enumerate(value):
                add(f"{path}[{index}]", item)
        elif isinstance(value, dict):
            for key, item in value.items():
                add(f"{path}.{key}", item)

    claims = unit.get("prompt_claims") if isinstance(unit.get("prompt_claims"), list) else []
    traces = (
        unit.get("prompt_source_trace")
        if isinstance(unit.get("prompt_source_trace"), list)
        else []
    )
    trace_relations = {
        item.get("trace_id"): item.get("relation")
        for item in traces
        if isinstance(item, dict) and isinstance(item.get("trace_id"), str)
    }
    for index, claim in enumerate(claims):
        if (
            isinstance(claim, dict)
            and trace_relations.get(claim.get("trace_id")) == "DIRECTORIAL_CONTROL"
        ):
            add(f"{unit_path}.prompt_claims[{index}].text", claim.get("text"))
    add(f"{unit_path}.negative_clauses", unit.get("negative_clauses"))
    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    for field in ("performance", "camera", "sound"):
        add(f"{unit_path}.director_contract.{field}", director.get(field))
    shots = director.get("shot_plan") if isinstance(director.get("shot_plan"), list) else []
    for shot_index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        for field in ("purpose", "camera"):
            add(
                f"{unit_path}.director_contract.shot_plan[{shot_index}].{field}",
                shot.get(field),
            )
        chain = shot.get("action_state_chain") if isinstance(shot.get("action_state_chain"), list) else []
        provenance = shot.get("field_provenance") if isinstance(shot.get("field_provenance"), dict) else {}
        chain_provenance = (
            provenance.get("action_state_chain")
            if isinstance(provenance.get("action_state_chain"), list)
            else []
        )
        for chain_index, value in enumerate(chain):
            item_provenance = (
                chain_provenance[chain_index]
                if chain_index < len(chain_provenance)
                and isinstance(chain_provenance[chain_index], dict)
                else {}
            )
            if item_provenance.get("status") == "PROPOSED_DIRECTOR_INFERENCE":
                add(
                    f"{unit_path}.director_contract.shot_plan[{shot_index}]"
                    f".action_state_chain[{chain_index}]",
                    value,
                )
    bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
    for layer in ("master_prompt", "transform_plan", "neutral_execution_prompt", "provider_prompt"):
        artifact = bundle.get(layer)
        if isinstance(artifact, dict):
            add(f"{unit_path}.prompt_bundle.{layer}.text", artifact.get("text"))
    return surfaces


def _semantic_phrase_findings(
    data: dict[str, Any], unit: dict[str, Any], surfaces: list[dict[str, str]]
) -> list[dict[str, str]]:
    window = unit.get("source_window") if isinstance(unit.get("source_window"), dict) else {}
    end_cp = window.get("end_cp")
    if not isinstance(end_cp, int):
        return []
    findings: list[dict[str, str]] = []
    for record in build_semantic_phrase_ledger(data):
        first_cp = record.get("first_start_cp")
        phrase = record.get("phrase")
        if not isinstance(first_cp, int) or first_cp < end_cp or not isinstance(phrase, str):
            continue
        for surface in surfaces:
            if phrase in surface["text"]:
                findings.append(
                    {
                        "code": "E_SEMANTIC_FUTURE_REVELATION",
                        "message": (
                            f"请修改 {surface['path']}：‘{phrase}’在当前来源窗口尚未首次出现，"
                            "不能提前写入摄影、表演、声音、主张或执行稿。"
                        ),
                        "path": surface["path"],
                    }
                )
    return findings


def _semantic_action_findings(
    data: dict[str, Any],
    unit: dict[str, Any],
    surfaces: list[dict[str, str]],
    action_locks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    source_text = _semantic_source_text(data)
    actors = _semantic_actor_candidates(source_text)
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def emit(code: str, message: str, path: str) -> None:
        key = (code, message, path)
        if key not in seen:
            seen.add(key)
            findings.append({"code": code, "message": message, "path": path})

    all_aliases = [
        alias
        for lock in action_locks
        for alias in lock.get("object_aliases", [])
        if isinstance(alias, str) and alias
    ]

    def same_locked_object(left: str, right: str) -> bool:
        if _semantic_objects_related(left, right):
            return True
        return any(
            _semantic_objects_related(left, alias)
            and _semantic_objects_related(right, alias)
            for alias in all_aliases
        )

    for surface in surfaces:
        path, text = surface["path"], surface["text"]
        scaffold = unit.get("locked_director_scaffold")
        anchors = scaffold.get("semantic_anchors") if isinstance(scaffold, dict) else []
        for anchor in anchors if isinstance(anchors, list) else []:
            exact = anchor.get("exact_text") if isinstance(anchor, dict) else None
            if isinstance(exact, str) and exact:
                text = text.replace(semantic_compare_text(exact), " ")
        for sentence in _semantic_split_outside_quotes(
            text, set("。！？!?\n"), split_after=True
        ):
            if not sentence.strip():
                continue
            relation_rows: list[dict[str, Any]] = []
            carried_subject: str | None = None
            sentence_subjects: list[str] = []
            for clause in _semantic_split_outside_quotes(
                sentence, set("，,；;")
            ):
                verb_matches = _semantic_verb_matches(clause)
                if not verb_matches:
                    continue
                explicit = _semantic_subject_before(clause, verb_matches[0][0], actors)
                if explicit:
                    carried_subject = explicit
                    if explicit not in sentence_subjects:
                        sentence_subjects.append(explicit)
                subject = explicit or (carried_subject if len(sentence_subjects) <= 1 else None)
                for start, end, canonical, alias in verb_matches:
                    object_text = _semantic_asserted_object(clause, start, end, subject)
                    polarity = "NEGATED" if SEMANTIC_NEGATION_RE.search(clause[:start]) else "AFFIRMED"
                    tool = _semantic_asserted_tool(clause, start, subject)
                    matching = [
                        lock
                        for lock in action_locks
                        if lock.get("predicate") == canonical
                        and (
                            any(
                                isinstance(item, str)
                                and (
                                    item in object_text
                                    or object_text in item
                                    or _semantic_objects_related(item, object_text)
                                )
                                for item in lock.get("object_aliases", [])
                            )
                            if object_text
                            else False
                        )
                    ]
                    object_is_current = bool(
                        object_text
                        and any(
                            item in object_text
                            or object_text in item
                            or _semantic_objects_related(item, object_text)
                            for item in all_aliases
                        )
                    )
                    relation_rows.append(
                        {
                            "canonical": canonical,
                            "verb": alias,
                            "subject": subject,
                            "object": object_text,
                            "polarity": polarity,
                            "tool": tool,
                            "matching": matching,
                        }
                    )
                    if not object_is_current:
                        continue
                    if not matching:
                        emit(
                            "E_SEMANTIC_UNSUPPORTED_ACTION",
                            f"请修改 {path}：‘{alias}{object_text}’复述了当前来源物件，"
                            "但当前窗口没有可机械核对的同一动作关系；请删除剧情断言或交由内容复核。",
                            path,
                        )
                        continue
                    if subject is None:
                        emit(
                            "E_SEMANTIC_ACTION_REVIEW_REQUIRED",
                            f"请修改 {path}：‘{alias}{object_text}’没有可唯一确认的执行主体；"
                            "系统不会猜测中文指代，内容必须保持 REVIEW_REQUIRED。",
                            path,
                        )
                        continue
                    subject_matches = [lock for lock in matching if lock.get("subject") == subject]
                    if not subject_matches:
                        expected_subjects = "、".join(
                            dict.fromkeys(str(lock.get("subject")) for lock in matching)
                        )
                        emit(
                            "E_SEMANTIC_ACTION_SUBJECT",
                            f"请修改 {path}：‘{alias}{object_text}’的执行主体写成“{subject}”，"
                            f"当前来源锁定主体为“{expected_subjects}”。",
                            path,
                        )
                        continue
                    if not any(lock.get("polarity") == polarity for lock in subject_matches):
                        emit(
                            "E_SEMANTIC_ACTION_CONTRADICTION",
                            f"请修改 {path}：‘{subject}{alias}{object_text}’的肯定/否定关系与当前来源相反。",
                            path,
                        )
                        continue
                    if tool:
                        source_tools = [
                            lock.get("tool")
                            for lock in subject_matches
                            if isinstance(lock.get("tool"), str) and lock.get("tool")
                        ]
                        if not source_tools or not any(
                            _semantic_objects_related(tool, source_tool)
                            for source_tool in source_tools
                        ):
                            expected_tools = "、".join(source_tools) if source_tools else "来源未锁定工具"
                            emit(
                                "E_SEMANTIC_ACTION_TOOL",
                                f"请修改 {path}：‘{subject}{alias}{object_text}’新增或改写了工具“{tool}”，"
                                f"当前可机械核对的工具为“{expected_tools}”。",
                                path,
                            )
            handling = [row for row in relation_rows if row["canonical"] in SEMANTIC_HANDLING_GROUPS]
            negative_contact = [
                row
                for row in relation_rows
                if row["canonical"] == "CONTACT" and row["polarity"] == "NEGATED"
            ]
            for handled in handling:
                for contact in negative_contact:
                    same_subject = (
                        handled["subject"] is not None
                        and (contact["subject"] or handled["subject"]) == handled["subject"]
                    )
                    if same_subject and same_locked_object(
                        handled["object"], contact["object"]
                    ):
                        emit(
                            "E_SEMANTIC_ACTION_CONTRADICTION",
                            f"请修改 {path}：同一句同时写“{handled['subject']}处理该物件”"
                            "和“该主体不接触该物件”，动作关系自相矛盾。",
                            path,
                        )
    return findings


def semantic_gate_findings(
    data: dict[str, Any],
    unit: dict[str, Any],
    surfaces: list[dict[str, str]],
    action_locks: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    locks = action_locks if action_locks is not None else build_high_confidence_action_locks(data, unit)
    return [
        *_semantic_phrase_findings(data, unit, surfaces),
        *_semantic_action_findings(data, unit, surfaces, locks),
    ]


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def unique_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value) and len(value) == len(set(value))


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def recursive_items(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from recursive_items(item)
    elif isinstance(value, list):
        for item in value:
            yield from recursive_items(item)


class Report:
    def __init__(self) -> None:
        self.errors: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []

    def error(self, code: str, message: str, path: str = "$") -> None:
        self.errors.append({"code": code, "path": path, "message": message})

    def warn(self, code: str, message: str, path: str = "$") -> None:
        self.warnings.append({"code": code, "path": path, "message": message})

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "valid": self.valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "error_codes": sorted({item["code"] for item in self.errors}),
            "errors": self.errors,
            "warnings": self.warnings,
            "production_validation": "NOT_TESTED",
        }


def safe_relative_path(base: Path, relative: str) -> Path | None:
    pure = PurePosixPath(relative.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        return None
    candidate = base.joinpath(*pure.parts).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate


def load_source_text(data: dict[str, Any], base: Path, report: Report) -> str:
    source = data.get("source")
    if not isinstance(source, dict):
        report.error("E_SOURCE_SCHEMA", "source 必须是对象", "$.source")
        return ""
    inline = source.get("normalized_text")
    text_path = source.get("text_path")
    if isinstance(inline, str) and isinstance(text_path, str):
        report.error("E_SOURCE_SCHEMA", "normalized_text 与 text_path 只能选择一种", "$.source")
        return normalize_text(inline)
    if isinstance(inline, str):
        return normalize_text(inline)
    if isinstance(text_path, str):
        resolved = safe_relative_path(base, text_path)
        if resolved is None:
            report.error("E_SOURCE_PATH", "text_path 必须是合同目录内的安全相对路径", "$.source.text_path")
            return ""
        try:
            return normalize_text(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            report.error("E_SOURCE_READ", f"无法读取 UTF-8 来源：{exc}", "$.source.text_path")
            return ""
    if source.get("ledger") == "SOURCE_ATOMS":
        atoms = data.get("source_atoms")
        if not isinstance(atoms, list) or not atoms or not all(
            isinstance(atom, dict) and isinstance(atom.get("text"), str) for atom in atoms
        ):
            report.error("E_SOURCE_SCHEMA", "SOURCE_ATOMS ledger 缺少完整 atom text", "$.source_atoms")
            return ""
        return normalize_text("".join(atom["text"] for atom in atoms))
    report.error("E_SOURCE_SCHEMA", "source 必须提供 normalized_text 或 text_path", "$.source")
    return ""


def expected_global_state(data: dict[str, Any]) -> dict[str, Any]:
    atoms = data.get("source_atoms") if isinstance(data.get("source_atoms"), list) else []
    units = data.get("units") if isinstance(data.get("units"), list) else []
    return {
        "source_classification": [
            {
                "atom_id": atom.get("atom_id"),
                "kind": atom.get("kind"),
                "source_class": atom.get("source_class"),
                "compile_target": atom.get("compile_target"),
                "compile_reason": atom.get("compile_reason"),
                "semantic_tags": atom.get("semantic_tags", []),
            }
            for atom in atoms
            if isinstance(atom, dict)
        ],
        "unit_manifest": [
            {
                "unit_id": unit.get("unit_id"),
                "order": unit.get("order"),
                "source_refs": unit.get("source_refs", []),
            }
            for unit in units
            if isinstance(unit, dict)
        ],
        "project_rules": data.get("project_rules", []),
        "continuity_bible": data.get("continuity_bible", {}),
        "visual_continuity_domains": data.get("visual_continuity_domains", []),
    }


def expected_skeleton_sha256(data: dict[str, Any], unit_ids: list[str]) -> str:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    projection = {
        "source_sha256": source.get("source_sha256"),
        "global_state_sha256": data.get("global_state_sha256"),
        "unit_ids": unit_ids,
    }
    return sha256_value(projection)


def uses_source_window_contract(data: dict[str, Any]) -> bool:
    return data.get("contract_version") in {
        R7_CONTRACT_VERSION, R8_CONTRACT_VERSION, R9_CONTRACT_VERSION,
        V14_CONTRACT_VERSION, CONTRACT_VERSION,
    }


def is_r8_contract(data: dict[str, Any]) -> bool:
    return data.get("contract_version") in {
        R8_CONTRACT_VERSION, R9_CONTRACT_VERSION, V14_CONTRACT_VERSION,
        CONTRACT_VERSION,
    }


def uses_locked_director_scaffold(data_or_version: Any) -> bool:
    version = (
        data_or_version.get("contract_version")
        if isinstance(data_or_version, dict)
        else data_or_version
    )
    return version in LOCKED_SCAFFOLD_CONTRACT_VERSIONS


def is_current_contract(data: dict[str, Any]) -> bool:
    return data.get("contract_version") == CONTRACT_VERSION


def expected_source_window(
    refs: list[str], atom_map: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    if not refs or any(ref not in atom_map for ref in refs):
        return None
    atom_ids = list(atom_map)
    positions = [atom_ids.index(ref) for ref in refs]
    if positions != list(range(positions[0], positions[-1] + 1)):
        return None
    atoms = [atom_map[ref] for ref in refs]
    if not all(
        isinstance(atom.get("start_cp"), int)
        and isinstance(atom.get("end_cp"), int)
        and isinstance(atom.get("text"), str)
        for atom in atoms
    ):
        return None
    return {
        "first_atom_id": refs[0],
        "last_atom_id": refs[-1],
        "atom_count": len(refs),
        "start_cp": atoms[0]["start_cp"],
        "end_cp": atoms[-1]["end_cp"],
        "text_sha256": sha256_text("".join(atom["text"] for atom in atoms)),
    }


def expected_unit_manifest(data: dict[str, Any]) -> list[dict[str, Any]]:
    units = data.get("units") if isinstance(data.get("units"), list) else []
    return [
        {
            "unit_id": unit.get("unit_id"),
            "order": unit.get("order"),
            "source_refs": unit.get("source_refs"),
            "source_window": unit.get("source_window"),
        }
        for unit in units
        if isinstance(unit, dict)
    ]


def expected_feature_matrix(data: dict[str, Any]) -> list[dict[str, Any]]:
    units = data.get("units") if isinstance(data.get("units"), list) else []
    inventory = (
        data.get("source_dialogue_inventory")
        if isinstance(data.get("source_dialogue_inventory"), list)
        else []
    )
    atom_map = {
        atom.get("atom_id"): atom
        for atom in data.get("source_atoms", [])
        if isinstance(atom, dict) and isinstance(atom.get("atom_id"), str)
    }
    matrix: list[dict[str, Any]] = []
    total = len(units)
    request = data.get("selection_request") if isinstance(data.get("selection_request"), dict) else {}
    requested_modes = request.get("target_modes") if isinstance(request.get("target_modes"), dict) else {}
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            continue
        bucket_index = min(2, (index * 3) // total) if total else 0
        director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
        unit_dialogue_ids = set(expected_dialogue_ids_for_unit(unit, inventory))
        unit_dialogues = [
            item
            for item in inventory
            if isinstance(item, dict)
            and item.get("dialogue_id") in unit_dialogue_ids
        ]
        speakers = sorted(
            {
                item.get("speaker_hint")
                for item in unit_dialogues
                if nonempty_string(item.get("speaker_hint"))
                and item.get("speaker_hint") != "SOURCE_UNSPECIFIED"
            }
        )
        unknown_speaker = any(item.get("speaker_hint") == "SOURCE_UNSPECIFIED" for item in unit_dialogues)
        source_text = "".join(
            atom_map.get(ref, {}).get("text", "")
            for ref in unit.get("source_refs", [])
            if isinstance(atom_map.get(ref, {}).get("text"), str)
        )
        action_count = len(ACTION_REACTION_RE.findall(source_text))
        dialogue_turn_count = len(unit_dialogues)
        if dialogue_turn_count >= 4 and (len(speakers) >= 3 or unknown_speaker):
            route_risk = "MULTI_TURN_DIALOGUE_SPLIT_REQUIRED"
        elif action_count >= 3:
            route_risk = "MULTI_ACTION_REACTION_SPLIT_REQUIRED"
        else:
            route_risk = "LOW"
        matrix.append(
            {
                "unit_id": unit.get("unit_id"),
                "order": unit.get("order"),
                "position_bucket": ("OPENING", "MIDDLE", "LATE")[bucket_index],
                "has_verbatim_dialogue": bool(unit_dialogues),
                "dialogue_turn_count": dialogue_turn_count,
                "speaker_count": len(speakers),
                "speaker_count_status": "PARTIAL_OR_UNKNOWN" if unknown_speaker else "KNOWN",
                "action_or_reaction_signal_count": action_count,
                "source_window_atom_count": unit.get("source_window", {}).get("atom_count"),
                "route_risk": route_risk,
                "target_mode": director.get("target_mode", requested_modes.get(unit.get("unit_id"))),
            }
        )
    return matrix


def expected_helper_lock_projection(data: dict[str, Any]) -> dict[str, Any]:
    output = data.get("output_contract") if isinstance(data.get("output_contract"), dict) else {}
    runtime = data.get("runtime_identity") if isinstance(data.get("runtime_identity"), dict) else {}
    projection = {
        "authoring_version": data.get("authoring_version"),
        "contract_version": data.get("contract_version"),
        "engine": data.get("engine"),
        "delivery_mode": data.get("delivery_mode"),
        "source": data.get("source"),
        "source_atoms": data.get("source_atoms"),
        "source_atoms_sha256": data.get("source_atoms_sha256"),
        "source_dialogue_inventory": data.get("source_dialogue_inventory"),
        "source_dialogue_inventory_sha256": data.get("source_dialogue_inventory_sha256"),
        "source_anomalies": data.get("source_anomalies"),
        "source_anomalies_sha256": data.get("source_anomalies_sha256"),
        "units": expected_unit_manifest(data),
        "unit_manifest_sha256": data.get("unit_manifest_sha256"),
        "feature_matrix_sha256": data.get("feature_matrix_sha256"),
        "selection_request": data.get("selection_request"),
        "authoring_guide_sha256": data.get("authoring_guide_sha256"),
        "authoring_workflow": data.get("authoring_workflow"),
        "project_rules": data.get("project_rules"),
        "continuity_bible": data.get("continuity_bible"),
        "visual_continuity_domains": data.get("visual_continuity_domains"),
        "output_contract": {
            "workspace_memory_policy": output.get("workspace_memory_policy"),
            "strict_output_set": output.get("strict_output_set"),
            "exact_relative_output_names": output.get("exact_relative_output_names"),
            "temp_root": output.get("temp_root"),
            "temp_input_names": output.get("temp_input_names"),
        },
    }
    if is_r8_contract(data):
        projection["runtime_identity"] = {
            "identity_version": runtime.get("identity_version"),
            "skill_build_id": runtime.get("skill_build_id"),
            "skill_manifest_sha256": runtime.get("skill_manifest_sha256"),
            "helper_scripts_sha256": runtime.get("helper_scripts_sha256"),
            "python_runtime": runtime.get("python_runtime"),
            "helper_lock_sha256": None,
            "archive_identity_status": runtime.get("archive_identity_status"),
        }
        projection["output_contract"]["commit_mode"] = output.get("commit_mode")
    return projection


SCAFFOLD_TIME_JUMP_RE = re.compile(
    r"(?:\d+\s*(?:秒|分钟|小时|天|周|月|年)后|"
    r"片刻后|稍后|随后|接着|不久后|当天|当晚|夜里|深夜|黎明|天亮前|"
    r"次日|翌日|第二天|数日后|几天后|数周后|几个月后|半年后|一年后|多年后|"
    r"清晨|早晨|中午|傍晚|黄昏)"
)
SCAFFOLD_REACTION_SIGNAL_RE = re.compile(
    r"(?:愣|怔|停住|停下|沉默|回头|抬头|低头|看向|望向|盯|皱眉|"
    r"后退|退开|避开|按住|没有按|未按|问|回答|答道|说道|喊道)"
)


def expected_semantic_anchors(
    unit: dict[str, Any],
    atom_map: dict[str, dict[str, Any]],
    dialogues: list[dict[str, Any]],
    contract_version: str = CONTRACT_VERSION,
) -> list[dict[str, Any]]:
    relevant = [
        item for item in dialogues
        if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
        and set(item.get("source_refs", [])).intersection(unit.get("source_refs", []))
    ]
    anchors: list[dict[str, Any]] = []
    for source_ref in unit.get("source_refs", []):
        atom = atom_map.get(source_ref, {})
        text = atom.get("text", "") if isinstance(atom.get("text"), str) else ""
        span_deriver = (
            semantic_sentence_spans_v14
            if contract_version in READ_ONLY_CONTRACT_VERSIONS
            else semantic_sentence_spans
        )
        for span in span_deriver(text, base_cp=atom.get("start_cp", 0)):
            exact_text = span["exact_text"]
            start_cp = span["start_cp"]
            end_cp = span["end_cp"]
            quote_ids = [
                item["dialogue_id"] for item in relevant
                if item.get("start_cp", end_cp) < end_cp and item.get("end_cp", start_cp) > start_cp
            ]
            role = (
                "TIME_TRANSITION" if SCAFFOLD_TIME_JUMP_RE.search(exact_text)
                else "DIALOGUE_BEAT" if quote_ids
                else "REACTION_BEAT" if SCAFFOLD_REACTION_SIGNAL_RE.search(exact_text)
                else "ACTION_BEAT"
            )
            anchors.append({
                "anchor_id": f"SA-{unit.get('unit_id')}-{len(anchors) + 1:03d}",
                "source_ref": source_ref,
                "start_cp": start_cp,
                "end_cp": end_cp,
                "exact_text": exact_text,
                "text_sha256": sha256_text(exact_text),
                "anchor_role": role,
                "quote_ids": quote_ids,
            })
    return anchors


def expected_dialogue_ids_for_unit(
    unit: dict[str, Any], dialogues: list[dict[str, Any]]
) -> list[str]:
    """Return complete source-dialogue records wholly owned by this Unit."""

    refs = set(unit.get("source_refs", []))
    return [
        item["dialogue_id"]
        for item in dialogues
        if isinstance(item, dict)
        and nonempty_string(item.get("dialogue_id"))
        and isinstance(item.get("source_refs"), list)
        and set(item["source_refs"]).issubset(refs)
    ]


def expected_single_shot_eligibility_v14(
    unit: dict[str, Any], anchors: list[dict[str, Any]], feature: dict[str, Any]
) -> dict[str, Any]:
    reasons: list[str] = []
    time_ids = [
        item["anchor_id"]
        for item in anchors
        if item.get("anchor_role") == "TIME_TRANSITION"
    ]
    if len(unit.get("source_refs", [])) > 3:
        reasons.append("ATOM_COUNT_GT_3")
    if len(anchors) > 4:
        reasons.append("SEMANTIC_ANCHORS_GT_4")
    if time_ids:
        reasons.append("TIME_TRANSITION_PRESENT")
    if feature.get("dialogue_turn_count", 0) >= 4:
        reasons.append("DIALOGUE_TURNS_GE_4")
    if feature.get("speaker_count", 0) >= 3:
        reasons.append("SPEAKER_COUNT_GE_3")
    route_risk = feature.get("route_risk", "LOW")
    if route_risk != "LOW":
        reasons.append(f"ROUTE_RISK_{route_risk}")
    return {
        "decision": "INELIGIBLE" if reasons else "ELIGIBLE",
        "eligible": not reasons,
        "reasons": reasons,
        "atom_count": len(unit.get("source_refs", [])),
        "semantic_anchor_count": len(anchors),
        "dialogue_turn_count": feature.get("dialogue_turn_count", 0),
        "speaker_count": feature.get("speaker_count", 0),
        "time_jump_anchor_ids": time_ids,
    }


def expected_single_shot_eligibility(
    unit: dict[str, Any], anchors: list[dict[str, Any]], feature: dict[str, Any]
) -> dict[str, Any]:
    """Add the 1.5 duration floor without changing the frozen 1.4 decision."""

    result = expected_single_shot_eligibility_v14(unit, anchors, feature)
    reasons = list(result["reasons"])
    if anchors and _estimate_anchor_group_duration_floor_raw(anchors) > 12.0:
        reasons.append("DURATION_FLOOR_GT_12")
    result["reasons"] = reasons
    result["eligible"] = not reasons
    result["decision"] = "INELIGIBLE" if reasons else "ELIGIBLE"
    return result


def expected_sequence_anchor_groups_v14(
    anchors: list[dict[str, Any]], minimum_shots: int
) -> list[list[dict[str, Any]]]:
    if len(anchors) < 2:
        raise ValueError(
            "E_SEQUENCE_SOURCE_WINDOW_THIN: an EDITED_SEQUENCE requires at least "
            "two complete semantic anchors"
        )
    required_group_count = max(2, minimum_shots)
    if required_group_count > len(anchors):
        raise ValueError(
            "E_SEQUENCE_SOURCE_WINDOW_THIN: the locked source has fewer "
            "semantic anchors than the required minimum shot count"
        )
    mandatory_cuts = sorted({
        index
        for index, item in enumerate(anchors)
        if index > 0 and item.get("anchor_role") == "TIME_TRANSITION"
    })
    boundaries = [0, *mandatory_cuts, len(anchors)]
    regions = [
        anchors[left:right]
        for left, right in zip(boundaries, boundaries[1:])
        if left < right
    ]
    # Every shot carries at most three complete semantic anchors.  Start with
    # the density floor for each mandatory-time region, then distribute any
    # additional minimum-shot demand without crossing a time cut.
    region_group_counts = [(len(region) + 2) // 3 for region in regions]
    target_group_count = max(required_group_count, sum(region_group_counts))
    while sum(region_group_counts) < target_group_count:
        eligible = [
            index
            for index, region in enumerate(regions)
            if region_group_counts[index] < len(region)
        ]
        if not eligible:
            break
        # Split the densest remaining region first; stable source order is the
        # final tie-breaker.
        selected = max(
            eligible,
            key=lambda index: (
                (len(regions[index]) + region_group_counts[index] - 1)
                // region_group_counts[index],
                len(regions[index]) - region_group_counts[index],
                -index,
            ),
        )
        region_group_counts[selected] += 1
    if sum(region_group_counts) < target_group_count:
        raise ValueError(
            "E_SEQUENCE_SOURCE_WINDOW_THIN: the locked source cannot form the "
            "required number of complete semantic beats"
        )
    groups: list[list[dict[str, Any]]] = []
    for region, group_count in zip(regions, region_group_counts):
        base_size, larger_group_count = divmod(len(region), group_count)
        cursor = 0
        for group_index in range(group_count):
            group_size = base_size + (1 if group_index < larger_group_count else 0)
            groups.append(region[cursor : cursor + group_size])
            cursor += group_size
    if (
        len(groups) < required_group_count
        or any(not 1 <= len(group) <= 3 for group in groups)
        or [item for group in groups for item in group] != anchors
    ):
        raise RuntimeError("canonical sequence anchor grouping invariant failed")
    return groups


CHINESE_SMALL_NUMERALS = {
    "零": 0, "〇": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
DURATION_NUMBER_CHARS = r"0-9０-９零〇一二两三四五六七八九十百千万点\.．,，"
DURATION_NUMERAL_START_CHARS = r"0-9０-９零〇一二两三四五六七八九十百千万"
DURATION_NUMBER_CONTINUATION_CHARS = r"0-9０-９零〇一二两三四五六七八九十百千万点"
DURATION_NUMBER_PATTERN = (
    r"(?:[0-9０-９]+(?:[\.．,，][0-9０-９]+)?|"
    r"[零〇一二两三四五六七八九十百千万]+(?:点[零〇一二两三四五六七八九]+)?)"
)
DURATION_HORIZONTAL_SPACE = r"[^\S\r\n]*"
DURATION_LIKE_NUMBER_PATTERN = (
    rf"[{DURATION_NUMERAL_START_CHARS}][{DURATION_NUMBER_CHARS}]*"
)
DURATION_LITERAL_ATOM_LIKE_PATTERN = (
    rf"(?:"
    rf"(?:半{DURATION_HORIZONTAL_SPACE}(?:个{DURATION_HORIZONTAL_SPACE})?|"
    rf"{DURATION_LIKE_NUMBER_PATTERN}{DURATION_HORIZONTAL_SPACE}"
    rf"(?:个{DURATION_HORIZONTAL_SPACE})?(?:半{DURATION_HORIZONTAL_SPACE})*)"
    rf"小时(?:{DURATION_HORIZONTAL_SPACE}半*)?|"
    rf"(?:半{DURATION_HORIZONTAL_SPACE}|"
    rf"{DURATION_LIKE_NUMBER_PATTERN}{DURATION_HORIZONTAL_SPACE}"
    rf"(?:(?:个{DURATION_HORIZONTAL_SPACE})?半{DURATION_HORIZONTAL_SPACE})?)"
    rf"刻(?:{DURATION_HORIZONTAL_SPACE}半)?钟|"
    rf"半{DURATION_HORIZONTAL_SPACE}(?:分钟|分)|"
    rf"{DURATION_LIKE_NUMBER_PATTERN}{DURATION_HORIZONTAL_SPACE}"
    rf"(?:(?:(?:个{DURATION_HORIZONTAL_SPACE})?半{DURATION_HORIZONTAL_SPACE})?"
    rf"分钟(?:{DURATION_HORIZONTAL_SPACE}半*)?|"
    rf"分(?:{DURATION_HORIZONTAL_SPACE}半+(?:{DURATION_HORIZONTAL_SPACE}钟)?)?)|"
    rf"半{DURATION_HORIZONTAL_SPACE}秒(?:钟)?|"
    rf"{DURATION_LIKE_NUMBER_PATTERN}{DURATION_HORIZONTAL_SPACE}"
    rf"秒(?:钟)?(?:{DURATION_HORIZONTAL_SPACE}半*)?"
    rf")"
)
DURATION_LITERAL_CANDIDATE_RE = re.compile(
    rf"(?<![{DURATION_NUMBER_CONTINUATION_CHARS}半个])"
    rf"(?P<literal>"
    rf"{DURATION_LITERAL_ATOM_LIKE_PATTERN}"
    rf"(?:{DURATION_HORIZONTAL_SPACE}{DURATION_LITERAL_ATOM_LIKE_PATTERN})*"
    rf"(?:{DURATION_HORIZONTAL_SPACE}"
    rf"(?:[{DURATION_NUMERAL_START_CHARS}半个]"
    rf"[{DURATION_NUMBER_CHARS}半个]*|[分秒刻钟小]+))?"
    r")"
    rf"(?![{DURATION_NUMBER_CONTINUATION_CHARS}半个])"
)
DURATION_HOUR_ATOM_RE = re.compile(
    rf"(?:(?P<bare_half>半)(?:个)?小时|"
    rf"(?P<number>{DURATION_NUMBER_PATTERN})(?:个)?"
    rf"(?P<pre_half>半)?小时(?P<post_half>半)?)"
)
DURATION_QUARTER_ATOM_RE = re.compile(
    rf"(?:(?P<bare_half>半)刻钟|"
    rf"(?P<number>{DURATION_NUMBER_PATTERN})"
    rf"(?:(?:个)?(?P<pre_half>半))?刻(?P<post_half>半)?钟)"
)
DURATION_MINUTE_ATOM_RE = re.compile(
    rf"(?:(?P<bare_half>半)(?:分钟|分)|"
    rf"(?P<number>{DURATION_NUMBER_PATTERN})"
    rf"(?:(?:个(?P<pre_half>半)|(?P<leading_half>半))?分钟"
    rf"(?P<post_half>半)?|"
    rf"分(?P<mid_half>半)(?:钟)?|"
    rf"分))"
)
DURATION_SECOND_ATOM_RE = re.compile(
    rf"(?:(?P<bare_half>半)秒(?:钟)?|"
    rf"(?P<number>{DURATION_NUMBER_PATTERN})秒(?:钟)?(?P<post_half>半)?)"
)
DURATION_CLOCK_LITERAL_RE = re.compile(
    r"(?:[0-9０-９]+|[零〇一二两三四五六七八九十百千万]+)点"
    r"(?:[0-9０-９]+|[零〇一二两三四五六七八九十百千万]+)分"
)
DURATION_TIMECODE_RE = re.compile(
    r"(?<![0-9０-９])(?P<minutes>[0-9０-９]{1,3})[：:]"
    r"(?P<seconds>[0-9０-９]{2})(?![0-9０-９])"
)
DURATION_ACTION_TRIGGER_RE = re.compile(
    r"(?:持续|连续|倒计时|计时|等待|停留|悬停|保持|重复|反复|循环|再来|重做|再做)"
)
DURATION_SEQUENCE_RELATION_RE = re.compile(
    r"(?:先|再|随后|然后|接着|结束后|完成后|之后|才)"
)
DURATION_CONCURRENT_RELATION_RE = re.compile(
    r"(?:同时|同步|一边|并行|共同)"
)
DURATION_EACH_EVENT_PREFIX_RE = re.compile(
    rf"(?:每次|每轮|每遍|各){DURATION_HORIZONTAL_SPACE}"
    rf"(?:(?:持续|连续|倒计时|计时|等待|停留|悬停|保持)"
    rf"{DURATION_HORIZONTAL_SPACE})?$"
)
DURATION_REPEAT_COUNT_RE = re.compile(
    rf"{DURATION_HORIZONTAL_SPACE}"
    rf"(?:(?:重复|连续|总共|共计|共|做){DURATION_HORIZONTAL_SPACE})?"
    rf"(?P<count>{DURATION_NUMBER_PATTERN}){DURATION_HORIZONTAL_SPACE}"
    rf"(?:次|轮|遍){DURATION_HORIZONTAL_SPACE}"
)
DURATION_REPEAT_LIKE_RE = re.compile(
    rf"{DURATION_HORIZONTAL_SPACE}"
    rf"(?:(?:重复|连续|总共|共计|共|做){DURATION_HORIZONTAL_SPACE})?"
    rf"(?P<count>[{DURATION_NUMERAL_START_CHARS}]"
    rf"[{DURATION_NUMBER_CHARS}]*){DURATION_HORIZONTAL_SPACE}"
    rf"(?:次|轮|遍){DURATION_HORIZONTAL_SPACE}"
)
DURATION_COUNT_EACH_RE = re.compile(
    rf"{DURATION_HORIZONTAL_SPACE}(?P<count>{DURATION_NUMBER_PATTERN})"
    rf"{DURATION_HORIZONTAL_SPACE}(?:次|轮|遍){DURATION_HORIZONTAL_SPACE}"
    rf"各{DURATION_HORIZONTAL_SPACE}"
)
DURATION_COUNT_EACH_LIKE_RE = re.compile(
    rf"{DURATION_HORIZONTAL_SPACE}(?P<count>[{DURATION_NUMERAL_START_CHARS}]"
    rf"[{DURATION_NUMBER_CHARS}]*){DURATION_HORIZONTAL_SPACE}"
    rf"(?:次|轮|遍){DURATION_HORIZONTAL_SPACE}各{DURATION_HORIZONTAL_SPACE}"
)
DURATION_MULTIPLY_AFTER_RE = re.compile(
    rf"{DURATION_HORIZONTAL_SPACE}[×xX*]{DURATION_HORIZONTAL_SPACE}"
    rf"(?P<count>{DURATION_NUMBER_PATTERN}){DURATION_HORIZONTAL_SPACE}"
)
DURATION_MULTIPLY_BEFORE_RE = re.compile(
    rf"{DURATION_HORIZONTAL_SPACE}(?P<count>{DURATION_NUMBER_PATTERN})"
    rf"{DURATION_HORIZONTAL_SPACE}[×xX*]{DURATION_HORIZONTAL_SPACE}"
)
DURATION_MULTIPLY_LIKE_RE = re.compile(
    rf"(?:{DURATION_HORIZONTAL_SPACE}[×xX*]{DURATION_HORIZONTAL_SPACE}"
    rf"[{DURATION_NUMBER_CHARS}]+{DURATION_HORIZONTAL_SPACE}|"
    rf"{DURATION_HORIZONTAL_SPACE}[{DURATION_NUMBER_CHARS}]+"
    rf"{DURATION_HORIZONTAL_SPACE}[×xX*]{DURATION_HORIZONTAL_SPACE})"
)
DURATION_REPLAY_COUNT_RE = re.compile(
    rf"{DURATION_HORIZONTAL_SPACE}(?:重复|再来|再做)"
    rf"{DURATION_HORIZONTAL_SPACE}(?P<count>{DURATION_NUMBER_PATTERN})"
    rf"{DURATION_HORIZONTAL_SPACE}遍{DURATION_HORIZONTAL_SPACE}"
)
DURATION_REPLAY_LIKE_RE = re.compile(
    rf"{DURATION_HORIZONTAL_SPACE}(?:重复|再来|再做)"
    rf"{DURATION_HORIZONTAL_SPACE}(?P<count>[{DURATION_NUMERAL_START_CHARS}]"
    rf"[{DURATION_NUMBER_CHARS}]*){DURATION_HORIZONTAL_SPACE}遍"
    rf"{DURATION_HORIZONTAL_SPACE}"
)
DURATION_REPETITION_MARKER_RE = re.compile(
    rf"(?:重复|再来|再做|每(?:次|轮|遍)|总共|共计|共(?!同)|各|"
    rf"(?:{DURATION_NUMBER_PATTERN}|多|几|数|若干)(?:次|轮|遍)|"
    rf"[×*]{DURATION_HORIZONTAL_SPACE}[{DURATION_NUMBER_CHARS}]+|"
    rf"(?<![A-Za-z])[xX]{DURATION_HORIZONTAL_SPACE}[{DURATION_NUMBER_CHARS}]+|"
    rf"[{DURATION_NUMBER_CHARS}]+{DURATION_HORIZONTAL_SPACE}[×*]|"
    rf"[{DURATION_NUMBER_CHARS}]+{DURATION_HORIZONTAL_SPACE}[xX](?![A-Za-z]))"
)
DURATION_ACTION_PROTOCOL_RE = re.compile(
    r"(?:按照|依照|遵照|照着|按)\s*"
    r"[\u201c\u300c\u300e\"](?P<body>[^\u201d\u300d\u300f\"]+)"
    r"[\u201d\u300d\u300f\"]\s*(?:的)?"
    r"(?:节奏|顺序|步骤|流程|动作组合|操作组合|组合)"
)
DURATION_PROTOCOL_ROUND_RE = re.compile(
    rf"^\s*(?:(?:完成|执行|做完|进行){DURATION_HORIZONTAL_SPACE})?"
    rf"(?P<count>{DURATION_NUMBER_PATTERN}){DURATION_HORIZONTAL_SPACE}"
    rf"(?:次|轮|遍)(?:\s|[，,；;。！？!?]|$)"
)
DURATION_ANAPHORIC_REFERENCE_PATTERN = (
    r"(?:同一(?:套)?(?:动作|组合|步骤|流程|节奏|操作)|"
    r"相同(?:的)?(?:动作|组合|步骤|流程|节奏|操作)|"
    r"同样(?:的)?(?:动作|组合|步骤|流程|节奏|操作)|"
    r"(?:上述|前述|该|这(?:一)?)(?:套|组)?(?:动作|组合|步骤|流程|节奏|操作))"
)
DURATION_ANAPHORIC_REPEAT_RE = re.compile(
    rf"(?:随后|然后|接着|再)?{DURATION_HORIZONTAL_SPACE}"
    rf"(?:把|将)?{DURATION_HORIZONTAL_SPACE}"
    rf"(?P<reference>{DURATION_ANAPHORIC_REFERENCE_PATTERN})"
    rf"{DURATION_HORIZONTAL_SPACE}(?:重复|重做|再做|再来|再执行)"
    rf"{DURATION_HORIZONTAL_SPACE}(?P<count>{DURATION_NUMBER_PATTERN})"
    rf"{DURATION_HORIZONTAL_SPACE}(?:次|轮|遍)"
)
DURATION_ANAPHORIC_REFERENCE_RE = re.compile(
    DURATION_ANAPHORIC_REFERENCE_PATTERN
)
DISPLAY_TEXT_CONTEXT_RE = re.compile(
    r"(?:显示|印着|写着|写进|标签|电子牌|屏幕|弹窗|下一步栏|状态文字)"
)
CAMERA_MOTION_TOKEN_RE = re.compile(
    r"(?:推近|后拉|拉远|摇摄|摇镜|横移|跟随|跟拍|环绕|升降|变焦|轨道|切到|转入|拉焦)"
)
ACTION_CLAUSE_SPLIT_RE = re.compile(r"[，,；;。！？!?\n]+")
DURATION_SEQUENTIAL_RE = re.compile(
    rf"(?:秒(?:结束)?后|结束后|(?:然后|随后|接着|再|才)"
    rf"[^。！？!?；;\n]{{0,16}}(?:{SPEECH_VERB_PATTERN}))"
)
DURATION_SIMULTANEOUS_RE = re.compile(
    rf"(?:一边[^。！？!?；;\n]{{0,48}}一边|"
    rf"(?:按住|保持|拿着|握住|扶住|看着|听着|等待|停留)"
    rf"[^。！？!?；;\n]{{0,20}}同时(?:{SPEECH_VERB_PATTERN}))"
)
PURE_DIALOGUE_ATTRIBUTION_RE = re.compile(
    rf"^\s*(?P<speaker>(?:我|你|他|她|其|我们|你们|他们|她们|"
    rf"{PERSON_NAME_PATTERN}|[A-Za-z][A-Za-z0-9_.-]{{0,31}}))"
    rf"(?P<modifier>(?:(?:听完|听罢|闻言|看完|读完)(?:后)?))?"
    rf"(?P<verb>(?:{SPEECH_VERB_PATTERN}))\s*[：:,，]?\s*$"
)
DURATION_PRONOUN_SPEAKERS = {
    "我", "你", "他", "她", "其", "我们", "你们", "他们", "她们",
}
DURATION_COMPOUND_SURNAMES = (
    "欧阳", "司马", "上官", "诸葛", "夏侯", "皇甫", "尉迟", "公孙",
    "慕容", "令狐", "宇文", "长孙", "司徒", "司空", "独孤",
)


def _small_number(value: str) -> float | None:
    """Parse one complete Arabic/Chinese duration numeral, including decimals."""

    normalized_digits: list[str] = []
    for char in value:
        if char in {".", "．", ",", "，"}:
            normalized_digits.append(".")
            continue
        try:
            normalized_digits.append(str(unicodedata.digit(char)))
        except (TypeError, ValueError):
            normalized_digits = []
            break
    if normalized_digits:
        numeric = "".join(normalized_digits)
        if numeric.count(".") <= 1:
            try:
                return float(numeric)
            except ValueError:
                pass
    try:
        return float(value)
    except ValueError:
        pass
    if value == "半":
        return 0.5
    if "点" in value:
        if value.count("点") != 1:
            return None
        integer_text, fractional_text = value.split("点", 1)
        integer = _small_number(integer_text)
        if integer is None or not fractional_text:
            return None
        fractional_digits: list[str] = []
        for char in fractional_text:
            digit = CHINESE_SMALL_NUMERALS.get(char)
            if digit is None:
                return None
            fractional_digits.append(str(digit))
        return integer + float("0." + "".join(fractional_digits))
    if not value or any(
        char not in CHINESE_SMALL_NUMERALS and char not in "十百千万"
        for char in value
    ):
        return None
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in CHINESE_SMALL_NUMERALS:
            number = CHINESE_SMALL_NUMERALS[char]
            continue
        unit = {"十": 10, "百": 100, "千": 1000, "万": 10000}[char]
        if unit == 10000:
            section += number
            total += (section or 1) * unit
            section = 0
            number = 0
        else:
            section += (number or 1) * unit
            number = 0
    return float(total + section + number)


def _duration_is_non_action_measurement(
    text: str, start: int, end: int
) -> bool:
    """Exclude a locally explicit clock/measurement offset from action time.

    Seconds are otherwise accepted without an action trigger because a bare
    ``十秒`` is a useful provider-neutral duration.  A clock that is *fast by*
    ten seconds, however, describes an offset, not ten seconds of observable
    action.  Keep this exception tightly scoped to the literal's own sentence
    and require an offset/error predicate or an explicit non-duration denial.
    """

    hard_marks = ("。", "！", "!", "？", "?", "；", ";", "\n")
    sentence_start = max(text.rfind(mark, 0, start) for mark in hard_marks) + 1
    sentence_end_candidates = [
        position
        for mark in hard_marks
        if (position := text.find(mark, end)) >= 0
    ]
    sentence_end = min(sentence_end_candidates, default=len(text))
    prefix = text[sentence_start:start]
    suffix = text[end:sentence_end]
    local_prefix = re.split(r"[，,：:]", prefix)[-1]
    offset_before = bool(
        re.search(
            r"(?:时差|校时误差|校准误差|时间误差|读数误差|计时误差|偏差|误差|"
            r"(?:钟|表|时钟|腕表|计时器|读数)[^，,；;。！？!?\n]{0,12}"
            r"(?:快|慢|相差|偏快|偏慢))"
            r"(?:了|为|是|约|大约|整整|足足)?\s*[±+\-]?\s*$",
            local_prefix,
        )
        or re.search(r"(?:快|慢|相差|偏快|偏慢)(?:了|为|是)?\s*$", local_prefix)
    )
    error_after = bool(
        re.search(
            r"^(?:\s*[^，,。！？!?；;\n]{0,12}|"
            r"\s*[，,]\s*(?:这|此|该(?:数值|读数)?|其)"
            r"(?:是|属于|为|表示|代表)"
            r"[^，,。！？!?；;\n]{0,24})"
            r"(?:时差|校时误差|校准误差|时间误差|读数误差|计时误差|偏差|误差)",
            suffix,
        )
    )
    denied_duration = bool(
        re.search(
            r"(?:不是|并非|不代表|不表示|不意味着)"
            r"[^。！？!?；;\n]{0,18}"
            r"(?:等待时长|持续时长|动作时长|动作持续时间|持续时间|时长)",
            suffix,
        )
    )
    return offset_before or error_after or denied_duration


def _duration_minute_has_action_context(text: str, start: int, end: int) -> bool:
    """Require action semantics for units easily confused with clocks or offsets."""

    clause_start = max(
        (text.rfind(mark, 0, start) for mark in ("，", ",", "；", ";", "。", "！", "!", "？", "?", "\n")),
        default=-1,
    )
    local_prefix = text[clause_start + 1 : start]
    local_suffix = text[end : end + 12]
    negated_action = re.search(
        r"(?:不代表|不表示|不意味着|并非|不是|没有|并未|未|不)"
        r"[^，,；;。！？!?\n]{0,12}"
        rf"(?:{DURATION_ACTION_TRIGGER_RE.pattern})\s*$",
        local_prefix,
    )
    surrounding = text[:start] + text[end:]
    bare_literal = not re.sub(
        r"[\s，,；;。！？!?：:'\"“”‘’（）()【】]+",
        "",
        surrounding,
    )
    return bool(
        not negated_action
        and not re.search(r"(?:时差|误差)", local_suffix)
        and not re.search(r"(?:时差|误差|快|慢)\s*$", local_prefix)
        and (
            bare_literal
            or DURATION_ACTION_TRIGGER_RE.search(local_prefix)
            or re.search(
                rf"(?:每次|每轮|每遍|各|"
                rf"{DURATION_NUMBER_PATTERN}(?:次|轮|遍)各)\s*$",
                local_prefix,
            )
        )
    )


def _duration_has_local_action_marker(text: str, start: int) -> bool:
    clause_start = max(
        (
            text.rfind(mark, 0, start)
            for mark in ("，", ",", "；", ";", "。", "！", "!", "？", "?", "\n")
        ),
        default=-1,
    )
    local_prefix = text[clause_start + 1 : start]
    return bool(
        DURATION_ACTION_TRIGGER_RE.search(local_prefix)
        or re.search(
            rf"(?:每次|每轮|每遍|各|"
            rf"{DURATION_NUMBER_PATTERN}(?:次|轮|遍)各)\s*$",
            local_prefix,
        )
    )


def _duration_atom_at(
    literal: str, start: int
) -> tuple[int, int, float, str] | None:
    """Parse one complete atom at ``start`` without accepting a partial numeral."""

    for rank, unit, pattern, scale in (
        (4, "hour", DURATION_HOUR_ATOM_RE, 3600.0),
        (3, "quarter", DURATION_QUARTER_ATOM_RE, 15.0 * 60.0),
        (2, "minute", DURATION_MINUTE_ATOM_RE, 60.0),
        (1, "second", DURATION_SECOND_ATOM_RE, 1.0),
    ):
        match = pattern.match(literal, start)
        if not match:
            continue
        if match.group("bare_half"):
            number = 0.5
        else:
            number = _small_number(match.group("number"))
            if number is None:
                return None
            half_markers = sum(
                bool(match.groupdict().get(name))
                for name in (
                    "pre_half", "leading_half", "mid_half", "post_half",
                )
            )
            if half_markers > 1:
                return None
            number += 0.5 * half_markers
        return match.end(), rank, number * scale, unit
    return None


def _parse_duration_literal(literal: str) -> tuple[float, set[str]] | None:
    """Parse a whole ordered composite duration; any unconsumed tail is invalid."""

    compact = re.sub(r"[^\S\r\n]+", "", literal)
    if not compact:
        return None
    cursor = 0
    previous_rank = 5
    total = 0.0
    units: set[str] = set()
    while cursor < len(compact):
        atom = _duration_atom_at(compact, cursor)
        if atom is None:
            return None
        end, rank, value, unit = atom
        if rank >= previous_rank or end <= cursor:
            return None
        total += value
        units.add(unit)
        previous_rank = rank
        cursor = end
    return total, units


def _duration_repeat_segment(segment: str) -> tuple[bool, float | None]:
    """Return (is_repeat_like, count); repeat-like malformed text yields None."""

    replay = DURATION_REPLAY_COUNT_RE.fullmatch(segment)
    if replay:
        count = _small_number(replay.group("count"))
        if count is None or count <= 0:
            return True, None
        # ``重复/再来一遍`` necessarily adds another execution to the
        # original event.  More repeats use the same conservative lower bound.
        return True, count + 1.0
    for pattern in (
        DURATION_COUNT_EACH_RE,
        DURATION_MULTIPLY_AFTER_RE,
        DURATION_MULTIPLY_BEFORE_RE,
        DURATION_REPEAT_COUNT_RE,
    ):
        strict = pattern.fullmatch(segment)
        if not strict:
            continue
        count = _small_number(strict.group("count"))
        if count is None or count <= 0:
            return True, None
        return True, count
    if DURATION_REPEAT_LIKE_RE.fullmatch(segment):
        return True, None
    if DURATION_COUNT_EACH_LIKE_RE.fullmatch(segment):
        return True, None
    if DURATION_MULTIPLY_LIKE_RE.fullmatch(segment):
        return True, None
    if DURATION_REPLAY_LIKE_RE.fullmatch(segment):
        return True, None
    if (
        re.match(r"\s*(?:重复|再来|再做|做|总共|共计|共)", segment)
        and DURATION_REPETITION_MARKER_RE.search(segment)
    ):
        return True, None
    return False, None


def _duration_repetition_multiplier(
    text: str, start: int, end: int
) -> tuple[float, bool, list[tuple[int, int]]]:
    """Resolve one adjacent repeat relation and report its consumed spans."""

    hard_marks = ("。", "！", "!", "？", "?", "；", ";", "\n")
    hard_start = max(text.rfind(mark, 0, start) for mark in hard_marks)
    hard_end_candidates = [
        position
        for mark in hard_marks
        if (position := text.find(mark, end)) >= 0
    ]
    hard_end = min(hard_end_candidates, default=len(text))
    comma_before = max(
        text.rfind("，", hard_start + 1, start),
        text.rfind(",", hard_start + 1, start),
    )
    comma_after_candidates = [
        position
        for mark in ("，", ",")
        if (position := text.find(mark, end, hard_end)) >= 0
    ]
    comma_after = min(comma_after_candidates, default=hard_end)
    segment_start = max(hard_start, comma_before) + 1
    event_prefix = text[segment_start:start]
    event_suffix = text[end:comma_after]
    repeat_segments: list[tuple[str, int, int]] = []
    each = DURATION_EACH_EVENT_PREFIX_RE.search(event_prefix)
    structural_consumed = (
        [(segment_start + each.start(), segment_start + each.end())]
        if each
        else []
    )
    prefix_before_event = event_prefix[: each.start()] if each else re.sub(
        rf"(?:{DURATION_ACTION_TRIGGER_RE.pattern}){DURATION_HORIZONTAL_SPACE}$",
        "",
        event_prefix,
    )
    if prefix_before_event.strip():
        repeat_segments.append(
            (prefix_before_event, segment_start, segment_start + len(prefix_before_event))
        )
    if event_suffix.strip():
        repeat_segments.append((event_suffix, end, comma_after))

    if comma_before >= 0 and not prefix_before_event.strip():
        previous_comma = max(
            text.rfind("，", hard_start + 1, comma_before),
            text.rfind(",", hard_start + 1, comma_before),
        )
        previous_start = max(hard_start, previous_comma) + 1
        repeat_segments.append(
            (text[previous_start:comma_before], previous_start, comma_before)
        )
    if comma_after < hard_end and not event_suffix.strip():
        next_comma_candidates = [
            position
            for mark in ("，", ",")
            if (position := text.find(mark, comma_after + 1, hard_end)) >= 0
        ]
        next_comma = min(next_comma_candidates, default=hard_end)
        repeat_segments.append(
            (text[comma_after + 1 : next_comma], comma_after + 1, next_comma)
        )

    counts: list[float] = []
    consumed: list[tuple[int, int]] = list(structural_consumed)
    malformed = False
    seen_spans: set[tuple[int, int]] = set()
    for segment, segment_lower, segment_upper in repeat_segments:
        if (segment_lower, segment_upper) in seen_spans:
            continue
        seen_spans.add((segment_lower, segment_upper))
        is_repeat, count = _duration_repeat_segment(segment)
        if not is_repeat:
            continue
        if count is None:
            malformed = True
        else:
            counts.append(count)
            consumed.append((segment_lower, segment_upper))
    if malformed or len(counts) > 1:
        return 1.0, True, consumed
    return (counts[0] if counts else 1.0), False, consumed


def _has_unconsumed_duration_repetition_marker(
    text: str,
    events: list[dict[str, Any]],
    consumed: list[tuple[int, int]],
) -> bool:
    """Fail closed when a repeat claim in a duration event was not parsed."""

    for marker in DURATION_REPETITION_MARKER_RE.finditer(text):
        if any(
            lower <= marker.start() and marker.end() <= upper
            for lower, upper in consumed
        ):
            continue
        for event in events:
            boundary_marks = (
                ("。", "！", "!", "？", "?", "；", ";", "\n")
                if event.get("action_context")
                else ("。", "！", "!", "？", "?", "；", ";", "，", ",", "\n")
            )
            lower = max(
                text.rfind(mark, 0, event["start"]) for mark in boundary_marks
            ) + 1
            right_candidates = [
                position
                for mark in boundary_marks
                if (position := text.find(mark, event["end"])) >= 0
            ]
            upper = min(right_candidates, default=len(text))
            if lower <= marker.start() and marker.end() <= upper:
                return True
    return False


def explicit_continuous_seconds(text: str) -> float:
    """Parse complete duration events and combine sequential/concurrent relations."""

    events: list[dict[str, Any]] = []
    consumed_repetition_spans: list[tuple[int, int]] = []
    comparison_text = semantic_compare_text(normalize_text(text))
    for match in DURATION_TIMECODE_RE.finditer(comparison_text):
        if _duration_is_non_action_measurement(
            comparison_text, match.start(), match.end()
        ):
            continue
        if not _duration_has_local_action_marker(comparison_text, match.start()):
            continue
        minutes = _small_number(match.group("minutes"))
        seconds = _small_number(match.group("seconds"))
        if (
            minutes is None
            or seconds is None
            or minutes < 0
            or not 0 <= seconds < 60
        ):
            return float("inf")
        multiplier, malformed_repeat, consumed = _duration_repetition_multiplier(
            comparison_text, match.start(), match.end()
        )
        if malformed_repeat:
            return float("inf")
        consumed_repetition_spans.extend(consumed)
        events.append(
            {
                "start": match.start(),
                "end": match.end(),
                "value": (minutes * 60.0 + seconds) * multiplier,
                "action_context": True,
            }
        )
    for match in DURATION_LITERAL_CANDIDATE_RE.finditer(comparison_text):
        literal = match.group("literal")
        compact_literal = re.sub(r"[^\S\r\n]+", "", literal)
        non_action_measurement = _duration_is_non_action_measurement(
            comparison_text, match.start(), match.end()
        )
        if (
            DURATION_CLOCK_LITERAL_RE.fullmatch(compact_literal)
            and not _duration_has_local_action_marker(comparison_text, match.start())
        ):
            continue
        parsed = _parse_duration_literal(literal)
        if parsed is None:
            # Clock readings and offsets can have the same surface numerals as
            # a malformed duration.  Fail closed only when the surrounding
            # clause actually claims an action duration (or is the bare
            # literal); otherwise leave unrelated story time untouched.
            if not non_action_measurement and _duration_minute_has_action_context(
                comparison_text, match.start(), match.end()
            ):
                return float("inf")
            continue
        if non_action_measurement:
            continue
        value, units = parsed
        local_action_context = _duration_has_local_action_marker(
            comparison_text, match.start()
        )
        if units - {"second"} and not _duration_minute_has_action_context(
            comparison_text, match.start(), match.end()
        ):
            continue
        multiplier, malformed_repeat, consumed = _duration_repetition_multiplier(
            comparison_text, match.start(), match.end()
        )
        if malformed_repeat:
            return float("inf")
        consumed_repetition_spans.extend(consumed)
        events.append(
            {
                "start": match.start(),
                "end": match.end(),
                "value": value * multiplier,
                "action_context": local_action_context,
            }
        )
    if not events:
        return 0.0
    events.sort(key=lambda item: (item["start"], item["end"]))
    if _has_unconsumed_duration_repetition_marker(
        comparison_text, events, consumed_repetition_spans
    ):
        return float("inf")
    concurrent_groups: list[list[float]] = [[events[0]["value"]]]
    for previous, current in zip(events, events[1:]):
        bridge = comparison_text[previous["end"] : current["start"]]
        current_clause_start = max(
            comparison_text.rfind(mark, 0, previous["start"])
            for mark in ("。", "！", "!", "？", "?", "；", ";", "\n")
        )
        leading = comparison_text[current_clause_start + 1 : previous["start"]]
        sequential = bool(DURATION_SEQUENCE_RELATION_RE.search(bridge))
        simultaneous = bool(
            DURATION_CONCURRENT_RELATION_RE.search(bridge)
            or (
                not sequential
                and DURATION_CONCURRENT_RELATION_RE.search(leading)
                and not re.search(r"[。！？!?；;\n]", bridge)
            )
        )
        if simultaneous and not sequential:
            concurrent_groups[-1].append(current["value"])
        else:
            concurrent_groups.append([current["value"]])
    return sum(max(group) for group in concurrent_groups)


def _duration_action_protocol_seconds(text: str) -> float:
    """Return one strictly quoted action protocol's complete cycle duration.

    Ordinary dialogue stays excluded by ``_duration_action_text``.  Only a
    bounded carrier such as ``按“前推四秒、停两秒”的节奏`` opts a quoted
    payload into action timing.  Ambiguous protocol repetition fails closed.
    """

    comparison_text = semantic_compare_text(normalize_text(text))
    matches = list(DURATION_ACTION_PROTOCOL_RE.finditer(comparison_text))
    if not matches:
        return 0.0
    if len(matches) != 1:
        return float("inf")
    match = matches[0]
    cycle_seconds = explicit_continuous_seconds(match.group("body"))
    if not math.isfinite(cycle_seconds) or cycle_seconds <= 0.0:
        return float("inf")
    hard_end_candidates = [
        position
        for mark in ("。", "！", "!", "？", "?", "；", ";", "\n")
        if (position := comparison_text.find(mark, match.end())) >= 0
    ]
    hard_end = min(hard_end_candidates, default=len(comparison_text))
    tail = comparison_text[match.end():hard_end]
    round_match = DURATION_PROTOCOL_ROUND_RE.match(tail)
    if round_match:
        count = _small_number(round_match.group("count"))
        if count is None or count <= 0:
            return float("inf")
        return cycle_seconds * count
    if DURATION_REPETITION_MARKER_RE.search(tail):
        return float("inf")
    return cycle_seconds


def _duration_anaphoric_repeat(
    text: str,
) -> tuple[bool, float | None, tuple[int, int] | None]:
    """Resolve one strict repeat of a previously named action protocol."""

    comparison_text = semantic_compare_text(normalize_text(text))
    matches = list(DURATION_ANAPHORIC_REPEAT_RE.finditer(comparison_text))
    if len(matches) == 1:
        match = matches[0]
        count = _small_number(match.group("count"))
        if count is None or count <= 0:
            return True, None, (match.start(), match.end())
        return True, count, (match.start(), match.end())
    if len(matches) > 1:
        return True, None, None
    if (
        DURATION_ANAPHORIC_REFERENCE_RE.search(comparison_text)
        and DURATION_REPETITION_MARKER_RE.search(comparison_text)
    ):
        return True, None, None
    return False, None, None


def _split_duration_repeat_transition_spans(
    spans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Split a repeat into its own exact span at an available natural comma.

    The split is current-1.5 only and activates solely after a strict timed
    action protocol in the same source text.  No characters are invented,
    removed, or moved; absolute code-point slices remain authoritative.
    """

    result: list[dict[str, Any]] = []
    context_remaining = 0
    for span in spans:
        exact_text = span["exact_text"]
        protocol_seconds = _duration_action_protocol_seconds(exact_text)
        has_protocol = math.isfinite(protocol_seconds) and protocol_seconds > 0.0
        if has_protocol:
            context_remaining = 2
        is_repeat, count, repeat_span = _duration_anaphoric_repeat(exact_text)
        did_split = False
        if is_repeat and count is not None and repeat_span is not None and context_remaining > 0:
            repeat_start = repeat_span[0]
            occupied: set[int] = set()
            active_close: str | None = None
            for index, char in enumerate(exact_text):
                if active_close is not None:
                    occupied.add(index)
                    if char == active_close:
                        active_close = None
                    continue
                if char in SEMANTIC_QUOTE_PAIRS:
                    active_close = SEMANTIC_QUOTE_PAIRS[char]
                    occupied.add(index)
            separators = [
                index
                for index, char in enumerate(exact_text[:repeat_start])
                if char in {"，", ",", "；", ";"} and index not in occupied
            ]
            if separators:
                cut = repeat_start
                left = exact_text[:cut]
                right = exact_text[cut:]
                if (
                    re.search(r"[\u4e00-\u9fffA-Za-z0-9]", left)
                    and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", right)
                ):
                    result.extend(
                        [
                            {
                                "start_cp": span["start_cp"],
                                "end_cp": span["start_cp"] + cut,
                                "exact_text": left,
                            },
                            {
                                "start_cp": span["start_cp"] + cut,
                                "end_cp": span["end_cp"],
                                "exact_text": right,
                            },
                        ]
                    )
                    did_split = True
            context_remaining = 0
        if not did_split:
            result.append(span)
        if has_protocol:
            continue
        if context_remaining > 0:
            context_remaining -= 1
    return result


def _duration_action_text(text: str) -> tuple[str, bool]:
    """Remove quote bodies and identify a speech carrier with no own action.

    A source anchor such as ``顾岚听完说：“……”`` contains a grammatical
    attribution prefix, but the prefix is not another action that must run in
    addition to the complete spoken line.  Only a tightly bounded attribution
    form is removed.  An independently observable action separated by a comma,
    such as ``她转身离开，说：“……”``, deliberately remains chargeable.
    """

    comparison_text = semantic_compare_text(normalize_text(text))
    quote_count = len(re.findall(r"“[^”]*”", comparison_text))
    action_text = re.sub(r"“[^”]*”", "", comparison_text)
    match = PURE_DIALOGUE_ATTRIBUTION_RE.fullmatch(action_text)
    speaker = match.group("speaker") if match else ""
    modifier = match.group("modifier") if match else ""
    ascii_label = bool(
        modifier
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,31}", speaker)
    )
    bounded_chinese_name = bool(
        modifier
        and re.fullmatch(PERSON_NAME_PATTERN, speaker)
        and (
            len(speaker) == 2
            or (
                len(speaker) == 3
                and speaker.startswith(DURATION_COMPOUND_SURNAMES)
            )
        )
    )
    pure_attribution = bool(
        match
        and quote_count == 1
        and (
            speaker in DURATION_PRONOUN_SPEAKERS
            or ascii_label
            or bounded_chinese_name
        )
        and explicit_continuous_seconds(action_text) == 0.0
    )
    return action_text, pure_attribution


def _duration_voice_is_explicitly_simultaneous(action_text: str) -> bool:
    """Accept only a local action/voice binding, with sequence taking priority."""

    comparison_text = semantic_compare_text(action_text)
    if DURATION_SEQUENTIAL_RE.search(comparison_text):
        return False
    return bool(DURATION_SIMULTANEOUS_RE.search(comparison_text))


def _estimate_anchor_duration_floor_raw(anchor: dict[str, Any]) -> float:
    """Return the unrounded source-only floor used by all 1.5 hard gates."""

    text = semantic_compare_text(normalize_text(anchor.get("exact_text", "")))
    # Quote reading time is accounted for separately below.  Remove quoted
    # bodies before estimating visible action so the preparation floor matches
    # the final execution compiler's action-plus-quote arithmetic instead of
    # either double-counting quote characters or taking an unsafe max().
    action_text, pure_attribution = _duration_action_text(text)
    semantic_chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", action_text))
    clauses = [
        item for item in ACTION_CLAUSE_SPLIT_RE.split(action_text) if item.strip()
    ]
    action_signals = len(ACTION_REACTION_RE.findall(action_text))
    if pure_attribution:
        action_floor = 0.0
    elif semantic_chars:
        action_floor = max(
            1.2,
            0.55 * max(1, len(clauses))
            + 0.35 * action_signals
            + semantic_chars / 28.0,
        )
    else:
        action_floor = 0.0
    quote_floor = 0.0
    protocol_body_ranges = [
        (match.start("body"), match.end("body"))
        for match in DURATION_ACTION_PROTOCOL_RE.finditer(text)
    ]
    for quote_match in re.finditer(r"“([^”]+)”", text):
        if any(
            lower <= quote_match.start(1) and quote_match.end(1) <= upper
            for lower, upper in protocol_body_ranges
        ):
            continue
        quote = quote_match.group(1)
        quote_chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", quote))
        if quote_chars:
            rate = (
                4.2
                if pure_attribution
                else 5.0 if DISPLAY_TEXT_CONTEXT_RE.search(text) else 4.2
            )
            quote_floor += (0.45 if pure_attribution else 0.6) + quote_chars / rate
    explicit_floor = max(
        explicit_continuous_seconds(action_text),
        _duration_action_protocol_seconds(text),
    )
    action_component = max(action_floor, explicit_floor)
    if quote_floor:
        if _duration_voice_is_explicitly_simultaneous(action_text):
            duration = max(action_component, quote_floor)
        else:
            duration = action_component + quote_floor
        return max(duration, 2.0) if pure_attribution else duration
    return action_component


def estimate_anchor_duration_floor(anchor: dict[str, Any]) -> float:
    """Return the two-decimal display floor; gates use the raw helper."""

    return round(_estimate_anchor_duration_floor_raw(anchor), 2)


def _project_anchor_duration_floors_raw(
    anchors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project ordered floors, carrying one strict protocol into its repeat."""

    projection: list[dict[str, Any]] = []
    context_seconds: float | None = None
    context_source_ref: str | None = None
    context_remaining = 0
    for anchor in anchors:
        text = semantic_compare_text(normalize_text(anchor.get("exact_text", "")))
        base_floor = _estimate_anchor_duration_floor_raw(anchor)
        protocol_seconds = _duration_action_protocol_seconds(text)
        is_repeat, repeat_count, repeat_span = _duration_anaphoric_repeat(text)
        floor = base_floor
        context_locked = False
        if is_repeat:
            context_locked = True
            source_ref = anchor.get("source_ref")
            if (
                repeat_count is None
                or repeat_span is None
                or context_seconds is None
                or context_remaining <= 0
                or not nonempty_string(source_ref)
                or source_ref != context_source_ref
            ):
                floor = float("inf")
            else:
                inherited = context_seconds * repeat_count
                outside = text[:repeat_span[0]] + text[repeat_span[1]:]
                outside = re.sub(r"[\s，,；;。！？!?：:]", "", outside)
                floor = (
                    max(base_floor, inherited)
                    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", outside)
                    else base_floor + inherited
                )
            context_seconds = None
            context_source_ref = None
            context_remaining = 0
        elif math.isfinite(protocol_seconds) and protocol_seconds > 0.0:
            floor = max(base_floor, protocol_seconds)
            context_locked = True
            context_seconds = protocol_seconds
            context_source_ref = anchor.get("source_ref")
            context_remaining = 2
        elif protocol_seconds == float("inf"):
            floor = float("inf")
            context_locked = True
            context_seconds = None
            context_source_ref = None
            context_remaining = 0
        elif context_remaining > 0:
            if (
                anchor.get("source_ref") != context_source_ref
                or anchor.get("anchor_role") == "TIME_TRANSITION"
            ):
                context_seconds = None
                context_source_ref = None
                context_remaining = 0
            else:
                context_remaining -= 1
        projection.append(
            {
                "floor": floor,
                "context_locked": context_locked,
            }
        )
    return projection


def _estimate_anchor_group_duration_floor_raw(
    group: list[dict[str, Any]],
) -> float:
    return sum(item["floor"] for item in _project_anchor_duration_floors_raw(group))


def estimate_anchor_group_duration_floor(group: list[dict[str, Any]]) -> float:
    return round(_estimate_anchor_group_duration_floor_raw(group), 2)


def expected_sequence_anchor_groups(
    anchors: list[dict[str, Any]], minimum_shots: int
) -> list[list[dict[str, Any]]]:
    """Group 1.5 anchors by time cuts, three-anchor cap, and 12-second floor."""

    if len(anchors) < 2:
        raise ValueError(
            "E_SEQUENCE_SOURCE_WINDOW_THIN: an EDITED_SEQUENCE requires at least "
            "two complete semantic anchors"
        )
    required_group_count = max(2, minimum_shots)
    if required_group_count > len(anchors):
        raise ValueError(
            "E_SEQUENCE_SOURCE_WINDOW_THIN: the locked source has fewer "
            "semantic anchors than the required minimum shot count"
        )
    duration_projection = _project_anchor_duration_floors_raw(anchors)
    duration_by_object = {
        id(anchor): item["floor"]
        for anchor, item in zip(anchors, duration_projection)
    }

    def group_floor(group: list[dict[str, Any]]) -> float:
        return sum(duration_by_object[id(item)] for item in group)

    for anchor in anchors:
        if duration_by_object[id(anchor)] > 12.0:
            raise ValueError(
                "E_SHOT_DURATION_OVERFLOW: one complete semantic anchor exceeds "
                "the 12-second provider-neutral shot ceiling"
            )
    mandatory_cuts = sorted({
        index for index, item in enumerate(anchors)
        if index > 0 and item.get("anchor_role") == "TIME_TRANSITION"
    })
    boundaries = [0, *mandatory_cuts, len(anchors)]
    regions = [
        anchors[left:right]
        for left, right in zip(boundaries, boundaries[1:])
        if left < right
    ]
    groups: list[list[dict[str, Any]]] = []
    for region in regions:
        current: list[dict[str, Any]] = []
        for anchor in region:
            candidate = current + [anchor]
            if current and (
                len(candidate) > 3
                or group_floor(candidate) > 12.0
            ):
                groups.append(current)
                current = [anchor]
            else:
                current = candidate
        if current:
            groups.append(current)
    while len(groups) < required_group_count:
        splittable = [
            (group_floor(group), index)
            for index, group in enumerate(groups)
            if len(group) > 1
        ]
        if not splittable:
            raise ValueError(
                "E_SEQUENCE_SOURCE_WINDOW_THIN: the locked source cannot form the "
                "required number of complete semantic beats"
            )
        _, selected = max(splittable, key=lambda item: (item[0], -item[1]))
        group = groups[selected]
        best_cut = min(
            range(1, len(group)),
            key=lambda cut: abs(
                group_floor(group[:cut])
                - group_floor(group[cut:])
            ),
        )
        groups[selected:selected + 1] = [group[:best_cut], group[best_cut:]]
    if (
        any(not 1 <= len(group) <= 3 for group in groups)
        or any(
            group_floor(group) > 12.0
            for group in groups
        )
        or [item for group in groups for item in group] != anchors
    ):
        raise RuntimeError("canonical 1.5 sequence anchor grouping invariant failed")
    return groups


def expected_locked_director_scaffold(
    target_mode: str,
    anchors: list[dict[str, Any]],
    minimum_shots: int,
    contract_version: str = CONTRACT_VERSION,
) -> dict[str, Any]:
    anchor_ids = [item["anchor_id"] for item in anchors]
    entry_ids, exit_ids = anchor_ids[:1], anchor_ids[-1:]
    continuity_ids = list(dict.fromkeys(entry_ids + exit_ids))
    group_deriver = (
        expected_sequence_anchor_groups_v14
        if contract_version in READ_ONLY_CONTRACT_VERSIONS
        else expected_sequence_anchor_groups
    )
    groups = group_deriver(anchors, minimum_shots) if target_mode == "EDITED_SEQUENCE" else [anchors]
    shots = []
    for serial, group in enumerate(groups, start=1):
        shots.append({
            "shot_id": f"SH{serial:03d}",
            "source_refs": list(dict.fromkeys(item["source_ref"] for item in group)),
            "source_anchor_ids": [item["anchor_id"] for item in group],
            "quote_ids": list(dict.fromkeys(qid for item in group for qid in item["quote_ids"])),
        })
    return {
        "scaffold_version": (
            V14_DIRECTOR_SCAFFOLD_VERSION
            if contract_version in READ_ONLY_CONTRACT_VERSIONS
            else DIRECTOR_SCAFFOLD_VERSION
        ),
        "derivation": "HELPER_DERIVED",
        "target_mode": target_mode,
        "minimum_shots": len(shots) if target_mode == "EDITED_SEQUENCE" else 0,
        "semantic_anchors": anchors,
        "entry_anchor_ids": entry_ids,
        "action_anchor_ids": anchor_ids,
        "exit_anchor_ids": exit_ids,
        "continuity_anchor_ids": continuity_ids,
        "shots": shots,
        "field_provenance": {
            "entry": {"status": "HELPER_DERIVED", "source_anchor_ids": entry_ids},
            "action_state_chain": {"status": "HELPER_DERIVED", "source_anchor_ids": anchor_ids},
            "exit": {"status": "HELPER_DERIVED", "source_anchor_ids": exit_ids},
            "continuity": {"status": "HELPER_DERIVED", "source_anchor_ids": continuity_ids},
            "shots": {"status": "HELPER_DERIVED", "source_anchor_ids": anchor_ids},
        },
    }


def expected_route_findings(
    feature: dict[str, Any], eligibility: dict[str, Any]
) -> list[str]:
    findings: list[str] = []
    risk = feature.get("route_risk", "LOW")
    if risk != "LOW":
        findings.append(f"SPLIT_REQUIRED:{risk}")
    if eligibility.get("eligible") is False:
        findings.append("SPLIT_REQUIRED:SINGLE_SHOT_INELIGIBLE")
    return list(dict.fromkeys(findings))


def expected_target_windows(data: dict[str, Any]) -> list[dict[str, Any]]:
    request = data.get("selection_request") if isinstance(data.get("selection_request"), dict) else {}
    sample_ids = request.get("sample_unit_ids") if isinstance(request.get("sample_unit_ids"), list) else []
    target_ids = request.get("target_ids") if isinstance(request.get("target_ids"), list) else []
    target_modes = request.get("target_modes") if isinstance(request.get("target_modes"), dict) else {}
    route_findings = request.get("route_findings") if isinstance(request.get("route_findings"), dict) else {}
    units = {
        unit.get("unit_id"): unit
        for unit in data.get("units", [])
        if isinstance(unit, dict) and isinstance(unit.get("unit_id"), str)
    }
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    if isinstance(source.get("normalized_text"), str):
        source_text = normalize_text(source["normalized_text"])
    elif source.get("ledger") == "SOURCE_ATOMS":
        source_text = normalize_text(
            "".join(
                atom.get("text", "")
                for atom in data.get("source_atoms", [])
                if isinstance(atom, dict) and isinstance(atom.get("text"), str)
            )
        )
    else:
        source_text = ""
    inventory = data.get("source_dialogue_inventory") if isinstance(data.get("source_dialogue_inventory"), list) else []
    atom_map = {
        atom.get("atom_id"): atom for atom in data.get("source_atoms", [])
        if isinstance(atom, dict) and nonempty_string(atom.get("atom_id"))
    }
    feature_map = {item.get("unit_id"): item for item in expected_feature_matrix(data)}
    result: list[dict[str, Any]] = []
    for index, unit_id in enumerate(sample_ids):
        unit = units.get(unit_id, {})
        window = unit.get("source_window") if isinstance(unit.get("source_window"), dict) else {}
        dialogue_ids = expected_dialogue_ids_for_unit(unit, inventory)
        dialogue_id_set = set(dialogue_ids)
        relevant_quotes = [
            item
            for item in inventory
            if isinstance(item, dict) and item.get("dialogue_id") in dialogue_id_set
        ]
        start, end = window.get("start_cp"), window.get("end_cp")
        excerpt = source_text[start:end] if isinstance(start, int) and isinstance(end, int) else ""
        target_window = {
                "target_id": target_ids[index] if index < len(target_ids) else None,
                "unit_id": unit_id,
                "target_mode": target_modes.get(unit_id),
                "source_window": window,
                "source_excerpt": excerpt,
                "dialogue_slot_ids": dialogue_ids,
                "quote_classification_hints": {
                    item.get("dialogue_id"): {
                        "classification_hints": item.get("classification_hints"),
                        "context_evidence": item.get("context_evidence"),
                    }
                    for item in relevant_quotes
                },
                "route_findings": route_findings.get(unit_id, []),
            }
        if uses_locked_director_scaffold(data):
            contract_version = data.get("contract_version", CONTRACT_VERSION)
            feature = feature_map.get(unit_id, {})
            anchors = expected_semantic_anchors(
                unit, atom_map, inventory, contract_version
            )
            eligibility_deriver = (
                expected_single_shot_eligibility_v14
                if contract_version in READ_ONLY_CONTRACT_VERSIONS
                else expected_single_shot_eligibility
            )
            eligibility = eligibility_deriver(unit, anchors, feature)
            target_window["route_findings"] = expected_route_findings(
                feature, eligibility
            )
            minimum_shots = expected_sequence_minimum_shots(
                excerpt,
                dialogue_turns=len(dialogue_ids),
                atom_count=len(unit.get("source_refs", [])),
            ) if target_modes.get(unit_id) == "EDITED_SEQUENCE" else 0
            scaffold = expected_locked_director_scaffold(
                target_modes.get(unit_id), anchors, minimum_shots, contract_version
            )
            target_window.update({
                "single_shot_eligibility": eligibility,
                "locked_director_scaffold": scaffold,
                "locked_scaffold_sha256": sha256_value(scaffold),
                "fixed_transform_roles": FIXED_TRANSFORM_ROLES,
            })
            if contract_version == CONTRACT_VERSION:
                target_window["semantic_gate"] = expected_semantic_gate(
                    data, unit, scaffold
                )
        result.append(target_window)
    return result


def validation_subject_projection(data: dict[str, Any]) -> dict[str, Any]:
    projection = copy.deepcopy(data)
    projection.pop("validation_result", None)
    summary = projection.get("run_summary")
    if isinstance(summary, dict):
        summary.pop("actual_validation", None)
    return projection


def validate_source(
    data: dict[str, Any], source_text: str, report: Report
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    expected_hash = sha256_text(source_text)
    if source.get("source_sha256") != expected_hash:
        report.error("E_SOURCE_HASH", "source_sha256 与规范化全文不匹配", "$.source.source_sha256")
    if source.get("source_complete") is not True:
        report.error("E_SOURCE_INCOMPLETE", "长内容冻结必须明确 source_complete=true", "$.source.source_complete")

    atoms = data.get("source_atoms")
    if not isinstance(atoms, list) or not atoms:
        report.error("E_SOURCE_ATOMS", "source_atoms 必须是非空数组", "$.source_atoms")
        return {}, set()

    atom_map: dict[str, dict[str, Any]] = {}
    compile_targets: set[str] = set()
    expected_start = 0
    for index, atom in enumerate(atoms):
        path = f"$.source_atoms[{index}]"
        if not isinstance(atom, dict):
            report.error("E_SOURCE_ATOM_SCHEMA", "source atom 必须是对象", path)
            continue
        atom_id = atom.get("atom_id")
        if not isinstance(atom_id, str) or not atom_id:
            report.error("E_SOURCE_ATOM_SCHEMA", "atom_id 必须是非空字符串", f"{path}.atom_id")
            continue
        if atom_id in atom_map:
            report.error("E_SOURCE_ATOM_DUPLICATE", f"重复 atom_id：{atom_id}", f"{path}.atom_id")
            continue
        atom_map[atom_id] = atom
        start = atom.get("start_cp")
        end = atom.get("end_cp")
        text = atom.get("text")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool) or not isinstance(text, str):
            report.error("E_SOURCE_SPAN", "start_cp/end_cp/text 类型不合法", path)
        else:
            normalized_atom = normalize_text(text)
            if uses_source_window_contract(data) and not normalized_atom.strip():
                report.error(
                    "E_SOURCE_BLANK_ATOM",
                    "r5 禁止用空白分隔行伪造可制作 atom；空白必须并入相邻内容 atom",
                    path,
                )
            if start != expected_start or end != start + len(normalized_atom):
                report.error("E_SOURCE_SPAN", "atom span 存在断口、重叠或长度错误", path)
            elif source_text[start:end] != normalized_atom:
                report.error("E_SOURCE_SPAN", "atom text 无法回切冻结全文", path)
            expected_start = end

        kind = atom.get("kind")
        source_class = atom.get("source_class")
        compile_target = atom.get("compile_target")
        coverage_status = atom.get("coverage_status")
        if not isinstance(atom.get("compile_reason"), str) or not atom.get("compile_reason"):
            report.error("E_SOURCE_CLASS", "compile_reason 必须是非空字符串", f"{path}.compile_reason")
        if kind in RENDERABLE_KINDS:
            expected_class, expected_target = "RENDERABLE_NARRATIVE", True
        elif kind in METADATA_KINDS:
            expected_class, expected_target = "NON_RENDERABLE_METADATA", False
        elif kind in CONTROL_KINDS:
            expected_class, expected_target = "OUT_OF_BAND_CONTROL", False
        else:
            expected_class, expected_target = None, None
            report.error("E_SOURCE_CLASS", f"未知或未分类 kind：{kind!r}", f"{path}.kind")
        if source_class != expected_class or compile_target is not expected_target:
            report.error("E_SOURCE_CLASS", "source_class/compile_target 与 kind 冲突", path)
        if compile_target is True:
            compile_targets.add(atom_id)
            if coverage_status not in {"mapped", "authorized_omission", "authorized_rewrite"}:
                report.error("E_RENDER_COVERAGE", "成片来源的 coverage_status 不合法", f"{path}.coverage_status")
        elif compile_target is False and coverage_status != "FILTERED_NON_RUNTIME":
            report.error("E_RUNTIME_FILTER", "非成片来源必须使用 FILTERED_NON_RUNTIME", f"{path}.coverage_status")
        if not isinstance(atom.get("semantic_tags", []), list):
            report.error("E_SOURCE_ATOM_SCHEMA", "semantic_tags 必须是数组", f"{path}.semantic_tags")

    if expected_start != len(source_text):
        report.error("E_INGESTION_COVERAGE", "atom span 未连续覆盖完整冻结全文", "$.source_atoms")
    return atom_map, compile_targets


def validate_r5_source_derivatives(
    data: dict[str, Any], source_text: str, atom_map: dict[str, dict[str, Any]], report: Report
) -> dict[str, dict[str, Any]]:
    if not uses_source_window_contract(data):
        return {}
    if not is_sha256(data.get("authoring_guide_sha256")):
        report.error(
            "E_AUTHORING_GUIDE_BINDING",
            "r7 合同必须绑定自包含 authoring guide 的 sha256",
            "$.authoring_guide_sha256",
        )
    workflow = data.get("authoring_workflow")
    if (
        not isinstance(workflow, dict)
        or workflow.get("mode") != "CHECK_THEN_COMMIT_V1"
        or not all(
            isinstance(workflow.get(key), list)
            and workflow[key]
            and all(nonempty_string(item) for item in workflow[key])
            for key in ("check_argv", "retry_argv", "commit_argv")
        )
        or "--check-overlays" not in workflow.get("check_argv", [])
        or "--check-overlays" not in workflow.get("retry_argv", [])
        or "--check-overlays" in workflow.get("commit_argv", [])
    ):
        report.error(
            "E_AUTHORING_WORKFLOW",
            "r7 合同必须携带精确 check/retry/commit argv，并把检查与提交分离",
            "$.authoring_workflow",
        )
    atoms = data.get("source_atoms")
    if data.get("source_atoms_sha256") != sha256_value(atoms):
        report.error(
            "E_SOURCE_ATOMS_HASH",
            "source_atoms_sha256 与不可变 atom 数组不匹配",
            "$.source_atoms_sha256",
        )
    inventory = data.get("source_dialogue_inventory")
    if not isinstance(inventory, list):
        report.error(
            "E_SOURCE_DIALOGUE_INVENTORY",
            "source_dialogue_inventory 必须是数组",
            "$.source_dialogue_inventory",
        )
        return {}
    if data.get("source_dialogue_inventory_sha256") != sha256_value(inventory):
        report.error(
            "E_SOURCE_DIALOGUE_HASH",
            "source_dialogue_inventory_sha256 与逐字库存不匹配",
            "$.source_dialogue_inventory_sha256",
        )
    anomalies = data.get("source_anomalies")
    if not isinstance(anomalies, list) or data.get("source_anomalies_sha256") != sha256_value(anomalies):
        report.error(
            "E_SOURCE_ANOMALIES",
            "source_anomalies 必须是 helper 锁定且 hash 可复算的数组",
            "$.source_anomalies",
        )
    quote_unbalanced = source_text.count("“") != source_text.count("”")
    quote_anomalies = [
        item
        for item in anomalies or []
        if isinstance(item, dict) and item.get("kind") == "UNBALANCED_CHINESE_DOUBLE_QUOTE"
    ]
    if quote_unbalanced != (len(quote_anomalies) == 1):
        report.error("E_SOURCE_ANOMALIES", "不平衡引号记录与冻结来源不一致", "$.source_anomalies")
    if quote_anomalies and (
        quote_anomalies[0].get("left_count") != source_text.count("“")
        or quote_anomalies[0].get("right_count") != source_text.count("”")
        or quote_anomalies[0].get("policy") != "PRESERVE_AND_REVIEW"
    ):
        report.error("E_SOURCE_ANOMALIES", "自动引号异常的计数或策略不可复算", "$.source_anomalies")
    seen_anomaly_ids: set[str] = set()
    for index, anomaly in enumerate(anomalies or []):
        path = f"$.source_anomalies[{index}]"
        if not isinstance(anomaly, dict):
            report.error("E_SOURCE_ANOMALIES", "source anomaly 必须是结构化对象", path)
            continue
        anomaly_id = anomaly.get("anomaly_id")
        kind = anomaly.get("kind")
        if not nonempty_string(anomaly_id) or anomaly_id in seen_anomaly_ids or not nonempty_string(kind):
            report.error("E_SOURCE_ANOMALIES", "anomaly_id/kind 必须非空且 ID 不重复", path)
            continue
        seen_anomaly_ids.add(anomaly_id)
        if kind == "UNBALANCED_CHINESE_DOUBLE_QUOTE":
            continue
        if anomaly.get("policy") != "PRESERVE_AND_REVIEW":
            report.error("E_SOURCE_ANOMALIES", "用户报告异常必须保留并复核", path)
        evidence_count = 0
        if "text" in anomaly:
            evidence_count += 1
            if not nonempty_string(anomaly.get("text")) or normalize_text(anomaly["text"]) not in source_text:
                report.error("E_SOURCE_ANOMALIES", "异常 text 证据必须逐字存在于冻结来源", path)
        if "variant" in anomaly:
            evidence_count += 1
            if not nonempty_string(anomaly.get("variant")):
                report.error("E_SOURCE_ANOMALIES", "异常 variant 必须非空", path)
        if "span" in anomaly:
            evidence_count += 1
            span = anomaly.get("span")
            if not isinstance(span, dict) or set(span) != {"start_cp", "end_cp", "text_sha256"}:
                report.error("E_SOURCE_ANOMALIES", "异常 span 字段不完整", path)
            else:
                start_cp, end_cp = span.get("start_cp"), span.get("end_cp")
                if (
                    not isinstance(start_cp, int)
                    or isinstance(start_cp, bool)
                    or not isinstance(end_cp, int)
                    or isinstance(end_cp, bool)
                    or not (0 <= start_cp < end_cp <= len(source_text))
                    or span.get("text_sha256") != sha256_text(source_text[start_cp:end_cp])
                ):
                    report.error("E_SOURCE_ANOMALIES", "异常 span 无法精确回切冻结来源", path)
        if evidence_count == 0:
            report.error("E_SOURCE_ANOMALIES", "用户异常不得缺少 text/variant/span 证据", path)
    result: dict[str, dict[str, Any]] = {}
    expected_quotes: list[dict[str, Any]] = []
    ordered_atoms = [atom for atom in data.get("source_atoms", []) if isinstance(atom, dict)]
    inventory_contract_version = data.get("contract_version", CONTRACT_VERSION)
    current_quote_contract = inventory_contract_version not in READ_ONLY_CONTRACT_VERSIONS
    for serial, match in enumerate(re.finditer(r"“([^”]+)”", source_text), start=1):
        expected_atoms = [
            atom
            for atom in ordered_atoms
            if isinstance(atom.get("start_cp"), int)
            and isinstance(atom.get("end_cp"), int)
            and atom["start_cp"] < match.end(1)
            and atom["end_cp"] > match.start(1)
        ]
        expected_refs = [atom.get("atom_id") for atom in expected_atoms]
        semantic_span = (
            semantic_span_containing_quote(source_text, match.start(), match.end())
            if current_quote_contract
            else None
        )
        semantic_start_cp = (
            semantic_span["start_cp"]
            if semantic_span is not None
            else expected_atoms[0].get("start_cp") if expected_atoms else None
        )
        semantic_end_cp = (
            semantic_span["end_cp"]
            if semantic_span is not None
            else expected_atoms[-1].get("end_cp") if expected_atoms else None
        )
        classification_hints, context_evidence = derive_quote_classification_hints(
            source_text,
            match.start(),
            match.end(),
            match.group(1),
            contract_version=inventory_contract_version,
            semantic_start_cp=semantic_start_cp,
            semantic_end_cp=semantic_end_cp,
        )
        expected_quote = {
            "dialogue_id": f"DLG{serial:04d}",
            "text": match.group(1),
            "start_cp": match.start(1),
            "end_cp": match.end(1),
            "source_refs": expected_refs,
            "classification_hints": classification_hints,
            "context_evidence": context_evidence,
        }
        if current_quote_contract:
            speaker_hint = infer_spoken_speaker_hint(
                source_text,
                match.start(),
                match.end(),
                contract_version=inventory_contract_version,
            )
            vocal_speaker = context_evidence.get("vocalization_speaker_hint")
            if "LIKELY_NON_LEXICAL_VOCALIZATION" in classification_hints:
                speaker_hint = (
                    vocal_speaker
                    if isinstance(vocal_speaker, str)
                    and vocal_speaker != "SOURCE_UNSPECIFIED"
                    else "SOURCE_UNSPECIFIED"
                )
            expected_quote["speaker_hint"] = speaker_hint
        expected_quotes.append(expected_quote)
    if len(inventory) != len(expected_quotes):
        report.error(
            "E_SOURCE_QUOTE_COVERAGE",
            "source_dialogue_inventory 必须逐项覆盖全部成对中文引号 span",
            "$.source_dialogue_inventory",
        )
    for index, item in enumerate(inventory):
        path = f"$.source_dialogue_inventory[{index}]"
        if not isinstance(item, dict):
            report.error("E_SOURCE_DIALOGUE_INVENTORY", "dialogue inventory item 必须是对象", path)
            continue
        dialogue_id = item.get("dialogue_id")
        text = item.get("text")
        start = item.get("start_cp")
        end = item.get("end_cp")
        refs = item.get("source_refs")
        if not nonempty_string(dialogue_id) or dialogue_id in result:
            report.error("E_SOURCE_DIALOGUE_INVENTORY", "dialogue_id 缺失或重复", path)
            continue
        result[dialogue_id] = item
        if item.get("source_quote_type") != "UNCLASSIFIED_SOURCE_QUOTE":
            report.error(
                "E_SOURCE_QUOTE_CLASS",
                "helper 库中的成对引号在作者分类前必须保持 UNCLASSIFIED_SOURCE_QUOTE",
                path,
            )
        if not nonempty_string(item.get("speaker")) or not nonempty_string(item.get("speaker_hint")):
            report.error("E_SOURCE_DIALOGUE_INVENTORY", "speaker/speaker_hint 必须非空", path)
        if index < len(expected_quotes):
            expected_quote = expected_quotes[index]
            expected_quote_keys = [
                "dialogue_id",
                "text",
                "start_cp",
                "end_cp",
                "source_refs",
                "classification_hints",
                "context_evidence",
            ]
            if current_quote_contract:
                expected_quote_keys.append("speaker_hint")
            actual_quote = {
                key: item.get(key) for key in expected_quote_keys
            }
            if actual_quote != expected_quote:
                report.error(
                    "E_SOURCE_QUOTE_COVERAGE",
                    "引号库存的顺序、span、逐字内容或连续 source_refs 与冻结来源不一致",
                    path,
                )
        span_valid = (
            not nonempty_string(text)
            or not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not (0 <= start < end <= len(source_text))
            or source_text[start:end] != normalize_text(text)
        )
        if span_valid:
            report.error("E_SOURCE_DIALOGUE_SPAN", "逐字对白无法按 cp span 回切冻结来源", path)
        if item.get("text_sha256") != sha256_text(text if isinstance(text, str) else ""):
            report.error("E_SOURCE_DIALOGUE_HASH", "对白 text_sha256 不匹配", path)
        expected = expected_source_window(refs, atom_map) if isinstance(refs, list) else None
        if expected is None or span_valid or not (expected["start_cp"] <= start < end <= expected["end_cp"]):
            report.error("E_SOURCE_DIALOGUE_REFS", "对白 source_refs 必须连续并覆盖对白 span", path)
    manifest = expected_unit_manifest(data)
    if data.get("unit_manifest_sha256") != sha256_value(manifest):
        report.error("E_UNIT_MANIFEST_HASH", "unit_manifest_sha256 不可复算", "$.unit_manifest_sha256")
    matrix = expected_feature_matrix(data)
    if data.get("feature_matrix_sha256") != sha256_value(matrix):
        report.error("E_FEATURE_MATRIX_HASH", "feature_matrix_sha256 不可复算", "$.feature_matrix_sha256")
    for index, feature in enumerate(matrix):
        if feature.get("target_mode") == "GENERATABLE_SHOT" and feature.get("route_risk") != "LOW":
            report.error(
                "E_ROUTE_SPLIT_REQUIRED",
                "多轮多人对白或多动作/反应窗口不得伪装成 GENERATABLE_SHOT",
                f"$.units[{index}].source_window",
            )
    request = data.get("selection_request") if isinstance(data.get("selection_request"), dict) else {}
    selected = set(request.get("sample_unit_ids", [])) if isinstance(request.get("sample_unit_ids"), list) else set()
    target_modes = request.get("target_modes") if isinstance(request.get("target_modes"), dict) else {}
    route_findings = request.get("route_findings") if isinstance(request.get("route_findings"), dict) else {}
    unit_by_id = {
        unit.get("unit_id"): unit
        for unit in data.get("units", [])
        if isinstance(unit, dict) and nonempty_string(unit.get("unit_id"))
    }
    for feature in matrix:
        unit_id = feature.get("unit_id")
        if unit_id not in selected:
            continue
        risk = feature.get("route_risk")
        eligibility = unit_by_id.get(unit_id, {}).get("single_shot_eligibility")
        expected_findings = (
            expected_route_findings(feature, eligibility)
            if uses_locked_director_scaffold(data)
            and isinstance(eligibility, dict)
            else ([] if risk == "LOW" else [f"SPLIT_REQUIRED:{risk}"])
        )
        if route_findings.get(unit_id) != expected_findings:
            report.error(
                "E_ROUTE_FINDING",
                "选中窗口的 SPLIT_REQUIRED finding 必须由 feature matrix 确定性回算",
                f"$.selection_request.route_findings.{unit_id}",
            )
        if (
            uses_locked_director_scaffold(data)
            and isinstance(eligibility, dict)
            and eligibility.get("eligible") is False
            and target_modes.get(unit_id) != "EDITED_SEQUENCE"
        ):
            report.error(
                "E_SINGLE_SHOT_ROUTE",
                "single_shot_eligibility=INELIGIBLE 必须写入 split finding 并路由为 EDITED_SEQUENCE",
                f"$.selection_request.target_modes.{unit_id}",
            )
        if risk != "LOW" and target_modes.get(unit_id) != "EDITED_SEQUENCE":
            report.error(
                "E_ROUTE_SPLIT_REQUIRED",
                "高风险选中窗口必须路由为 EDITED_SEQUENCE",
                f"$.selection_request.target_modes.{unit_id}",
            )
    lock_hash = data.get("helper_lock_sha256")
    if not is_sha256(lock_hash) or lock_hash != sha256_value(expected_helper_lock_projection(data)):
        report.error("E_HELPER_LOCK", "helper-owned Phase-A 投影被改写", "$.helper_lock_sha256")
    return result


def validate_negative_plan(unit: dict[str, Any], path: str, report: Report) -> None:
    plan = unit.get("negative_clause_plan")
    clauses = unit.get("negative_clauses")
    if not isinstance(plan, dict) or not isinstance(clauses, list):
        report.error("E_NEGATIVE_CLAUSE_PLAN", "缺少结构化负向条款库存", path)
        return
    candidates = plan.get("candidate_clauses")
    selected = plan.get("selected_clause_ids")
    if not isinstance(candidates, list) or not candidates or not unique_strings(selected) or not selected or not clauses:
        report.error("E_NEGATIVE_CLAUSE_EMPTY", "候选、选择和最终负向条款都必须非空", path)
        return
    candidate_map: dict[str, str] = {}
    for index, candidate in enumerate(candidates):
        candidate_path = f"{path}.negative_clause_plan.candidate_clauses[{index}]"
        if not isinstance(candidate, dict):
            report.error("E_NEGATIVE_CLAUSE_PLAN", "candidate 必须是对象", candidate_path)
            continue
        clause_id = candidate.get("clause_id")
        text = candidate.get("text")
        risk_refs = candidate.get("risk_refs")
        if not isinstance(clause_id, str) or not clause_id or clause_id in candidate_map:
            report.error("E_NEGATIVE_CLAUSE_PLAN", "clause_id 缺失或重复", candidate_path)
            continue
        if not isinstance(text, str) or not text.strip() or "\n" in normalize_text(text) or not text.rstrip().endswith(TERMINAL_PUNCTUATION):
            report.error("E_NEGATIVE_CLAUSE_INCOMPLETE", "每项必须是一条带终止标点的完整约束", candidate_path)
            continue
        candidate_map[clause_id] = normalize_text(text)
        if not isinstance(risk_refs, list) or not risk_refs or not all(isinstance(item, str) and item for item in risk_refs):
            report.error("E_NEGATIVE_CLAUSE_PLAN", "每条负向约束必须有 risk_refs", candidate_path)
        if candidate.get("text_sha256") != sha256_text(text):
            report.error("E_NEGATIVE_CLAUSE_HASH", "text_sha256 与完整条款不匹配", candidate_path)
    expected = []
    for clause_id in selected:
        if clause_id not in candidate_map:
            report.error("E_NEGATIVE_CLAUSE_PLAN", f"选中未知 clause_id：{clause_id}", path)
        else:
            expected.append(candidate_map[clause_id])
    normalized_actual = [normalize_text(item) if isinstance(item, str) else item for item in clauses]
    if normalized_actual != expected:
        report.error("E_NEGATIVE_CLAUSE_PLAN_MISMATCH", "最终条款与选中库存的文本或顺序不一致", path)
    for index, text in enumerate(normalized_actual):
        if not isinstance(text, str) or "\n" in text or not text.rstrip().endswith(TERMINAL_PUNCTUATION):
            report.error("E_NEGATIVE_CLAUSE_INCOMPLETE", "最终条款出现半句、拼接或缺失终止标点", f"{path}.negative_clauses[{index}]")


def validate_traces(
    unit: dict[str, Any],
    atom_map: dict[str, dict[str, Any]],
    unit_source_refs: set[str],
    project_rule_ids: set[str],
    path: str,
    report: Report,
) -> set[str]:
    claims = unit.get("prompt_claims")
    traces = unit.get("prompt_source_trace")
    if not isinstance(claims, list) or not isinstance(traces, list) or not claims or not traces:
        report.error("E_TRACE_EMPTY", "prompt_claims 与 prompt_source_trace 必须是非空数组", path)
        return set()
    trace_map: dict[str, dict[str, Any]] = {}
    for index, trace in enumerate(traces):
        trace_path = f"{path}.prompt_source_trace[{index}]"
        if not isinstance(trace, dict) or not isinstance(trace.get("trace_id"), str) or not trace.get("trace_id"):
            report.error("E_TRACE_SCHEMA", "trace 必须有非空 trace_id", trace_path)
            continue
        trace_id = trace["trace_id"]
        if trace_id in trace_map:
            report.error("E_TRACE_DUPLICATE", f"重复 trace_id：{trace_id}", trace_path)
            continue
        trace_map[trace_id] = trace

    claim_ids: set[str] = set()
    trace_use_count: dict[str, int] = {}
    trace_claim_text: dict[str, str] = {}
    for index, claim in enumerate(claims):
        claim_path = f"{path}.prompt_claims[{index}]"
        if not isinstance(claim, dict):
            report.error("E_TRACE_SCHEMA", "claim 必须是对象", claim_path)
            continue
        claim_id, text, trace_id = claim.get("claim_id"), claim.get("text"), claim.get("trace_id")
        if not isinstance(claim_id, str) or not claim_id or claim_id in claim_ids:
            report.error("E_TRACE_SCHEMA", "claim_id 缺失或重复", claim_path)
        else:
            claim_ids.add(claim_id)
        if not isinstance(text, str) or not text.strip():
            report.error("E_TRACE_SCHEMA", "claim text 必须非空", claim_path)
        elif (
            INTERNAL_ID_RE.search(unicodedata.normalize("NFKC", text))
            and trace_map.get(trace_id, {}).get("relation") != "VERBATIM"
        ):
            report.error("E_PROMPT_INTERNAL_ID", "自然语言 claim 泄漏工程 ID", claim_path)
        if not isinstance(trace_id, str) or trace_id not in trace_map:
            report.error("E_TRACE_MISSING", "每个 claim 必须引用一条存在的 trace", claim_path)
        else:
            trace_use_count[trace_id] = trace_use_count.get(trace_id, 0) + 1
            if isinstance(text, str):
                trace_claim_text[trace_id] = normalize_text(text)

    covered_source_refs: set[str] = set()
    for trace_id, trace in trace_map.items():
        trace_path = f"{path}.prompt_source_trace[{trace_id}]"
        if trace_use_count.get(trace_id, 0) != 1:
            report.error("E_TRACE_CARDINALITY", "每条 trace 必须恰好支持一个 claim", trace_path)
        relation = trace.get("relation")
        if relation not in TRACE_RELATIONS:
            report.error("E_TRACE_SCHEMA", f"未知 relation：{relation!r}", trace_path)
            continue
        source_refs = trace.get("source_refs", [])
        state_refs = trace.get("state_refs", [])
        rule_refs = trace.get("project_rule_refs", [])
        if not isinstance(source_refs, list) or not isinstance(state_refs, list) or not isinstance(rule_refs, list):
            report.error("E_TRACE_SCHEMA", "trace refs 必须是数组", trace_path)
            continue
        if any(ref not in unit_source_refs for ref in source_refs):
            report.error("E_TRACE_FOREIGN_SOURCE", "trace 引用了当前 Unit 之外或未来的来源", trace_path)
        if relation in STORY_TRACE_RELATIONS and not source_refs:
            report.error("E_TRACE_MISSING_SOURCE", "故事 claim 必须引用当前成片来源", trace_path)
        if relation in STORY_TRACE_RELATIONS:
            covered_source_refs.update(ref for ref in source_refs if ref in unit_source_refs)
        if relation == "VERBATIM":
            claim_text = trace_claim_text.get(trace_id, "")
            bound_text = "".join(
                normalize_text(atom_map[ref].get("text", ""))
                for ref in source_refs
                if ref in atom_map and isinstance(atom_map[ref].get("text"), str)
            )
            if not claim_text or claim_text not in bound_text:
                report.error(
                    "E_TRACE_VERBATIM_MISMATCH",
                    "VERBATIM claim 必须是按序连续 source_refs 的规范化逐字子串；概括须标 FAITHFUL_PARAPHRASE",
                    trace_path,
                )
        if relation == "CONTINUITY_CARRY" and not state_refs:
            report.error("E_TRACE_MISSING_STATE", "连续性 claim 必须引用入口状态", trace_path)
        if relation == "PROJECT_CONTROL":
            if not rule_refs or any(ref not in project_rule_ids for ref in rule_refs):
                report.error("E_TRACE_PROJECT_RULE", "项目控制 claim 必须引用有效 Project Rule", trace_path)
        if relation == "DIRECTORIAL_CONTROL" and not (source_refs or state_refs or rule_refs):
            report.error("E_TRACE_DIRECTORIAL_EVIDENCE", "导演控制 claim 必须具有当前证据", trace_path)
    if covered_source_refs != unit_source_refs:
        report.error(
            "E_TRACE_UNIT_COVERAGE",
            "每个 Unit 的全部 compile-target source_refs 都必须进入故事 trace",
            path,
        )
    return covered_source_refs


def validate_locked_semantic_claims(
    data: dict[str, Any], unit: dict[str, Any], path: str, report: Report
) -> None:
    """For current 1.5, accept only helper-derived source claims plus one slot."""

    if not is_current_contract(data):
        return
    scaffold = unit.get("locked_director_scaffold")
    if not isinstance(scaffold, dict):
        return
    slots = expected_authoring_claim_slots(unit, scaffold)
    source_slots = slots[:-1]
    request = data.get("selection_request") if isinstance(data.get("selection_request"), dict) else {}
    selected_ids = (
        request.get("sample_unit_ids")
        if isinstance(request.get("sample_unit_ids"), list)
        else []
    )
    try:
        serial = selected_ids.index(unit.get("unit_id")) + 1
    except ValueError:
        return
    expected_claims = [
        {
            "claim_id": f"CL{serial:03d}-SOURCE-{index:02d}",
            "text": slot["text"],
            "trace_id": f"TR{serial:03d}-SOURCE-{index:02d}",
        }
        for index, slot in enumerate(source_slots, start=1)
    ]
    expected_traces = [
        {
            "trace_id": f"TR{serial:03d}-SOURCE-{index:02d}",
            "relation": slot["relation"],
            "source_refs": slot["source_refs"],
            "state_refs": [],
            "project_rule_refs": [],
            "capability_ids": ["BASE_NARRATIVE"],
        }
        for index, slot in enumerate(source_slots, start=1)
    ]
    claims = unit.get("prompt_claims")
    traces = unit.get("prompt_source_trace")
    if not isinstance(claims, list) or not isinstance(traces, list):
        return
    if claims[: len(expected_claims)] != expected_claims or traces[: len(expected_traces)] != expected_traces:
        report.error(
            "E_SEMANTIC_CLAIM_LOCK",
            "请重新准备本 Unit：来源主张正文、关系和引用必须由锁定来源锚生成，不能手写、换标签或换主体。",
            f"{path}.prompt_claims",
        )
        return
    extra_claims = claims[len(expected_claims) :]
    extra_traces = traces[len(expected_traces) :]
    if len(extra_claims) != len(extra_traces) or len(extra_claims) > 1:
        report.error(
            "E_SEMANTIC_CLAIM_LOCK",
            "请修改主张区：当前写路径只允许一个预分配的导演控制文本槽，不能增删来源主张。",
            f"{path}.prompt_claims",
        )
        return
    if extra_claims:
        expected_claim = {
            "claim_id": f"CL{serial:03d}-DIRECTORIAL",
            "text": extra_claims[0].get("text") if isinstance(extra_claims[0], dict) else None,
            "trace_id": f"TR{serial:03d}-DIRECTORIAL",
        }
        expected_trace = {
            "trace_id": f"TR{serial:03d}-DIRECTORIAL",
            "relation": "DIRECTORIAL_CONTROL",
            "source_refs": list(unit.get("source_refs", [])),
            "state_refs": [],
            "project_rule_refs": [],
            "capability_ids": ["BASE_NARRATIVE"],
        }
        if (
            extra_claims[0] != expected_claim
            or extra_traces[0] != expected_trace
            or not nonempty_string(expected_claim["text"])
        ):
            report.error(
                "E_SEMANTIC_CLAIM_LOCK",
                "请修改导演控制槽：只能填写该槽正文；关系、引用、顺序和槽数量均由 helper 锁定。",
                f"{path}.prompt_claims[{len(expected_claims)}]",
            )


def validate_current_semantic_content(
    data: dict[str, Any], unit: dict[str, Any], path: str, report: Report
) -> None:
    if not is_current_contract(data):
        return
    for finding in semantic_gate_findings(
        data, unit, semantic_unit_surfaces(unit, path)
    ):
        report.error(finding["code"], finding["message"], finding["path"])


def validate_capability_routing(unit: dict[str, Any], path: str, report: Report) -> None:
    routing = unit.get("capability_routing")
    if not isinstance(routing, dict):
        report.error("E_CAPABILITY_ROUTING", "已接受 Unit 必须有结构化 capability_routing", path)
        return
    for key in ("PRIMARY", "SUPPORT", "SUPPRESS"):
        if not unique_strings(routing.get(key)):
            report.error("E_CAPABILITY_ROUTING", f"capability_routing.{key} 必须是无重复字符串数组", path)
    if not isinstance(routing.get("PRIMARY"), list) or not routing.get("PRIMARY"):
        report.error("E_CAPABILITY_ROUTING", "已接受 Unit 至少需要一项 PRIMARY 路由", path)


def expected_source_prompt_block(
    unit: dict[str, Any], atom_map: dict[str, dict[str, Any]]
) -> str:
    window = unit.get("source_window") if isinstance(unit.get("source_window"), dict) else {}
    return (
        "[[SOURCE_WINDOW_REF]]\n"
        f"source_refs={','.join(unit.get('source_refs', []))}\n"
        f"text_sha256={window.get('text_sha256', '')}\n"
        "source_text=BOUND_IN_MACHINE_LEDGER\n"
        "[[/SOURCE_WINDOW_REF]]"
    )


def creator_prompt_surface(value: Any) -> str:
    text = normalize_text(value) if isinstance(value, str) else ""
    return re.sub(
        r"\[\[(?:SOURCE_WINDOW_REF|SOURCE_WINDOW_READ_ONLY|MASTER_DIRECTOR_DESIGN_BLOCK|DRAFT_DIRECTOR_EXECUTION_BLOCK|NEUTRAL_EXECUTION_DIRECTOR_BLOCK|EXECUTION_BEATS)\]\].*?"
        r"\[\[/(?:SOURCE_WINDOW_REF|SOURCE_WINDOW_READ_ONLY|MASTER_DIRECTOR_DESIGN_BLOCK|DRAFT_DIRECTOR_EXECUTION_BLOCK|NEUTRAL_EXECUTION_DIRECTOR_BLOCK|EXECUTION_BEATS)\]\]",
        "",
        text,
        flags=re.DOTALL,
    ).strip()


def expected_execution_beats_v14(unit: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive the minimum executable beat contract from the authored director surface."""

    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    target_mode = director.get("target_mode")
    dialogue_inventory = director.get("dialogue_inventory")
    dialogue_map = {
        item.get("dialogue_id"): item
        for item in dialogue_inventory or []
        if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
    } if isinstance(dialogue_inventory, list) else {}
    shot_plan = director.get("shot_plan") if isinstance(director.get("shot_plan"), list) else []
    if target_mode == "GENERATABLE_SHOT":
        shot_plan = [
            {
                "shot_id": "SH001",
                "source_refs": list(unit.get("source_refs", [])),
                "dialogue_slot_ids": list(dialogue_map),
                "action_state_chain": list(director.get("action_state_chain", []))
                if isinstance(director.get("action_state_chain"), list)
                else [],
                "camera": director.get("camera"),
            }
        ]
    beats: list[dict[str, Any]] = []
    previous_exit = director.get("entry")
    for index, shot in enumerate(shot_plan, start=1):
        if not isinstance(shot, dict):
            continue
        if isinstance(shot.get("action"), list):
            chain = shot["action"]
        elif nonempty_string(shot.get("action")):
            chain = [shot["action"]]
        else:
            chain = shot.get("action_state_chain") if isinstance(shot.get("action_state_chain"), list) else []
        dialogue_ids = shot.get("dialogue_slot_ids") if isinstance(shot.get("dialogue_slot_ids"), list) else []
        audio_order = [
            f"{dialogue_map[dialogue_id].get('speaker', 'SOURCE_UNSPECIFIED')}：{dialogue_map[dialogue_id].get('text', '')}"
            for dialogue_id in dialogue_ids
            if dialogue_id in dialogue_map
        ]
        if nonempty_string(director.get("sound")):
            audio_order.append(f"声音环境：{normalize_text(director['sound']).strip()}")
        dialogue_chars = sum(
            len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", str(dialogue_map[item].get("text", ""))))
            for item in dialogue_ids
            if item in dialogue_map
        )
        duration = round(max(2.0, min(12.0, 2.0 + 0.18 * dialogue_chars + 1.2 * max(1, len(chain)))), 1)
        observable_action = " → ".join(normalize_text(item).strip() for item in chain if nonempty_string(item))
        exit_state = (
            director.get("exit")
            if index == len(shot_plan)
            else (chain[-1] if chain and nonempty_string(chain[-1]) else director.get("exit"))
        )
        camera = normalize_text(shot.get("camera", "")).strip() if isinstance(shot.get("camera"), str) else ""
        beats.append(
            {
                "beat_id": f"EB{index:03d}",
                "shot_id": shot.get("shot_id"),
                "source_refs": list(shot.get("source_refs", [])) if isinstance(shot.get("source_refs"), list) else [],
                "duration_seconds": duration,
                "entry_state": previous_exit,
                "spatial_position": f"按本镜构图落位：{camera}" if camera else "",
                "observable_action": observable_action,
                "camera": camera,
                "audio_order": audio_order or ["现场保持无对白、无新增画外音"],
                "exit_state": exit_state,
            }
        )
        previous_exit = exit_state
    return beats


QUOTE_ASSIGNMENT_KEYS = {
    "dialogue_id", "shot_id", "kind", "speaker", "text", "source_refs",
}
VISIBLE_QUOTE_KINDS = {"NON_LEXICAL_VOCALIZATION", "QUOTED_TEXT"}
VISIBLE_QUOTE_CUE_TITLE = "【本镜必须保留的发声与画面文字】"
EXPLICIT_SOURCE_SOUND_RE = re.compile(
    r"(?:铃声|脚步声|敲门声|撞击声|爆裂声|风声|雨声|雨点|雷声|枪声|"
    r"继电器.{0,10}轻响|归于安静|浪涌|警示钟|响起|传来[^，。；！？\n]{0,12}声|"
    r"咔哒|咔嚓|砰|啪|铮|叮|轰隆|嗡鸣|滴答|滴落|沙沙|摩擦声|轻颤声)"
)
_SOURCE_SOUND_SEGMENT_RE = re.compile(
    r"(?:雨点.{0,16}(?:密|急)|继电器.{0,16}(?:轻响|声)|归于安静|"
    r"风声.{0,20}(?:远处|近处|窗外|护栏|响)|(?:先|再|随后)?听到(?:规律的)?(?:浪涌|警示钟)|"
    r"(?:浪涌|警示钟)(?!灯)|铃声|脚步声|敲门声|撞击声|爆裂声|雷声|枪声|"
    r"响起|传来[^，。；！？\n]{0,12}声|传出[^，。；！？\n]{0,18}(?:声|响)|"
    r"滴落(?:[一二两三四五六七八九十百\d]+次)?|滴答|沙沙声|摩擦声|轻颤声)"
)
_SOURCE_AUDIO_QUANTITY_RE = re.compile(
    r"(?P<quantity>(?:一|二|两|三|四|五|六|七|八|九|十|百|\d+)(?:次|声))"
)
_SOURCE_AUDIO_QUOTE_RE = re.compile(r"[“「『\"](?P<body>.*?)[”」』\"]")


def _source_inventory_map(
    source_dialogue_inventory: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("dialogue_id")): item
        for item in source_dialogue_inventory
        if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
    }


def _assignment_span_in_anchor(
    assignment: dict[str, Any],
    source_item: dict[str, Any],
    anchor: dict[str, Any],
    inventory_map: dict[str, dict[str, Any]],
) -> tuple[int, int] | None:
    """Resolve one quote body to its immutable source code-point span.

    Current 1.5 helper inventories carry absolute spans.  The deterministic
    fallback exists only for hand-built regression fixtures and still chooses
    by the quote-id ordinal inside the same anchor, so equal text at distinct
    source spans is never collapsed merely because its spelling is equal.
    """

    anchor_start = anchor.get("start_cp")
    anchor_end = anchor.get("end_cp")
    quote_start = source_item.get("start_cp")
    quote_end = source_item.get("end_cp")
    if all(isinstance(item, int) for item in (anchor_start, anchor_end, quote_start, quote_end)):
        if anchor_start <= quote_start <= quote_end <= anchor_end:
            return quote_start, quote_end
    if not isinstance(anchor_start, int):
        return None
    text = normalize_text(anchor.get("exact_text", ""))
    body = normalize_text(source_item.get("text", ""))
    if not body:
        return None
    matches = [
        match
        for match in _SOURCE_AUDIO_QUOTE_RE.finditer(text)
        if normalize_text(match.group("body")) == body
    ]
    if not matches:
        return None
    dialogue_id = str(assignment.get("dialogue_id", ""))
    same_text_ids = [
        str(item)
        for item in anchor.get("quote_ids", [])
        if normalize_text(inventory_map.get(str(item), {}).get("text", "")) == body
    ]
    ordinal = same_text_ids.index(dialogue_id) if dialogue_id in same_text_ids else 0
    match = matches[min(ordinal, len(matches) - 1)]
    return anchor_start + match.start("body"), anchor_start + match.end("body")


def _source_audio_quantity(anchor_text: str, local_start: int, local_end: int) -> str:
    before = anchor_text[max(0, local_start - 28):local_start]
    after = anchor_text[local_end:min(len(anchor_text), local_end + 20)]
    before_matches = list(_SOURCE_AUDIO_QUANTITY_RE.finditer(before))
    if before_matches:
        return before_matches[-1].group("quantity")
    after_match = _SOURCE_AUDIO_QUANTITY_RE.search(after)
    return after_match.group("quantity") if after_match else ""


def _render_sfx_event(
    anchor_text: str, quote_text: str, local_start: int, local_end: int
) -> tuple[str, str, str]:
    explicit_quantity = _source_audio_quantity(anchor_text, local_start, local_end)
    quantity = explicit_quantity or "一次"
    if "止回阀" in anchor_text or "阀门" in anchor_text:
        carrier = "止回阀"
        qualifier = "清楚的" if "清楚" in anchor_text else ""
        rendered = f"{carrier}发出{explicit_quantity}{qualifier}“{quote_text}”"
    elif "黄铜校准片" in anchor_text and "弹正" in anchor_text:
        carrier = "黄铜校准片弹正时"
        rendered = f"{carrier}发出{explicit_quantity or '一声'}“{quote_text}”"
    elif "入口感应铃" in anchor_text:
        carrier = "入口感应铃"
        place = "在近处" if "近处" in anchor_text else ""
        rendered = f"{carrier}{place}响起{explicit_quantity or '一声'}“{quote_text}”"
    elif "门外传来" in anchor_text:
        carrier = "门外"
        rendered = (
            f"门外传来{explicit_quantity}“{quote_text}”"
            if explicit_quantity else f"门外传来“{quote_text}”"
        )
    else:
        owner_match = re.search(
            r"(?P<owner>[\u4e00-\u9fffA-Za-z0-9]{1,18}?)(?:在[^，。；！？]{0,12})?"
            r"(?:发出|传来|响起)[^，。；！？]{0,12}$",
            anchor_text[:local_start],
        )
        carrier = owner_match.group("owner") if owner_match else "来源声响"
        rendered = f"{carrier}发出{explicit_quantity}“{quote_text}”"
    return carrier, quantity, rendered


def _render_nonlexical_event(
    assignment: dict[str, Any], anchor_text: str, local_start: int, local_end: int
) -> tuple[str, str, str]:
    speaker = normalize_text(assignment.get("speaker", "")).strip()
    quote_text = normalize_text(assignment.get("text", "")).strip()
    quantity = _source_audio_quantity(anchor_text, local_start, local_end) or "一声"
    before = anchor_text[max(0, local_start - 24):local_start]
    after = anchor_text[local_end:min(len(anchor_text), local_end + 16)]
    verb = "呼出" if "呼出" in before else ""
    if not verb and "闷哼" in before + after:
        verb = "闷哼"
    if not verb and "倒吸" in before:
        verb = "倒吸"
    if not verb:
        verb = "发出"
    rendered = f"{speaker}{verb}{quantity}“{quote_text}”"
    return speaker, quantity, rendered


def _render_spoken_event(
    assignment: dict[str, Any], anchor_text: str
) -> tuple[str, str]:
    speaker = normalize_text(assignment.get("speaker", "")).strip()
    quote_text = normalize_text(assignment.get("text", "")).strip()
    if "单耳耳机" in anchor_text and "补录" in anchor_text:
        return "单耳耳机内补录", f"单耳耳机内{speaker}补录：“{quote_text}”"
    if "现场口播" in anchor_text and ("档案" in anchor_text or "同期" in anchor_text):
        return "档案内同期口播", f"档案内{speaker}现场口播：“{quote_text}”"
    return speaker, f"{speaker}：{quote_text}"


def _masked_unquoted_anchor_text(anchor_text: str) -> str:
    chars = list(anchor_text)
    for match in _SOURCE_AUDIO_QUOTE_RE.finditer(anchor_text):
        for index in range(match.start(), match.end()):
            chars[index] = " "
    return "".join(chars)


def _render_unquoted_source_sound(
    segment: str, anchor_text: str
) -> tuple[str, str] | None:
    cleaned = segment.strip().strip("，。；！？ ")
    if not cleaned or not _SOURCE_SOUND_SEGMENT_RE.search(cleaned):
        return None
    if "警示灯" in cleaned and "警示钟" not in cleaned:
        return None
    if "单耳耳机" in anchor_text:
        if "浪涌" in cleaned:
            return "单耳耳机", "单耳耳机内浪涌"
        if "警示钟" in cleaned:
            return "单耳耳机", "单耳耳机内警示钟"
    if "雨点" in cleaned and ("密" in cleaned or "急" in cleaned):
        return "棚顶雨点" if "棚顶" in cleaned else "雨点", cleaned
    if "继电器" in cleaned:
        return "机柜继电器" if "机柜" in cleaned else "继电器", cleaned
    if "归于安静" in cleaned:
        return "现场声场", cleaned
    if "窗外风声" in cleaned:
        return "窗外风声", cleaned
    if "滴落" in cleaned:
        carrier = "画面内排水口" if "排水口" in anchor_text else "来源排水处"
        return carrier, cleaned
    return "来源声响", cleaned


def derive_source_audio_events(
    unit: dict[str, Any],
    source_dialogue_inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the private 1.5 source-audio projection in source span order.

    This is intentionally not serialized into the public contract.  Public
    quote assignments keep their six keys and execution beats keep their ten;
    the richer span/carrier/count records exist only while recomputing those
    fixed public surfaces.
    """

    assignments = expected_quote_assignments(unit, source_dialogue_inventory)
    inventory_map = _source_inventory_map(source_dialogue_inventory)
    assignments_by_id = {
        str(item.get("dialogue_id")): item
        for item in assignments
        if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
    }
    scaffold = (
        unit.get("locked_director_scaffold")
        if isinstance(unit.get("locked_director_scaffold"), dict) else {}
    )
    anchor_map = {
        str(item.get("anchor_id")): item
        for item in scaffold.get("semantic_anchors", [])
        if isinstance(item, dict) and nonempty_string(item.get("anchor_id"))
    }
    events: list[dict[str, Any]] = []

    def add_event(
        *, shot_id: str, anchor: dict[str, Any], start_cp: int, end_cp: int,
        route: str, render_text: str, quote_id: str = "", carrier: str = "",
        quantity: str = "",
    ) -> None:
        events.append(
            {
                "shot_id": shot_id,
                "anchor_id": str(anchor.get("anchor_id", "")),
                "source_ref": str(anchor.get("source_ref", "")),
                "start_cp": start_cp,
                "end_cp": end_cp,
                "route": route,
                "quote_id": quote_id,
                "carrier": carrier,
                "quantity": quantity,
                "render_text": render_text,
            }
        )

    shots = scaffold.get("shots") if isinstance(scaffold.get("shots"), list) else []
    for shot in shots:
        if not isinstance(shot, dict) or not nonempty_string(shot.get("shot_id")):
            continue
        shot_id = str(shot["shot_id"])
        for anchor_id in shot.get("source_anchor_ids", []):
            anchor = anchor_map.get(str(anchor_id))
            if not isinstance(anchor, dict):
                continue
            anchor_text = normalize_text(anchor.get("exact_text", ""))
            anchor_start = anchor.get("start_cp") if isinstance(anchor.get("start_cp"), int) else 0
            quote_events_claim_anchor = False
            for dialogue_id in anchor.get("quote_ids", []):
                assignment = assignments_by_id.get(str(dialogue_id))
                source_item = inventory_map.get(str(dialogue_id), {})
                if not isinstance(assignment, dict) or not isinstance(source_item, dict):
                    continue
                span = _assignment_span_in_anchor(
                    assignment, source_item, anchor, inventory_map
                )
                if span is None:
                    continue
                quote_start, quote_end = span
                local_start = max(0, quote_start - anchor_start)
                local_end = max(local_start, quote_end - anchor_start)
                kind = assignment.get("kind")
                quote_text = normalize_text(assignment.get("text", "")).strip()
                if kind == "SPOKEN_DIALOGUE":
                    carrier, rendered = _render_spoken_event(assignment, anchor_text)
                    quantity = _source_audio_quantity(
                        anchor_text, local_start, local_end
                    ) or "一次"
                    add_event(
                        shot_id=shot_id, anchor=anchor, start_cp=quote_start,
                        end_cp=quote_end, route="SPOKEN_DIALOGUE",
                        render_text=rendered, quote_id=str(dialogue_id),
                        carrier=carrier, quantity=quantity,
                    )
                elif kind == "NON_LEXICAL_VOCALIZATION":
                    carrier, quantity, rendered = _render_nonlexical_event(
                        assignment, anchor_text, local_start, local_end
                    )
                    add_event(
                        shot_id=shot_id, anchor=anchor, start_cp=anchor_start,
                        end_cp=anchor.get("end_cp", quote_end),
                        route="NON_LEXICAL_VOCALIZATION", render_text=rendered,
                        quote_id=str(dialogue_id), carrier=carrier,
                        quantity=quantity,
                    )
                    quote_events_claim_anchor = True
                elif kind == "SFX":
                    carrier, quantity, rendered = _render_sfx_event(
                        anchor_text, quote_text, local_start, local_end
                    )
                    add_event(
                        shot_id=shot_id, anchor=anchor, start_cp=anchor_start,
                        end_cp=anchor.get("end_cp", quote_end), route="SFX",
                        render_text=rendered, quote_id=str(dialogue_id),
                        carrier=carrier, quantity=quantity,
                    )
                    quote_events_claim_anchor = True
                # QUOTED_TEXT and INTERNAL_THOUGHT deliberately have no audio event.

            if quote_events_claim_anchor:
                continue
            unquoted = _masked_unquoted_anchor_text(anchor_text)
            for match in re.finditer(r"[^，。；！？\n]+[，。；！？]?", unquoted):
                rendered = _render_unquoted_source_sound(match.group(0), anchor_text)
                if rendered is None:
                    continue
                carrier, render_text = rendered
                quantity_match = _SOURCE_AUDIO_QUANTITY_RE.search(match.group(0))
                add_event(
                    shot_id=shot_id,
                    anchor=anchor,
                    start_cp=anchor_start + match.start(),
                    end_cp=anchor_start + match.end(),
                    route="SOURCE_SOUND",
                    render_text=render_text,
                    carrier=carrier,
                    quantity=quantity_match.group("quantity") if quantity_match else "",
                )

    events.sort(
        key=lambda item: (
            item["start_cp"], item["end_cp"], item["quote_id"], item["route"]
        )
    )
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for event in events:
        semantic_key = (
            event["shot_id"], event["start_cp"], event["end_cp"],
            event["quote_id"], event["route"], event["carrier"],
            event["quantity"], event["render_text"],
        )
        if semantic_key in seen:
            continue
        seen.add(semantic_key)
        merged.append(event)
    return merged


def source_locked_nonlexical_speakers_from_window(
    window: dict[str, Any],
) -> dict[str, str]:
    """Return helper-owned NONLEX speakers exposed as read-only authoring data."""

    hint_map = (
        window.get("quote_classification_hints")
        if isinstance(window.get("quote_classification_hints"), dict)
        else {}
    )
    locked: dict[str, str] = {}
    for dialogue_id, payload in hint_map.items():
        if not isinstance(payload, dict):
            continue
        hints = payload.get("classification_hints")
        evidence = payload.get("context_evidence")
        speaker = (
            evidence.get("vocalization_speaker_hint")
            if isinstance(evidence, dict)
            else None
        )
        if (
            isinstance(hints, list)
            and "LIKELY_NON_LEXICAL_VOCALIZATION" in hints
            and nonempty_string(speaker)
            and speaker != "SOURCE_UNSPECIFIED"
        ):
            locked[str(dialogue_id)] = normalize_text(speaker).strip()
    return locked


def derive_quote_assignments(
    source_dialogue_inventory: list[dict[str, Any]],
    locked_director_scaffold: dict[str, Any],
    quote_classifications: dict[str, Any],
    spoken_dialogue_inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project every source quote into exactly its helper-locked shot."""

    source_map = {
        item.get("dialogue_id"): item
        for item in source_dialogue_inventory
        if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
    }
    spoken_map = {
        item.get("dialogue_id"): item
        for item in spoken_dialogue_inventory
        if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
    }
    assignments: list[dict[str, Any]] = []
    shots = (
        locked_director_scaffold.get("shots")
        if isinstance(locked_director_scaffold.get("shots"), list)
        else []
    )
    for shot in shots:
        if not isinstance(shot, dict) or not nonempty_string(shot.get("shot_id")):
            continue
        quote_ids = shot.get("quote_ids") if isinstance(shot.get("quote_ids"), list) else []
        for dialogue_id in quote_ids:
            source_item = source_map.get(dialogue_id)
            if not isinstance(source_item, dict):
                continue
            kind = quote_classifications.get(dialogue_id)
            speaker = "SOURCE_UNSPECIFIED"
            if kind == "SPOKEN_DIALOGUE":
                spoken_item = spoken_map.get(dialogue_id, {})
                if nonempty_string(spoken_item.get("speaker")):
                    speaker = normalize_text(spoken_item["speaker"]).strip()
            elif kind == "NON_LEXICAL_VOCALIZATION":
                evidence = source_item.get("context_evidence")
                hint = (
                    evidence.get("vocalization_speaker_hint")
                    if isinstance(evidence, dict) else None
                )
                if nonempty_string(hint):
                    speaker = normalize_text(hint).strip()
            assignments.append(
                {
                    "dialogue_id": dialogue_id,
                    "shot_id": shot["shot_id"],
                    "kind": kind,
                    "speaker": speaker,
                    "text": source_item.get("text"),
                    "source_refs": list(source_item.get("source_refs", []))
                    if isinstance(source_item.get("source_refs"), list) else [],
                }
            )
    return assignments


def expected_quote_assignments(
    unit: dict[str, Any], source_dialogue_inventory: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Recompute the helper-owned 1.5 quote-to-shot projection."""

    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    provenance = unit.get("provenance") if isinstance(unit.get("provenance"), dict) else {}
    classifications = (
        provenance.get("quote_classifications")
        if isinstance(provenance.get("quote_classifications"), dict) else {}
    )
    scaffold = (
        unit.get("locked_director_scaffold")
        if isinstance(unit.get("locked_director_scaffold"), dict) else {}
    )
    spoken_inventory = (
        director.get("dialogue_inventory")
        if isinstance(director.get("dialogue_inventory"), list) else []
    )
    return derive_quote_assignments(
        source_dialogue_inventory,
        scaffold,
        classifications,
        spoken_inventory,
    )


def render_visible_quote_cues(assignments: list[dict[str, Any]]) -> list[str]:
    """Render source-faithful non-spoken cues with natural shot positions."""

    cues: list[str] = []
    for assignment in assignments:
        if not isinstance(assignment, dict) or assignment.get("kind") not in VISIBLE_QUOTE_KINDS:
            continue
        shot_match = re.fullmatch(r"SH(\d{3,})", str(assignment.get("shot_id", "")))
        shot_number = int(shot_match.group(1)) if shot_match else 0
        prefix = f"镜头 {shot_number}："
        text = normalize_text(assignment.get("text", "")).strip()
        if assignment.get("kind") == "NON_LEXICAL_VOCALIZATION":
            speaker = normalize_text(assignment.get("speaker", "")).strip()
            cues.append(f"{prefix}{speaker}发出“{text}”")
        else:
            cues.append(f"{prefix}画面文字（不朗读）：“{text}”")
    return cues


def render_visible_quote_cue_block(cues: list[str]) -> str:
    if not cues:
        return ""
    return "\n".join([VISIBLE_QUOTE_CUE_TITLE, *(f"- {cue}" for cue in cues)])


def strip_helper_owned_visible_quote_block(text: str, cues: list[str]) -> str:
    """Strip only an exact canonical cue suffix before layer comparison."""

    normalized = normalize_text(text).strip()
    block = render_visible_quote_cue_block(cues)
    if not block:
        return normalized
    if normalized == block:
        return ""
    suffix = f"\n\n{block}"
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)].rstrip()
    return normalized


def expected_visible_quote_voice_coverage(
    unit: dict[str, Any], source_dialogue_inventory: list[dict[str, Any]]
) -> dict[str, list[str]]:
    assignments = expected_quote_assignments(unit, source_dialogue_inventory)
    master_cues = render_visible_quote_cues(assignments)
    neutral_cues: list[str] = []
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        if assignment.get("kind") in {"NON_LEXICAL_VOCALIZATION", "QUOTED_TEXT"}:
            cue = normalize_text(assignment.get("text", "")).strip()
            if cue:
                neutral_cues.append(cue)
    return {
        "master_prompt": master_cues,
        "neutral_execution_prompt": neutral_cues,
    }


def explicit_source_sound_cues(anchors: list[dict[str, Any]]) -> list[str]:
    """Return legacy caller-friendly source clauses without spelling de-duplication.

    Current 1.5 execution uses :func:`derive_source_audio_events`, which owns
    quote routing, spans, counts and carriers.  This small compatibility helper
    remains useful to read bare anchors in focused diagnostics; distinct source
    spans are deliberately retained even when their text is identical.
    """

    cues: list[str] = []
    for anchor in anchors:
        text = normalize_text(anchor.get("exact_text", ""))
        unquoted = _masked_unquoted_anchor_text(text)
        for match in re.finditer(r"[^，。；！？\n]+[，。；！？]?", unquoted):
            rendered = _render_unquoted_source_sound(match.group(0), text)
            if rendered is not None:
                cues.append(rendered[1])
    return cues


def _execution_action_duration_floor(actions: list[str]) -> float:
    unquoted_actions: list[str] = []
    for item in actions:
        if not nonempty_string(item):
            continue
        action_text, pure_attribution = _duration_action_text(item)
        if pure_attribution:
            continue
        unquoted_actions.append(action_text)
    text = "。".join(item for item in unquoted_actions if item.strip())
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
        return 0.0
    clauses = [item for item in ACTION_CLAUSE_SPLIT_RE.split(text) if item.strip()]
    semantic_chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))
    action_signals = len(ACTION_REACTION_RE.findall(text))
    return max(
        1.0,
        0.5 * max(1, len(clauses))
        + 0.3 * action_signals
        + semantic_chars / 32.0,
    )


def _estimate_execution_beat_duration_raw(
    actions: list[str],
    camera: str,
    assignments: list[dict[str, Any]],
) -> float:
    """Compute the unrounded 1.5 shot floor used by the hard ceiling gate."""

    spoken_seconds = 0.0
    non_lexical_seconds = 0.0
    quoted_text_seconds = 0.0
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        text = semantic_compare_text(normalize_text(assignment.get("text", "")))
        chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))
        if assignment.get("kind") == "SPOKEN_DIALOGUE":
            spoken_seconds += 0.45 + chars / 4.2
        elif assignment.get("kind") == "NON_LEXICAL_VOCALIZATION":
            non_lexical_seconds += max(0.7, 0.35 + chars / 5.0)
        elif assignment.get("kind") == "QUOTED_TEXT":
            quoted_text_seconds += 0.6 + chars / 5.0
    camera_text = semantic_compare_text(normalize_text(camera))
    camera_seconds = 0.45 * len(CAMERA_MOTION_TOKEN_RE.findall(camera_text))
    action_seconds = _execution_action_duration_floor(actions)
    unquoted_action_texts = [
        _duration_action_text(item)[0]
        for item in actions
        if nonempty_string(item)
    ]
    action_camera_text = "。".join([*unquoted_action_texts, camera_text])
    explicit_seconds = explicit_continuous_seconds(action_camera_text)
    action_camera_seconds = max(
        action_seconds + camera_seconds,
        explicit_seconds,
    )
    voice_seconds = spoken_seconds + non_lexical_seconds + quoted_text_seconds
    if voice_seconds and _duration_voice_is_explicitly_simultaneous(
        action_camera_text
    ):
        combined_seconds = max(action_camera_seconds, voice_seconds)
    else:
        combined_seconds = action_camera_seconds + voice_seconds
    return max(combined_seconds, 2.0)


def estimate_execution_beat_duration(
    actions: list[str],
    camera: str,
    assignments: list[dict[str, Any]],
) -> float:
    """Return the display duration; hard gates use the unrounded helper."""

    return round(_estimate_execution_beat_duration_raw(actions, camera, assignments), 1)


def expected_execution_beats(
    unit: dict[str, Any],
    source_dialogue_inventory: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Derive 1.5 per-shot execution without copying the global sound strategy."""

    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    target_mode = director.get("target_mode")
    assignments = expected_quote_assignments(unit, source_dialogue_inventory or [])
    source_audio_events = derive_source_audio_events(
        unit, source_dialogue_inventory or []
    )
    scaffold = (
        unit.get("locked_director_scaffold")
        if isinstance(unit.get("locked_director_scaffold"), dict) else {}
    )
    semantic_anchors = [
        item
        for item in scaffold.get("semantic_anchors", [])
        if isinstance(item, dict) and nonempty_string(item.get("anchor_id"))
    ]
    anchor_map = {
        item.get("anchor_id"): item
        for item in semantic_anchors
    }
    duration_projection = _project_anchor_duration_floors_raw(semantic_anchors)
    duration_by_anchor_id = {
        anchor["anchor_id"]: item
        for anchor, item in zip(semantic_anchors, duration_projection)
    }
    locked_shot_map = {
        item.get("shot_id"): item
        for item in scaffold.get("shots", [])
        if isinstance(item, dict) and nonempty_string(item.get("shot_id"))
    }
    shot_plan = director.get("shot_plan") if isinstance(director.get("shot_plan"), list) else []
    if target_mode == "GENERATABLE_SHOT":
        locked_shot = next(iter(locked_shot_map.values()), {})
        shot_plan = [
            {
                "shot_id": locked_shot.get("shot_id", "SH001"),
                "source_refs": list(locked_shot.get("source_refs", unit.get("source_refs", []))),
                "semantic_anchor_ids": list(locked_shot.get("source_anchor_ids", [])),
                "action_state_chain": list(director.get("action_state_chain", []))
                if isinstance(director.get("action_state_chain"), list) else [],
                "camera": director.get("camera"),
            }
        ]
    beats: list[dict[str, Any]] = []
    previous_exit = director.get("entry")
    for index, shot in enumerate(shot_plan, start=1):
        if not isinstance(shot, dict):
            continue
        shot_id = shot.get("shot_id")
        chain = (
            list(shot.get("action_state_chain", []))
            if isinstance(shot.get("action_state_chain"), list) else []
        )
        local_assignments = [
            item for item in assignments
            if isinstance(item, dict) and item.get("shot_id") == shot_id
        ]
        audio_order = [
            str(event["render_text"])
            for event in source_audio_events
            if event.get("shot_id") == shot_id
        ]
        if not audio_order:
            audio_order = ["本镜无来源口播或明确声响"]
        camera = normalize_text(shot.get("camera", "")).strip() if isinstance(shot.get("camera"), str) else ""
        raw_duration = _estimate_execution_beat_duration_raw(
            chain, camera, local_assignments
        )
        source_duration_items = [
            duration_by_anchor_id[anchor_id]
            for anchor_id in shot.get("semantic_anchor_ids", [])
            if anchor_id in duration_by_anchor_id
        ]
        if any(item["context_locked"] for item in source_duration_items):
            raw_duration = max(
                raw_duration,
                sum(item["floor"] for item in source_duration_items),
            )
        if raw_duration > 12.0:
            raise ValueError(
                f"E_SHOT_DURATION_OVERFLOW: {shot_id} deterministic duration floor "
                f"{raw_duration:.3f}s exceeds the 12-second ceiling"
            )
        duration = round(raw_duration, 1)
        observable_action = " → ".join(
            normalize_text(item).strip() for item in chain if nonempty_string(item)
        )
        exit_state = (
            director.get("exit")
            if index == len(shot_plan)
            else (chain[-1] if chain and nonempty_string(chain[-1]) else director.get("exit"))
        )
        beats.append(
            {
                "beat_id": f"EB{index:03d}",
                "shot_id": shot_id,
                "source_refs": list(shot.get("source_refs", []))
                if isinstance(shot.get("source_refs"), list) else [],
                "duration_seconds": duration,
                "entry_state": previous_exit,
                "spatial_position": f"按本镜构图落位：{camera}" if camera else "",
                "observable_action": observable_action,
                "camera": camera,
                "audio_order": audio_order,
                "exit_state": exit_state,
            }
        )
        previous_exit = exit_state
    return beats


def expected_execution_beats_for_version(
    unit: dict[str, Any],
    source_dialogue_inventory: list[dict[str, Any]] | None = None,
    contract_version: str = CONTRACT_VERSION,
) -> list[dict[str, Any]]:
    if contract_version in READ_ONLY_CONTRACT_VERSIONS:
        return expected_execution_beats_v14(unit)
    return expected_execution_beats(unit, source_dialogue_inventory)


def _audio_item_routes_forbidden_quote(item: Any, quote_text: str) -> bool:
    """Match an actual audio route without substring-harming short screen text."""

    if not isinstance(item, str) or not quote_text:
        return False
    normalized_item = normalize_text(item).strip()
    normalized_quote = normalize_text(quote_text).strip()
    if normalized_item == normalized_quote:
        return True
    wrapped_patterns = (
        f"“{normalized_quote}”", f"「{normalized_quote}」",
        f"『{normalized_quote}』", f'"{normalized_quote}"',
    )
    if any(pattern in normalized_item for pattern in wrapped_patterns):
        return True
    if len(normalized_quote) >= 4 and re.search(
        rf"(?:朗读|口播|对白|旁白|声音|说|念|读)[^\n]{{0,16}}{re.escape(normalized_quote)}",
        normalized_item,
    ):
        return True
    return False


def validate_source_audio_projection(
    unit: dict[str, Any],
    expected_beats: list[dict[str, Any]],
    actual_beats: Any,
    source_dialogue_inventory: list[dict[str, Any]],
    path: str,
    report: Report,
) -> None:
    """Reject deterministic 1.5 source-audio loss, reordering and invention."""

    expected_by_shot = {
        item.get("shot_id"): item.get("audio_order", [])
        for item in expected_beats
        if isinstance(item, dict) and nonempty_string(item.get("shot_id"))
    }
    actual_by_shot = {
        item.get("shot_id"): item.get("audio_order", [])
        for item in actual_beats or []
        if isinstance(item, dict) and nonempty_string(item.get("shot_id"))
    } if isinstance(actual_beats, list) else {}
    assignments = expected_quote_assignments(unit, source_dialogue_inventory)
    forbidden_quotes = [
        normalize_text(item.get("text", "")).strip()
        for item in assignments
        if isinstance(item, dict)
        and item.get("kind") in {"QUOTED_TEXT", "INTERNAL_THOUGHT"}
        and nonempty_string(item.get("text"))
    ]
    for shot_id, expected_audio in expected_by_shot.items():
        actual_audio = actual_by_shot.get(shot_id)
        shot_path = f"{path}[{shot_id}].audio_order"
        if not isinstance(actual_audio, list):
            report.error(
                "E_SOURCE_AUDIO_COVERAGE",
                "逐镜声音表缺少当前镜头的来源声音事件流",
                shot_path,
            )
            continue
        for item in actual_audio:
            if any(
                _audio_item_routes_forbidden_quote(item, quote_text)
                for quote_text in forbidden_quotes
            ):
                report.error(
                    "E_QUOTED_TEXT_AUDIO_ROUTE",
                    "画面文字或内心文字不得进入 audio_order；短画面字只按完整包裹形式判断",
                    shot_path,
                )
                break
        expected_counter = Counter(expected_audio)
        actual_counter = Counter(actual_audio)
        missing = list((expected_counter - actual_counter).elements())
        surplus = list((actual_counter - expected_counter).elements())
        duplicates = [item for item in surplus if item in expected_counter]
        extras = [item for item in surplus if item not in expected_counter]
        if missing:
            report.error(
                "E_SOURCE_AUDIO_COVERAGE",
                "来源声音事件缺失或次数被改写：" + " / ".join(str(item) for item in missing[:4]),
                shot_path,
            )
        if duplicates:
            report.error(
                "E_SOURCE_AUDIO_DUPLICATE",
                "同一来源声音事件在本镜被重复写入：" + " / ".join(str(item) for item in duplicates[:4]),
                shot_path,
            )
        if extras:
            report.error(
                "E_SOURCE_AUDIO_EXTRA",
                "逐镜声音表出现来源事件流以外的声音：" + " / ".join(str(item) for item in extras[:4]),
                shot_path,
            )
        if not missing and not surplus and actual_audio != expected_audio:
            report.error(
                "E_SOURCE_AUDIO_ORDER",
                "逐镜来源声音必须严格按来源 code-point 顺序排列",
                shot_path,
            )


SCAFFOLD_ANCHOR_ROLES = {
    "ACTION_BEAT", "REACTION_BEAT", "DIALOGUE_BEAT", "TIME_TRANSITION",
}
LOCKED_SCAFFOLD_KEYS = {
    "scaffold_version", "derivation", "target_mode", "minimum_shots",
    "semantic_anchors", "entry_anchor_ids", "action_anchor_ids",
    "exit_anchor_ids", "continuity_anchor_ids", "shots", "field_provenance",
}
LOCKED_ANCHOR_KEYS = {
    "anchor_id", "source_ref", "start_cp", "end_cp", "exact_text",
    "text_sha256", "anchor_role", "quote_ids",
}
LOCKED_SHOT_KEYS = {"shot_id", "source_refs", "source_anchor_ids", "quote_ids"}
LOCKED_SCAFFOLD_PROVENANCE_KEYS = {
    "entry", "action_state_chain", "exit", "continuity", "shots",
}
FIXED_TRANSFORM_ROLES = {
    "source_role": "PROVIDER_NEUTRAL_MASTER",
    "target_role": "NEUTRAL_EXECUTION_PROMPT",
    "derivation": "HELPER_DERIVED",
}
SINGLE_SHOT_ELIGIBILITY_KEYS = {
    "decision", "eligible", "reasons", "atom_count", "semantic_anchor_count",
    "dialogue_turn_count", "speaker_count", "time_jump_anchor_ids",
}
SINGLE_SHOT_REASON_PREFIXES = {
    "ATOM_COUNT_GT_3", "SEMANTIC_ANCHORS_GT_4", "TIME_TRANSITION_PRESENT",
    "DIALOGUE_TURNS_GE_4", "SPEAKER_COUNT_GE_3", "DURATION_FLOOR_GT_12",
}


def _ordered_unique_strings(values: Any) -> list[str] | None:
    if not isinstance(values, list) or not all(nonempty_string(item) for item in values):
        return None
    if len(values) != len(set(values)):
        return None
    return list(values)


def validate_v14_locked_scaffold(
    unit: dict[str, Any],
    atom_map: dict[str, dict[str, Any]],
    source_dialogue_inventory: list[dict[str, Any]],
    canonical_scaffold: dict[str, Any],
    unit_source_refs: set[str],
    contract_path: str,
    report: Report,
    contract_version: str = CONTRACT_VERSION,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Validate a versioned helper-owned directing projection copied into a unit."""

    scaffold = unit.get("locked_director_scaffold")
    scaffold_path = f"{contract_path.rsplit('.director_contract', 1)[0]}.locked_director_scaffold"
    if not isinstance(scaffold, dict) or set(scaffold) != LOCKED_SCAFFOLD_KEYS:
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "1.4/1.5 Unit 必须保留 exact locked_director_scaffold，禁止增删或改写锁定字段",
            scaffold_path,
        )
        return {}, {}
    if scaffold != canonical_scaffold:
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "locked_director_scaffold 必须精确等于 canonical 来源、路由与镜头投影",
            scaffold_path,
        )
    if (
        scaffold.get("scaffold_version") != (
            V14_DIRECTOR_SCAFFOLD_VERSION
            if contract_version in READ_ONLY_CONTRACT_VERSIONS
            else DIRECTOR_SCAFFOLD_VERSION
        )
        or scaffold.get("derivation") != "HELPER_DERIVED"
        or scaffold.get("target_mode") not in DIRECTOR_TARGET_MODES
        or not isinstance(scaffold.get("minimum_shots"), int)
        or scaffold.get("minimum_shots", -1) < 0
    ):
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "locked scaffold 的版本、派生方式、路由或 minimum_shots 非 canonical",
            scaffold_path,
        )
    recorded_hash = unit.get("locked_scaffold_sha256")
    if not is_sha256(recorded_hash) or recorded_hash != sha256_value(scaffold):
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "locked_scaffold_sha256 必须等于当前 locked_director_scaffold 的 canonical hash",
            f"{scaffold_path.rsplit('.', 1)[0]}.locked_scaffold_sha256",
        )
    if unit.get("fixed_transform_roles") != FIXED_TRANSFORM_ROLES:
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "fixed_transform_roles 必须保留 helper 固定的 MASTER 到中性执行层映射",
            f"{scaffold_path.rsplit('.', 1)[0]}.fixed_transform_roles",
        )

    anchors = scaffold.get("semantic_anchors")
    anchor_map: dict[str, dict[str, Any]] = {}
    if not isinstance(anchors, list) or not anchors:
        report.error("E_AUTHORING_SCAFFOLD_TAMPER", "semantic_anchors 必须是非空锁定数组", scaffold_path)
        anchors = []
    canonical_anchors = expected_semantic_anchors(
        unit, atom_map, source_dialogue_inventory, contract_version
    )
    if anchors != canonical_anchors:
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "semantic_anchors 必须精确等于来源台账的 canonical 完整句投影",
            f"{scaffold_path}.semantic_anchors",
        )
    for index, anchor in enumerate(anchors):
        anchor_path = f"{scaffold_path}.semantic_anchors[{index}]"
        if not isinstance(anchor, dict) or set(anchor) != LOCKED_ANCHOR_KEYS:
            report.error("E_AUTHORING_SCAFFOLD_TAMPER", "semantic anchor exact keys 不匹配", anchor_path)
            continue
        anchor_id = anchor.get("anchor_id")
        source_ref = anchor.get("source_ref")
        quote_ids = anchor.get("quote_ids")
        if not nonempty_string(anchor_id) or anchor_id in anchor_map:
            report.error("E_AUTHORING_SCAFFOLD_TAMPER", "anchor_id 缺失或重复", anchor_path)
            continue
        anchor_map[anchor_id] = anchor
        if source_ref not in unit_source_refs or source_ref not in atom_map:
            report.error("E_AUTHORING_SCAFFOLD_TAMPER", "semantic anchor 必须绑定当前 Unit source_ref", anchor_path)
            continue
        atom = atom_map[source_ref]
        start_cp, end_cp = anchor.get("start_cp"), anchor.get("end_cp")
        atom_start, atom_end = atom.get("start_cp"), atom.get("end_cp")
        exact_text = anchor.get("exact_text")
        valid_quote_ids = isinstance(quote_ids, list) and all(nonempty_string(item) for item in quote_ids)
        if valid_quote_ids and len(quote_ids) != len(set(quote_ids)):
            valid_quote_ids = False
        valid_span = (
            isinstance(start_cp, int) and isinstance(end_cp, int)
            and isinstance(atom_start, int) and isinstance(atom_end, int)
            and atom_start <= start_cp < end_cp <= atom_end
            and isinstance(atom.get("text"), str)
            and nonempty_string(exact_text)
        )
        if valid_span:
            projected = atom["text"][start_cp - atom_start : end_cp - atom_start]
            valid_span = normalize_text(projected).strip() == normalize_text(exact_text).strip()
        if (
            not valid_span
            or anchor.get("text_sha256") != sha256_text(exact_text)
            or anchor.get("anchor_role") not in SCAFFOLD_ANCHOR_ROLES
            or not valid_quote_ids
            or not source_anchor_is_complete_for_version(
                exact_text, atom.get("text", ""), contract_version
            )
        ):
            report.error(
                "E_AUTHORING_SCAFFOLD_TAMPER",
                "semantic anchor 必须是当前 atom 的完整、逐字、hash 绑定来源锚",
                anchor_path,
            )

    anchor_id_set = set(anchor_map)
    for key in ("entry_anchor_ids", "action_anchor_ids", "exit_anchor_ids", "continuity_anchor_ids"):
        ids = _ordered_unique_strings(scaffold.get(key))
        if ids is None or any(item not in anchor_id_set for item in ids):
            report.error("E_AUTHORING_SCAFFOLD_TAMPER", f"{key} 必须有序引用锁定 semantic anchors", f"{scaffold_path}.{key}")

    scaffold_provenance = scaffold.get("field_provenance")
    if not isinstance(scaffold_provenance, dict) or set(scaffold_provenance) != LOCKED_SCAFFOLD_PROVENANCE_KEYS:
        report.error("E_AUTHORING_SCAFFOLD_TAMPER", "locked scaffold provenance exact keys 不匹配", f"{scaffold_path}.field_provenance")
    else:
        expected_ids = {
            "entry": scaffold.get("entry_anchor_ids"),
            "action_state_chain": scaffold.get("action_anchor_ids"),
            "exit": scaffold.get("exit_anchor_ids"),
            "continuity": scaffold.get("continuity_anchor_ids"),
            "shots": [
                anchor_id
                for shot in scaffold.get("shots", []) if isinstance(shot, dict)
                for anchor_id in shot.get("source_anchor_ids", []) if isinstance(anchor_id, str)
            ],
        }
        for key, record in scaffold_provenance.items():
            if record != {"status": "HELPER_DERIVED", "source_anchor_ids": expected_ids[key]}:
                report.error("E_AUTHORING_SCAFFOLD_TAMPER", "locked scaffold provenance 不是可复算 helper 投影", f"{scaffold_path}.field_provenance.{key}")

    shots = scaffold.get("shots")
    if not isinstance(shots, list):
        report.error("E_AUTHORING_SCAFFOLD_TAMPER", "locked scaffold shots 必须是数组", f"{scaffold_path}.shots")
        shots = []
    for index, shot in enumerate(shots, start=1):
        shot_path = f"{scaffold_path}.shots[{index - 1}]"
        if not isinstance(shot, dict) or set(shot) != LOCKED_SHOT_KEYS:
            report.error("E_AUTHORING_SCAFFOLD_TAMPER", "locked shot exact keys 不匹配", shot_path)
            continue
        refs = _ordered_unique_strings(shot.get("source_refs"))
        anchor_ids = _ordered_unique_strings(shot.get("source_anchor_ids"))
        quote_ids = shot.get("quote_ids")
        quote_ids_valid = isinstance(quote_ids, list) and all(nonempty_string(item) for item in quote_ids)
        if quote_ids_valid and len(quote_ids) != len(set(quote_ids)):
            quote_ids_valid = False
        if (
            shot.get("shot_id") != f"SH{index:03d}"
            or refs is None or any(ref not in unit_source_refs for ref in refs)
            or anchor_ids is None or any(item not in anchor_id_set for item in anchor_ids)
            or any(anchor_map[item].get("source_ref") not in refs for item in anchor_ids or [])
            or not quote_ids_valid
        ):
            report.error("E_AUTHORING_SCAFFOLD_TAMPER", "locked shot 不是当前来源窗口的有序 helper scaffold", shot_path)
        elif refs != list(dict.fromkeys(anchor_map[item]["source_ref"] for item in anchor_ids)) or quote_ids != list(
            dict.fromkeys(
                quote_id
                for item in anchor_ids
                for quote_id in anchor_map[item].get("quote_ids", [])
            )
        ):
            report.error(
                "E_AUTHORING_SCAFFOLD_TAMPER",
                "locked shot 的 source_refs/quote_ids 必须由 source_anchor_ids 唯一投影",
                shot_path,
            )
    flattened_anchor_ids = [
        anchor_id
        for shot in shots if isinstance(shot, dict)
        for anchor_id in shot.get("source_anchor_ids", []) if isinstance(anchor_id, str)
    ]
    ordered_anchor_ids = list(anchor_map)
    expected_continuity_ids = list(dict.fromkeys(ordered_anchor_ids[:1] + ordered_anchor_ids[-1:]))
    if (
        scaffold.get("entry_anchor_ids") != ordered_anchor_ids[:1]
        or scaffold.get("action_anchor_ids") != ordered_anchor_ids
        or scaffold.get("exit_anchor_ids") != ordered_anchor_ids[-1:]
        or scaffold.get("continuity_anchor_ids") != expected_continuity_ids
        or flattened_anchor_ids != ordered_anchor_ids
        or (
            scaffold.get("target_mode") == "EDITED_SEQUENCE"
            and scaffold.get("minimum_shots") != len(shots)
        )
        or (
            scaffold.get("target_mode") == "GENERATABLE_SHOT"
            and (scaffold.get("minimum_shots") != 0 or len(shots) != 1)
        )
    ):
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "locked scaffold 的入口/动作/出口/连续性/镜头必须是语义锚的可复算有序投影",
            scaffold_path,
        )
    return scaffold, anchor_map


def validate_v14_single_shot_eligibility(
    unit: dict[str, Any],
    scaffold: dict[str, Any],
    canonical_eligibility: dict[str, Any],
    contract_path: str,
    report: Report,
) -> dict[str, Any]:
    eligibility = unit.get("single_shot_eligibility")
    path = f"{contract_path.rsplit('.director_contract', 1)[0]}.single_shot_eligibility"
    if not isinstance(eligibility, dict) or set(eligibility) != SINGLE_SHOT_ELIGIBILITY_KEYS:
        report.error("E_AUTHORING_SCAFFOLD_TAMPER", "single_shot_eligibility exact keys 不匹配", path)
        return {}
    if eligibility != canonical_eligibility:
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "single_shot_eligibility 必须精确等于 canonical 来源与 feature 投影",
            path,
        )
    target_mode = unit.get("director_contract", {}).get("target_mode")
    if eligibility.get("eligible") is False and target_mode != "EDITED_SEQUENCE":
        report.error(
            "E_SINGLE_SHOT_ROUTE",
            "single_shot_eligibility=INELIGIBLE 必须路由为 EDITED_SEQUENCE",
            f"{contract_path}.target_mode",
        )
    if scaffold and scaffold.get("target_mode") != target_mode:
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "director_contract.target_mode 必须等于 locked scaffold 路由",
            f"{contract_path}.target_mode",
        )
    return eligibility


def validate_provenance_record(
    value: Any,
    record: Any,
    inference_map: dict[str, dict[str, Any]],
    allowed_refs: set[str],
    path: str,
    report: Report,
    code: str = "E_DIRECTOR_PROVENANCE",
) -> bool:
    """Validate one exact SOURCE or PROPOSED record against actual string leaves."""

    if not isinstance(record, dict):
        report.error(code, "provenance record 必须是对象", path)
        return False
    refs = record.get("source_refs")
    if not unique_strings(refs) or any(ref not in allowed_refs for ref in refs):
        report.error(code, "provenance 必须精确回链当前允许的 source_refs", path)
        return False
    if record.get("status") == "SOURCE_SUPPORTED":
        anchor = record.get("source_anchor")
        if (
            set(record) != {"status", "source_refs", "source_anchor"}
            or not nonempty_string(anchor)
            or not normalized_value_contains_exact_string(value, anchor)
        ):
            report.error(code, "SOURCE_SUPPORTED 必须把完整 source_anchor 作为真实字符串叶写入字段", path)
            return False
        return True
    if record.get("status") == "PROPOSED_DIRECTOR_INFERENCE":
        inference_id = record.get("inference_id")
        fragment = record.get("field_fragment")
        inference_text = inference_map.get(inference_id, {}).get("text", "") if isinstance(inference_id, str) else ""
        if (
            set(record) != {"status", "source_refs", "inference_id", "field_fragment"}
            or inference_id not in inference_map
            or refs != inference_map.get(inference_id, {}).get("source_refs")
            or not nonempty_string(fragment)
            or not normalized_value_contains_exact_string(value, fragment)
            or normalize_text(fragment).strip() not in normalize_text(str(inference_text)).strip()
        ):
            report.error(code, "PROPOSED provenance 必须用 fragment 同时绑定字段值与 inference", path)
            return False
        return True
    report.error(code, "provenance status 只能是 SOURCE_SUPPORTED 或 PROPOSED_DIRECTOR_INFERENCE", path)
    return False


def validate_v14_action_provenance(
    actions: Any,
    records: Any,
    locked_anchor_ids: list[str],
    anchor_map: dict[str, dict[str, Any]],
    inference_map: dict[str, dict[str, Any]],
    path: str,
    report: Report,
) -> None:
    """Validate source-prefix plus creative-suffix action chains item by item."""

    if (
        not isinstance(actions, list) or not actions
        or not all(nonempty_string(item) for item in actions)
        or not isinstance(records, list) or len(records) != len(actions)
    ):
        report.error(
            "E_DIRECTOR_PROVENANCE",
            "action_state_chain 与其 provenance 必须是等长非空数组",
            path,
        )
        return
    locked_texts = [
        anchor_map.get(anchor_id, {}).get("exact_text") for anchor_id in locked_anchor_ids
    ]
    allowed_refs = {
        anchor_map.get(anchor_id, {}).get("source_ref") for anchor_id in locked_anchor_ids
        if nonempty_string(anchor_map.get(anchor_id, {}).get("source_ref"))
    }
    if (
        any(not nonempty_string(text) for text in locked_texts)
        or [normalize_text(item).strip() for item in actions[: len(locked_texts)]]
        != [normalize_text(item).strip() for item in locked_texts]
    ):
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "action_state_chain 必须以前置顺序保留 locked semantic anchor exact_text",
            path,
        )
    for index, (action, record) in enumerate(zip(actions, records)):
        record_path = f"{path}[{index}]"
        if not isinstance(record, dict):
            report.error("E_DIRECTOR_PROVENANCE", "逐项 action provenance 必须是对象", record_path)
            continue
        if index < len(locked_anchor_ids):
            anchor = anchor_map.get(locked_anchor_ids[index], {})
            expected = {
                "status": "SOURCE_SUPPORTED",
                "source_refs": [anchor.get("source_ref")],
                "source_anchor": anchor.get("exact_text"),
            }
            if record != expected or not source_supported_value_is_exact(action, str(anchor.get("exact_text", ""))):
                report.error(
                    "E_AUTHORING_SCAFFOLD_TAMPER",
                    "锁定 action 项必须有 exact SOURCE_SUPPORTED provenance",
                    record_path,
                )
            continue
        inference_id = record.get("inference_id")
        fragment = record.get("field_fragment")
        inference_text = inference_map.get(inference_id, {}).get("text", "") if isinstance(inference_id, str) else ""
        if (
            set(record) != {"status", "source_refs", "inference_id", "field_fragment"}
            or record.get("status") != "PROPOSED_DIRECTOR_INFERENCE"
            or inference_id not in inference_map
            or not unique_strings(record.get("source_refs"))
            or any(ref not in allowed_refs for ref in record.get("source_refs", []))
            or record.get("source_refs") != inference_map.get(inference_id, {}).get("source_refs")
            or not nonempty_string(fragment)
            or normalize_text(fragment).strip() not in normalize_text(action).strip()
            or normalize_text(fragment).strip() not in normalize_text(str(inference_text)).strip()
        ):
            report.error(
                "E_DIRECTOR_PROVENANCE",
                "新增 action 项必须逐项绑定 finalizer 生成的 PROPOSED inference",
                record_path,
            )


V14_FINAL_SHOT_KEYS = {
    "shot_id", "purpose", "action_state_chain", "camera", "source_refs",
    "semantic_anchor_ids", "dialogue_slot_ids", "field_provenance",
}


def validate_v14_final_projection(
    unit: dict[str, Any],
    contract: dict[str, Any],
    scaffold: dict[str, Any],
    anchor_map: dict[str, dict[str, Any]],
    inference_map: dict[str, dict[str, Any]],
    unit_source_refs: set[str],
    contract_path: str,
    report: Report,
) -> None:
    """Require the final director surface to be the locked source projection plus creative overlay."""

    if not scaffold or not anchor_map:
        return
    anchor_texts = lambda ids: [anchor_map[item]["exact_text"] for item in ids if item in anchor_map]
    for field, ids in (
        ("entry", scaffold.get("entry_anchor_ids", [])),
        ("exit", scaffold.get("exit_anchor_ids", [])),
        ("continuity", scaffold.get("continuity_anchor_ids", [])[:1]),
    ):
        expected = anchor_texts(ids)
        if not expected or normalize_text(contract.get(field, "")).strip() != normalize_text(expected[0]).strip():
            report.error(
                "E_AUTHORING_SCAFFOLD_TAMPER",
                f"director_contract.{field} 必须逐字投影 locked semantic anchor",
                f"{contract_path}.{field}",
            )
    top_provenance = contract.get("field_provenance")
    action_records = top_provenance.get("action_state_chain") if isinstance(top_provenance, dict) else None
    validate_v14_action_provenance(
        contract.get("action_state_chain"), action_records,
        scaffold.get("action_anchor_ids", []), anchor_map, inference_map,
        f"{contract_path}.field_provenance.action_state_chain", report,
    )
    locked_hash = unit.get("locked_scaffold_sha256")
    expected_shot_provenance = {
        "status": "HELPER_DERIVED",
        "source_refs": list(unit.get("source_refs", [])),
        "locked_scaffold_sha256": locked_hash,
    }
    if not isinstance(top_provenance, dict) or top_provenance.get("shot_plan") != expected_shot_provenance:
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "shot_plan provenance 必须是可复算的 HELPER_DERIVED locked scaffold 投影",
            f"{contract_path}.field_provenance.shot_plan",
        )

    shot_plan = contract.get("shot_plan")
    locked_shots = scaffold.get("shots", [])
    if scaffold.get("target_mode") == "GENERATABLE_SHOT":
        if shot_plan != []:
            report.error(
                "E_SINGLE_SHOT_ROUTE",
                "GENERATABLE_SHOT 的 final shot_plan 必须精确为空数组",
                f"{contract_path}.shot_plan",
            )
        return
    if not isinstance(shot_plan, list) or len(shot_plan) != len(locked_shots):
        report.error(
            "E_AUTHORING_SCAFFOLD_TAMPER",
            "Sequence final shot_plan 必须与 locked shots 等长同序",
            f"{contract_path}.shot_plan",
        )
        return
    dialogue_ids = {
        item.get("dialogue_id")
        for item in contract.get("dialogue_inventory", [])
        if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
    }
    for index, (shot, locked) in enumerate(zip(shot_plan, locked_shots)):
        shot_path = f"{contract_path}.shot_plan[{index}]"
        if not isinstance(shot, dict) or set(shot) != V14_FINAL_SHOT_KEYS:
            report.error("E_AUTHORING_SCAFFOLD_TAMPER", "final shot 必须保留精确 8 键 shape", shot_path)
            continue
        expected_dialogue_ids = [item for item in locked["quote_ids"] if item in dialogue_ids]
        if (
            shot.get("shot_id") != locked.get("shot_id")
            or shot.get("source_refs") != locked.get("source_refs")
            or shot.get("semantic_anchor_ids") != locked.get("source_anchor_ids")
            or shot.get("dialogue_slot_ids") != expected_dialogue_ids
        ):
            report.error(
                "E_AUTHORING_SCAFFOLD_TAMPER",
                "final shot 的 ID/refs/semantic anchors/dialogue slots 必须由 locked shot 唯一投影",
                shot_path,
            )
        shot_provenance = shot.get("field_provenance")
        if not isinstance(shot_provenance, dict) or set(shot_provenance) != {
            "purpose", "action_state_chain", "camera",
        }:
            report.error("E_SEQUENCE_SHOT_PROVENANCE", "final shot provenance exact keys 不匹配", f"{shot_path}.field_provenance")
            continue
        validate_v14_action_provenance(
            shot.get("action_state_chain"), shot_provenance.get("action_state_chain"),
            locked.get("source_anchor_ids", []), anchor_map, inference_map,
            f"{shot_path}.field_provenance.action_state_chain", report,
        )
        for field in ("purpose", "camera"):
            validate_provenance_record(
                shot.get(field), shot_provenance.get(field), inference_map,
                set(locked.get("source_refs", [])), f"{shot_path}.field_provenance.{field}",
                report, "E_SEQUENCE_SHOT_PROVENANCE",
            )


def _replace_exact_source_body_with_pointer(
    text: str, source_body: str, pointer: str
) -> str:
    """Reserve one canonical source-body surface without harming substrings."""

    result = normalize_text(text)
    body = normalize_text(source_body).strip()
    if not body:
        return result
    for left, right in (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"')):
        result = result.replace(f"{left}{body}{right}", pointer)
    result = re.sub(
        rf"(?<![\u4e00-\u9fffA-Za-z0-9]){re.escape(body)}"
        rf"(?![\u4e00-\u9fffA-Za-z0-9])",
        pointer,
        result,
    )
    return result


def exact_source_body_count(text: Any, source_body: str) -> int:
    """Count a complete source body, never its occurrence inside a larger word."""

    if not isinstance(text, str):
        return 0
    body = normalize_text(source_body).strip()
    if not body:
        return 0
    return len(
        re.findall(
            rf"(?<![\u4e00-\u9fffA-Za-z0-9]){re.escape(body)}"
            rf"(?![\u4e00-\u9fffA-Za-z0-9])",
            normalize_text(text),
        )
    )


def _source_value_without_quote_bodies(
    value: Any,
    quote_texts: list[str],
    pointer: str = "〔原话见逐镜执行稿〕",
) -> Any:
    if isinstance(value, str):
        result = value
        for quote_text in sorted(set(quote_texts), key=len, reverse=True):
            result = _replace_exact_source_body_with_pointer(
                result, quote_text, pointer
            )
        return result
    if isinstance(value, list):
        return [
            _source_value_without_quote_bodies(item, quote_texts, pointer)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _source_value_without_quote_bodies(item, quote_texts, pointer)
            for key, item in value.items()
        }
    return value


def render_execution_beats_block(
    beats: list[dict[str, Any]],
    quote_assignments: list[dict[str, Any]] | None = None,
) -> str:
    quote_texts = [
        normalize_text(item.get("text", "")).strip()
        for item in quote_assignments or []
        if isinstance(item, dict) and nonempty_string(item.get("text"))
    ]
    safe_beats = _source_value_without_quote_bodies(
        beats, quote_texts, "〔原话见执行面〕"
    ) if quote_texts else beats
    return (
        "[[EXECUTION_BEATS]]\n"
        + json.dumps(safe_beats, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n[[/EXECUTION_BEATS]]"
    )


COPYABLE_EXECUTION_TITLE = "### 逐镜视频提示词（每条可单独复制）"


def extract_shared_creator_context(value: Any) -> str:
    """Keep only the author-written common setup before the first shot marker."""

    text = creator_prompt_surface(value).split(COPYABLE_EXECUTION_TITLE, 1)[0].strip()
    if not text:
        return ""
    marker = re.search(
        r"(?:第一镜|镜头\s*[一1１]|第\s*[一1１]\s*镜)\s*[：:]",
        text,
    )
    context = text[: marker.start()].strip() if marker else ""
    context = re.sub(r"^生成(?:一个|一段)?", "", context).strip()
    # The text before ``镜头一`` describes the whole authored sequence.  A
    # creator may naturally write "生成四个连续镜头" there; copying that
    # quantity into every standalone shot prompt creates a contradictory
    # request (one exported shot that also asks for four shots).  Keep the
    # medium/style context, but remove sequence-count grammar at this boundary.
    context = re.sub(
        r"^(?:本段|全段)?\s*"
        r"(?:[二三四五六七八九十百零〇两\d０-９]+)\s*(?:个|条|组)?\s*"
        r"(?:(?:可)?连续(?:剪辑)?|相互衔接)?\s*的?\s*",
        "",
        context,
    ).strip()
    return context.rstrip("。；;，, ")


def extract_creator_shot_sections(value: Any) -> list[str]:
    """Extract the author-written 第一镜/第二镜 sections before the compiled surface."""

    text = creator_prompt_surface(value).split(COPYABLE_EXECUTION_TITLE, 1)[0].strip()
    if not text:
        return []
    pattern = re.compile(
        r"(?:第[一二三四五六七八九十百零〇两\d０-９]+镜|镜头\s*[一二三四五六七八九十百零〇两\d０-９]+)\s*[：:]"
    )
    markers = list(pattern.finditer(text))
    sections: list[str] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        section = text[marker.end() : end].strip(" \t\r\n。；;")
        if section:
            sections.append(section)
    return sections


def _natural_sentence(value: Any) -> str:
    text = normalize_text(value).strip()
    if not text:
        return ""
    if text.endswith(("。", "！", "？", "；", "…")):
        return text
    if re.search(r"[。！？；…—][”’》）\]]$", text):
        return text
    return text + "。"


VISIBLE_ENDPOINT_RE = re.compile(
    r"(?:画面|构图|主体|人物|身体|手|手指|手掌|手势|眼|目光|视线|嘴|口型|"
    r"头|肩|衣|脚|腿|爪|尾|道具|书|牌|火焰|光|灯|帘|屏幕|控制台|设备|物体|波|尘|蛇|车|门|位置|"
    r"站|坐|蹲|跪|躺|走|跑|步|抬|转|倒|起身|回头|侧身|伸手|收手|"
    r"站稳|停住|停在|停步|落在|位于|保持|收住|消散|指向|看向|压住|进入|离开|同框)"
)
NONVISUAL_ENDPOINT_RE = re.compile(
    r"(?:对应原话完成后的状态|逐字对白见|本意|内心|不打算|并非真正|"
    r"不会参与|不属于|仅仅只是|语气|声音.{0,12}(?:压低|升高|褪去)|"
    r"世界观|设定|剧情上|意味着)"
)
CREATOR_AUDIO_RE = re.compile(
    r"(?:声音|声响|音效|环境声|人声|脚步|呼吸|摩擦|低鸣|灵鸣|远雷|"
    r"嗤笑|笑出声|爆鸣|轰鸣|衣料|布料|竹条|蛇鳞|火焰收束)"
)


def _endpoint_is_visible(value: Any) -> bool:
    text = normalize_text(value).strip(" \t\r\n。；;，,：:")
    if not text or "对应原话完成后的状态" in text:
        return False
    if NONVISUAL_ENDPOINT_RE.search(text) and not VISIBLE_ENDPOINT_RE.search(text):
        return False
    return bool(VISIBLE_ENDPOINT_RE.search(text))


def _extract_visible_endpoint(
    creator_detail: str,
    camera: str,
    source_action: str,
    exit_state: str,
    quote_bodies: list[str],
) -> str:
    """Choose an authored/source-supported state that a camera can show."""

    candidates: list[str] = []
    for pattern in (
        r"结束画面(?:清楚显示|停在|停于|是|为)?\s*[：:]?\s*(.+?)(?=(?:\n|摄影[：:]|声音[：:]|限制[：:]|不要|不得|不加|$))",
        r"(?:镜头|摄影|焦点|画面)?[^。；\n]{0,80}?(?:结束|停)(?:在|于)\s*([^。；\n]+)",
    ):
        candidates.extend(
            match.group(1).strip(" \t\r\n。；;，,")
            for match in re.finditer(pattern, creator_detail, flags=re.DOTALL)
            if match.group(1).strip()
        )
    candidates.extend(
        match.group(1).strip(" \t\r\n。；;，,")
        for match in re.finditer(
            r"(?:结束|停)(?:在|于)\s*([^。；\n]+)", camera
        )
        if match.group(1).strip()
    )
    creator_clauses = [
        item.strip(" \t\r\n。；;，,")
        for item in re.split(r"[。；\n]", creator_detail)
        if item.strip()
    ]
    candidates.extend(reversed(creator_clauses))
    safe_exit = exit_state
    for quote in quote_bodies:
        safe_exit = _source_value_without_quote_bodies(safe_exit, [quote], "")
    candidates.append(safe_exit.strip(" \t\r\n。；;，,：:"))
    action_clauses = [
        item.strip(" \t\r\n。；;，,")
        for item in re.split(r"[。；\n]", source_action)
        if item.strip()
    ]
    candidates.extend(reversed(action_clauses))
    for candidate in candidates:
        if any(
            exact_source_body_count(candidate, quote) > 0
            for quote in quote_bodies
            if quote
        ):
            continue
        if _endpoint_is_visible(candidate):
            return candidate
    return ""


def _creator_audio_detail(value: str) -> str:
    """Return current-shot sound wording without importing another shot's plan."""

    explicit_lines = [
        re.sub(
            r"^(?:声音与口型|声音|声响|音效|环境声)\s*[：:]\s*",
            "",
            line.strip(),
        ).strip(" \t\r\n。；;，,")
        for line in normalize_text(value).splitlines()
        if re.match(
            r"^\s*(?:声音与口型|声音|声响|音效|环境声)\s*[：:]",
            line,
        )
    ]
    explicit_lines = [item for item in explicit_lines if item]
    if explicit_lines:
        return "；".join(dict.fromkeys(explicit_lines[:2]))

    clauses = [
        item.strip(" \t\r\n。；;，,")
        for item in re.split(r"[。；\n]", normalize_text(value))
        if item.strip()
    ]
    selected = [
        re.sub(r"^(?:声音与口型|声音|声响|音效|环境声)\s*[：:]\s*", "", item).strip()
        for item in clauses
        if CREATOR_AUDIO_RE.search(item)
        and not re.search(r"(?:不加|不要|不得|禁止|关闭).{0,18}(?:声音|声响|音效|音乐)", item)
    ]
    if not selected:
        return ""
    return "；".join(dict.fromkeys(selected[:2]))


def _sound_direction_for_creator(
    beat: dict[str, Any],
    assignments: list[dict[str, Any]],
    creator_detail: str = "",
) -> str:
    kinds = {str(item.get("kind", "")) for item in assignments if isinstance(item, dict)}
    spoken_count = sum(
        1
        for item in assignments
        if isinstance(item, dict) and item.get("kind") == "SPOKEN_DIALOGUE"
    )
    notes: list[str] = []
    if "SPOKEN_DIALOGUE" in kinds:
        if "原文明确" in creator_detail and "画外音" in creator_detail:
            notes.append("保留原文已经明确的画外音声源；画面中的身体不伪装成正在开口")
        else:
            notes.append(
                "上面每句人物原话各出现一次；发声身体、口型、停顿和被打断的位置分别与原话同步"
                if spoken_count > 1
                else "上面这句人物原话只出现一次；发声身体、口型、停顿和被打断的位置与原话同步"
            )
    if "NON_LEXICAL_VOCALIZATION" in kinds:
        notes.append("人物发声与当时的呼吸、表情和动作同步")
    if "SFX" in kinds:
        notes.append("声响准确落在物体接触或动作发生的瞬间")
    if "QUOTED_TEXT" in kinds:
        notes.append("引号内文字只作为画面文字出现，不朗读")
    if "INTERNAL_THOUGHT" in kinds:
        notes.append("内心文字不发声，除非原文已经明确为画外音")
    creator_audio = _creator_audio_detail(creator_detail)
    if creator_audio:
        notes.append(creator_audio)
    if notes:
        label = "声音与口型：" if kinds & {"SPOKEN_DIALOGUE", "NON_LEXICAL_VOCALIZATION"} else "声音："
        return label + "；".join(notes) + "。"

    audio = beat.get("audio_order") if isinstance(beat.get("audio_order"), list) else []
    useful = [
        normalize_text(item).strip()
        for item in audio
        if isinstance(item, str)
        and item.strip()
        and "本镜无来源口播或明确声响" not in item
    ]
    if useful:
        return "声音：" + "；".join(useful) + "。"
    return "声音：只保留当前可见动作自然产生的现场声和空间底噪；人物嘴部保持闭合，音乐轨留空。"


def _creator_visual_detail(value: str) -> str:
    """Remove author-labelled sound/end lines before rendering the action line."""

    kept = [
        line
        for line in normalize_text(value).splitlines()
        if not re.match(r"^\s*(?:声音与口型|声音|声响|音效|环境声)\s*[：:]", line)
    ]
    text = "\n".join(kept).strip()
    text = re.sub(
        r"\s*结束画面(?:清楚显示|停在|停于|是|为)?\s*[：:]?\s*[^\n]+",
        "",
        text,
    )
    return text.strip()


def _friendly_duration(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return ""
    rounded = max(1, int(seconds + 0.5))
    return str(rounded)


def _clean_negative_clause(value: Any) -> str:
    text = normalize_text(value).strip().rstrip("。；; ")
    return text


def _naturalize_creator_audio_cue(value: str) -> str:
    text = normalize_text(value).strip()
    return re.sub(r"^来源声响发出(?:一声)?", "画面中清楚听到", text)


def _hydrate_creator_section(
    section: str,
    assignments: list[dict[str, Any]],
) -> str:
    """Put immutable local quote bodies back into an author section for display."""

    hydrated = section
    spoken_pointer = "〔逐字对白见下方逐镜执行稿〕"
    nonspoken_pointer = "〔由固定镜头提示写入〕"
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        quote_text = normalize_text(assignment.get("text", "")).strip()
        if not quote_text:
            continue
        kind = assignment.get("kind")
        pointer = spoken_pointer if kind == "SPOKEN_DIALOGUE" else nonspoken_pointer
        if pointer in hydrated:
            replacement = f"“{quote_text}”" if kind == "SPOKEN_DIALOGUE" else ""
            hydrated = hydrated.replace(pointer, replacement, 1)
            if replacement and re.search(r"[。！？!?…—]$", quote_text):
                hydrated = re.sub(
                    re.escape(replacement) + r"[。！？!?；;，,]+",
                    replacement,
                    hydrated,
                    count=1,
                )
    hydrated = hydrated.replace(spoken_pointer, "").replace(nonspoken_pointer, "")
    hydrated = re.sub(r"([。！？…—][”」』\"]?)[；;，,]", r"\1", hydrated)
    hydrated = re.sub(
        r"([。！？…—][”」』\"])(?=[\u4e00-\u9fff])",
        r"\1\n",
        hydrated,
    )
    return hydrated.strip()


def render_copyable_execution_surface(
    beats: list[dict[str, Any]],
    quote_assignments: list[dict[str, Any]],
    *,
    shot_plan: list[dict[str, Any]] | None = None,
    shared_context: str = "",
    creator_shot_sections: list[str] | None = None,
    negative_clauses: list[str] | None = None,
    creator_friendly_audio: bool = False,
) -> str:
    """Render natural, standalone shot prompts; never expose the machine ledger."""

    assignments_by_shot: dict[str, list[dict[str, Any]]] = {}
    for assignment in quote_assignments:
        if not isinstance(assignment, dict):
            continue
        assignments_by_shot.setdefault(str(assignment.get("shot_id", "")), []).append(
            assignment
        )
    purpose_by_shot = {
        str(item.get("shot_id", "")): normalize_text(item.get("purpose", "")).strip()
        for item in shot_plan or []
        if isinstance(item, dict)
    }
    common = _natural_sentence(shared_context)
    sections = creator_shot_sections or []
    negatives = [
        _clean_negative_clause(item)
        for item in negative_clauses or []
        if _clean_negative_clause(item)
    ]
    lines = [COPYABLE_EXECUTION_TITLE, ""]
    for index, beat in enumerate(beats, start=1):
        if not isinstance(beat, dict):
            continue
        shot_id = str(beat.get("shot_id", ""))
        local_assignments = assignments_by_shot.get(shot_id, [])
        source_action = normalize_text(beat.get("observable_action", "")).strip().replace(
            " → ", "随后，"
        )
        camera = normalize_text(beat.get("camera", "")).strip()
        exit_state = normalize_text(beat.get("exit_state", "")).strip()
        creator_detail = normalize_text(
            sections[index - 1] if index - 1 < len(sections) else ""
        ).strip()
        creator_detail = _hydrate_creator_section(creator_detail, local_assignments)
        if any(
            fragment in creator_detail
            for fragment in (
                "逐字对白见下方",
                "此处同步说出或发出",
                "按本镜构图落位",
                "本镜无来源口播或明确声响",
                "{{VERBATIM_DIALOGUE_SLOT:",
            )
        ):
            creator_detail = ""
        action = _creator_visual_detail(creator_detail) or source_action
        for assignment in local_assignments:
            if not isinstance(assignment, dict):
                continue
            kind = assignment.get("kind")
            if kind == "SPOKEN_DIALOGUE":
                continue
            quote_text = normalize_text(assignment.get("text", "")).strip()
            if not quote_text:
                continue
            replacement = {
                "NON_LEXICAL_VOCALIZATION": "这声人物发声",
                "SFX": "这一下声响",
                "QUOTED_TEXT": "这段画面文字",
                "INTERNAL_THOUGHT": "这段内心内容",
            }.get(str(kind), "这段声音或文字")
            action = _source_value_without_quote_bodies(action, [quote_text], replacement)
        inserted_quote_lines: list[str] = []
        for assignment in local_assignments:
            if not isinstance(assignment, dict):
                continue
            quote_text = normalize_text(assignment.get("text", "")).strip()
            if not quote_text or exact_source_body_count(action, quote_text):
                continue
            speaker = normalize_text(assignment.get("speaker", "")).strip()
            kind = assignment.get("kind")
            if kind == "SPOKEN_DIALOGUE":
                inserted_quote_lines.append(
                    _natural_sentence(f"对白：{speaker or '人物'}逐字说：“{quote_text}”")
                )
            elif kind == "NON_LEXICAL_VOCALIZATION":
                audio = beat.get("audio_order") if isinstance(beat.get("audio_order"), list) else []
                exact_audio = next(
                    (
                        normalize_text(item).strip()
                        for item in audio
                        if isinstance(item, str) and quote_text in normalize_text(item)
                    ),
                    "",
                )
                inserted_quote_lines.append(
                    _natural_sentence(exact_audio or f"{speaker or '人物'}发出一声“{quote_text}”")
                )
            elif kind == "SFX":
                audio = beat.get("audio_order") if isinstance(beat.get("audio_order"), list) else []
                exact_audio = next(
                    (
                        normalize_text(item).strip()
                        for item in audio
                        if isinstance(item, str) and quote_text in normalize_text(item)
                    ),
                    "",
                )
                inserted_quote_lines.append(
                    _natural_sentence(
                        _naturalize_creator_audio_cue(exact_audio)
                        if exact_audio and creator_friendly_audio
                        else exact_audio or f"声响：动作发生时清楚听到“{quote_text}”"
                    )
                )
            elif kind == "QUOTED_TEXT":
                inserted_quote_lines.append(f"- 画面文字（不朗读）：“{quote_text}”")
            elif kind == "INTERNAL_THOUGHT":
                inserted_quote_lines.append(_natural_sentence(f"内心内容“{quote_text}”，不发声"))
        purpose = purpose_by_shot.get(shot_id, "")
        duration = _friendly_duration(beat.get("duration_seconds"))
        prompt_lines = [
            _natural_sentence(
                f"生成一段约{duration}秒的镜头，{shared_context}"
                if duration and shared_context
                else f"生成这一镜，{shared_context}" if shared_context else f"生成一段约{duration}秒的镜头"
            ),
        ]
        if purpose:
            prompt_lines.append(_natural_sentence(f"叙事目标：{purpose}"))
        prompt_lines.append(_natural_sentence(f"画面与表演：{action}"))
        if camera:
            prompt_lines.append(_natural_sentence(f"摄影：{camera}"))
        prompt_lines.extend(inserted_quote_lines)
        prompt_lines.append(
            _sound_direction_for_creator(beat, local_assignments, creator_detail)
        )
        local_quote_bodies = [
            normalize_text(item.get("text", "")).strip()
            for item in local_assignments
            if isinstance(item, dict) and nonempty_string(item.get("text"))
        ]
        visible_endpoint = _extract_visible_endpoint(
            creator_detail,
            camera,
            source_action,
            exit_state,
            local_quote_bodies,
        )
        if any(quote.endswith("——") for quote in local_quote_bodies):
            if visible_endpoint:
                prompt_lines.append(
                    _natural_sentence(
                        f"结束画面：{visible_endpoint}；对白停在破折号处，意思尚未说完，下一镜立即打断"
                    )
                )
        elif visible_endpoint:
            prompt_lines.append(_natural_sentence(f"结束画面：{visible_endpoint}"))
        if negatives:
            prompt_lines.append("限制：" + "；".join(negatives) + "。")
        prompt_text = "\n".join(item for item in prompt_lines if item)
        lines.extend(
            [
                f"#### 镜头 {index}｜建议时长约 {duration or beat.get('duration_seconds', '')} 秒",
                "",
                *([f"这一镜要完成：{purpose}", ""] if purpose else []),
                "可直接复制：",
                "",
                prompt_text,
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def copyable_execution_surface_findings(value: Any) -> list[str]:
    """Review the final creator-facing shot prompts, not only their source fields."""

    text = normalize_text(value)
    sections = re.split(r"(?m)^####\s*镜头\s*\d+[^\n]*\n", text)[1:]
    findings: list[str] = []
    if not sections:
        return ["没有找到可单独复制的逐镜提示词"]
    for index, section in enumerate(sections, start=1):
        copy_part = section.split("可直接复制：", 1)[-1].strip()
        first_line = next((line.strip() for line in copy_part.splitlines() if line.strip()), "")
        if re.search(
            r"生成.{0,24}(?:[二三四五六七八九十百零〇两\d０-９]+)\s*(?:个|条|组)?\s*"
            r"(?:(?:可)?连续(?:剪辑)?|相互衔接).{0,10}镜头",
            first_line,
        ):
            findings.append(f"镜头 {index} 的单镜提示词仍要求一次生成多个镜头")
        leaked = next(
            (
                phrase
                for phrase in (
                    "对应原话完成后的状态",
                    "逐字对白见下方",
                    "此处同步说出或发出",
                    "按本镜构图落位",
                )
                if phrase in copy_part
            ),
            "",
        )
        if leaked:
            findings.append(f"镜头 {index} 仍含占位话“{leaked}”")
        endpoints = re.findall(r"(?m)^结束画面：(.+)$", copy_part)
        if len(endpoints) != 1 or not _endpoint_is_visible(endpoints[0]):
            findings.append(f"镜头 {index} 缺少可直接看见的唯一结束画面")
        sound_lines = re.findall(r"(?m)^声音(?:与口型)?：(.+)$", copy_part)
        body_without_sound = re.sub(r"(?m)^声音(?:与口型)?：.+$", "", copy_part)
        if any(
            re.search(r"(?:没有来源对白或明确声响|其他无来源声音保持关闭)", item)
            for item in sound_lines
        ) and CREATOR_AUDIO_RE.search(body_without_sound):
            findings.append(f"镜头 {index} 的声音说明与同一提示词前文冲突")
        if any("只保留当前可见动作自然产生的现场声和空间底噪" in item for item in sound_lines):
            findings.append(f"镜头 {index} 仍使用通用声音占位，必须写明本镜实际声音或明确静默范围")
    return findings


def expected_shot_handoffs(
    beats: list[dict[str, Any]],
    quote_assignments: list[dict[str, Any]],
    creator_shot_sections: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build an adjacent-shot baton ledger from the actual compiled shots."""

    assignments_by_shot: dict[str, list[dict[str, Any]]] = {}
    for assignment in quote_assignments:
        if isinstance(assignment, dict):
            assignments_by_shot.setdefault(str(assignment.get("shot_id", "")), []).append(
                assignment
            )
    sections = creator_shot_sections or []
    result: list[dict[str, Any]] = []
    for index in range(max(0, len(beats) - 1)):
        previous = beats[index]
        following = beats[index + 1]
        if not isinstance(previous, dict) or not isinstance(following, dict):
            continue
        previous_assignments = assignments_by_shot.get(str(previous.get("shot_id", "")), [])
        previous_quotes = [
            normalize_text(item.get("text", "")).strip()
            for item in previous_assignments
            if isinstance(item, dict) and nonempty_string(item.get("text"))
        ]
        creator_detail = normalize_text(
            sections[index] if index < len(sections) else ""
        ).strip()
        handoff_out = _extract_visible_endpoint(
            creator_detail,
            normalize_text(previous.get("camera", "")).strip(),
            normalize_text(previous.get("observable_action", "")).strip(),
            normalize_text(previous.get("exit_state", "")).strip(),
            previous_quotes,
        )
        following_creator_detail = normalize_text(
            sections[index + 1] if index + 1 < len(sections) else ""
        ).strip()
        following_action = normalize_text(following.get("observable_action", "")).strip()
        following_visual = _creator_visual_detail(following_creator_detail)
        receiver_source = following_visual or following_action
        receiver_in = next(
            (
                item.strip(" \t\r\n。；;，,：:")
                for item in re.split(r"[。；\n]|\s+→\s+", receiver_source)
                if item.strip()
            ),
            normalize_text(following.get("entry_state", "")).strip(),
        )
        all_quote_texts = [
            normalize_text(item.get("text", "")).strip()
            for item in quote_assignments
            if isinstance(item, dict) and nonempty_string(item.get("text"))
        ]
        for quote in all_quote_texts:
            receiver_in = _source_value_without_quote_bodies(receiver_in, [quote], "")
        receiver_in = receiver_in.strip(" \t\r\n。；;，,：:") or handoff_out
        completed_action = _creator_visual_detail(creator_detail) or normalize_text(
            previous.get("observable_action", "")
        ).strip()
        for assignment in quote_assignments:
            if not isinstance(assignment, dict):
                continue
            quote = normalize_text(assignment.get("text", "")).strip()
            if not quote:
                continue
            replacement = (
                "人物原话"
                if assignment.get("kind") == "SPOKEN_DIALOGUE"
                else "人物发声"
                if assignment.get("kind") == "NON_LEXICAL_VOCALIZATION"
                else "画面文字"
                if assignment.get("kind") == "QUOTED_TEXT"
                else "声响"
            )
            completed_action = _source_value_without_quote_bodies(
                completed_action, [quote], replacement
            )
        completed_action = re.sub(r"声响的?一声", "一次明确声响", completed_action)
        interrupted = any(quote.endswith("——") for quote in previous_quotes)
        transition = bool(
            re.search(
                r"(?:同一时间|与此同时|多年后|一个月后|次日|翌日|清晨|夜晚|切到|切入|转入|换场)",
                following_action,
            )
        )
        previous_audio = _creator_audio_detail(creator_detail)
        following_audio = _creator_audio_detail(following_creator_detail)
        for assignment in quote_assignments:
            if not isinstance(assignment, dict):
                continue
            quote = normalize_text(assignment.get("text", "")).strip()
            if not quote:
                continue
            kind = assignment.get("kind")
            replacement = (
                "本镜固定原话"
                if kind == "SPOKEN_DIALOGUE"
                else "本镜人物发声"
                if kind == "NON_LEXICAL_VOCALIZATION"
                else "本镜画面文字"
                if kind == "QUOTED_TEXT"
                else "本镜固定声响"
            )
            previous_audio = _source_value_without_quote_bodies(
                previous_audio, [quote], replacement
            )
            following_audio = _source_value_without_quote_bodies(
                following_audio, [quote], replacement
            )
        if interrupted:
            audio_bridge = "上一镜未说完的对白直接跨切到下一镜，不重说句首"
        elif previous_audio or following_audio:
            previous_audio = previous_audio or "上一镜现场声自然收住"
            following_audio = following_audio or "下一镜从可见动作产生的现场声进入"
            audio_bridge = (
                f"切点前以“{previous_audio}”收住；换场后从“{following_audio}”重新建立声场"
                if transition
                else f"上一镜以“{previous_audio}”交出；下一镜从“{following_audio}”接入；一次性声响不重放"
            )
        elif transition:
            audio_bridge = "换场切点收净上一镜一次性声音，下一镜从新空间的声音开始"
        else:
            audio_bridge = "上一镜的一次性声响不在下一镜重放；同一地点的自然环境声保持连续"
        result.append(
            {
                "from_shot_id": previous.get("shot_id"),
                "to_shot_id": following.get("shot_id"),
                "handoff_out": handoff_out,
                "receiver_in": receiver_in,
                "completed_action": completed_action,
                "motion_and_space": normalize_text(following.get("spatial_position", "")).removeprefix(
                    "按本镜构图落位："
                ).strip(),
                "prop_and_eyeline": (
                    f"上一镜以“{handoff_out}”交出；下一镜从“{receiver_in}”开始，"
                    "已有道具、身体朝向和视线只能通过画面内动作改变"
                ),
                "lighting": (
                    "这里发生明确换场，上一镜光线在切点结束，下一镜按新地点与时段重新建立主光"
                    if transition
                    else "同一地点延续上一镜主光方向、阴影侧和曝光层级"
                ),
                "audio_bridge": audio_bridge,
            }
        )
    return result


def prompt_layer_independence_findings(
    master: Any,
    draft: Any,
    helper_owned_visible_cues: list[str] | None = None,
) -> list[str]:
    """Detect copied creator payloads hidden behind tiny boilerplate changes."""

    master_text = creator_prompt_surface(master)
    draft_text = creator_prompt_surface(draft)
    if helper_owned_visible_cues:
        master_text = strip_helper_owned_visible_quote_block(
            master_text, helper_owned_visible_cues
        )
        draft_text = strip_helper_owned_visible_quote_block(
            draft_text, helper_owned_visible_cues
        )
    findings: list[str] = []
    if any(phrase in master_text or phrase in draft_text for phrase in GENERIC_PROMPT_FILLER_PHRASES):
        findings.append("GENERIC_PROMPT_FILLER")

    def reduced(value: str) -> str:
        text = re.sub(r"\{\{VERBATIM_DIALOGUE_SLOT:[A-Za-z0-9._-]+\}\}", "", value)
        for phrase in GENERIC_PROMPT_FILLER_PHRASES:
            text = text.replace(phrase, "")
        return re.sub(r"[\s，。；：、,.!?！？\[\]{}()（）\"'“”]+", "", text)

    master_reduced = reduced(master_text)
    draft_reduced = reduced(draft_text)
    if master_reduced and master_reduced == draft_reduced:
        findings.append("PROMPT_LAYER_SAME_CORE")
    elif master_reduced and draft_reduced:
        match = difflib.SequenceMatcher(None, master_reduced, draft_reduced, autojunk=False).find_longest_match(
            0, len(master_reduced), 0, len(draft_reduced)
        )
        if match.size >= 80:
            findings.append("PROMPT_LAYER_SHARED_LONG_BLOCK")
    return findings


def _prompt_source_value_without_dialogue(value: Any, dialogue_texts: list[str]) -> Any:
    """Keep helper source actions while reserving spoken text for its one slot."""

    return _source_value_without_quote_bodies(
        value, dialogue_texts, "〔逐字对白见执行面〕"
    )


def expected_director_prompt_block(contract: dict[str, Any], layer: str = "DRAFT") -> str:
    dialogue_texts = list(dict.fromkeys(
        normalize_text(item["text"]).strip()
        for item in (
            contract.get("quote_assignments", [])
            if isinstance(contract.get("quote_assignments"), list)
            else contract.get("dialogue_inventory", [])
        )
        if isinstance(item, dict)
        and item.get("kind") in {"SPOKEN_DIALOGUE", "VERBATIM_DIALOGUE"}
        and nonempty_string(item.get("text"))
    ))
    shot_plan = contract.get("shot_plan") if isinstance(contract.get("shot_plan"), list) else []
    safe_shots = [
        {
            "shot_id": shot.get("shot_id"),
            "purpose": _prompt_source_value_without_dialogue(
                shot.get("purpose"), dialogue_texts
            ),
            "action_state_chain": _prompt_source_value_without_dialogue(
                shot.get("action_state_chain"), dialogue_texts
            ),
            "camera": _prompt_source_value_without_dialogue(
                shot.get("camera"), dialogue_texts
            ),
        }
        for shot in shot_plan
        if isinstance(shot, dict)
    ]
    if layer == "MP":
        marker = "MASTER_DIRECTOR_DESIGN_BLOCK"
        projection = {
            "target_mode": contract.get("target_mode"),
            "entry": _prompt_source_value_without_dialogue(contract.get("entry"), dialogue_texts),
            "dramatic_action": _prompt_source_value_without_dialogue(
                contract.get("action_state_chain"), dialogue_texts
            ),
            "performance_intent": _prompt_source_value_without_dialogue(
                contract.get("performance"), dialogue_texts
            ),
            "visual_strategy": _prompt_source_value_without_dialogue(
                contract.get("camera"), dialogue_texts
            ),
            "sound_strategy": _prompt_source_value_without_dialogue(
                contract.get("sound"), dialogue_texts
            ),
            "exit": _prompt_source_value_without_dialogue(contract.get("exit"), dialogue_texts),
            "continuity": _prompt_source_value_without_dialogue(
                contract.get("continuity"), dialogue_texts
            ),
            "planned_shot_count": len(safe_shots),
        }
    elif layer in {"DRAFT", "NEUTRAL_EXECUTION"}:
        marker = (
            "NEUTRAL_EXECUTION_DIRECTOR_BLOCK"
            if layer == "NEUTRAL_EXECUTION" else "DRAFT_DIRECTOR_EXECUTION_BLOCK"
        )
        projection = {
            "target_mode": contract.get("target_mode"),
            "continuous_time_space": contract.get("continuous_time_space"),
            "entry": _prompt_source_value_without_dialogue(contract.get("entry"), dialogue_texts),
            "action_state_chain": _prompt_source_value_without_dialogue(
                contract.get("action_state_chain"), dialogue_texts
            ),
            "performance": _prompt_source_value_without_dialogue(
                contract.get("performance"), dialogue_texts
            ),
            "camera": _prompt_source_value_without_dialogue(
                contract.get("camera"), dialogue_texts
            ),
            "sound": _prompt_source_value_without_dialogue(
                contract.get("sound"), dialogue_texts
            ),
            "exit": _prompt_source_value_without_dialogue(contract.get("exit"), dialogue_texts),
            "continuity": _prompt_source_value_without_dialogue(
                contract.get("continuity"), dialogue_texts
            ),
            "shot_plan": safe_shots,
        }
    else:
        raise ValueError("director prompt layer must be MP, DRAFT, or NEUTRAL_EXECUTION")
    return (
        f"[[{marker}]]\n"
        + json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + f"\n[[/{marker}]]"
    )


def validate_r5_prompt_compilation(
    unit: dict[str, Any], atom_map: dict[str, dict[str, Any]], path: str, report: Report
) -> None:
    bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    expected_source = expected_source_prompt_block(unit, atom_map)
    for layer in ("master_prompt", "draft_prompt"):
        artifact = bundle.get(layer) if isinstance(bundle.get(layer), dict) else {}
        text = normalize_text(artifact.get("text", "")) if isinstance(artifact.get("text"), str) else ""
        if text.count(expected_source) != 1:
            report.error(
                "E_PROMPT_SOURCE_BLOCK",
                "r7 MP/DRAFT 必须恰含一份 finalizer 编译的来源 refs/hash 绑定，禁止复制全文",
                f"{path}.prompt_bundle.{layer}",
            )
        director_layer = "MP" if layer == "master_prompt" else "DRAFT"
        expected_director = expected_director_prompt_block(director, director_layer)
        if text.count(expected_director) != 1:
            report.error(
                "E_PROMPT_DIRECTOR_BLOCK",
                "r6 MP/DRAFT 必须恰含一份 finalizer 编译的完整导演执行块",
                f"{path}.prompt_bundle.{layer}",
            )
        if "{{VERBATIM_DIALOGUE_SLOT:" in text:
            report.error("E_DIALOGUE_SLOT_UNRESOLVED", "成品 Prompt 禁止残留对白 slot", f"{path}.prompt_bundle.{layer}")

    master = bundle.get("master_prompt") if isinstance(bundle.get("master_prompt"), dict) else {}
    draft = bundle.get("draft_prompt") if isinstance(bundle.get("draft_prompt"), dict) else {}
    expected_beats_block = render_execution_beats_block(expected_execution_beats_v14(unit))
    draft_text = normalize_text(draft.get("text", "")) if isinstance(draft.get("text"), str) else ""
    master_text = normalize_text(master.get("text", "")) if isinstance(master.get("text"), str) else ""
    if draft_text.count(expected_beats_block) != 1 or "[[EXECUTION_BEATS]]" in master_text:
        report.error(
            "E_EXECUTION_BEAT",
            "DRAFT 必须恰含一份可复算 EXECUTION_BEATS，MASTER 不得复制执行块",
            f"{path}.prompt_bundle",
        )

    master_surface = creator_prompt_surface(master.get("text"))
    draft_surface = creator_prompt_surface(draft.get("text"))
    if master_surface and draft_surface and master_surface == draft_surface:
        report.error(
            "E_PROMPT_LAYER_DUPLICATE",
            "MASTER 必须表达导演设计，DRAFT 必须转成逐镜执行；两层创作者正文不得同文",
            f"{path}.prompt_bundle",
        )
    independence_findings = prompt_layer_independence_findings(master.get("text"), draft.get("text"))
    if "GENERIC_PROMPT_FILLER" in independence_findings:
        report.error(
            "E_AUTHORING_GENERIC_FILLER",
            "正式 Prompt 禁止使用自测/占位模板语句代替具体导演设计",
            f"{path}.prompt_bundle",
        )
    if (
        len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", draft_surface)) < 24
        or "[[" in draft_surface
        or re.search(r'"(?:target_mode|source_refs|shot_plan|director_contract)"\s*:', draft_surface)
    ):
        report.error(
            "E_PROMPT_WORKING_DRAFT",
            "每个 Unit 必须有可直接复制的自然语言提示词工作稿，不能用 SOURCE/JSON/导演摘要冒充",
            f"{path}.prompt_bundle.draft_prompt",
        )
    if any(item.startswith("PROMPT_LAYER_") for item in independence_findings):
        report.error(
            "E_PROMPT_LAYER_DUPLICATE",
            "MASTER 与 DRAFT 不得共享同一长导演/JSON 载荷后仅改通用前后缀",
            f"{path}.prompt_bundle",
        )


def validate_v13_prompt_compilation(
    unit: dict[str, Any],
    atom_map: dict[str, dict[str, Any]],
    source_dialogue_inventory: list[dict[str, Any]],
    path: str,
    report: Report,
    contract_version: str = CONTRACT_VERSION,
) -> None:
    bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    master = bundle.get("master_prompt") if isinstance(bundle.get("master_prompt"), dict) else {}
    transform = bundle.get("transform_plan") if isinstance(bundle.get("transform_plan"), dict) else {}
    neutral = (
        bundle.get("neutral_execution_prompt")
        if isinstance(bundle.get("neutral_execution_prompt"), dict) else {}
    )
    master_text = normalize_text(master.get("text", "")) if isinstance(master.get("text"), str) else ""
    transform_text = normalize_text(transform.get("text", "")) if isinstance(transform.get("text"), str) else ""
    neutral_text = normalize_text(neutral.get("text", "")) if isinstance(neutral.get("text"), str) else ""
    source_block = expected_source_prompt_block(unit, atom_map)
    if master_text.count(source_block) != 1 or neutral_text.count(source_block) != 1:
        report.error(
            "E_PROMPT_SOURCE_BLOCK",
            "MASTER and NEUTRAL_EXECUTION_PROMPT must each bind exactly one frozen source window",
            f"{path}.prompt_bundle",
        )
    if source_block in transform_text:
        report.error(
            "E_PROMPT_LAYER_ROLE_CONFLICT",
            "TRANSFORM_PLAN must reference preservation responsibilities, not copy the source body",
            f"{path}.prompt_bundle.transform_plan",
        )
    if master_text.count(expected_director_prompt_block(director, "MP")) != 1:
        report.error(
            "E_PROMPT_DIRECTOR_BLOCK", "MASTER director design block is missing or duplicated",
            f"{path}.prompt_bundle.master_prompt",
        )
    if neutral_text.count(
        expected_director_prompt_block(director, "NEUTRAL_EXECUTION")
    ) != 1:
        report.error(
            "E_PROMPT_DIRECTOR_BLOCK",
            "NEUTRAL_EXECUTION_PROMPT director execution block is missing or duplicated",
            f"{path}.prompt_bundle.neutral_execution_prompt",
        )
    dialogue_rows = director.get("dialogue_inventory") if isinstance(
        director.get("dialogue_inventory"), list
    ) else []
    master_surface = creator_prompt_surface(master_text)
    neutral_surface = creator_prompt_surface(neutral_text)
    for row in dialogue_rows:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str):
            continue
        dialogue_text = normalize_text(row["text"])
        master_count = exact_source_body_count(master_text, dialogue_text)
        neutral_count = exact_source_body_count(neutral_text, dialogue_text)
        if master_count != 1 or neutral_count != 1:
            report.error(
                "E_DIALOGUE_SLOT_COUNT",
                "verbatim dialogue must occur exactly once in raw MASTER and "
                f"raw NEUTRAL_EXECUTION_PROMPT; master={master_count}, "
                f"neutral={neutral_count}",
                f"{path}.prompt_bundle",
            )
        if dialogue_text and dialogue_text in transform_text:
            report.error(
                "E_PROMPT_LAYER_ROLE_CONFLICT",
                "TRANSFORM_PLAN must not copy dialogue body text",
                f"{path}.prompt_bundle.transform_plan",
            )
    helper_cues = (
        render_visible_quote_cues(
            expected_quote_assignments(unit, source_dialogue_inventory)
        )
        if contract_version == CONTRACT_VERSION else []
    )
    independence_findings = prompt_layer_independence_findings(
        master.get("text"), neutral.get("text"), helper_cues
    )
    if "GENERIC_PROMPT_FILLER" in independence_findings:
        report.error(
            "E_AUTHORING_GENERIC_FILLER",
            "正式 Prompt 禁止使用自测/占位模板语句代替具体导演设计",
            f"{path}.prompt_bundle",
        )
    if (
        len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", creator_prompt_surface(neutral_text))) < 24
        or "[[" in creator_prompt_surface(neutral_text)
        or re.search(
            r'"(?:target_mode|source_refs|shot_plan|director_contract)"\s*:',
            creator_prompt_surface(neutral_text),
        )
    ):
        report.error(
            "E_PROMPT_WORKING_DRAFT",
            "每个 Unit 必须有可直接复制的自然语言提示词工作稿，不能用 SOURCE/JSON/导演摘要冒充",
            f"{path}.prompt_bundle.neutral_execution_prompt",
        )
    if any(item.startswith("PROMPT_LAYER_") for item in independence_findings):
        report.error(
            "E_PROMPT_LAYER_DUPLICATE",
            "MASTER 与 NEUTRAL_EXECUTION_PROMPT 不得共享同一长导演/JSON 载荷后仅改通用前后缀",
            f"{path}.prompt_bundle",
        )


def validate_prompt_artifact(
    artifact: Any, expected_layer: str, unit_id: str, path: str, report: Report
) -> tuple[str, int] | None:
    if not isinstance(artifact, dict):
        report.error("E_PROMPT_BUNDLE_EMPTY", f"{expected_layer} Prompt 必须是对象", path)
        return None
    artifact_id = artifact.get("artifact_id")
    text = artifact.get("text")
    if not nonempty_string(artifact_id) or artifact.get("layer") != expected_layer:
        report.error("E_PROMPT_BUNDLE_SCHEMA", f"{expected_layer} Prompt 缺少 artifact_id 或 layer", path)
    if artifact.get("unit_id") != unit_id:
        report.error("E_PROMPT_BUNDLE_SCHEMA", f"{expected_layer} Prompt 必须绑定当前 Unit", path)
    if not nonempty_string(text):
        report.error("E_PROMPT_BUNDLE_EMPTY", f"{expected_layer} Prompt 正文不得为空", path)
        return None
    creator_text = re.sub(
        r"\[\[(?:SOURCE_WINDOW_READ_ONLY|SOURCE_WINDOW_REF|MASTER_DIRECTOR_DESIGN_BLOCK|DRAFT_DIRECTOR_EXECUTION_BLOCK|NEUTRAL_EXECUTION_DIRECTOR_BLOCK|EXECUTION_BEATS)\]\].*?"
        r"\[\[/(?:SOURCE_WINDOW_READ_ONLY|SOURCE_WINDOW_REF|MASTER_DIRECTOR_DESIGN_BLOCK|DRAFT_DIRECTOR_EXECUTION_BLOCK|NEUTRAL_EXECUTION_DIRECTOR_BLOCK|EXECUTION_BEATS)\]\]",
        "",
        text,
        flags=re.DOTALL,
    )
    if INTERNAL_ID_RE.search(unicodedata.normalize("NFKC", creator_text)):
        report.error("E_PROMPT_INTERNAL_ID", f"{expected_layer} Prompt 正文泄漏工程 ID", path)
    expected_hash = sha256_text(text)
    if artifact.get("sha256") != expected_hash:
        report.error("E_PROMPT_BODY_HASH", f"{expected_layer} Prompt sha256 与正文不匹配", path)
    return expected_hash, len(normalize_text(text))


def validate_v13_prompt_bundle(
    unit: dict[str, Any],
    unit_id: str,
    path: str,
    report: Report,
    source_dialogue_inventory: list[dict[str, Any]] | None = None,
    contract_version: str = CONTRACT_VERSION,
) -> tuple[dict[str, str], int]:
    bundle = unit.get("prompt_bundle")
    if not isinstance(bundle, dict):
        report.error("E_PROMPT_BUNDLE_EMPTY", "1.3 compiled Unit requires a Prompt bundle", path)
        return {}, 0
    provider_status = unit.get("provider_binding_status")
    expected_keys = {
        "master_prompt", "transform_plan", "neutral_execution_prompt",
    }
    if provider_status == "PROVIDER_BOUND":
        expected_keys.add("provider_prompt")
    if set(bundle) != expected_keys:
        code = "E_LEGACY_PROMPT_ROLE" if "draft_prompt" in bundle else "E_PROMPT_BUNDLE_SCHEMA"
        report.error(
            code,
            f"1.3 Prompt bundle must contain exactly {sorted(expected_keys)}",
            f"{path}.prompt_bundle",
        )
    results: dict[str, tuple[str, int] | None] = {
        "master_prompt": validate_prompt_artifact(
            bundle.get("master_prompt"), "MP", unit_id,
            f"{path}.prompt_bundle.master_prompt", report,
        ),
        "transform_plan": validate_prompt_artifact(
            bundle.get("transform_plan"), "TP", unit_id,
            f"{path}.prompt_bundle.transform_plan", report,
        ),
        "neutral_execution_prompt": validate_prompt_artifact(
            bundle.get("neutral_execution_prompt"), "NEP", unit_id,
            f"{path}.prompt_bundle.neutral_execution_prompt", report,
        ),
    }
    master = bundle.get("master_prompt") if isinstance(bundle.get("master_prompt"), dict) else {}
    transform = bundle.get("transform_plan") if isinstance(bundle.get("transform_plan"), dict) else {}
    neutral = (
        bundle.get("neutral_execution_prompt")
        if isinstance(bundle.get("neutral_execution_prompt"), dict) else {}
    )
    transform_text = transform.get("text")
    try:
        transform_value = json.loads(transform_text) if isinstance(transform_text, str) else None
    except json.JSONDecodeError:
        transform_value = None
    transform_keys = {
        "source_role", "target_role", "preserve", "operations",
        "deferred_provider_decisions",
    }
    if (
        not isinstance(transform_value, dict)
        or set(transform_value) != transform_keys
        or transform_value.get("source_role") != "PROVIDER_NEUTRAL_MASTER"
        or transform_value.get("target_role") != "NEUTRAL_EXECUTION_PROMPT"
        or any(
            not isinstance(transform_value.get(field), list)
            for field in ("preserve", "operations", "deferred_provider_decisions")
        )
        or "{{VERBATIM_DIALOGUE_SLOT:" in str(transform_text)
        or "[[EXECUTION_BEATS]]" in str(transform_text)
    ):
        report.error(
            "E_PROMPT_LAYER_ROLE_CONFLICT",
            "TRANSFORM_PLAN must be a planning-only structured conversion contract",
            f"{path}.prompt_bundle.transform_plan",
        )
    master_text = normalize_text(master.get("text", "")) if isinstance(master.get("text"), str) else ""
    neutral_text = normalize_text(neutral.get("text", "")) if isinstance(neutral.get("text"), str) else ""
    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    expected_beat_values = expected_execution_beats_for_version(
        unit, source_dialogue_inventory, contract_version
    )
    expected_beats = render_execution_beats_block(
        expected_beat_values,
        expected_quote_assignments(unit, source_dialogue_inventory or [])
        if contract_version == CONTRACT_VERSION else None,
    )
    expected_copyable_surface = (
        render_copyable_execution_surface(
            expected_beat_values,
            expected_quote_assignments(unit, source_dialogue_inventory or []),
            shot_plan=(
                director.get("shot_plan")
                if isinstance(director.get("shot_plan"), list)
                else []
            ),
            shared_context=extract_shared_creator_context(neutral_text),
            creator_shot_sections=extract_creator_shot_sections(neutral_text),
            negative_clauses=(
                unit.get("negative_clauses")
                if isinstance(unit.get("negative_clauses"), list)
                else []
            ),
        )
        if contract_version == CONTRACT_VERSION else ""
    )
    if "[[EXECUTION_BEATS]]" in master_text or neutral_text.count(expected_beats) != 1:
        report.error(
            "E_EXECUTION_BEAT",
            "execution beats belong exactly once to NEUTRAL_EXECUTION_PROMPT and never to MASTER",
            f"{path}.prompt_bundle",
        )
    if contract_version == CONTRACT_VERSION and (
        expected_copyable_surface in master_text
        or neutral_text.count(expected_copyable_surface) != 1
    ):
        report.error(
            "E_EXECUTION_SURFACE",
            "逐镜执行稿必须只在 NEUTRAL_EXECUTION_PROMPT 中完整出现一次",
            f"{path}.prompt_bundle",
        )
    if contract_version == CONTRACT_VERSION:
        for finding in copyable_execution_surface_findings(expected_copyable_surface):
            report.error(
                "E_FINAL_PROMPT_EXECUTABILITY",
                finding,
                f"{path}.prompt_bundle.neutral_execution_prompt",
            )
    if (
        "{{VERBATIM_DIALOGUE_SLOT:" in master_text
        or "{{VERBATIM_DIALOGUE_SLOT:" in neutral_text
        or not creator_prompt_surface(neutral_text)
    ):
        report.error(
            "E_DIALOGUE_SLOT_UNRESOLVED",
            "MASTER and NEUTRAL_EXECUTION_PROMPT must be fully compiled copyable text",
            f"{path}.prompt_bundle",
        )
    helper_cues = (
        render_visible_quote_cues(
            expected_quote_assignments(unit, source_dialogue_inventory or [])
        )
        if contract_version == CONTRACT_VERSION else []
    )
    if any(
        item.startswith("PROMPT_LAYER_")
        for item in prompt_layer_independence_findings(
            master_text, neutral_text, helper_cues
        )
    ):
        report.error(
            "E_PROMPT_LAYER_DUPLICATE",
            "MASTER and NEUTRAL_EXECUTION_PROMPT have collapsed into one role",
            f"{path}.prompt_bundle",
        )
    provider_id = unit.get("provider_registry_id")
    if provider_status == "PROVIDER_PENDING":
        if provider_id not in (None, "") or "provider_prompt" in bundle:
            report.error(
                "E_PROVIDER_BINDING",
                "PROVIDER_PENDING cannot fabricate a provider binding or compiled provider Prompt",
                path,
            )
    elif provider_status == "PROVIDER_BOUND":
        if not nonempty_string(provider_id):
            report.error("E_PROVIDER_BINDING", "PROVIDER_BOUND requires provider_registry_id", path)
        results["provider_prompt"] = validate_prompt_artifact(
            bundle.get("provider_prompt"), "PP", unit_id,
            f"{path}.prompt_bundle.provider_prompt", report,
        )
    else:
        report.error(
            "E_PROVIDER_BINDING",
            "provider_binding_status must be PROVIDER_PENDING or PROVIDER_BOUND",
            path,
        )
    prompt_hashes = {key: value[0] for key, value in results.items() if value is not None}
    prompt_chars = sum(value[1] for value in results.values() if value is not None)
    return prompt_hashes, prompt_chars


def validate_prompt_bundle(
    unit: dict[str, Any], unit_id: str, path: str, report: Report,
    contract_version: str | None = None,
    source_dialogue_inventory: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, str], int]:
    if uses_locked_director_scaffold(contract_version):
        return validate_v13_prompt_bundle(
            unit, unit_id, path, report, source_dialogue_inventory,
            contract_version or CONTRACT_VERSION,
        )
    bundle = unit.get("prompt_bundle")
    if not isinstance(bundle, dict):
        report.error("E_PROMPT_BUNDLE_EMPTY", "已接受 Unit 必须有真实 Prompt bundle", path)
        return {}, 0
    results: dict[str, tuple[str, int] | None] = {
        "master_prompt": validate_prompt_artifact(
            bundle.get("master_prompt"), "MP", unit_id, f"{path}.prompt_bundle.master_prompt", report
        ),
        "draft_prompt": validate_prompt_artifact(
            bundle.get("draft_prompt"), "DRAFT", unit_id, f"{path}.prompt_bundle.draft_prompt", report
        ),
    }
    provider_status = unit.get("provider_binding_status")
    provider_id = unit.get("provider_registry_id")
    if provider_status == "PROVIDER_PENDING":
        if provider_id not in (None, "") or "provider_prompt" in bundle or "provider_prompt" in unit:
            report.error("E_PROVIDER_BINDING", "PROVIDER_PENDING 禁止伪造 provider ID 或 PP", path)
    elif provider_status == "PROVIDER_BOUND":
        if not nonempty_string(provider_id):
            report.error("E_PROVIDER_BINDING", "PROVIDER_BOUND 必须提供 provider_registry_id", path)
        results["provider_prompt"] = validate_prompt_artifact(
            bundle.get("provider_prompt"), "PP", unit_id, f"{path}.prompt_bundle.provider_prompt", report
        )
    else:
        report.error("E_PROVIDER_BINDING", "provider_binding_status 必须为 PROVIDER_PENDING 或 PROVIDER_BOUND", path)
    prompt_hashes = {key: value[0] for key, value in results.items() if value is not None}
    prompt_chars = sum(value[1] for value in results.values() if value is not None)
    return prompt_hashes, prompt_chars


def validate_director_contract(
    unit: dict[str, Any],
    atom_map: dict[str, dict[str, Any]],
    source_dialogue_inventory: list[dict[str, Any]],
    canonical_single_shot_eligibility: dict[str, Any],
    canonical_locked_scaffold: dict[str, Any],
    unit_source_refs: set[str],
    path: str,
    report: Report,
    contract_version: str | None = None,
    authorizations: list[dict[str, Any]] | None = None,
) -> None:
    """Validate the text-only directing surface and its dialogue evidence."""

    contract = unit.get("director_contract")
    contract_path = f"{path}.director_contract"
    if not isinstance(contract, dict):
        report.error("E_DIRECTOR_CONTRACT", "文字 Pilot/成品 Unit 必须有结构化 director_contract", contract_path)
        return
    target_mode = contract.get("target_mode")
    if target_mode not in DIRECTOR_TARGET_MODES:
        report.error(
            "E_DIRECTOR_CONTRACT",
            "director_contract.target_mode 必须为 EDITED_SEQUENCE 或 GENERATABLE_SHOT",
            f"{contract_path}.target_mode",
        )
    locked_scaffold: dict[str, Any] = {}
    locked_anchor_map: dict[str, dict[str, Any]] = {}
    single_shot_eligibility: dict[str, Any] = {}
    if uses_locked_director_scaffold(contract_version):
        locked_scaffold, locked_anchor_map = validate_v14_locked_scaffold(
            unit,
            atom_map,
            source_dialogue_inventory,
            canonical_locked_scaffold,
            unit_source_refs,
            contract_path,
            report,
            contract_version or CONTRACT_VERSION,
        )
        single_shot_eligibility = validate_v14_single_shot_eligibility(
            unit,
            locked_scaffold,
            canonical_single_shot_eligibility,
            contract_path,
            report,
        )
    for key in ("entry", "performance", "camera", "sound", "exit", "continuity"):
        if not nonempty_string(contract.get(key)):
            report.error("E_DIRECTOR_CONTRACT", f"director_contract.{key} 必须是非空文字", f"{contract_path}.{key}")
    sound_text = normalize_text(contract.get("sound", "")) if isinstance(contract.get("sound"), str) else ""
    sound_lines = [line.strip() for line in sound_text.splitlines() if line.strip()]
    if len(sound_lines) != len(set(sound_lines)) or re.search(
        r"(?:同上|重复前述|可能是.{0,16}(?:也可能|或者)|发声主体不确定)", sound_text
    ):
        report.error(
            "E_SOUND_DUPLICATE_OR_AMBIGUOUS",
            "声音设计不得重复同句或保留发声主体/声音来源二选一歧义",
            f"{contract_path}.sound",
        )
    chain = contract.get("action_state_chain")
    if not isinstance(chain, list) or not chain or not all(nonempty_string(item) for item in chain):
        report.error(
            "E_DIRECTOR_CONTRACT",
            "director_contract.action_state_chain 必须是非空动作状态链",
            f"{contract_path}.action_state_chain",
        )

    inferences = contract.get("proposed_director_inferences")
    if not isinstance(inferences, list):
        report.error(
            "E_DIRECTOR_INFERENCE",
            "proposed_director_inferences 必须是数组",
            f"{contract_path}.proposed_director_inferences",
        )
        inferences = []
    inference_map: dict[str, dict[str, Any]] = {}
    for index, inference in enumerate(inferences):
        inference_path = f"{contract_path}.proposed_director_inferences[{index}]"
        if not isinstance(inference, dict):
            report.error("E_DIRECTOR_INFERENCE", "导演推断必须是对象", inference_path)
            continue
        inference_id = inference.get("inference_id")
        refs = inference.get("source_refs")
        if not nonempty_string(inference_id) or inference_id in inference_map:
            report.error("E_DIRECTOR_INFERENCE", "inference_id 缺失或重复", inference_path)
            continue
        inference_map[inference_id] = inference
        if inference.get("status") != "PROPOSED_DIRECTOR_INFERENCE" or not nonempty_string(inference.get("text")):
            report.error(
                "E_DIRECTOR_INFERENCE",
                "导演推断必须有非空文字并显式标 PROPOSED_DIRECTOR_INFERENCE",
                inference_path,
            )
        if not unique_strings(refs) or any(ref not in unit_source_refs for ref in refs):
            report.error("E_DIRECTOR_INFERENCE", "导演推断必须引用当前 Unit 的非空 source_refs", inference_path)
        if uses_locked_director_scaffold(contract_version) and (
            inference.get("proposal_category") not in PROPOSAL_CATEGORIES
            or inference.get("plot_state_delta") != "NONE"
        ):
            report.error(
                "E_PROPOSAL_CONTROL",
                "r8 导演提案必须使用闭集 proposal_category，且 plot_state_delta=NONE",
                inference_path,
            )
        inference_text = normalize_text(inference.get("text", "")) if isinstance(inference.get("text"), str) else ""
        bound_source = "".join(
            normalize_text(atom_map[ref].get("text", ""))
            for ref in refs or []
            if ref in atom_map and isinstance(atom_map[ref].get("text"), str)
        )
        # A usable directing proposal normally has to name source characters,
        # actions or props.  Treating any four/six-character overlap as a
        # provenance violation rejects ordinary camera, performance and sound
        # direction.  Current 1.4 therefore rejects only the dishonest case:
        # the whole "proposal" is actually a complete source anchor.  Plot
        # changes, out-of-window actions, source-field mixing and dialogue
        # fidelity remain guarded independently below.
        source_only_proposal = (
            source_anchor_is_complete_for_version(
                inference_text, bound_source, contract_version or CONTRACT_VERSION
            )
            if uses_locked_director_scaffold(contract_version)
            else any(
                phrase in inference_text
                or any(
                    inference_text[offset : offset + 6] in phrase
                    for offset in range(max(0, len(inference_text) - 5))
                    if len(inference_text[offset : offset + 6]) == 6
                )
                for phrase in (
                    fragment.strip()
                    for fragment in re.split(
                        r"[\s，。；！？、：“”‘’（）()…]+", bound_source
                    )
                    if len(fragment.strip()) >= 4
                )
            )
        )
        if source_only_proposal:
            report.error(
                "E_INFERENCE_SOURCE_MIX",
                "完整来源事实不得伪装成新增导演提案",
                inference_path,
            )

    if uses_locked_director_scaffold(contract_version):
        validate_v14_final_projection(
            unit, contract, locked_scaffold, locked_anchor_map, inference_map,
            unit_source_refs, contract_path, report,
        )
        source_text_for_content = "".join(
            normalize_text(atom_map[ref].get("text", ""))
            for ref in unit.get("source_refs", [])
            if ref in atom_map and isinstance(atom_map[ref].get("text"), str)
        )
        bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
        execution_layer = (
            "neutral_execution_prompt"
            if uses_locked_director_scaffold(contract_version) else "draft_prompt"
        )
        creator_surfaces = "\n".join(
            creator_prompt_surface(bundle.get(layer, {}).get("text"))
            for layer in ("master_prompt", execution_layer)
            if isinstance(bundle.get(layer), dict)
        )
        proposed_texts = "\n".join(
            normalize_text(item.get("text", ""))
            for item in inferences
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
        action_text = "\n".join(
            normalize_text(item)
            for item in contract.get("action_state_chain", [])
            if isinstance(item, str)
        )
        authored_content = "\n".join((creator_surfaces, proposed_texts, action_text))
        for locked_action in SOURCE_ACTION_LOCKS:
            if locked_action in source_text_for_content and (
                locked_action not in action_text or locked_action not in creator_surfaces
            ):
                report.error(
                    "E_SOURCE_ACTION_LOCK",
                    "来源中的关键可见动作必须逐字进入 action_state_chain 与 DRAFT 工作稿，不得弱化改写",
                    f"{contract_path}.action_state_chain",
                )
        confirmed_interpretations = {
            normalize_text(item.get("text", "")).strip()
            for item in authorizations or []
            if isinstance(item, dict)
            and item.get("kind") == "SOURCE_INTERPRETATION"
            and item.get("status") == "USER_CONFIRMED"
            and nonempty_string(item.get("text"))
        }
        interpretation_matches = [
            match.group(0).strip()
            for match in UNCONFIRMED_INTERPRETATION_RE.finditer(authored_content)
        ]
        unconfirmed_matches = [
            match for match in interpretation_matches if match not in confirmed_interpretations
        ]
        if unconfirmed_matches:
            report.error(
                "E_UNCONFIRMED_SOURCE_INTERPRETATION",
                "来源异写或引号不得擅自解释为‘实指、应为、音近笔误’；"
                f"须先取得逐字用户确认。命中片段：{' / '.join(unconfirmed_matches[:3])}",
                contract_path,
            )
        for action_name, pattern in PLOT_ACTION_GROUPS.items():
            authored_match = pattern.search(authored_content)
            if authored_match and not pattern.search(source_text_for_content):
                report.error(
                    "E_OUT_OF_WINDOW_PLOT_ACTION",
                    f"命中词：“{authored_match.group(0)}”。{action_name} 推进动作未出现在当前 source window，不得冒充来源或导演提案",
                    contract_path,
                )
        camera_surface = "\n".join(
            [normalize_text(contract.get("camera", ""))]
            + [
                normalize_text(shot.get("camera", ""))
                for shot in contract.get("shot_plan", [])
                if isinstance(shot, dict) and isinstance(shot.get("camera"), str)
            ]
            + [creator_surfaces]
        )
        if POV_OBSERVER_CONFLICT_RE.search(camera_surface):
            report.error(
                "E_POV_OBSERVER_CONFLICT",
                "主观/第一人称镜头不得同时让视角观察者本人入画",
                f"{contract_path}.camera",
            )
        if FIXED_CAMERA_RE.search(camera_surface) and MOVING_CAMERA_RE.search(camera_surface):
            report.error(
                "E_CAMERA_MOTION_CONFLICT",
                "同一执行设计不得同时声明固定机位和跟随/摇移/推轨",
                f"{contract_path}.camera",
            )
        dialogue_inventory_for_voice = contract.get("dialogue_inventory")
        has_spoken_dialogue = isinstance(dialogue_inventory_for_voice, list) and bool(dialogue_inventory_for_voice)
        voice_surface = "\n".join((normalize_text(contract.get("sound", "")), creator_surfaces))
        if not has_spoken_dialogue and has_affirmative_unsourced_voice(voice_surface):
            report.error(
                "E_UNSOURCED_VOICE",
                "当前窗口无口播库存时不得新增内心独白、画外音或旁白",
                f"{contract_path}.sound",
            )
        performance_findings = analyze_performance_feasibility(
            creator_surfaces,
            has_spoken_dialogue=has_spoken_dialogue,
            spoken_speakers=[
                normalize_text(item.get("speaker", "")).strip()
                for item in dialogue_inventory_for_voice or []
                if isinstance(item, dict) and nonempty_string(item.get("speaker"))
            ],
            require_copy_endings=COPYABLE_EXECUTION_TITLE in creator_surfaces,
        )
        for finding in performance_findings:
            report.error(
                finding.code,
                f"{finding.message} 命中：{finding.evidence}",
                f"{contract_path}.performance",
            )
        if PUNCTUATION_COLLISION_RE.search("\n".join((authored_content, camera_surface, voice_surface))):
            report.error(
                "E_PUNCTUATION_COLLISION",
                "作者字段在 check 前不得含‘。；/！；/？；’等标点碰撞",
                contract_path,
            )
        continuous = contract.get("continuous_time_space")
        shot_plan = contract.get("shot_plan")
        if target_mode == "EDITED_SEQUENCE":
            source_text_for_route = "".join(
                normalize_text(atom_map[ref].get("text", ""))
                for ref in unit.get("source_refs", [])
                if ref in atom_map and isinstance(atom_map[ref].get("text"), str)
            )
            dialogue_turns = len(contract.get("dialogue_inventory", [])) if isinstance(
                contract.get("dialogue_inventory"), list
            ) else 0
            minimum_shots = expected_sequence_minimum_shots(
                source_text_for_route,
                dialogue_turns=dialogue_turns,
                atom_count=len(unit.get("source_refs", [])),
            )
            if continuous is not False or not isinstance(shot_plan, list) or len(shot_plan) < minimum_shots:
                report.error(
                    "E_SEQUENCE_SHOT_PLAN",
                    f"EDITED_SEQUENCE 必须 continuous_time_space=false 且按对白/动作密度提供至少 {minimum_shots} 镜",
                    f"{contract_path}.shot_plan",
                )
            else:
                prior_position = -1
                atom_positions = {atom_id: index for index, atom_id in enumerate(atom_map)}
                covered_shot_refs: set[str] = set()
                semantically_realized_refs: set[str] = set()
                camera_texts: list[str] = []
                copied_purpose_count = 0
                dialogue_inventory = contract.get("dialogue_inventory")
                expected_dialogue_ids = [
                    item.get("dialogue_id")
                    for item in dialogue_inventory
                    if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
                ] if isinstance(dialogue_inventory, list) else []
                dialogue_by_id = {
                    item["dialogue_id"]: item
                    for item in dialogue_inventory or []
                    if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
                }
                seen_dialogue_ids: list[str] = []
                for index, shot in enumerate(shot_plan, start=1):
                    shot_path = f"{contract_path}.shot_plan[{index - 1}]"
                    if not isinstance(shot, dict) or shot.get("shot_id") != f"SH{index:03d}":
                        report.error("E_SEQUENCE_SHOT_PLAN", "shot_id 必须从 SH001 连续递增", shot_path)
                        continue
                    refs = shot.get("source_refs")
                    if not unique_strings(refs) or any(ref not in unit_source_refs for ref in refs):
                        report.error("E_SEQUENCE_SHOT_PLAN", "每镜必须引用当前窗口的非空 source_refs", shot_path)
                    else:
                        covered_shot_refs.update(refs)
                        positions = [atom_positions.get(ref, -1) for ref in refs]
                        if positions != sorted(positions) or positions[0] < prior_position:
                            report.error("E_SEQUENCE_SHOT_ORDER", "shot_plan 不得倒序穿越来源窗口", shot_path)
                        prior_position = positions[-1]
                    for key in ("purpose", "camera"):
                        if not nonempty_string(shot.get(key)):
                            report.error("E_SEQUENCE_SHOT_PLAN", f"shot_plan.{key} 必须非空", shot_path)
                    if nonempty_string(shot.get("camera")):
                        camera_texts.append(normalize_text(shot["camera"]).strip())
                    if uses_locked_director_scaffold(contract_version) and isinstance(shot.get("semantic_anchor_ids"), list):
                        semantically_realized_refs.update(
                            locked_anchor_map[anchor_id]["source_ref"]
                            for anchor_id in shot["semantic_anchor_ids"]
                            if anchor_id in locked_anchor_map
                        )
                    purpose_text = normalize_text(shot.get("purpose", "")).strip() if isinstance(
                        shot.get("purpose"), str
                    ) else ""
                    bound_shot_text = "".join(
                        normalize_text(atom_map[ref].get("text", ""))
                        for ref in refs or []
                        if ref in atom_map and isinstance(atom_map[ref].get("text"), str)
                    )
                    purpose_payload = re.sub(r"^本镜呈现\s*[：:]\s*", "", purpose_text)
                    if purpose_payload != purpose_text and purpose_payload and purpose_payload in bound_shot_text:
                        copied_purpose_count += 1
                        report.error(
                            "E_DRAMATIC_BEAT",
                            "purpose 必须说明本镜戏剧任务，不能用‘本镜呈现+原文’代替",
                            f"{shot_path}.purpose",
                        )
                    if isinstance(shot, dict) and GENERIC_SHOT_FILLER_RE.search(
                        json.dumps(shot, ensure_ascii=False, sort_keys=True)
                    ):
                        report.error(
                            "E_AUTHORING_GENERIC_FILLER",
                            "正式 shot_plan 禁止使用第N镜推进/保持可辨等自测占位句",
                            shot_path,
                        )
                    shot_dialogue_ids = shot.get("dialogue_slot_ids") if isinstance(shot, dict) else None
                    if (
                        not isinstance(shot_dialogue_ids, list)
                        or len(shot_dialogue_ids) != len(set(shot_dialogue_ids))
                        or any(dialogue_id not in dialogue_by_id for dialogue_id in shot_dialogue_ids)
                    ):
                        report.error(
                            "E_SEQUENCE_DIALOGUE_COVERAGE",
                            "每镜 dialogue_slot_ids 必须是当前 Unit 口播 ID 的去重子集",
                            f"{shot_path}.dialogue_slot_ids",
                        )
                    else:
                        if any(dialogue_id in seen_dialogue_ids for dialogue_id in shot_dialogue_ids):
                            report.error(
                                "E_SEQUENCE_DIALOGUE_COVERAGE",
                                "同一口播 ID 不得分配给多个镜头",
                                f"{shot_path}.dialogue_slot_ids",
                            )
                        for dialogue_id in shot_dialogue_ids:
                            quote_refs = dialogue_by_id[dialogue_id].get("source_refs")
                            if not isinstance(refs, list) or not isinstance(quote_refs, list) or not set(
                                quote_refs
                            ).issubset(set(refs)):
                                report.error(
                                    "E_SEQUENCE_DIALOGUE_COVERAGE",
                                    "口播 ID 必须放在覆盖其精确来源 refs 的镜头",
                                    f"{shot_path}.dialogue_slot_ids",
                                )
                            else:
                                semantically_realized_refs.update(quote_refs)
                        seen_dialogue_ids.extend(shot_dialogue_ids)
                    shot_chain = shot.get("action_state_chain")
                    if (
                        not isinstance(shot_chain, list)
                        or not shot_chain
                        or len(shot_chain) > 3
                        or not all(nonempty_string(item) for item in shot_chain)
                    ):
                        report.error(
                            "E_SEQUENCE_SHOT_ACTION_CHAIN",
                            "每镜必须提供 1-3 步的单一连续动作状态链",
                            f"{shot_path}.action_state_chain",
                        )
                    shot_provenance = shot.get("field_provenance")
                    shot_fields = {"purpose", "action_state_chain", "camera"}
                    if not isinstance(shot_provenance, dict) or set(shot_provenance) != shot_fields:
                        report.error(
                            "E_SEQUENCE_SHOT_PROVENANCE",
                            "每个 shot 必须逐字段绑定 purpose/action_state_chain/camera 的来源或导演提案",
                            f"{shot_path}.field_provenance",
                        )
                    else:
                        for field, record in shot_provenance.items():
                            record_path = f"{shot_path}.field_provenance.{field}"
                            if uses_locked_director_scaffold(contract_version) and field == "action_state_chain":
                                # 1.4 action provenance is deliberately item-wise and was
                                # checked against the locked anchor prefix above.
                                continue
                            if not isinstance(record, dict):
                                report.error("E_SEQUENCE_SHOT_PROVENANCE", "shot provenance 必须是对象", record_path)
                                continue
                            provenance_refs = record.get("source_refs")
                            if (
                                not unique_strings(provenance_refs)
                                or not isinstance(refs, list)
                                or any(ref not in refs for ref in provenance_refs)
                            ):
                                report.error(
                                    "E_SEQUENCE_SHOT_PROVENANCE",
                                    "shot 字段 provenance 必须精确回链本镜 source_refs",
                                    record_path,
                                )
                            if record.get("status") == "SOURCE_SUPPORTED":
                                anchor = record.get("source_anchor")
                                bound_text = "".join(
                                    normalize_text(atom_map[ref].get("text", ""))
                                    for ref in provenance_refs or []
                                    if ref in atom_map and isinstance(atom_map[ref].get("text"), str)
                                )
                                if (
                                    set(record) != {"status", "source_refs", "source_anchor"}
                                    or not nonempty_string(anchor)
                                    or normalize_text(anchor) not in bound_text
                                    or not normalized_value_contains_exact_string(shot.get(field), anchor)
                                ):
                                    report.error(
                                        "E_SEQUENCE_SHOT_PROVENANCE",
                                        "SOURCE_SUPPORTED shot 字段必须把逐字 source_anchor 真正写入字段",
                                        record_path,
                                    )
                                elif not source_anchor_is_complete_for_version(
                                    anchor, bound_text, contract_version or CONTRACT_VERSION
                                ):
                                    report.error(
                                        "E_SOURCE_ANCHOR_FRAGMENT",
                                        "SOURCE_SUPPORTED shot 锚必须是完整来源行或完整分句，禁止任意截断前后缀",
                                        record_path,
                                    )
                                elif not source_supported_value_is_exact(shot.get(field), anchor):
                                    report.error(
                                        "E_PROVENANCE_MIXED_CONTENT",
                                        "SOURCE_SUPPORTED shot 字段只能是完整来源锚；新增解释必须拆成 PROPOSED",
                                        record_path,
                                    )
                                else:
                                    semantically_realized_refs.update(provenance_refs or [])
                            elif record.get("status") == "PROPOSED_DIRECTOR_INFERENCE":
                                inference_id = record.get("inference_id")
                                fragment = record.get("field_fragment")
                                inference_text = inference_map.get(inference_id, {}).get("text", "") if isinstance(
                                    inference_id, str
                                ) else ""
                                if (
                                    set(record) != {"status", "source_refs", "inference_id", "field_fragment"}
                                    or inference_id not in inference_map
                                    or not nonempty_string(fragment)
                                    or normalize_text(fragment) not in normalize_text(str(inference_text))
                                    or not normalized_value_contains_exact_string(shot.get(field), fragment)
                                ):
                                    report.error(
                                        "E_SEQUENCE_SHOT_PROVENANCE",
                                        "PROPOSED shot 字段必须用 fragment 同时绑定字段值与 inference",
                                        record_path,
                                    )
                            else:
                                report.error(
                                    "E_SEQUENCE_SHOT_PROVENANCE",
                                    "shot provenance 只能 SOURCE_SUPPORTED 或 PROPOSED_DIRECTOR_INFERENCE",
                                    record_path,
                                )
                # A punctuation-only source atom (for example a standalone
                # ellipsis) carries timing, not a fact anchor.  It is realized
                # only when the author explicitly keeps its ref in the same
                # shot as an already realized adjacent semantic ref.
                for ref in unit_source_refs:
                    atom_text = normalize_text(atom_map.get(ref, {}).get("text", ""))
                    if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", atom_text):
                        continue
                    if any(
                        isinstance(shot, dict)
                        and ref in shot.get("source_refs", [])
                        and any(
                            other_ref != ref and other_ref in semantically_realized_refs
                            for other_ref in shot.get("source_refs", [])
                        )
                        for shot in shot_plan
                    ):
                        semantically_realized_refs.add(ref)
                if covered_shot_refs != unit_source_refs:
                    report.error(
                        "E_SEQUENCE_SHOT_COVERAGE",
                        "shot_plan 必须按序覆盖窗口全部 source_refs，不能只绑首 atom",
                        f"{contract_path}.shot_plan",
                    )
                if semantically_realized_refs != unit_source_refs:
                    report.error(
                        "E_SEQUENCE_SOURCE_COVERAGE",
                        "每个 source_ref 必须由完整来源锚或其精确口播 ID 真正实现，不能只挂 ref",
                        f"{contract_path}.shot_plan",
                    )
                if seen_dialogue_ids != expected_dialogue_ids:
                    report.error(
                        "E_SEQUENCE_DIALOGUE_COVERAGE",
                        "EDITED_SEQUENCE 的全部 SPOKEN_DIALOGUE 必须按来源顺序恰好映射到一个镜头",
                        f"{contract_path}.shot_plan",
                    )
                if len(camera_texts) >= 4:
                    most_common_camera = max(camera_texts.count(item) for item in set(camera_texts))
                    if most_common_camera / len(camera_texts) >= 0.6:
                        report.error(
                            "E_GENERIC_CAMERA_RATIO",
                            "相机设计同文比例不得达到 60%；逐镜必须体现不同戏剧任务",
                            f"{contract_path}.shot_plan",
                        )
                if shot_plan and copied_purpose_count / len(shot_plan) >= 0.5:
                    report.error(
                        "E_PURPOSE_SOURCE_COPY_RATIO",
                        "半数以上 purpose 复制‘本镜呈现+原文’，没有形成戏剧 beat",
                        f"{contract_path}.shot_plan",
                    )
                if (
                    len(shot_plan) >= 8
                    and len(shot_plan) == len(unit_source_refs)
                    and all(isinstance(shot, dict) and len(shot.get("source_refs", [])) == 1 for shot in shot_plan)
                ):
                    report.error(
                        "E_MECHANICAL_ATOM_SHOT_MAPPING",
                        "长序列禁止机械一 atom 一镜；必须按戏剧 beat 合并或拆分",
                        f"{contract_path}.shot_plan",
                    )
        elif target_mode == "GENERATABLE_SHOT":
            if continuous is not True or shot_plan not in ([], None):
                report.error(
                    "E_SHOT_SEQUENCE_MASQUERADE",
                    "GENERATABLE_SHOT 必须 continuous_time_space=true，且不得内嵌多镜 shot_plan",
                    contract_path,
                )

        try:
            expected_beats = expected_execution_beats_for_version(
                unit, source_dialogue_inventory, contract_version or CONTRACT_VERSION
            )
        except ValueError as exc:
            if str(exc).startswith("E_SHOT_DURATION_OVERFLOW"):
                report.error(
                    "E_SHOT_DURATION_OVERFLOW",
                    str(exc),
                    f"{contract_path}.execution_beats",
                )
                expected_beats = []
            else:
                raise
        execution_beats = contract.get("execution_beats")
        expected_beat_count = len(contract.get("shot_plan", [])) if target_mode == "EDITED_SEQUENCE" else 1
        if (
            execution_beats != expected_beats
            or len(expected_beats) != expected_beat_count
            or any(
                not isinstance(beat, dict)
                or set(beat) != {
                    "beat_id", "shot_id", "source_refs", "duration_seconds", "entry_state",
                    "spatial_position", "observable_action", "camera", "audio_order", "exit_state",
                }
                or not (2.0 <= beat.get("duration_seconds", 0) <= 12.0)
                or not all(
                    nonempty_string(beat.get(field))
                    for field in ("entry_state", "spatial_position", "observable_action", "camera", "exit_state")
                )
                or not isinstance(beat.get("audio_order"), list)
                or not beat.get("audio_order")
                for beat in expected_beats
            )
        ):
            report.error(
                "E_EXECUTION_BEAT",
                "每个镜头必须有 finalizer 可复算的执行 beat：自然时长/入口/空间/动作/摄影/声音顺序/出口/source refs",
                f"{contract_path}.execution_beats",
            )
        if contract_version == CONTRACT_VERSION and isinstance(execution_beats, list):
            validate_source_audio_projection(
                unit,
                expected_beats,
                execution_beats,
                source_dialogue_inventory,
                f"{contract_path}.execution_beats",
                report,
            )
            global_sound = normalize_text(contract.get("sound", "")).strip()
            repeated_global_sound = []
            for beat in execution_beats:
                if not isinstance(beat, dict) or not isinstance(beat.get("audio_order"), list):
                    continue
                for item in beat["audio_order"]:
                    normalized_item = normalize_text(item).strip() if isinstance(item, str) else ""
                    if global_sound and normalized_item in {
                        global_sound, f"声音环境：{global_sound}",
                    }:
                        repeated_global_sound.append(beat.get("shot_id"))
            if repeated_global_sound:
                report.error(
                    "E_CROSS_SHOT_GLOBAL_SOUND",
                    "top-level sound 只定义整体声音原则，不得复制进任何逐镜 audio_order",
                    f"{contract_path}.execution_beats",
                )
            execution_artifact = (
                bundle.get(execution_layer)
                if isinstance(bundle.get(execution_layer), dict)
                else {}
            )
            execution_surface = creator_prompt_surface(execution_artifact.get("text", ""))
            expected_handoffs = expected_shot_handoffs(
                expected_beats,
                expected_quote_assignments(unit, source_dialogue_inventory),
                extract_creator_shot_sections(execution_surface),
            )
            if contract.get("shot_handoffs") != expected_handoffs:
                report.error(
                    "E_SHOT_HANDOFF_MATRIX",
                    "每对相邻镜头必须逐项记录上一镜可见落点、下一镜入口、空间动作和声音桥",
                    f"{contract_path}.shot_handoffs",
                )
        if target_mode == "GENERATABLE_SHOT":
            execution = bundle.get(execution_layer) if isinstance(
                bundle.get(execution_layer), dict
            ) else {}
            draft_surface = creator_prompt_surface(execution.get("text"))
            if (
                len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", draft_surface)) < 32
                or len(expected_beats) != 1
                or not expected_beats
                or len(re.findall(r"(?:先|随后|接着|然后|最后|直至|同时)", draft_surface)) < 1
            ):
                report.error(
                    "E_THIN_SINGLE_SHOT",
                    "GENERATABLE_SHOT 必须有一镜可执行工作稿与明确动作/声音时序，不能用薄概述冒充",
                    f"{path}.prompt_bundle.{execution_layer}",
                )
            locked_actions = [
                locked_anchor_map[item].get("exact_text")
                for item in locked_scaffold.get("action_anchor_ids", [])
                if item in locked_anchor_map
            ]
            execution_text = normalize_text(execution.get("text", "")) if isinstance(execution.get("text"), str) else ""
            beat = expected_beats[0] if len(expected_beats) == 1 and isinstance(expected_beats[0], dict) else {}
            observable_action = beat.get("observable_action", "")
            spoken_texts = [
                item.get("text")
                for item in contract.get("dialogue_inventory", [])
                if isinstance(item, dict) and nonempty_string(item.get("text"))
            ]
            if (
                single_shot_eligibility.get("eligible") is not True
                or any(not normalized_value_contains_exact_string(contract.get("action_state_chain"), action) for action in locked_actions)
                or any(normalize_text(action).strip() not in normalize_text(str(observable_action)).strip() for action in locked_actions)
                or any(normalize_text(action).strip() not in execution_text for action in locked_actions)
                or any(normalize_text(text).strip() not in execution_text for text in spoken_texts)
            ):
                report.error(
                    "E_SINGLE_SHOT_EXECUTION_COVERAGE",
                    "单镜必须覆盖全部锁定动作锚、执行 beat 与口播，并真实进入 neutral execution prompt",
                    f"{path}.prompt_bundle.{execution_layer}",
                )

        provenance = contract.get("field_provenance")
        provenance_fields = {
            "entry",
            "action_state_chain",
            "performance",
            "camera",
            "sound",
            "exit",
            "continuity",
            "shot_plan",
        }
        if not isinstance(provenance, dict) or set(provenance) != provenance_fields:
            report.error(
                "E_DIRECTOR_PROVENANCE",
                "director_contract.field_provenance 必须逐字段覆盖八个导演字段",
                f"{contract_path}.field_provenance",
            )
        else:
            for field, record in provenance.items():
                record_path = f"{contract_path}.field_provenance.{field}"
                if field in {"action_state_chain", "shot_plan"}:
                    # 1.4 owns these two records: action is item-wise and
                    # shot_plan is an exact HELPER_DERIVED scaffold proof.
                    continue
                if not isinstance(record, dict):
                    report.error("E_DIRECTOR_PROVENANCE", "provenance record 必须是对象", record_path)
                    continue
                status = record.get("status")
                refs = record.get("source_refs")
                if not unique_strings(refs) or any(ref not in unit_source_refs for ref in refs):
                    report.error("E_DIRECTOR_PROVENANCE", "每个导演字段必须回链当前 source_window", record_path)
                if status == "SOURCE_SUPPORTED":
                    anchor = record.get("source_anchor")
                    if set(record) != {"status", "source_refs", "source_anchor"}:
                        report.error(
                            "E_DIRECTOR_PROVENANCE",
                            "SOURCE_SUPPORTED 必须含 status/source_refs/source_anchor",
                            record_path,
                        )
                    if len(unit_source_refs) > 1 and set(refs) == unit_source_refs:
                        report.error(
                            "E_DIRECTOR_PROVENANCE_BROAD",
                            "SOURCE_SUPPORTED 必须精确定位，不得把整个窗口泛绑到每个导演字段",
                            record_path,
                        )
                    bound_text = "".join(
                        normalize_text(atom_map[ref].get("text", ""))
                        for ref in refs
                        if ref in atom_map and isinstance(atom_map[ref].get("text"), str)
                    )
                    if (
                        not nonempty_string(anchor)
                        or normalize_text(anchor) not in bound_text
                        or not normalized_value_contains_exact_string(contract.get(field), anchor)
                    ):
                        report.error(
                            "E_DIRECTOR_SOURCE_ANCHOR",
                            "SOURCE_SUPPORTED.source_anchor 必须同时逐字存在于来源与对应导演字段",
                            record_path,
                        )
                    elif not source_anchor_is_complete_for_version(
                        anchor, bound_text, contract_version or CONTRACT_VERSION
                    ):
                        report.error(
                            "E_SOURCE_ANCHOR_FRAGMENT",
                            "SOURCE_SUPPORTED 锚必须是完整来源行或完整分句，禁止任意截断前后缀",
                            record_path,
                        )
                    elif not source_supported_value_is_exact(contract.get(field), anchor):
                        report.error(
                            "E_PROVENANCE_MIXED_CONTENT",
                            "SOURCE_SUPPORTED 字段去掉固定标签后必须等于完整来源锚；新增内容须拆成 PROPOSED",
                            record_path,
                        )
                elif status == "PROPOSED_DIRECTOR_INFERENCE":
                    inference_id = record.get("inference_id")
                    fragment = record.get("field_fragment")
                    inference_text = (
                        inference_map.get(inference_id, {}).get("text", "")
                        if isinstance(inference_id, str)
                        else ""
                    )
                    if (
                        set(record) != {"status", "source_refs", "inference_id", "field_fragment"}
                        or not nonempty_string(inference_id)
                        or inference_id not in inference_map
                        or not nonempty_string(fragment)
                        or normalize_text(fragment) not in normalize_text(str(inference_text))
                        or not normalized_value_contains_exact_string(contract.get(field), fragment)
                    ):
                        report.error(
                            "E_DIRECTOR_PROVENANCE",
                            "PROPOSED 字段必须用 field_fragment 同时绑定字段值与当前 inference 文本",
                            record_path,
                        )
                else:
                    report.error(
                        "E_DIRECTOR_PROVENANCE",
                        "provenance status 只能 SOURCE_SUPPORTED 或 PROPOSED_DIRECTOR_INFERENCE；UNSET 不得晋级",
                        record_path,
                    )
            for required_field in ("entry", "exit", "continuity"):
                required_record = provenance.get(required_field)
                if not isinstance(required_record, dict) or required_record.get("status") != "SOURCE_SUPPORTED":
                    report.error(
                        "E_DIRECTOR_SOURCE_CORE",
                        "entry/action_state_chain/exit/continuity 必须以精确 source_anchor 锚定来源，不能全写成导演提案",
                        f"{contract_path}.field_provenance.{required_field}",
                    )

    inventory = contract.get("dialogue_inventory")
    if not isinstance(inventory, list):
        report.error("E_DIALOGUE_INVENTORY", "director_contract.dialogue_inventory 必须是数组", contract_path)
        return
    bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
    master = bundle.get("master_prompt") if isinstance(bundle.get("master_prompt"), dict) else {}
    execution_layer = (
        "neutral_execution_prompt"
        if uses_locked_director_scaffold(contract_version) else "draft_prompt"
    )
    draft = bundle.get(execution_layer) if isinstance(bundle.get(execution_layer), dict) else {}
    master_text = normalize_text(master.get("text", "")) if isinstance(master.get("text"), str) else ""
    draft_text = normalize_text(draft.get("text", "")) if isinstance(draft.get("text"), str) else ""
    if inference_map:
        denial_re = re.compile(
            r"(?:不|未|没有|无)(?:作任何)?(?:新增|添加)(?:任何)?"
            r"(?:来源|原文)?(?:事实|动作|人物|对白|因果|内容)?"
        )
        creator_text = creator_prompt_surface(master_text) + "\n" + creator_prompt_surface(draft_text)
        if denial_re.search(creator_text):
            report.error(
                "E_DIRECTOR_UNDECLARED_PROPOSAL",
                "Prompt 已含 PROPOSED 导演提案时，不得同时声称没有新增；应明确提案不改写来源事实",
                f"{path}.prompt_bundle",
            )
    dialogue_ids: set[str] = set()
    for index, item in enumerate(inventory):
        item_path = f"{contract_path}.dialogue_inventory[{index}]"
        if not isinstance(item, dict):
            report.error("E_DIALOGUE_INVENTORY", "dialogue item 必须是对象", item_path)
            continue
        dialogue_id = item.get("dialogue_id")
        text = item.get("text")
        refs = item.get("source_refs")
        kind = item.get("kind")
        if not nonempty_string(dialogue_id) or dialogue_id in dialogue_ids:
            report.error("E_DIALOGUE_INVENTORY", "dialogue_id 缺失或重复", item_path)
        else:
            dialogue_ids.add(dialogue_id)
        if not nonempty_string(item.get("speaker")) or not nonempty_string(text):
            report.error("E_DIALOGUE_INVENTORY", "dialogue speaker/text 必须非空", item_path)
            continue
        if kind not in DIALOGUE_KINDS:
            report.error("E_DIALOGUE_INVENTORY", f"未知 dialogue kind：{kind!r}", item_path)
            continue
        if not unique_strings(refs) or any(ref not in unit_source_refs for ref in refs):
            report.error("E_DIALOGUE_SOURCE", "dialogue 必须引用当前 Unit 的非空 source_refs", item_path)
            refs = []
        normalized_dialogue = normalize_text(text)
        if kind == "VERBATIM_DIALOGUE":
            bound_text = "".join(
                normalize_text(atom_map[ref].get("text", ""))
                for ref in refs
                if ref in atom_map and isinstance(atom_map[ref].get("text"), str)
            )
            if normalized_dialogue not in bound_text:
                report.error(
                    "E_DIALOGUE_VERBATIM_SOURCE",
                    "VERBATIM_DIALOGUE 必须是绑定 source atom 的规范化逐字子串",
                    item_path,
                )
            master_count = exact_source_body_count(master_text, normalized_dialogue)
            draft_count = exact_source_body_count(draft_text, normalized_dialogue)
            if master_count != 1 or draft_count != 1:
                report.error(
                    "E_DIALOGUE_VERBATIM_PROMPT",
                    "VERBATIM_DIALOGUE 必须在 raw MP 与 raw NEP 各逐字出现恰好一次；"
                    f"master={master_count}, execution={draft_count}",
                    item_path,
                )
        elif (
            item.get("status") != "PROPOSED_DIRECTOR_INFERENCE"
            or not nonempty_string(item.get("inference_id"))
            or item.get("inference_id") not in inference_map
        ):
            report.error(
                "E_DIALOGUE_PROPOSED_INFERENCE",
                "把叙述改为画外音必须显式标 PROPOSED_DIRECTOR_INFERENCE 并绑定推断记录",
                item_path,
            )

    if contract_version == CONTRACT_VERSION:
        expected_assignments = expected_quote_assignments(
            unit, source_dialogue_inventory
        )
        actual_assignments = contract.get("quote_assignments")
        relevant_ids = [
            item.get("dialogue_id")
            for item in source_dialogue_inventory
            if isinstance(item, dict)
            and nonempty_string(item.get("dialogue_id"))
            and isinstance(item.get("source_refs"), list)
            and set(item["source_refs"]).issubset(unit_source_refs)
        ]
        assignment_shape_ok = (
            isinstance(actual_assignments, list)
            and all(
                isinstance(item, dict) and set(item) == QUOTE_ASSIGNMENT_KEYS
                for item in actual_assignments
            )
        )
        if (
            not assignment_shape_ok
            or actual_assignments != expected_assignments
            or [item.get("dialogue_id") for item in expected_assignments] != relevant_ids
        ):
            report.error(
                "E_QUOTE_ASSIGNMENT",
                "quote_assignments 必须由来源引号库存、分类和锁定镜头逐项重算；禁止漏项、错镜或改写",
                f"{contract_path}.quote_assignments",
            )
        for index, assignment in enumerate(expected_assignments):
            if (
                assignment.get("kind") == "NON_LEXICAL_VOCALIZATION"
                and assignment.get("speaker") == "SOURCE_UNSPECIFIED"
            ):
                report.error(
                    "E_NON_LEXICAL_VOCALIZATION_SPEAKER",
                    "非词汇人声必须从最近的来源发声主体确定说话者；无法确定时退回，不得猜测",
                    f"{contract_path}.quote_assignments[{index}].speaker",
                )
        expected_coverage = expected_visible_quote_voice_coverage(
            unit, source_dialogue_inventory
        )
        layer_artifacts = {
            "master_prompt": master,
            "neutral_execution_prompt": draft,
        }
        for layer, cues in expected_coverage.items():
            surface = creator_prompt_surface(layer_artifacts.get(layer, {}).get("text"))
            if layer == "neutral_execution_prompt" and COPYABLE_EXECUTION_TITLE in surface:
                surface = surface.split(COPYABLE_EXECUTION_TITLE, 1)[1]
            if any(exact_source_body_count(surface, cue) != 1 for cue in cues):
                report.error(
                    "E_VISIBLE_QUOTE_VOICE_COVERAGE",
                    "NON_LEXICAL 与 QUOTED_TEXT 必须各在 MP/NEP 的正确镜头位置可见一次；画面文字必须标明不朗读",
                    f"{path}.prompt_bundle.{layer}",
                )


def expected_dialogue_diff(data: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    inventory = (
        data.get("source_dialogue_inventory")
        if isinstance(data.get("source_dialogue_inventory"), list)
        else []
    )
    refs = set(unit.get("source_refs", []))
    expected_items = [
        item
        for item in inventory
        if isinstance(item, dict)
        and isinstance(item.get("source_refs"), list)
        and set(item["source_refs"]).issubset(refs)
    ]
    provenance = unit.get("provenance") if isinstance(unit.get("provenance"), dict) else {}
    classifications = (
        provenance.get("quote_classifications")
        if isinstance(provenance.get("quote_classifications"), dict)
        else {}
    )
    expected_items = [
        item
        for item in expected_items
        if classifications.get(item.get("dialogue_id")) == "SPOKEN_DIALOGUE"
    ]
    expected_ids = [item.get("dialogue_id") for item in expected_items if nonempty_string(item.get("dialogue_id"))]
    slot_ids = provenance.get("dialogue_slot_ids") if isinstance(provenance.get("dialogue_slot_ids"), list) else []
    bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
    master = bundle.get("master_prompt") if isinstance(bundle.get("master_prompt"), dict) else {}
    execution_layer = (
        "neutral_execution_prompt"
        if uses_locked_director_scaffold(data) else "draft_prompt"
    )
    draft = bundle.get(execution_layer) if isinstance(bundle.get(execution_layer), dict) else {}
    master_text = normalize_text(master.get("text", "")) if isinstance(master.get("text"), str) else ""
    draft_text = normalize_text(draft.get("text", "")) if isinstance(draft.get("text"), str) else ""
    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    authored_inventory = director.get("dialogue_inventory") if isinstance(director.get("dialogue_inventory"), list) else []
    authored_map = {
        item.get("dialogue_id"): item
        for item in authored_inventory
        if isinstance(item, dict) and nonempty_string(item.get("dialogue_id"))
    }
    expected_map = {item.get("dialogue_id"): item for item in expected_items}
    missing: list[str] = []
    changed: list[str] = []
    for dialogue_id in expected_ids:
        source_item = expected_map[dialogue_id]
        authored = authored_map.get(dialogue_id)
        if dialogue_id not in slot_ids or authored is None:
            missing.append(dialogue_id)
            continue
        text = normalize_text(source_item.get("text", ""))
        if (
            authored.get("kind") != "VERBATIM_DIALOGUE"
            or normalize_text(authored.get("text", "")) != text
            or authored.get("source_refs") != source_item.get("source_refs")
            or text not in master_text
            or text not in draft_text
        ):
            changed.append(dialogue_id)
    added = sorted(
        {
            dialogue_id
            for dialogue_id in list(slot_ids) + list(authored_map)
            if dialogue_id not in expected_ids
        }
    )
    narration_promoted = sorted(
        item.get("dialogue_id")
        for item in authored_inventory
        if isinstance(item, dict)
        and item.get("kind") == "NARRATION_AS_PROPOSED_VOICE_OVER"
        and nonempty_string(item.get("dialogue_id"))
    )
    status = "PASS" if not any((missing, changed, added, narration_promoted)) else "FAIL"
    return {
        "expected_dialogue_ids": expected_ids,
        "dialogue_slot_ids": slot_ids,
        "missing": missing,
        "changed": changed,
        "added": added,
        "narration_promoted": narration_promoted,
        "status": status,
    }


def validate_r5_unit_evidence(data: dict[str, Any], unit: dict[str, Any], path: str, report: Report) -> None:
    provenance = unit.get("provenance")
    expected_keys = {
        "source_window_sha256",
        "authoring_overlay_sha256",
        "source_dialogue_inventory_sha256",
        "dialogue_slot_ids",
        "quote_classifications",
    }
    if not isinstance(provenance, dict) or set(provenance) != expected_keys:
        report.error("E_UNIT_PROVENANCE", "r5 成品 Unit 缺少精确 provenance", f"{path}.provenance")
        return
    window = unit.get("source_window") if isinstance(unit.get("source_window"), dict) else {}
    if provenance.get("source_window_sha256") != window.get("text_sha256"):
        report.error("E_UNIT_PROVENANCE", "provenance 未绑定当前 source_window", f"{path}.provenance")
    if provenance.get("source_dialogue_inventory_sha256") != data.get("source_dialogue_inventory_sha256"):
        report.error("E_UNIT_PROVENANCE", "provenance 未绑定根逐字对白库存", f"{path}.provenance")
    if not is_sha256(provenance.get("authoring_overlay_sha256")):
        report.error("E_UNIT_PROVENANCE", "authoring_overlay_sha256 必须是 SHA-256", f"{path}.provenance")
    if not isinstance(provenance.get("dialogue_slot_ids"), list) or len(provenance["dialogue_slot_ids"]) != len(
        set(provenance["dialogue_slot_ids"])
    ):
        report.error("E_DIALOGUE_SLOT", "dialogue_slot_ids 必须是无重复数组", f"{path}.provenance")
    inventory = data.get("source_dialogue_inventory") if isinstance(data.get("source_dialogue_inventory"), list) else []
    refs = set(unit.get("source_refs", []))
    relevant = [
        item
        for item in inventory
        if isinstance(item, dict)
        and isinstance(item.get("source_refs"), list)
        and set(item["source_refs"]).issubset(refs)
    ]
    classifications = provenance.get("quote_classifications")
    expected_ids = [item.get("dialogue_id") for item in relevant]
    allowed_quote_types = {
        "SPOKEN_DIALOGUE",
        "INTERNAL_THOUGHT",
        "NON_LEXICAL_VOCALIZATION",
        "SFX",
        "QUOTED_TEXT",
    }
    if (
        not isinstance(classifications, dict)
        or set(classifications) != set(expected_ids)
        or any(value not in allowed_quote_types for value in classifications.values())
    ):
        report.error("E_QUOTE_CLASSIFICATION", "当前窗口每个成对引号 span 必须有唯一合法去向", f"{path}.provenance")
        classifications = {}
    spoken_ids = [dialogue_id for dialogue_id in expected_ids if classifications.get(dialogue_id) == "SPOKEN_DIALOGUE"]
    if provenance.get("dialogue_slot_ids") != spoken_ids:
        report.error("E_DIALOGUE_SLOT", "对白 slot 必须精确等于 SPOKEN_DIALOGUE 分类顺序", f"{path}.provenance")
    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    for item in relevant:
        dialogue_id = item.get("dialogue_id")
        quote_type = classifications.get(dialogue_id)
        if (
            data.get("contract_version") == CONTRACT_VERSION
            and "LIKELY_NON_LEXICAL_VOCALIZATION"
            in item.get("classification_hints", [])
            and quote_type != "NON_LEXICAL_VOCALIZATION"
        ):
            report.error(
                "E_QUOTE_CLASSIFICATION_CONFLICT",
                "来源已锁定为人物非词汇发声，不得改成对白、环境声、画面文字或内心文字",
                f"{path}.provenance.quote_classifications.{dialogue_id}",
            )
        if (
            data.get("contract_version") == CONTRACT_VERSION
            and "LIKELY_QUOTED_TEXT" in item.get("classification_hints", [])
            and quote_type != "QUOTED_TEXT"
        ):
            report.error(
                "E_QUOTE_CLASSIFICATION_CONFLICT",
                "画面文字载体直接支配该引号，必须归为 QUOTED_TEXT 且不得朗读",
                f"{path}.provenance.quote_classifications.{dialogue_id}",
            )
        if quote_type == "SPOKEN_DIALOGUE":
            conflicts = spoken_quote_conflicts(item)
            if conflicts:
                report.error(
                    "E_QUOTE_CLASSIFICATION_CONFLICT",
                    "明显拟声/内心提示与 SPOKEN_DIALOGUE 冲突，且附近没有明确说话动词证据："
                    + ", ".join(conflicts),
                    f"{path}.provenance.quote_classifications.{dialogue_id}",
                )
        if quote_type == "SFX" and "LIKELY_NON_LEXICAL_VOCALIZATION" in item.get("classification_hints", []):
            report.error(
                "E_QUOTE_CLASSIFICATION_CONFLICT",
                "有明确人物/动物发声语境的非词汇叫声不得归为无主体 SFX",
                f"{path}.provenance.quote_classifications.{dialogue_id}",
            )
        if (
            data.get("contract_version") != CONTRACT_VERSION
            and quote_type == "SFX"
            and item.get("text") not in str(director.get("sound", ""))
        ):
            report.error("E_QUOTE_ROUTING", "SFX 引号 span 必须逐字进入 sound", f"{path}.director_contract.sound")
        if quote_type == "INTERNAL_THOUGHT" and item.get("text") not in str(director.get("performance", "")):
            report.error("E_QUOTE_ROUTING", "INTERNAL_THOUGHT 必须逐字进入 performance", f"{path}.director_contract.performance")
        if (
            data.get("contract_version") != CONTRACT_VERSION
            and quote_type == "NON_LEXICAL_VOCALIZATION"
        ):
            text = item.get("text")
            if text not in str(director.get("sound", "")) or text not in str(director.get("performance", "")):
                report.error(
                    "E_NON_LEXICAL_VOCALIZATION_ROUTING",
                    "人物/动物非词汇发声必须逐字进入 sound，并在 performance 中绑定发声主体/反应",
                    f"{path}.director_contract",
                )
    expected = expected_dialogue_diff(data, unit)
    if unit.get("dialogue_diff") != expected:
        report.error("E_DIALOGUE_DIFF", "dialogue_diff 不是库存/slot/成品 Prompt 的确定性 diff", f"{path}.dialogue_diff")
    elif expected["status"] != "PASS":
        report.error("E_DIALOGUE_DIFF_NOT_PASS", "逐字对白 diff 存在 missing/changed/added/narration promoted", f"{path}.dialogue_diff")


def expected_content_self_review(
    unit: dict[str, Any],
    source_dialogue_inventory: list[dict[str, Any]] | None = None,
    contract_version: str = CONTRACT_VERSION,
    *,
    scene_title: str | None = None,
) -> dict[str, Any]:
    """Compute the five content axes from current artifacts, never from self-reported booleans."""

    stored = unit.get("content_self_review") if isinstance(unit.get("content_self_review"), dict) else {}
    title = scene_title if scene_title is not None else stored.get("scene_title", "")
    title_ok = bool(
        nonempty_string(title)
        and not re.search(r"(?i)(?:\bU\d{3,}\b|样片\s*\d+|未命名场景)", str(title))
    )
    bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
    execution_layer = (
        "neutral_execution_prompt" if "neutral_execution_prompt" in bundle else "draft_prompt"
    )
    draft = bundle.get(execution_layer) if isinstance(bundle.get(execution_layer), dict) else {}
    draft_surface = creator_prompt_surface(draft.get("text"))
    surface_findings = (
        copyable_execution_surface_findings(draft_surface)
        if contract_version == CONTRACT_VERSION
        else []
    )
    draft_ok = bool(
        len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", draft_surface)) >= 24
        and "[[" not in draft_surface
        and not re.search(r'"(?:target_mode|source_refs|shot_plan|director_contract)"\s*:', draft_surface)
        and not surface_findings
    )
    director = unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    provenance = director.get("field_provenance") if isinstance(director.get("field_provenance"), dict) else {}
    inferences = director.get("proposed_director_inferences") if isinstance(
        director.get("proposed_director_inferences"), list
    ) else []
    provenance_ok = bool(
        provenance
        and all(
            (
                field == "action_state_chain"
                and isinstance(record, list)
                and bool(record)
                and all(
                    isinstance(item, dict)
                    and item.get("status") in {"SOURCE_SUPPORTED", "PROPOSED_DIRECTOR_INFERENCE"}
                    for item in record
                )
            )
            or (
                field == "shot_plan"
                and isinstance(record, dict)
                and record.get("status") == "HELPER_DERIVED"
                and is_sha256(record.get("locked_scaffold_sha256"))
            )
            or (
                field not in {"action_state_chain", "shot_plan"}
                and isinstance(record, dict)
                and record.get("status") in {"SOURCE_SUPPORTED", "PROPOSED_DIRECTOR_INFERENCE"}
            )
            for field, record in provenance.items()
        )
        and all(
            isinstance(item, dict)
            and item.get("proposal_category") in PROPOSAL_CATEGORIES
            and item.get("plot_state_delta") == "NONE"
            for item in inferences
        )
    )
    beats = director.get("execution_beats")
    try:
        expected_beats = expected_execution_beats_for_version(
            unit, source_dialogue_inventory, contract_version
        )
    except ValueError:
        expected_beats = []
    shots_ok = bool(beats == expected_beats and beats)
    if director.get("target_mode") == "EDITED_SEQUENCE":
        shot_plan = director.get("shot_plan") if isinstance(director.get("shot_plan"), list) else []
        shots_ok = shots_ok and all(
            isinstance(shot, dict)
            and nonempty_string(shot.get("purpose"))
            and GENERIC_SHOT_FILLER_RE.search(str(shot.get("purpose"))) is None
            for shot in shot_plan
        )
    sound = normalize_text(director.get("sound", "")) if isinstance(director.get("sound"), str) else ""
    sound_lines = [line.strip() for line in sound.splitlines() if line.strip()]
    dialogue_inventory = director.get("dialogue_inventory")
    sound_ok = bool(
        sound.strip()
        and len(sound_lines) == len(set(sound_lines))
        and not re.search(r"(?:同上|重复前述|可能是.{0,16}(?:也可能|或者)|发声主体不确定)", sound)
        and not (
            (not isinstance(dialogue_inventory, list) or not dialogue_inventory)
            and has_affirmative_unsourced_voice("\n".join((sound, draft_surface)))
        )
    )
    checks = {
        "scene_title_is_specific": title_ok,
        "prompt_working_draft_present": draft_ok,
        "facts_proposals_separated": provenance_ok,
        "shots_have_dramatic_beats": shots_ok,
        "sound_is_unambiguous": sound_ok,
    }
    findings = [key for key, passed in checks.items() if not passed]
    findings.extend(f"final_prompt:{item}" for item in surface_findings)
    return {
        "status": "PASS" if not findings else "FAIL",
        "scene_title": title if isinstance(title, str) else "",
        "checks": checks,
        "findings": findings,
    }


def validate_prompt_quality(
    unit: dict[str, Any], unit_id: str, prompt_hashes: dict[str, str], path: str, report: Report,
    contract_version: str | None = None,
    source_dialogue_inventory: list[dict[str, Any]] | None = None,
) -> str | None:
    content_review = unit.get("content_self_review")
    checks = content_review.get("checks") if isinstance(content_review, dict) else None
    if uses_locked_director_scaffold(contract_version) and "execution_beats" in (
        unit.get("director_contract") if isinstance(unit.get("director_contract"), dict) else {}
    ) and content_review != expected_content_self_review(
        unit,
        source_dialogue_inventory,
        contract_version or CONTRACT_VERSION,
    ):
        report.error(
            "E_CONTENT_SELF_REVIEW_COMPUTED",
            "content_self_review 必须等于 helper 对当前提示词/来源分离/执行beat/声音的可复算结果",
            f"{path}.content_self_review",
        )
    if (
        not isinstance(content_review, dict)
        or set(content_review) != {"status", "scene_title", "checks", "findings"}
        or content_review.get("status") != "PASS"
        or not nonempty_string(content_review.get("scene_title"))
        or re.search(r"(?i)(?:\bU\d{3,}\b|样片\s*\d+)", str(content_review.get("scene_title", "")))
        or not isinstance(checks, dict)
        or set(checks) != CONTENT_SELF_REVIEW_CHECK_KEYS
        or not all(value is True for value in checks.values())
        or content_review.get("findings") != []
    ):
        report.error(
            "E_CONTENT_SELF_REVIEW",
            "每个已接受 Unit 必须完成 PASS 内容自检、具体场景名、五项 true checks 且零遗留",
            f"{path}.content_self_review",
        )
    records = unit.get("prompt_quality_records")
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        report.error("E_PROMPT_QUALITY_CARDINALITY", "每个已接受 Unit 必须恰有一条质量记录", path)
        return None
    record = records[0]
    quality_id = record.get("id")
    quality_status = record.get("quality_status")
    if not nonempty_string(quality_id) or record.get("unit_id") != unit_id:
        report.error("E_PROMPT_QUALITY_SCHEMA", "质量记录必须有唯一 ID 并绑定当前 Unit", path)
    if record.get("lifecycle_status") != "CURRENT" or not isinstance(quality_status, dict) or quality_status.get("status") != "PASS":
        report.error("E_PROMPT_QUALITY_NOT_READY", "质量记录必须是唯一 CURRENT/PASS", path)
    if "provenance" in unit and (
        not isinstance(quality_status, dict) or quality_status.get("findings") != []
    ):
        report.error(
            "E_AUTHORING_FINDINGS",
            "r5 finalizer 只在无剩余 authoring findings 时生成 CURRENT/PASS",
            path,
        )
    if "provenance" in unit and record.get("quality_scope") != "CONTRACT_STRUCTURAL":
        report.error(
            "E_EDITORIAL_REVIEW_AXIS",
            "CURRENT/PASS 质量卡只证明 CONTRACT_STRUCTURAL，不得伪装成编辑或内容审阅通过",
            path,
        )
    if normalize_value(record.get("prompt_sha256s")) != normalize_value(prompt_hashes):
        report.error("E_PROMPT_QUALITY_BINDING", "质量记录必须精确绑定当前 Prompt 正文 hash", path)
    return quality_id if nonempty_string(quality_id) else None


def expected_unit_compile_state(unit: dict[str, Any], global_state_sha256: Any) -> dict[str, Any]:
    state = {
        "unit_id": unit.get("unit_id"),
        "source_refs": unit.get("source_refs", []),
        "global_state_sha256": global_state_sha256,
        "capability_routing": unit.get("capability_routing"),
        "prompt_claims": unit.get("prompt_claims"),
        "prompt_source_trace": unit.get("prompt_source_trace"),
        "negative_clause_plan": unit.get("negative_clause_plan"),
        "negative_clauses": unit.get("negative_clauses"),
        "prompt_bundle": unit.get("prompt_bundle"),
        "provider_binding_status": unit.get("provider_binding_status"),
        "provider_registry_id": unit.get("provider_registry_id"),
        "prompt_quality_records": unit.get("prompt_quality_records"),
        "unit_handoff_out": unit.get("unit_handoff_out"),
    }
    # Preserve hashes of legacy MEDIA_ENABLED contracts that predate the
    # text-only director contract, while binding it whenever it is present.
    if "director_contract" in unit:
        state["director_contract"] = unit.get("director_contract")
    if "dialogue_diff" in unit:
        state["dialogue_diff"] = unit.get("dialogue_diff")
    if "provenance" in unit:
        state["provenance"] = unit.get("provenance")
    if "content_self_review" in unit:
        state["content_self_review"] = unit.get("content_self_review")
    return state


def validate_unit_handoff(
    unit: dict[str, Any], unit_id: str, expected_next: str | None, path: str, report: Report
) -> None:
    handoff_path = f"{path}.unit_handoff_out"
    handoff = unit.get("unit_handoff_out")
    if not isinstance(handoff, dict):
        report.error("E_UNIT_HANDOFF_SCOPE", "已接受 Unit 缺少结构化 Unit handoff", handoff_path)
        return
    if handoff.get("scope") != "UNIT_TO_UNIT" or handoff.get("from_unit_id") != unit_id:
        report.error("E_UNIT_HANDOFF_SCOPE", "Unit handoff 的 scope/from_unit_id 不正确", handoff_path)
    if handoff.get("to_unit_id") != expected_next:
        report.error("E_UNIT_HANDOFF_TARGET", "Unit handoff 必须指向 manifest 紧邻下一 Unit", handoff_path)
    if not is_sha256(handoff.get("state_out_sha256")):
        report.error("E_UNIT_HANDOFF_STATE", "state_out_sha256 必须是 SHA-256", handoff_path)
    for required in ("entry_facts_for_next_unit", "open_actions", "dialogue_audio_carry"):
        if not isinstance(handoff.get(required), list):
            report.error("E_UNIT_HANDOFF_SCHEMA", f"{required} 必须是数组", handoff_path)
    for key, value in recursive_items(handoff):
        if key in UNIT_HANDOFF_FORBIDDEN_KEYS:
            report.error("E_UNIT_HANDOFF_SCOPE", f"Unit handoff 禁止字段：{key}", handoff_path)
        if isinstance(value, str) and UNIT_HANDOFF_FORBIDDEN_TEXT.search(value):
            report.error("E_UNIT_HANDOFF_SCOPE", "Unit handoff 混入 Batch/checkpoint 恢复文本", handoff_path)


def validate_units(
    data: dict[str, Any], atom_map: dict[str, dict[str, Any]], compile_targets: set[str], report: Report
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], set[str]]:
    raw_units = data.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        report.error("E_UNIT_SCHEMA", "units 必须是非空数组", "$.units")
        return [], {}, set()
    units: list[dict[str, Any]] = []
    unit_ids: set[str] = set()
    all_unit_source_refs: list[str] = []
    project_rules = data.get("project_rules") if isinstance(data.get("project_rules"), list) else []
    project_rule_ids = {
        rule.get("rule_id") for rule in project_rules if isinstance(rule, dict) and isinstance(rule.get("rule_id"), str)
    }
    compiled: dict[str, dict[str, Any]] = {}
    compiled_trace_coverage: set[str] = set()
    quality_owners: dict[str, str] = {}
    expected_v14_windows = {
        window.get("unit_id"): window
        for window in expected_target_windows(data)
        if isinstance(window, dict) and nonempty_string(window.get("unit_id"))
    } if uses_locked_director_scaffold(data) else {}
    source_dialogue_inventory = (
        data.get("source_dialogue_inventory")
        if isinstance(data.get("source_dialogue_inventory"), list) else []
    )
    for index, unit in enumerate(raw_units):
        path = f"$.units[{index}]"
        if not isinstance(unit, dict):
            report.error("E_UNIT_SCHEMA", "Unit 必须是对象", path)
            continue
        unit_id = unit.get("unit_id")
        if not isinstance(unit_id, str) or not UNIT_ID_RE.fullmatch(unit_id) or unit_id in unit_ids:
            report.error("E_UNIT_SCHEMA", "unit_id 格式错误或重复", f"{path}.unit_id")
            continue
        unit_ids.add(unit_id)
        units.append(unit)
        if unit_id in expected_v14_windows:
            expected_locked = expected_v14_windows[unit_id]
            for locked_field in (
                "single_shot_eligibility", "locked_director_scaffold",
                "locked_scaffold_sha256", "fixed_transform_roles",
            ):
                if unit.get(locked_field) != expected_locked.get(locked_field):
                    report.error(
                        "E_AUTHORING_SCAFFOLD_TAMPER",
                        f"final Unit 的 {locked_field} 必须等于从 source ledger 可复算的 authoring lock",
                        f"{path}.{locked_field}",
                    )
        if unit.get("order") != index + 1:
            report.error("E_UNIT_ORDER", "Unit order 必须从 1 连续递增", f"{path}.order")
        refs = unit.get("source_refs")
        if not unique_strings(refs):
            report.error("E_UNIT_SOURCE_REFS", "source_refs 必须是无重复非空字符串数组", f"{path}.source_refs")
            refs = []
        for ref in refs:
            if ref not in atom_map:
                report.error("E_UNIT_SOURCE_REFS", f"未知来源：{ref}", f"{path}.source_refs")
            elif ref not in compile_targets:
                report.error("E_NON_TARGET_UNIT_REF", f"Unit 引用了 compile_target=false 来源：{ref}", f"{path}.source_refs")
        if uses_source_window_contract(data):
            expected_window = expected_source_window(refs, atom_map)
            if expected_window is None:
                report.error(
                    "E_UNIT_SOURCE_WINDOW",
                    "r5 Unit 的 source_refs 必须是来源顺序中的连续 atom 窗口",
                    f"{path}.source_refs",
                )
            elif unit.get("source_window") != expected_window:
                report.error(
                    "E_UNIT_SOURCE_WINDOW",
                    "source_window 必须精确回算 first/last/count/cp span/text hash",
                    f"{path}.source_window",
                )
        all_unit_source_refs.extend(refs)
        compile_status = unit.get("compile_status")
        prompt_shells = sorted(PROMPT_SHELL_KEYS.intersection(unit))
        if compile_status in (None, "PLANNED"):
            if prompt_shells:
                report.error(
                    "E_PHASE_A_PROMPT_SHELL",
                    f"未编译 Unit 不得预铺 Prompt/negative/quality/handoff 空壳：{prompt_shells}",
                    path,
                )
            continue
        if compile_status not in {"ACCEPTED", "COMMITTED"}:
            report.error("E_UNIT_COMPILE_STATUS", "compile_status 只能是 PLANNED/ACCEPTED/COMMITTED", path)
            continue
        validate_capability_routing(unit, path, report)
        covered_refs = validate_traces(unit, atom_map, set(refs), project_rule_ids, path, report)
        validate_locked_semantic_claims(data, unit, path, report)
        compiled_trace_coverage.update(covered_refs)
        validate_negative_plan(unit, path, report)
        prompt_hashes, prompt_chars = validate_prompt_bundle(
            unit, unit_id, path, report, data.get("contract_version"),
            source_dialogue_inventory,
        )
        if data.get("delivery_mode") == "TEXT_ONLY_ECO_TEST":
            validate_director_contract(
                unit,
                atom_map,
                source_dialogue_inventory,
                expected_v14_windows.get(unit_id, {}).get(
                    "single_shot_eligibility", {}
                ),
                expected_v14_windows.get(unit_id, {}).get(
                    "locked_director_scaffold", {}
                ),
                set(refs),
                path,
                report,
                data.get("contract_version"),
                data.get("authorizations") if isinstance(data.get("authorizations"), list) else [],
            )
            if uses_locked_director_scaffold(data):
                validate_v13_prompt_compilation(
                    unit, atom_map, source_dialogue_inventory, path, report,
                    data.get("contract_version", CONTRACT_VERSION),
                )
                validate_r5_unit_evidence(data, unit, path, report)
                validate_current_semantic_content(data, unit, path, report)
            elif uses_source_window_contract(data):
                validate_r5_prompt_compilation(unit, atom_map, path, report)
                validate_r5_unit_evidence(data, unit, path, report)
        quality_id = validate_prompt_quality(
            unit, unit_id, prompt_hashes, path, report,
            data.get("contract_version"), source_dialogue_inventory,
        )
        if quality_id is not None:
            if quality_id in quality_owners:
                report.error(
                    "E_PROMPT_QUALITY_DUPLICATE",
                    f"质量记录 ID 被多个 Unit 复用：{quality_id}",
                    path,
                )
            quality_owners[quality_id] = unit_id
        expected_next = raw_units[index + 1].get("unit_id") if index + 1 < len(raw_units) and isinstance(raw_units[index + 1], dict) else None
        validate_unit_handoff(unit, unit_id, expected_next, path, report)
        if unit.get("global_state_sha256") != data.get("global_state_sha256"):
            report.error("E_UNIT_GLOBAL_STATE", "已接受 Unit 必须回链冻结 global_state_sha256", path)
        compile_state = expected_unit_compile_state(unit, data.get("global_state_sha256"))
        compile_sha256 = sha256_value(compile_state)
        if unit.get("unit_compile_sha256") != compile_sha256:
            report.error("E_UNIT_COMPILE_HASH", "unit_compile_sha256 与真实 Unit 成品不匹配", path)
        compiled[unit_id] = {
            "quality_id": quality_id,
            "unit_compile_sha256": compile_sha256,
            "prompt_chars": prompt_chars,
            "source_refs": set(covered_refs),
            "compile_status": compile_status,
        }

    seen: set[str] = set()
    duplicates = {ref for ref in all_unit_source_refs if ref in seen or seen.add(ref)}
    if duplicates:
        report.error("E_RENDER_DUPLICATE", f"成片来源被多个 Unit 重复主引用：{sorted(duplicates)}", "$.units")
    referenced = set(all_unit_source_refs)
    authorization_ids = {
        item.get("authorization_id")
        for item in data.get("authorizations", [])
        if isinstance(item, dict) and isinstance(item.get("authorization_id"), str)
    }
    for atom_id in sorted(compile_targets - referenced):
        atom = atom_map[atom_id]
        status = atom.get("coverage_status")
        authorization_id = atom.get("authorization_id")
        if status not in {"authorized_omission"} or authorization_id not in authorization_ids:
            report.error("E_RENDER_COVERAGE", f"成片来源未被 Unit 覆盖：{atom_id}", "$.source_atoms")

    source_positions = {atom_id: index for index, atom_id in enumerate(atom_map)}
    positions = [source_positions[ref] for ref in all_unit_source_refs if ref in source_positions]
    if positions != sorted(positions):
        report.error("E_UNIT_SOURCE_ORDER", "Unit 来源映射相对冻结全文发生倒序", "$.units")
    return units, compiled, compiled_trace_coverage


def validate_global_state(data: dict[str, Any], unit_ids: list[str], report: Report) -> None:
    expected = expected_global_state(data)
    if normalize_value(data.get("global_state")) != normalize_value(expected):
        report.error("E_GLOBAL_STATE_PROJECTION", "global_state 不是当前 Phase-A 投影", "$.global_state")
    expected_hash = sha256_value(expected)
    if data.get("global_state_sha256") != expected_hash:
        report.error("E_GLOBAL_STATE_HASH", "global_state_sha256 与当前投影不匹配", "$.global_state_sha256")
    skeleton = expected_skeleton_sha256(data, unit_ids)
    if data.get("skeleton_sha256") != skeleton:
        report.error("E_SKELETON_HASH", "skeleton_sha256 与来源/global state/Unit manifest 不匹配", "$.skeleton_sha256")


def validate_delivery_status(data: dict[str, Any], report: Report) -> tuple[str | None, str | None]:
    delivery_mode = data.get("delivery_mode")
    status = data.get("project_status")
    if delivery_mode not in DELIVERY_MODES:
        report.error("E_DELIVERY_MODE", "delivery_mode 必须为 TEXT_ONLY_ECO_TEST 或 MEDIA_ENABLED", "$.delivery_mode")
        return None, None
    allowed_statuses = TEXT_PROJECT_STATUSES if delivery_mode == "TEXT_ONLY_ECO_TEST" else MEDIA_PROJECT_STATUSES
    if data.get("contract_version") == LEGACY_CONTRACT_VERSION:
        allowed_statuses = allowed_statuses - {"PILOT_REWORK_REQUIRED"}
    if status not in allowed_statuses:
        report.error("E_PROJECT_STATUS", f"{delivery_mode} 的 project_status 不合法", "$.project_status")
        return delivery_mode, None
    return delivery_mode, status


def validate_text_status_contract(
    data: dict[str, Any], delivery_mode: str | None, status: str | None, report: Report
) -> None:
    if delivery_mode != "TEXT_ONLY_ECO_TEST":
        return
    axes = data.get("status_contract")
    if not isinstance(axes, dict):
        report.error("E_TEXT_STATUS_CONSISTENCY", "纯文字合同缺少 status_contract", "$.status_contract")
        return
    if uses_locked_director_scaffold(data):
        expected = expected_text_status_contract(status)
        if axes != expected:
            workflow = axes.get("workflow_status") if isinstance(
                axes.get("workflow_status"), dict
            ) else {}
            if workflow.get("spec_status") in TEXT_PROJECT_STATUSES:
                report.error(
                    "E_SPEC_STATUS_NAMESPACE",
                    "longform text end state cannot be written into workflow spec_status",
                    "$.status_contract.workflow_status.spec_status",
                )
            if workflow.get("observation_status") == "NOT_EXECUTED":
                report.error(
                    "E_OBSERVATION_STATUS_NAMESPACE",
                    "NOT_EXECUTED belongs to execution_status, not observation_status",
                    "$.status_contract.workflow_status.observation_status",
                )
            report.error(
                "E_TEXT_STATUS_CONSISTENCY",
                "1.3 status_contract must exactly map the text end state into generic workflow namespaces",
                "$.status_contract",
            )
        if data.get("production_validation") != axes.get("production_validation"):
            report.error(
                "E_TEXT_STATUS_CONSISTENCY",
                "status_contract.production_validation differs from the root status",
                "$.status_contract.production_validation",
            )
        return
    status_axes = TEXT_STATUS_AXES if uses_source_window_contract(data) else LEGACY_TEXT_STATUS_AXES
    expected = {
        "text_end_state": status,
        "spec_status": status,
        **status_axes,
    }
    if axes != expected:
        report.error(
            "E_TEXT_STATUS_CONSISTENCY",
            "text_end_state/spec_status/排除项与真实性轴必须和当前纯文字终点完全一致",
            "$.status_contract",
        )
    if data.get("production_validation") != axes.get("production_validation"):
        report.error(
            "E_TEXT_STATUS_CONSISTENCY",
            "status_contract.production_validation 与根状态不一致",
            "$.status_contract.production_validation",
        )


def validate_runtime_identity(data: dict[str, Any], report: Report) -> None:
    """Bind a formal r7+ run to the helper payload that actually prepared it.

    An outer archive SHA cannot truthfully self-embed, so the contract records
    NOT_EXPOSED instead of inventing one.  MANIFEST and helper-lock bindings
    remain locally recomputable in both source and extracted runtime packages.
    """

    if not is_r8_contract(data):
        return
    identity = data.get("runtime_identity")
    expected_keys = {
        "identity_version",
        "skill_build_id",
        "skill_manifest_sha256",
        "helper_scripts_sha256",
        "python_runtime",
        "helper_lock_sha256",
        "archive_identity_status",
    }
    if not isinstance(identity, dict) or set(identity) != expected_keys:
        report.error(
            "E_RUNTIME_IDENTITY",
            "runtime_identity 必须是可复算的精确七字段对象",
            "$.runtime_identity",
        )
        return
    manifest_path = Path(__file__).resolve().parent.parent / "MANIFEST.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        report.error("E_RUNTIME_IDENTITY", "当前运行包 MANIFEST.json 不可读", "$.runtime_identity")
        return
    expected_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    expected_build = manifest.get("build") if isinstance(manifest, dict) else None
    script_root = Path(__file__).resolve().parent
    try:
        helper_projection = [
            {
                "name": name,
                "sha256": hashlib.sha256((script_root / name).read_bytes()).hexdigest(),
            }
            for name in (
                "prepare_longform_authoring.py",
                "finalize_longform_contract.py",
                "validate_longform_contract.py",
            )
        ]
    except OSError:
        helper_projection = []
    expected_helpers_sha = sha256_value(helper_projection) if helper_projection else None
    if (
        identity.get("identity_version") != "alpha7-runtime-identity-1.0"
        or identity.get("skill_build_id") != expected_build
        or identity.get("skill_manifest_sha256") != expected_manifest_sha
        or identity.get("helper_scripts_sha256") != expected_helpers_sha
        or identity.get("python_runtime") != sys.version
        or identity.get("helper_lock_sha256") != data.get("helper_lock_sha256")
        or identity.get("archive_identity_status") != "NOT_EXPOSED"
    ):
        report.error(
            "E_RUNTIME_IDENTITY",
            "runtime_identity 与当前 MANIFEST/helper lock 不一致；不得伪造外层 archive SHA",
            "$.runtime_identity",
        )


def validate_output_contract(
    data: dict[str, Any],
    base: Path,
    contract_name: str | None,
    delivery_mode: str | None,
    report: Report,
) -> None:
    if delivery_mode != "TEXT_ONLY_ECO_TEST":
        return
    contract = data.get("output_contract")
    if not isinstance(contract, dict):
        report.error("E_OUTPUT_CONTRACT", "纯文字运行缺少 output_contract", "$.output_contract")
        return
    expected_keys = {
        "workspace_memory_policy",
        "strict_output_set",
        "exact_relative_output_names",
        "temp_root",
        "temp_input_names",
        "temp_root_cleaned",
    }
    if is_r8_contract(data):
        expected_keys.add("commit_mode")
    if set(contract) != expected_keys:
        report.error("E_OUTPUT_CONTRACT", "output_contract 字段不完整或含未授权扩展", "$.output_contract")
    if contract.get("workspace_memory_policy") != "DO_NOT_WRITE":
        report.error("E_OUTPUT_MEMORY_POLICY", "workspace_memory_policy 必须为 DO_NOT_WRITE", "$.output_contract")
    if contract.get("strict_output_set") is not True:
        report.error("E_OUTPUT_CONTRACT", "strict_output_set 必须为 true", "$.output_contract.strict_output_set")
    commit_mode = contract.get("commit_mode") if is_r8_contract(data) else SIBLING_COMMIT_MODE
    if is_r8_contract(data) and commit_mode not in COMMIT_MODES:
        report.error("E_OUTPUT_COMMIT_MODE", "commit_mode 不是受支持的三载体提交模式", "$.output_contract.commit_mode")
    names = contract.get("exact_relative_output_names")
    if not unique_strings(names) or len(names) != 3:
        report.error("E_OUTPUT_SET", "exact_relative_output_names 必须恰含 3 个唯一相对文件名", "$.output_contract")
        names = []
    if names and len({unicodedata.normalize("NFC", name).rstrip(" .").casefold() for name in names}) != 3:
        report.error("E_OUTPUT_SET", "Windows/NFC 规范化后输出名也必须唯一", "$.output_contract")
    for index, name in enumerate(names):
        pure = PurePosixPath(name.replace("\\", "/"))
        extension = OUTPUT_ROLE_EXTENSIONS[index]
        if (
            pure.is_absolute()
            or len(pure.parts) != 1
            or ".." in pure.parts
            or name in {".", ".."}
            or unicodedata.normalize("NFC", name) != name
            or INVALID_WINDOWS_BASENAME_RE.search(name) is not None
            or INVISIBLE_FILENAME_RE.search(name) is not None
            or name.endswith((".", " "))
            or name.split(".", 1)[0].upper() in WINDOWS_RESERVED_BASENAMES
        ):
            report.error("E_OUTPUT_SET", "输出名必须是当前目录内的单层安全相对文件名", "$.output_contract")
            continue
        if not name.casefold().endswith(extension):
            report.error(
                "E_OUTPUT_SET",
                f"输出角色 {index + 1} 必须使用 {extension} 扩展名：{name}",
                "$.output_contract",
            )
    if contract_name is None or not names or contract_name != names[1]:
        report.error(
            "E_OUTPUT_SELF_VALIDATION",
            "被验证 JSON 自身必须是 exact output set 中登记的 machine-state 文件",
            "$.output_contract",
        )

    temp_root = contract.get("temp_root")
    if commit_mode == IN_PLACE_COMMIT_MODE:
        if temp_root != "." or contract.get("temp_root_cleaned") is not True:
            report.error(
                "E_OUTPUT_TEMP_ROOT",
                "IN_PLACE 提交必须登记 temp_root='.'，终点必须标记三载体已消费",
                "$.output_contract.temp_root",
            )
        if any((base / name).exists() for name in TEMP_INPUT_NAMES):
            report.error(
                "E_OUTPUT_TEMP_ROOT",
                "IN_PLACE 终点不得残留 TARGET_PLAN/AUTHORING/OVERLAYS 载体",
                "$.output_contract.temp_input_names",
            )
    elif commit_mode == SIBLING_COMMIT_MODE:
        temp_pure = PurePosixPath(str(temp_root).replace("\\", "/")) if isinstance(temp_root, str) else None
        temp_path = safe_relative_path(base.parent, temp_root) if isinstance(temp_root, str) else None
        if (
            temp_path is None
            or temp_pure is None
            or temp_pure.is_absolute()
            or len(temp_pure.parts) != 1
            or not re.fullmatch(r"\.alpha7-tmp-RUN\d+", temp_pure.name)
        ):
            report.error("E_OUTPUT_TEMP_ROOT", "SIBLING temp_root 必须是输出目录同级的 .alpha7-tmp-RUNn 安全单层目录", "$.output_contract.temp_root")
        elif contract.get("temp_root_cleaned") is not True or temp_path.exists():
            report.error("E_OUTPUT_TEMP_ROOT", "终点前 sibling temp_root 必须已清理且不存在", "$.output_contract.temp_root")
    if contract.get("temp_input_names") != TEMP_INPUT_NAMES:
        report.error(
            "E_OUTPUT_TEMP_ROOT",
            "temp_input_names 必须锁定 TARGET_PLAN/AUTHORING/OVERLAYS，禁止旁路脚本或其他临时产物",
            "$.output_contract.temp_input_names",
        )

    try:
        actual = sorted(
            item.relative_to(base).as_posix()
            for item in base.rglob("*")
            if item.is_file()
        )
    except OSError as exc:
        report.error("E_OUTPUT_SCAN", f"无法扫描严格输出目录：{exc}", "$.output_contract")
        return
    if sorted(names) != actual:
        report.error(
            "E_OUTPUT_SET",
            f"严格输出集合不一致：expected={sorted(names)!r}, actual={actual!r}",
            "$.output_contract",
        )


def validate_batch_plan(
    data: dict[str, Any],
    unit_ids: list[str],
    compiled: dict[str, dict[str, Any]],
    delivery_mode: str | None,
    status: str | None,
    report: Report,
) -> list[dict[str, Any]]:
    plan = data.get("batch_plan")
    if not isinstance(plan, dict):
        report.error("E_BATCH_PLAN", "batch_plan 必须是对象", "$.batch_plan")
        return []
    requested = plan.get("requested_mode")
    normalized = plan.get("normalized_mode")
    if not isinstance(requested, str) or requested not in MODE_ALIASES:
        report.error("E_MODE_NORMALIZATION", f"未知 requested_mode：{requested!r}", "$.batch_plan.requested_mode")
    elif normalized != MODE_ALIASES[requested]:
        report.error("E_MODE_NORMALIZATION", "requested_mode 未按合同规范化", "$.batch_plan.normalized_mode")
    batches = plan.get("batches")
    if not isinstance(batches, list):
        report.error("E_BATCH_PLAN", "batches 必须是数组", "$.batch_plan.batches")
        return []
    batches_required = delivery_mode == "MEDIA_ENABLED" or status == "TEXT_SPEC_COMPLETE"
    if batches_required and not batches:
        report.error("E_BATCH_PLAN", "当前终点必须提供连续生产批次", "$.batch_plan.batches")
        return []
    normalized_batches: list[dict[str, Any]] = []
    covered: list[str] = []
    committed_ids = {
        item.get("checkpoint_id")
        for item in data.get("checkpoints", [])
        if isinstance(item, dict) and item.get("status") == "COMMITTED"
    }
    for index, batch in enumerate(batches):
        path = f"$.batch_plan.batches[{index}]"
        if not isinstance(batch, dict):
            report.error("E_BATCH_PLAN", "Batch 必须是对象", path)
            continue
        expected_id = f"B{index + 1:03d}"
        if batch.get("batch_id") != expected_id or not BATCH_ID_RE.fullmatch(str(batch.get("batch_id", ""))):
            report.error("E_BATCH_ORDER", f"Batch ID 应为 {expected_id}", f"{path}.batch_id")
        batch_units = batch.get("unit_ids")
        if not unique_strings(batch_units):
            report.error("E_BATCH_UNITS", "Batch unit_ids 必须是无重复字符串数组", f"{path}.unit_ids")
            batch_units = []
        normalized_batch = dict(batch)
        normalized_batch["unit_ids"] = batch_units
        normalized_batches.append(normalized_batch)
        covered.extend(batch_units)
        is_final = index == len(batches) - 1
        if any(key in batch for key in ("is_pilot", "pilot_unit_ids", "prompt_pilot")):
            report.error("E_PILOT_BATCH_COUPLING", "Prompt Pilot 不得绑定或嵌入连续 Batch", path)
        if batch.get("is_final") is not is_final:
            report.error("E_BATCH_FINAL_FLAG", "只有最后一批必须标记 is_final=true", f"{path}.is_final")
        count = len(batch_units)
        exception = batch.get("batch_budget_exception")
        valid_exception = (
            isinstance(exception, dict)
            and exception.get("code") in ALLOWED_EXCEPTION_CODES
            and nonempty_string(exception.get("reason"))
        )
        if count > 10 or (count < 4 and not (is_final or valid_exception)):
            report.error("E_BATCH_SIZE", "连续批次通常为 4—10 个 Unit，越界需合法例外", f"{path}.unit_ids")
        actual_chars = batch.get("actual_prompt_chars")
        if batch.get("batch_id") in committed_ids:
            expected_chars = sum(
                compiled.get(unit_id, {}).get("prompt_chars", 0)
                for unit_id in batch_units
            )
            if not isinstance(actual_chars, int) or isinstance(actual_chars, bool) or actual_chars != expected_chars:
                report.error("E_BATCH_CHAR_RECOMPUTE", "已提交批次的 actual_prompt_chars 必须由 Prompt 正文重算", f"{path}.actual_prompt_chars")
            elif not is_final and not 18000 <= actual_chars <= 28000 and not valid_exception:
                report.error("E_BATCH_CHAR_BUDGET", "非末批超出 18,000—28,000 时必须有结构化例外", path)
        elif actual_chars is not None:
            report.error("E_BATCH_CHAR_PRECOMMIT", "未提交批次 actual_prompt_chars 必须为 null", f"{path}.actual_prompt_chars")
    if batches and covered != unit_ids:
        report.error("E_BATCH_COVERAGE", "所有 Batch 必须按顺序无缺口覆盖完整 Unit Manifest", "$.batch_plan.batches")
    return normalized_batches


def validate_prompt_pilot(
    data: dict[str, Any],
    unit_ids: list[str],
    compiled: dict[str, dict[str, Any]],
    delivery_mode: str | None,
    status: str | None,
    report: Report,
) -> list[str]:
    pilot = data.get("prompt_pilot")
    pilot_required = status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE", "IN_PROGRESS", "COMPLETE"}
    if not pilot_required:
        if pilot not in (None, {}):
            report.error("E_PILOT_PREMATURE", "GLOBAL_READY 不得预铺 Prompt Pilot", "$.prompt_pilot")
        return []
    if not isinstance(pilot, dict):
        report.error("E_PILOT_SCHEMA", "当前终点必须单独提供 prompt_pilot", "$.prompt_pilot")
        return []
    if any(key in pilot for key in ("batch_id", "batch_unit_ids", "checkpoint_id", "is_pilot")):
        report.error("E_PILOT_BATCH_COUPLING", "prompt_pilot 不得硬绑首个连续批次", "$.prompt_pilot")
    samples = pilot.get("sample_unit_ids")
    quality_ids = pilot.get("prompt_quality_record_ids")
    if not unique_strings(samples) or not 3 <= len(samples) <= 5:
        report.error("E_PILOT_SIZE", "Prompt Pilot 必须含 3—5 个唯一代表 Unit", "$.prompt_pilot.sample_unit_ids")
        samples = []
    if any(unit_id not in unit_ids for unit_id in samples):
        report.error("E_PILOT_UNITS", "Prompt Pilot 引用了未知 Unit", "$.prompt_pilot.sample_unit_ids")
    spread = pilot.get("spread_policy")
    spread_claim = spread.get("claim") if isinstance(spread, dict) and set(spread) == {"claim"} else None
    if spread_claim not in PILOT_SPREAD_CLAIMS:
        report.error(
            "E_PILOT_SPREAD",
            "prompt_pilot.spread_policy 必须声明 NONCONTIGUOUS、EARLY_MIDDLE_LATE 或 TARGETED_EXACT_RANGES",
            "$.prompt_pilot.spread_policy",
        )
    else:
        positions = sorted(unit_ids.index(unit_id) for unit_id in samples if unit_id in unit_ids)
        noncontiguous = len(positions) == len(samples) and all(
            right - left > 1 for left, right in zip(positions, positions[1:])
        )
        if spread_claim == "NONCONTIGUOUS" and not noncontiguous:
            report.error("E_PILOT_SPREAD", "Pilot 声称 NONCONTIGUOUS，但样本 Unit order 实际相邻", "$.prompt_pilot")
        if spread_claim == "EARLY_MIDDLE_LATE":
            total = len(unit_ids)
            bands = {
                min(2, (position * 3) // total)
                for position in positions
            } if total else set()
            if bands != {0, 1, 2}:
                report.error(
                    "E_PILOT_SPREAD",
                    "Pilot 声称 EARLY_MIDDLE_LATE，但样本未真实覆盖 Unit order 三段",
                    "$.prompt_pilot",
                )
        if spread_claim == "TARGETED_EXACT_RANGES":
            request = data.get("selection_request")
            if not isinstance(request, dict) or request.get("selection_mode") != "USER_TARGETED_EXACT_RANGES_V1":
                report.error(
                    "E_PILOT_SPREAD",
                    "TARGETED_EXACT_RANGES 只允许 helper 锁定的 USER_TARGETED 模式",
                    "$.prompt_pilot",
                )
    expected_quality_ids = [compiled.get(unit_id, {}).get("quality_id") for unit_id in samples]
    if not unique_strings(quality_ids) or quality_ids != expected_quality_ids:
        report.error("E_PILOT_QUALITY_IDS", "Pilot 质量记录 ID 必须与样本 Unit 精确一一对应", "$.prompt_pilot.prompt_quality_record_ids")
    if pilot.get("status") != "PASS" or not nonempty_string(pilot.get("selection_basis")):
        report.error("E_PILOT_NOT_READY", "Prompt Pilot 必须有代表性选择依据且状态为 PASS", "$.prompt_pilot")
    if uses_source_window_contract(data):
        request = data.get("selection_request")
        selection_mode = pilot.get("selection_mode")
        allowed_modes = {"USER_TARGETED_EXACT_RANGES_V1", "MACHINE_REPRESENTATIVE_V1"}
        if (
            not isinstance(request, dict)
            or request.get("selection_mode") not in allowed_modes
            or selection_mode != request.get("selection_mode")
            or request.get("sample_unit_ids") != samples
        ):
            report.error(
                "E_SELECTION_MODE",
                "Prompt Pilot 必须复用 helper 锁定的 USER_TARGETED 或 MACHINE selection",
                "$.prompt_pilot.selection_mode",
            )
        evidence = pilot.get("selection_evidence")
        expected_evidence = request.get("selection_evidence") if isinstance(request, dict) else None
        if evidence != expected_evidence:
            report.error(
                "E_SELECTION_EVIDENCE",
                "selection_evidence 必须与 helper 的可复算选择证据完全一致",
                "$.prompt_pilot.selection_evidence",
            )
        if isinstance(evidence, dict):
            if evidence.get("unit_manifest_sha256") != data.get("unit_manifest_sha256"):
                report.error("E_SELECTION_HASH", "selection unit manifest hash 不匹配", "$.prompt_pilot.selection_evidence")
            if evidence.get("feature_matrix_sha256") != data.get("feature_matrix_sha256"):
                report.error("E_SELECTION_HASH", "selection feature matrix hash 不匹配", "$.prompt_pilot.selection_evidence")
            positions = [unit_ids.index(unit_id) for unit_id in samples if unit_id in unit_ids]
            gaps = [right - left for left, right in zip(positions, positions[1:])]
            if (
                evidence.get("selected_unit_ids") != samples
                or evidence.get("selected_order_indexes") != positions
                or evidence.get("adjacent_order_gaps") != gaps
                or evidence.get("derived_noncontiguous") != (bool(gaps) and all(gap > 1 for gap in gaps))
            ):
                report.error("E_SELECTION_EVIDENCE", "selection 位置/间距证据不可复算", "$.prompt_pilot.selection_evidence")
        if any(
            isinstance(value, str) and value.strip().lower() == "pending"
            for _, value in recursive_items({"selection_mode": selection_mode, "selection_evidence": evidence})
        ):
            report.error("E_SELECTION_PENDING", "selection mode/hash/evidence 禁止 PENDING", "$.prompt_pilot")
    for unit_id in samples:
        if unit_id not in compiled:
            report.error("E_ACCEPTED_UNIT_INCOMPLETE", f"Pilot Unit {unit_id} 不是完整成品", "$.prompt_pilot")
    return list(samples)


def validate_checkpoints(
    data: dict[str, Any],
    unit_ids: list[str],
    batches: list[dict[str, Any]],
    compiled: dict[str, dict[str, Any]],
    delivery_mode: str | None,
    status: str | None,
    report: Report,
) -> list[str]:
    checkpoints = data.get("checkpoints")
    if not isinstance(checkpoints, list):
        report.error("E_CHECKPOINT_SCHEMA", "checkpoints 必须是数组", "$.checkpoints")
        return []
    if status in {"GLOBAL_READY", "TEXT_PILOT_COMPLETE"} and checkpoints:
        report.error("E_CHECKPOINT_PROGRESS", f"{status} 必须允许并保持 0 个 committed checkpoint", "$.checkpoints")
    if delivery_mode == "MEDIA_ENABLED" and status == "IN_PROGRESS" and (
        not checkpoints or len(checkpoints) >= len(batches)
    ):
        report.error("E_CHECKPOINT_PROGRESS", "IN_PROGRESS 必须提交至少一批但少于完整批次", "$.checkpoints")
    if status in {"COMPLETE", "TEXT_SPEC_COMPLETE"} and len(checkpoints) != len(batches):
        report.error("E_CHECKPOINT_PROGRESS", f"{status} 必须提交全部连续批次", "$.checkpoints")
    if len(checkpoints) > len(batches):
        report.error("E_CHECKPOINT_PROGRESS", "checkpoint 数量超过批次计划", "$.checkpoints")

    previous_hash = data.get("skeleton_sha256")
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    raw_units = data.get("units") if isinstance(data.get("units"), list) else []
    checkpoint_hashes: list[str] = []
    accepted_in_order: list[str] = []
    for index, checkpoint in enumerate(checkpoints):
        path = f"$.checkpoints[{index}]"
        if not isinstance(checkpoint, dict):
            report.error("E_CHECKPOINT_SCHEMA", "checkpoint 必须是对象", path)
            continue
        expected_batch = batches[index] if index < len(batches) else {}
        expected_id = expected_batch.get("batch_id")
        if checkpoint.get("checkpoint_id") != expected_id:
            report.error("E_CHECKPOINT_ORDER", "checkpoint_id 必须与对应 Batch 一致", f"{path}.checkpoint_id")
        if checkpoint.get("status") != "COMMITTED":
            report.error("E_CHECKPOINT_STATUS", "只有 COMMITTED checkpoint 计入进度", f"{path}.status")
        batch_units = expected_batch.get("unit_ids", [])
        if checkpoint.get("batch_units") != batch_units or checkpoint.get("accepted_units") != batch_units:
            report.error("E_CHECKPOINT_UNITS", "batch_units/accepted_units 必须与批次计划完全一致", path)
        accepted_in_order.extend(batch_units)
        expected_quality_ids = [compiled.get(unit_id, {}).get("quality_id") for unit_id in batch_units]
        if checkpoint.get("prompt_quality_record_ids") != expected_quality_ids or not unique_strings(expected_quality_ids):
            report.error("E_CHECKPOINT_QUALITY_IDS", "checkpoint 质量记录 ID 必须与 accepted_units 精确相等", path)
        expected_compile_hashes = {
            unit_id: compiled.get(unit_id, {}).get("unit_compile_sha256") for unit_id in batch_units
        }
        if checkpoint.get("unit_compile_sha256s") != expected_compile_hashes or any(
            unit_id not in compiled for unit_id in batch_units
        ):
            report.error("E_ACCEPTED_UNIT_INCOMPLETE", "checkpoint 接受了未形成完整可哈希成品的 Unit", path)
        if checkpoint.get("source_sha256") != source.get("source_sha256"):
            report.error("E_CHECKPOINT_SOURCE", "checkpoint source_sha256 不一致", path)
        if checkpoint.get("skeleton_sha256") != data.get("skeleton_sha256"):
            report.error("E_CHECKPOINT_SKELETON", "checkpoint skeleton_sha256 不一致", path)
        if checkpoint.get("global_state_sha256") != data.get("global_state_sha256"):
            report.error("E_CHECKPOINT_GLOBAL_STATE", "checkpoint 未引用冻结 global_state_sha256", path)
        if checkpoint.get("previous_checkpoint_sha256") != previous_hash:
            report.error("E_CHECKPOINT_CHAIN", "previous_checkpoint_sha256 链断裂", path)
        checkpoint_body = {key: value for key, value in checkpoint.items() if key != "sha256"}
        expected_hash = sha256_value(checkpoint_body)
        if checkpoint.get("sha256") != expected_hash:
            report.error("E_CHECKPOINT_HASH", "checkpoint canonical sha256 不匹配", f"{path}.sha256")
        checkpoint_hashes.append(expected_hash)
        previous_hash = expected_hash

        if batch_units:
            last_unit = batch_units[-1]
            try:
                last_index = unit_ids.index(last_unit)
                expected_next = unit_ids[last_index + 1] if last_index + 1 < len(unit_ids) else None
            except ValueError:
                expected_next = None
                report.error("E_CHECKPOINT_UNITS", "checkpoint 引用了未知 Unit", path)
        else:
            last_unit, expected_next = None, None
        if checkpoint.get("next_unit_id") != expected_next:
            report.error("E_CHECKPOINT_NEXT_UNIT", "checkpoint next_unit_id 不正确", f"{path}.next_unit_id")
        snapshot = checkpoint.get("continuity_snapshot")
        if not isinstance(snapshot, dict) or not CONTINUITY_SNAPSHOT_KEYS.issubset(snapshot):
            report.error("E_CONTINUITY_SNAPSHOT", "continuity_snapshot 缺少必需状态字段", f"{path}.continuity_snapshot")
        handoff = checkpoint.get("batch_handoff")
        if not isinstance(handoff, dict):
            report.error("E_BATCH_HANDOFF_SCOPE", "checkpoint 缺少 batch_handoff", f"{path}.batch_handoff")
        else:
            expected_next_checkpoint = batches[index + 1].get("batch_id") if index + 1 < len(batches) else None
            checks = {
                "scope": "BATCH_TO_BATCH",
                "from_checkpoint_id": expected_id,
                "next_checkpoint_id": expected_next_checkpoint,
                "last_accepted_unit_id": last_unit,
                "next_unit_id": expected_next,
                "boundary_after": last_unit,
            }
            for key, value in checks.items():
                if handoff.get(key) != value:
                    report.error("E_BATCH_HANDOFF_SCOPE", f"batch_handoff.{key} 不正确", f"{path}.batch_handoff")
            if "sha256" in handoff or "checkpoint_sha256" in handoff:
                report.error("E_BATCH_HANDOFF_RECURSIVE_HASH", "batch_handoff 不得自含当前 checkpoint hash", f"{path}.batch_handoff")
            if last_unit in unit_ids and unit_ids.index(last_unit) < len(raw_units):
                unit = raw_units[unit_ids.index(last_unit)]
                unit_next = unit.get("unit_handoff_out", {}).get("to_unit_id") if isinstance(unit, dict) else None
                if handoff.get("next_unit_id") != unit_next:
                    report.error("E_HANDOFF_NEXT_MISMATCH", "Unit 与 Batch handoff 的 next Unit 不一致", f"{path}.batch_handoff")

    expected_latest = checkpoints[-1].get("checkpoint_id") if checkpoints and isinstance(checkpoints[-1], dict) else None
    if data.get("latest_checkpoint_id") != expected_latest:
        report.error("E_LATEST_CHECKPOINT", "latest_checkpoint_id 未指向最后 committed checkpoint", "$.latest_checkpoint_id")
    expected_latest_hash = checkpoint_hashes[-1] if checkpoint_hashes else None
    if data.get("latest_checkpoint_sha256") != expected_latest_hash:
        report.error(
            "E_LATEST_CHECKPOINT",
            "latest_checkpoint_sha256 未指向最后 committed checkpoint 的 canonical hash",
            "$.latest_checkpoint_sha256",
        )
    return accepted_in_order


def validate_compilation_scope(
    data: dict[str, Any],
    unit_ids: list[str],
    compile_targets: set[str],
    compiled: dict[str, dict[str, Any]],
    compiled_trace_coverage: set[str],
    pilot_samples: list[str],
    checkpoint_units: list[str],
    delivery_mode: str | None,
    status: str | None,
    report: Report,
) -> None:
    compiled_ids = set(compiled)
    if status == "GLOBAL_READY" and compiled_ids:
        report.error("E_GLOBAL_READY_ARTIFACTS", "GLOBAL_READY 必须保持 0 个 Prompt 成品/空壳", "$.units")
    if status == "PILOT_REWORK_REQUIRED" and compiled_ids:
        report.error(
            "E_REWORK_ACCEPTED_ARTIFACT",
            "PILOT_REWORK_REQUIRED 不得保留 ACCEPTED/COMMITTED 或 PASS 质量卡",
            "$.units",
        )
    if status == "TEXT_PILOT_COMPLETE" and compiled_ids != set(pilot_samples):
        report.error("E_PILOT_SCOPE", "TEXT_PILOT_COMPLETE 只接受单独登记的 Pilot 样本成品", "$.units")
    if status in {"TEXT_SPEC_COMPLETE", "COMPLETE"} and compiled_ids != set(unit_ids):
        report.error("E_TEXT_SPEC_INCOMPLETE", "完整终点必须让全部 Unit 形成成品", "$.units")
    if status == "IN_PROGRESS" and compiled_ids != set(checkpoint_units).union(pilot_samples):
        report.error("E_CHECKPOINT_PROGRESS", "IN_PROGRESS 成品范围必须等于 Pilot 与已提交连续批次", "$.units")
    for unit_id in checkpoint_units:
        if unit_id not in compiled:
            report.error("E_ACCEPTED_UNIT_INCOMPLETE", f"checkpoint accepted Unit {unit_id} 缺少真实成品", "$.units")
    if status == "TEXT_SPEC_COMPLETE" and compiled_trace_coverage != compile_targets:
        report.error(
            "E_TEXT_SPEC_SOURCE_PRODUCT_COVERAGE",
            "TEXT_SPEC_COMPLETE 必须由非空成品 trace 覆盖所有 compile-target 来源",
            "$.units",
        )


def validate_continuation_authorization(data: dict[str, Any], delivery_mode: str | None, report: Report) -> None:
    if delivery_mode != "TEXT_ONLY_ECO_TEST":
        return
    authorization = data.get("continuation_authorization")
    expected_keys = {"scope", "external_actions", "creative_defaults", "stop_conditions"}
    if not isinstance(authorization, dict) or set(authorization) != expected_keys:
        report.error("E_CONTINUATION_AUTHORIZATION", "纯文字连续授权必须使用有界固定字段", "$.continuation_authorization")
        return
    if (
        authorization.get("scope") != "TEXT_ONLY_TO_RUN_SUMMARY"
        or authorization.get("external_actions") is not False
        or authorization.get("creative_defaults") != "PROPOSED_ONLY"
        or authorization.get("stop_conditions") != TEXT_STOP_CONDITIONS
    ):
        report.error(
            "E_CONTINUATION_AUTHORIZATION",
            "纯文字授权不得扩大外部动作、创意默认或三项停止条件",
            "$.continuation_authorization",
        )


def validate_run_summary(
    data: dict[str, Any],
    unit_ids: list[str],
    compile_target_ids: list[str],
    compiled: dict[str, dict[str, Any]],
    pilot_samples: list[str],
    checkpoint_units: list[str],
    delivery_mode: str | None,
    status: str | None,
    report: Report,
    require_actual_validation: bool = True,
) -> None:
    if delivery_mode != "TEXT_ONLY_ECO_TEST":
        return
    summary = data.get("run_summary")
    if not isinstance(summary, dict):
        report.error("E_RUN_SUMMARY", "TEXT_ONLY_ECO_TEST 每轮必须有结构化 run_summary", "$.run_summary")
        return
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    expected_completed = [unit_id for unit_id in unit_ids if unit_id in compiled]
    expected_quality_ids = [compiled[unit_id].get("quality_id") for unit_id in pilot_samples if unit_id in compiled]
    expected_pilot_status = "PASS" if pilot_samples else "NOT_RUN"
    expected_entrypoint = {
        "GLOBAL_READY": "PROMPT_PILOT",
        "PILOT_REWORK_REQUIRED": "AUTHORING_REWORK",
        "TEXT_PILOT_COMPLETE": "EDITORIAL_REVIEW",
        "TEXT_SPEC_COMPLETE": "TEXT_SPEC_COMPLETE",
    }.get(status)
    remaining = [unit_id for unit_id in unit_ids if unit_id not in checkpoint_units]
    expected_next_unit = remaining[0] if remaining and status != "GLOBAL_READY" else (unit_ids[0] if unit_ids else None)
    if status == "TEXT_SPEC_COMPLETE":
        expected_next_unit = None
    if status == "TEXT_PILOT_COMPLETE":
        expected_next_unit = None
    checks = {
        "source_sha256": source.get("source_sha256"),
        "source_scope_unit_ids": unit_ids,
        "compile_target_atom_count": len(compile_target_ids),
        "compile_target_atom_ids_sha256": sha256_value(compile_target_ids),
        "selected_source_ranges": [
            {
                "unit_id": unit_id,
                "first_atom_id": data["units"][unit_ids.index(unit_id)].get("source_window", {}).get("first_atom_id"),
                "last_atom_id": data["units"][unit_ids.index(unit_id)].get("source_window", {}).get("last_atom_id"),
                "text_sha256": data["units"][unit_ids.index(unit_id)].get("source_window", {}).get("text_sha256"),
            }
            for unit_id in pilot_samples
            if unit_id in unit_ids
        ],
        "completed_unit_ids": expected_completed,
        "skipped_stages": R5_TEXT_SKIPPED_STAGES if uses_source_window_contract(data) else TEXT_SKIPPED_STAGES,
        "execution_status": "NOT_EXECUTED",
        "observation_status": (
            "NOT_APPLICABLE" if uses_locked_director_scaffold(data) else "NOT_EXECUTED"
        ),
        "media_qa_status": (
            "NOT_APPLICABLE" if uses_locked_director_scaffold(data) else "QA_NOT_EXECUTED"
        ),
        "production_validation": "NOT_TESTED",
    }
    if uses_source_window_contract(data):
        checks.update(
            {
                "stage_status": TEXT_EXCLUDED_STAGE_STATUS,
                "release_status": "RELEASE_NOT_READY",
                "learning_status": "NO_REAL_DATA",
            }
        )
    for key, value in checks.items():
        if summary.get(key) != value:
            report.error("E_RUN_SUMMARY", f"run_summary.{key} 与真实范围/状态不一致", f"$.run_summary.{key}")
    if uses_source_window_contract(data):
        expected_structural = (
            "PASS"
            if status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"}
            else "FAIL" if status == "PILOT_REWORK_REQUIRED" else "NOT_RUN"
        )
        review_axes = {
            "quality_scope": "CONTRACT_STRUCTURAL",
            "structural_validation_status": expected_structural,
            "editorial_review_status": "NOT_REVIEWED",
            "content_self_review_status": (
                "PASS" if status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"} else "NOT_RUN"
            ),
            "content_readiness": "REVIEW_REQUIRED",
        }
        for key, value in review_axes.items():
            if summary.get(key) != value:
                report.error(
                    "E_EDITORIAL_REVIEW_AXIS",
                    f"run_summary.{key} 必须把结构校验与未执行的编辑/内容审阅分开",
                    f"$.run_summary.{key}",
                )
    pilot_summary = summary.get("prompt_pilot")
    if not isinstance(pilot_summary, dict) or pilot_summary != {
        "sample_unit_ids": pilot_samples,
        "prompt_quality_record_ids": expected_quality_ids,
        "status": expected_pilot_status,
    }:
        report.error("E_RUN_SUMMARY", "run_summary.prompt_pilot 与单独登记的 Pilot 不一致", "$.run_summary.prompt_pilot")
    if not isinstance(summary.get("open_items"), list):
        report.error("E_RUN_SUMMARY", "run_summary.open_items 必须是数组", "$.run_summary.open_items")
    elif (
        uses_source_window_contract(data)
        and status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"}
        and "INDEPENDENT_EDITORIAL_REVIEW_REQUIRED" not in summary["open_items"]
    ):
        report.error(
            "E_CONTENT_SELF_REVIEW",
            "结构终点必须保留由本轮创作者之外的编辑复核待办，禁止笼统宣称已经跑通",
            "$.run_summary.open_items",
        )
    expected_resume = {
        "entrypoint": expected_entrypoint,
        "next_unit_id": expected_next_unit,
        "latest_checkpoint_id": data.get("latest_checkpoint_id"),
    }
    if summary.get("resume_entry") != expected_resume:
        report.error("E_RUN_SUMMARY", "run_summary.resume_entry 不是当前可恢复入口", "$.run_summary.resume_entry")
    if uses_source_window_contract(data) and require_actual_validation:
        validation = data.get("validation_result")
        expected_actual = {
            key: validation.get(key)
            for key in (
                "validator",
                "phase",
                "subject_sha256",
                "exit_code",
                "valid",
                "error_count",
                "error_codes",
                "production_validation",
                "package_sha256",
                "summary_sha256",
            )
        } if isinstance(validation, dict) else None
        if summary.get("actual_validation") != expected_actual:
            report.error(
                "E_RUN_SUMMARY_VALIDATION",
                "run_summary.actual_validation 必须精确投影根 validation_result",
                "$.run_summary.actual_validation",
            )
        if any(
            isinstance(value, str) and value.strip().lower() == "pending"
            for _, value in recursive_items(summary)
        ):
            report.error("E_RUN_SUMMARY_PENDING", "机器渲染总结禁止 PENDING", "$.run_summary")


def validate_recorded_validation_result(
    data: dict[str, Any], status: str | None, base: Path, report: Report
) -> None:
    if not uses_source_window_contract(data):
        return
    result = data.get("validation_result")
    expected_keys = {
        "validator",
        "phase",
        "subject_sha256",
        "exit_code",
        "valid",
        "error_count",
        "error_codes",
        "production_validation",
        "package_sha256",
        "summary_sha256",
    }
    if not isinstance(result, dict) or set(result) != expected_keys:
        report.error(
            "E_VALIDATION_RESULT",
            "r5 最终合同必须有 finalizer 写入的精确 validation_result",
            "$.validation_result",
        )
        return
    expected_subject = sha256_value(validation_subject_projection(data))
    if result.get("subject_sha256") != expected_subject:
        report.error(
            "E_VALIDATION_SUBJECT_HASH",
            "validation_result.subject_sha256 不是剔除自身/summary投影后的真实 hash",
            "$.validation_result.subject_sha256",
        )
    if result.get("validator") != "validate_longform_contract.py" or result.get("phase") != "TERMINAL_PROMOTION_GATE":
        report.error("E_VALIDATION_RESULT", "validation_result 的 validator/phase 不合法", "$.validation_result")
    if result.get("production_validation") != "NOT_TESTED":
        report.error("E_VALIDATION_RESULT", "文字验证不得解锁 Production Validation", "$.validation_result")
    names = data.get("output_contract", {}).get("exact_relative_output_names", [])
    package_name = names[0] if isinstance(names, list) and len(names) == 3 else None
    summary_name = names[2] if isinstance(names, list) and len(names) == 3 else None
    for field, name in (("package_sha256", package_name), ("summary_sha256", summary_name)):
        path = safe_relative_path(base, name) if isinstance(name, str) else None
        try:
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else None
        except OSError:
            actual_hash = None
        if not is_sha256(result.get(field)) or result.get(field) != actual_hash:
            report.error(
                "E_OUTPUT_DOCUMENT_HASH",
                f"validation_result.{field} 未绑定最终 MD 字节（recorded={result.get(field)!r}, actual={actual_hash!r}）",
                f"$.validation_result.{field}",
            )
    codes = result.get("error_codes")
    if not isinstance(codes, list) or codes != sorted(set(codes)) or not all(nonempty_string(code) for code in codes):
        report.error("E_VALIDATION_RESULT", "error_codes 必须是排序去重字符串数组", "$.validation_result.error_codes")
        codes = []
    if result.get("error_count") != len(codes):
        report.error("E_VALIDATION_RESULT", "error_count 必须等于唯一 error_codes 数", "$.validation_result")
    if status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"}:
        if result.get("valid") is not True or result.get("exit_code") != 0 or codes:
            report.error(
                "E_TERMINAL_PROMOTION",
                "只有 exit_code=0、valid=true、零错误才可保留文字终点",
                "$.validation_result",
            )
    elif status == "PILOT_REWORK_REQUIRED":
        if result.get("valid") is not False or result.get("exit_code") == 0 or not codes:
            report.error(
                "E_REWORK_VALIDATION_RESULT",
                "REWORK 必须保存非零退出与真实失败错误码",
                "$.validation_result",
            )
    if any(
        isinstance(value, str) and value.strip().lower() == "pending"
        for _, value in recursive_items(result)
    ):
        report.error("E_VALIDATION_PENDING", "validation_result 禁止 PENDING", "$.validation_result")


def validate_contract(
    data: Any,
    base: Path,
    contract_name: str | None = None,
    *,
    validate_outputs: bool = True,
    validate_recorded_result: bool = True,
) -> Report:
    report = Report()
    if not isinstance(data, dict):
        report.error("E_ROOT_SCHEMA", "合同根必须是 JSON object")
        return report
    if data.get("contract_version") not in ACCEPTED_CONTRACT_VERSIONS:
        report.error(
            "E_CONTRACT_VERSION",
            f"contract_version 必须为 current {CONTRACT_VERSION} 或只读兼容 "
            f"{V14_CONTRACT_VERSION}/{R9_CONTRACT_VERSION}/{R8_CONTRACT_VERSION}/"
            f"{R7_CONTRACT_VERSION}/{LEGACY_CONTRACT_VERSION}",
            "$.contract_version",
        )
    elif data.get("contract_version") in READ_ONLY_CONTRACT_VERSIONS:
        report.warn(
            "W_LEGACY_CONTRACT_READ_ONLY",
            "alpha7-longform-1.0/1.1/1.2/1.3/1.4 仅保留只读迁移兼容；新终点必须由 1.5 finalizer 生成",
            "$.contract_version",
        )
    if data.get("engine") != "SILVER_LONGFORM":
        report.error("E_ENGINE", "engine 必须为 SILVER_LONGFORM", "$.engine")

    source_text = load_source_text(data, base, report)
    atom_map, compile_targets = validate_source(data, source_text, report)
    validate_r5_source_derivatives(data, source_text, atom_map, report)
    units, compiled, compiled_trace_coverage = validate_units(data, atom_map, compile_targets, report)
    unit_ids = [unit.get("unit_id") for unit in units if isinstance(unit.get("unit_id"), str)]
    validate_global_state(data, unit_ids, report)
    delivery_mode, status = validate_delivery_status(data, report)
    validate_text_status_contract(data, delivery_mode, status, report)
    validate_runtime_identity(data, report)
    if validate_outputs:
        validate_output_contract(data, base, contract_name, delivery_mode, report)
    batches = validate_batch_plan(data, unit_ids, compiled, delivery_mode, status, report)
    pilot_samples = validate_prompt_pilot(data, unit_ids, compiled, delivery_mode, status, report)
    checkpoint_units = validate_checkpoints(
        data, unit_ids, batches, compiled, delivery_mode, status, report
    )
    validate_compilation_scope(
        data,
        unit_ids,
        compile_targets,
        compiled,
        compiled_trace_coverage,
        pilot_samples,
        checkpoint_units,
        delivery_mode,
        status,
        report,
    )
    validate_continuation_authorization(data, delivery_mode, report)
    compile_target_ids = [atom_id for atom_id in atom_map if atom_id in compile_targets]
    validate_run_summary(
        data,
        unit_ids,
        compile_target_ids,
        compiled,
        pilot_samples,
        checkpoint_units,
        delivery_mode,
        status,
        report,
        validate_recorded_result,
    )
    if validate_recorded_result:
        validate_recorded_validation_result(data, status, base, report)

    production_validation = data.get("production_validation")
    production_evidence = data.get("production_evidence")
    if production_validation != "NOT_TESTED":
        report.error(
            "E_PRODUCTION_EVIDENCE_BOUNDARY",
            "本验证器只验证编译合同，production_validation 必须保持 NOT_TESTED",
            "$.production_validation",
        )
    if production_evidence not in (None, {}, []):
        report.warn(
            "W_PRODUCTION_EVIDENCE_NOT_EVALUATED",
            "检测到媒体证据描述，但本验证器不会据此解锁 Production Validation",
            "$.production_evidence",
        )
    return report


def read_contract(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_phase_a_fixture() -> dict[str, Any]:
    pieces = [f"第{index:02d}段内容。\n" for index in range(1, 16)]
    source_text = "".join(pieces)
    atoms: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    cursor = 0
    for index, piece in enumerate(pieces, start=1):
        atom_id = f"SRC{index:04d}"
        unit_id = f"U{index:03d}"
        normalized_piece = normalize_text(piece)
        atoms.append(
            {
                "atom_id": atom_id,
                "kind": "DIALOGUE",
                "source_class": "RENDERABLE_NARRATIVE",
                "compile_target": True,
                "compile_reason": "当前段落需要进入成片",
                "start_cp": cursor,
                "end_cp": cursor + len(normalized_piece),
                "text": normalized_piece,
                "semantic_tags": ["CONTENT:EVENT"],
                "coverage_status": "mapped",
            }
        )
        cursor += len(normalized_piece)
        units.append(
            {
                "unit_id": unit_id,
                "order": index,
                "source_refs": [atom_id],
            }
        )

    data: dict[str, Any] = {
        "contract_version": LEGACY_CONTRACT_VERSION,
        "engine": "SILVER_LONGFORM",
        "delivery_mode": "TEXT_ONLY_ECO_TEST",
        "project_status": "GLOBAL_READY",
        "source": {
            "normalized_text": source_text,
            "source_sha256": sha256_text(source_text),
            "source_complete": True,
        },
        "authorizations": [],
        "source_atoms": atoms,
        "project_rules": [{"rule_id": "RULE001", "text": "保持来源忠实", "semantic_tags": ["CONTROL:FAITHFUL"]}],
        "continuity_bible": {"identity": "冻结", "world": "冻结"},
        "visual_continuity_domains": [{"domain_id": "VCD001", "description": "统一视觉域"}],
        "units": units,
        "batch_plan": {
            "requested_mode": "FULL_PROJECT",
            "normalized_mode": "FULL_EXPORT",
            "batches": [],
        },
        "checkpoints": [],
        "latest_checkpoint_id": None,
        "latest_checkpoint_sha256": None,
        "production_validation": "NOT_TESTED",
        "production_evidence": {},
        "status_contract": {
            "text_end_state": "GLOBAL_READY",
            "spec_status": "GLOBAL_READY",
            **LEGACY_TEXT_STATUS_AXES,
        },
        "output_contract": {
            "workspace_memory_policy": "DO_NOT_WRITE",
            "strict_output_set": True,
            "exact_relative_output_names": [
                "RUN0_长篇文字测试包.md",
                "RUN0_MACHINE_STATE.json",
                "RUN0_RUN_SUMMARY.md",
            ],
            "temp_root": ".alpha7-tmp-RUN1",
            "temp_input_names": ["TARGET_PLAN.json", "AUTHORING.json", "OVERLAYS.json"],
            "temp_root_cleaned": True,
        },
        "continuation_authorization": {
            "scope": "TEXT_ONLY_TO_RUN_SUMMARY",
            "external_actions": False,
            "creative_defaults": "PROPOSED_ONLY",
            "stop_conditions": list(TEXT_STOP_CONDITIONS),
        },
    }
    data["global_state"] = expected_global_state(data)
    data["global_state_sha256"] = sha256_value(data["global_state"])
    unit_ids = [unit["unit_id"] for unit in units]
    data["skeleton_sha256"] = expected_skeleton_sha256(data, unit_ids)

    data["run_summary"] = build_fixture_run_summary(data)
    return data


def fixture_prompt_artifact(unit_id: str, layer: str, text: str, serial: int) -> dict[str, Any]:
    return {
        "artifact_id": f"{layer}-{serial:03d}",
        "unit_id": unit_id,
        "layer": layer,
        "text": text,
        "sha256": sha256_text(text),
    }


def compile_fixture_unit(data: dict[str, Any], index: int, compile_status: str = "ACCEPTED") -> None:
    unit = data["units"][index]
    serial = index + 1
    unit_id = unit["unit_id"]
    atom_id = unit["source_refs"][0]
    clause = "不得无因改变人物、场景或道具状态。"
    verbatim_dialogue = f"第{serial:02d}段内容。"
    master_text = f"忠实呈现对白「{verbatim_dialogue}」，以清楚动作、空间关系和连续状态推进。"
    draft_text = f"呈现对白「{verbatim_dialogue}」；保持人物、场景与道具连续。"
    prompt_bundle = {
        "master_prompt": fixture_prompt_artifact(unit_id, "MP", master_text, serial),
        "draft_prompt": fixture_prompt_artifact(unit_id, "DRAFT", draft_text, serial),
    }
    prompt_hashes = {
        "master_prompt": prompt_bundle["master_prompt"]["sha256"],
        "draft_prompt": prompt_bundle["draft_prompt"]["sha256"],
    }
    next_unit = data["units"][index + 1]["unit_id"] if index + 1 < len(data["units"]) else None
    unit.update(
        {
            "compile_status": compile_status,
            "global_state_sha256": data["global_state_sha256"],
            "capability_routing": {"PRIMARY": ["BASE_NARRATIVE"], "SUPPORT": [], "SUPPRESS": []},
            "prompt_claims": [
                {"claim_id": f"CL{serial:03d}", "text": f"呈现第{serial:02d}段内容。", "trace_id": f"TR{serial:03d}"}
            ],
            "prompt_source_trace": [
                {
                    "trace_id": f"TR{serial:03d}",
                    "relation": "FAITHFUL_PARAPHRASE",
                    "source_refs": [atom_id],
                    "state_refs": [],
                    "project_rule_refs": [],
                    "capability_ids": ["BASE_NARRATIVE"],
                }
            ],
            "negative_clause_plan": {
                "candidate_clauses": [
                    {
                        "clause_id": f"NEG{serial:03d}",
                        "text": clause,
                        "risk_refs": [f"RISK{serial:03d}"],
                        "origin": "CONTINUITY",
                        "text_sha256": sha256_text(clause),
                    }
                ],
                "selected_clause_ids": [f"NEG{serial:03d}"],
            },
            "negative_clauses": [clause],
            "prompt_bundle": prompt_bundle,
            "content_self_review": {
                "status": "PASS",
                "scene_title": f"测试场景{serial:02d}",
                "checks": {
                    "scene_title_is_specific": True,
                    "prompt_working_draft_present": True,
                    "facts_proposals_separated": True,
                    "shots_have_dramatic_beats": True,
                    "sound_is_unambiguous": True,
                },
                "findings": [],
            },
            "director_contract": {
                "target_mode": "EDITED_SEQUENCE",
                "entry": "承接上一段的稳定人物与空间状态。",
                "action_state_chain": ["角色进入可见位置", "角色完成当前事件", "状态稳定后退出"],
                "performance": "表演服从当前来源事实，不把推测升级成事实。",
                "camera": "摄影清楚交代主体、动作与空间关系。",
                "sound": "保留来源对白并区分对白、环境声与待定后期声音。",
                "exit": "以当前事件完成后的可见状态结束。",
                "continuity": "出口状态只交接给紧邻下一 Unit。",
                "dialogue_inventory": [
                    {
                        "dialogue_id": f"DLG{serial:03d}",
                        "speaker": "测试角色",
                        "text": verbatim_dialogue,
                        "kind": "VERBATIM_DIALOGUE",
                        "source_refs": [atom_id],
                    }
                ],
                "proposed_director_inferences": [],
            },
            "provider_binding_status": "PROVIDER_PENDING",
            "provider_registry_id": None,
            "prompt_quality_records": [
                {
                    "id": f"PQ-{serial:03d}",
                    "unit_id": unit_id,
                    "lifecycle_status": "CURRENT",
                    "quality_status": {"status": "PASS", "findings": []},
                    "prompt_sha256s": prompt_hashes,
                }
            ],
            "unit_handoff_out": {
                "scope": "UNIT_TO_UNIT",
                "from_unit_id": unit_id,
                "to_unit_id": next_unit,
                "state_out_sha256": sha256_value({"unit_id": unit_id, "state": "accepted"}),
                "entry_facts_for_next_unit": ([] if next_unit is None else ["保持上一段结束状态"]),
                "open_actions": [],
                "dialogue_audio_carry": [],
            },
        }
    )
    unit["unit_compile_sha256"] = sha256_value(
        expected_unit_compile_state(unit, data["global_state_sha256"])
    )


def fixture_prompt_chars(unit: dict[str, Any]) -> int:
    bundle = unit.get("prompt_bundle") if isinstance(unit.get("prompt_bundle"), dict) else {}
    return sum(
        len(normalize_text(artifact.get("text", "")))
        for artifact in bundle.values()
        if isinstance(artifact, dict) and isinstance(artifact.get("text"), str)
    )


def set_fixture_pilot(data: dict[str, Any], sample_unit_ids: list[str]) -> None:
    unit_map = {unit["unit_id"]: unit for unit in data["units"]}
    data["prompt_pilot"] = {
        "sample_unit_ids": sample_unit_ids,
        "prompt_quality_record_ids": [unit_map[unit_id]["prompt_quality_records"][0]["id"] for unit_id in sample_unit_ids],
        "status": "PASS",
        "selection_basis": "覆盖开端、中段与结尾的身份、动作和连续性风险",
        "spread_policy": {"claim": "EARLY_MIDDLE_LATE"},
    }


def fixture_snapshot() -> dict[str, Any]:
    return {
        "identity_versions": {},
        "wardrobe_versions": {},
        "spatial_state": {},
        "injuries_and_surface_state": {},
        "prop_ownership": {},
        "motion_vectors": {},
        "camera_state": {},
        "environment_state": {},
        "open_actions": [],
        "observed_state_authority": "PLANNED_STATE",
    }


def build_fixture_checkpoint(
    data: dict[str, Any], batch: dict[str, Any], index: int, previous_hash: str
) -> dict[str, Any]:
    unit_map = {unit["unit_id"]: unit for unit in data["units"]}
    batch_units = batch["unit_ids"]
    last_index = [unit["unit_id"] for unit in data["units"]].index(batch_units[-1])
    next_unit = data["units"][last_index + 1]["unit_id"] if last_index + 1 < len(data["units"]) else None
    next_checkpoint = data["batch_plan"]["batches"][index + 1]["batch_id"] if index + 1 < len(data["batch_plan"]["batches"]) else None
    checkpoint: dict[str, Any] = {
        "checkpoint_id": batch["batch_id"],
        "status": "COMMITTED",
        "source_sha256": data["source"]["source_sha256"],
        "skeleton_sha256": data["skeleton_sha256"],
        "global_state_sha256": data["global_state_sha256"],
        "previous_checkpoint_sha256": previous_hash,
        "batch_units": batch_units,
        "accepted_units": batch_units,
        "prompt_quality_record_ids": [unit_map[unit_id]["prompt_quality_records"][0]["id"] for unit_id in batch_units],
        "unit_compile_sha256s": {unit_id: unit_map[unit_id]["unit_compile_sha256"] for unit_id in batch_units},
        "next_unit_id": next_unit,
        "continuity_snapshot": fixture_snapshot(),
        "unresolved_exceptions": [],
        "batch_handoff": {
            "scope": "BATCH_TO_BATCH",
            "from_checkpoint_id": batch["batch_id"],
            "next_checkpoint_id": next_checkpoint,
            "last_accepted_unit_id": batch_units[-1],
            "next_unit_id": next_unit,
            "boundary_after": batch_units[-1],
        },
    }
    checkpoint["sha256"] = sha256_value(checkpoint)
    return checkpoint


def build_fixture_run_summary(data: dict[str, Any]) -> dict[str, Any]:
    unit_ids = [unit["unit_id"] for unit in data["units"]]
    compiled_ids = [unit["unit_id"] for unit in data["units"] if unit.get("compile_status") in {"ACCEPTED", "COMMITTED"}]
    pilot = data.get("prompt_pilot") if isinstance(data.get("prompt_pilot"), dict) else {}
    samples = pilot.get("sample_unit_ids", [])
    quality_ids = pilot.get("prompt_quality_record_ids", [])
    checkpoint_units = [
        unit_id for checkpoint in data.get("checkpoints", []) if isinstance(checkpoint, dict) for unit_id in checkpoint.get("accepted_units", [])
    ]
    status = data["project_status"]
    remaining = [unit_id for unit_id in unit_ids if unit_id not in checkpoint_units]
    next_unit = None if status in {"TEXT_PILOT_COMPLETE", "TEXT_SPEC_COMPLETE"} else (remaining[0] if remaining else None)
    compile_target_ids = [atom["atom_id"] for atom in data["source_atoms"] if atom.get("compile_target") is True]
    unit_map = {unit["unit_id"]: unit for unit in data["units"]}
    return {
        "source_sha256": data["source"]["source_sha256"],
        "source_scope_unit_ids": unit_ids,
        "compile_target_atom_ids": compile_target_ids,
        "compile_target_atom_count": len(compile_target_ids),
        "compile_target_atom_ids_sha256": sha256_value(compile_target_ids),
        "selected_source_ranges": [
            {
                "unit_id": unit_id,
                "first_atom_id": unit_map[unit_id].get("source_window", {}).get("first_atom_id"),
                "last_atom_id": unit_map[unit_id].get("source_window", {}).get("last_atom_id"),
                "text_sha256": unit_map[unit_id].get("source_window", {}).get("text_sha256"),
            }
            for unit_id in samples
            if unit_id in unit_map
        ],
        "completed_unit_ids": compiled_ids,
        "prompt_pilot": {
            "sample_unit_ids": samples,
            "prompt_quality_record_ids": quality_ids,
            "status": "PASS" if samples else "NOT_RUN",
        },
        "skipped_stages": list(TEXT_SKIPPED_STAGES),
        "execution_status": "NOT_EXECUTED",
        "observation_status": "NOT_EXECUTED",
        "media_qa_status": "QA_NOT_EXECUTED",
        "production_validation": "NOT_TESTED",
        "open_items": [],
        "resume_entry": {
            "entrypoint": {
                "GLOBAL_READY": "PROMPT_PILOT",
                "TEXT_PILOT_COMPLETE": "EDITORIAL_REVIEW",
                "TEXT_SPEC_COMPLETE": "TEXT_SPEC_COMPLETE",
            }[status],
            "next_unit_id": next_unit,
            "latest_checkpoint_id": data.get("latest_checkpoint_id"),
        },
    }


def build_pilot_fixture() -> dict[str, Any]:
    data = build_phase_a_fixture()
    samples = ["U001", "U008", "U015"]
    for index in (0, 7, 14):
        compile_fixture_unit(data, index, "ACCEPTED")
    data["project_status"] = "TEXT_PILOT_COMPLETE"
    data["status_contract"] = {
        "text_end_state": "TEXT_PILOT_COMPLETE",
        "spec_status": "TEXT_PILOT_COMPLETE",
        **LEGACY_TEXT_STATUS_AXES,
    }
    set_fixture_pilot(data, samples)
    data["run_summary"] = build_fixture_run_summary(data)
    return data


def build_self_test_fixture() -> dict[str, Any]:
    data = build_phase_a_fixture()
    for index in range(len(data["units"])):
        compile_fixture_unit(data, index, "COMMITTED")
    data["project_status"] = "TEXT_SPEC_COMPLETE"
    data["status_contract"] = {
        "text_end_state": "TEXT_SPEC_COMPLETE",
        "spec_status": "TEXT_SPEC_COMPLETE",
        **LEGACY_TEXT_STATUS_AXES,
    }
    set_fixture_pilot(data, ["U001", "U008", "U015"])
    batches = [
        {
            "batch_id": "B001",
            "unit_ids": [f"U{index:03d}" for index in range(1, 9)],
            "is_final": False,
            "actual_prompt_chars": None,
            "batch_budget_exception": {"code": "LOW_DENSITY_UNITS", "reason": "内置短文本回归夹具"},
        },
        {
            "batch_id": "B002",
            "unit_ids": [f"U{index:03d}" for index in range(9, 16)],
            "is_final": True,
            "actual_prompt_chars": None,
        },
    ]
    data["batch_plan"]["batches"] = batches
    previous_hash = data["skeleton_sha256"]
    checkpoints: list[dict[str, Any]] = []
    for index, batch in enumerate(batches):
        batch["actual_prompt_chars"] = sum(
            fixture_prompt_chars(data["units"][int(unit_id[1:]) - 1]) for unit_id in batch["unit_ids"]
        )
        checkpoint = build_fixture_checkpoint(data, batch, index, previous_hash)
        checkpoints.append(checkpoint)
        previous_hash = checkpoint["sha256"]
    data["checkpoints"] = checkpoints
    data["latest_checkpoint_id"] = checkpoints[-1]["checkpoint_id"]
    data["latest_checkpoint_sha256"] = checkpoints[-1]["sha256"]
    data["run_summary"] = build_fixture_run_summary(data)
    return data


def refresh_fixture_product_hashes(data: dict[str, Any]) -> None:
    for unit in data["units"]:
        if unit.get("compile_status") not in {"ACCEPTED", "COMMITTED"}:
            continue
        unit["unit_compile_sha256"] = sha256_value(
            expected_unit_compile_state(unit, data.get("global_state_sha256"))
        )
    unit_map = {unit["unit_id"]: unit for unit in data["units"]}
    checkpoint_ids = {
        checkpoint.get("checkpoint_id") for checkpoint in data.get("checkpoints", []) if isinstance(checkpoint, dict)
    }
    for batch in data.get("batch_plan", {}).get("batches", []):
        if batch.get("batch_id") in checkpoint_ids:
            batch["actual_prompt_chars"] = sum(fixture_prompt_chars(unit_map[unit_id]) for unit_id in batch["unit_ids"])
    previous_hash = data["skeleton_sha256"]
    for checkpoint in data.get("checkpoints", []):
        accepted = checkpoint.get("accepted_units", [])
        checkpoint["prompt_quality_record_ids"] = [
            (unit_map[unit_id].get("prompt_quality_records") or [{}])[0].get("id") for unit_id in accepted
        ]
        checkpoint["unit_compile_sha256s"] = {
            unit_id: unit_map[unit_id].get("unit_compile_sha256") for unit_id in accepted
        }
        checkpoint["previous_checkpoint_sha256"] = previous_hash
        checkpoint["sha256"] = sha256_value({key: value for key, value in checkpoint.items() if key != "sha256"})
        previous_hash = checkpoint["sha256"]
    if data.get("checkpoints"):
        data["latest_checkpoint_sha256"] = data["checkpoints"][-1]["sha256"]


def run_self_test() -> dict[str, Any]:
    sentence_fixture = "值夜员说：“第一句。第二句！”。\n！？；\n尾句无标点\n"
    sentence_spans = semantic_sentence_spans(sentence_fixture, base_cp=17)
    if [item["exact_text"] for item in sentence_spans] != [
        "值夜员说：“第一句。第二句！”。",
        "尾句无标点",
    ] or any(
        normalize_text(sentence_fixture)[
            item["start_cp"] - 17 : item["end_cp"] - 17
        ]
        != item["exact_text"]
        for item in sentence_spans
    ):
        raise AssertionError("canonical semantic sentence spans lost quote/cp fidelity")
    if not all(
        source_anchor_is_complete(item["exact_text"], sentence_fixture)
        for item in sentence_spans
    ):
        raise AssertionError("canonical sentences are not accepted as complete anchors")
    if source_anchor_is_complete("！？；", sentence_fixture) or any(
        not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", item["exact_text"])
        for item in sentence_spans
    ):
        raise AssertionError("punctuation-only source anchor was accepted")
    route_fixture = expected_route_findings(
        {"route_risk": "MULTI_ACTION_REACTION_SPLIT_REQUIRED"},
        {"eligible": False},
    )
    if route_fixture != [
        "SPLIT_REQUIRED:MULTI_ACTION_REACTION_SPLIT_REQUIRED",
        "SPLIT_REQUIRED:SINGLE_SHOT_INELIGIBLE",
    ]:
        raise AssertionError("canonical route finding order drifted")
    time_anchor_fixture = [
        {"anchor_id": f"SA-U001-{index:03d}", "anchor_role": role}
        for index, role in enumerate(
            ["ACTION_BEAT", "TIME_TRANSITION", "TIME_TRANSITION", "ACTION_BEAT"],
            start=1,
        )
    ]
    time_groups = expected_sequence_anchor_groups(time_anchor_fixture, 2)
    if [item[0]["anchor_id"] for item in time_groups] != [
        "SA-U001-001",
        "SA-U001-002",
        "SA-U001-003",
    ] or [item["anchor_id"] for group in time_groups for item in group] != [
        item["anchor_id"] for item in time_anchor_fixture
    ]:
        raise AssertionError("mandatory time-transition cuts were truncated or reordered")
    dense_anchor_fixture = [
        {
            "anchor_id": f"SA-U002-{index:03d}",
            "anchor_role": "TIME_TRANSITION" if index in {5, 9} else "ACTION_BEAT",
        }
        for index in range(1, 12)
    ]
    dense_groups = expected_sequence_anchor_groups(dense_anchor_fixture, 7)
    if (
        len(dense_groups) < 7
        or any(not 1 <= len(group) <= 3 for group in dense_groups)
        or [item for group in dense_groups for item in group] != dense_anchor_fixture
        or not {"SA-U002-005", "SA-U002-009"}.issubset(
            {group[0]["anchor_id"] for group in dense_groups}
        )
    ):
        raise AssertionError("dense sequence grouping violated time cuts, density, or order")
    try:
        expected_sequence_anchor_groups(dense_anchor_fixture[:3], 4)
    except ValueError as exc:
        if "E_SEQUENCE_SOURCE_WINDOW_THIN" not in str(exc):
            raise
    else:
        raise AssertionError("sequence with fewer anchors than minimum shots did not fail closed")
    try:
        expected_sequence_anchor_groups(time_anchor_fixture[:1], 2)
    except ValueError as exc:
        if "E_SEQUENCE_SOURCE_WINDOW_THIN" not in str(exc):
            raise
    else:
        raise AssertionError("single-anchor Sequence did not fail closed")

    negative_voice_directions = [
        "不要旁白。",
        "当前段落不得增加任何画外音。",
        "禁止设置内心独白，只保留环境声。",
        "避免使用旁白。",
        "不设画外音；不使用内心独白。",
        "无新增旁白，不增加额外画外音。",
    ]
    affirmative_voice_directions = [
        "新增旁白交代时间。",
        "加入画外音解释背景。",
        "不要音乐而新增旁白。",
        "环境声之外使用内心独白。",
    ]
    if any(has_affirmative_unsourced_voice(text) for text in negative_voice_directions):
        raise AssertionError("negative same-clause voice direction was treated as an addition")
    if not all(has_affirmative_unsourced_voice(text) for text in affirmative_voice_directions):
        raise AssertionError("affirmative unsourced voice addition escaped detection")

    temp_dir = tempfile.TemporaryDirectory(prefix="alpha7-longform-r4-")
    test_base = Path(temp_dir.name)
    machine_name = "RUN0_MACHINE_STATE.json"
    for name in (
        "RUN0_长篇文字测试包.md",
        machine_name,
        "RUN0_RUN_SUMMARY.md",
    ):
        (test_base / name).write_text("self-test fixture\n", encoding="utf-8")
    media_fixture = build_self_test_fixture()
    media_fixture["delivery_mode"] = "MEDIA_ENABLED"
    media_fixture["project_status"] = "COMPLETE"
    media_fixture.pop("continuation_authorization", None)
    media_fixture.pop("run_summary", None)
    media_fixture.pop("status_contract", None)
    media_fixture.pop("output_contract", None)
    positives = {
        "global_ready_zero_prompt_shells": build_phase_a_fixture(),
        "text_pilot_noncontiguous_three_zero_media": build_pilot_fixture(),
        "text_spec_complete": build_self_test_fixture(),
        "media_complete_legacy_status": media_fixture,
    }
    positive_results: list[dict[str, Any]] = []
    for name, fixture in positives.items():
        report = validate_contract(
            fixture,
            test_base,
            machine_name if fixture.get("delivery_mode") == "TEXT_ONLY_ECO_TEST" else None,
        )
        if not report.valid:
            raise AssertionError(f"positive {name} failed: {report.as_dict()}")
        positive_results.append({"name": name, "valid": True})
    direct_path = test_base / machine_name
    direct_path.write_text(
        json.dumps(positives["text_pilot_noncontiguous_three_zero_media"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    direct_report = validate_contract(read_contract(direct_path), test_base, direct_path.name)
    if not direct_report.valid:
        raise AssertionError(f"direct artifact positive failed: {direct_report.as_dict()}")
    positive_results.append({"name": "text_pilot_direct_artifact_roundtrip", "valid": True})
    phase_a = positives["global_ready_zero_prompt_shells"]
    if any(PROMPT_SHELL_KEYS.intersection(unit) for unit in phase_a["units"]):
        raise AssertionError("GLOBAL_READY fixture unexpectedly contains Prompt shells")
    pilot_fixture = positives["text_pilot_noncontiguous_three_zero_media"]
    if pilot_fixture["checkpoints"] or pilot_fixture["batch_plan"]["batches"]:
        raise AssertionError("TEXT_PILOT_COMPLETE fixture must have zero continuous batches/checkpoints")

    fixture = positives["text_spec_complete"]
    attacks: list[tuple[str, str, Any]] = []

    def attack(name: str, expected_code: str, mutate, base: dict[str, Any] | None = None, refresh: bool = False) -> None:
        candidate = copy.deepcopy(base if base is not None else fixture)
        mutate(candidate)
        if refresh:
            refresh_fixture_product_hashes(candidate)
        report = validate_contract(
            candidate,
            test_base,
            machine_name if candidate.get("delivery_mode") == "TEXT_ONLY_ECO_TEST" else None,
        )
        codes = {item["code"] for item in report.errors}
        if report.valid or expected_code not in codes:
            raise AssertionError(f"{name} did not fail with {expected_code}: {sorted(codes)}")
        attacks.append((name, expected_code, sorted(codes)))

    def strip_all_products(item: dict[str, Any]) -> None:
        for unit in item["units"]:
            for key in set(PROMPT_SHELL_KEYS).union({"compile_status"}):
                unit.pop(key, None)

    attack("p0_complete_with_source_refs_only", "E_ACCEPTED_UNIT_INCOMPLETE", strip_all_products)

    def custom_schema_not_canonical(item: dict[str, Any]) -> None:
        item.pop("contract_version", None)
        item["schema"] = "silver-showrunner/text-eco-machine-state/v1"

    attack(
        "run1_custom_schema_not_canonical",
        "E_CONTRACT_VERSION",
        custom_schema_not_canonical,
        base=pilot_fixture,
    )

    def terminal_with_not_run_quality(item: dict[str, Any]) -> None:
        for unit_id in item["prompt_pilot"]["sample_unit_ids"]:
            unit = next(unit for unit in item["units"] if unit["unit_id"] == unit_id)
            unit["prompt_quality_records"][0]["quality_status"] = {"status": "NOT_RUN", "findings": []}

    attack(
        "run1_not_run_quality_claims_terminal",
        "E_PROMPT_QUALITY_NOT_READY",
        terminal_with_not_run_quality,
        base=pilot_fixture,
        refresh=True,
    )

    def false_noncontiguous_claim(item: dict[str, Any]) -> None:
        samples = ["U004", "U005", "U006"]
        unit_map = {unit["unit_id"]: unit for unit in item["units"]}
        item["prompt_pilot"]["sample_unit_ids"] = samples
        item["prompt_pilot"]["prompt_quality_record_ids"] = [
            unit_map[unit_id]["prompt_quality_records"][0]["id"] for unit_id in samples
        ]
        item["prompt_pilot"]["spread_policy"] = {"claim": "NONCONTIGUOUS"}

    attack(
        "run1_consecutive_samples_claim_noncontiguous",
        "E_PILOT_SPREAD",
        false_noncontiguous_claim,
    )

    def compressed_dialogue_claimed_verbatim(item: dict[str, Any]) -> None:
        unit = item["units"][0]
        unit["director_contract"]["dialogue_inventory"][0]["text"] = "第01段。"

    attack(
        "run1_compressed_dialogue_claimed_verbatim",
        "E_DIALOGUE_VERBATIM_SOURCE",
        compressed_dialogue_claimed_verbatim,
        base=pilot_fixture,
        refresh=True,
    )

    def narration_as_unmarked_dialogue(item: dict[str, Any]) -> None:
        unit = item["units"][0]
        unit["director_contract"]["dialogue_inventory"].append(
            {
                "dialogue_id": "DLG-NARRATION",
                "speaker": "画外音",
                "text": "把来源叙述直接说出来。",
                "kind": "NARRATION_AS_PROPOSED_VOICE_OVER",
                "source_refs": list(unit["source_refs"]),
            }
        )

    attack(
        "run1_narration_to_voice_over_without_proposed_mark",
        "E_DIALOGUE_PROPOSED_INFERENCE",
        narration_as_unmarked_dialogue,
        base=pilot_fixture,
        refresh=True,
    )

    attack(
        "run1_terminal_spec_status_conflict",
        "E_TEXT_STATUS_CONSISTENCY",
        lambda item: item["status_contract"].__setitem__("spec_status", "TEXT_SPEC_COMPLETE"),
        base=pilot_fixture,
    )

    def empty_trace(item: dict[str, Any]) -> None:
        for unit in item["units"]:
            unit["prompt_claims"] = []
            unit["prompt_source_trace"] = []

    attack("p0_empty_claims_and_trace", "E_TEXT_SPEC_SOURCE_PRODUCT_COVERAGE", empty_trace, refresh=True)

    def empty_negative(item: dict[str, Any]) -> None:
        unit = item["units"][0]
        unit["negative_clause_plan"] = {"candidate_clauses": [], "selected_clause_ids": []}
        unit["negative_clauses"] = []

    attack("p0_empty_negative_inventory", "E_NEGATIVE_CLAUSE_EMPTY", empty_negative, refresh=True)

    def empty_prompt(item: dict[str, Any]) -> None:
        artifact = item["units"][0]["prompt_bundle"]["master_prompt"]
        artifact["text"] = ""
        artifact["sha256"] = sha256_text("")
        item["units"][0]["prompt_quality_records"][0]["prompt_sha256s"]["master_prompt"] = artifact["sha256"]

    attack("p0_empty_prompt_body", "E_PROMPT_BUNDLE_EMPTY", empty_prompt, refresh=True)

    def empty_quality(item: dict[str, Any]) -> None:
        item["units"][0]["prompt_quality_records"] = []

    attack("p0_empty_quality_and_checkpoint_ids", "E_PROMPT_QUALITY_CARDINALITY", empty_quality, refresh=True)

    def checkpoint_quality_mismatch(item: dict[str, Any]) -> None:
        item["checkpoints"][0]["prompt_quality_record_ids"] = item["checkpoints"][0]["prompt_quality_record_ids"][1:]
        item["checkpoints"][0]["sha256"] = sha256_value(
            {key: value for key, value in item["checkpoints"][0].items() if key != "sha256"}
        )

    attack("p0_checkpoint_quality_not_exact", "E_CHECKPOINT_QUALITY_IDS", checkpoint_quality_mismatch)

    def fake_pp_pending(item: dict[str, Any]) -> None:
        unit = item["units"][0]
        unit["prompt_bundle"]["provider_prompt"] = fixture_prompt_artifact(
            unit["unit_id"], "PP", "保持同一事件与连续状态。", 1
        )

    attack("fake_pp_while_provider_pending", "E_PROVIDER_BINDING", fake_pp_pending, refresh=True)

    def bound_without_pp(item: dict[str, Any]) -> None:
        unit = item["units"][0]
        unit["provider_binding_status"] = "PROVIDER_BOUND"
        unit["provider_registry_id"] = "PROVIDER-TEST"

    attack("provider_bound_without_pp", "E_PROMPT_BUNDLE_EMPTY", bound_without_pp, refresh=True)
    attack(
        "missing_continuation_authorization",
        "E_CONTINUATION_AUTHORIZATION",
        lambda item: item.pop("continuation_authorization"),
        base=pilot_fixture,
    )
    attack("missing_run_summary", "E_RUN_SUMMARY", lambda item: item.pop("run_summary"), base=pilot_fixture)
    attack(
        "run_summary_media_exclusion_tamper",
        "E_RUN_SUMMARY",
        lambda item: item["run_summary"].__setitem__("skipped_stages", ["IMAGE", "VIDEO"]),
        base=pilot_fixture,
    )
    attack(
        "run_summary_resume_cursor_tamper",
        "E_RUN_SUMMARY",
        lambda item: item["run_summary"]["resume_entry"].__setitem__("next_unit_id", "U008"),
        base=pilot_fixture,
    )
    attack(
        "pilot_coupled_to_first_batch",
        "E_PILOT_BATCH_COUPLING",
        lambda item: item["prompt_pilot"].__setitem__("batch_id", "B001"),
    )
    attack(
        "committed_prompt_chars_not_recomputed",
        "E_BATCH_CHAR_RECOMPUTE",
        lambda item: item["batch_plan"]["batches"][0].__setitem__("actual_prompt_chars", 1),
    )

    def precommit_chars(item: dict[str, Any]) -> None:
        item["batch_plan"]["batches"] = [
            {
                "batch_id": "B001",
                "unit_ids": [f"U{index:03d}" for index in range(1, 16)],
                "is_final": True,
                "actual_prompt_chars": 123,
                "batch_budget_exception": {"code": "CAPACITY_LIMIT", "reason": "测试"},
            }
        ]

    attack("precommit_prompt_chars_must_be_null", "E_BATCH_CHAR_PRECOMMIT", precommit_chars, base=pilot_fixture)
    attack(
        "legacy_mode_alias_mismatch",
        "E_MODE_NORMALIZATION",
        lambda item: item["batch_plan"].__setitem__("normalized_mode", "ONEFILE_SAFE_BATCH"),
    )
    attack(
        "production_claim_without_media_evidence",
        "E_PRODUCTION_EVIDENCE_BOUNDARY",
        lambda item: item.__setitem__("production_validation", "VALIDATED"),
    )

    extra_path = test_base / "unexpected-memory.md"
    extra_path.write_text("forbidden extra output\n", encoding="utf-8")
    extra_report = validate_contract(pilot_fixture, test_base, machine_name)
    extra_codes = {item["code"] for item in extra_report.errors}
    extra_path.unlink()
    if extra_report.valid or "E_OUTPUT_SET" not in extra_codes:
        raise AssertionError(f"run1_extra_output_file did not fail with E_OUTPUT_SET: {sorted(extra_codes)}")
    attacks.append(("run1_extra_output_file", "E_OUTPUT_SET", sorted(extra_codes)))

    result = {
        "contract_version": CONTRACT_VERSION,
        "self_test": "PASS",
        "positive_count": len(positive_results),
        "positives": positive_results,
        "attack_count": len(attacks),
        "attacks": [
            {"name": name, "expected_code": code, "actual_codes": actual}
            for name, code, actual in attacks
        ],
        "production_validation": "NOT_TESTED",
    }
    temp_dir.cleanup()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="验证银幕总控 Alpha.7 长内容编译与恢复合同")
    parser.add_argument("contract", nargs="?", type=Path, help="longform contract JSON")
    parser.add_argument("--self-test", action="store_true", help="运行内置正例与攻击负例")
    args = parser.parse_args()

    if args.self_test:
        try:
            result = run_self_test()
        except Exception as exc:  # fail closed for the executable self-test boundary
            print(json.dumps({"self_test": "FAIL", "error": str(exc)}, ensure_ascii=False, sort_keys=True))
            return 1
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    if args.contract is None:
        parser.error("请提供 contract JSON，或使用 --self-test")
    path = args.contract.resolve()
    try:
        data = read_contract(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "contract_version": CONTRACT_VERSION,
                    "valid": False,
                    "error_codes": ["E_INPUT_READ"],
                    "errors": [{"code": "E_INPUT_READ", "path": str(path), "message": str(exc)}],
                    "production_validation": "NOT_TESTED",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    report = validate_contract(data, path.parent, path.name)
    print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
