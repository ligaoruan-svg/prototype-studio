"""skill 附带文件的「要点」和「页面外壳」。

以前 AI 做页面时把规范（1.7 万字）和组件库（4.5 万字）整份读进对话，之后每一步都连同这 6 万多字
重新发一遍——一页 8 分钟、52 万输入 tokens，大头都在这里。现在：

- 要点：每个附带文件第一次用时，程序（不用模型、不花钱）摘一份几千字的要点——
  规范摘目录和带【必须】/禁止的硬约束，组件库摘设计 Token 和组件函数的签名。
  要点常驻系统提示，AI 不必再整份读；要看某一节的原文，按行号去读那一节。
- 外壳：skill 里如果有「页面外壳」（样式、布局、菜单、路由、弹窗、Toast 都现成），
  新页面直接从它起步，由程序整份复制，AI 只写这一页的菜单、内容和交互。
要点按文件修改时间缓存，规范改了会自动重摘。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import skills

MD_LIMIT = 5200
HTML_LIMIT = 3600
SHELL_NAME = re.compile(r"(外壳|shell)\.html?$", re.I)
_cache: dict[str, tuple[float, str]] = {}


def _md_digest(text: str) -> str:
    lines = text.splitlines()
    outline, rules, seen = [], [], set()
    for i, line in enumerate(lines, 1):
        s = line.strip()
        m = re.match(r"^(#{1,3})\s+(.+)", s)
        if m:
            title = re.sub(r"[*`]", "", m.group(2)).strip()
            outline.append(f"{'  ' * (len(m.group(1)) - 1)}- {title}（第 {i} 行）")
            continue
        if re.search(r"【必须】|必须|禁止|不得|严禁|硬约束", s) and 6 <= len(s) <= 220:
            clean = re.sub(r"^[-*\d.)\s]+", "", re.sub(r"[*`]", "", s)).strip()
            key = re.sub(r"\W", "", clean)[:40]
            if clean and key not in seen:
                seen.add(key)
                rules.append(f"- {clean[:150]}")
    out = "目录（要看原文就按行号读那一节）：\n" + "\n".join(outline[:70])
    if rules:
        out += "\n\n硬约束（原文摘句）：\n" + "\n".join(rules)
    return out[:MD_LIMIT]


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", s)[:140]


def _html_digest(text: str) -> str:
    parts = []
    root = re.search(r":root\s*\{([^}]*)\}", text)
    if root:
        tokens = re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root.group(1))
        if tokens:
            parts.append("设计 Token（:root）：" + "；".join(f"{k}:{v.strip()}" for k, v in tokens[:60]))
    sigs = []
    for m in re.finditer(r"(?m)^\s{0,4}([A-Za-z_$][\w$]*)\s*:\s*\(([^)]*)\)\s*=>", text):
        if not m.group(1).startswith("_"):
            sigs.append(m.group(1) + "(" + _flat(m.group(2)) + ")")
    for m in re.finditer(r"(?m)^(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*\(([^)]*)\)\s*=>", text):
        sigs.append(m.group(1) + "(" + _flat(m.group(2)) + ")")
    for m in re.finditer(r"(?m)^function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)", text):
        sigs.append(f"function {m.group(1)}({m.group(2)[:100]})")
    if sigs:
        parts.append("现成的组件和函数（签名）：\n" + "\n".join(f"- {s}" for s in dict.fromkeys(sigs)))
    classes = re.findall(r"(?m)^\s*\.([a-z][\w-]*)\s*[{,:]", text)
    if classes:
        parts.append("主要样式类：" + "、".join(list(dict.fromkeys(classes))[:80]))
    return "\n\n".join(parts)[:HTML_LIMIT]


def file_digest(skill: str, relative: str) -> str:
    folder = skills._folder(skill)
    path = folder / relative
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ""
    key = f"{skill}/{relative}"
    hit = _cache.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    text = path.read_text("utf-8", errors="replace")
    digest = _md_digest(text) if path.suffix.lower() in {".md", ".txt"} else _html_digest(text) if path.suffix.lower() in {".html", ".htm"} else ""
    _cache[key] = (mtime, digest)
    return digest


def digest_block(skill: str, files: list[str]) -> str:
    """系统提示里给这个 skill 的附带文件附上的要点。外壳文件不摘（它整份由程序复制）。"""
    parts = []
    for rel in files:
        if SHELL_NAME.search(rel) or rel.lower() == "readme.md":
            continue
        d = file_digest(skill, rel)
        if d:
            parts.append(f"### {rel} 的要点\n{d}")
    return "\n\n".join(parts)


def find_shell() -> tuple[str, str, str] | None:
    """装了的 skill 里第一个「页面外壳」：(skill 名, 相对路径, 内容)。"""
    for item in skills.listing():
        for rel in item.get("files", []):
            if SHELL_NAME.search(rel):
                try:
                    return item["folder"], rel, skills.read_file(item["folder"], rel)
                except (ValueError, FileNotFoundError, OSError):
                    continue
    return None


def outline(text: str) -> list[str]:
    """大文件的目录：标题和行号，给「整份读」的请求代替原文"""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^\s*(#{1,3})\s+(.+)", line)
        if m:
            out.append(f"第 {i} 行：{re.sub(r'[*`]', '', m.group(2)).strip()[:60]}")
    return out[:80]


if __name__ == "__main__":   # 手动看看摘出来什么样：python -m backend.skill_digest
    for item in skills.listing():
        print(json.dumps(item["files"], ensure_ascii=False))
        print(digest_block(item["folder"], item["files"]))
