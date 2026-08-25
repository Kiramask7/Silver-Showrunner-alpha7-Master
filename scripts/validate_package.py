#!/usr/bin/env python3
"""Validate an Alpha.7 Master source tree or extracted RUNTIME_ONLY package."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.dont_write_bytecode = True
VERSION = "1.1.3"
BUILD = "alpha7-master-v1.1.3"
DISPLAY_NAME = "Silver-Showrunner-alpha.7-Master v1.1.3"
RELEASE_BASENAME = "Silver-Showrunner-alpha.7-Master-v1.1.3"
DEFAULT_PROFILE = "MANGA_CORE"
READ_MODE = "MODULAR_ONLY"
READ_MODE_MARKER_FILE = "00_READ_ME_FIRST.md"
READ_MODE_MARKER = "SILVER_SHOWRUNNER_READ_MODE: MODULAR_ONLY"
ROUTE_REGISTRY = "schemas/runtime_route_registry.json"
ROUTE_REGISTRY_SCHEMA = "alpha7-master-runtime-route-registry-v1"
ONEFILE_MARKER = "SILVER_SHOWRUNNER_READ_MODE: ONEFILE_ONLY"
ONEFILE_GUARD_MARKER = "DO_NOT_LOAD_SOURCE_MODULES_WITH_THIS_ONEFILE: true"
PROFILE_ORDER = (
    "MANGA_CORE", "TEXT_ONLY_ECO", "LONGFORM", "AUX", "MEDIA_RELEASE", "FULL",
)
RUNTIME_EXCLUDED_PREFIXES = ("tests/",)
RUNTIME_EXCLUDED_FILES = (
    "VERSION_NOTES.md",
    "scripts/build_onefile.py",
    "scripts/build_release.py",
    "scripts/sync_embedded_schemas.py",
)
RUNTIME_ADDED_FILES = (
    "运行银幕总控.cmd",
    "schemas/runtime_route_registry.json",
    "schemas/user_presentation_dictionary.json",
    "scripts/migrate_longform_contract.py",
    "scripts/render_creator_view.py",
    "scripts/runtime_launcher.py",
)
REPOSITORY_ONLY_FILES = (
    "README.md",
    "RELEASE_NOTES.md",
    "1分钟说明使用手册.md",
)
SOURCE_ADDED_TESTS = (
    "tests/run_execution_compile_tests.py",
    "tests/run_semantic_gate_tests.py",
    "tests/run_longform_authoring_tests.py",
    "tests/run_creator_presentation_tests.py",
    "tests/run_route_registry_tests.py",
    "tests/run_release_cleanliness_tests.py",
    "tests/run_runtime_launcher_tests.py",
    "tests/run_master_production_tests.py",
    "tests/run_release_fix_tests.py",
)

# Keep the release gate machine-readable without placing blocked wording in the
# package source itself. IDs are stable so failures can be reported safely.
RESTRICTED_CJK_CODEPOINT_GROUPS = (
    ("CN001", (0x4E09, 0x4E2A, 0x4EE3, 0x8868)),
    ("CN002", (0x653F, 0x6CBB)),
    ("CN003", (0x653F, 0x515A)),
    ("CN004", (0x653F, 0x9EE8)),
    ("CN005", (0x5171, 0x4EA7, 0x515A)),
    ("CN006", (0x5171, 0x7522, 0x9EE8)),
    ("CN007", (0x4E2D, 0x5171)),
    ("CN008", (0x515A, 0x653F)),
    ("CN009", (0x653F, 0x5E9C)),
    ("CN010", (0x653F, 0x6743)),
    ("CN011", (0x653F, 0x6B0A)),
    ("CN012", (0x6267, 0x653F)),
    ("CN013", (0x57F7, 0x653F)),
    ("CN014", (0x4EBA, 0x5927)),
    ("CN015", (0x653F, 0x534F)),
    ("CN016", (0x570B, 0x653F, 0x5354)),
    ("CN017", (0x56FD, 0x5BB6, 0x4E3B, 0x5E2D)),
    ("CN018", (0x570B, 0x5BB6, 0x4E3B, 0x5E2D)),
    ("CN019", (0x603B, 0x4E66, 0x8BB0)),
    ("CN020", (0x7E3D, 0x66F8, 0x8A18)),
    ("CN021", (0x603B, 0x7EDF)),
    ("CN022", (0x7E3D, 0x7D71)),
    ("CN023", (0x603B, 0x7406)),
    ("CN024", (0x7E3D, 0x7406)),
    ("CN025", (0x56FD, 0x52A1, 0x9662)),
    ("CN026", (0x570B, 0x52D9, 0x9662)),
    ("CN027", (0x4EBA, 0x6C11, 0x4EE3, 0x8868, 0x5927, 0x4F1A)),
    ("CN028", (0x4EBA, 0x6C11, 0x4EE3, 0x8868, 0x5927, 0x6703)),
    ("CN029", (0x8BAE, 0x4F1A)),
    ("CN030", (0x8B70, 0x6703)),
    ("CN031", (0x56FD, 0x4F1A)),
    ("CN032", (0x570B, 0x6703)),
    ("CN033", (0x5185, 0x9601)),
    ("CN034", (0x5167, 0x95A3)),
    ("CN035", (0x515A, 0x59D4)),
    ("CN036", (0x9EE8, 0x59D4)),
    ("CN037", (0x6267, 0x653F, 0x515A)),
    ("CN038", (0x57F7, 0x653F, 0x9EE8)),
    ("CN039", (0x53CD, 0x5BF9, 0x515A)),
    ("CN040", (0x53CD, 0x5C0D, 0x9EE8)),
    ("CN041", (0x6C11, 0x4E3B)),
    ("CN042", (0x4E13, 0x5236)),
    ("CN043", (0x5C08, 0x5236)),
    ("CN044", (0x610F, 0x8BC6, 0x5F62, 0x6001)),
    ("CN045", (0x610F, 0x8B58, 0x5F62, 0x614B)),
    ("CN046", (0x9A6C, 0x514B, 0x601D, 0x4E3B, 0x4E49)),
    ("CN047", (0x99AC, 0x514B, 0x601D, 0x4E3B, 0x7FA9)),
    ("CN048", (0x5217, 0x5B81, 0x4E3B, 0x4E49)),
    ("CN049", (0x5217, 0x5BE7, 0x4E3B, 0x7FA9)),
    ("CN050", (0x6BDB, 0x6CFD, 0x4E1C, 0x601D, 0x60F3)),
    ("CN051", (0x6BDB, 0x6FA4, 0x6771, 0x601D, 0x60F3)),
    ("CN052", (0x9093, 0x5C0F, 0x5E73, 0x7406, 0x8BBA)),
    ("CN053", (0x9127, 0x5C0F, 0x5E73, 0x7406, 0x8AD6)),
    ("CN054", (0x79D1, 0x5B66, 0x53D1, 0x5C55, 0x89C2)),
    ("CN055", (0x79D1, 0x5B78, 0x767C, 0x5C55, 0x89C0)),
    ("CN056", (0x4E2D, 0x56FD, 0x7279, 0x8272, 0x793E, 0x4F1A, 0x4E3B, 0x4E49)),
    ("CN057", (0x4E2D, 0x570B, 0x7279, 0x8272, 0x793E, 0x6703, 0x4E3B, 0x7FA9)),
    ("CN058", (0x793E, 0x4F1A, 0x4E3B, 0x4E49)),
    ("CN059", (0x793E, 0x6703, 0x4E3B, 0x7FA9)),
    ("CN060", (0x5171, 0x4EA7, 0x4E3B, 0x4E49)),
    ("CN061", (0x5171, 0x7522, 0x4E3B, 0x7FA9)),
    ("CN062", (0x4E00, 0x56FD, 0x4E24, 0x5236)),
    ("CN063", (0x4E00, 0x570B, 0x5169, 0x5236)),
    ("CN064", (0x9009, 0x4E3E)),
    ("CN065", (0x9078, 0x8209)),
    ("CN066", (0x5019, 0x9009, 0x4EBA)),
    ("CN067", (0x5019, 0x9078, 0x4EBA)),
    ("CN068", (0x8BAE, 0x5458)),
    ("CN069", (0x8B70, 0x54E1)),
    ("CN070", (0x5916, 0x4EA4)),
    ("CN071", (0x4E3B, 0x6743)),
    ("CN072", (0x4E3B, 0x6B0A)),
    ("CN073", (0x4E09, 0x500B, 0x4EE3, 0x8868)),
    ("CN074", (0x33, 0x4E2A, 0x4EE3, 0x8868)),
    ("CN075", (0x33, 0x500B, 0x4EE3, 0x8868)),
)
RESTRICTED_LATIN_CODEPOINT_GROUPS = (
    ("EN001", (112, 111, 108, 105, 116, 105, 99, 115)),
    ("EN002", (112, 111, 108, 105, 116, 105, 99, 97, 108)),
    ("EN003", (103, 111, 118, 101, 114, 110, 109, 101, 110, 116)),
    ("EN004", (101, 108, 101, 99, 116, 105, 111, 110)),
    ("EN005", (112, 114, 101, 115, 105, 100, 101, 110, 116)),
    ("EN006", (112, 114, 105, 109, 101, 32, 109, 105, 110, 105, 115, 116, 101, 114)),
    ("EN007", (112, 97, 114, 108, 105, 97, 109, 101, 110, 116)),
    ("EN008", (115, 101, 110, 97, 116, 101)),
    ("EN009", (99, 111, 110, 103, 114, 101, 115, 115)),
    ("EN010", (99, 111, 109, 109, 117, 110, 105, 115, 109)),
    ("EN011", (99, 111, 109, 109, 117, 110, 105, 115, 116)),
    ("EN012", (115, 111, 99, 105, 97, 108, 105, 115, 109)),
    ("EN013", (115, 111, 99, 105, 97, 108, 105, 115, 116)),
    ("EN014", (105, 100, 101, 111, 108, 111, 103, 121)),
    ("EN015", (115, 111, 118, 101, 114, 101, 105, 103, 110, 116, 121)),
    ("EN016", (100, 105, 112, 108, 111, 109, 97, 99, 121)),
    ("EN017", (99, 99, 112)),
    ("EN018", (99, 112, 99)),
    ("EN019", (116, 104, 114, 101, 101, 32, 114, 101, 112, 114, 101, 115, 101, 110, 116, 115)),
    ("EN020", (116, 104, 114, 101, 101, 32, 114, 101, 112, 114, 101, 115, 101, 110, 116, 97, 116, 105, 111, 110, 115)),
    ("EN021", (115, 97, 110, 32, 103, 101, 32, 100, 97, 105, 32, 98, 105, 97, 111)),
    ("EN022", (115, 97, 110, 103, 101, 100, 97, 105, 98, 105, 97, 111)),
)
PUBLIC_REVISION_CODEPOINT_GROUPS = (
    ("REV001", (97, 108, 112, 104, 97, 51)),
    ("REV002", (97, 108, 112, 104, 97, 52)),
    ("REV003", (97, 108, 112, 104, 97, 53)),
    ("REV004", (97, 108, 112, 104, 97, 54)),
)
PUBLIC_REVISION_FAMILY_PREFIX = (97, 108, 112, 104, 97, 55, 114)
PUBLIC_SELF_RELEASE_SCOPE = (109, 97, 115, 116, 101, 114)
PUBLIC_SOURCE_ARCHIVE_SCOPE = (115, 111, 117, 114, 99, 101, 95, 97, 114, 99, 104, 105, 118, 101)
PUBLIC_LONGFORM_ARCHIVE_SCOPE = (
    115, 105, 108, 118, 101, 114, 108, 111, 110, 103, 102, 111, 114, 109,
    99, 111, 110, 116, 105, 110, 117, 105, 116, 121, 118, 105, 100, 101, 111,
    100, 105, 114, 101, 99, 116, 111, 114, 115, 107, 105, 108, 108,
)
PUBLIC_LONGFORM_SOURCE_SCOPE = (
    115, 105, 108, 118, 101, 114, 32, 108, 111, 110, 103, 102, 111, 114, 109,
    32, 99, 111, 110, 116, 105, 110, 117, 105, 116, 121, 32, 118, 105, 100, 101,
    111, 32, 100, 105, 114, 101, 99, 116, 111, 114,
)
PUBLIC_RETIRED_SELF_VERSIONS = (
    (49, 46, 49, 46, 48),
    (49, 46, 49, 46, 49),
    (49, 46, 49, 46, 50),
)
PUBLIC_STANDALONE_RETIRED_REVISIONS = (
    ("REV007", (114, 49, 51)),
)
TEXT_CLEAN_SUFFIXES = {".cmd", ".json", ".md", ".py", ".txt", ".yaml", ".yml"}


def ordered_unique(items):
    return tuple(dict.fromkeys(items))


def remap_embedded_local_refs(value: object, schema_name: str) -> object:
    """Retarget standalone refs without importing excluded source tooling."""

    if isinstance(value, dict):
        return {
            key: (
                f"#/$defs/{schema_name}/$defs/{item[len('#/$defs/') :]}"
                if key == "$ref" and isinstance(item, str) and item.startswith("#/$defs/")
                else remap_embedded_local_refs(item, schema_name)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [remap_embedded_local_refs(item, schema_name) for item in value]
    return value


def iter_refs(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            yield from iter_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_refs(child)


def resolve_local_ref(document, ref: str):
    if not ref.startswith("#/"):
        raise KeyError(ref)
    current = document
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def is_generated_onefile(path: Path) -> bool:
    name = path.name
    return name == "SILVER_SHOWRUNNER_ONEFILE.md" or (
        "ONEFILE" in name.upper() and name.lower().endswith(".md")
    )


def has_onefile_content(path: Path) -> bool:
    """Detect renamed ONEFILE payloads by identity and embedded-source markers."""

    if path.suffix.lower() != ".md" or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8-sig", errors="strict")
    if ONEFILE_MARKER in text:
        return True
    return (
        ONEFILE_GUARD_MARKER in text
        and "Source / SHA-256 Index" in text
        and text.count("<!-- SOURCE:") >= 1
    )


def package_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and not is_generated_onefile(path)
    )


def relative_name(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def is_runtime_payload_relative(relative: str) -> bool:
    return (
        relative not in RUNTIME_EXCLUDED_FILES
        and relative not in REPOSITORY_ONLY_FILES
        and not relative.startswith(RUNTIME_EXCLUDED_PREFIXES)
    )


def runtime_payload_files(root: Path) -> list[Path]:
    return [
        path for path in package_files(root)
        if is_runtime_payload_relative(relative_name(root, path))
    ]


def _decoded_codepoints(points: tuple[int, ...]) -> str:
    return "".join(chr(point) for point in points)


def restricted_lexicon_hits(label: str, text: str) -> list[str]:
    """Return stable gate IDs without echoing blocked wording."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    compact = "".join(character for character in normalized if character.isalnum())
    latin_words = re.sub(r"[^a-z0-9]+", " ", normalized)
    hits: list[str] = []
    for gate_id, points in RESTRICTED_CJK_CODEPOINT_GROUPS:
        if _decoded_codepoints(points) in compact:
            hits.append(f"TEXT_CLEAN_GATE[{gate_id}] {label}")
    for gate_id, points in RESTRICTED_LATIN_CODEPOINT_GROUPS:
        term = _decoded_codepoints(points)
        pattern = r"(?<![a-z0-9])" + r"\s+".join(
            re.escape(part) for part in term.split()
        ) + r"(?![a-z0-9])"
        if re.search(pattern, latin_words):
            hits.append(f"TEXT_CLEAN_GATE[{gate_id}] {label}")
    return hits


