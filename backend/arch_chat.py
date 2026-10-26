"""架构模式下的对话：AI 只改画布上的页面树，不碰原型代码。

把现在的树写成大纲（见 arch_text）交给模型，它回一句说明 + 改好的整份大纲；读回来时路径没变的节点沿用原来的编号，
和原型对没对上的标记（proto / seen）跟着编号走。写结构不写代码，一般几秒到十几秒。
"""
from __future__ import annotations

import re
from typing import Any, Callable

from . import architecture, storage
from .arch_text import from_outline, keep_ids, to_outline
from .deepseek_client import DeepSeekError, chat
from .errors import WorkError
from .source_map import code_map

MAX_TOKENS = 24_000

SYSTEM = """你是产品架构师，帮产品经理改原型的页面树（只做电脑端）。你只改结构，不写代码。

回复格式：第一行以「说明：」开头，一句话说你改了什么；空一行；然后输出改好后的【整份】页面树，只要【页面】这一段，不要 Markdown 代码块，不要别的解释。
用户没要求动的节点原样保留（名字、顺序、属性都别改），只改用户说的地方。

页面树写法（缩进两个空格一层，方括号里是类型，冒号后是一句介绍，| 后面是属性）：
【页面】
模块名 [模块]：一句话
  菜单页名 [菜单页]：这页干什么 | 地址：路由key
    页签名 [页签]
      筛选 [区块] | 字段：编号、名称、状态（下拉：草稿/已发布）
      列表 [表格] | 列：编号、名称、状态、更新时间
        查看 [按钮] | 打开：xx详情
        编辑 [按钮] | 打开：编辑xx | 出现：状态是草稿时
        删除 [按钮] | 二次确认：删除后不能恢复
        编号 [按钮] | 跳到：xx详情页
      新增xx [按钮] | 打开：新增xx
      导出 [按钮] | 执行：按筛选条件导出 Excel
      新增xx [弹窗] | 字段：名称*、类型*（下拉：A类/B类）、生效日期（日期）、负责人（选人）、附件（上传）、编号🔒、备注 | 确认后：列表多一行
      xx详情 [抽屉]：只读 | 字段：…
      xx详情页 [下钻页] | 入口：点列表里的编号 | 返回：返回列表
一级菜单页 [菜单页]   ← 没有分组的菜单项直接写在最外层

类型只能用：模块 菜单页 页签 下钻页 区块 表格 按钮 弹窗 抽屉 向导 功能。
字段：必填加 *；自动带出、不用填的加 🔒；控件写在最后的括号里，选项用 / 分开。控件有：文本、多行、下拉、多选、单选、勾选、日期、日期时间、日期范围、时间、数字、金额、手机号、上传、图片、开关、选人、级联、提示文字。普通文本框不用写。
查看用抽屉，新增 / 编辑用弹窗，多步用向导；行里的按钮缩进在表格下面；按状态出现的按钮写「出现：」。

后面可能附上「原型代码里的线索」（代码地图 + 每一页代码里出现的文字）。用户让你「同步 / 补全 / 对照原型」时，照原型里实际有的菜单、按钮、弹窗、抽屉、字段把页面树补全；
原型里没有的不要编。别的时候它只是参考。"""

DIGEST_MAX = 14_000


