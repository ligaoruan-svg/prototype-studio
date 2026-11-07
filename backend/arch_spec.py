"""业务梳理：出架构之前，先把这个系统想清楚——给谁用、管哪些东西、东西有哪些状态、谁让它从哪个状态走到哪个、
有哪些规则、做到哪为止。产品经理看这一张卡片确认（拿不准的地方 AI 最多问 3 个，带选项），确认了再按它画页面树。

以前是一句需求进来直接画树：没想业务，画出来像拼凑的。梳理存在 architecture.json 的 spec 里，
以后改架构、生成原型都能拿它当依据。这里只管提示词、读模型的回复、整理成固定的样子；怎么调模型在 arch_chat。
"""
from __future__ import annotations

import json
import re
from typing import Any

SPEC_SYSTEM = """你是资深 B 端产品经理。用户要做一个电脑端的管理后台原型，先别画页面，先把业务梳理清楚，交给用户确认。

只输出一个 JSON 对象，不要 Markdown 代码块，不要别的文字：
{
  "summary": "一句话：这个系统给谁用、解决什么问题",
  "roles": [{"name": "物业客服", "does": "受理报修、派单、回访"}],
  "objects": [{"name": "报修工单", "desc": "业主报的一次维修", "owner": "物业客服",
               "states": ["待派单", "处理中", "待评价", "已完成", "已关闭"],
               "actions": ["派单：待派单→处理中（客服）", "完工：处理中→待评价（维修工）", "关闭：待派单→已关闭（客服，需填原因）"]}],
  "flows": ["业主报修 → 客服派单 → 维修工上门处理 → 完工 → 业主评价"],
  "rules": ["紧急工单 30 分钟内必须派单，超时标红并提醒主管"],
  "scope": {"in": ["报修受理与派单", "维修工管理"], "out": ["业主小程序（本次只做管理后台）"], "external": ["收费系统：费用由它回传"]},
  "assumptions": ["维修费用只记录，不在系统里收款"],
  "questions": [{"q": "维修工是否需要在系统里接单？", "options": ["要，维修工也登录后台接单", "不要，客服代为操作"]}]
}

怎么想：
- 角色 2–6 个。只在别的端用、不登录这个后台的（业主小程序），写进 scope.out 或 external，不算角色。
- 业务对象是系统要管的「东西」（工单、设备、合同、账单……），核心的 3–10 个。有流转的写 states（3–7 个）和 actions，
  action 写成「动作：从状态→到状态（谁，必要的条件）」；只是基础资料（字典、区域）的不写状态。
- 主流程 1–3 条，用 → 串起来，写清谁在哪一步做什么。
- 规则要具体、能验证：时限、校验、唯一性、联动（A 变了 B 跟着变）、统计口径。不要写「数据要准确」这种空话。
- 范围：做什么、不做什么、哪些是外部系统（只接它的数据，不做它的页面）。
- 能合理假设的别问，写进 assumptions；只有会明显改变架构、你猜不准的才问，最多 3 个，每个 2–4 个选项，推荐的放第一个。
- 用户给了现在的页面树或原型线索：已经有的业务都要梳理进来，不要丢；用户只让你改梳理的某处，就只改那处，别的照旧。"""

# 按业务梳理画页面树：在 arch_chat 的格式说明后面接上这一段
DRAW_RULES = """按业务梳理画页面树的规则：
1. 模块按业务域分（一个业务对象和它的上下游放在一起），不按角色分。一级模块 3–7 个，每个模块 2–6 个菜单页。
   首页 / 工作台、统计分析、系统管理（账号、角色、字典、参数）按需要各成一个模块。
2. 每个核心业务对象至少有：管理它的菜单页（筛选区块 + 表格「xx列表」+ 主按钮「新增xx」）、详情抽屉（只读字段）、
   新增 / 编辑弹窗（字段写全，标必填和控件；编号、状态、创建人这类系统生成的加 🔒）。
3. 梳理里的每个流转动作都落成一个按钮：挂在表格行（或详情）下面，写「出现：状态是 xx 时」，点了打开对应弹窗或二次确认，
   写「确认后：状态变为 yy」，有联动的接着写（「；铺位变为空置」）。
4. 状态多、不同阶段不同人处理的对象，菜单页下按状态分页签（待派单 / 处理中 / 已完成），或者在筛选里放状态下拉，二选一。
5. 只给某个角色干活的（维修工接单），给他一个「我的任务」类菜单页，只列他要处理的。
6. 统计、看板放首页或统计分析模块，每个指标从业务对象算出来，在介绍里写清口径。
7. 范围里「不做」的不出页面；「外部系统」不做页面，只在用到它数据的地方写「数据：由 xx 系统回传」。
8. 名字要具体：表格叫「工单列表」「巡检记录」，不要叫「列表」「表格」；按钮用动词开头。
9. 规则（校验、时限、联动）写进对应按钮的「确认后」、弹窗字段或页面介绍里，不要丢。"""

