"""架构是原型的镜子：从展开图（业务页面、弹窗、子页面、表头、表单项）读出页面树，不用 AI，几秒就好。

左边对话里 AI 改完原型，展开图在后台跟着同步，页面树再从展开图读一遍（refresh）；
你在树里写的介绍、字段控件这些原型里看不出来的，读的时候带过去（carry）。
你在树里改了还没同步的，不读——先「同步到原型」，让 AI 把那几处改进原型。
"""
from __future__ import annotations

import re

from . import storage
from .arch_fields import form_fields, parse_field


def _texts(html: str, pattern: str, limit: int = 30) -> list[str]:
    out = []
    for m in re.finditer(pattern, html or "", re.S):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        if text and len(text) <= 30 and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _main(html: str) -> str:
    """页面快照里去掉侧边菜单那一段，只看正文"""
    return re.sub(r"<aside.*?</aside>", "", html or "", flags=re.S)


def _nav_groups(html: str, titles: list[str]) -> list[tuple[str, list[str]]]:
    """侧边菜单里按出现顺序：不是页面名的短文字当分组（模块），页面名归到它前面那个分组"""
    aside = re.search(r"<aside.*?</aside>", html or "", re.S)
    texts = [re.sub(r"\s+", " ", t).strip() for t in re.split(r"<[^>]+>", aside.group(0) if aside else "")]
    texts = [t.strip("⌃⌄▾▸▴ ") for t in texts if t.strip("⌃⌄▾▸▴ ")]
    groups: list[tuple[str, list[str]]] = []
    current = ""
    for t in texts:
        if t in titles:
            if not groups or groups[-1][0] != current:
                groups.append((current, []))
            if t not in groups[-1][1]:
                groups[-1][1].append(t)
        elif len(t) <= 14 and re.search(r"[一-鿿A-Za-z]", t):
            current = t
    placed = {t for _, items in groups for t in items}
    rest = [t for t in titles if t not in placed]
    if rest:
        groups.append(("", rest))
    return groups


SKIP_COLS = {"操作", "序号", "#", "选择", ""}


def _cols(html: str) -> list[str]:
    return [c for c in _texts(html, r"<th[^>]*>(.*?)</th>", 30) if c not in SKIP_COLS]


def _dts(html: str, limit: int = 20) -> list[str]:
    """只读的「字段：值」（<dt>工单号</dt><dd>BX-…</dd>）里的字段名"""
    return [t.strip(" ：:") for t in _texts(html, r"<dt[^>]*>(.*?)</dt>", limit)]


def _layer_title(html: str, fallback: str) -> str:
    """弹窗自己的标题：aria-label，没有就取 xx-hd / xx-header 头部的字。旧的展开结果标题可能取成了正文小节"""
    m = re.search(r'role="dialog"[^>]*aria-label="([^"]{1,40})"|aria-label="([^"]{1,40})"[^>]*role="dialog"', html or "")
    if m and (m.group(1) or m.group(2)).strip() not in ("关闭", "弹窗"):
        return (m.group(1) or m.group(2)).strip()
    m = re.search(r'class="[^"]*(?:-hd|_hd|header|Header)[^"]*"[^>]*>\s*(?:<(?!button)[^>]+>\s*)*([^<]{1,40})', html or "")
    return m.group(1).strip() if m and m.group(1).strip() else fallback


def _col_of(html: str, text: str) -> str:
    """表格里这个字在哪一列，返回那一列的表头（工单号）"""
    heads = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", html or "", re.S)]
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", re.S):
        if text not in row:
            continue
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        # 认点的那个按钮 / 链接本身的字，不能光看包含：「派单」按钮会被认到「待派单」那一列
        clean = lambda h: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h)).strip()
        for i, cell in enumerate(cells):
            hit = clean(cell) == text or any(clean(b) == text for _, b in re.findall(r"<(a|button)\b[^>]*>(.*?)</\1>", cell, re.S))
            if hit and i < len(heads):
                return heads[i]
    return ""


