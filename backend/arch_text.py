"""架构的文字写法：手动编的「大纲」、AI 起草时的回复、从 Excel 粘贴的功能清单，都落到这里。

大纲长这样（缩进就是层级，方括号是类型，冒号后面是介绍，竖线隔开其它属性）：

    系统：智慧双碳管理平台
    介绍：给园区管碳排放
    角色：管理员、核算员

    【页面】
    碳排放核算管理 [模块]：算清楚每家企业排了多少
      碳排核算模板配置 [菜单页]：按行业管核算模板 | 数据：核算模板 | 地址：template
        模板详情 [下钻页]：范围、子类别、设施 | 入口：点模板编号 | 带过去：模板编号 | 返回：返回模板列表
        新增模板 [弹窗]

    【数据】
    核算模板 TMP-xxx [配置]：一套行业的核算方法
      模板编号 🔑
      因子库 → 因子库：1 个
      关联排放源数 = 由边界自动统计
      因子值 🔒 来自因子库
      状态：草稿 → 启用 → 停用
    维修工单 [外部]

    【关系】
    因子库 → 核算模板：1 → N

    【流程】
    泳道：管理员（电脑）、系统自动 [系统]、巡检执行 [不做]（手机端）、维修系统 [外部]
    管理员 · 配路线：给点排顺序 | 下一步：建计划
    管理员 · 建计划 | 下一步：生成任务

只写页面那一段也行（没有【】标题时整段都算页面）。类型不写时按层级猜：第一层模块、第二层菜单页、再往下功能。
"""
from __future__ import annotations

import re
from typing import Any

from .architecture import NODE_TYPES, walk

TYPE_WORDS = {
    "module": ["模块", "子系统", "系统模块"], "page": ["菜单页", "页面", "菜单", "一级页面"], "tab": ["页签", "标签页", "tab", "Tab"],
    "drill": ["下钻页", "下钻", "详情页", "子页面"], "modal": ["弹窗", "弹框", "对话框", "表单弹窗"], "drawer": ["抽屉", "侧滑", "详情抽屉"],
    "wizard": ["向导", "步骤", "分步"], "jump": ["跳转", "链接"], "block": ["区块", "区域", "板块", "卡片"], "table": ["表格", "列表", "表"],
    "button": ["按钮", "操作", "链接按钮", "行操作"], "feature": ["功能", "功能点", "规则", "联动"],
}
WORD_TYPE = {w: t for t, words in TYPE_WORDS.items() for w in words}
LANE_WORDS = {"系统": "system", "系统自动": "system", "不做": "skip", "本次不做": "skip", "外部": "external", "外部系统": "external", "人": "user"}
LANE_LABEL = {"user": "", "system": "系统", "skip": "不做", "external": "外部"}
PROPS = [("when", "出现"), ("fields", "字段"), ("cols", "列"), ("after", "确认后"), ("data", "数据"), ("route", "地址"), ("who", "谁用"),
         ("entry", "入口"), ("params", "带过去"), ("back", "返回"), ("tags", "标签"), ("req", "需求")]
PROP_WORDS = {"数据": "data", "地址": "route", "路由": "route", "谁用": "who", "入口": "entry", "怎么进来": "entry", "带过去": "params", "参数": "params",
              "返回": "back", "怎么回去": "back", "标签": "tags", "需求": "req", "需求编号": "req", "字段": "fields", "表单": "fields",
              "列": "cols", "表头": "cols", "出现": "when", "什么时候出现": "when", "确认后": "after", "保存后": "after"}