# 确认梳理、开始画：卡片上的按钮发的话，或者你直接说「可以 / 就这样 / 直接画」
DRAW_HEAD = "按业务梳理画架构"
CONFIRM = re.compile(r"^\s*(?:好的?|可以|行|没问题|确认|对|就这样|就按这个|按这个|直接|开始)[，,\s]*(?:画|出|生成|做)?(?:吧|架构|页面树)?[。！!~\s]*$")


def _s(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _list(value: Any, count: int, limit: int) -> list[str]:
    items = value if isinstance(value, list) else re.split(r"[\n；;]", str(value or ""))
    out: list[str] = []
    for item in items:
        text = _s(item, limit)
        if text and text not in out:
            out.append(text)
        if len(out) >= count:
            break
    return out


def normalize(raw: Any) -> dict | None:
    """模型或界面给的梳理收拾成固定的样子；什么都没有就是 None"""
    if not isinstance(raw, dict):
        return None
    roles = []
    for r in (raw.get("roles") if isinstance(raw.get("roles"), list) else [])[:8]:
        name, does = (_s(r.get("name"), 20), _s(r.get("does"), 80)) if isinstance(r, dict) else (_s(r, 20), "")
        if name:
            roles.append({"name": name, "does": does})
    objects = []
    for o in (raw.get("objects") if isinstance(raw.get("objects"), list) else [])[:12]:
        if not isinstance(o, dict) or not _s(o.get("name"), 20):
            continue
        objects.append({"name": _s(o.get("name"), 20), "desc": _s(o.get("desc"), 100), "owner": _s(o.get("owner"), 20),
                        "states": _list(o.get("states"), 8, 12), "actions": _list(o.get("actions"), 10, 80)})
    scope = raw.get("scope") if isinstance(raw.get("scope"), dict) else {}
    questions = []
    for q in (raw.get("questions") if isinstance(raw.get("questions"), list) else [])[:3]:
        if isinstance(q, dict) and _s(q.get("q"), 100):
            options = _list(q.get("options"), 4, 50)
            if len(options) >= 2:
                questions.append({"q": _s(q.get("q"), 100), "options": options})
    spec = {"status": "confirmed" if raw.get("status") == "confirmed" else "draft", "summary": _s(raw.get("summary"), 200),
            "roles": roles, "objects": objects, "flows": _list(raw.get("flows"), 4, 200), "rules": _list(raw.get("rules"), 14, 140),
            "scope": {k: _list(scope.get(k), 10, 60) for k in ("in", "out", "external")},
            "assumptions": _list(raw.get("assumptions"), 6, 120), "questions": questions}
    return spec if (roles or objects) else None


def parse(reply: str) -> dict | None:
    """模型的回复里找出那个 JSON（可能包在代码块里、前后有一两句话）"""
    text = re.sub(r"```(?:json)?", "", reply or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return normalize(json.loads(text[start:end + 1]))
    except ValueError:
        return None


def to_text(spec: dict) -> str:
    """写成一段文字交给模型（画树、改树、回答问题时当依据）"""
    lines = []
    if spec.get("summary"):
        lines.append("定位：" + spec["summary"])
    if spec.get("roles"):
        lines.append("角色：" + "；".join(r["name"] + (f"（{r['does']}）" if r["does"] else "") for r in spec["roles"]))
    if spec.get("objects"):
        lines.append("业务对象：")
        for o in spec["objects"]:
            head = f"- {o['name']}" + (f"：{o['desc']}" if o["desc"] else "") + (f"（{o['owner']}管）" if o["owner"] else "")
            lines.append(head)
            if o["states"]:
                lines.append("  状态：" + " / ".join(o["states"]))
            for a in o["actions"]:
                lines.append("  动作：" + a)
    for key, label in (("flows", "主流程"), ("rules", "规则"), ("assumptions", "假设")):
        if spec.get(key):
            lines.append(label + "：")
            lines += [f"- {x}" for x in spec[key]]
    scope = spec.get("scope") or {}
    for key, label in (("in", "这次做"), ("out", "这次不做"), ("external", "外部系统")):
        if scope.get(key):
            lines.append(f"{label}：" + "；".join(scope[key]))
    return "\n".join(lines)


def headline(spec: dict, revised: bool = False) -> str:
    """对话里卡片上面那一句"""
    n = lambda key: len(spec.get(key) or [])   # noqa: E731
    head = "按你的意思改了梳理" if revised else "先把业务梳理了一下"
    tail = f"有 {n('questions')} 处要你定，" if n("questions") else ""
    return f"{head}：{n('roles')} 个角色、{n('objects')} 个业务对象、{n('rules')} 条规则。{tail}确认后我按它画架构。"
