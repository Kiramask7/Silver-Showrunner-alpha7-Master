#!/usr/bin/env python3
"""Fail closed on visibly impossible performance directions.

This guard is deliberately small and conservative. It does not try to judge
artistic quality in general. It rejects production-breaking shortcuts that a
structural validator cannot see, and verifies that public per-shot copy has an
explicit endpoint.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


COPY_SHOT_RE = re.compile(
    r"(?ms)^####\s*镜头\s*[^\n]+\n.*?(?=^####\s*镜头\s*|\Z)"
)
HIDDEN_MOUTH_FIX_RE = re.compile(
    r"(?:现实|本人|角色|主体)?(?:的)?(?:嘴部|嘴巴|口型)"
    r"[^。；;\n]{0,16}(?:不展示|不拍|不做特写|避开|藏住|遮住|看不见)"
    r"|不强行展示[^。；;\n]{0,12}(?:嘴部|口型)"
)
REALITY_VOICE_RE = re.compile(
    r"(?:声音|对白|这句话)[^。；;\n]{0,18}(?:来自|源自)(?:现实|真实)"
    r"[^。；;\n]{0,12}(?:角色|人物|身体|小破)?"
)
FANTASY_SPEECH_RE = re.compile(
    r"(?:幻想|梦境|想象)[^。；;\n]{0,36}(?:张嘴|开口|说|宣言|对白)"
)
MOUTH_OCCUPIED_RE = re.compile(
    r"(?:嘴里|口中|嘴巴|嘴角)[^。；;\n]{0,18}(?:叼|含|咬|塞|衔)"
    r"|(?:叼|含|咬住|衔住)[^。；;\n]{0,18}(?:嘴里|口中|嘴巴|嘴角|鱼干|食物|物件)"
)
VISIBLE_RELEASE_RE = re.compile(
    r"(?:先|随即|随后|接着|开口前)?[^。；;\n]{0,12}"
    r"(?:吐出|松口|从(?:嘴里|口中|嘴巴|嘴角)(?:拿出|取出|移开|移到)|"
    r"用(?:前爪|爪子|手)接住|转移到(?:前爪|爪子|手中)|"
    r"放到(?:前爪|爪子|手中|桌上|一旁))"
)
SPEECH_RE = re.compile(
    r"(?:对白|逐字说|开口说|张嘴说|清楚说|发声|朗读|宣言|口型同步)"
)
GENERIC_SOUND_RE = re.compile(
    r"只保留(?:与动作同步的)?接触声、衣料声和环境底噪"
    r"|接触声、衣料声和环境底噪"
)


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    evidence: str


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _evidence(text: str, match: re.Match[str], radius: int = 34) -> str:
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _line_value(section: str, label: str) -> str:
    match = re.search(rf"(?m)^{re.escape(label)}[：:]\s*(.+)$", section)
    return match.group(1).strip() if match else ""


def _mouth_speech_conflict(clause: str, speakers: list[str]) -> str | None:
    occupied = MOUTH_OCCUPIED_RE.search(clause)
    spoken = SPEECH_RE.search(clause)
    if not occupied or not spoken:
        return None
    if speakers:
        occupied_prefix = clause[max(0, occupied.start() - 36) : occupied.end()]
        speech_prefix = clause[max(0, spoken.start() - 36) : spoken.end()]
        occupied_people = [
            (occupied_prefix.rfind(item), item)
            for item in speakers
            if item in occupied_prefix
        ]
        speaking_people = [
            (speech_prefix.rfind(item), item)
            for item in speakers
            if item in speech_prefix
        ]
        occupied_person = max(occupied_people)[1] if occupied_people else None
        speaking_person = max(speaking_people)[1] if speaking_people else None
        if occupied_person and speaking_person and occupied_person != speaking_person:
            return None
    if occupied.start() > spoken.start():
        # Re-biting or re-taking the prop after speech is a valid visible
        # endpoint, not a pre-speech obstruction.
        return None
    release = VISIBLE_RELEASE_RE.search(clause)
    if release and release.start() < spoken.start():
        return None
    return re.sub(r"\s+", " ", clause).strip()[:160]


def analyze_prompt(
    text: str,
    *,
    has_spoken_dialogue: bool,
    spoken_speakers: list[str] | None = None,
    require_copy_endings: bool = True,
) -> list[Finding]:
    """Return reproducible findings without mutating the prompt."""

    surface = text or ""
    findings: list[Finding] = []

    if has_spoken_dialogue:
        hidden = HIDDEN_MOUTH_FIX_RE.search(surface)
        if hidden:
            findings.append(
                Finding(
                    "E_HIDDEN_PHYSICAL_CONFLICT",
                    "不能靠不展示嘴部或口型来掩盖发声与身体状态的冲突；必须改成画面可见的动作解法，或明确取得授权后改变发声方式。",
                    _evidence(surface, hidden),
                )
            )

        reality_voice = REALITY_VOICE_RE.search(surface)
        fantasy_speech = FANTASY_SPEECH_RE.search(surface)
        visible_release = VISIBLE_RELEASE_RE.search(surface)
        mouth_explicitly_free = re.search(
            r"(?:现实)?(?:嘴部|嘴巴|口中)[^。；;\n]{0,12}(?:空出|腾空|没有道具|可以发声)",
            surface,
        )
        body_ready_before_voice = any(
            match is not None and match.start() < reality_voice.start()
            for match in (visible_release, mouth_explicitly_free)
        ) if reality_voice else False
        if reality_voice and fantasy_speech and not body_ready_before_voice:
            findings.append(
                Finding(
                    "E_VOICE_SOURCE_BODY_MISMATCH",
                    "画面中的幻想主体在开口，声音却被指定来自现实身体；必须明确唯一声源，并让该身体具备可见、可执行的发声条件。",
                    _evidence(surface, reality_voice),
                )
            )

        # Same-clause conflicts are safe to reject automatically. Cross-shot
        # state is handled by the explicit concealment/source checks above and
        # by the authored physical-continuity directions.
        speakers = [item for item in spoken_speakers or [] if item]
        for clause in re.split(r"[。；;\n]", surface):
            evidence = _mouth_speech_conflict(clause, speakers)
            if evidence is None:
                continue
            findings.append(
                Finding(
                    "E_MOUTH_OCCUPIED_SPEECH",
                    "同一动作段里嘴部被道具占用却要清楚发声；对白前必须拍到道具离开嘴部并由手、爪或环境承接，不能让道具消失。",
                    evidence,
                )
            )
            break

    generic_sound = GENERIC_SOUND_RE.search(surface)
    if generic_sound:
        findings.append(
            Finding(
                "E_GENERIC_SOUND_FILLER",
                "声音说明不能用通用底噪占位；只写本镜画面中确实发生、能与动作对齐的具体声音。",
                _evidence(surface, generic_sound),
            )
        )

    if require_copy_endings and "可直接复制：" in surface:
        sections = COPY_SHOT_RE.findall(surface)
        for index, section in enumerate(sections, start=1):
            if "结束画面：" not in section:
                findings.append(
                    Finding(
                        "E_MISSING_VISIBLE_END_STATE",
                        f"镜头 {index} 缺少明确的可见结束画面，不能可靠续接或剪辑。",
                        section.splitlines()[0].strip(),
                    )
                )
            action = _compact(_line_value(section, "画面与表演"))
            camera = _compact(_line_value(section, "摄影"))
            if action and camera and (
                action == camera or (len(action) >= 24 and action in camera)
            ):
                findings.append(
                    Finding(
                        "E_ACTION_CAMERA_DUPLICATE",
                        f"镜头 {index} 的摄影说明重复画面动作，没有提供独立的机位、构图或运动信息。",
                        _line_value(section, "摄影")[:160],
                    )
                )

    unique: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for finding in findings:
        key = (finding.code, finding.evidence)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def assert_prompt_feasible(
    text: str,
    *,
    has_spoken_dialogue: bool,
    spoken_speakers: list[str] | None = None,
    require_copy_endings: bool = True,
) -> None:
    findings = analyze_prompt(
        text,
        has_spoken_dialogue=has_spoken_dialogue,
        spoken_speakers=spoken_speakers,
        require_copy_endings=require_copy_endings,
    )
    if findings:
        summary = " | ".join(f"{item.code}: {item.message}" for item in findings)
        raise ValueError(summary)


def self_test() -> None:
    bad_hidden = """#### 镜头 1｜8 秒
