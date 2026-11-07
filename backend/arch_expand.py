"""从展开图（业务页面、弹窗、子页面、表头、表单项）读出页面树，不用 AI，几秒就好。

画布和原型怎么对齐（refresh_canvas）：
- base：上一次从原型读出来的样子（存在 architecture.base.json），编号和画布上的对得上
- 画布 = base + 你在画布上做的改动（加、删、改名、挪、改字段）。改动 = diff(base, 画布)，就是「同步到原型」要交给 AI 的那几处
- 再读一次原型：新的 base 按名字对上旧的编号；画布 = 新 base 上重放你还没同步的改动——
  所以原型里新做的补进来，你删掉的不会被补回来，改名的不会变成两个；AI 照着改好了，那一条改动自然就没了
- 原型里删掉、画布上还留着的，标「原型里已经没有」；只写在画布上的介绍、谁用这些，按编号带过去
"""
from __future__ import annotations

import copy
import re
import uuid

from . import storage
from .arch_fields import form_fields, parse_field
from .architecture import loose_name


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


# 表格上方的标题：卡片头（card-title / xx-hd / header）或小标题 h2-h6
TITLE_AT = re.compile(r'<h[2-6][^>]*>(.*?)</h[2-6]>|class="[^"]*(?:title|-hd\b|_hd\b|header|heading)[^"]*"[^>]*>(.*?)</', re.S)
TITLE_NEAR = 900          # 标题离表格太远（中间隔着指标卡、筛选栏）就不算这张表的
# 以前读出来的通用名：老画布上的这些节点按列 / 字段对上新读出来的，不当成删了一个、又加了一个
GENERIC = {"列表", "明细表", "筛选 / 表单", "筛选", "表单"}


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def _tables(html: str, owner: str) -> list[dict]:
    """这一层里的每张表，各自的列；名字取表格上方最近的标题（「日运行明细」「设备状态」），
    没有标题就叫「页面名 + 列表」（实时告警列表）。以前一页几张表的表头全并成一张「列表」"""
    out, start = [], 0
    for m in re.finditer(r"<table\b.*?</table>", html or "", re.S):
        cols = _cols(m.group(0))
        before = (html or "")[max(start, m.start() - TITLE_NEAR):m.start()]
        start = m.end()
        if not cols:
            continue
        title = ""
        for t in TITLE_AT.finditer(before):
            text = _clean(t.group(1) or t.group(2))
            if 2 <= len(text) <= 16 and re.search(r"[一-鿿]", text) and not re.match(r"共\s*\d|第\s*\d", text):
                title = text
        out.append({"title": title, "cols": cols, "html": m.group(0)})
    base = re.sub(r"(管理|配置|列表|清单|查询|中心|详情)$", "", owner) or owner
    used: set[str] = set()
    for i, t in enumerate(out):
        name = t["title"] if t["title"] and t["title"] != owner else base + "列表"
        while name in used:
            name = f"{base}列表{len(used) + 1}" if name.startswith(base) else name + "2"
        used.add(name)
        t["name"] = name
    return out


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


TAB_CLASS = r'class="(?:[^"]*\s)?(?:[\w-]*-)?tab(?:-item)?(?:\s[^"]*)?"[^>]*>(.*?)</'


def _tab_names(html: str) -> list[str]:
    """页面上页签的名字。class 里要有单独的 tab（tab / hub-tab / lp-tab）：data-table 不算，
    不然表头「报修分类」会被认成页签；名字后面带的数（待派单3、待派单(3)）去掉"""
    return [re.sub(r"\s*[(（]?\d+[)）]?$", "", t) for t in _texts(html, TAB_CLASS, 12)]


def _fold_tab(tab: dict, page_kids: list[dict]) -> None:
    """按状态分的页签（列表页模板就是这样）：每个页签里是同一套筛选、表格、按钮。页签只留名字，
    只在这个页签里出现的按钮（待接单里的「接单」）、弹窗并到页面那一层——画架构时也是这么写的"""
    tables = {k["name"]: k for k in page_kids if k["type"] == "table"}
    blocks = {k["name"] for k in page_kids if k["type"] == "block"}
    mine = [k for k in tab["children"] if k["type"] in ("table", "block")]
    if not mine or not all(k["name"] in tables or k["name"] in blocks for k in mine):
        return
    for k in tab["children"]:
        if k["type"] == "table":
            have = {b["name"] for b in tables[k["name"]]["children"]}
            tables[k["name"]]["children"] += [b for b in k["children"] if b["name"] not in have]
        elif k["type"] not in ("block",) and not any(x["type"] == k["type"] and x["name"] == k["name"] for x in page_kids):
            first = next(i for i, x in enumerate(page_kids) if x["type"] == "tab")
            page_kids.insert(first, k)
    tab["children"] = []


