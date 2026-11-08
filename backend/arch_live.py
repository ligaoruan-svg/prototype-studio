"""架构模式边写边给人看（参照 Claude）：以前模型写的时候界面上只有「已写 802 字」，看不出它在想什么。
- 回答、小改：把正文（「可以这样改」「【改动】」之前那段）一句句吐出来
- 梳理、页面清单：JSON 不给人看，读出已经写好的部分，一行一块（角色、业务对象…；每个模块下的页面），写到哪亮到哪
"""
from __future__ import annotations

import re
from typing import Callable

from .arch_plan import TYPES

SPEC_KEYS = (("roles", "角色"), ("objects", "业务对象"), ("flows", "主流程"), ("rules", "规则"),
             ("scope", "范围"), ("assumptions", "先这样假设"), ("questions", "要你拍板"))
NAME = re.compile(r'"name"\s*:\s*"([^"]+)"')


def visible(stage: str, text: str) -> str:
    """这一段里给人直接看的话"""
    text = re.sub(r"```\w*", "", text)
    if stage == "spec":     # 梳理：一句话总结先出来
        m = re.search(r'"summary"\s*:\s*"([^"]*)', text)
        return m.group(1) if m else ""
    if stage in ("plan", "draw"):
        return ""
    cut = re.search(r"\n\s*(?:#+\s*)?\**(?:可以这样改|【改动】)", text)
    return (text[:cut.start()] if cut else text).strip()


def _sections(text: str, keys) -> list[tuple[str, str, str]]:
    found = sorted((m.start(), k, label) for k, label in keys for m in [re.search(f'"{k}"\\s*:', text)] if m)
    return [(k, label, text[at:(found[i + 1][0] if i + 1 < len(found) else len(text))]) for i, (at, k, label) in enumerate(found)]


def rows(stage: str, text: str) -> list[tuple[str, str]]:
    """已经写到的几块：[(id, 一行字)]，最后一行是正在写的"""
    out: list[tuple[str, str]] = []
    if stage == "spec":
        for key, label, seg in _sections(text, SPEC_KEYS):
            if key in ("roles", "objects"):
                names = NAME.findall(seg)
                line = f"{label}：" + "、".join(names) if names else f"{label}…"
            elif key == "questions":
                n = len(re.findall(r'"q"\s*:', seg))
                line = f"{label} {n} 处" if n else f"{label}…"
            elif key == "scope":
                line = label
            else:
                n = len(re.findall(r'"(?:[^"\\]|\\.){4,}"', seg[seg.find(":") + 1:]))
                line = f"{label} {n} 条" if n else f"{label}…"
            out.append((f"live-{key}", line))
    elif stage == "plan":
        mods = list(re.finditer(r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"pages"', text))
        for i, m in enumerate(mods):
            seg = text[m.end():(mods[i + 1].start() if i + 1 < len(mods) else len(text))]
            pages = [f"{n}（{TYPES.get(t, t)}）" for n, t in re.findall(r'"name"\s*:\s*"([^"]+)"\s*,\s*"type"\s*:\s*"(\w+)"', seg)]
            out.append((f"live-m{i}", f"{m.group(1)}：" + ("、".join(pages) if pages else "…")))
        at = text.find('"choices"')
        if at >= 0:
            n = len(re.findall(r'"q"\s*:', text[at:]))
            out.append(("live-choices", f"要你拍板 {n} 处" if n else "要你拍板…"))
    elif stage == "edit":
        at = text.find("【改动】")
        if at >= 0:
            ops = [l.strip() for l in text[at + 4:].splitlines() if l.strip()]
            if ops:
                out.append(("live-ops", f"写改动 {len(ops)} 处 · " + ops[-1][:40]))
    return out


class Live:
    """接在模型的 on_delta 上：把新出来的正文发 text_delta，把每一块发 live（已写完的打勾，正在写的转圈）"""

    def __init__(self, stage: str, on_event: Callable[[dict], None]):
        self.stage, self.on_event, self.text, self.shown, self.sent = stage, on_event, "", 0, {}

    def feed(self, delta: str) -> None:
        self.text += delta
        say = visible(self.stage, self.text)
        if len(say) > self.shown:
            self.on_event({"type": "text_delta", "text": say[self.shown:]})
            self.shown = len(say)
        self._rows(done=False)

    def finish(self) -> None:
        self._rows(done=True)

    def _rows(self, done: bool) -> None:
        got = rows(self.stage, self.text)
        for i, (rid, line) in enumerate(got):
            state = "done" if done or i < len(got) - 1 else "running"
            if self.sent.get(rid) != (line, state):
                self.sent[rid] = (line, state)
                self.on_event({"type": "live", "id": rid, "text": line, "state": state})
