"""给 AI 的「源码地图」：少翻几轮源码就能动手。

实测一页生成 23 轮里有 16 轮只在读：搜一个名字 → 看到行号 → 再搜下一个，每一轮都把前面所有内容重发一遍。
这里做四件事，都是为了让它第一眼就知道去哪、改完知道落在哪：
- code_map：页面里每个函数、页面方法、数据、交互绑定在第几行（只给名字和行号，不给正文）
- prefetch：用户这轮点名的函数、报错里的名字、点选的位置，程序先在源码里找出来，随第一条消息给它
- changes_view：改完以后新代码落在哪几行、后面的行号挪了多少，不用再搜一遍核对
- snip_line：原型的脚本常常一行就是一整个函数（两三千字），搜索结果只展开命中的那一段，旁边的行只给开头
"""
from __future__ import annotations

import difflib
import re

LONG_LINE = 800        # 比这长的一行，地图上标出字数：它多半是一整个函数
HIT_FULL = 1500        # 命中的那一行不超过这么长就整行给，再长只给命中附近
HIT_WINDOW = 500       # 只给命中附近时，左右各给多少字
NEIGHBOR = 160         # 命中行上下的邻居行，只给开头这么多字
MAP_CAP = 4000         # 代码地图最多这么多字
PREFETCH_CAP = 6000    # 预取片段最多这么多字


def snip_line(line: str, query: str = "", full: int = HIT_FULL, window: int = HIT_WINDOW) -> str:
    """一行源码的展示：短的整行，长的只给命中附近，并说清楚截掉了（免得把截断的样子当原文去做补丁）"""
    if len(line) <= full:
        return line
    at = line.lower().find(query.lower()) if query else -1
    if at < 0:
        return line[:full] + f"…［这一行共 {len(line)} 字，后面省略；要整行就 read_source_slice 读这一行］"
    a, b = max(0, at - window), min(len(line), at + len(query) + window)
    return (("…" if a else "") + line[a:b] + ("…" if b < len(line) else "")
            + f"［这一行共 {len(line)} 字，只给了第 {a + 1}–{b} 字；要整行就 read_source_slice 读这一行］")


def neighbor_line(line: str) -> str:
    return line if len(line) <= NEIGHBOR + 40 else line[:NEIGHBOR] + f"…［截断，共 {len(line)} 字］"


def context_chunks(lines: list[str], hits: list[int], query: str = "", radius: int = 4, cap: int = 8000,
                   queries: dict[int, str] | None = None) -> str:
    """把命中的几行连同上下几行拼成片段：命中行给全（或命中附近），邻居行只给开头；挨着的命中并成一段"""
    if not hits:
        return ""
    spans: list[list[int]] = []
    for hit in sorted(set(hits)):
        s, e = max(0, hit - radius), min(len(lines), hit + radius + 1)
        if spans and s <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    hit_set, chunks, size = set(hits), [], 0
    for s, e in spans:
        rows = []
        for i in range(s, e):
            q = (queries or {}).get(i, query)
            rows.append(f"{i + 1}: " + (snip_line(lines[i], q) if i in hit_set else neighbor_line(lines[i])))
        chunk = "\n".join(rows)
        if chunks and size + len(chunk) > cap:
            break
        chunks.append(chunk[:cap])
        size += len(chunk) + 5
    return "\n---\n".join(chunks)


# ---------- 代码地图 ----------

_FUNC = re.compile(r"^\s*(?:async\s+)?function\s*\*?\s*([\w$]+)\s*\(([^)]*)\)")
_TOP = re.compile(r"^(?:const|let|var)\s+([\w$]+)\s*=\s*(.)")
_ARROW = re.compile(r"^(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?(\([^)]*\)|[\w$]+)\s*=>")
_MEMBER = re.compile(r"^\s{1,4}([\w$]+)\s*(?:\(([^)]*)\)\s*\{|:\s*(?:async\s*)?(?:function\b|\(([^)]*)\)\s*=>|[\w$]+\s*=>))")
_Q = r"""('[^']*'|"[^"]*"|`[^`]*`)"""
_EVENT = re.compile(r"PageEvents\.on\(\s*" + _Q + r"\s*,\s*" + _Q + r"\s*,\s*" + _Q)
_PAGE_IF = re.compile(r"\bpage\s*===?\s*['\"]([\w-]+)['\"]")
_HTML_ID = re.compile(r"<(\w+)\b[^>]*?\sid\s*=\s*[\"']([^\"'${}]+)[\"']")
_NAV_ITEM = re.compile(r"key\s*:\s*['\"]([\w-]+)['\"]\s*,\s*label\s*:\s*['\"]([^'\"]+)['\"]")
_KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "else", "do", "try", "with"}