def _fill(container: dict, html: str, nodes: list[dict], parent_id, extras: dict | None = None) -> None:
    """一个页面（或下钻页、页签、弹窗）里面有什么：筛选、表格、按钮，按钮点了打开哪个弹窗 / 跳到哪个子页面，弹窗里有哪些字段。
    extras：这一层上点了没弹出东西的按钮（导出、停用、只弹提示、跳到别的页），也记成按钮"""
    kids = container["children"]
    labels, shows = form_fields(html), _dts(html)
    tables = _tables(html, container["name"]) if "<table" in (html or "") else []
    names = {parse_field(f)["name"] for f in labels}
    if container["type"] == "drawer" and (labels or shows):
        container["fields"] = labels + [d for d in shows if d not in names]
    elif container["type"] in ("modal", "wizard") and (labels or shows):
        # 弹窗上面带出来给你看的（工单号、报修事项）是只读的，加 🔒；下面要填的照 <label>，带上是下拉还是日期
        container["fields"] = [d + "🔒" for d in shows if d not in names] + labels
    elif labels:
        # 页面上有表格：上面那排输入框是筛选；没有表格就是一张表单
        kids.append({"type": "block", "name": "筛选" if tables else "表单", "fields": labels, "children": []})
    for t in tables:
        t["node"] = {"type": "table", "name": t["name"], "cols": t["cols"], "children": []}
        kids.append(t["node"])
    table = tables[0]["node"] if tables else None

    def table_of(label: str):
        """表格行上的按钮挂在它所在的那张表下面"""
        return next((t["node"] for t in tables if label and label in _clean(t["html"])), table)
    seen_buttons, seen_targets = set(), set()
    for n in [n for n in nodes if n.get("parent") == parent_id]:
        raw = str(n.get("label") or "")
        row = raw.startswith("表格行")
        label = re.sub(r"^(表格行|页签)\s*·\s*", "", raw).strip()[:30] or "操作"
        title = str(n.get("title") or label)[:40]
        if n.get("kind") != "subpage" and not raw.startswith("页签"):
            title = _layer_title(n.get("html") or "", title)
        # 每一行点开的弹窗标题带着那一行的名字或编号（「1#光伏逆变器 · 设备详情」「派单 · BX20261107-0001」）：留有中文的那半截
        if row and " · " in title:
            parts = [x.strip() for x in title.split(" · ") if re.search(r"[一-鿿]", x)]
            title = parts[-1] if parts else title.rsplit(" · ", 1)[-1].strip() or title
        if raw.startswith("页签"):    # 页签上带的数（待派单3、待派单(3)）不是名字
            label = re.sub(r"\s*[(（]?\d+[)）]?$", "", label) or label
        # 表格里点的是一条数据（工单号 BX-202610-011）：按钮叫那一列的名字，每一行点开的都是同一个详情，只记一次
        # 哪一列：只在这个按钮所在的那张表里找（一页几张表时，表头不能混着数）
        col = _col_of(next((tb["html"] for tb in tables if label in _clean(tb["html"])), html), label) if row else ""
        if row and col and col not in SKIP_COLS and col != label:
            label = col
        if raw.startswith("页签"):
            target = {"type": "tab", "name": label, "children": []}
            kids.append(target)
            _fill(target, n.get("html") or "", nodes, n.get("id"), extras)
            _fold_tab(target, kids)
            continue
        kind = "drill" if n.get("kind") == "subpage" else "drawer" if "drawer" in str(n.get("layerSel", "")).lower() else "modal"
        if kind != "drill" and not re.search(r"[一-鿿]", title) and re.search(r"[一-鿿]", label):
            title = label                 # 弹窗标题只有那条数据的编号（BX20261107-0001）：用按钮的名字
        # 点表格里的编号进去的详情页，标题就是那条数据的编号（TMP-BUILD-2026-V2）：换成「xx详情」，编号放进入口
        shown = label
        if kind == "drill" and not re.search(r"[一-鿿]", title):
            title = re.sub(r"(配置|管理|列表|清单)$", "", container["name"]) + "详情"
            label = "点编号进详情" if not re.search(r"[一-鿿]", label) else label
        button = {"type": "button", "name": label, "action": "jump" if kind == "drill" else "open", "target": title, "children": []}
        holder = table_of(label)["children"] if (row and table) else kids
        if (label, title) not in seen_buttons:
            seen_buttons.add((label, title))
            holder.append(button)
        # 别的按钮也打开这一层（「工单号」和「详情」都打开工单详情）
        for extra in n.get("also") or []:
            name = re.sub(r"^表格行\s*·\s*", "", str(extra)).strip()[:30]
            if name and (name, title) not in seen_buttons:
                seen_buttons.add((name, title))
                (table_of(name)["children"] if (str(extra).startswith("表格行") and table) else kids).append({**button, "name": name, "children": []})
        if (kind, title) in seen_targets:
            continue
        seen_targets.add((kind, title))
        target = {"type": kind, "name": title, "children": []}
        if kind == "drill":
            target.update(entry=f"点「{shown}」" if shown == label else f"点列表里的编号（如 {shown}）", back="返回" + container["name"])
        kids.append(target)
        _fill(target, n.get("html") or "", nodes, n.get("id"), extras)
    for raw, action, target_name in (extras or {}).get(parent_id, []):
        row = raw.startswith("表格行")
        label = re.sub(r"^(表格行|页签)\s*·\s*", "", raw).strip()[:30]
        col = _col_of(next((tb["html"] for tb in tables if label in _clean(tb["html"])), html), label) if row else ""
        if row and col and col not in SKIP_COLS and col != label:
            label = col                   # 点表格里的编号跳走：按钮叫那一列的名字，每一行只记一次
        if not label or any(b[0] == label for b in seen_buttons):
            continue
        seen_buttons.add((label, target_name))
        button = {"type": "button", "name": label, "action": action, "children": []}
        if target_name:
            button["target"] = target_name
        (table_of(label)["children"] if (row and table) else kids).append(button)
    # 页签：当前亮着的那个没点过（页面本身就是它），也补上；按页面上的顺序排
    tabs = [k for k in kids if k["type"] == "tab"]
    if tabs:
        names = _tab_names(html)
        have = {t["name"] for t in tabs}
        tabs += [{"type": "tab", "name": n, "children": []} for n in names if n not in have]
        tabs.sort(key=lambda t: names.index(t["name"]) if t["name"] in names else len(names))
        at = next(i for i, k in enumerate(kids) if k["type"] == "tab")
        kids[:] = [k for k in kids if k["type"] != "tab"]
        kids[at:at] = tabs