# 按钮点了以后：「打开：新增设施弹窗」「跳到：模板详情」「执行：导出 Excel」「二次确认：删除后不能恢复」
ACTION_WORDS = {"打开": "open", "弹出": "open", "跳到": "jump", "跳转": "jump", "执行": "run", "二次确认": "confirm", "确认框": "confirm"}
ACTION_LABEL = {"open": "打开", "jump": "跳到", "run": "执行", "confirm": "二次确认"}
LIST_PROPS = {"data", "who", "tags", "req", "fields", "cols"}
SECTIONS = {"页面": "nodes", "页面树": "nodes", "数据": "entities", "数据关系": "entities", "关系": "relations", "流程": "flow", "业务流程": "flow"}
SEP = re.compile(r"\s*[|｜]\s*")
SPLIT = re.compile(r"[,，、;；]\s*")
TAG_SPLIT = re.compile(r"[;；]\s*")


def split_outside(text: str, seps: str = "、,，;；") -> list[str]:
    """按分隔符切开，但括号里面的不切：「管理员（电脑、看结果）、系统自动」是两项"""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch in "（([［【":
            depth += 1
        elif ch in "）)]］】":
            depth = max(0, depth - 1)
        if ch in seps and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


# ---------- 写成大纲 ----------
def to_outline(arch: dict | None) -> str:
    if not arch:
        return ""
    lines = []
    if arch.get("name"):
        lines.append(f"系统：{arch['name']}")
    if arch.get("summary"):
        lines.append(f"介绍：{arch['summary'].replace(chr(10), ' ')}")
    if arch.get("roles"):
        lines.append("角色：" + "、".join(arch["roles"]))
    lines += ["", "【页面】"]
    for node, depth, _ in walk(arch.get("nodes") or []):
        text = "  " * depth + f"{node['name']} [{NODE_TYPES[node['type']]}]"
        if node.get("desc"):
            text += "：" + node["desc"].replace("\n", " ")
        if node.get("action"):
            text += f" | {ACTION_LABEL[node['action']]}：{node.get('target') or ''}"
        for key, label in PROPS:
            value = node.get(key)
            if value:
                text += f" | {label}：" + (("；" if key == "tags" else "、").join(value) if isinstance(value, list) else value)
        lines.append(text)
    if arch.get("entities"):
        lines += ["", "【数据】"]
        for e in arch["entities"]:
            head = e["name"] + (f" {e['code']}" if e.get("code") else "")
            tag = "外部" if e.get("external") else e.get("role")
            if tag:
                head += f" [{tag}]"
            if e.get("desc"):
                head += "：" + e["desc"].replace("\n", " ")
            lines.append(head)
            for f in e.get("fields") or []:
                note = f.get("note", "")
                if f["kind"] == "key":
                    lines.append(f"  {f['name']} 🔑" + (f" {note}" if note else ""))
                elif f["kind"] == "ref":
                    lines.append(f"  {f['name']} → {f.get('ref', '')}" + (f"：{note}" if note else ""))
                elif f["kind"] == "derived":
                    lines.append(f"  {f['name']} = {note.lstrip('=＝ ') or '自动算'}")
                elif f["kind"] == "locked":
                    lines.append(f"  {f['name']} 🔒" + (f" {note}" if note else ""))
                else:
                    lines.append(f"  {f['name']}" + (f"：{note}" if note else ""))
            if e.get("states"):
                lines.append("  状态：" + " → ".join(e["states"]))
    if arch.get("relations"):
        lines += ["", "【关系】"]
        lines += [f"{r['from']} → {r['to']}" + (f"：{r['label']}" if r.get("label") else "") for r in arch["relations"]]
    if arch.get("steps"):
        lines += ["", "【流程】"]
        lanes = arch.get("lanes") or []
        lines.append("泳道：" + "、".join(l["name"] + (f" [{LANE_LABEL[l['kind']]}]" if LANE_LABEL.get(l["kind"]) else "")
                                         + (f"（{l['note']}）" if l.get("note") else "") for l in lanes))
        names = {l["id"]: l["name"] for l in lanes}
        step_names = {s["id"]: s["name"] for s in arch.get("steps") or []}
        for s in arch.get("steps") or []:
            text = f"{names.get(s['lane'], '')} · {s['name']}"
            if s.get("desc"):
                text += f"：{s['desc']}"
            nxt = [step_names[n] for n in s.get("next") or [] if n in step_names]
            if nxt:
                text += " | 下一步：" + "、".join(nxt)
            lines.append(text)
    return "\n".join(lines).strip() + "\n"


