"""拼进提示词的背景：选中的元素在哪个弹窗 / 子页面、预览现场（停在哪页、点过什么、报过什么错）、
界面语言，以及页面外壳（空外壳怎么认、外壳里现成有哪些组件和样式类）。
"""
from __future__ import annotations

import re

from .patcher import SHELL_HOME_PAGE

CONTEXT_KEYS = ("in_modal", "in_subpage", "modal_trail", "view_route")


def context_text(a: dict) -> str:
    return "".join(f" {k}={a[k]!r}" for k in CONTEXT_KEYS if a.get(k))


def scene_text(scene: dict | None) -> str:
    """预览现场写成几行话：用户说「点了没反应」「报错了」时，AI 直接知道是哪个按钮、发生了什么。"""
    if not isinstance(scene, dict):
        return ""
    text = lambda v, n=60: str(v or "").replace("\n", " ")[:n]
    lines = []
    if scene.get("route"):
        lines.append(f"预览停在：{text(scene['route'], 120)}")
    for c in [c for c in (scene.get("clicks") or []) if isinstance(c, dict)][-5:]:
        what = []
        if text(c.get("hashBefore"), 120) != text(c.get("hashAfter"), 120):
            what.append(f"地址 {text(c.get('hashBefore'), 120) or '（空）'} → {text(c.get('hashAfter'), 120) or '（空）'}")
        what.append("弹出了弹窗" if c.get("opened") else "内容有变化" if c.get("changed") else "页面没有任何变化")
        errors = [text(e, 200) for e in (c.get("errors") or [])[:3]]
        if errors:
            what.append("报错：" + "；".join(errors))
        lines.append(f"- 点了「{text(c.get('label'), 40)}」<{text(c.get('tag'), 12)}> selector={text(c.get('selector'), 200)} → {'，'.join(what)}")
    errors = [text(e, 300) for e in (scene.get("errors") or [])[-5:]]
    if errors:
        lines.append("页面报过的错：" + "；".join(errors))
    if not lines:
        return ""
    return ("\n用户在预览里的现场（按时间先后，最后一条最近）。用户说「点了没反应」「报错」「这里不对」时，"
            "先按这里的 selector 和报错去源码里找，不要从头通读：\n" + "\n".join(lines))


LANG_NAMES = {'zh': '中文', 'en': 'English'}


def language_note(lang: str) -> str:
    """界面不是中文时补一句：程序代发的指令（「按已讨论的建议修改」「【自检】……」）是中文写的，
    不能让 AI 照着它们的语言回复"""
    name = LANG_NAMES.get(lang.split('-')[0], lang)
    return (f"\n\n（用户的界面语言是 {name}。回复、汇报、计划、提问和选项都用用户自己说话的语言；"
            f"上面这句如果是程序代发的中文指令、看不出用户用什么语言，就用 {name}。"
            f"新建页面时，页面上的文字也用这种语言。）")


SHELL_NOTE = ("外壳里样式、布局、菜单、路由、弹窗、Toast 都在。**不用再读源码找位置**：\n"
                                       "下一步直接调一次 apply_operations，用一条 {action:'shell_add', nav, pages, bind, script} 把这页写完——"
                                       "nav 是菜单分组，pages 是页面方法，bind 是 bindPage 里的代码，script 是数据、状态和辅助函数；外壳的「首页」占位会自动删掉。\n"
                                       "要改外壳本身的某一处时才用 replace_source_text。三处的含义：\n"
                                       "1. /*PA:NAV*/ 后面那行菜单配置 → 这次要的一级分组和二级页面（key 就是 URL hash）\n"
                                       "2. /*PA:PAGES*/ 后面的 home(){...} → 每个二级页面一个方法，返回 pageShell(标题, 说明, 内容HTML, 右上按钮HTML)\n"
                                       "3. /*PA:BIND*/ 函数体 → 按 page 绑定这一页的按钮、筛选、行操作（或 PageEvents.on(page, …)；不要 document.addEventListener，会串页）\n"
                                       "组件直接用 ZeroUI.Button / Tag / Field / Pager / Empty / Toast / Modal / ConfirmModal / Drawer / openModal / openDrawer 和 Card()，"
                                       "签名见系统提示里的要点。样式类沿用外壳里的（card、metric-grid、data-table、lnk、tw 等），不要另写一套 CSS。"
                                       "尽量一两次 apply_operations 把整页内容写完，不要拆成十几次小改。")


def is_fresh_shell(source: str) -> bool:
    """页面是还没写内容的外壳（按风格新建项目时第一页就是它）：外壳自带的「首页」占位还在"""
    return "const Pages={/*PA:PAGES*/\n  " + SHELL_HOME_PAGE in (source or "")


def shell_api(shell: str) -> dict:
    """外壳里现成能用的：组件函数和参数、页面函数、样式类。放进 start_from_shell 的返回里，模型不用再翻源码看怎么写。"""
    objects = re.findall(r"^\s{2}(\w+):\(\{([^}]*)\}", shell, re.M)          # Button:({label,kind…})=>
    plain = re.findall(r"^\s{2}(\w+):\((\w[^)]*)\)=>", shell, re.M)          # Toast:(message,type='')=>
    helpers = re.findall(r"^const (\w+)=\(\{([^}]*)\}\)=>", shell, re.M)
    funcs = re.findall(r"^function (\w+)\(([^)]*)\)", shell, re.M)
    css = sorted(set(re.findall(r"(?:^|[},])\.([a-z][\w-]*)", shell.split("</style>")[0], re.M)))
    sig = lambda args: re.sub(r"=('[^']*'|`[^`]*`|\[\]|\{\}|[\w.]+)", "", args).replace(" ", "")
    return {"ZeroUI": [f"ZeroUI.{n}({{{sig(a)}}})" for n, a in objects if not n.startswith("_")]
                      + [f"ZeroUI.{n}({sig(a)})" for n, a in plain if not n.startswith("_")],
            "helpers": [f"{n}({{{sig(a)}}})" for n, a in helpers] + [f"{n}({a})" for n, a in funcs if n in {"pageShell", "bindPage"}],
            "events": "PageEvents.on('页面key','click','选择器',(el,e)=>{...})：只在那一页触发",
            "notes": ["ZeroUI.openModal(ZeroUI.Modal({...}), (close, 确定按钮)=>{...}, 触发按钮)：校验不过就 return，不调 close",
                      "改完数据后 Router.render() 重画当前页；每页的状态放自己的对象里（const planState={page:1}）",
                      "不要 location.reload()、不要在 document 上挂 click 监听",
                      "表格包在 <div class=\"tw\"> 里（宽了会横向滚动），不要自己起 table-wrap 之类的类名"],
            "css": css[:120]}