# 点了没弹出东西的按钮：展开时没点（导出、停用这类有风险的）、点了只弹提示、点了跳到别的页面
SKIP_ACTION = {"commit": ("confirm", "二次确认后执行"), "noise": ("run", "")}
NOISE_SKIP = re.compile(r"^(查询|重置|搜索|刷新|清空|翻页|上一页|下一页)$")


def _extras(result: dict, titles: dict) -> dict:
    """{parent: [(按钮文字, 点了怎样, 目标)]}。只知道名字、不知道在哪一层的，看它的字出现在哪个弹窗里，都不在就算页面上的"""
    out: dict = {}
    nodes = result.get("nodes") or []

    def where(label: str):
        text = re.sub(r"^表格行\s*·\s*", "", label)
        hit = next((n for n in nodes if text and text in (n.get("html") or "")), None)
        return hit.get("id") if hit else None
    for j in result.get("jumps") or []:
        out.setdefault(j.get("parent"), []).append((j.get("label", ""), "jump", titles.get(j.get("hash"), j.get("title") or "")))
    for d in result.get("dead") or []:
        out.setdefault(d.get("parent"), []).append((d.get("label", ""), "run", "点了还没反应"))
    cov = result.get("coverage") or {}
    for label in (cov.get("none") or {}).get("labels") or []:
        out.setdefault(where(label), []).append((label, "run", ""))
    for reason, (action, target) in SKIP_ACTION.items():
        for label in ((cov.get("skipped") or {}).get(reason) or {}).get("labels") or []:
            if not NOISE_SKIP.match(label):
                out.setdefault(None, []).append((label, action, target))
    return out


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
    by_hash = {r.get("hash"): r.get("title") or r.get("hash") for r in routes}
    for r in routes:
        result = (entries.get(r.get("hash")) or {}).get("result") or {}
        node = {"type": "page", "name": r.get("title") or r.get("hash"), "route": str(r.get("hash", "")).lstrip("#"), "children": []}
        html = _main(result.get("page") or "")
        # class 里要有单独的 tab（tab / hub-tab / lp-tab）：data-table 不算，不然表头「报修分类」会被认成页签
        tabs_of[node["name"]] = _tab_names(html)
        _fill(node, html, result.get("nodes") or [], None, _extras(result, by_hash))
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


