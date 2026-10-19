"""AI 读页面源码用的：分段读、搜关键词、把点选的目标对到源码行号，以及把「插入组件」换成真正的插入。

读进来的每一个字之后每一轮都要重发，所以这里处处在控制「一次给多少」。
"""
from __future__ import annotations

import re

from . import components
from .patcher import PatchError, outline
from .source_map import context_chunks

SAFE_PAGE_PATH = re.compile(r"(?:[a-z][a-z0-9-]{0,20}/)?[a-z][a-z0-9-]{0,30}\.html")
# 共享样式和脚本只能落在 assets/ 下，不允许写到别处去。


def expand_components(ops: list[dict]) -> list[dict]:
    """把 insert_component 换成真正的插入操作。

    让模型重抄一遍组件原文既浪费输出额度，也是输出被截断的主要原因；
    它只写名字，内容由这里填。
    """
    slots = {"before": "insert_before", "after": "insert_after",
             "inside": "append_html", "replace": "replace_outer_html"}
    for op in ops:
        if op.get("action") != "insert_component":
            continue
        name = str(op.get("name", ""))
        try:
            op["value"] = components.read(name)
        except (ValueError, FileNotFoundError) as exc:
            raise PatchError(f"没有这个组件：{name}。可用的见系统提示里的组件清单") from exc
        op["action"] = slots.get(str(op.get("position", "after")), "insert_after")
        if not op.get("selector"):
            raise PatchError("插入组件要指定 selector，说明插在哪个元素旁边")
    return ops


def _num(value, default: int) -> int:
    """模型给的行号可能是 null、"12"、12.0，取不到就用默认值，不能让一个参数把整轮工作抛成内部错误"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def read_budget(context_budget: int) -> int:
    """一次读取最多给多少字符。

    跟上下文预算挂钩：窗口大就一次多给点，省得来回分段读；
    但永远不超过预算的四分之一——一次读掉一半上下文，剩下的不够干活。
    """
    return min(READ_CAP, max(12_000, context_budget // 4))


READ_CAP = 20_000           # 一次读最多这么多字：读进来的每一字之后每一步都要重发，要多看就接着读下一段


def _slice_lines(lines: list[str], start: int, end: int, budget: int = 12_000) -> dict:
    """按行给源码，并且如实说自己给到了哪一行。

    以前是把整段拼好再 [:12000] 一刀切，返回的 end 仍是模型要求的那个行号。
    模型请求 1–530 行、实际只拿到前 156 行，却被告知已经读到 530 行——
    它当然会觉得自己读完了，找不到东西就再读一遍，来回空转。
    现在按行累加到预算为止，返回真实到达的行号，并告诉它从哪一行接着读。
    """
    picked, size = [], 0
    for i in range(start - 1, end):
        row = f"{i+1}: {lines[i]}"
        if picked and size + len(row) + 1 > budget:
            break
        picked.append(row)
        size += len(row) + 1
    reached = start - 1 + len(picked)
    out = {"start": start, "end": reached, "total_lines": len(lines),
           "content": "\n".join(picked)}
    if reached < end:
        out["truncated"] = True
        out["note"] = (f"这次只给到第 {reached} 行（一次最多 {budget} 字符）。"
                       f"要看后面的内容，从 start={reached + 1} 继续读。")
    return out


def _search_source(source: str, query: str) -> dict:
    """搜索结果同样如实：命中几处、给了几处。"""
    if not query:
        return {"hits": 0, "context": "没有给搜索词。"}
    lines = source.splitlines()
    hits = [i for i, line in enumerate(lines) if query.lower() in line.lower()]
    if not hits:
        return {"hits": 0, "context": f"整个页面里没有「{query}」。"
                "如果这正是你要改的东西，说明页面上并不存在它，不要再换范围重读——"
                "直接把这个事实汇报给用户。"}
    # 命中的那一行给全（太长只给命中附近），上下几行只给开头：原型脚本一行常常就是一整个函数，
    # 以前上下各 6 行原样给，一次搜索 8000 字，十来次搜索就把上下文撑到两三万 tokens
    radius = 6 if len(hits) <= 2 else 3
    out = {"hits": len(hits), "lines": [i + 1 for i in hits[:20]],
           "context": context_chunks(lines, hits[:5], query, radius=radius, cap=8000)}
    if len(hits) > 5:
        out["note"] = f"共命中 {len(hits)} 处，上面只展开了前 5 处的上下文；全部行号见 lines。"
    return out


GENERIC_CLASS = re.compile(r"^(btn|button|active|show|open|is-|has-|el-|ant-|col-|row|flex|grid|text-|mt-|mb-|ml-|mr-|p[xytblr]?-|m[xytblr]?-|w-|h-|d-)", re.I)


def locate_lines(source: str, target: dict, limit: int = 3) -> list[dict]:
    """选中的元素大概在源码哪几行。

    原型多是脚本拼出来的，预览里的选择器（nth-of-type 之类）在源码里根本对不上，
    以前 AI 只能拿着文字一段段翻。这里把元素身上能在源码里找到的东西——文字、id、data-pid、
    data-action、onclick、不太通用的 class——拿去对行，几样同时挤在一小段里的位置最可能就是它。
    """
    lines = source.splitlines()
    html = str(target.get("outer_html") or "")[:5000]
    tokens: dict[str, int] = {}
    def add(token: str, weight: int):
        token = token.strip()
        if 2 <= len(token) <= 60 and not token.isdigit():
            tokens[token] = max(tokens.get(token, 0), weight)
    for piece in re.split(r"\s*\n\s*|\s{2,}", str(target.get("text") or "")[:500]):
        add(piece, 3)
    for m in re.finditer(r"""(?:\sid|\sname|\sdata-[\w-]+|\shref=["']#)\s*=?\s*["']?([^"'\s>]{2,60})["']""", html):
        add(m.group(1), 4)
    m = re.search(r"""onclick\s*=\s*["']([A-Za-z_$][\w$.]*)\s*\(""", html)
    if m:
        add(m.group(1), 4)
    for sel_id in re.findall(r"#([\w-]{3,})", str(target.get("selector") or "")):
        add(sel_id, 4)
    first = re.search(r"""class\s*=\s*["']([^"']+)["']""", html)
    for cls in (first.group(1).split() if first else []):
        if len(cls) >= 4 and not GENERIC_CLASS.match(cls) and "$" not in cls:
            add(cls, 1)
    if not tokens or not lines:
        return []
    picked = sorted(tokens.items(), key=lambda kv: -kv[1])[:12]
    hits: dict[int, set] = {}
    weight: dict[str, float] = {}
    for token, w in picked:
        rows = [i for i, line in enumerate(lines) if token in line]
        # 到处都有的词（「查看」「保存」）说明不了位置：命中的行越多分量越轻，太泛的直接不用；
        # 真正靠得住的是几样东西挤在同一小段里
        if not rows or len(rows) > 300:
            continue
        weight[token] = w * (1 if len(rows) <= 15 else 0.5 if len(rows) <= 60 else 0.25)
        for i in rows:
            hits.setdefault(i, set()).add(token)
    if not weight:
        return []
    scored = []
    for i in hits:
        near = set().union(*(hits.get(j, set()) for j in range(i - 4, i + 5)))
        score = sum(weight[t] for t in near)
        if (len(near) >= 2 and score >= 1.5) or score >= 3:
            scored.append((score, -i, near))
    out = []
    for score, neg_i, near in sorted(scored, reverse=True):
        i = -neg_i
        if any(abs(i + 1 - o["line"]) <= 8 for o in out):
            continue
        out.append({"line": i + 1, "matched": sorted(near, key=lambda t: -weight[t])[:5], "snippet": lines[i].strip()[:160]})
        if len(out) >= limit:
            break
    return out


