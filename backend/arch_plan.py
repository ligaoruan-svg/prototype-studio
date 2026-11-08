"""页面清单：业务梳理确认后，AI 先只定「有哪些模块、哪些页、给谁用、管哪个对象、是什么类型的页」——
一页一行，产品经理在小卡上看全、可选页打钩、拿不准的单选；确认后程序按页面类型把整棵树展开。

以前是 AI 一口气画一百多个节点：需要判断的（怎么分模块、首页看什么）和机械的（每个状态一个页签、
每个动作一个按钮、字段抄进弹窗）混在一起，机械的最容易漏、前后不一。现在 AI 只做判断，规范的部分程序保证。
"""
from __future__ import annotations

import json
import re
from typing import Any

from .arch_fields import field_text, parse_field
from .arch_gen import CODEISH, NAMEISH

PLAN_HEAD = "按页面清单画架构"
TYPES = {"list": "管理列表", "tasks": "我的任务", "dashboard": "看板", "report": "统计", "config": "基础配置"}

PLAN_SYSTEM = """你是资深 B 端产品经理。业务梳理已经确认，现在定这个后台的页面清单：有哪些模块、每个模块有哪些菜单页、每页给谁用、管哪个业务对象、是什么类型。
不用画页面里的细节（列、按钮、弹窗程序会按类型和业务梳理自动展开），只做需要判断的事。

只输出一个 JSON 对象，不要 Markdown 代码块，不要别的文字：
{
  "modules": [
    {"name": "首页", "pages": [
      {"name": "首页看板", "type": "dashboard", "who": ["主管", "物业客服"], "desc": "一进来先看今天要处理的",
       "metrics": ["待派单：状态是待派单的工单数", "超时未派单：紧急且提交超过 30 分钟还没派单的工单数"], "lists": ["超时未派单的工单"]}]},
    {"name": "报修工单", "pages": [
      {"name": "工单管理", "type": "list", "object": "报修工单", "who": ["物业客服", "主管"], "desc": "客服受理、派单、关闭", "add": false},
      {"name": "我的任务", "type": "tasks", "object": "报修工单", "who": ["维修工"], "desc": "只列派给自己的工单"}]},
    {"name": "统计分析", "pages": [
      {"name": "工单统计", "type": "report", "object": "报修工单", "who": ["主管"], "dims": ["报修分类", "维修工"],
       "metrics": ["工单数：按提交时间统计", "平均处理时长：完工时间减接单时间的平均"]}]},
    {"name": "系统管理", "pages": [
      {"name": "账号管理", "type": "config", "object": "账号", "who": ["系统管理员"], "optional": true, "pick": false}]}
  ],
  "choices": [{"q": "统计放在首页里，还是单独一个「统计分析」模块？", "options": ["单独一个模块", "并进首页看板"]}]
}

页面类型（type）只能是这几种：
- list 管理列表：一个业务对象的全部数据，按状态分页签、筛选、表格、新增、行上的流转按钮、详情。add 写这个对象是不是在本后台新增（小程序、外部系统来的写 false）。
- tasks 我的任务：某个角色要处理的那部分（维修工接单、完工），who 写那个角色。
- dashboard 看板：metrics 写指标，每条「名字：口径」，口径从业务对象算出来；lists 写下面要列的待办清单（最多 2 个）。
- report 统计：dims 写按什么分组（用业务对象里的字段名），metrics 同上。
- config 基础配置：字典、价目表、账号、角色这类，增删改加启停用。

怎么定：
- 模块按业务域分，3–7 个；每个核心业务对象至少一个 list 页；角色要处理的有 tasks 页；首页看板按需要放；统计放统计模块或首页。
- object 写业务梳理里的对象名，一字不差；who 写梳理里的角色名。范围里「不做」「外部系统」的不出页面。
- 不是非有不可的页（账号、角色、日志、参数）写 optional: true，pick 写推荐要不要（true / false）。
- choices 只放会明显改变页面清单、你又拿不准的，最多 3 个，推荐的放第一个；页面清单按第一个选项来写。没有就给空数组。
- 用户已经有页面树或原型：已有的业务页保留（名字不变），在它的基础上补全。"""