# ---------- 和原型对齐 ----------
# 原型里看得出来的：画布上改了要同步到原型
VISIBLE = ("type", "fields", "cols", "action", "target", "when")
# 只写在画布上、原型里看不出来的：按编号带过去，不算要同步的改动
NOTES = ("desc", "who", "req", "tags", "entry", "back", "params", "after", "route", "data")


def _walk(nodes: list[dict], parent: str = ""):
    for i, n in enumerate(nodes):
        yield n, parent, i
        yield from _walk(n.get("children") or [], n.get("id", ""))


def _index(nodes: list[dict]) -> dict[str, tuple[dict, str, int]]:
    return {n["id"]: (n, parent, i) for n, parent, i in _walk(nodes) if n.get("id")}


def gone(node: dict) -> bool:
    """原型里以前有、现在没了，画布上还留着"""
    return bool(node.get("seen")) and not node.get("proto")


def diff(before: list[dict], after: list[dict]) -> list[dict]:
    """画布比 base 多做了什么：整棵加进来 / 删掉的只记最上面那一个。原型里已经没有的那些不算（那是原型那边的事）"""
    old, now, ops = _index(before), _index(after), []
    for nid, (node, parent, i) in now.items():
        if nid not in old:
            if (not parent or parent in old) and not gone(node):
                ops.append({"op": "add", "node": copy.deepcopy(node), "parent": parent, "index": i})
            continue
        prev, prev_parent, _ = old[nid]
        if prev["name"] != node["name"]:
            ops.append({"op": "rename", "id": nid, "name": node["name"]})
        if prev_parent != parent:
            ops.append({"op": "move", "id": nid, "parent": parent, "index": i})
        props = {k: node.get(k) for k in VISIBLE if prev.get(k) != node.get(k)}
        if props:
            ops.append({"op": "edit", "id": nid, "props": props})
    for nid, (node, parent, _) in old.items():
        if nid not in now and (not parent or parent in now):
            ops.append({"op": "remove", "id": nid})
    return ops


def _list_of(tree: list[dict], parent: str) -> list[dict] | None:
    if not parent:
        return tree
    hit = _index(tree).get(parent)
    return hit[0].setdefault("children", []) if hit else None


def _detach(tree: list[dict], nid: str) -> dict | None:
    hit = _index(tree).get(nid)
    if not hit:
        return None
    lst = _list_of(tree, hit[1])
    lst.remove(hit[0])
    return hit[0]


def _graft(target: dict, planned: dict) -> None:
    """规划的那一页原型里已经有了（AI 做出来了）：原型里有的为准，还没做的子项、字段接上去，照旧算「还没有」"""
    for key in ("fields", "cols"):
        names = {parse_field(f)["name"] for f in target.get(key) or []}
        extra = [f for f in planned.get(key) or [] if parse_field(f)["name"] not in names]
        if extra:
            target[key] = (target.get(key) or []) + extra
    for child in planned.get("children") or []:
        same = _match(target.setdefault("children", []), child)
        if same:
            _graft(same, child)
        else:
            target["children"].append(child)