可直接复制：
画面与表演：幻想中的小破张嘴说完整宣言；这句声音来自现实中的小破，现实口型暂不展示。
摄影：正面中近景。
声音与口型：对白完整出现。
结束画面：宣言停在破折号处。
"""
    codes = {item.code for item in analyze_prompt(bad_hidden, has_spoken_dialogue=True)}
    expected = {"E_HIDDEN_PHYSICAL_CONFLICT", "E_VOICE_SOURCE_BODY_MISMATCH"}
    if not expected.issubset(codes):
        raise AssertionError(f"hidden reality-body conflict escaped: {sorted(codes)}")

    bad_mouth = """#### 镜头 1｜8 秒
可直接复制：
画面与表演：小兽嘴里叼着鱼干，同时张嘴说完整对白。
摄影：侧面近景。
声音与口型：逐字对白与口型同步。
结束画面：鱼干仍在嘴里。
"""
    codes = {
        item.code
        for item in analyze_prompt(
            bad_mouth,
            has_spoken_dialogue=True,
            spoken_speakers=["小兽"],
        )
    }
    if "E_MOUTH_OCCUPIED_SPEECH" not in codes:
        raise AssertionError(f"mouth occupancy escaped: {sorted(codes)}")

    different_speaker = """#### 镜头 1｜6 秒