def public_revision_hits(label: str, text: str) -> list[str]:
    """Reject retired public revision labels without storing them as text."""

    normalized = unicodedata.normalize("NFKC", text).casefold()
    compact = "".join(character for character in normalized if character.isalnum())
    hits: list[str] = []

    def add_hit(gate_id: str) -> None:
        finding = f"PUBLIC_REVISION_NAME_GATE[{gate_id}] {label}"
        if finding not in hits:
            hits.append(finding)

    for gate_id, points in PUBLIC_REVISION_CODEPOINT_GROUPS:
        if _decoded_codepoints(points) in compact:
            add_hit(gate_id)
    family = _decoded_codepoints(PUBLIC_REVISION_FAMILY_PREFIX)
    if re.search(re.escape(family) + r"[0-9]+", compact):
        add_hit("REV005")

    semantic_version = r"(?<![0-9.])v?(\d+\.\d+\.\d+)(?![0-9]|\.[0-9])"
    self_scope = _decoded_codepoints(PUBLIC_SELF_RELEASE_SCOPE)
    self_pattern = re.compile(
        re.escape(self_scope) + r"[\s._-]*" + semantic_version,
        flags=re.IGNORECASE,
    )
    retired_versions = {
        _decoded_codepoints(points) for points in PUBLIC_RETIRED_SELF_VERSIONS
    }
    if any(match.group(1) in retired_versions for match in self_pattern.finditer(normalized)):
        add_hit("REV006")

    source_archive_scope = _decoded_codepoints(PUBLIC_SOURCE_ARCHIVE_SCOPE)
    longform_archive_scope = _decoded_codepoints(PUBLIC_LONGFORM_ARCHIVE_SCOPE)
    longform_scope = _decoded_codepoints(PUBLIC_LONGFORM_SOURCE_SCOPE)
    for line in normalized.splitlines():
        version_match = re.search(semantic_version, line, flags=re.IGNORECASE)
        normalized_words = " ".join(line.replace("-", " ").replace("_", " ").split())
        compact_line = "".join(character for character in line if character.isalnum())
        if (
            source_archive_scope in line
            and longform_archive_scope in compact_line
            and version_match
            and version_match.group(1) in retired_versions
        ):
            add_hit("REV006")
        if (
            longform_scope in normalized_words
            and version_match
            and version_match.group(1) in retired_versions
        ):
            add_hit("REV006")

    for gate_id, points in PUBLIC_STANDALONE_RETIRED_REVISIONS:
        token = re.escape(_decoded_codepoints(points))
        if re.search(r"(?<![a-z0-9])" + token + r"(?![a-z0-9])", normalized):
            add_hit(gate_id)
    return hits


