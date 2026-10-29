#!/usr/bin/env python3
"""Build explicit-allowlist Skill archives without reading local account data."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FILES = ("SKILL.md", "README.md", "LICENSE", "agents/openai.yaml")
SOURCE_FILES = FILES + (".gitignore", "scripts/build_release.py")


def scalar(value):
    return json.dumps(value, ensure_ascii=False)


def skill_data():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.fullmatch(r"---\r?\n(.*?)\r?\n---\r?\n(.*)", text, re.S)
    if match is None:
        raise ValueError("SKILL.md must contain YAML frontmatter")
    header, body = match.groups()
    name_match = re.search(r"^name:\s*([a-z0-9-]+)\s*$", header, re.M)
    desc_match = re.search(r"^description:\s*(.+)$", header, re.M)
    version_match = re.search(r'^\s+version:\s*"([0-9]+\.[0-9]+\.[0-9]+)"\s*$', header, re.M)
    if not all((name_match, desc_match, version_match)):
        raise ValueError("Missing skill name, single-line description or metadata.version")
    return name_match.group(1), desc_match.group(1), version_match.group(1), text, body


def workbuddy_skill(name, description, version, body):
    fields = {
        "name": name,
        "display_name": "基金从业培训学习助手",
        "display_name_en": "Fund Training Learning Assistant",
        "description": description,
        "description_zh": "辅助本人观看培训视频、确认绿勾后自动切换，测验自行作答与提交。",
        "description_en": "Assist learners with course navigation, normal playback and verified video transitions; learners answer and submit quizzes themselves.",
        "version": version,
        "author": "fund-training-assistant contributors",
    }
    header = "\n".join(f"{key}: {scalar(value)}" for key, value in fields.items())
    return f"---\n{header}\n---\n{body}"


def build(output):
    name, description, version, skill, body = skill_data()
    payloads = {}
    for relative in SOURCE_FILES:
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing file or symbolic link not allowed: {relative}")
        payloads[relative] = path.read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in ("standard", "workbuddy", "source"):
        archive = output / f"{name}-{variant}-v{version}.zip"
        if archive.exists():
            raise FileExistsError(f"Refusing to replace an existing archive: {archive.name}")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            for relative, content in payloads.items():
                if variant != "source" and relative not in FILES:
                    continue
                if variant == "workbuddy" and relative == "agents/openai.yaml":
                    continue
                if variant == "workbuddy" and relative == "SKILL.md":
                    content = workbuddy_skill(name, description, version, body).encode("utf-8")
                info = zipfile.ZipInfo(f"{name}/{relative}", date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                handle.writestr(info, content)
        with zipfile.ZipFile(archive) as handle:
            if handle.testzip() is not None:
                raise ValueError(f"Corrupt archive: {archive.name}")
        results.append((archive.name, hashlib.sha256(archive.read_bytes()).hexdigest()))
    checksums = output / "SHA256SUMS.txt"
    if checksums.exists():
        raise FileExistsError("Refusing to replace an existing checksum file")
    checksums.write_text("".join(f"{digest}  {filename}\n" for filename, digest in results), encoding="utf-8")
    for filename, digest in results:
        print(f"{filename}  {digest}")
    print(checksums.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    arguments = parser.parse_args()
    build(arguments.output.resolve())