def replay(tree: list[dict], ops: list[dict]) -> list[dict]:
    """在新读出来的树上重放画布上还没同步的改动；对不上的（原型那边已经照着改了、或者那一项没了）就跳过"""
    for op in [o for o in ops if o["op"] == "remove"]:
        _detach(tree, op["id"])
    for op in ops:
        node = _index(tree).get(op.get("id", ""), (None,))[0]
        if op["op"] == "rename" and node:
            node["name"] = op["name"]
        elif op["op"] == "edit" and node:
            for k, v in op["props"].items():
                if v in (None, "", []):
                    node.pop(k, None)
                else:
                    node[k] = v
        elif op["op"] == "move" and node and op["parent"] != op["id"]:
            target = _list_of(tree, op["parent"])
            if target is not None:
                _detach(tree, op["id"])
                target.insert(min(op["index"], len(target)), node)
        elif op["op"] == "add":
            target = _list_of(tree, op["parent"])
            if target is None:            # 挂在哪儿已经找不到了（那一页原型里没了 / 以前读错了）：跳过，不要堆到最外层
                continue
            same = _match(target, op["node"])
            if same:
                _graft(same, op["node"])
            else:
                target.insert(min(op["index"], len(target)), op["node"])
    return tree


def _key(name: str) -> str:
    """比名字用：「1#光伏逆变器 · 设备详情」这种带着那一行名字的只看后半截，括号补充、末尾的弹窗 / 抽屉不算"""
    return loose_name(str(name).rsplit(" · ", 1)[-1])


def _names_in(node: dict) -> set[str]:
    return {parse_field(f)["name"] for f in (node.get("cols") or []) + (node.get("fields") or [])}


def _match(items: list[dict], node: dict, alias: dict | None = None) -> dict | None:
    names = lambda o: {o["name"], (alias or {}).get(o.get("id"), o["name"])}   # noqa: E731
    same = [o for o in items if node["name"] in names(o)] or [o for o in items if _key(node["name"]) in {_key(x) for x in names(o)}]
    if not same:
        # 以前读成「列表」「筛选 / 表单」的那张，现在按标题起了名：同一种、列 / 字段大半一样就是它
        mine = _names_in(node)
        same = [o for o in items if o["type"] == node["type"] and (o["name"] in GENERIC or node["name"] in GENERIC) and mine
                and len(mine & _names_in(o)) >= 0.6 * min(len(mine), len(_names_in(o)) or 1)]
    return next((o for o in same if o["type"] == node["type"]), same[0] if same else None)


def _align(fresh: list[dict], old: list[dict], alias: dict) -> None:
    """新读出来的树对上旧 base 的编号：按名字（画布上改过名的也认），对不上的给新编号；都标成原型里有"""
    for node in fresh:
        prev = _match(old, node, alias)
        if prev:
            old = [o for o in old if o is not prev]
        node["id"] = prev["id"] if prev else "n" + uuid.uuid4().hex[:8]
        node["proto"] = node["seen"] = True
        _align(node.get("children") or [], (prev or {}).get("children") or [], alias)


def refresh_canvas(canvas: list[dict], base: list[dict] | None, fresh: list[dict]) -> tuple[list[dict], list[dict]]:
    """返回 (新画布, 新 base)。base 没有（第一次读）：画布上原型里读到过的当作 base，没读到过的（自己规划的）算改动"""
    if base is None:
        def keep(nodes):
            return [{**n, "children": keep(n.get("children") or [])} for n in nodes if n.get("seen") or n.get("proto")]
        base = keep(copy.deepcopy(canvas))
    ops = diff(base, canvas)
    alias = {op["id"]: op["name"] for op in ops if op["op"] == "rename"}
    _align(fresh, copy.deepcopy(base), alias)
    new_base = copy.deepcopy(fresh)
    tree = replay(copy.deepcopy(fresh), ops)
    # 只写在画布上的介绍、谁用这些：按编号带过去
    notes = {nid: n for nid, (n, _, _) in _index(canvas).items()}
    for nid, (node, _, _) in _index(tree).items():
        prev = notes.get(nid)
        for key in NOTES:
            if prev and prev.get(key) and not node.get(key):
                node[key] = prev[key]
    # 原型里删掉了、画布上还留着的：留着，标「原型里已经没有」，删不删你决定
    names = {(n["name"], n["type"]) for n, _, _ in _walk(tree)}
    have = _index(tree)
    for nid, (node, parent, i) in _index(canvas).items():
        if nid in have or (node["name"], node["type"]) in names or (parent and parent not in have) or not (node.get("seen") or node.get("proto")):
            continue
        lst = _list_of(tree, parent)
        if lst is not None:
            left = copy.deepcopy(node)
            for n, _, _ in _walk([left]):
                n["proto"], n["seen"] = False, True
            lst.insert(min(i, len(lst)), left)
            have = _index(tree)
    return tree, new_base