def release_text_clean_findings(root: Path, paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        relative = relative_name(root, path)
        findings.extend(restricted_lexicon_hits(f"path:{relative}", relative))
        findings.extend(public_revision_hits(f"path:{relative}", relative))
        if path.suffix.casefold() not in TEXT_CLEAN_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8-sig", errors="strict")
        except (OSError, UnicodeError):
            findings.append(f"TEXT_CLEAN_GATE[READ] {relative}")
            continue
        findings.extend(restricted_lexicon_hits(f"file:{relative}", text))
        findings.extend(public_revision_hits(f"file:{relative}", text))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--surface", choices=("auto", "source", "runtime"), default="auto")
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    surface = args.surface
    if surface == "auto":
        surface = "source" if (root / "scripts/build_release.py").is_file() else "runtime"

    try:
        manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: invalid manifest: {exc}", file=sys.stderr)
        return 2

    files = package_files(root)
    runtime_files = runtime_payload_files(root)
    # Repository-only guides are excluded from the installable runtime count but
    # remain public text, so every visible file must still pass the clean gate.
    clean_scope = files
    errors.extend(release_text_clean_findings(root, clean_scope))
    cached_artifacts = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if "__pycache__" in path.parts or (path.is_file() and path.suffix == ".pyc")
    )
    if cached_artifacts:
        errors.append(
            "runtime source tree must not contain Python cache artifacts: "
            + ", ".join(cached_artifacts)
        )
    if manifest.get("version") != VERSION:
        errors.append(f"manifest version is {manifest.get('version')!r}, expected {VERSION!r}")
    if manifest.get("name") != RELEASE_BASENAME:
        errors.append("manifest name does not match the Alpha.7 release root")
    if manifest.get("display_name") != DISPLAY_NAME:
        errors.append("manifest display_name is stale")
    if manifest.get("build") != BUILD:
        errors.append("manifest build label is stale")
    if manifest.get("read_mode") != READ_MODE:
        errors.append("E_READ_MODE_CONFLICT: manifest read_mode must be MODULAR_ONLY")
    if manifest.get("read_mode_marker_file") != READ_MODE_MARKER_FILE:
        errors.append("E_READ_MODE_CONFLICT: manifest read mode marker file is stale")
    if manifest.get("read_mode_marker") != READ_MODE_MARKER:
        errors.append("E_READ_MODE_CONFLICT: manifest read mode marker is stale")
    if manifest.get("runtime_route_registry") != ROUTE_REGISTRY:
        errors.append("manifest runtime_route_registry is stale")
    if surface == "source" and manifest.get("source_manifest_file_count") != len(files):
        errors.append(
            f"manifest source_manifest_file_count={manifest.get('source_manifest_file_count')} "
            f"but source contains {len(files)} files"
        )
    if manifest.get("file_count") != len(runtime_files):
        errors.append(
            f"manifest file_count={manifest.get('file_count')} "
            f"but runtime payload contains {len(runtime_files)} files"
        )
    if manifest.get("payload_file_count") != len(runtime_files):
        errors.append(
            f"manifest payload_file_count={manifest.get('payload_file_count')} "
            f"but runtime payload contains {len(runtime_files)} files"
        )
    if manifest.get("runtime_payload_file_count") != len(runtime_files):
        errors.append("manifest runtime_payload_file_count does not match runtime payload")
    if manifest.get("distribution_profile") != "RUNTIME_ONLY":
        errors.append("manifest distribution_profile must be RUNTIME_ONLY")
    if manifest.get("source_regression_fixtures_present") is not True:
        errors.append("manifest must record source regression fixtures")
    for key in (
        "regression_fixtures_included", "tests_included",
        "build_tooling_included", "version_history_included",
    ):
        if manifest.get(key) is not False:
            errors.append(f"manifest {key} must be false for RUNTIME_ONLY delivery")
    if manifest.get("runtime_excluded_prefixes") != list(RUNTIME_EXCLUDED_PREFIXES):
        errors.append("manifest runtime_excluded_prefixes is stale")
    if manifest.get("runtime_excluded_files") != list(RUNTIME_EXCLUDED_FILES):
        errors.append("manifest runtime_excluded_files is stale")
    if manifest.get("runtime_added_files") != list(RUNTIME_ADDED_FILES):
        errors.append("manifest runtime_added_files is stale")
    if manifest.get("source_added_tests") != list(SOURCE_ADDED_TESTS):
        errors.append("manifest source_added_tests is stale")
    if manifest.get("read_first") != "SKILL.md":
        errors.append("manifest read_first must be the unique SKILL.md entry")
    if manifest.get("skill_name") != "silver-showrunner":
        errors.append("manifest skill_name must be silver-showrunner")
    if manifest.get("default_interaction_language") != "zh-CN":
        errors.append("manifest default_interaction_language must be zh-CN")
    if manifest.get("competition_demo_included") is not False:
        errors.append("Alpha.7 runtime package must not include a competition demo")
    if manifest.get("runtime_core_project_specific_content") is not False:
        errors.append("runtime core must not contain benchmark-project facts")
    if manifest.get("benchmark_fixtures_included") is not False:
        errors.append("Alpha.7 runtime package must not include benchmark fixtures")
    if manifest.get("skill_entry") != "SKILL.md":
        errors.append("manifest skill_entry must be SKILL.md")
    if manifest.get("handoff_read_first") != "SKILL.md":
        errors.append("manifest handoff_read_first must be SKILL.md")
    if manifest.get("schema_draft") != "2020-12":
        errors.append("manifest schema_draft must be 2020-12")
    if manifest.get("onefile_default_profile") != DEFAULT_PROFILE:
        errors.append(f"manifest onefile_default_profile must be {DEFAULT_PROFILE}")
    if manifest.get("onefile_delivery") != "EXTERNAL_RELEASE_ARTIFACT":
        errors.append("manifest ONEFILE delivery must be external to the modular package")
    if manifest.get("onefile_module_policy") != "MUTUALLY_EXCLUSIVE":
        errors.append("manifest must declare ONEFILE/modules mutually exclusive")
    if manifest.get("onefile_profiles") != list(PROFILE_ORDER):
        errors.append("manifest onefile_profiles does not match the frozen profile order")

    if surface == "runtime":
        leaked = [
            relative_name(root, path)
            for path in files
            if not is_runtime_payload_relative(relative_name(root, path))
            and relative_name(root, path) not in REPOSITORY_ONLY_FILES
        ]
        if leaked:
            errors.append("runtime package contains source-only files: " + ", ".join(leaked))

    embedded_onefiles = []
    for path in sorted(root.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            content_detected = has_onefile_content(path)
        except (OSError, UnicodeError) as exc:
            errors.append(
                "E_READ_MODE_CONFLICT: cannot inspect Markdown identity "
                f"{path.relative_to(root).as_posix()}: {exc}"
            )
            continue
        if is_generated_onefile(path) or content_detected:
            embedded_onefiles.append(path.relative_to(root).as_posix())
    if embedded_onefiles:
        errors.append(
            "E_READ_MODE_CONFLICT: modular package contains a named or "
            "content-detected ONEFILE artifact: "
            + ", ".join(embedded_onefiles)
        )

    registry_path = root / ROUTE_REGISTRY
    try:
        route_registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid runtime route registry: {exc}")
        route_registry = {}
    if route_registry.get("schema_version") != ROUTE_REGISTRY_SCHEMA:
        errors.append("runtime route registry schema version is stale")
    read_mode_contract = route_registry.get("read_mode_contract", {})
    if (
        read_mode_contract.get("mode") != READ_MODE
        or read_mode_contract.get("manifest_key") != "read_mode"
        or read_mode_contract.get("entry_marker_file") != READ_MODE_MARKER_FILE
        or read_mode_contract.get("entry_marker") != READ_MODE_MARKER
        or read_mode_contract.get("onefile_marker") != ONEFILE_MARKER
        or read_mode_contract.get("onefile_guard_marker") != ONEFILE_GUARD_MARKER
        or read_mode_contract.get("conflict_error") != "E_READ_MODE_CONFLICT"
    ):
        errors.append("E_READ_MODE_CONFLICT: route registry read mode contract is stale")

    readme_pointer = root / "00_READ_ME_FIRST.md"
    if not readme_pointer.is_file():
        errors.append("00_READ_ME_FIRST.md compatibility pointer missing")
    else:
        pointer_bytes = readme_pointer.read_bytes()
        pointer_text = pointer_bytes.decode("utf-8-sig")
        if len(pointer_bytes) > 1024:
            errors.append("00_READ_ME_FIRST.md must remain a <=1 KiB compatibility pointer")
        for marker in ("SKILL.md", "ONEFILE", READ_MODE_MARKER, "不得同时"):
            if marker not in pointer_text:
                errors.append(f"00_READ_ME_FIRST.md missing compatibility marker: {marker}")

    for path in files:
        relative = path.relative_to(root).as_posix()
        if "\ufffd" in path.read_text(encoding="utf-8-sig", errors="replace"):
            errors.append(f"replacement character found in {relative}")
        if path.suffix == ".json":
            try:
                json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSON {relative}: {exc}")

    skill_text = (root / "SKILL.md").read_text(encoding="utf-8-sig")
    frontmatter = re.match(r"\A---\s*\n(.*?)\n---\s*\n", skill_text, flags=re.DOTALL)
    if not frontmatter:
        errors.append("SKILL.md frontmatter missing")
    else:
        keys = {
            line.split(":", 1)[0].strip()
            for line in frontmatter.group(1).splitlines()
            if ":" in line
        }
        if keys != {"name", "description"}:
            errors.append(f"SKILL.md frontmatter keys are {sorted(keys)}, expected name/description only")

    if "中文优先" not in skill_text or "中文用户使用自然简体中文沟通" not in skill_text:
        errors.append("SKILL.md missing Chinese-first interaction contract")
    if "name: silver-showrunner" not in skill_text:
        errors.append("SKILL.md name must be silver-showrunner")
    if "# Silver-Showrunner-alpha.7-Master v1.1.3" not in skill_text:
        errors.append("SKILL.md display title is stale")
    if "RELEASE_READY" not in skill_text or "后续外部动作由用户决定" not in skill_text:
        errors.append("SKILL.md must stop automation at RELEASE_READY and leave later external actions to the user")
    for marker in (
        "AUTHORING.json.immutable_contract.authoring_workflow",
        "MACHINE_REPRESENTATIVE_V1",
        "供应商中性提示词工作稿（可复制）",
        "content_self_review",
        "quality_scope = CONTRACT_STRUCTURAL",
        "INDEPENDENT_EDITORIAL_REVIEW_REQUIRED",
        "IN_PLACE_THREE_CARRIER_V1",
        "execution_beats",
        "runtime_identity",
        "GUIDE_ONLY",
        "reprepare_argv",
        "`python -S`",
    ):
        if marker not in skill_text:
            errors.append(f"SKILL.md missing current creative-runtime marker: {marker}")

    language_contract = root / "references/LANGUAGE_AND_PRESENTATION_CONTRACT.md"
    if not language_contract.is_file():
        errors.append("current language and presentation contract missing")

    for contract_name in (
        "ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md",
        "ALPHA7_PROJECT_TYPE_AND_ORCHESTRATION.md",
        "ALPHA7_LONGFORM_CONTINUITY_ENGINE.md",
        "ALPHA7_EXTERNAL_EXECUTION_CONTRACT.md",
        "ALPHA7_MEDIA_EXECUTION_AND_EDITING.md",
        "ALPHA7_CHINESE_COPY_AND_FOURFOLD_PREFLIGHT.md",
        "LANGUAGE_AND_PRESENTATION_CONTRACT.md",
        "EVIDENCE_PROVIDER_RELEASE_LEARNING_CONTRACT.md",
        "NCS_NRS_BASELINE.md",
        "AGE_SAFETY_PROVIDER_AND_COVERAGE_CONTRACT.md",
        "CONTEXT_AND_BATCH_BUDGET.md",
        "TEXT_ONLY_ECO_WORKFLOW.md",
        "SCRIPT_AND_DIALOGUE_WRITING_ENGINE.md",
        "ALPHA7_CONTINUUM_CREATIVE_FIDELITY_ENGINE.md",
        "ON_DEMAND_RESEARCH_ROUTER.md",
        "PROMPT_QUALITY_CORE.md",
        "ALPHA7_MASTER_PRODUCTION_CONTROL.md",
        "PROVIDER_REGISTRY_SEED_2026-08-14.md",
        "THIRD_PARTY_ATTRIBUTIONS.md",
    ):
        if not (root / "references" / contract_name).is_file():
            errors.append(f"required Alpha.7 runtime reference missing: {contract_name}")

    eco_contract_path = root / "references/TEXT_ONLY_ECO_WORKFLOW.md"
    if eco_contract_path.is_file():
        eco_text = eco_contract_path.read_text(encoding="utf-8-sig")
        for marker in (
            "# Alpha.7 Master 纯文字省算力工作流",
            "authoring_guide.guide_version = alpha7-overlay-guide-1.5",
            "AUTHORING.json.immutable_contract.authoring_workflow",
            "MACHINE_REPRESENTATIVE_V1",
            "USER_TARGETED_EXACT_RANGES_V1",
            "locked_director_scaffold",
            "action_additions",
            "quality_overlay.scene_title / findings",
            "供应商中性的 NEP",
            "resume_entry",
            "INDEPENDENT_EDITORIAL_REVIEW_REQUIRED",
            "IN_PLACE_THREE_CARRIER_V1",
            "source_read_scope_attestation",
            "runtime_identity",
            "execution_beats",
            "引号的逐镜归位",
            "SOURCE_LOCKED_NONLEXICAL",
            "DIRECTORIAL_CONTROL",
            "逐镜视频提示词（每条可单独复制）",
            "更早合同只作为迁移输入读取",
            "E_NO_DELETE_COMMIT_REQUIRES_NEW_PATH",
            "`python -S`",
        ):
            if marker not in eco_text:
                errors.append(f"text-only ECO contract missing current marker: {marker}")

    continuum_contract_path = root / "references/ALPHA7_CONTINUUM_CREATIVE_FIDELITY_ENGINE.md"
    if continuum_contract_path.is_file():
        continuum_text = continuum_contract_path.read_text(encoding="utf-8-sig")
        for marker in (
            "# Alpha.7 Master 创作保真与完整交接引擎",
            "compression_authority: NONE",
            "delivery_fidelity: FULL_FIDELITY",
            "SEGMENTED_FULL_FIDELITY",
            "VIDEO_PROMPT",
            "IMAGE_PROMPT",
            "运行银幕总控.cmd 创作预检",
            "Production Validation 仍为 `NOT_TESTED`",
        ):
            if marker not in continuum_text:
                errors.append(f"CONTINUUM creative-fidelity contract missing marker: {marker}")

    creative_preflight_path = root / "scripts/continuum_creative_preflight.py"
    if creative_preflight_path.is_file():
        creative_preflight_text = creative_preflight_path.read_text(encoding="utf-8-sig")
        for marker in (
            'CONTRACT_VERSION = "alpha7-master-creative-preflight-v1"',
            'MODES = {"SCRIPT", "VIDEO_PROMPT", "IMAGE_PROMPT"}',
            "CF_SILENT_COMPRESSION",
            "CF_DIALOGUE_CHANGED",
            "CF_TIMELINE_GAP",
            "production_validation",
            'parser.add_argument("--self-test"',
        ):
            if marker not in creative_preflight_text:
                errors.append(f"CONTINUUM creative preflight missing marker: {marker}")

    production_control_path = root / "references/ALPHA7_MASTER_PRODUCTION_CONTROL.md"
    if production_control_path.is_file():
        production_control_text = production_control_path.read_text(encoding="utf-8-sig")
        for marker in (
            "# Alpha.7 Master 对白、动作、交接与制作登记合同",
            "alpha7-master-production-control-v1",
            "对白先排声音",
            "动作必须有因果链",
            "相邻镜头必须完成一次接力",
            "Production Validation",
            "NOT_TESTED",
        ):
            if marker not in production_control_text:
                errors.append(f"Master production-control contract missing marker: {marker}")

    production_validator_path = root / "scripts/validate_production_control.py"
    if production_validator_path.is_file():
        production_validator_text = production_validator_path.read_text(encoding="utf-8-sig")
        for marker in (
            'CONTRACT_VERSION = "alpha7-master-production-control-v1"',
            "PC_DIALOGUE_CURSOR_GAP",
            "PC_REFERENCE_MOTION_BLEED",
            "PC_OBSERVED_STATE_PRIORITY",
            "PC_COST_ACTUAL_NO_EVIDENCE",
            'parser.add_argument("--self-test"',
        ):
            if marker not in production_validator_text:
                errors.append(f"Master production-control validator missing marker: {marker}")

    legacy_runtime_files = (
        "LEGACY_GENERATION_STATE_AND_EVIDENCE_CONTRACT.md",
        "LEGACY_GENERATION_DETERMINISTIC_GUARDS.md",
        "LEGACY_GENERATION_TERMINAL_GATE_AND_COMPLETION_CONTRACT.md",
        "LEGACY_GENERATION_SEMANTIC_INTEGRITY_CONTRACT.md",
        "PROFESSIONAL_INTERACTION_PRINCIPLES.md",
    )
    for legacy_name in legacy_runtime_files:
        if (root / "references" / legacy_name).exists():
            errors.append(f"superseded runtime reference still shipped: {legacy_name}")

    agents_yaml = root / "agents/openai.yaml"
    if not agents_yaml.is_file():
        errors.append("agents/openai.yaml missing")
    else:
        agents_text = agents_yaml.read_text(encoding="utf-8-sig")
        if f'display_name: "{DISPLAY_NAME}"' not in agents_text:
            errors.append("agents/openai.yaml display name is stale")
        if "$silver-showrunner" not in agents_text:
            errors.append("agents/openai.yaml default prompt must reference $silver-showrunner")

    version_notes = root / "VERSION_NOTES.md"
    if surface == "source" and not version_notes.is_file():
        errors.append("VERSION_NOTES.md missing from source tree")
    elif surface == "source":
        version_text = version_notes.read_text(encoding="utf-8-sig")
        for marker in (
            VERSION,
            BUILD,
            "MANGA_CORE",
            "模块与 ONEFILE 互斥",
            "PROVIDER_NEUTRAL_DRAFT",
        ):
            if marker not in version_text:
                errors.append(f"VERSION_NOTES.md missing release marker: {marker}")
        if "不可执行" not in version_text or "同时回链 MASTER 与 DRAFT" not in version_text:
            errors.append("VERSION_NOTES.md does not state the DRAFT execution/binding boundary")

    required_schemas = (
        "project_state.schema.json", "stage_result.schema.json", "provider_prompt.schema.json",
        "prompt_quality.schema.json",
        "decision.schema.json", "artifact.schema.json",
        "workflow_status.schema.json", "gate_requirement.schema.json", "gate.schema.json",
        "observation.schema.json", "repair.schema.json", "learning.schema.json",
        "provider.schema.json", "publication.schema.json", "evidence.schema.json", "canonical_duration.schema.json",
        "asset_registry.schema.json", "shot_plan.schema.json", "system_invariant_registry.json",
        "protected_unknown.schema.json", "quantity_semantics.schema.json", "causal_boundary.schema.json",
        "baseline_spec.schema.json", "pilot_assessment.schema.json", "state_cleanup.schema.json",
        "project_route.schema.json", "task_record.schema.json",
        "execution_receipt.schema.json", "fourfold_preflight.schema.json",
        "minor_safety.schema.json", "dialogue_inventory.schema.json",
        "tts_coverage.schema.json", "subtitle_cue.schema.json",
        "production_control.schema.json",
    )
    for schema_name in required_schemas:
        if not (root / "schemas" / schema_name).is_file():
            errors.append(f"required Alpha.7 schema missing: {schema_name}")

    try:
        project_schema = json.loads(
            (root / "schemas/project_state.schema.json").read_text(encoding="utf-8-sig")
        )
        provider_schema = json.loads(
            (root / "schemas/provider_prompt.schema.json").read_text(encoding="utf-8-sig")
        )
        workflow_schema = json.loads(
            (root / "schemas/workflow_status.schema.json").read_text(encoding="utf-8-sig")
        )
        gate_schema = json.loads(
            (root / "schemas/gate.schema.json").read_text(encoding="utf-8-sig")
        )
        if not provider_schema.get("allOf"):
            errors.append("provider_prompt schema lacks the non-Chinese prompt conditional")
        required_project_fields = {
            "schema_version", "master_prompts", "provider_neutral_drafts",
            "reference_registry", "dialogue_inventory", "tts_coverage_records",
            "subtitle_cues",
            "spec_completion_records", "format_profiles", "output_complexity_profile",
            "project_route", "task_graph", "execution_receipts", "fourfold_preflight_records",
        }
        missing_project_fields = required_project_fields - set(project_schema.get("required", []))
        if missing_project_fields:
            errors.append(
                "project_state schema omits required Alpha.7 fields: "
                + ", ".join(sorted(missing_project_fields))
            )
        spec_values = (
            workflow_schema.get("properties", {}).get("spec_status", {}).get("enum", [])
        )
        if spec_values != ["SPEC_DRAFT", "SPEC_READY"]:
            errors.append("workflow spec_status must be exactly SPEC_DRAFT/SPEC_READY")
        if "status_basis" not in workflow_schema.get("required", []):
            errors.append("workflow_status schema must require status_basis")
        gate_properties = gate_schema.get("properties", {})
        if gate_properties.get("evaluation_status", {}).get("const") != "EXECUTED":
            errors.append("Alpha.7 persistent Gate schema must allow EXECUTED only")
        if "scope_bindings" not in gate_schema.get("required", []):
            errors.append("Alpha.7 Gate schema must require scope_bindings")
        prompt_defs = provider_schema.get("$defs", {})
        if (
            prompt_defs.get("master_prompt", {}).get("properties", {})
            .get("prompt_layer", {}).get("const") != "PROVIDER_NEUTRAL_MASTER"
        ):
            errors.append("provider_prompt schema lacks PROVIDER_NEUTRAL_MASTER definition")
        if (
            prompt_defs.get("provider_neutral_draft", {}).get("properties", {})
            .get("prompt_layer", {}).get("const") != "PROVIDER_NEUTRAL_DRAFT"
        ):
            errors.append("provider_prompt schema lacks PROVIDER_NEUTRAL_DRAFT definition")
        if (
            prompt_defs.get("transform_plan", {}).get("properties", {})
            .get("prompt_layer", {}).get("const") != "TRANSFORM_PLAN"
        ):
            errors.append("provider_prompt schema lacks TRANSFORM_PLAN definition")
        if (
            prompt_defs.get("neutral_execution_prompt", {}).get("properties", {})
            .get("prompt_layer", {}).get("const") != "NEUTRAL_EXECUTION_PROMPT"
        ):
            errors.append("provider_prompt schema lacks NEUTRAL_EXECUTION_PROMPT definition")
        if (
            provider_schema.get("properties", {}).get("prompt_layer", {}).get("const")
            != "PROVIDER_COMPILED"
        ):
            errors.append("provider_prompt root must be PROVIDER_COMPILED")
        if not {
            "prompt_layer", "master_prompt_id", "provider_registry_id",
            "reference_ids", "source_spec_version",
        } <= set(provider_schema.get("required", [])):
            errors.append(
                "provider_prompt schema does not require the base compiled binding chain"
            )
        binding_branches = (
            provider_schema.get("allOf", [{}])[0].get("oneOf", [])
            if provider_schema.get("allOf") else []
        )
        branch_required = {
            frozenset(branch.get("required", []))
            for branch in binding_branches
            if isinstance(branch, dict)
        }
        if not {
            frozenset({"provider_neutral_draft_id"}),
            frozenset({"transform_plan_id", "neutral_execution_prompt_id"}),
        } <= branch_required:
            errors.append(
                "provider_prompt schema lacks the DRAFT or TRANSFORM_PLAN/NEP binding branch"
            )
        schema_pairs = {
            "decision": "decision.schema.json",
            "evidence": "evidence.schema.json",
            "artifact": "artifact.schema.json",
            "provider_prompt": "provider_prompt.schema.json",
            "stage_result": "stage_result.schema.json",
            "workflow_status": "workflow_status.schema.json",
            "gate_requirement": "gate_requirement.schema.json",
            "gate": "gate.schema.json",
            "observation": "observation.schema.json",
            "repair": "repair.schema.json",
            "learning": "learning.schema.json",
            "provider": "provider.schema.json",
            "publication": "publication.schema.json",
            "canonical_duration": "canonical_duration.schema.json",
            "asset_registry": "asset_registry.schema.json",
            "shot_plan": "shot_plan.schema.json",
            "protected_unknown": "protected_unknown.schema.json",
            "quantity_semantics": "quantity_semantics.schema.json",
            "causal_boundary": "causal_boundary.schema.json",
            "baseline_spec": "baseline_spec.schema.json",
            "pilot_assessment": "pilot_assessment.schema.json",
            "state_cleanup": "state_cleanup.schema.json",
            "project_route": "project_route.schema.json",
            "task_record": "task_record.schema.json",
            "execution_receipt": "execution_receipt.schema.json",
            "fourfold_preflight": "fourfold_preflight.schema.json",
            "minor_safety": "minor_safety.schema.json",
            "dialogue_inventory": "dialogue_inventory.schema.json",
            "tts_coverage": "tts_coverage.schema.json",
            "subtitle_cue": "subtitle_cue.schema.json",
            "prompt_quality": "prompt_quality.schema.json",
        }
        embedded_defs = project_schema.get("$defs", {})
        for definition_name, schema_name in schema_pairs.items():
            external = json.loads(
                (root / "schemas" / schema_name).read_text(encoding="utf-8-sig")
            )
            canonical = {
                key: value
                for key, value in external.items()
                if key not in {"$schema", "title"}
            }
            embedded_canonical = remap_embedded_local_refs(canonical, definition_name)
            if embedded_defs.get(definition_name) != embedded_canonical:
                errors.append(
                    f"project_state $defs/{definition_name} is out of sync with {schema_name}"
                )
        for schema_path in sorted((root / "schemas").glob("*.schema.json")):
            document = json.loads(schema_path.read_text(encoding="utf-8-sig"))
            for ref in iter_refs(document):
                if not ref.startswith("#/"):
                    errors.append(
                        f"schema uses non-standalone external $ref: {schema_path.name}: {ref}"
                    )
                    continue
                try:
                    resolve_local_ref(document, ref)
                except (KeyError, IndexError, ValueError, TypeError):
                    errors.append(
                        f"unresolved local $ref in {schema_path.name}: {ref}"
                    )
    except (OSError, json.JSONDecodeError):
        pass

    if surface == "source":
        try:
            from build_onefile import (  # source-only development dependency
                BASE_PROFILE_SOURCES, BUILD as ONEFILE_BUILD,
                DEFAULT_PROFILE as ONEFILE_DEFAULT_PROFILE,
                DISPLAY_NAME as ONEFILE_DISPLAY_NAME,
                PROFILE_SOURCES, VERSION as ONEFILE_VERSION,
                profile_sources_for_root, render,
            )
        except (ImportError, OSError) as exc:
            errors.append(f"source ONEFILE builder unavailable: {exc}")
        else:
            if (ONEFILE_VERSION, ONEFILE_BUILD, ONEFILE_DISPLAY_NAME, ONEFILE_DEFAULT_PROFILE) != (
                VERSION, BUILD, DISPLAY_NAME, DEFAULT_PROFILE,
            ):
                errors.append("source ONEFILE builder release identity is stale")
            if tuple(PROFILE_SOURCES) != PROFILE_ORDER:
                errors.append("source ONEFILE profile order is stale")
            expected_profiles = profile_sources_for_root(root)
            if PROFILE_SOURCES != expected_profiles:
                errors.append("ONEFILE profiles do not match the registry dependency closure")
            if PROFILE_SOURCES.get("FULL") != expected_profiles.get("FULL"):
                errors.append("FULL profile is not the complete operational dependency closure")

            entries_by_path = {
                entry.get("path"): entry
                for entry in route_registry.get("entries", [])
                if isinstance(entry, dict) and isinstance(entry.get("path"), str)
            }
            for profile, sources in PROFILE_SOURCES.items():
                source_set = set(sources)
                for source in sources:
                    entry = entries_by_path.get(source, {})
                    for dependency in entry.get("dependencies", []):
                        dependency_entry = entries_by_path.get(dependency, {})
                        if dependency_entry.get("model_readable") is True and dependency not in source_set:
                            errors.append(
                                f"E_PROFILE_DEPENDENCY: {profile} omits {dependency} required by {source}"
                            )

            full_excluded = {
                "00_READ_ME_FIRST.md",
                "VERSION_NOTES.md",
                "references/THIRD_PARTY_ATTRIBUTIONS.md",
            }
            full_required = {
                path
                for path, entry in entries_by_path.items()
                if path not in full_excluded
                and entry.get("model_readable") is True
            }
            if omissions := full_required - set(PROFILE_SOURCES.get("FULL", ())):
                errors.append("FULL profile omits operational sources: " + ", ".join(sorted(omissions)))

            text_only_contract = "references/TEXT_ONLY_ECO_WORKFLOW.md"
            for profile in ("TEXT_ONLY_ECO", "LONGFORM", "FULL"):
                if text_only_contract not in PROFILE_SOURCES.get(profile, ()):
                    errors.append(f"{profile} profile omits the text-only ECO contract")
            for profile in ("MANGA_CORE", "AUX", "MEDIA_RELEASE"):
                if text_only_contract in PROFILE_SOURCES.get(profile, ()):
                    errors.append(f"{profile} profile leaks the text-only ECO contract")
            if PROFILE_SOURCES.get("TEXT_ONLY_ECO") != ("SKILL.md", text_only_contract):
                errors.append("TEXT_ONLY_ECO must contain only SKILL.md and the ECO contract")

            rich_copy_contract = "references/SCRIPT_AND_DIALOGUE_WRITING_ENGINE.md"
            for profile in ("MANGA_CORE", "LONGFORM", "AUX", "FULL"):
                if rich_copy_contract not in PROFILE_SOURCES.get(profile, ()):
                    errors.append(f"{profile} profile omits the narrative copywriting contract")
            for profile in ("TEXT_ONLY_ECO", "MEDIA_RELEASE"):
                if rich_copy_contract in PROFILE_SOURCES.get(profile, ()):
                    errors.append(f"{profile} profile unexpectedly loads the narrative copywriting contract")

            continuum_contract = "references/ALPHA7_CONTINUUM_CREATIVE_FIDELITY_ENGINE.md"
            for profile in ("MANGA_CORE", "LONGFORM", "AUX", "FULL"):
                if continuum_contract not in PROFILE_SOURCES.get(profile, ()):
                    errors.append(f"{profile} profile omits the CONTINUUM creative-fidelity contract")
            for profile in ("TEXT_ONLY_ECO", "MEDIA_RELEASE"):
                if continuum_contract in PROFILE_SOURCES.get(profile, ()):
                    errors.append(f"{profile} profile unexpectedly loads the CONTINUUM creative-fidelity contract")

            forbidden_roots = ("tests/", "schemas/", "scripts/", "benchmark/")
            markers = (
                "SILVER_SHOWRUNNER_READ_MODE: ONEFILE_ONLY",
                "DO_NOT_LOAD_SOURCE_MODULES_WITH_THIS_ONEFILE: true",
                "互斥读取规则", "不得再加载 `SKILL.md`", "Source / SHA-256 Index",
            )
            for profile, sources in PROFILE_SOURCES.items():
                if len(sources) != len(set(sources)):
                    errors.append(f"ONEFILE profile contains duplicate sources: {profile}")
                for source in sources:
                    if source.startswith(forbidden_roots):
                        errors.append(f"ONEFILE includes forbidden source: {profile}: {source}")
                    if not (root / source).is_file():
                        errors.append(f"ONEFILE source missing: {profile}: {source}")
                try:
                    onefile_text = render(root, profile)
                except (KeyError, OSError, UnicodeError) as exc:
                    errors.append(f"ONEFILE cannot be rendered: {profile}: {exc}")
                    continue
                for marker in markers:
                    if marker not in onefile_text:
                        errors.append(f"ONEFILE omits marker: {profile}: {marker}")
                if f"<!-- PROFILE: {profile} -->" not in onefile_text:
                    errors.append(f"ONEFILE profile marker mismatch: {profile}")
                for source in sources:
                    if onefile_text.count(f"<!-- SOURCE: {source} -->") != 1:
                        errors.append(f"ONEFILE source marker mismatch: {profile}: {source}")
                if onefile_text.count("<!-- SOURCE_SHA256: ") != len(sources):
                    errors.append(f"ONEFILE source hashes mismatch: {profile}")

            manga_forbidden = {
                "references/TEXT_ONLY_ECO_WORKFLOW.md",
                "references/ON_DEMAND_RESEARCH_ROUTER.md",
                "references/EVIDENCE_PROVIDER_RELEASE_LEARNING_CONTRACT.md",
                "references/ALPHA7_MEDIA_EXECUTION_AND_EDITING.md",
                "references/ALPHA7_CHINESE_COPY_AND_FOURFOLD_PREFLIGHT.md",
                "04_EVIDENCE_TREND_VIRAL_INTELLIGENCE.md",
                "engines/05_ARTIFACT_SIMULATION_AND_COMMIT.md",
                "engines/09_STRUCTURAL_PREMORTEM.md",
                "phases/01_GREENLIGHT_MARKET_CREATIVE_DIRECTION.md",
                "phases/14_POST_PRODUCTION.md", "phases/15_PACKAGING_COMPLIANCE_RELEASE.md",
                "phases/16_PERFORMANCE_LEARNING.md",
            }
            if leakage := manga_forbidden & set(PROFILE_SOURCES["MANGA_CORE"]):
                errors.append("MANGA_CORE leaks optional sources: " + ", ".join(sorted(leakage)))

    required_runtime_files = (
        "engines/10_EXECUTION_ORCHESTRATOR.md",
        *RUNTIME_ADDED_FILES,
        "scripts/compile_prompt_sections.py",
        "scripts/continuum_creative_preflight.py",
        "scripts/validate_production_control.py",
        "scripts/select_runtime_modules.py",
        "scripts/validate_package.py",
        "scripts/validate_state.py",
        "scripts/prepare_longform_authoring.py",
        "scripts/finalize_longform_contract.py",
        "scripts/validate_longform_contract.py",
        "scripts/build_media_timeline.py",
        "scripts/media_preflight.py",
        "scripts/render_media_ffmpeg.py",
        "scripts/fourfold_preflight.py",
    )
    required_source_files = (
        "VERSION_NOTES.md",
        "scripts/build_onefile.py",
        "scripts/build_release.py",
        "scripts/sync_embedded_schemas.py",
        "tests/legacy_generation_migration_suite.py",
        "tests/longform_selftest_support.py",
        "tests/run_alpha7_fixtures.py",
        "tests/run_alpha7_orchestration_tests.py",
        "tests/run_longform_interface_tests.py",
        "tests/run_longform_compatibility_tests.py",
        *SOURCE_ADDED_TESTS,
        "tests/fixtures/legacy_generation_valid_simulation_state.json",
        "tests/fixtures/alpha7_valid_review_state.json",
        "tests/ALPHA7_RUNTIME_REGRESSION_TESTS.md",
        "tests/ALPHA7_ORCHESTRATION_EXECUTION_TESTS.md",
        "tests/ALPHA7_LONGFORM_INTEGRATION_TESTS.md",
        "tests/ALPHA7_MEDIA_PIPELINE_TESTS.md",
        "tests/ALPHA7_FOURFOLD_PREFLIGHT_TESTS.md",
        "tests/CONTEXT_ROUTING_TESTS.md",
        "tests/PROMPT_SECTION_COMPILER_TESTS.md",
        "tests/MASTER_NATURAL_LANGUAGE_TESTS.md",
    )
    for relative in required_runtime_files:
        if not (root / relative).is_file():
            errors.append(f"required integrated runtime file missing: {relative}")
    if surface == "source":
        for relative in required_source_files:
            if not (root / relative).is_file():
                errors.append(f"required source-only validation file missing: {relative}")

    launcher_cmd_path = root / "运行银幕总控.cmd"
    if launcher_cmd_path.is_file():
        launcher_bytes = launcher_cmd_path.read_bytes()
        launcher_cmd_text = launcher_bytes.decode("utf-8")
        if launcher_bytes.count(b"\n") != launcher_bytes.count(b"\r\n"):
            errors.append("Windows launcher must use CRLF line endings")
        for marker in (
            "SILVER_PYTHON",
            "codex-primary-runtime",
            ".workbuddy\\binaries\\python\\versions",
            "py.exe", "python3.exe", "python.exe",
            "sys.version_info[:2] >= (3, 10)",
            "PYTHONDONTWRITEBYTECODE",
            "runtime_launcher.py",
        ):
            if marker not in launcher_cmd_text:
                errors.append(f"portable Windows launcher missing marker: {marker}")

    runtime_launcher_path = root / "scripts/runtime_launcher.py"
    if runtime_launcher_path.is_file():
        runtime_launcher_text = runtime_launcher_path.read_text(encoding="utf-8-sig")
        for marker in (
            '"准备": "prepare_longform_authoring.py"',
            '"创作预检": "continuum_creative_preflight.py"',
            '"制作检查": "validate_production_control.py"',
            '"检查": ("check_argv"',
            '"提交": ("commit_argv"',
            '"重新准备": ("reprepare_argv"',
            "subprocess.run(",
            'environment["PYTHONDONTWRITEBYTECODE"] = "1"',
            "def _validate_prepare_run_number(",
            "本轮编号写法不对。请写成大写 RUN 加阿拉伯数字，例如 RUN001。",
        ):
            if marker not in runtime_launcher_text:
                errors.append(f"runtime launcher missing frozen marker: {marker}")

    selector_path = root / "scripts/select_runtime_modules.py"
    if selector_path.is_file():
        selector_text = selector_path.read_text(encoding="utf-8-sig")
        for marker in (
            'SELECTOR_READ_MODE = "MODULAR_ONLY"',
            'REGISTRY_RELATIVE = "schemas/runtime_route_registry.json"',
            'EXPECTED_REGISTRY_SCHEMA = "alpha7-master-runtime-route-registry-v1"',
            '"--delivery-mode"',
            '"TEXT_ONLY_ECO_TEST"',
            '"--budget-profile"',
            '"SPLIT_REQUIRED"',
            "looks_like_onefile_content",
        ):
            if marker not in selector_text:
                errors.append(f"runtime selector missing registry/read-mode marker: {marker}")
        for forbidden_mapping in ("TASK_MODULES =", "FACTUAL_TYPES ="):
            if forbidden_mapping in selector_text:
                errors.append(
                    f"runtime selector retains a second routing source: {forbidden_mapping}"
                )

    prepare_path = root / "scripts/prepare_longform_authoring.py"
    if prepare_path.is_file():
        prepare_text = prepare_path.read_text(encoding="utf-8-sig")
        for marker in (
            'AUTHORING_VERSION = "alpha7-longform-authoring-1.5"',
            'AUTHORING_GUIDE_VERSION = "alpha7-overlay-guide-1.5"',
            '"alpha7-longform-authoring-1.4"',
            '"alpha7-overlay-guide-1.4"',
            'DIRECTOR_SCAFFOLD_VERSION = "alpha7-director-scaffold-1.1"',
            '"locked_director_scaffold"',
            '"single_shot_eligibility"',
            '"action_additions"',
            'IN_PLACE_COMMIT_MODE = "IN_PLACE_THREE_CARRIER_V1"',
            '"authoring_guide"',
            '"authoring_workflow"',
            '"reprepare_argv"',
            '"runtime_identity"',
            '"source_read_scope_attestation"',
            '"quote_assignments"',
            "runtime_helper_scripts_sha256",
            '"semantic_gate"',
            "SOURCE_LOCKED_NONLEXICAL",
            "E_OUTPUT_TARGET_NOT_EMPTY",
            "E_REPREPARE_SCOPE",
            '"MACHINE_REPRESENTATIVE_V1"',
            '"--output-dir"',
            '"--package-name"',
            "E_TEMP_ROOT_CONTRACT",
            '"--overlays-output"',
            '"--self-test"',
            "run_self_test",
        ):
            if marker not in prepare_text:
                errors.append(f"longform prepare helper missing frozen 1.5 marker: {marker}")

    finalizer_path = root / "scripts/finalize_longform_contract.py"
    if finalizer_path.is_file():
        finalizer_text = finalizer_path.read_text(encoding="utf-8-sig")
        for marker in (
            'AUTHORING_VERSION = "alpha7-longform-authoring-1.5"',
            'AUTHORING_GUIDE_VERSION = "alpha7-overlay-guide-1.5"',
            '"locked_director_scaffold"',
            '"locked_scaffold_sha256"',
            '"action_additions"',
            '"--overlays"',
            '"--check-overlays"',
            '"source_read_scope_attestation"',
            '"execution_beats"',
            '"quote_assignments"',
            "_runtime_helper_scripts_sha256",
            "semantic_gate_findings",
            "render_copyable_execution_surface",
            'VISIBLE_QUOTE_TITLE = "【本镜必须保留的发声与画面文字】"',
            "E_SOURCE_READ_SCOPE",
            '"structural_validation_status"',
            '"content_self_review_status"',
            '"editorial_review_status"',
            '"content_readiness"',
            '"quality_scope"',
            "E_TEMP_ROOT_CONTRACT",
            "E_AUTHORING_GUIDE_TAMPER",
            "E_OVERLAY_CHECK_FAILED",
            "E_NO_DELETE_COMMIT_REQUIRES_NEW_PATH",
            "E_REPREPARE_REQUIRED",
            "E_SEMANTIC_CLAIM_LOCK",
            '"### 剧情拆解"',
            "copy_prompt = render_copyable_execution_surface",
            '"### 分镜总览"',
            '"--self-test"',
            "run_self_test",
        ):
            if marker not in finalizer_text:
                errors.append(f"longform finalizer missing frozen 1.5 marker: {marker}")

    longform_validator_path = root / "scripts/validate_longform_contract.py"
    if longform_validator_path.is_file():
        validator_text = longform_validator_path.read_text(encoding="utf-8-sig")
        for marker in (
            'CONTRACT_VERSION = "alpha7-longform-1.5"',
            'V14_CONTRACT_VERSION = "alpha7-longform-1.4"',
            'R9_CONTRACT_VERSION = "alpha7-longform-1.3"',
            'DIRECTOR_SCAFFOLD_VERSION = "alpha7-director-scaffold-1.1"',
            'V14_DIRECTOR_SCAFFOLD_VERSION = "alpha7-director-scaffold-1.0"',
            'IN_PLACE_COMMIT_MODE = "IN_PLACE_THREE_CARRIER_V1"',
            "E_RUNTIME_IDENTITY", "E_OUTPUT_COMMIT_MODE",
            "E_UNCONFIRMED_SOURCE_INTERPRETATION", "E_OUT_OF_WINDOW_PLOT_ACTION",
            "E_POV_OBSERVER_CONFLICT", "E_CAMERA_MOTION_CONFLICT",
            "E_UNSOURCED_VOICE", "E_PUNCTUATION_COLLISION",
            "E_PROPOSAL_CONTROL", "E_EXECUTION_BEAT", "E_THIN_SINGLE_SHOT",
            "E_CONTENT_SELF_REVIEW_COMPUTED", "E_SOURCE_ACTION_LOCK",
            "E_ROUTE_FINDING", "E_ROUTE_SPLIT_REQUIRED",
            "E_SINGLE_SHOT_ROUTE", "E_SINGLE_SHOT_EXECUTION_COVERAGE",
            "E_AUTHORING_SCAFFOLD_TAMPER", '"HELPER_DERIVED"',
            "E_QUOTE_ASSIGNMENT", "E_NON_LEXICAL_VOCALIZATION_SPEAKER",
            "E_CROSS_SHOT_GLOBAL_SOUND", "E_VISIBLE_QUOTE_VOICE_COVERAGE",
            "E_SHOT_DURATION_OVERFLOW",
            "expected_semantic_gate", "E_SEMANTIC_FUTURE_REVELATION",
            "semantic_compare_text", "_semantic_is_default_ignorable",
            "E_SEMANTIC_ACTION_TOOL", "E_SOURCE_AUDIO_COVERAGE",
            "E_QUOTED_TEXT_AUDIO_ROUTE",
            'COPYABLE_EXECUTION_TITLE = "### 逐镜视频提示词（每条可单独复制）"',
        ):
            if marker not in validator_text:
                errors.append(f"longform validator missing frozen 1.5 marker: {marker}")

    migrate_path = root / "scripts/migrate_longform_contract.py"
    if migrate_path.is_file():
        migrate_text = migrate_path.read_text(encoding="utf-8-sig")
        for marker in (
            "READ_ONLY_CONTRACT_VERSIONS",
            '"target_contract_version": CONTRACT_VERSION',
            '"target_authoring_version": AUTHORING_VERSION',
            '"target_guide_version": AUTHORING_GUIDE_VERSION',
            '"review_required": True',
            "assert_fresh_v15_migration",
            "E_MIGRATION_STATUS_INHERITANCE",
            "E_MIGRATION_V15_SCAFFOLD",
            "E_MIGRATION_CREATIVE_INHERITANCE",
        ):
            if marker not in migrate_text:
                errors.append(f"longform migration helper missing frozen 1.5 marker: {marker}")

    for module_dir in ("engines", "phases"):
        for path in sorted((root / module_dir).glob("*.md")):
            module_text = path.read_text(encoding="utf-8-sig")
            if not re.search(r"[\u3400-\u4DBF\u4E00-\u9FFF]", module_text):
                errors.append(f"Chinese-first module has no Chinese text: {path.relative_to(root).as_posix()}")
            in_fence = False
            for line_number, line in enumerate(module_text.splitlines(), start=1):
                if line.strip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence or re.search(r"[\u3400-\u4DBF\u4E00-\u9FFF]", line):
                    continue
                plain = line.strip().lstrip("#>-* ")
                if plain.startswith("`") and plain.endswith("`"):
                    continue
                words = re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", plain)
                machine_tokens = re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b|`[^`]+`|https?://\S+", plain)
                if len(words) >= 6 and len(machine_tokens) < len(words) / 2:
                    errors.append(
                        f"creator-facing English-only paragraph in {path.relative_to(root).as_posix()}:{line_number}"
                    )

    forbidden = re.compile(r"\b(TODO|TBD|PLACEHOLDER)\b", flags=re.IGNORECASE)
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative.startswith("scripts/") or relative.startswith("tests/"):
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if forbidden.search(text):
            errors.append(f"placeholder token found in {relative}")

    if errors:
        print(f"FAIL: {len(errors)} package validation error(s)")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        f"PASS: surface={surface}; source-visible={len(files)}; "
        f"runtime-payload={len(runtime_files)}; JSON, metadata and runtime contracts valid"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