def _fill(container: dict, html: str, nodes: list[dict], parent_id) -> None:
    """一个页面（或下钻页、页签、弹窗）里面有什么：筛选、表格、按钮，按钮点了打开哪个弹窗 / 跳到哪个子页面，弹窗里有哪些字段"""
    kids = container["children"]
    labels, cols, shows = form_fields(html), _cols(html), _dts(html)
    names = {parse_field(f)["name"] for f in labels}
    if container["type"] == "drawer" and (labels or shows):
        container["fields"] = labels + [d for d in shows if d not in names]
    elif container["type"] in ("modal", "wizard") and (labels or shows):
        # 弹窗上面带出来给你看的（工单号、报修事项）是只读的，加 🔒；下面要填的照 <label>，带上是下拉还是日期
        container["fields"] = [d + "🔒" for d in shows if d not in names] + labels
    elif labels:
        kids.append({"type": "block", "name": "筛选 / 表单", "fields": labels, "children": []})
    table = None
    if cols:
        table = {"type": "table", "name": "列表" if container["type"] not in ("modal", "drawer", "wizard") else "明细表", "cols": cols, "children": []}
        kids.append(table)
    seen_buttons, seen_targets = set(), set()
    for n in [n for n in nodes if n.get("parent") == parent_id]:
        raw = str(n.get("label") or "")
        row = raw.startswith("表格行")
        label = re.sub(r"^(表格行|页签)\s*·\s*", "", raw).strip()[:30] or "操作"
        title = str(n.get("title") or label)[:40]
        if n.get("kind") != "subpage" and not raw.startswith("页签"):
            title = _layer_title(n.get("html") or "", title)
        # 表格里点的是一条数据（工单号 BX-202610-011）：按钮叫那一列的名字，每一行点开的都是同一个详情，只记一次
        col = _col_of(html, label) if row else ""
        if row and col and col not in SKIP_COLS and col != label:
            label = col
        if raw.startswith("页签"):
            target = {"type": "tab", "name": label, "children": []}
            kids.append(target)
            _fill(target, n.get("html") or "", nodes, n.get("id"))
            continue
        kind = "drill" if n.get("kind") == "subpage" else "drawer" if "drawer" in str(n.get("layerSel", "")).lower() else "modal"
        # 点表格里的编号进去的详情页，标题就是那条数据的编号（TMP-BUILD-2026-V2）：换成「xx详情」，编号放进入口
        shown = label
        if kind == "drill" and not re.search(r"[一-鿿]", title):
            title = re.sub(r"(配置|管理|列表|清单)$", "", container["name"]) + "详情"
            label = "点编号进详情" if not re.search(r"[一-鿿]", label) else label
        button = {"type": "button", "name": label, "action": "jump" if kind == "drill" else "open", "target": title, "children": []}
        holder = table["children"] if (row and table) else kids
        if (label, title) not in seen_buttons:
            seen_buttons.add((label, title))
            holder.append(button)
        # 别的按钮也打开这一层（「工单号」和「详情」都打开工单详情）
        for extra in n.get("also") or []:
            name = re.sub(r"^表格行\s*·\s*", "", str(extra)).strip()[:30]
            if name and (name, title) not in seen_buttons:
                seen_buttons.add((name, title))
                (table["children"] if (str(extra).startswith("表格行") and table) else kids).append({**button, "name": name, "children": []})
        if (kind, title) in seen_targets:
            continue
        seen_targets.add((kind, title))
        target = {"type": kind, "name": title, "children": []}
        if kind == "drill":
            target.update(entry=f"点「{shown}」" if shown == label else f"点列表里的编号（如 {shown}）", back="返回" + container["name"])
        kids.append(target)
        _fill(target, n.get("html") or "", nodes, n.get("id"))


def expand_tree(project_id: str, page_id: str) -> list[dict]:
    """展开图 → 页面树。菜单分组当模块，业务页面当菜单页，点得开的子页面当下钻页、弹窗抽屉照实放进去。
    不在任何分组下的菜单项直接放最外层（一级菜单页）；一个业务页面其实是另一页的页签（报修工单的「工单统计」）就挂成那一页的页签"""
    try:
        data = storage.load_expand(project_id, page_id)
    except (ValueError, FileNotFoundError):
        return []
    routes, entries = data.get("routes") or [], data.get("entries") or {}
    if not routes:
        return []
    titles = [r.get("title") or r.get("hash") for r in routes]
    first = next((e.get("result") or {} for e in entries.values() if (e.get("result") or {}).get("page")), {})
    groups = _nav_groups(first.get("page") or "", titles)
    pages, tabs_of = {}, {}
    for r in routes:
        result = (entries.get(r.get("hash")) or {}).get("result") or {}
        node = {"type": "page", "name": r.get("title") or r.get("hash"), "route": str(r.get("hash", "")).lstrip("#"), "children": []}
        html = _main(result.get("page") or "")
        tabs_of[node["name"]] = _texts(html, r'class="[^"]*(?:tab|hub-tab)[^"]*"[^>]*>(.*?)</', 12)
        _fill(node, html, result.get("nodes") or [], None)
        pages[node["name"]] = node
    # 页签：A 页上的页签里有 B 页的名字 → B 是 A 的一个页签。A 自己的内容放进它当前那个页签
    nested = set()
    for name, node in pages.items():
        as_tabs = [t for t in tabs_of[name] if t in pages and t != name and t not in nested]
        if not as_tabs:
            continue
        own = next((t for t in tabs_of[name] if t not in pages), "")
        kids = [{"type": "tab", "name": own, "children": node["children"]}] if own else node["children"]
        for t in as_tabs:
            tab = pages[t]
            kids.append({"type": "tab", "name": t, "route": tab.get("route", ""), "children": tab["children"]})
            nested.add(t)
        node["children"] = kids
    out = []
    for name, items in groups:
        kids = [pages[t] for t in items if t in pages and t not in nested]
        if not kids:
            continue
        if name:
            out.append({"type": "module", "name": name, "children": kids})
        else:
            out += kids
    return out


# 原型里看不出来、只在树里写的：读新树时从旧树带过去
KEEP_KEYS = ("desc", "who", "req", "tags", "entry", "back", "params", "when", "after", "data", "route")


def _match(old: list[dict], node: dict) -> dict | None:
    same = [o for o in old if o["name"] == node["name"]]
    return next((o for o in same if o["type"] == node["type"]), same[0] if same else None)


def carry(old: list[dict], fresh: list[dict]) -> list[dict]:
    """新读出来的树为准（原型里有什么就是什么），同名的节点沿用旧的编号，介绍、谁用这些旧的有、新的没有就带上；
    字段：原型里认出来的为准，认不出控件的那个字段用旧树里写的"""
    for node in fresh:
        prev = _match(old, node)
        if not prev:
            carry([], node.get("children") or [])
            continue
        if prev.get("id"):
            node["id"] = prev["id"]
        for key in KEEP_KEYS:
            if prev.get(key) and not node.get(key):
                node[key] = prev[key]
        if prev.get("fields"):
            if not node.get("fields"):
                node["fields"] = prev["fields"]
            else:
                written = {parse_field(f)["name"]: f for f in prev["fields"]}
                node["fields"] = [written.get(parse_field(f)["name"], f) if parse_field(f)["guessed"] else f for f in node["fields"]]
        if prev.get("cols") and not node.get("cols"):
            node["cols"] = prev["cols"]
        node["children"] = carry(prev.get("children") or [], node.get("children") or [])
    return fresh