# ---------- 读大纲 ----------
def _indent(line: str) -> int:
    raw = line[: len(line) - len(line.lstrip())]
    return raw.count("\t") * 4 + raw.count(" ") + raw.count("　") * 2


def _strip_bullet(text: str) -> str:
    return re.sub(r"^([-*•·]|\d+[.、)])\s+", "", text.strip())


def _node_from_line(text: str, depth: int) -> dict:
    parts = SEP.split(text)
    head = parts[0]
    m = re.match(r"^(?P<name>.*?)\s*(?:[\[［【](?P<type>[^\]］】]+)[\]］】])?\s*(?:[:：]\s*(?P<desc>.*))?$", head)
    name, kind, desc = (m.group("name") or head).strip(), (m.group("type") or "").strip(), (m.group("desc") or "").strip()
    node: dict[str, Any] = {"name": name, "type": WORD_TYPE.get(kind) or (kind if kind in NODE_TYPES else ""), "children": []}
    if not node["type"]:
        node["type"] = "module" if depth == 0 else "page" if depth == 1 else "feature"
    if desc:
        node["desc"] = desc
    for part in parts[1:]:
        km = re.match(r"^(?P<k>[^:：]+)[:：]\s*(?P<v>.*)$", part)
        if not km:
            continue
        word, value = km.group("k").strip(), km.group("v").strip()
        if word in ACTION_WORDS:
            node["action"] = ACTION_WORDS[word]
            if value:
                node["target"] = value
            continue
        key = PROP_WORDS.get(word)
        if key and value:
            # 标签里常有逗号顿号（「联动：改了 A，B 跟着变」），只按分号分；别的按顿号逗号分
            # 字段、列括号里可以有顿号（「类型（下拉：A、B）」），括号里的不切
            if key in ("fields", "cols"):
                node[key] = split_outside(value)
            else:
                splitter = TAG_SPLIT if key == "tags" else SPLIT
                node[key] = [v.strip() for v in splitter.split(value) if v.strip()] if key in LIST_PROPS else value
    return node


def _tree(lines: list[str]) -> list[dict]:
    """缩进几个空格都行：和上面一行比，缩进多了就是它的子项"""
    roots: list[dict] = []
    stack: list[tuple[int, dict]] = []
    for line in lines:
        if not line.strip():
            continue
        indent = _indent(line)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        node = _node_from_line(_strip_bullet(line), len(stack))
        (stack[-1][1]["children"] if stack else roots).append(node)
        stack.append((indent, node))
    return roots


def _field(text: str) -> dict:
    text = _strip_bullet(text)
    m = re.match(r"^(?P<n>.+?)\s*(?:→|->)\s*(?P<ref>[^:：\s]+)\s*(?:[:：]\s*(?P<note>.*))?$", text)
    if m:
        return {"name": m.group("n").strip(), "kind": "ref", "ref": m.group("ref").strip(), "note": (m.group("note") or "").strip()}
    m = re.match(r"^(?P<n>.+?)\s*[=＝]\s*(?P<note>.*)$", text)
    if m:
        return {"name": m.group("n").strip(), "kind": "derived", "note": m.group("note").strip().lstrip("=＝ ")}
    for mark, kind in (("🔑", "key"), ("🔒", "locked")):
        if mark in text:
            name, _, note = text.partition(mark)
            return {"name": name.strip(), "kind": kind, "note": note.strip()}
    parts = re.split(r"[:：]", text, maxsplit=1)
    return {"name": parts[0].strip(), "kind": "plain", "note": parts[1].strip() if len(parts) > 1 else ""}


