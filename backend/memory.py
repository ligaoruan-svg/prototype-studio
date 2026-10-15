"""项目记忆：跨轮次、跨页面记住用户说过的约定。

对话历史只保留同一页最近若干条，换页就断、超限就静默丢弃，所以同一句偏好会被反复重说。
这里只存用户**明确表达过**的、对整个项目长期有效的约定，随系统提示常驻。
不记推断、不记一次性指令、不记页面内容——那些会迅速把记忆塞满噪音，而用户无从反驳。
"""
from __future__ import annotations

import re
import uuid

from . import storage

MAX_ITEMS = 30
MAX_CHARS = 120


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。、；：,.;:!！?？]+", "", text).lower()


def listing(meta: dict) -> list[dict]:
    return list(meta.get("memory", []))[:MAX_ITEMS]


@storage._locked
def add(project_id: str, note: str) -> dict:
    text = " ".join(str(note or "").split())[:MAX_CHARS]
    if len(text) < 4:
        raise ValueError("要记的内容太短，写成一句完整的约定")
    meta = storage.load_meta(project_id)
    items = meta.setdefault("memory", [])
    key = _normalize(text)
    for item in items:
        if _normalize(item["text"]) == key:
            return {**item, "duplicate": True}
    entry = {"id": "m" + uuid.uuid4().hex[:6], "text": text, "created_at": storage.now_iso()}
    items.append(entry)
    # 满了就挤掉最早的，避免无限增长撑爆提示词
    del items[:-MAX_ITEMS]
    meta["updated_at"] = storage.now_iso()
    storage.save_meta(meta)
    return entry


@storage._locked
def remove(project_id: str, note_id: str) -> bool:
    meta = storage.load_meta(project_id)
    items = meta.get("memory", [])
    kept = [i for i in items if i["id"] != note_id]
    if len(kept) == len(items):
        return False
    meta["memory"] = kept
    meta["updated_at"] = storage.now_iso()
    storage.save_meta(meta)
    return True


# 「以后」「一律」「统一」「别再」这类说法：多半是长期约定。只用来提醒 AI 判断，记不记由它定
RULE_HINT = re.compile(r"以后|今后|往后|一律|统一|每次|始终|总是|一直用|都要|都用|都改成|都按|全部按|默认|别再|不要再|不许|禁止|记住|规范是|风格是")


def looks_like_rule(text: str) -> bool:
    return bool(RULE_HINT.search(str(text or "")))


HOW_TO = ("用户说了以后都算数的约定（「按钮一律用描边」「表格都带斑马纹」「别再用渐变」），"
          "照做之外调 remember 记下来（一次一条，用你自己的话写成一句），以后这个项目的所有页面都照这个来。"
          "只记他明确说过、以后还算数的；一次性的指令、你的推测、页面里的内容都不要记。"
          "他说不用再守某条时，调 forget 传对应的 [id]。")


def index_block(meta: dict) -> str:
    """挂进系统提示的一段。

    以前没有记忆时整段不出现——连「什么时候该记」的说明也一起没了，于是永远记不下第一条。
    """
    items = listing(meta)
    if not items:
        return "\n\n# 项目记忆\n\n这个项目还没有记住的约定。" + HOW_TO
    lines = "\n".join(f"- [{i['id']}] {i['text']}" for i in items)
    return ("\n\n# 这个项目记住的约定\n\n用户之前说过下面这些，对整个项目长期有效，不必再问一遍，"
            "改动时默认遵守；和这轮的要求冲突时以这轮为准，并在 summary 里提一句：\n\n"
            + lines + "\n\n" + HOW_TO)
