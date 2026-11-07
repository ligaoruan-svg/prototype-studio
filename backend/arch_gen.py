"""画布 → 页面（3C）：带表格的菜单页照画布直接写成 ListPage 配置，不用 AI 一行行手写；
状态流转照业务梳理写成 Store.flow。首页看板、统计、详情页这类手写页面和演示数据（Store.define）留给 AI 补。

字段的 key 就用画布上的名字（「工单编号」），状态列固定叫 status：AI 补演示数据时照列名写就对得上。
"""
from __future__ import annotations

import json
import re

from .arch_fields import parse_field

CJK = re.compile(r"[一-鿿]")
MONEY = re.compile(r"(费|金额|价|总额|合计)(（元）)?$")
ADD = re.compile(r"^(新增|添加|新建|登记|创建)")
FORM = {"select": "select", "radio": "select", "multi": "select", "person": "select", "textarea": "textarea", "note": "textarea",
        "date": "date", "daterange": "date", "datetime": "datetime", "number": "number", "money": "money",
        "upload": "file", "image": "file", "check": "check", "switch": "check"}
ACTION = re.compile(r"^([^：:（(]+)[：:]\s*(.+?)\s*(?:→|->)\s*([^（(]+?)\s*(?:[（(].*)?$")


class JS(str):
    """原样写进去的一段 JS（函数）"""


