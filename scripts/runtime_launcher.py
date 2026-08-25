#!/usr/bin/env python3
"""银幕总控统一运行入口；普通用户和创作模型无需直接调用底层脚本。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

sys.dont_write_bytecode = True
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PACKAGE_ROOT / "scripts"

DIRECT_COMMANDS = {
    "准备": "prepare_longform_authoring.py",
    "prepare": "prepare_longform_authoring.py",
    "模块": "select_runtime_modules.py",
    "modules": "select_runtime_modules.py",
    "验证合同": "validate_longform_contract.py",
    "合同验证": "validate_longform_contract.py",
    "validate-contract": "validate_longform_contract.py",
    "创作预检": "continuum_creative_preflight.py",
    "creative-preflight": "continuum_creative_preflight.py",
    "制作检查": "validate_production_control.py",
    "production-check": "validate_production_control.py",
}
WORKFLOW_COMMANDS = {
    "检查": ("check_argv", "finalize_longform_contract.py", True),
    "check": ("check_argv", "finalize_longform_contract.py", True),
    "重试": ("retry_argv", "finalize_longform_contract.py", True),
    "retry": ("retry_argv", "finalize_longform_contract.py", True),
    "提交": ("commit_argv", "finalize_longform_contract.py", False),
    "commit": ("commit_argv", "finalize_longform_contract.py", False),
    "重新准备": ("reprepare_argv", "prepare_longform_authoring.py", None),
    "reprepare": ("reprepare_argv", "prepare_longform_authoring.py", None),
}


class LauncherError(ValueError):
    """A user-actionable launcher error."""


RUN_NUMBER_RE = re.compile(r"RUN[0-9]+")

PUBLIC_SUCCESS_MESSAGES = {
    "模块": "模块选择已完成。",
    "modules": "模块选择已完成。",
    "验证合同": "合同检查已通过。",
    "合同验证": "合同检查已通过。",
    "validate-contract": "合同检查已通过。",
    "创作预检": "剧本与提示词的完整性预检已通过。",
    "creative-preflight": "剧本与提示词的完整性预检已通过。",
    "制作检查": "对白、动作、镜头衔接和制作记录检查已通过。",
    "production-check": "对白、动作、镜头衔接和制作记录检查已通过。",
    "检查": "检查已通过，可以继续提交。",
    "check": "检查已通过，可以继续提交。",
    "重试": "检查已通过，可以继续提交。",
    "retry": "检查已通过，可以继续提交。",
    "提交": "文字方案已经保存。尚未进行真实媒体验证。",
    "commit": "文字方案已经保存。尚未进行真实媒体验证。",
    "重新准备": "工作面已经重新准备，请继续填写。",
    "reprepare": "工作面已经重新准备，请继续填写。",
}


def _validate_prepare_run_number(arguments: Sequence[str]) -> None:
    """Keep the public run-number contract ahead of the internal helper."""
    supplied: list[str] = []
    index = 0
    while index < len(arguments):
        item = arguments[index]
        if item == "--":
            break
        if item == "--run-id":
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
                raise LauncherError(
                    "没有填写本轮编号。请写成大写 RUN 加阿拉伯数字，例如 RUN001。"
                )
            supplied.append(arguments[index + 1])
            index += 2
            continue
        if item.startswith("--run-id="):
            supplied.append(item.split("=", 1)[1])
        index += 1

    if not supplied:
        raise LauncherError(
            "还没有填写本轮编号。请写成大写 RUN 加阿拉伯数字，例如 RUN001。"
        )
    if len(supplied) > 1:
        raise LauncherError(
            "本轮编号只能填写一次。请保留一个大写 RUN 加阿拉伯数字的编号，例如 RUN001。"
        )
    if supplied and RUN_NUMBER_RE.fullmatch(supplied[0]) is None:
        raise LauncherError(
            "本轮编号写法不对。请写成大写 RUN 加阿拉伯数字，例如 RUN001。"
        )


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _read_workflow_command(
    authoring_path: Path,
    field: str,
    expected_script: str,
    check_flag_required: bool | None,
) -> list[str]:
    try:
        document = json.loads(authoring_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise LauncherError(f"找不到工作面文件：{authoring_path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LauncherError(f"工作面文件无法读取或格式不正确：{authoring_path}") from exc

    workflow = (
        document.get("immutable_contract", {}).get("authoring_workflow", {})
        if isinstance(document, dict)
        else {}
    )
    command = workflow.get(field)
    if (
        not isinstance(command, list)
        or len(command) < 2
        or any(not isinstance(item, str) or not item for item in command)
    ):
        raise LauncherError("工作面缺少可执行步骤，请重新运行“准备”。")

    expected_path = SCRIPTS_DIR / expected_script
    actual_path = Path(command[1])
    if not _same_path(actual_path, expected_path):
        raise LauncherError("工作面中的运行目标不属于当前银幕总控包，已拒绝执行。")

    has_check_flag = "--check-overlays" in command[2:]
    if check_flag_required is not None and has_check_flag is not check_flag_required:
        raise LauncherError("工作面中的检查或提交步骤已发生变化，请重新运行“准备”。")
    return [str(expected_path), *command[2:]]


def _machine_payload(*streams: str | None) -> dict:
    """Read a helper result without exposing its machine surface."""

    for stream in streams:
        if not isinstance(stream, str):
            continue
        candidates = [stream.strip(), *reversed(stream.splitlines())]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
    return {}


def _public_failure_message(action: str | None, payload: dict) -> str:
    count = payload.get("root_error_count", payload.get("error_count"))
    count_text = f"发现 {count} 处需要修改。" if isinstance(count, int) and count > 0 else ""
    if action in {"检查", "check", "重试", "retry", "提交", "commit"}:
        message = (
            f"银幕总控没有完成这一步。{count_text}"
            "当前工作面已保留。"
        )
        repairs = payload.get("public_repairs")
        if isinstance(repairs, list) and repairs:
            lines = [message, "需要修改的位置："]
            for item in repairs:
                if not isinstance(item, dict):
                    continue
                sample = item.get("sample")
                area = item.get("area")
                instruction = item.get("instruction")
                if all(isinstance(value, str) and value for value in (sample, area, instruction)):
                    lines.append(f"- {sample} · {area}：{instruction}")
            if len(lines) > 2:
                lines.append("修正后再运行‘重试’即可。")
                return "\n".join(lines)
        return message + "请按工作面中的中文要求修正后重试。"
    if action in {"准备", "prepare"}:
        detail = payload.get("error")
        if isinstance(detail, str):
            if any(
                phrase in detail
                for phrase in (
                    "来源文件格式不支持",
                    "DOCX 文件已损坏",
                    "DOCX 包含不安全",
                    "DOCX 解压后过大",
                    "DOCX 缺少正文",
                    "DOCX 的正文结构已损坏",
                    "来源文件没有可读取的正文",
                    "找不到来源文件",
                )
            ):
                return "银幕总控没有完成准备。" + detail
        return (
            "银幕总控没有完成准备。请确认来源文件存在、结果目录为空，"
            "文件使用 TXT、Markdown 或 Word DOCX，并按帮助中的本轮编号示例修正后重试。"
        )
    if action in {"创作预检", "creative-preflight"}:
        return "剧本或提示词仍有需要修正的完整性问题。请查看指定的机器报告并局部修订。"
    if action in {"制作检查", "production-check"}:
        message = f"制作记录还不能继续。{count_text}"
        repairs = payload.get("public_repairs")
        if isinstance(repairs, list) and repairs:
            lines = [message, "需要修改的位置："]
            for item in repairs:
                if not isinstance(item, dict):
                    continue
                area = item.get("area")
                instruction = item.get("instruction")
                if isinstance(area, str) and area and isinstance(instruction, str) and instruction:
                    lines.append(f"- {area}：{instruction}")
            if len(lines) > 2:
                return "\n".join(lines)
        return message + "请按制作记录中的中文提示局部修正。"
    return "银幕总控没有完成这一步。请检查输入文件和填写内容后重试。"


def _run_python_script(
    script_and_args: Sequence[str], *, action: str | None = None,
    success_message: str | None = None
) -> int:
    if not script_and_args:
        raise LauncherError("没有可执行的银幕总控步骤。")
    script = Path(script_and_args[0])
    if not script.is_file():
        raise LauncherError(f"运行所需文件缺失：{script.name}")
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONUTF8"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(script), *script_and_args[1:]],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise LauncherError("运行环境暂时无法启动，请确认文件完整后重试。") from exc
    payload = _machine_payload(completed.stdout, completed.stderr)
    if completed.returncode:
        print(_public_failure_message(action, payload), file=sys.stderr)
    else:
        print(success_message or PUBLIC_SUCCESS_MESSAGES.get(action, "银幕总控已完成这一步。"))
        if action in {"准备", "prepare"}:
            prepared = payload
            for label, field in (
                ("请填写创作工作面", "compact_overlays"),
                ("检查时使用", "authoring"),
                ("最终结果目录", "final_output_directory"),
            ):
                value = prepared.get(field)
                if isinstance(value, str) and value:
                    print(f"{label}：{value}")
    return completed.returncode


def _print_help() -> None:
    print(
        "银幕总控统一运行入口\n"
        "  运行银幕总控.cmd 准备 <来源文件> --output-dir <空目录> --run-id <本轮编号>\n"
        "  本轮编号必须写成大写 RUN 加阿拉伯数字，例如 RUN001（可以直接复制）。\n"
        "  来源文件支持 TXT、Markdown 和 Word DOCX。\n"
        "  可复制示例：运行银幕总控.cmd 准备 \"我的小说.docx\" --output-dir \"本轮结果\" --run-id RUN001\n"
        "  运行银幕总控.cmd 检查 <AUTHORING.json>\n"
        "  运行银幕总控.cmd 重试 <AUTHORING.json>\n"
        "  运行银幕总控.cmd 提交 <AUTHORING.json>\n"
        "  运行银幕总控.cmd 重新准备 <AUTHORING.json>\n"
        "  运行银幕总控.cmd 验证合同 <MACHINE_STATE.json>（也可写“合同验证”）\n"
        "  运行银幕总控.cmd 创作预检 <创作预检.json> --output <机器报告.json>\n"
        "  运行银幕总控.cmd 制作检查 <制作记录.json> --output <机器报告.json>\n"
        "普通用户不需要安装或选择 Python；启动器会自动寻找可用环境。"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"帮助", "help", "--help", "-h"}:
        _print_help()
        return 0

    command, *remaining = args
    if command == "自检参数" and os.environ.get("SILVER_LAUNCHER_TEST_MODE") == "1":
        print(
            "SILVER_LAUNCHER_TEST:"
            + json.dumps(
                {"executable": sys.executable, "args": remaining},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0

    try:
        if command in DIRECT_COMMANDS:
            if command in {"准备", "prepare"}:
                _validate_prepare_run_number(remaining)
            script = SCRIPTS_DIR / DIRECT_COMMANDS[command]
            return _run_python_script(
                [str(script), *remaining],
                action=command,
                success_message=(
                    "银幕总控已完成准备，可以继续填写工作面。"
                    if command in {"准备", "prepare"}
                    else None
                ),
            )
        if command in WORKFLOW_COMMANDS:
            if len(remaining) != 1:
                raise LauncherError(f"“{command}”只需要一个 AUTHORING.json 路径。")
            field, expected_script, check_flag_required = WORKFLOW_COMMANDS[command]
            persisted = _read_workflow_command(
                Path(remaining[0]), field, expected_script, check_flag_required
            )
            return _run_python_script(persisted, action=command)
        raise LauncherError(f"不认识步骤“{command}”。请运行“运行银幕总控.cmd 帮助”。")
    except LauncherError as exc:
        print(f"银幕总控无法继续：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