def _blocks(source: str, tag: str) -> list[tuple[int, int]]:
    """<script> / <style> 在第几行到第几行（1 开始，含两头）"""
    out = []
    for m in re.finditer(rf"<{tag}\b(?![^>]*\bsrc=)[^>]*>(.*?)</{tag}>", source, re.S | re.I):
        out.append((source.count("\n", 0, m.start(1)) + 1, source.count("\n", 0, m.end(1)) + 1))
    return out


def _block_end(lines: list[str], start: int) -> int:
    """从 const X=[ / { 那一行往下找收尾的 ]; / }; ：同一行就收尾的算一行"""
    first = lines[start].rstrip()
    if re.search(r"[\]}]\s*;?\s*$", first) and first.count("{") + first.count("[") <= first.count("}") + first.count("]"):
        return start
    for j in range(start + 1, min(len(lines), start + 3000)):
        if re.match(r"^[\]}]", lines[j]):
            return j
    return start


def code_map(source: str, cap: int = MAP_CAP) -> str:
    """页面里每样东西在第几行：函数、页面方法、数据数组、交互绑定、有 id 的区块。只给名字和行号，不给正文"""
    lines = source.splitlines()
    if not lines:
        return ""
    scripts, styles = _blocks(source, "script"), _blocks(source, "style")
    in_script = [False] * (len(lines) + 2)
    in_style = [False] * (len(lines) + 2)
    for a, b in scripts:
        for i in range(a, b + 1):
            in_script[i] = True
    for a, b in styles:
        for i in range(a, b + 1):
            in_style[i] = True
    entries: list[str] = []
    html_ids: list[str] = []
    skip_until = 0
    size_note = lambda i: f"（{len(lines[i])}字）" if len(lines[i]) > LONG_LINE else ""
    for i, line in enumerate(lines):
        n = i + 1
        if in_style[n]:
            continue
        if line.lstrip().startswith(("//", "/*", "*")) and "/*PA:" not in line:
            continue
        if not in_script[n]:
            for tag, ident in _HTML_ID.findall(line)[:3]:
                html_ids.append(f"{n} <{tag}#{ident}>")
            continue
        for page, typ, sel in _EVENT.findall(line):
            entries.append(f"L{n} PageEvents.on({page},{typ},{sel[:60]}){size_note(i)}")
        if i < skip_until:
            continue
        m = _FUNC.match(line)
        if m:
            entries.append(f"L{n} function {m[1]}({m[2][:60]}){size_note(i)}")
            branches = []
            if m[1] == "bindPage":
                end = _block_end(lines, i) if line.rstrip().endswith("{") or "/*PA:BIND*/" in line else i
                for j in range(i, max(end, i) + 1):
                    branches += [f"{p} L{j + 1}" for p in _PAGE_IF.findall(lines[j])]
                if branches:
                    entries[-1] += " 分页：" + "、".join(dict.fromkeys(branches))
            continue
        m = _ARROW.match(line)
        if m:
            entries.append(f"L{n} const {m[1]}={m[2][:60]}=>{size_note(i)}")
            continue
        m = _TOP.match(line)
        if not m:
            continue
        name, opener = m[1], m[2]
        if opener not in "[{":
            entries.append(f"L{n} const {name}{size_note(i)}")
            continue
        end = _block_end(lines, i)
        span = f"L{n}" if end == i else f"L{n}-{end + 1}"
        if name == "NAV" or "/*PA:NAV*/" in line:
            items = _NAV_ITEM.findall("\n".join(lines[i:end + 1]))
            entries.append(f"{span} NAV 菜单：" + ("、".join(f"{k} {label}" for k, label in items[:40]) or "（空）"))
        elif opener == "[" or end == i:
            entries.append(f"{span} const {name}={opener}…" + (f"（{end - i - 1} 行数据）" if end - i > 1 else size_note(i)))
        else:
            members = []
            for j in range(i + 1, end):
                mm = _MEMBER.match(lines[j])
                if mm and mm[1] not in _KEYWORDS:
                    members.append((mm[1], j + 1, len(lines[j])))
            if len(members) <= 15:
                body = ", ".join(f"{k} L{ln}" + (f"（{w}字）" if w > LONG_LINE else "") for k, ln, w in members)
            else:
                body = ", ".join(k for k, _, _ in members[:30]) + ("…" if len(members) > 30 else "")
            entries.append(f"{span} {name}{{{body}}}")
        skip_until = end + 1
    head = [f"共 {len(lines)} 行"]
    if styles:
        head.append("样式 " + "、".join(f"L{a}-{b}" for a, b in styles))
    if scripts:
        head.append("脚本 " + "、".join(f"L{a}-{b}" for a, b in scripts))
    text = "；".join(head) + "\n" + "\n".join(entries)
    if html_ids:
        text += "\n有 id 的元素：" + "  ".join(html_ids[:40])
    if len(text) > cap:
        text = text[:cap].rsplit("\n", 1)[0] + "\n…（地图太长，后面省略；要找别的就 search_source）"
    return text