def js(v) -> str:
    if isinstance(v, JS):
        return str(v)
    if isinstance(v, dict):
        return "{" + ",".join((k if re.fullmatch(r"[A-Za-z_]\w*", k) else json.dumps(k, ensure_ascii=False)) + ":" + js(x)
                              for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(js(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def key_of(name: str) -> str:
    """数据里的字段名：状态固定叫 status；后面括号里的说明、单位不算（「人工费（元）」「评价内容（数据：小程序回传）」→ 人工费 / 评价内容）"""
    name = re.sub(r"\s*[（(][^）)]*[）)]\s*$", "", name).strip() or name
    return "status" if name == "状态" else name


def label_of(name: str) -> str:
    """给人看的名字：单位留着（人工费（元）），说明去掉"""
    return re.sub(r"\s*[（(][^）)]*[：:，,≥≤][^）)]*[）)]\s*$", "", name).strip() or name


def flows(spec: dict) -> dict[str, dict[str, list]]:
    """业务梳理里的动作 → {对象: {动作: [从, 到]}}。到哪儿有两种的（已对平 / 有差异）先写第一种"""
    out: dict = {}
    for o in (spec or {}).get("objects") or []:
        for a in o.get("actions") or []:
            m = ACTION.match(str(a).strip())
            if not m:
                continue
            verb, src, dst = (x.strip() for x in m.groups())
            src = [x for x in re.split(r"\s*[/、,，]\s*|或", src) if x and not re.fullmatch(r"[—\-–－]+|无|空|新建", x)]
            if not src:      # 「生成：—→待核对」是新建一条，不是流转：页面顶上叫「生成…」的按钮做成新增，初始状态是「待核对」
                out.setdefault("_new", {}).setdefault(o["name"], {})[verb] = re.split(r"\s*[/／]\s*", dst)[0]
                continue
            out.setdefault(o["name"], {})[verb] = [src[0] if len(src) == 1 else src, re.split(r"\s*[/／]\s*", dst)[0]]
    return out


def _grams(text: str) -> set[str]:
    text = re.sub(r"(管理|列表|清单|档案|记录)$", "", text)
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _object(page: dict, table: dict, spec: dict) -> dict | None:
    """这一页管的是梳理里的哪个对象：页签和它的状态对得上最准，其次看名字"""
    tabs = {re.sub(r"\d+$", "", t["name"]) for t in page.get("children") or [] if t["type"] == "tab"}
    names = _grams(page["name"]) | _grams(table["name"])
    best, score = None, 0
    for o in (spec or {}).get("objects") or []:
        s = 10 * len(tabs & set(o.get("states") or [])) + len(names & _grams(o["name"])) + (5 if o["name"] in (page["name"], table["name"]) else 0)
        if s > score:
            best, score = o, s
    return best


def _find(page: dict, name: str, types: tuple) -> dict | None:
    """页面里（含页签、弹窗里）叫这个名字的弹窗 / 抽屉，有字段的优先"""
    hits = []
    stack = list(page.get("children") or [])
    while stack:
        n = stack.pop(0)
        if n["type"] in types and n["name"] == name:
            hits.append(n)
        stack += n.get("children") or []
    return next((h for h in hits if h.get("fields")), hits[0] if hits else None)


def _real(options: list[str]) -> bool:
    """括号里写的是说明不是选项（「只列在岗、技能覆盖本单分类…」）：不当选项，留给 AI 从数据里取"""
    return bool(options) and all(len(o) <= 8 for o in options)


def _pick(data: str, key: str) -> JS:
    """下拉没写选项：从这份数据里已有的值取（演示数据补上以后就有）"""
    return JS(f"()=>[...new Set(Store.all({js(data)}).map(r=>r[{js(key)}]).filter(Boolean))]")


def _form(fields: list[str], data: str = "") -> list[dict]:
    out = []
    for raw in fields:
        f = parse_field(raw)
        item = {"key": key_of(f["name"]), "label": label_of(f["name"]), "type": FORM.get(f["type"], "text")}
        if _real(f["options"]):
            item["options"] = f["options"]
        elif item["type"] == "select" and data:
            item["options"] = _pick(data, item["key"])
        if f["must"]:
            item["required"] = True
        if f["locked"]:
            item.update(readonly=True, value=JS(f"r=>r?r[{json.dumps(key_of(f['name']), ensure_ascii=False)}]:''"))
        out.append(item)
    return out


def _filters(block: dict | None, has_tabs: bool, data: str = "") -> list[dict]:
    out, seen = [], set()
    for raw in (block or {}).get("fields") or []:
        f = parse_field(raw)
        name, kind = f["name"], f["type"]
        if (name == "状态" and has_tabs) or name in seen:
            continue
        if re.search(r"[起止]$", name) and kind in ("date", "datetime"):      # 「提交时间起」「提交时间止」合成一个日期范围
            name, kind = name[:-1], "daterange"
            if name in seen:
                continue
        seen.add(name)
        item = {"key": key_of(name), "label": name}
        if kind in ("select", "radio", "multi", "person"):
            item.update(type="select", options=f["options"] if _real(f["options"]) else _pick(data, item["key"]))
        elif kind in ("daterange", "date", "datetime"):
            item["type"] = "daterange"
        elif kind in ("check", "switch"):
            item["type"] = "check"
        out.append(item)
    return out


def _columns(cols: list[str]) -> list[dict]:
    out = []
    for i, c in enumerate(cols):
        item = {"key": key_of(c), "label": label_of(c)}
        if c == "状态":
            item["tag"] = True
        elif MONEY.search(c) and "编号" not in c:
            item["money"] = True
        if i == 0:
            item["width"] = 140
        out.append(item)
    return out


def _states(when: str) -> list[str]:
    """「状态是待接单、处理中，且已过预约时间时」→ [待接单, 处理中]（后面的「且…」交给 AI 补进 show）"""
    m = re.match(r"状态是(.+?)(?:[，,]\s*且.*)?时$", (when or "").strip())
    return [x for x in re.split(r"[、,，/]|或", m.group(1)) if x] if m else []


def _button(b: dict, page: dict, verbs: dict, first: str, row: bool, data: str = "", made: dict | None = None) -> dict | None:
    name = b["name"]
    new_as = next((to for verb, to in (made or {}).items() if name.startswith(verb)), "") if not row else ""
    if new_as:
        first = new_as
    if not CJK.search(name) or b.get("action") == "jump":     # 点编号跳详情页：详情页是手写的，留给 AI
        return None
    item: dict = {"label": name}
    if row and name in verbs:
        item["flow"] = name
    elif row and _states(b.get("when", "")):
        item["show"] = JS(f"r=>{js(_states(b['when']))}.includes(r.status)")
    target = b.get("target") or ""
    layer = _find(page, target, ("modal", "drawer", "wizard")) if b.get("action") == "open" else None
    if layer and layer["type"] == "drawer":
        item["detail"] = True
    elif layer:
        item["form"] = _form(layer.get("fields") or [], data)
        if layer["name"] != name:
            item["title"] = layer["name"]
        if not row and (ADD.match(name) or new_as):
            item.update(add=True, primary=True, defaults={"status": first} if first else {})
        elif row and not item.get("flow") and re.match(r"^(编辑|修改)", name):
            item["edit"] = True
        if not item["form"] and (row and item.get("flow") or item.get("add")):   # 弹窗里没字段：当二次确认
            item.pop("form")
            item["confirm"] = f"确认{name}？"
    elif b.get("action") == "confirm":
        item["confirm"] = target or f"确认{name}？"
        if re.match(r"^删除", name) and not item.get("flow"):
            item["remove"] = True
    elif new_as:
        item.update(add=True, primary=True, defaults={"status": new_as}, confirm=f"确认{name}？")
    elif not item.get("flow"):
        item["run"] = JS(f"()=>UI.Toast({js((target or name) + '（演示）')})")
    return item


def list_page(page: dict, spec: dict, flow_map: dict) -> dict | None:
    """一页菜单页 → ListPage 配置；页面上没有表格（看板、统计）返回 None，留给 AI"""
    kids = page.get("children") or []
    tables = [k for k in kids if k["type"] == "table"]
    # 没表格，或者有指标卡、图表这类区块（看板、统计页）：手写更合适，留给 AI
    if not tables or any(k["type"] == "block" and k["name"] != "筛选" for k in kids):
        return None
    table = max(tables, key=lambda t: (sum(1 for b in t.get("children") or [] if b.get("when")), len(t.get("children") or [])))
    obj = _object(page, table, spec)
    data = obj["name"] if obj else re.sub(r"列表$", "", table["name"]) or page["name"]
    verbs = flow_map.get(data, {})
    first = ((obj or {}).get("states") or [""])[0]
    tabs = []
    for t in kids:
        name = re.sub(r"\d+$", "", t["name"]) if t["type"] == "tab" else ""
        if name and name not in tabs:
            tabs.append(name)
    cfg: dict = {"title": page["name"]}
    if page.get("desc"):
        cfg["desc"] = page["desc"]
    cfg["data"] = data
    if tabs:
        cfg["tabs"] = tabs
    filters = _filters(next((k for k in kids if k["type"] == "block" and k["name"] == "筛选"), None), bool(tabs), data)
    if filters:
        cfg["filters"] = filters
    cfg["columns"] = _columns(table.get("cols") or [])
    if table["name"] != page["name"] + "列表":
        cfg["listTitle"] = table["name"]
    actions, toolbar, names = [], [], set()
    for b in table.get("children") or []:
        item = b["type"] == "button" and b["name"] not in names and _button(b, page, verbs, first, True, data)
        if item:
            names.add(b["name"])
            actions.append(item)
    made = flow_map.get("_new", {}).get(data, {})
    for b in kids:
        item = b["type"] == "button" and _button(b, page, verbs, first, False, data, made)
        if item:
            toolbar.append(item)
    if actions:
        cfg["actions"] = actions
    if toolbar:
        cfg["toolbar"] = toolbar
    drawer = next((a for a in actions if a.get("detail")), None)
    if drawer:
        layer = _find(page, next(b.get("target") for b in table["children"] if b["name"] == drawer["label"]), ("drawer",))
        fields = [parse_field(f)["name"] for f in (layer or {}).get("fields") or []]
        if fields:
            cfg["detail"] = {"title": layer["name"], "fields": [{"key": key_of(f), "label": label_of(f), **({"tag": True} if f == "状态" else {})} for f in fields]}
    return cfg


def generate(arch: dict, only: set[str] | None = None) -> dict:
    """整棵树 → shell_add 要的 {nav, pages, script} + 交给 AI 的事。only：只生成这几页（原型里还没有的）"""
    spec, flow_map = arch.get("spec") or {}, flows(arch.get("spec") or {})
    groups, pages, made, left, used, keys = [], [], [], [], set(), {}
    n = 0
    for i, mod in enumerate(arch.get("nodes") or []):
        members = [mod] if mod["type"] == "page" else [p for p in mod.get("children") or [] if p["type"] == "page"] if mod["type"] == "module" else []
        items = []
        for p in members:
            n += 1
            key = re.sub(r"[^\w-]", "", str(p.get("route") or "").lstrip("#")) or f"p{n}"
            items.append({"key": key, "label": p["name"]})
            keys[p["name"]] = key
            if only is not None and p["name"] not in only:
                continue
            cfg = list_page(p, spec, flow_map)
            if cfg:
                used.add(cfg["data"])
                name = key if re.fullmatch(r"[A-Za-z_]\w*", key) else json.dumps(key)   # order-fee 这种带 - 的要加引号
                pages.append(f"{name}(){{return ListPage({js(cfg)})}}")
                made.append(p["name"])
            else:
                left.append(p["name"])
        if items:
            groups.append({"key": f"g{i + 1}", "label": mod["name"] if mod["type"] == "module" else "", "items": items})
    script = "\n".join(f"Store.flow({js(name)},{js(fl)});" for name, fl in flow_map.items() if name != "_new")
    return {"nav": ",\n  ".join(js(g) for g in groups), "pages": ",\n  ".join(pages), "script": script,
            "made": made, "left": left, "keys": keys, "data": sorted(used | set(flow_map) - {"_new"})}


def handoff(gen: dict) -> str:
    """交给 AI 的话：哪些页程序写好了、它还要补什么"""
    left = "、".join(f"{n}（key: {gen['keys'][n]}）" for n in gen["left"]) or "没有"
    return ("\n\n程序已经照画布把这些列表页写好了（Pages 里的 ListPage 配置；菜单 NAV、状态流转 Store.flow 也写好了）："
            + "、".join(gen["made"]) + "。这几页不要整页重写，要改就用 replace_source_text 小改。你接着做（用 shell_add）：\n"
            "1. 演示数据：script 里 Store.define 这几份：" + "、".join(gen["data"]) + "。字段名就用各页 columns / form / detail 里的 key（中文名），"
            "状态字段叫 status，每个状态 2–3 条，编号唯一、日期围绕今天；引用别的数据的（维修工、分类）要在那份数据里真有；\n"
            "2. 手写这几页（pages 里加同名 key 的方法）：" + left + "；\n"
            "3. 业务梳理里的规则：能在按钮上校验的，给对应 ListPage 按钮加 check:(值,行)=>'不通过的提示'；按钮只是提示演示的（run 弹 Toast）照业务接上真实行为。")
