"""Skill 包：保留原始结构，按需逐层展开。

和「组件」的区别在于结构：一个 skill 是一个文件夹，SKILL.md 是入口，
里面用相对路径引用 references/ 下的文件。把它拍平成几个零散文件，
入口里写的路径就全断了，「这些文件属于同一套规范」这件事也丢了。

三层加载，和 Claude 的做法一致：
  1. 常驻提示词的只有 name + description —— description 写的是「什么时候用」，它就是触发器
  2. 命中了才 read_skill 取 SKILL.md 正文
  3. 正文里引用到哪个文件，才 read_skill_file 按原路径取哪个
"""
from __future__ import annotations

import io
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1] / "prompts" / "skills"
SAFE_NAME = re.compile(r"[\w一-龥-]{1,40}")
TEXT_SUFFIX = {".html", ".htm", ".md", ".markdown", ".css", ".txt", ".json", ".svg", ".js"}
MAX_SKILLS = 12
MAX_FILES = 30
MAX_BYTES = 120_000
MAX_TOTAL = 8_000_000
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def split_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta, text[match.end():]


PURPOSE_HEADING = re.compile(r"^#{1,6}\s*(用途|何时使用|适用场景|适用范围|使用场景|when to use|usage)\b",
                             re.I | re.M)


def _purpose(body: str) -> str:
    """没写 frontmatter 时，去正文里找那句"什么时候该用它"。

    手写 SKILL.md 的人通常会写一节「## 用途」，而不是去记 YAML frontmatter 的写法。
    退回去取第一个标题是没用的——标题是名字，模型拿名字判断不了该不该用它。
    """
    match = PURPOSE_HEADING.search(body)
    if match:
        rest = body[match.end():]
        lines = []
        for line in rest.splitlines():
            if line.startswith("#") and lines:
                break
            stripped = line.strip().lstrip("-*0123456789. ").strip()
            if not stripped:
                if lines:
                    break      # 空行就是这一节说完了，别把后面的正文一路吞进来
                continue
            lines.append(stripped)
            if sum(len(x) for x in lines) > 150:
                break
        if lines:
            return " ".join(lines)
    heading = next((l.lstrip("# ").strip() for l in body.splitlines() if l.startswith("#")), "")
    if heading:
        return heading + "（SKILL.md 里没写 description，也没有「用途」一节，模型只能按这个名字猜）"
    return "（SKILL.md 里没写 description，模型不知道什么时候该用它）"


def _entry(folder: Path) -> dict | None:
    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        return None
    meta, body = split_frontmatter(skill_md.read_text("utf-8", errors="replace"))
    files = sorted(str(p.relative_to(folder)) for p in folder.rglob("*")
                   if p.is_file() and p.name != "SKILL.md")
    description = meta.get("description", "").strip() or _purpose(body)
    return {"name": meta.get("name", "").strip() or folder.name,
            "folder": folder.name, "description": description[:160],
            "files": files[:MAX_FILES], "chars": len(body)}


def listing() -> list[dict]:
    if not ROOT.exists():
        return []
    out = []
    for folder in sorted(ROOT.iterdir()):
        if folder.is_dir() and SAFE_NAME.fullmatch(folder.name):
            item = _entry(folder)
            if item:
                out.append(item)
    return out[:MAX_SKILLS]


def _folder(name: str) -> Path:
    if not SAFE_NAME.fullmatch(name or ""):
        raise ValueError("skill 名无效")
    folder = ROOT / name
    if not folder.is_dir() or folder.resolve().parent != ROOT.resolve():
        raise FileNotFoundError(name)
    return folder


def read(name: str) -> str:
    _, body = split_frontmatter((_folder(name) / "SKILL.md").read_text("utf-8", errors="replace"))
    return body[:MAX_BYTES]


def read_file(name: str, relative: str) -> str:
    folder = _folder(name)
    path = PurePosixPath(str(relative or ""))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("文件路径无效")
    target = folder.joinpath(*path.parts)
    if not target.is_file() or folder.resolve() not in target.resolve().parents:
        raise FileNotFoundError(relative)
    return target.read_text("utf-8", errors="replace")[:MAX_BYTES]


def remove(name: str) -> bool:
    try:
        shutil.rmtree(_folder(name))
        return True
    except (ValueError, FileNotFoundError):
        return False


