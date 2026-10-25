"""让 AI 起草 / 补全架构。

回复用「大纲」写法（见 arch_text），不用 JSON：同样的内容字数少一大半，
实测一份 46 页的架构用 JSON 写要好几分钟，大纲快得多，也和手动编的是同一种写法。

从现有原型整理时不把整份源码塞给模型（零碳园区一页就 94 万字）：
有展开过的，用展开图里的业务页面、弹窗、子页面、表头和表单项；没展开过的，用代码地图和页面上的文字。
"""
from __future__ import annotations

import json
import re

from . import architecture, storage
from .arch_text import from_outline, keep_ids, to_outline
from .source_map import code_map

BRIEF_MAX = 30_000

OUTLINE_NOTE = """用下面这种「大纲」写法回复，只输出大纲本身，不要解释，不要 Markdown 代码块：

系统：系统名
介绍：一两句，给谁用、管什么
角色：管理员、核算员

【页面】
模块名 [模块]：一句话
  菜单页名 [菜单页]：这页干什么 | 数据：用到的数据名 | 地址：路由key | 谁用：角色
    页签名 [页签]：… | 数据：…
      查看xx [抽屉]：只读
      新增 / 编辑xx [弹窗]：… | 标签：联动
      xx详情 [下钻页]：… | 入口：点列表里的编号 | 带过去：编号 | 返回：返回列表
      按状态出现的操作 [功能]：…

【数据】
数据名 编号样子如PT-xxx [配置]：一句话
  点位编号 🔑
  关联设备 → 设备档案：1 台
  巡检点数 = 点的个数
  类型 🔒 来自定义
  备注
  状态：待执行 → 执行中 → 已完成
维修工单 [外部]

【关系】
被依赖的数据 → 依赖它的数据：1 → N

【流程】
泳道：管理员（电脑）、系统自动 [系统]、巡检执行 [不做]（手机端）、维修系统 [外部]
管理员 · 配路线：给点排顺序 | 下一步：建计划
管理员 · 建计划 | 下一步：生成任务

写法：缩进两个空格一层；方括号里的类型只能用 模块 菜单页 页签 下钻页 弹窗 抽屉 向导 跳转 区块 功能；
字段：🔑 编号，→ 引用别的数据，= 自动算，🔒 继承不能改，什么都不加是普通字段。
要点：
- 只做电脑端。手机上执行的环节放进 [不做] 泳道，不做页面，只当数据来源。
- 一个菜单下几块并列内容用页签；点编号进去才看到的用下钻页，写清入口 / 带过去 / 返回。
- 查看用抽屉，新增 / 编辑用弹窗，多步用向导。
- 数据要成链：谁引用谁写 →，个数、进度、摘要写 =，从模板带来不能改的写 🔒。
- 每个页面写一句介绍；用到的数据写在「数据：」里，名字和【数据】里的一致。
- 用业务里的叫法，别写成通用的「数据管理」。写精炼：介绍一句话，字段只列关键的。"""


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


def expand_brief(project_id: str, page_id: str) -> str:
    """展开图 → 原型结构：每个业务页面的标题、表头、表单项，页面上点得开的弹窗 / 子页面（谁在谁下面）"""
    try:
        data = storage.load_expand(project_id, page_id)
    except (ValueError, FileNotFoundError):
        return ""
    routes, entries = data.get("routes") or [], data.get("entries") or {}
    if not routes or not entries:
        return ""
    lines = ["原型的业务页面（菜单里的每一项），以及每页点得开的弹窗、子页面："]
    for r in routes:
        result = (entries.get(r.get("hash")) or {}).get("result") or {}
        page = _main(result.get("page") or "")
        lines.append(f"\n## {r.get('title')}（地址 {r.get('hash', '').lstrip('#')}）" + (f" 页面标题：{result['title']}" if result.get("title") else ""))
        tabs = _texts(page, r'class="[^"]*(?:tab|hub-tab)[^"]*"[^>]*>(.*?)</', 12)
        if tabs:
            lines.append("  页签：" + "、".join(tabs))
        heads = _texts(page, r"<th[^>]*>(.*?)</th>", 24)
        if heads:
            lines.append("  表头：" + "、".join(heads))
        labels = _texts(page, r"<label[^>]*>(.*?)</label>", 16)
        if labels:
            lines.append("  筛选 / 表单：" + "、".join(labels))
        nodes = result.get("nodes") or []
        by_id = {n.get("id"): n for n in nodes}
        for n in nodes:
            depth, p = 0, n.get("parent")
            while p in by_id and depth < 6:
                depth, p = depth + 1, by_id[p].get("parent")
            kind = "子页面" if n.get("kind") == "subpage" else "抽屉" if "drawer" in str(n.get("layerSel", "")) else "弹窗"
            label = re.sub(r"^表格行\s*·\s*", "", str(n.get("label") or ""))
            text = f"{'  ' * (depth + 1)}- [{kind}] {n.get('title') or label}（点「{label}」打开）"
            fields = _texts(n.get("html") or "", r"<th[^>]*>(.*?)</th>", 12) + _texts(n.get("html") or "", r"<label[^>]*>(.*?)</label>", 12)
            if fields:
                text += "：" + "、".join(fields[:16])
            lines.append(text)
    return "\n".join(lines)


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