def _s(v: Any, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _names(v: Any, count: int = 8, n: int = 60) -> list[str]:
    items = v if isinstance(v, list) else re.split(r"[、,，;；\n]", str(v or ""))
    return [x for x in (_s(i, n) for i in items) if x][:count]


def normalize(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    modules = []
    for m in (raw.get("modules") if isinstance(raw.get("modules"), list) else [])[:9]:
        if not isinstance(m, dict) or not _s(m.get("name"), 20):
            continue
        pages = []
        for p in (m.get("pages") if isinstance(m.get("pages"), list) else [])[:10]:
            if not isinstance(p, dict) or not _s(p.get("name"), 20):
                continue
            kind = p.get("type") if p.get("type") in TYPES else "list"
            page = {"name": _s(p.get("name"), 20), "type": kind, "object": _s(p.get("object"), 20),
                    "who": _names(p.get("who"), 6, 20), "desc": _s(p.get("desc"), 80)}
            for key in ("metrics", "lists", "dims"):
                if p.get(key):
                    page[key] = _names(p.get(key), 8, 60)
            if p.get("add") is False:
                page["add"] = False
            if p.get("optional"):
                page.update(optional=True, pick=p.get("pick") is not False)
            pages.append(page)
        if pages:
            modules.append({"name": _s(m.get("name"), 20), "pages": pages})
    choices = []
    for q in (raw.get("choices") if isinstance(raw.get("choices"), list) else [])[:3]:
        options = _names(q.get("options"), 4, 50) if isinstance(q, dict) else []
        if isinstance(q, dict) and _s(q.get("q"), 100) and len(options) >= 2:
            choices.append({"q": _s(q.get("q"), 100), "options": options})
    return {"status": "draft", "modules": modules, "choices": choices} if modules else None


def parse(reply: str) -> dict | None:
    text = re.sub(r"```(?:json)?", "", reply or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    raw = text[start:end + 1]
    for attempt in (raw, re.sub(r",\s*([}\]])", r"\1", re.sub(r"(?<![:\"'\\])//[^\n]*", "", raw))):
        try:
            return normalize(json.loads(attempt))
        except ValueError:
            continue
    return None


def headline(plan: dict, revised: bool = False) -> str:
    pages = [p for m in plan["modules"] for p in m["pages"]]
    optional = sum(1 for p in pages if p.get("optional"))
    tail = (f"{optional} 个可选页打钩，" if optional else "") + (f"{len(plan['choices'])} 处要你定，" if plan["choices"] else "")
    return (("按你的意思改了页面清单" if revised else "页面清单出来了") + f"：{len(plan['modules'])} 个模块、{len(pages)} 个页面。"
            + tail + "确认后程序按页面类型把整棵树展开。")


def settle(plan: dict, message: str) -> tuple[dict, list[str]]:
    """确认时用户选的：可选页要哪几个（「可选页要：A、B」，没写就按推荐），问题怎么答。返回 (清单, 和推荐不一样的回答)"""
    m = re.search(r"可选页要[:：]\s*(.*)", message or "")
    wanted = set(_names(m.group(1), 20, 20)) if m else None
    modules = []
    for mod in plan["modules"]:
        pages = [p for p in mod["pages"] if not p.get("optional") or (p["name"] in wanted if wanted is not None else p.get("pick"))]
        if pages:
            modules.append({**mod, "pages": pages})
    picked, differ = {}, []
    for line in (message or "").splitlines():
        hit = re.match(r"^\s*[-*•]\s*(.+?)[：:]\s*(.+?)\s*$", line)
        if hit:
            picked[hit.group(1).strip()] = hit.group(2).strip()
    for q in plan.get("choices") or []:
        answer = picked.get(q["q"], q["options"][0])
        if answer != q["options"][0]:
            differ.append(f"{q['q']}——{answer}")
    return {**plan, "modules": modules, "choices": [], "status": "confirmed"}, differ


# ---------- 按页面类型展开 ----------

def _parsed(obj: dict) -> list[dict]:
    return [parse_field(f) for f in obj.get("fields") or []]


def _filters(fields: list[dict], states: list[str], tabs: bool, mine: list[str] = ()) -> list[str]:
    """mine：这一页是谁的（维修工的「我的任务」）——指向他自己的那个关联字段（维修工）不用筛"""
    fields = [f for f in fields if not (f["type"] == "ref" and f["options"][:1] and f["options"][0] in mine)]
    key = [f for f in fields if CODEISH.search(f["name"]) or NAMEISH.search(f["name"])][:1]     # 编号 / 名称：输入框搜
    out = [f["name"] for f in key]
    out += [f["name"] + ("（下拉：" + "/".join(f["options"]) + "）" if f["options"] and f["type"] != "ref" else "（下拉）")
            for f in fields if f["type"] in ("select", "radio", "ref", "person") and not f["locked"] and f not in key][:3]
    when = next((f["name"] for f in fields if f["type"] in ("date", "datetime")), "")
    if when:
        out.append(f"{when}（日期范围）")
    if states and not tabs:
        out.append("状态（下拉：" + "/".join(states) + "）")
    return out


LONG = re.compile(r"(描述|说明|备注|原因|内容|意见|照片|图片|附件|地址)$")


def _cols(fields: list[dict], states: list[str], limit: int = 7) -> list[str]:
    """表格列：编号、名称打头，再挑选项 / 关联 / 人（分得清是哪类、谁的），金额、时间各一个；长文字（描述、地址）进详情不进表格。
    连状态最多 limit 列，一屏放得下、操作列不压住内容"""
    show = [f for f in fields if f["type"] not in ("textarea", "upload", "image", "note") and not LONG.search(f["name"])]
    # 打头的是编号和名称各一个（订单号、商品名称），别让「物流单号」挤到第二列
    first = [f for f in (next((f for f in show if CODEISH.search(f["name"])), None), next((f for f in show if NAMEISH.search(f["name"])), None)) if f]
    rest = [f for f in show if f not in first]
    choice = lambda f: f["type"] in ("select", "radio", "ref", "person")
    when = lambda f: f["type"] in ("date", "datetime") or re.search(r"(时间|日期)$", f["name"])
    money = lambda f: f["type"] == "money" or re.search(r"(金额|费|价|合计|租金)$", f["name"])
    room = limit - len(first) - (1 if states else 0)
    # 选项 / 关联最多三个，时间、金额各一个，还有空再按字段表顺序补
    picked = [f for f in rest if choice(f)][:3]
    picked += [f for f in rest if when(f) and f not in picked][:1] + [f for f in rest if money(f) and not when(f) and f not in picked][:1]
    picked = picked[:room]
    picked += [f for f in rest if f not in picked][:max(0, room - len(picked))]
    cols = [f["name"] for f in first + [f for f in rest if f in picked]]
    return cols + (["状态"] if states else [])


def parse_action(raw: str) -> tuple[str, list[str], str, str, str] | None:
    """「派单：待派单→处理中（客服，必须选维修工）」→ (派单, [待派单], 处理中, 客服, 必须选维修工)；起点是「—」的 src 为空"""
    m = re.match(r"^([^：:（(]+)[：:]\s*(.+?)\s*(?:→|->)\s*([^（(]+?)\s*(?:[（(](.*)[）)])?\s*$", str(raw).strip())
    if not m:
        return None
    verb, src, dst, note = (x.strip() if x else "" for x in m.groups())
    who, rest = (re.split(r"[，,；;、\s]", note or "", maxsplit=1) + [""])[:2]
    src_list = [x for x in re.split(r"\s*[/、,，]\s*|或", src) if x and not re.fullmatch(r"[—\-–－]+|无|空|新建", x)]
    return verb, src_list, re.split(r"\s*[/／]\s*", dst)[0], who, rest


def filled_by(obj: dict, extra: list[str] = ()) -> dict[str, set[str]]:
    """哪些字段要等某一步做了才有值：{字段: 有值的状态}。派单才选的维修工、完工才填的处理说明、
    「派单时间」「付款时间」这种带动作名的时间、弹窗里的「审核驳回原因」（extra：字段表外、页面上出现的字段）——
    走到那一步之后（从它的终点能到的状态）才填"""
    states, acts = obj.get("states") or [], [a for a in map(parse_action, obj.get("actions") or []) if a]
    nxt: dict[str, set[str]] = {}
    for _, src, dst, _, _ in acts:
        for x in src:
            nxt.setdefault(x, set()).add(dst)

    def reach(start):
        seen, todo = {start}, [start]
        while todo:
            for y in nxt.get(todo.pop(), ()):
                if y not in seen:
                    seen.add(y)
                    todo.append(y)
        return seen
    fields = _parsed(obj)
    out: dict[str, set[str]] = {}
    for verb, src, dst, _, rest in acts:
        if not src or dst not in states:
            continue
        stamp = re.compile(f"(?:{re.escape(verb[:2])}|{re.escape(verb[-2:])}).{{0,2}}(时间|日期)")
        names = {f["name"] for f in _asked(rest, fields)} | {f["name"] for f in fields if f["locked"] and stamp.fullmatch(f["name"])} \
            | {n for n in extra if n.startswith(verb) and n != verb}
        for n in names:
            out.setdefault(n, set()).update(reach(dst))
    for f in fields:     # 「完成时间」「付款时间」：到了「已完成」「已付款」才有
        head = re.sub(r"(时间|日期)$", "", f["name"])
        st = next((x for x in states if len(head) >= 2 and head in x), "") if f["locked"] and head != f["name"] else ""
        if st and f["name"] not in out:
            out[f["name"]] = reach(st)
    return out


def _asked(note: str, fields: list[dict]) -> list[dict]:
    """「必须选维修工」「需填处理说明」才是要填的；「通知维修工」「记录接单时间」不是"""
    return [f for f in fields if not f["locked"] and re.search(r"(?:填|选|(?<!记)录|上传|附)[^，,；;。]*?" + re.escape(f["name"]), note)]


def _modal_fields(note: str, fields: list[dict], verb: str) -> list[str]:
    """流转弹窗只放这一步要填的：动作说明里点到的字段，提到原因 / 说明的加一个多行"""
    asked = _asked(note, fields)
    out = [field_text(f["name"], True, False, f["type"], f["options"]) for f in asked]
    named = "".join(f["name"] for f in asked)
    if re.search(r"原因", note) and "原因" not in named:
        out.append(f"{verb}原因*（多行）")
    elif re.search(r"说明|备注|意见", note) and not re.search(r"说明|备注|意见", named):
        out.append(f"{verb}说明*（多行）")
    return out


def _sub_table(sub: dict, parent: str, editable: bool) -> dict:
    """明细子表（一张工单下的几行材料）：去掉指回主对象的那个关联字段"""
    fields = [f for f in _parsed(sub) if not (f["type"] == "ref" and f["options"][:1] == [parent])]
    if editable:
        return {"type": "table", "name": sub["name"], "fields": [field_text(f["name"], f["must"], False, f["type"], f["options"]) for f in fields if not f["locked"]]}
    return {"type": "table", "name": sub["name"], "cols": _cols(fields, [])}


def _mentions(note: str, name: str) -> bool:
    """动作说明里点到了这份明细（「需填处理说明和材料明细」点到了「工单材料明细」）"""
    return any(name[i:] in note for i in range(len(name) - 2))     # 至少三个字：「记录」太泛


def _object_page(page: dict, obj: dict, roles: list[str], subs: list[dict] = (), logs: list[dict] = ()) -> list[dict]:
    """list / tasks / config 页：筛选、表格（行上查看 + 流转按钮）、新增、详情、流转弹窗。
    subs：挂在这个对象下、自己没有页面的明细（工单材料明细）——详情里一张子表，点到它的流转弹窗里也放一张；
    logs：每做一次动作记一条的（催办 → 催办记录）——那个动作的弹窗填的就是这条记录的字段"""
    name, kind = obj["name"], page["type"]
    fields, states = _parsed(obj), obj.get("states") or []
    acts, born, later = [], False, set()     # born：有人新建（梳理里写了 —→X 的动作），不是这一页的人也算；later：后面哪步才填的字段
    for raw in obj.get("actions") or []:
        act = parse_action(raw)
        if not act:
            continue
        verb, src_list, dst, who, rest = act
        mine = any(r and (r in who or who in r) for r in page["who"]) if who else True
        machine = re.search(r"系统|自动|定时|超时|到期", who) and not any(r and r in who for r in roles)
        born = born or not src_list
        if src_list:
            later |= {f["name"] for f in _asked(rest, fields)}
        if mine and not machine:
            acts.append((verb, src_list, dst, rest))     # rest：括号里谁做的后面那段（选维修工、填关闭原因）
    tabs = []
    if kind == "list" and len(states) >= 3:
        tabs = list(states)
    elif kind == "tasks":     # 只有一种要处理的状态就不分页签（「待发货」页下面只一个「待发货」页签没意义）
        tabs = [s for s in states if any(s in a[1] for a in acts)]
        tabs = tabs if len(tabs) >= 2 else []
    kids: list[dict] = [{"type": "tab", "name": t} for t in tabs]
    kids.append({"type": "block", "name": "筛选", "fields": _filters(fields, states if kind != "tasks" else [], bool(tabs), page["who"] if kind == "tasks" else [])})
    buttons = [{"type": "button", "name": "查看", "action": "open", "target": f"{name}详情"}]
    layers = [{"type": "drawer", "name": f"{name}详情", "fields": [f["name"] for f in fields] + (["状态"] if states else []),
               # 详情里看得到明细和历次记录（催办、跟进）；有自己状态流转的（售后单、合同）是另一件事，不往里塞
               "children": [_sub_table(x, name, False) for x in [*subs, *(x for x in logs if not x.get("states"))]]}]
    editable = [f for f in fields if not f["locked"]]
    if kind == "config":
        buttons.append({"type": "button", "name": "编辑", "action": "open", "target": f"编辑{name}"})
        layers.append({"type": "modal", "name": f"编辑{name}", "fields": [field_text(f["name"], f["must"], False, f["type"], f["options"]) for f in editable]})
    for verb, src, dst, note in acts:
        if not src:
            continue
        button = {"type": "button", "name": verb, "when": "状态是" + "、".join(src) + "时",
                  **({} if src == [dst] else {"after": f"状态变为{dst}"})}     # 催办、改地址：状态不变
        body = _modal_fields(note, fields, verb)
        log = next((x for x in [*logs, *subs] if x["name"].startswith(verb)), None)
        if log:
            body += [field_text(f["name"], f["must"], False, f["type"], f["options"]) for f in _parsed(log)
                     if not f["locked"] and not (f["type"] == "ref" and f["options"][:1] == [name]) and field_text(f["name"], f["must"], False, f["type"], f["options"]) not in body]
        inner = [_sub_table(x, name, True) for x in subs if x is not log and _mentions(note, x["name"])]
        if body or inner:
            title = verb + name if verb in ("关闭", "取消", "删除", "作废") else verb    # 弹窗只叫「关闭」读回来认不出
            button.update(action="open", target=title)
            layers.append({"type": "modal", "name": title, "fields": body, "children": inner})
        else:
            button.update(action="confirm", target=f"确认{verb}？")
        buttons.append(button)
    # 我的任务页：只有一种要处理的状态就叫「待发货订单」，几种就叫「我的订单列表」（「我的」放在审批人页面上不对）
    title = f"{name}列表" if kind != "tasks" else (tabs and f"我的{name}列表") or next((f"{a[1][0]}{name}" for a in acts if a[1]), f"我的{name}列表")
    table = {"type": "table", "name": title, "cols": _cols(fields, states), "children": buttons}
    if kind == "tasks":     # 我的任务只列要我处理的状态（维修工看处理中的），不是全部
        todo = [x for x in states if any(x in a[1] for a in acts)]
        if todo:
            table["when"] = "状态是" + "、".join(todo) + "时"
    kids.append(table)
    # 新建只填一开始就有的：派单才选的维修工、完工才写的处理说明不放
    form = [field_text(f["name"], f["must"], False, f["type"], f["options"]) for f in editable if f["name"] not in later]
    # 新建：梳理里写了谁新建（新建：—→草稿）就照它，按钮叫「新建报销单」、新的一条是那个状态；
    # 没写就是一般的「新增」；写了但不是这一页的人（顾客在小程序里申请）就不放
    news = [(verb, dst) for verb, src, dst, _ in acts if not src] if kind != "tasks" else []
    if not news and not born and kind != "tasks" and page.get("add") is not False:
        news = [("新增", "")]
    for verb, dst in news:
        kids.append({"type": "button", "name": verb + name, "action": "open", "target": verb + name,
                     **({"after": f"新增一条，状态是{dst}"} if dst else {})})
        layers.append({"type": "modal", "name": verb + name, "fields": form})
    return kids + layers


def _metric_page(page: dict, spec: dict) -> list[dict]:
    """dashboard / report 页：指标卡（每条带口径）、统计图、明细或待办清单"""
    kids: list[dict] = []
    if page["type"] == "report":
        kids.append({"type": "block", "name": "筛选", "fields": [f"{d}（下拉）" for d in page.get("dims") or []] + ["统计时间（日期范围）"]})
    if page.get("metrics"):     # 字段只放指标名，口径写进介绍：整句当字段名，会被当成字段跟字段表比
        calibers = [m for m in page["metrics"] if re.search(r"[：:].", m)]
        kids.append({"type": "block", "name": "指标卡", "fields": [re.split(r"[：:]", m, maxsplit=1)[0] for m in page["metrics"]],
                     **({"desc": "口径：" + "；".join(calibers)} if calibers else {})})
    if page["type"] == "report":
        dims = page.get("dims") or []
        if dims:
            kids.append({"type": "block", "name": "统计图", "desc": "按" + "、".join(dims) + "分组"})
        kids.append({"type": "table", "name": f"{page['name']}明细", "cols": dims + [m.split("：")[0] for m in page.get("metrics") or []]})
    obj = next((o for o in (spec or {}).get("objects") or [] if o["name"] == page.get("object")), None)
    for title in page.get("lists") or []:
        cols = _cols(_parsed(obj), obj.get("states") or []) if obj else []
        kids.append({"type": "table", "name": title, "cols": cols[:6],
                     "children": [{"type": "button", "name": "查看", "action": "open", "target": f"{obj['name']}详情"}] if obj else []})
    return kids


def expand(plan: dict, spec: dict) -> list[dict]:
    """页面清单 → 整棵页面树（画布的节点）"""
    objects = {o["name"]: o for o in (spec or {}).get("objects") or []}
    roles = [r["name"] for r in (spec or {}).get("roles") or []]
    paged = {p.get("object") for m in plan["modules"] for p in m["pages"]}
    # 自己没页面、关联到别的对象的（工单材料明细 → 报修工单）：当那个对象的明细子表
    # 有页面、也关联到别的对象的（催办记录 → 报修工单）：那个对象上同名动作（催办）的弹窗填它的字段
    subs: dict[str, list[dict]] = {}
    logs: dict[str, list[dict]] = {}
    for o in objects.values():
        ref = next((f["options"][0] for f in _parsed(o) if f["type"] == "ref" and f["options"]), "")
        if ref in paged:
            (logs if o["name"] in paged else subs).setdefault(ref, []).append(o)
    nodes = []
    for mod in plan["modules"]:
        pages = []
        for p in mod["pages"]:
            obj = objects.get(p.get("object"))
            if p["type"] in ("list", "tasks", "config") and obj:
                kids = _object_page(p, obj, roles, subs.get(obj["name"], []), logs.get(obj["name"], []))
            else:
                kids = _metric_page(p, spec)
            pages.append({"type": "page", "name": p["name"], "desc": p.get("desc", ""), "who": p["who"], "children": kids})
        if len(pages) == 1 and pages[0]["name"] == mod["name"]:     # 「首页」模块下只有一个「首页」：直接放最外层，左侧菜单不套一层
            nodes.append(pages[0])
        else:
            nodes.append({"type": "module", "name": mod["name"], "children": pages})
    return nodes


def to_text(plan: dict) -> str:
    lines = []
    for m in plan["modules"]:
        lines.append(f"- {m['name']}")
        for p in m["pages"]:
            lines.append(f"  - {p['name']}（{TYPES[p['type']]}｜{p.get('object') or '—'}｜{'、'.join(p['who'])}）" + ("（可选）" if p.get("optional") else ""))
    return "\n".join(lines)