def _phrases(text: str, limit: int = 80) -> list[str]:
    """一段代码里引号中的中文短语（按钮文字、弹窗标题、字段名、提示），去重按出现顺序"""
    out: list[str] = []
    for m in re.finditer(r"['\"`]([^'\"`\n<>{}]{1,30})['\"`]", text):
        t = m.group(1).strip()
        if re.search(r"[一-鿿]", t) and t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def prototype_digest(source: str) -> str:
    """原型代码的线索：代码地图，加上每一页（Pages{…} 里的每一项）代码里的中文短语。不塞整份源码"""
    if len(source or "") < 400:
        return ""
    cmap = code_map(source)
    lines = source.split("\n")
    parts = ["代码地图：\n" + cmap[:6000]]
    m = re.search(r"L(\d+)-(\d+) Pages\{([^}]*)\}", cmap)
    marks = sorted((int(n), name) for name, n in re.findall(r"(\w+) L(\d+)", m.group(3))) if m else []
    if marks:
        ends = [n for n, _ in marks[1:]] + [int(m.group(2)) + 1]
        parts.append("每一页代码里的文字：")
        for (start, name), end in zip(marks, ends):
            parts.append(f"- {name}：" + "、".join(_phrases("\n".join(lines[start - 1:end - 1]))))
    else:
        parts.append("代码里的文字：" + "、".join(_phrases(source, 400)))
    return "\n".join(parts)[:DIGEST_MAX]


def _split(reply: str) -> tuple[str, str]:
    text = re.sub(r"```\w*", "", reply or "").strip()
    m = re.match(r"^\s*说明[:：]\s*(.+?)\s*(?:\n|$)", text)
    if not m:
        return "", text
    return m.group(1).strip(), text[m.end():].strip()


def run(project_id: str, page_id: str, message: str, key: str, model: str, base_url: str, max_tokens: int,
        on_event: Callable[[dict], None], should_stop: Callable[[], bool], stream: bool = True) -> dict[str, Any]:
    storage.append_chat(project_id, "user", message, {"page_id": page_id, "intent": "architecture"})
    current = architecture.load(project_id) or architecture.empty()
    current["name"] = current.get("name") or storage.load_meta(project_id).get("name", "")
    outline = to_outline({"name": current["name"], "nodes": current["nodes"]})
    try:
        digest = prototype_digest(storage.read_page(project_id, page_id)) if page_id else ""
    except (OSError, ValueError, KeyError):
        digest = ""
    # 原型线索放前面：同一个原型来回问几次，这一段不变，模型那边能走缓存
    clue = f"原型代码里的线索：\n<<<\n{digest}\n>>>\n\n" if digest else ""
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"{clue}现在的页面树：\n<<<\n{outline}\n>>>\n\n这次要改的：{message}"}]
    on_event({"type": "progress", "label": "AI 正在改页面树"})
    written = [0, 0]

    def on_delta(text, kind="note"):
        written[0] += len(text)
        if written[0] - written[1] >= 200:
            written[1] = written[0]
            on_event({"type": "progress", "label": f"AI 正在改页面树 · 已写 {written[0]} 字"})
    try:
        resp = chat(key, model, messages, None, base_url=base_url, max_tokens=min(MAX_TOKENS, max(8000, int(max_tokens or 16000))),
                    on_delta=on_delta if stream else None, should_stop=should_stop)
    except DeepSeekError as exc:
        if exc.code == "stopped":
            raise WorkError("stopped", "已停止，页面树没有改动") from exc
        raise
    choice = (resp.get("choices") or [{}])[0]
    summary, body = _split((choice.get("message") or {}).get("content") or "")
    fresh = from_outline(body)
    if not fresh.get("nodes"):
        cut = "（输出被截断了）" if choice.get("finish_reason") in ("length", "max_tokens") else ""
        raise WorkError("arch_unreadable", "AI 给的页面树读不出来" + cut + "，换个说法再试一次")
    fresh = keep_ids(fresh, current)
    flags = {n["id"]: {k: n[k] for k in ("proto", "seen") if n.get(k)} for n, _, _ in architecture.walk(current["nodes"])}
    for n, _, _ in architecture.walk(fresh["nodes"]):
        n.update(flags.get(n.get("id"), {}))
    current["nodes"] = fresh["nodes"]
    architecture.save(project_id, current)
    summary = summary or "页面树改好了"
    usage = resp.get("usage") or {}
    storage.append_chat(project_id, "assistant", summary, {"page_id": page_id, "changed": False, "intent": "architecture", "usage": usage})
    return {"changed": False, "intent": "architecture", "content": summary, "architecture_changed": True, "usage": usage}