def expand_tree(project_id: str, page_id: str) -> list[dict]:
    """不用 AI：展开图 → 页面树。菜单分组当模块，业务页面当菜单页，点得开的子页面当下钻页、弹窗抽屉照实放进去"""
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
    pages = {}
    for r in routes:
        result = (entries.get(r.get("hash")) or {}).get("result") or {}
        heads = _texts(_main(result.get("page") or ""), r"<th[^>]*>(.*?)</th>", 12)
        heads = [h for h in heads if h not in ("操作", "序号", "#")]
        node = {"type": "page", "name": r.get("title") or r.get("hash"), "route": str(r.get("hash", "")).lstrip("#"),
                "desc": ("列：" + "、".join(heads[:8])) if heads else "", "children": []}
        made = {}
        for n in result.get("nodes") or []:
            label = re.sub(r"^表格行\s*·\s*", "", str(n.get("label") or ""))
            tab = re.match(r"^页签\s*·\s*(.+)$", label)
            kind = "tab" if tab else "drill" if n.get("kind") == "subpage" else "drawer" if "drawer" in str(n.get("layerSel", "")) else "modal"
            child = {"type": kind, "name": (tab.group(1) if tab else n.get("title") or label)[:40], "children": []}
            if kind == "drill":
                child["entry"] = f"点「{label}」"
            parent = made.get(n.get("parent"))
            (parent["children"] if parent else node["children"]).append(child)
            made[n.get("id")] = child
        pages[node["name"]] = node
    out = []
    for name, items in groups:
        kids = [pages[t] for t in items if t in pages]
        if kids:
            out.append({"type": "module", "name": name or "其他页面", "children": kids})
    return out


def source_brief(source: str) -> str:
    """没展开过：代码地图 + 页面里出现的中文（去重，按出现顺序），够模型看出有哪些页面、弹窗、字段"""
    seen, words = set(), []
    for m in re.finditer(r"[一-鿿][一-鿿A-Za-z0-9 /（）()·、-]{1,24}", source):
        w = m.group(0).strip()
        if w not in seen:
            seen.add(w)
            words.append(w)
    return ("代码地图：\n" + code_map(source)[:12_000] + "\n\n页面上出现的文字（按出现顺序）：\n" + "、".join(words))[:BRIEF_MAX]


def prototype_brief(project_id: str, page_id: str) -> str:
    text = expand_brief(project_id, page_id)
    if len(text) > 200:
        return text[:BRIEF_MAX]
    return source_brief(storage.read_page(project_id, page_id))


def messages(mode: str, text: str, current: dict | None, project_id: str = "", page_id: str = "") -> list[dict]:
    system = ("你是产品架构师，帮产品经理把需求梳理成可以直接生成原型的架构：页面树、共用的数据、业务流程。"
              "想清楚业务再写：谁用、管什么、有哪些状态、数据之间谁依赖谁。\n\n" + OUTLINE_NOTE)
    if mode == "page":
        user = ("下面是一份已有原型的结构（从原型里提取的页面、页签、表头、弹窗和子页面）。把它整理成架构："
                "菜单、页签、下钻页、弹窗抽屉、功能，页面用到的数据和它们的关系，业务流程。照原型里的叫法写。"
                + (f"\n补充说明：{text}" if text else "") + "\n<<<原型结构\n" + prototype_brief(project_id, page_id) + "\n原型结构>>>")
    elif mode == "refine" and current:
        user = ("下面是用户已经编好的架构。在它的基础上补全：缺介绍的补一句介绍，数据缺字段的补上，缺流程的补业务流程，"
                "明显漏掉的弹窗、抽屉、下钻页补上。用户已有的节点和名字都保留，别删别改名，整份写出来。"
                + (f"\n这次的要求：{text}" if text else "") + "\n<<<现在的架构\n" + to_outline(current) + "\n现在的架构>>>")
    else:
        user = "需求：" + (text or "（用户没写，按常见的后台管理系统起一个）")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse(reply: str) -> dict:
    """模型的回复 → 架构。按大纲读；万一它还是回了 JSON 也认"""
    text = re.sub(r"^```\w*\s*|\s*```\s*$", "", (reply or "").strip())
    if text.startswith("{"):
        try:
            return json.loads(text[: text.rfind("}") + 1])
        except ValueError:
            pass
    arch = from_outline(text)
    if not arch.get("nodes"):
        raise ValueError("模型没有给出架构")
    return arch


def finish(reply: str, mode: str, current: dict | None) -> dict:
    fresh = parse(reply)
    if mode == "refine" and current:
        fresh = keep_ids(fresh, current)
        fresh["rules"] = current.get("rules")
    fresh["status"] = "draft"
    return architecture.normalize(fresh)