# ---------- 预取 ----------

_STOP = {"function", "const", "let", "var", "return", "document", "window", "this", "true", "false", "null", "undefined",
         "click", "page", "pages", "data-pid", "div", "span", "button", "class", "style", "html", "body", "script",
         "onclick", "addEventListener", "innerHTML", "length", "Uncaught", "ReferenceError", "TypeError", "SyntaxError",
         "Error", "not", "defined", "the", "and", "error", "primary", "danger", "success", "warning", "info"}
# 外壳和浏览器自带的东西：到处都在用，说明不了用户指的是哪
_COMMON = {"Math", "JSON", "Object", "Array", "String", "Number", "Date", "Promise", "console", "ZeroUI", "UI", "Router",
           "PageEvents", "Shell", "location", "localStorage", "Pages.", "slice", "filter", "reduce", "forEach", "includes",
           "indexOf", "replace", "toFixed", "push", "splice", "find", "findIndex", "some", "every", "join", "split", "trim",
           "keys", "values", "entries", "ceil", "floor", "round", "max", "min", "abs", "parseInt", "parseFloat", "setTimeout",
           "querySelector", "querySelectorAll", "getElementById", "closest", "toLocaleString", "padStart", "render",
           "current", "Toast", "Modal", "ConfirmModal", "Drawer", "openModal", "openDrawer", "Button", "Field", "Pager",
           "Tag", "Empty", "ListItem", "pageShell", "Card", "bindPage", "esc", "navItems", "navGroups", "dataset", "map",
           "on", "rows", "close", "then", "catch", "stopPropagation", "preventDefault", "toggle", "remove", "add"}