def lines_text(hints: list[dict]) -> str:
    if not hints:
        return ""
    return " 源码里大概在：" + "；".join(f"第 {h['line']} 行（对上了 {'、'.join(h['matched'][:3])}）" for h in hints)


def inspect_output(working_source: str, page: dict, anns: list[dict]) -> dict:
    """inspect_page：页面概况（标题、区块、标题层级、按钮）和每个定位目标在源码里的样子、行号"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(working_source,"html.parser")
    targets = []
    for a in anns:
        try: node = soup.select_one(a["selector"])
        except Exception: node = None
        # 只给定位要用的字段：以前把整条标注（outer_html 5000 字、样式、坐标…）原样塞进来，16 个目标就超过 10 万字
        brief = {k: a[k] for k in ("id", "selector", "note", "name", "tag", "text", "kind", "in_modal", "modal_trail", "in_subpage") if a.get(k)}
        targets.append({**brief,"found":bool(node),"html":str(node)[:2200] if node else str(a.get("outer_html",""))[:2200],
                        "source_lines":locate_lines(working_source, a)})
    for node in soup(['script','style']): node.decompose()
    return {"title":page.get("title"),"chars":len(working_source),"annotations":targets,"regions":outline(working_source),
            "page_text":(soup.body or soup).get_text(' ',strip=True)[:5000],
            "headings":[h.get_text(' ',strip=True)[:120] for h in soup.select('h1,h2,h3')[:24]],
            "actions":[n.get_text(' ',strip=True)[:80] or n.get('aria-label','') for n in soup.select('button,a,input[type=submit]')[:30]]}
