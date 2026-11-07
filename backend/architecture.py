"""架构模式：先把「系统 → 模块 → 页面 → 功能」、共用的数据和业务流程理清楚，确认了再按它一页一步生成。

一个项目一份，存在 data/projects/<pid>/architecture.json，分三块：
- nodes：页面树。模块 / 菜单页 / 页签 / 下钻页 / 弹窗 / 抽屉 / 向导 / 跳转 / 区块 / 功能
- entities + relations：数据关系。所有页面共用这一份数据；字段分编号、引用、自动算、继承
- lanes + steps：业务流程。谁、做什么；本次不做的端和外部系统用虚线泳道，只生成它们产生的数据

本次只做电脑端（scope = pc），生成时每页都按 PC_RULES 这套统一规则来。
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Iterator

from . import storage
from .arch_spec import normalize as normalize_spec
from .atomicio import write_atomic

NODE_TYPES = {"module": "模块", "page": "菜单页", "tab": "页签", "drill": "下钻页", "modal": "弹窗", "drawer": "抽屉",
              "wizard": "向导", "jump": "跳转", "block": "区块", "table": "表格", "button": "按钮", "feature": "功能"}
LAYER_TYPES = ("modal", "drawer", "wizard")    # 点按钮打开的那一层
# 按钮点了以后怎样：打开哪个弹窗 / 跳到哪一页 / 直接执行 / 先二次确认
ACTIONS = {"open": "打开", "jump": "跳到", "run": "执行", "confirm": "二次确认"}
SCREEN_TYPES = ("page", "tab", "drill")       # 会成为一个能看到的页面
FIELD_KINDS = {"key": "编号", "ref": "引用", "derived": "自动算", "locked": "继承", "plain": ""}
LANE_KINDS = {"user": "操作的人", "system": "系统自动", "skip": "本次不做", "external": "外部系统"}
PC_RULES = [
    "列表页：页头 → 筛选区（查询 / 重置）→ 操作栏（左边新增、右边导出）→ 表格 → 分页",
    "查看用右侧抽屉，只读；新增 / 编辑用居中弹窗，和查看共用一套表单",
    "多步操作用向导弹窗，带步骤条",
    "跳转带上编号：打开对应的抽屉，或切到对应页签；关掉回到原来的列表",
    "行操作按状态出现（比如离线才有「停用」、待执行才有「开始」）",
    "一个菜单下的几个页签共用菜单入口，每个页签都能单独直达",
    "外部系统回传的数据标明「由 XX 系统回传，只读」",
    "全局只有一份演示数据：引用的东西必须存在；个数、进度、摘要这类派生值从数据算，不能写死",
]
DEFAULT_LANES = [{"id": "l_user", "name": "管理员", "kind": "user", "note": "电脑"},
                 {"id": "l_sys", "name": "系统自动", "kind": "system", "note": ""}]
MAX_NODES, MAX_DEPTH, MAX_ENTITIES, MAX_FIELDS, MAX_STEPS = 2000, 10, 60, 40, 120
ID_RE = re.compile(r"^[a-z][\w-]{0,31}$")


def _new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:8]


def _s(value: Any, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit] if not isinstance(value, (dict, list)) else ""


def _text(value: Any, limit: int = 600) -> str:
    """介绍可以分行，其余空白收起来"""
    if isinstance(value, (dict, list)):
        return ""
    return re.sub(r"[ \t]+", " ", str(value or "")).strip()[:limit]


def loose_name(name: str) -> str:
    """按钮写的打开「新增报修工单（业主来电代录）」，弹窗叫「新增报修工单」：括号里的补充、末尾的「弹窗 / 抽屉」不算"""
    text = re.sub(r"[（(][^（()）]*[）)]", "", str(name or ""))
    return re.sub(r"\s+|(弹窗|弹框|抽屉|对话框|页面)$", "", text)


def _strings(value: Any, count: int = 20, limit: int = 60) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,，、;；\n]", value)
    out = []
    for item in value if isinstance(value, list) else []:
        text = _s(item, limit)
        if text and text not in out:
            out.append(text)
    return out[:count]


def empty() -> dict[str, Any]:
    return {"version": 1, "status": "draft", "scope": "pc", "name": "", "summary": "", "roles": [], "nodes": [],
            "entities": [], "relations": [], "lanes": [dict(l) for l in DEFAULT_LANES], "steps": [],
            "rules": list(PC_RULES), "updated_at": ""}


def normalize(raw: Any) -> dict[str, Any]:
    """把界面或模型给的架构收拾成固定的样子：类型只认已知的、编号唯一、长度和数量有上限。坏数据丢掉，不报错"""
    raw = raw if isinstance(raw, dict) else {}
    arch = empty()
    arch["status"] = "confirmed" if raw.get("status") == "confirmed" else "draft"
    arch["name"] = _s(raw.get("name"), 60)
    arch["summary"] = _text(raw.get("summary"), 400)
    arch["roles"] = _strings(raw.get("roles"), 12, 20)
    arch["updated_at"] = _s(raw.get("updated_at"), 40)
    seen: set[str] = set()

    def uid(value: Any, prefix: str) -> str:
        value = _s(value, 32)
        if not ID_RE.match(value) or value in seen:
            value = _new_id(prefix)
            while value in seen:
                value = _new_id(prefix)
        seen.add(value)
        return value

    count = 0

    def node(item: Any, depth: int) -> dict[str, Any] | None:
        nonlocal count
        if not isinstance(item, dict) or count >= MAX_NODES:
            return None
        kind = item.get("type") if item.get("type") in NODE_TYPES else ("module" if depth == 0 else "feature")
        name = _s(item.get("name"), 40)
        if not name:
            return None
        count += 1
        out = {"id": uid(item.get("id"), "n"), "type": kind, "name": name, "desc": _text(item.get("desc"), 400)}
        for key, limit in (("route", 60), ("entry", 160), ("params", 120), ("back", 160), ("target", 60), ("when", 120), ("after", 200)):
            if _s(item.get(key), limit):
                out[key] = _s(item.get(key), limit)
        if item.get("action") in ACTIONS:
            out["action"] = item["action"]
        for key, n, size in (("who", 8, 40), ("data", 12, 40), ("tags", 8, 80), ("req", 8, 40), ("fields", 40, 120), ("cols", 30, 30)):
            raw_value = item.get(key)
            if key == "tags" and isinstance(raw_value, list):   # 标签里常有逗号，是列表就不再拆
                values = list(dict.fromkeys(_s(t, size) for t in raw_value[:n] if _s(t, size)))
            else:
                values = _strings(raw_value, n, size)
            if values:
                out[key] = values
        if item.get("collapsed") is True:
            out["collapsed"] = True
        # 和原型对不对得上（从原型读的时候标）：proto 这次读到了；seen 以前读到过。都没有 = 你规划了、原型里还没有
        for flag in ("proto", "seen"):
            if item.get(flag) is True:
                out[flag] = True
        kids = item.get("children") if depth + 1 < MAX_DEPTH else []
        out["children"] = [c for c in (node(child, depth + 1) for child in (kids if isinstance(kids, list) else [])) if c]
        return out

    arch["nodes"] = [n for n in (node(item, 0) for item in (raw.get("nodes") if isinstance(raw.get("nodes"), list) else [])) if n]

    names: set[str] = set()
    for item in (raw.get("entities") if isinstance(raw.get("entities"), list) else [])[:MAX_ENTITIES]:
        if not isinstance(item, dict) or not _s(item.get("name"), 30) or _s(item.get("name"), 30) in names:
            continue
        name = _s(item.get("name"), 30)
        names.add(name)
        fields = []
        for f in (item.get("fields") if isinstance(item.get("fields"), list) else [])[:MAX_FIELDS]:
            if not isinstance(f, dict) or not _s(f.get("name"), 40):
                continue
            field = {"name": _s(f.get("name"), 40), "kind": f.get("kind") if f.get("kind") in FIELD_KINDS else "plain"}
            if _s(f.get("ref"), 30):
                field["ref"] = _s(f.get("ref"), 30)
            if _s(f.get("note"), 80):
                field["note"] = _s(f.get("note"), 80)
            fields.append(field)
        arch["entities"].append({"id": uid(item.get("id"), "e"), "name": name, "code": _s(item.get("code"), 20),
                                 "role": _s(item.get("role"), 16), "desc": _text(item.get("desc"), 300),
                                 "external": item.get("external") is True, "fields": fields,
                                 "states": _strings(item.get("states"), 10, 16)})
    # 关系两头写成「业主报修提交 [外部]」「设备档案（台账）」：去掉方括号、括号里的补充，对得上数据名就用数据名
    known = {e["name"] for e in arch["entities"]}

    def end(value):
        text = _s(value, 40)
        if text in known:
            return text
        bare = re.sub(r"\s*[\[［【][^\]］】]*[\]］】]\s*|\s*[（(][^（()）]*[）)]\s*", "", text).strip()
        return bare if bare in known else text[:30]
    for item in (raw.get("relations") if isinstance(raw.get("relations"), list) else [])[:200]:
        if isinstance(item, dict) and end(item.get("from")) and end(item.get("to")):
            arch["relations"].append({"from": end(item.get("from")), "to": end(item.get("to")), "label": _s(item.get("label"), 40)})

    lanes = []
    for item in (raw.get("lanes") if isinstance(raw.get("lanes"), list) else [])[:8]:
        if isinstance(item, dict) and _s(item.get("name"), 20):
            lanes.append({"id": uid(item.get("id"), "l"), "name": _s(item.get("name"), 20),
                          "kind": item.get("kind") if item.get("kind") in LANE_KINDS else "user", "note": _s(item.get("note"), 30)})
    if lanes or isinstance(raw.get("lanes"), list):
        arch["lanes"] = lanes
    else:
        for lane in arch["lanes"]:
            seen.add(lane["id"])
    lane_ids = {l["id"] for l in arch["lanes"]}
    lane_names = {l["name"]: l["id"] for l in arch["lanes"]}
    steps = []
    for item in (raw.get("steps") if isinstance(raw.get("steps"), list) else [])[:MAX_STEPS]:
        if not isinstance(item, dict) or not _s(item.get("name"), 30):
            continue
        lane = _s(item.get("lane"), 32)
        lane = lane if lane in lane_ids else lane_names.get(lane, arch["lanes"][0]["id"] if arch["lanes"] else "")
        step = {"id": uid(item.get("id"), "s"), "lane": lane, "name": _s(item.get("name"), 30), "desc": _s(item.get("desc"), 60),
                "next": _strings(item.get("next"), 6, 32)}
        if _s(item.get("node"), 32):
            step["node"] = _s(item.get("node"), 32)
        steps.append(step)
    arch["steps"] = steps
    rules = _strings(raw.get("rules"), 20, 120) if isinstance(raw.get("rules"), list) else []
    arch["rules"] = rules or list(PC_RULES)
    # 业务梳理（见 arch_spec）：出架构前先想清楚的那张卡片，确认后画树、以后改树都拿它当依据
    spec = normalize_spec(raw.get("spec"))
    if spec:
        arch["spec"] = spec
    return arch


# ---------- 读写 ----------
def _path(project_id: str):
    return storage.project_dir(project_id) / "architecture.json"


def load(project_id: str) -> dict[str, Any] | None:
    path = _path(project_id)
    if not path.exists():
        return None
    try:
        return normalize(json.loads(path.read_text("utf-8")))
    except (ValueError, OSError):
        return None


def _base_path(project_id: str):
    return storage.project_dir(project_id) / "architecture.base.json"


def load_base(project_id: str) -> list[dict] | None:
    """上一次从原型读出来的样子（编号和画布对得上）。画布和它比，多做的就是还没同步到原型的改动。没读过就是 None"""
    path = _base_path(project_id)
    try:
        return normalize({"nodes": json.loads(path.read_text("utf-8"))})["nodes"] if path.exists() else None
    except (ValueError, OSError):
        return None


def save_base(project_id: str, nodes: list[dict]) -> None:
    write_atomic(_base_path(project_id), json.dumps(nodes, ensure_ascii=False))


def save(project_id: str, raw: Any) -> dict[str, Any]:
    storage.load_meta(project_id)   # 项目不存在 / 在回收站里就报错，不凭空建目录
    arch = normalize(raw)
    arch["updated_at"] = storage.now_iso()
    write_atomic(_path(project_id), json.dumps(arch, ensure_ascii=False, indent=1))
    return arch


# ---------- 遍历、顺序、检查 ----------
def walk(nodes: list[dict], depth: int = 0, parents: tuple = ()) -> Iterator[tuple[dict, int, tuple]]:
    for item in nodes:
        yield item, depth, parents
        yield from walk(item.get("children") or [], depth + 1, parents + (item,))


def is_screen(item: dict) -> bool:
    """会做成一个页面的：菜单页、页签、下钻页；还有下面什么都没挂的模块——它就是一个一级菜单页（左侧菜单点「测试」直接进页面）"""
    return item["type"] in SCREEN_TYPES or (item["type"] == "module" and not item.get("children"))


def screens(arch: dict) -> list[dict]:
    """要做出来的页面：一个菜单页一个，它下面的页签、下钻页、弹窗抽屉都算在这一页里（一页一步做完）。
    不在任何菜单页下面的下钻页 / 页签（少见）单独算一页；没挂子项的模块自己算一页"""
    out = []
    for item, depth, parents in walk(arch.get("nodes") or []):
        if not is_screen(item) or any(p["type"] in SCREEN_TYPES for p in parents):
            continue
        inside = [n for n, _, _ in walk(item.get("children") or [])]
        data = list(dict.fromkeys(d for n in [item, *inside] for d in n.get("data") or []))
        out.append({"node": item, "path": [p["name"] for p in parents if p["type"] != "module"] + [item["name"]],
                    "module": next((p["name"] for p in reversed(parents) if p["type"] == "module"), ""),
                    "tabs": [n["name"] for n in item.get("children") or [] if n["type"] == "tab"],
                    "drills": [n["name"] for n in inside if n["type"] == "drill"], "data": data})
    return out


def entity_ranks(arch: dict) -> dict[str, int]:
    """数据的依赖深度：A 有字段引用 B，A 就排在 B 后面。有环就按已经算到的深度断开"""
    entities = {e["name"]: e for e in arch.get("entities") or []}
    ranks: dict[str, int] = {}

    def rank(name: str, stack: tuple) -> int:
        if name in ranks:
            return ranks[name]
        if name in stack or name not in entities:
            return 0
        deps = [f["ref"] for f in entities[name]["fields"] if f.get("kind") == "ref" and f.get("ref") in entities and f["ref"] != name]
        ranks[name] = 1 + max((rank(d, stack + (name,)) for d in deps), default=-1)
        return ranks[name]

    for name in entities:
        rank(name, ())
    return ranks


def order(arch: dict) -> list[dict]:
    """生成顺序：被依赖的数据先做（设备定义 → 设备录入 → 巡检点 → 路线 → 计划…）；
    没标数据的页面（工作台、统计分析）放最后：它们汇总的是前面那些页面的数据"""
    ranks = entity_ranks(arch)
    last = max(ranks.values(), default=0) + 1
    items = []
    for index, screen in enumerate(screens(arch)):
        data = [ranks[d] for d in screen["data"] if d in ranks]
        items.append((max(data) if data else last, index, screen))
    return [{"id": s["node"]["id"], "name": s["node"]["name"], "type": s["node"]["type"], "path": " / ".join(s["path"]),
             "module": s["module"], "tabs": s["tabs"], "drills": s["drills"]}
            for _, _, s in sorted(items, key=lambda x: (x[0], x[1]))]


def check(arch: dict) -> list[dict]:
    """架构自己对不对得上：引用的数据要有、流程的箭头要指得到、页面要有介绍。error 要先改，warn 只是提醒。
    数据关系是 AI 自己维护的内部东西（界面上收在「⋯ › 高级：数据」），那边对不上只提醒、不挡生成，记成 area 是 data。"""
    issues: list[dict] = []
    entities = {e["name"]: e for e in arch.get("entities") or []}

    def add(level, text, **where):
        issues.append({"level": level, "text": text, **where})

    pages = screens(arch)
    if not pages:
        add("warn", "还没有页面：先加一个模块和菜单页")
    names_all = {n["name"] for n, _, _ in walk(arch.get("nodes") or [])}
    loose_all = {loose_name(n) for n in names_all}
    for item, depth, parents in walk(arch.get("nodes") or []):
        for name in item.get("data") or []:
            if name not in entities:
                add("warn", f"「{item['name']}」用到的数据「{name}」在数据关系里没有", node=item["id"], area="data")
        if is_screen(item) and not item.get("desc"):
            add("warn", f"「{item['name']}」还没写介绍：AI 会按名字猜", node=item["id"])
        if item["type"] == "button" and item.get("action") in ("open", "jump") and item.get("target") and item["target"] not in names_all and loose_name(item["target"]) not in loose_all:
            add("error", f"按钮「{item['name']}」要{ACTIONS[item['action']]}的「{item['target']}」在页面树里没有", node=item["id"])
        if item["type"] == "drill" and not item.get("entry"):
            add("warn", f"下钻页「{item['name']}」没写从哪进", node=item["id"])
    for e in entities.values():
        for f in e["fields"]:
            if f.get("kind") == "ref" and f.get("ref") not in entities:
                add("warn", f"「{e['name']}.{f['name']}」引用的「{f.get('ref') or '（没选）'}」不存在", entity=e["id"], area="data")
    for r in arch.get("relations") or []:
        for end in (r["from"], r["to"]):
            if end not in entities:
                add("warn", f"关系「{r['from']} → {r['to']}」里的「{end}」不存在", area="data")
    step_ids = {s["id"] for s in arch.get("steps") or []}
    node_ids = {n["id"] for n, _, _ in walk(arch.get("nodes") or [])}
    lane_ids = {l["id"] for l in arch.get("lanes") or []}
    for s in arch.get("steps") or []:
        if s["lane"] not in lane_ids:
            add("error", f"流程步骤「{s['name']}」不在任何泳道里", step=s["id"])
        for nxt in s.get("next") or []:
            if nxt not in step_ids:
                add("error", f"流程步骤「{s['name']}」指向的下一步不存在", step=s["id"])
        if s.get("node") and s["node"] not in node_ids:
            add("warn", f"流程步骤「{s['name']}」对应的页面已经删了", step=s["id"])
    names = [n["name"] for n, _, _ in walk(arch.get("nodes") or []) if n["type"] in ("page", "drill")]
    for name in sorted({n for n in names if names.count(n) > 1}):
        add("warn", f"有两个页面都叫「{name}」，生成时容易混")
    return issues


def summary(arch: dict) -> dict:
    nodes = [n for n, _, _ in walk(arch.get("nodes") or [])]
    count = lambda *kinds: sum(1 for n in nodes if n["type"] in kinds)
    return {"modules": count("module"), "pages": count("page"), "tabs": count("tab"), "drills": count("drill"),
            "layers": count("modal", "drawer", "wizard"), "features": count("feature", "block", "jump", "table"), "buttons": count("button"),
            "entities": len(arch.get("entities") or []), "screens": len(screens(arch))}


def bundle(arch: dict | None) -> dict:
    """接口统一回这一包：架构本身、检查结果、生成顺序、计数"""
    if not arch:
        return {"architecture": None, "issues": [], "order": [], "counts": {}}
    return {"architecture": arch, "issues": check(arch), "order": order(arch), "counts": summary(arch)}


# ---------- 交给 AI 的文字 ----------
def _node_line(item: dict) -> str:
    # 没挂子项的模块就是一个一级菜单页：左侧菜单点它直接进页面
    kind = "一级菜单页（没有子菜单）" if item["type"] == "module" and not item.get("children") else NODE_TYPES[item["type"]]
    parts = [f"[{kind}] {item['name']}" + ("（规划中，原型里还没有）" if not item.get("seen") and not item.get("proto") else "")]
    if item.get("desc"):
        parts.append(item["desc"].replace("\n", " "))
    if item.get("action"):
        parts.append(f"点了：{ACTIONS[item['action']]}" + (f"「{item['target']}」" if item.get("target") else ""))
    for key, label in (("when", "什么时候出现"), ("who", "谁用"), ("entry", "入口"), ("route", "地址"), ("params", "带过去"), ("back", "返回"),
                       ("fields", "字段"), ("cols", "列"), ("after", "确认后"), ("data", "数据"), ("tags", "标签"), ("req", "需求")):
        value = item.get(key)
        if value:
            parts.append(f"{label}：{'、'.join(value) if isinstance(value, list) else value}")
    return "｜".join(parts)


def brief(arch: dict, limit: int = 16000) -> str:
    # 架构是原型的镜子：这里给 AI 看整棵树当背景，这一轮具体改哪几处以用户的话为准，别的页面不要动
    lines = [f"页面树（用户在架构画布上规划的结构，做页面时照它来；这一轮只做用户说的那几处）：{arch.get('name') or '（未命名）'}（只做电脑端）"]
    if arch.get("summary"):
        lines.append(arch["summary"])
    if arch.get("roles"):
        lines.append("角色：" + "、".join(arch["roles"]))
    lines.append("\n页面树（缩进是层级）：")
    for item, depth, _ in walk(arch.get("nodes") or []):
        lines.append("  " * depth + "- " + _node_line(item))
    if arch.get("entities"):
        lines.append("\n数据（所有页面共用这一份：先在脚本里定义一份演示数据，各页都从它渲染；"
                     "引用的东西必须真实存在；「自动算」的从数据算出来，不能写死；「继承」的不能手改）：")
        for e in arch["entities"]:
            fields = []
            for f in e["fields"]:
                tag = FIELD_KINDS.get(f["kind"], "")
                text = f["name"] + (f"（{tag}" + (f" {f['ref']}" if f.get("ref") else "") + "）" if tag else "")
                fields.append(text + (f" {f['note']}" if f.get("note") else ""))
            head = f"- {e['name']}" + (f" {e['code']}" if e.get("code") else "") + (f"（{e['role']}）" if e.get("role") else "")
            if e.get("external"):
                head += "【外部系统，只读，只生成它回传的数据，不做它的页面】"
            lines.append(head + ("：" + e["desc"] if e.get("desc") else "") + (" 字段：" + "；".join(fields) if fields else "")
                         + (" 状态：" + " → ".join(e["states"]) if e.get("states") else ""))
        for r in arch.get("relations") or []:
            lines.append(f"  关系：{r['from']} → {r['to']}" + (f"（{r['label']}）" if r.get("label") else ""))
    if arch.get("steps"):
        lanes = {l["id"]: l for l in arch.get("lanes") or []}
        names = {s["id"]: s["name"] for s in arch["steps"]}
        lines.append("\n业务流程（「本次不做」和「外部系统」的泳道不做页面，只生成它们产生的数据，保证后面的页面有数据可看）：")
        for s in arch["steps"]:
            lane = lanes.get(s["lane"], {})
            tag = f"{lane.get('name', '')}" + (f"·{LANE_KINDS[lane['kind']]}" if lane.get("kind") in ("skip", "external") else "")
            nxt = "、".join(names[n] for n in s.get("next") or [] if n in names)
            lines.append(f"- [{tag}] {s['name']}" + (f"：{s['desc']}" if s.get("desc") else "") + (f" → {nxt}" if nxt else ""))
    lines.append("\n电脑端统一规则（每一页都按这个来，页面之间不要各做各的）：")
    lines += [f"- {r}" for r in arch.get("rules") or PC_RULES]
    text = "\n".join(lines)
    return text if len(text) <= limit else text[:limit] + "\n（架构太长，后面截掉了）"