def _candidates(text: str) -> list[tuple[int, str]]:
    """一段话里像代码名字的东西，按靠不靠得住排好：报错里的变量名 > 选择器片段、id > 函数名 > 「」里的页面叫法"""
    out: dict[str, int] = {}
    def add(tier: int, token: str):
        token = token.strip()
        bare = token.rstrip("(")
        if len(bare) < 3 or bare in _STOP or bare in _COMMON or bare.split(".")[0] in _COMMON:
            return
        if token not in out or out[token] > tier:
            out[token] = tier
    for m in re.finditer(r"([A-Za-z_$][\w$]*) is not (?:defined|a function)", text):
        add(0, m[1])
    for m in re.finditer(r"Cannot read propert(?:y|ies) of \w+ \(reading '([\w$]+)'\)", text):
        add(0, m[1])
    for m in re.finditer(r"data-[\w-]+[\^$*~|]?=\s*['\"]?([^'\"\]\s]{2,40})", text):
        add(1, m[1])
    for m in re.finditer(r"#([A-Za-z][\w-]{2,40})", text):
        add(1, m[1])
    for m in re.finditer(r"\b([A-Z][\w$]*)\.([A-Za-z_$][\w$]*)", text):
        if m[1] not in _COMMON:
            add(2, m[0])
            add(2, m[2] + "(")
    for m in re.finditer(r"(?<![.\w$])([A-Za-z_$][\w$]{3,})\s*\(", text):
        add(2, m[1])
    for m in re.finditer(r"['\"`]([A-Za-z][\w-]{2,40})['\"`]", text):
        add(3, m[1])
    for m in re.finditer(r"「([^」]{2,30})」", text):
        for part in re.split(r"\s*[·/]\s*", m[1]):
            if 2 <= len(part) <= 20 and part not in {"表格行", "按钮", "页面"}:
                add(4, part)
    return sorted(((tier, token) for token, tier in out.items()), key=lambda x: x[0])


def prefetch(source: str, texts: list[str], hint_lines: list[int] | None = None,
             cap: int = PREFETCH_CAP, max_hits: int = 6) -> str:
    """把用户这轮点名的东西先在源码里找出来：命中很少（≤6 行）的名字才算数，到处都有的说明不了位置。
    按靠得住的程度一个个加，加满预算就停——宁可少给，也不拿一堆无关的行把上下文撑大"""
    lines = source.splitlines()
    if not lines:
        return ""
    picked: dict[int, str] = {}
    found: list[str] = []
    size = 0
    def cost(i: int, q: str) -> int:
        return len(snip_line(lines[i], q)) + 2 * (NEIGHBOR + 20)
    for n in hint_lines or []:   # 点选的位置最靠得住，先放
        if 1 <= n <= len(lines) and n - 1 not in picked:
            picked[n - 1] = ""
            size += cost(n - 1, "")
    for _, token in _candidates("\n".join(t for t in texts if t)):
        low = token.lower()
        rows = [i for i, line in enumerate(lines) if low in line.lower()]
        if not rows or len(rows) > max_hits:
            continue
        extra = sum(cost(i, token) for i in rows if i not in picked)
        if picked and size + extra > cap:
            continue
        found.append(token.rstrip("("))
        for i in rows:
            picked.setdefault(i, token)
        size += extra
        if len(found) >= 8:
            break
    if not picked:
        return ""
    body = context_chunks(lines, list(picked), radius=1, cap=int(cap * 1.5), queries=picked)
    head = ("程序按你这轮提到的" + ("「" + "」「".join(found[:8]) + "」" if found else "位置")
            + "预先在源码里找到的片段（改动前的原文，带行号）。够用就直接改，别再一个名字一个名字地搜：\n")
    return head + body


# ---------- 改完落在哪 ----------

def changes_view(old: str, new: str, cap: int = 2500) -> dict:
    """改动后新代码在第几行、后面的行号挪了多少：它接着改下一处时不用先搜一遍「刚才写到哪了」"""
    a, b = old.splitlines(), new.splitlines()
    ops = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    hunks, size = [], 0
    for tag, i1, i2, j1, j2 in ops[:12]:
        if tag == "delete":
            item = f"删掉了原来的第 {i1 + 1}–{i2} 行（现在第 {j1} 行之后）"
        else:
            shown = [f"{j + 1}: {neighbor_line(b[j])}" for j in range(j1, min(j2, j1 + 6))]
            more = f"\n…（这段共 {j2 - j1} 行）" if j2 - j1 > 6 else ""
            item = f"现在的第 {j1 + 1}–{j2} 行（{'新增' if tag == 'insert' else '改过'}）：\n" + "\n".join(shown) + more
        if hunks and size + len(item) > cap:
            hunks.append(f"…还有 {len(ops) - len(hunks)} 处改动没列出")
            break
        hunks.append(item)
        size += len(item)
    return {"total_lines": len(b), "shift": len(b) - len(a), "changed": hunks}