def _entities(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for line in lines:
        if not line.strip():
            continue
        if _indent(line) == 0 or not out:
            text = _strip_bullet(line)
            m = re.match(r"^(?P<name>[^\s\[［:：]+)\s*(?P<code>[^\[［:：]*?)\s*(?:[\[［](?P<tag>[^\]］]+)[\]］])?\s*(?:[:：]\s*(?P<desc>.*))?$", text)
            if not m:
                out.append({"name": text, "fields": []})
                continue
            tag = (m.group("tag") or "").strip()
            out.append({"name": m.group("name"), "code": (m.group("code") or "").strip(), "role": "" if tag in ("外部", "外部系统") else tag,
                        "external": tag in ("外部", "外部系统"), "desc": (m.group("desc") or "").strip(), "fields": [], "states": []})
            continue
        text = _strip_bullet(line)
        sm = re.match(r"^状态\s*[:：]\s*(.*)$", text)
        if sm:
            out[-1]["states"] = [s.strip() for s in re.split(r"→|->|[,，、]", sm.group(1)) if s.strip()]
        else:
            out[-1]["fields"].append(_field(text))
    return out


def _relations(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        m = re.match(r"^(?P<a>[^→\->]+?)\s*(?:→|->)\s*(?P<b>[^:：]+?)\s*(?:[:：]\s*(?P<label>.*))?$", _strip_bullet(line))
        if m:
            out.append({"from": m.group("a").strip(), "to": m.group("b").strip(), "label": (m.group("label") or "").strip()})
    return out


def _lane(spec: str) -> dict:
    """「现场抄表（手机端） [不做]（只作为数据来源）」：方括号是类型，最后一对括号是备注，剩下的是名字"""
    kind = ""
    km = re.search(r"[\[［]([^\]］]+)[\]］]", spec)
    if km:
        kind, spec = km.group(1).strip(), (spec[:km.start()] + spec[km.end():]).strip()
    note = ""
    nm = re.search(r"[（(]([^（()）]*)[）)]\s*$", spec)
    if nm and nm.start() > 0:
        note, spec = nm.group(1).strip(), spec[:nm.start()].strip()
    return {"name": spec.strip(), "kind": LANE_WORDS.get(kind, "user"), "note": note}


def _flow(lines: list[str]) -> tuple[list[dict], list[dict]]:
    lanes: list[dict] = []
    raw = []
    for line in lines:
        text = _strip_bullet(line)
        if not text:
            continue
        lm = re.match(r"^泳道\s*[:：]\s*(.*)$", text)
        if lm:
            for spec in split_outside(lm.group(1)):
                lane = _lane(spec)
                if lane["name"]:
                    lanes.append({"id": "l" + str(len(lanes) + 1), **lane})
            continue
        parts = SEP.split(text)
        m = re.match(r"^(?P<lane>[^·•:：]+?)\s*[·•]\s*(?P<rest>.+)$", parts[0])
        lane, rest = (m.group("lane").strip(), m.group("rest")) if m else ("", parts[0])
        name, _, desc = rest.partition("：") if "：" in rest else rest.partition(":")
        nxt = []
        for part in parts[1:]:
            pm = re.match(r"^下一步\s*[:：]\s*(.*)$", part)
            if pm:
                nxt += [n for n in split_outside(pm.group(1)) if n]
        raw.append({"lane": lane, "name": name.strip(), "desc": desc.strip(), "next": nxt})
    # 老写法「步骤：说明 → 下一步」：最后一个箭头后面都是已有的步骤名，才算下一步，不然是说明里的箭头
    names = {r["name"] for r in raw}
    for r in raw:
        if r["next"]:
            continue
        for src in ("desc", "name"):
            if "→" in r[src]:
                head, _, tail = r[src].rpartition("→")
                cands = [n for n in split_outside(tail) if n]
                if cands and all(c in names for c in cands):
                    r[src], r["next"] = head.strip(), cands
                break
    if not lanes:
        for r in raw:
            if r["lane"] and r["lane"] not in [l["name"] for l in lanes]:
                lanes.append({"id": "l" + str(len(lanes) + 1), "name": r["lane"], "kind": "user", "note": ""})

    def lane_id(name: str) -> str:
        for l in lanes:
            if name in (l["name"], f"{l['name']}（{l['note']}）", f"{l['name']}({l['note']})"):
                return l["id"]
        return lanes[0]["id"] if lanes else ""
    ids: dict[str, str] = {}
    steps = []
    for i, r in enumerate(raw):
        sid = f"s{i + 1}"
        ids.setdefault(r["name"], sid)
        steps.append({"id": sid, "lane": lane_id(r["lane"]), "name": r["name"], "desc": r["desc"], "_next": r["next"]})
    for st in steps:
        st["next"] = [ids[n] for n in st.pop("_next") if n in ids]
    return lanes, steps


def from_outline(text: str) -> dict:
    """大纲 → 架构（还没收拾过，交给 architecture.normalize）"""
    meta: dict[str, Any] = {}
    sections: dict[str, list[str]] = {"nodes": [], "entities": [], "relations": [], "flow": []}
    current = "nodes"
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        head = re.match(r"^(?:#+\s*|【)\s*([^】#]+?)\s*】?\s*$", stripped)
        if head and head.group(1) in SECTIONS and (stripped.startswith("#") or stripped.startswith("【")):
            current = SECTIONS[head.group(1)]
            continue
        mm = re.match(r"^(系统|系统名|介绍|角色)\s*[:：]\s*(.*)$", stripped)
        if mm and _indent(line) == 0 and current == "nodes" and not sections["nodes"]:
            meta[{"系统": "name", "系统名": "name", "介绍": "summary", "角色": "roles"}[mm.group(1)]] = mm.group(2).strip()
            continue
        sections[current].append(line)
    arch: dict[str, Any] = {"name": meta.get("name", ""), "summary": meta.get("summary", ""),
                            "roles": [r for r in SPLIT.split(meta.get("roles", "")) if r],
                            "nodes": _tree(sections["nodes"]), "entities": _entities(sections["entities"]),
                            "relations": _relations(sections["relations"])}
    if any(l.strip() for l in sections["flow"]):
        arch["lanes"], arch["steps"] = _flow(sections["flow"])
    return arch


# ---------- 从 Excel 粘过来的功能清单 ----------
LEVEL_HEADS = re.compile(r"模块|子系统|系统|一级|二级|三级|四级|菜单|页面|页签|功能(?!描述|说明)|功能点|子功能")
DESC_HEADS = re.compile(r"说明|描述|备注|功能描述|详细|内容")
ID_HEADS = re.compile(r"编号|序号|ID|id|需求号")


def looks_like_table(text: str) -> bool:
    rows = [r for r in (text or "").splitlines() if r.strip()]
    return len(rows) >= 2 and sum("\t" in r for r in rows) >= max(2, len(rows) // 2)


def from_table(text: str) -> dict:
    """功能清单（Excel 复制出来是用 Tab 分开的几列）→ 架构。
    合并单元格复制出来只有第一行有值，下面几行是空的：空格子沿用上一行的。"""
    rows = [r.split("\t") for r in (text or "").replace("\r\n", "\n").split("\n") if r.strip()]
    if not rows:
        return {"nodes": []}
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = [c.strip() for c in rows[0]]
    has_header = sum(bool(LEVEL_HEADS.search(c) or DESC_HEADS.search(c) or ID_HEADS.fullmatch(c) or ID_HEADS.search(c)) for c in header) >= 2
    if has_header:
        body = rows[1:]
        ids = [i for i, c in enumerate(header) if ID_HEADS.search(c) and not LEVEL_HEADS.search(c)]
        descs = [i for i, c in enumerate(header) if DESC_HEADS.search(c) and i not in ids]
        levels = [i for i, c in enumerate(header) if i not in ids and i not in descs and LEVEL_HEADS.search(c)]
        if not levels:
            levels = [i for i in range(width) if i not in ids and i not in descs]
    else:
        body = rows
        # 没有表头：最后一列字多就当说明，第一列像编号就当编号，其余按顺序是层级
        last_long = sum(len(r[-1].strip()) > 12 for r in body) >= len(body) / 2
        first_id = all(re.fullmatch(r"[#\w.-]{1,12}", r[0].strip() or "x") and not re.search(r"[一-鿿]", r[0]) for r in body)
        ids = [0] if first_id and width > 2 else []
        descs = [width - 1] if last_long and width > 1 else []
        levels = [i for i in range(width) if i not in ids and i not in descs]
    kinds = ["module", "page", "tab", "feature"] if len(levels) >= 4 else ["module", "page", "feature"] if len(levels) == 3 else ["page", "feature"] if len(levels) == 2 else ["feature"]
    while len(kinds) < len(levels):
        kinds.append("feature")
    roots: list[dict] = []
    carry = [""] * width
    for row in body:
        cells = [c.strip() for c in row]
        # 合并单元格：这一行哪一层空着，就沿用上一行；某一层换了值，它下面的层不能再沿用
        changed = False
        for i in levels:
            if cells[i]:
                if cells[i] != carry[i]:
                    changed = True
                carry[i] = cells[i]
            elif changed:
                carry[i] = ""
        path = [(carry[i], kinds[n]) for n, i in enumerate(levels) if carry[i]]
        if not path:
            continue
        siblings, node = roots, None
        for name, kind in path:
            node = next((n for n in siblings if n["name"] == name), None)
            if not node:
                node = {"name": name, "type": kind, "children": []}
                siblings.append(node)
            siblings = node["children"]
        desc = "；".join(cells[i] for i in descs if cells[i])
        if desc and not node.get("desc"):
            node["desc"] = desc
        req = [cells[i] for i in ids if cells[i]]
        if req:
            node["req"] = sorted(set(node.get("req", []) + req))
    return {"nodes": roots}


# ---------- 合并：追加时同名的并到一起 ----------
def merge_nodes(target: list[dict], incoming: list[dict]) -> None:
    for node in incoming:
        same = next((n for n in target if n["name"] == node["name"]), None)
        if not same:
            target.append(node)
            continue
        for key in ("desc", "route", "entry", "params", "back"):
            if node.get(key) and not same.get(key):
                same[key] = node[key]
        for key in ("data", "who", "tags", "req"):
            if node.get(key):
                same[key] = list(dict.fromkeys((same.get(key) or []) + node[key]))
        merge_nodes(same.setdefault("children", []), node.get("children") or [])


def keep_ids(fresh: dict, current: dict | None) -> dict:
    """大纲改完再读回来：路径没变的节点、名字没变的数据和步骤沿用原来的 id，流程指向页面的链接就不会断"""
    if not current:
        return fresh
    old_nodes = {}
    for node, _, parents in walk(current.get("nodes") or []):
        old_nodes[tuple(p["name"] for p in parents) + (node["name"],)] = node["id"]

    def visit(nodes, path=()):
        for n in nodes:
            key = path + (n["name"],)
            if not n.get("id") and key in old_nodes:
                n["id"] = old_nodes[key]
            visit(n.get("children") or [], key)
    visit(fresh.get("nodes") or [])
    ents = {e["name"]: e["id"] for e in current.get("entities") or []}
    for e in fresh.get("entities") or []:
        if not e.get("id") and e["name"] in ents:
            e["id"] = ents[e["name"]]
    old_steps = {s["name"]: s for s in current.get("steps") or []}
    for s in fresh.get("steps") or []:
        if s["name"] in old_steps and old_steps[s["name"]].get("node"):
            s["node"] = old_steps[s["name"]]["node"]
    fresh.setdefault("rules", current.get("rules"))
    fresh["status"] = current.get("status", "draft")
    return fresh