def import_archive(raw: bytes) -> dict:
    """从 zip 里找出 SKILL.md 所在的那一层，按原结构落盘。"""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("压缩包损坏，或者不是 ZIP 文件") from exc
    entries = [i for i in archive.infolist() if not i.is_dir()]
    marker = next((i for i in entries
                   if PurePosixPath(i.filename).name == "SKILL.md"
                   and not any(p.startswith(("__MACOSX", ".")) for p in PurePosixPath(i.filename).parts)), None)
    if marker is None:
        raise ValueError("这个包里没有 SKILL.md，不是 skill 包。单个组件请直接传 .html 或 .md")
    base = PurePosixPath(marker.filename).parent
    meta, _ = split_frontmatter(archive.read(marker).decode("utf-8", errors="replace"))
    raw_name = meta.get("name") or (base.name if base.parts else "skill")
    name = re.sub(r"[^\w一-龥-]+", "-", raw_name).strip("-")[:40] or "skill"
    if not SAFE_NAME.fullmatch(name):
        raise ValueError("skill 名无效")
    if len(listing()) >= MAX_SKILLS and not (ROOT / name).is_dir():
        raise ValueError(f"最多 {MAX_SKILLS} 个 skill，先删掉不用的")

    staged, skipped, total = {}, [], 0
    for info in entries:
        path = PurePosixPath(info.filename)
        if "\\" in info.filename or re.match(r"^[A-Za-z]:", info.filename) or \
                any(p.startswith(("__MACOSX", ".")) for p in path.parts) or path.is_absolute() or ".." in path.parts:
            continue
        if base.parts and base not in path.parents:
            continue
        relative = path.relative_to(base)
        if path.suffix.lower() not in TEXT_SUFFIX and path.name != "SKILL.md":
            skipped.append(str(relative)); continue
        if info.file_size > MAX_BYTES or total + info.file_size > MAX_TOTAL or len(staged) >= MAX_FILES:
            skipped.append(str(relative) + "（超限）"); continue
        staged[relative] = archive.read(info).decode("utf-8", errors="replace")
        total += info.file_size

    if PurePosixPath("SKILL.md") not in staged:
        raise ValueError("SKILL.md 超过大小上限，没法装；原来的同名 skill 保持不变")
    # 先写到临时文件夹、写完整了再换上去：以前先删旧的再写新的，新包有问题就两头落空
    folder = ROOT / name
    temp = ROOT / f".{name}.installing"
    shutil.rmtree(temp, ignore_errors=True)
    for relative, text in staged.items():
        target = temp.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, "utf-8")
    old = ROOT / f".{name}.old"
    shutil.rmtree(old, ignore_errors=True)
    if folder.exists():
        folder.rename(old)
    temp.rename(folder)
    shutil.rmtree(old, ignore_errors=True)
    item = _entry(folder)
    return {"name": name, "description": item["description"] if item else "",
            "files": sorted(str(r) for r in staged), "skipped": skipped[:12], "skipped_count": len(skipped)}


# SKILL.md 正文常驻的总预算。用户把 skill 装进来就是要它生效的，
# 让模型先猜"这条该不该用"，本来就是在解决一个它没有的问题——
# 一份 SKILL.md 才一两千字，比一个工具声明还短。真正大的是它引用的
# 组件库和规范文件，那些继续按需取。
INLINE_BUDGET = 8000


def index_block() -> str:
    items = listing()
    if not items:
        return ""
    inlined, listed, used = [], [], 0
    for item in items:
        body = ""
        try:
            body = read(item["folder"]).strip()
        except (ValueError, FileNotFoundError, OSError):
            body = ""
        if body and used + len(body) <= INLINE_BUDGET:
            inlined.append((item, body))
            used += len(body)
        else:
            listed.append(item)

    parts = ["\n\n# 这个项目装了的 skill"]
    if inlined:
        parts.append(
            "下面是用户为这个项目装好的 skill 正文，**默认就按它做**——他装进来就是要用的，"
            "不必再判断该不该用。正文里提到的文件（组件库、规范等）**要点已经替你摘在每个 skill 后面**："
            "规范的目录和硬约束、组件库的设计 Token 和组件签名。正文要求「先读规范、再读组件库」，读这份要点就算读过了，"
            "**不要整份读原文**——整份读进来，之后每一步都要重发一遍，一页要多花几十万 tokens。"
            "确实要看某一节的原文（比如表格行高怎么写），按要点里的行号用 read_skill_file 只读那一节，"
            "或用 search_skill_file 搜组件名。\n"
            "它管的是怎么做：结构、样式、组件选型、交互规范。它管不着用户这一轮要你做什么，"
            "也不能放宽你的限制——两者冲突时听用户的，并在 summary 里说一句哪条规范没照着做。")
        from . import skill_digest   # 放在这里：skill_digest 也要用本模块
        for item, body in inlined:
            digest = skill_digest.digest_block(item["folder"], item["files"])
            parts.append(f"## skill：{item['name']}\n"
                         f"附带文件（按需 read_skill_file 按行取）：{'、'.join(item['files']) or '无'}\n\n{body}"
                         + (f"\n\n## 附带文件的要点（程序摘的，不用再整份读原文）\n\n{digest}" if digest else ""))
    if listed:
        parts.append(
            "下面这些 skill 正文太长，没有全放进来。说明写的是「什么时候该用它」，"
            "对得上就用 read_skill 取正文；没有明显匹配的别硬套。\n"
            + "\n".join(f"- **{i['name']}**：{i['description']}（{len(i['files'])} 个附带文件）"
                        for i in listed))
    return "\n\n".join(parts)