可直接复制：
画面与表演：小破嘴角咬紧鱼干，陆珩侧过脸开口说完整对白。
摄影：侧面中景同时保留两名角色。
声音与口型：陆珩的对白与陆珩口型同步。
结束画面：陆珩闭口，小破仍叼着同一根鱼干。
"""
    if analyze_prompt(
        different_speaker,
        has_spoken_dialogue=True,
        spoken_speakers=["小破", "陆珩"],
    ):
        raise AssertionError("a prop held by a non-speaking character was falsely rejected")

    good_visible_transfer = """#### 镜头 1｜10 秒
可直接复制：
画面与表演：小兽先松口，用前爪接住鱼干，鱼干始终可见；嘴部空出后逐字说完整对白，说完再把鱼干叼回嘴里。
摄影：同高度中近景固定观察嘴部、前爪和鱼干的连续转移。
声音与口型：对白只出现一次，口型同步；爪垫接住鱼干时有一次轻响。
结束画面：小兽重新叼住同一根鱼干，前爪落回床面。
"""
    if analyze_prompt(good_visible_transfer, has_spoken_dialogue=True):
        raise AssertionError("visible prop transfer was falsely rejected")

    good_reality_to_fantasy_l_cut = """#### 镜头 1｜10 秒
可直接复制：
画面与表演：现实中的小兽先松口，用前爪接住鱼干，现实嘴部空出并开始说话；随后切入幻想王座，幻想画面承接表情，但声音始终来自已经空出嘴部的现实身体。
摄影：先拍清嘴、前爪和鱼干的转移，再用连续声桥切入幻想中景。
声音与口型：对白只有一个连续声音游标，不从头重播。
结束画面：切回现实，角色说完最后一个字，鱼干仍在前爪中。
"""
    if analyze_prompt(good_reality_to_fantasy_l_cut, has_spoken_dialogue=True):
        raise AssertionError("physically established reality-to-fantasy L-cut was rejected")

    good_authorized_voice = """#### 镜头 1｜8 秒
可直接复制：
画面与表演：原文明确的幻想画外音覆盖潮汐王座画面，现实身体不承担这句发声。
摄影：固定中景观察王座与潮水层次。
声音与口型：只使用原文明确的幻想画外音，不新增对白。
结束画面：画外音停在破折号，潮水反光仍在王座下移动。
"""
    if analyze_prompt(good_authorized_voice, has_spoken_dialogue=True):
        raise AssertionError("source-authorized fantasy voice was falsely rejected")

    missing_end = """#### 镜头 1｜5 秒
可直接复制：
画面与表演：角色抬眼。
摄影：固定近景。
声音：不新增声音。
"""
    codes = {item.code for item in analyze_prompt(missing_end, has_spoken_dialogue=False)}
    if "E_MISSING_VISIBLE_END_STATE" not in codes:
        raise AssertionError("missing visible endpoint escaped")

    generic = """#### 镜头 1｜5 秒
可直接复制：
画面与表演：角色转身。
摄影：侧面中景。
声音：只保留与动作同步的接触声、衣料声和环境底噪。
结束画面：角色停在门口。
"""
    codes = {item.code for item in analyze_prompt(generic, has_spoken_dialogue=False)}
    if "E_GENERIC_SOUND_FILLER" not in codes:
        raise AssertionError("generic sound filler escaped")

    print("Performance feasibility guard self-test: 8/8 passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", type=Path)
    parser.add_argument("--spoken-dialogue", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.prompt is None:
        parser.error("prompt path is required unless --self-test is used")
    findings = analyze_prompt(
        args.prompt.read_text(encoding="utf-8-sig"),
        has_spoken_dialogue=args.spoken_dialogue,
    )
    print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
