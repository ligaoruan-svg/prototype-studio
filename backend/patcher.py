"""Source-preserving edits: parsers locate nodes; only original ranges change."""
from __future__ import annotations

import functools

import difflib
import hashlib
import html
import re
import shutil
import subprocess
from dataclasses import dataclass
from html.parser import HTMLParser

from bs4 import BeautifulSoup


class PatchError(RuntimeError):
    pass


VOID = set("area base br col embed hr img input link meta param source track wbr".split())
MARKER = re.compile(r"^[\t ]*(?:<!--|/\*)[\t ]*#(end)?region[\t ]+([\w-]+)[\t ]*(?:-->|\*/)[\t ]*\r?$", re.M)
DEFAULT_TOKENS = {
    "--color-primary": "#b8532f", "--color-bg": "#faf9f5",
    "--color-surface": "#ffffff", "--color-text": "#141413",
    "--color-muted": "#6f6e69", "--color-border": "#e5e2d6",
    "--color-danger": "#b42318", "--color-success": "#4c7a52",
}


@dataclass
class Span:
    tag: str
    start: int
    open_end: int
    close_start: int = -1
    end: int = -1


class SourceIndex(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0] + [m.end() for m in re.finditer("\n", source)]
        self.nodes = {}
        self.stack = []
        self.feed(source)

    def position(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        start = self.position()
        node = Span(tag, start, start + len(self.get_starttag_text()))
        self.nodes[start] = node
        if tag in VOID:
            node.close_start = node.end = node.open_end
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        node = self.nodes[self.position()]
        node.close_start = node.end = node.open_end
        if self.stack and self.stack[-1] is node:
            self.stack.pop()

    def handle_endtag(self, tag):
        at = self.position()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                node = self.stack[i]
                node.close_start = at
                node.end = self.source.find(">", at) + 1
                del self.stack[i:]
                return


def locate(source: str, selector: str):
    soup = BeautifulSoup(source, "html.parser")
    try:
        matches = soup.select(selector)
    except Exception as exc:
        raise PatchError(f"无效选择器：{selector}") from exc
    if len(matches) != 1:
        raise PatchError(f"目标必须唯一命中，当前命中 {len(matches)} 处：{selector}。动态元素请搜索其模板源码。")
    node = matches[0]
    index = SourceIndex(source)
    if not node.sourceline:
        raise PatchError("无法确认元素在源码中的位置")
    at = index.lines[node.sourceline - 1] + node.sourcepos
    span = index.nodes.get(at)
    if not span or span.end < 0:
        raise PatchError("元素缺少明确的结束标签，无法安全直接编辑")
    return node, span


def regions(source: str):
    result, stack = {}, []
    for mark in MARKER.finditer(source):
        end, name = mark.groups()
        if not end:
            if name in result or any(n == name for n, _ in stack):
                raise PatchError(f"region 重复：{name}")
            stack.append((name, mark))
        else:
            if not stack or stack[-1][0] != name:
                raise PatchError(f"region 标记不匹配：{name}")
            _, start = stack.pop()
            result[name] = (start.end(), mark.start())
    if stack:
        raise PatchError(f"region 未闭合：{stack[-1][0]}")
    return result


def token_values(source: str):
    soup = BeautifulSoup(source, "html.parser")
    css = "\n".join(t.get_text() for t in soup.find_all("style"))
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+)\s*;", css))


def outline(source: str):
    return [{"name": name, "lines": source[a:b].count("\n"),
             "summary": source[a:b].strip().split("\n")[0][:100] if source[a:b].strip() else "空区块"}
            for name, (a, b) in regions(source).items()]


def closest_snippet(text: str, old: str, offset_line: int = 0):
    """FIND 没命中时，找出文件里最像它的一段真实源码。

    只告诉模型“命中 0 处”，它不知道是空格、换行还是位置错了，只能瞎猜着重试；
    把真实原文附回去，它第二次通常就能照着原样构造。
    """
    wanted = old.strip()
    lines, target = text.splitlines(), wanted.splitlines()
    if not lines or not target:
        return None
    span = len(target)
    probe = target[0].strip()[:200]
    if not probe:
        return None
    # 先用首行粗筛，避免对每个窗口做全量比对
    rough = difflib.SequenceMatcher(autojunk=False)
    rough.set_seq2(probe)
    candidates = []
    for i, line in enumerate(lines):
        rough.set_seq1(line.strip()[:200])
        if rough.real_quick_ratio() < 0.45 or rough.quick_ratio() < 0.45:
            continue
        candidates.append((rough.ratio(), i))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    full = difflib.SequenceMatcher(autojunk=False)
    full.set_seq2(wanted[:6000])
    best = None
    for _, i in candidates[:40]:
        window = "\n".join(lines[i:i + span])
        full.set_seq1(window[:6000])
        score = full.ratio()
        if best is None or score > best[0]:
            best = (score, i, window)
    if best is None or best[0] < 0.5:
        return None
    score, i, window = best
    return {"score": round(score, 2), "start": offset_line + i + 1,
            "end": offset_line + i + len(window.splitlines()), "content": window[:1600]}


def replace_unique(source, old, new, region=""):
    a, b = 0, len(source)
    if region:
        bounds = regions(source)
        if region not in bounds:
            raise PatchError(f"region 不存在：{region}")
        a, b = bounds[region]
    text = source[a:b]
    count = text.count(old) if old else 0
    if count != 1:
        message = f"FIND 必须唯一命中，当前 {count} 处；请重新读取真实片段并扩大定位范围"
        if count == 0 and old:
            near = closest_snippet(text, old, source[:a].count("\n"))
            if near:
                message += (f"\n文件里最接近的一段真实源码（第 {near['start']}–{near['end']} 行，"
                            f"相似度 {near['score']}）——请照这段原文重新构造 FIND：\n{near['content']}")
        raise PatchError(message)
    return source[:a] + text.replace(old, new, 1) + source[b:]


# ===== 脚本生成的元素：文字直接改源码里那一处字面量 =====
# 「设备总数」「在线率」这种标签在脚本里是写死的字符串，只出现一次就能直接换；
# 「4」「50%」这种是算出来的数，换不了，交给 AI。
_COMPUTED = re.compile(r"[\d\s.,，%:：¥$+\-/()（）]+")
_UNSAFE = re.compile(r"[\'\"`<>\\\n\r]|\$\{")


def literal_count(source: str, text: str) -> int:
    text = (text or "").strip()
    if len(text) < 2 or len(text) > 200 or _COMPUTED.fullmatch(text) or _UNSAFE.search(text):
        return 0
    return source.count(text)


def replace_literal(source: str, old: str, new: str) -> str:
    old, new = (old or "").strip(), (new or "").strip()
    if not new:
        raise PatchError("文字不能为空")
    if _UNSAFE.search(new) or len(new) > 200:
        raise PatchError("新文字里不能有引号、尖括号、反斜杠、换行；复杂的改动用评论交给 AI")
    n = literal_count(source, old)
    if n != 1:
        raise PatchError("这段文字在源码里出现了 %d 次，没法确定改哪一处；用评论交给 AI" % n if n
                         else "这段文字是脚本算出来的，源码里找不到原样的字；用评论交给 AI")
    return source.replace(old, new, 1)


def append_block(source, value, kind):
    closing = re.search(r"</head\s*>" if kind == "style" else r"</body\s*>", source, re.I)
    if not closing:
        raise PatchError(f"缺少 {kind} 的插入位置")
    at = closing.start()
    return source[:at] + f"\n<{kind}>\n{value}\n</{kind}>\n" + source[at:]


def set_token(source, name, value):
    if not re.fullmatch(r"--[a-zA-Z][\w-]*", name):
        raise PatchError("无效设计变量名")
    if not re.fullmatch(r"#[0-9a-fA-F]{3,8}|[\d.]+(?:px|rem|em|%)", value):
        raise PatchError("设计变量支持十六进制颜色或尺寸")
    bounds = regions(source)
    if "tokens" in bounds:
        a, b = bounds["tokens"]
        chunk = source[a:b]
        pattern = re.compile(r"(" + re.escape(name) + r"\s*:\s*)[^;{}]+(?=;)")
        if len(pattern.findall(chunk)) > 1:
            raise PatchError("变量在 tokens 区出现多次，请交给 AI 确认")
        if pattern.search(chunk):
            chunk = pattern.sub(lambda m: m.group(1) + value, chunk)
        else:
            chunk += f"\n:root {{ {name}: {value}; }}\n"
        return source[:a] + chunk + source[b:]
    return append_block(source, f"/* #region tokens */\n:root {{ {name}: {value}; }}\n/* #endregion tokens */", "style")


# 编辑模式能直接写的属性和各自允许的值。值都是封闭的写法（数字+px、设计变量、十六进制色、固定的几个词），
# 写进 CSS 规则里不会带出别的声明或选择器
_PX = r"\d{1,3}(?:\.\d{1,2})?px"
_SIGNED_PX = r"-?" + _PX
_COLOR = r"var\(--[\w-]+\)|#[0-9a-fA-F]{3}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}"
_SIZE = _PX + r"|fit-content|100%|auto"
SHADOWS = {
    "none",
    "0 1px 2px rgba(0,0,0,.06)",
    "0 4px 12px rgba(0,0,0,.08)",
    "0 12px 32px rgba(0,0,0,.12)",
}
STYLE_VALUES = {
    "color": _COLOR, "background-color": _COLOR + r"|transparent", "border-color": _COLOR,
    "font-size": _PX, "font-weight": r"[1-9]00|normal|bold", "line-height": r"\d(?:\.\d{1,2})?|" + _PX + r"|normal",
    "letter-spacing": _SIGNED_PX + r"|normal", "text-align": r"left|center|right|justify",
    "border-radius": _PX + r"|50%", "border-width": _PX, "border-style": r"none|solid|dashed|dotted",
    "padding-top": _PX, "padding-bottom": _PX, "padding-left": _PX, "padding-right": _PX,
    "margin-top": _SIGNED_PX + r"|auto", "margin-bottom": _SIGNED_PX + r"|auto",
    "margin-left": _SIGNED_PX + r"|auto", "margin-right": _SIGNED_PX + r"|auto",
    "gap": _PX,
    "display": r"none|revert|block|flex|grid|inline|inline-block|inline-flex",
    "flex-direction": r"row|column", "flex-wrap": r"wrap|nowrap", "flex": r"1 1 0%|0 0 auto|none",
    "justify-content": r"flex-start|center|flex-end|space-between|space-around",
    "align-items": r"flex-start|center|flex-end|stretch|baseline",
    "width": _SIZE, "height": _SIZE,
    "opacity": r"0|1|0?\.\d{1,2}",
}


def style_value_ok(name, value):
    if name == "box-shadow":
        return value in SHADOWS
    pattern = STYLE_VALUES.get(name)
    return bool(pattern) and re.fullmatch(pattern, value) is not None


def style_ops(source, action, selector, prop, value, more=None):
    """一次手动修改可以带几条样式（比如横向排列 = display + flex-direction），写进同一个版本；
    用到页面里还没有的设计变量先补上。"""
    more = more or {}
    pairs = [(prop, value), *((k, v) for k, v in more.items() if k != prop)]
    if len(pairs) > 6 or any(k == 'text' or k.startswith('--') for k, _ in pairs[1:]):
        raise PatchError('一次只能一起改几条样式')
    ops, tokens = [], token_values(source)
    for name, val in pairs:
        match = re.fullmatch(r'var\((--[\w-]+)\)', val)
        if match and match[1] not in tokens:
            if match[1] not in DEFAULT_TOKENS:
                raise PatchError('未知设计变量')
            ops.append({'action': 'set_token', 'name': match[1], 'value': DEFAULT_TOKENS[match[1]]})
            tokens = {**tokens, match[1]: DEFAULT_TOKENS[match[1]]}
        ops.append({'action': action, 'selector': selector, 'name': name, 'value': val})
    return ops


def set_style(source, selector, name, value):
    if name not in STYLE_VALUES and name != "box-shadow":
        raise PatchError("属性不在直接编辑范围内")
    if not style_value_ok(name, value):
        raise PatchError("这个值不能直接写入，请换一个或交给 AI 修改")
    ident = r"[\w-]+"
    attribute = r'\[data-pid=(?:"' + ident + r'"|\x27' + ident + r'\x27|' + ident + r')\]'
    qualifier = r'(?:[.#]' + ident + '|' + attribute + r'|:nth-of-type\([1-9]\d*\))'
    part = r'(?:[a-zA-Z][\w-]*(?:' + qualifier + r')*|' + qualifier + r'+)'
    if not re.fullmatch(part + r'(?:\s*(?:>|\s)\s*' + part + r')*', selector):
        raise PatchError("该元素的定位方式不适合直接写入样式，请重新点选或交给 AI 修改")
    ident = hashlib.sha256(f"{selector}/{name}".encode()).hexdigest()[:16]
    rule = f"/* edit:{ident} */ {selector} {{ {name}: {value} !important; }}"
    pattern = re.compile(r"/\* edit:" + ident + r" \*/[^\n]*")
    if pattern.search(source):
        return pattern.sub(lambda _: rule, source)
    bounds = regions(source)
    if "manual-styles" in bounds:
        _, at = bounds["manual-styles"]
        return source[:at] + rule + "\n" + source[at:]
    return append_block(source, f"/* #region manual-styles */\n{rule}\n/* #endregion manual-styles */", "style")


SHELL_HOME_NAV = "{key:'biz',label:'业务模块',items:[{key:'home',label:'首页'}]}"
SHELL_HOME_PAGE = "home(){return pageShell('首页','',`${Card({title:'内容',body:'在这里写这一页的内容'})}`)}"
SHELL_SCRIPT_AT = "// ===== 业务页面："


def shell_add(source: str, nav: str = "", pages: str = "", bind: str = "", script: str = "") -> str:
    """往页面外壳里加页面：菜单分组、页面方法、交互绑定、数据和辅助函数各放进它的位置，
    不用先读源码找占位、再一段段 replace——以前一页光找位置就要绕十来轮。外壳自带的「首页」占位顺手删掉。
    认的是代码里的那几处（const NAV=[/*PA:NAV*/ 等），不是文件开头注释里提到的同名占位。"""
    nav_at, pages_at, bind_at = "const NAV=[/*PA:NAV*/", "const Pages={/*PA:PAGES*/", "function bindPage(page){/*PA:BIND*/"
    if not all(m in source for m in (nav_at, pages_at, bind_at)):
        raise PatchError("页面不是从外壳起步的，没有 const NAV=[/*PA:NAV*/ 等位置；用 replace_source_text 改")
    if not (nav or pages or bind or script):
        raise PatchError("shell_add 至少要写 nav、pages、bind、script 中的一项")
    clean = lambda text: str(text or "").strip().rstrip(",")
    if nav:
        source = source.replace(nav_at + "\n  " + SHELL_HOME_NAV + "\n", nav_at + "\n", 1)
        source = source.replace(nav_at, nav_at + "\n  " + clean(nav) + ",", 1)
    if pages:
        source = source.replace(pages_at + "\n  " + SHELL_HOME_PAGE + "\n", pages_at + "\n", 1)
        source = source.replace(pages_at, pages_at + "\n  " + clean(pages) + ",", 1)
    if bind:
        source = source.replace(bind_at, bind_at + "\n  " + str(bind).strip() + "\n", 1)
    if script:
        at = source.find(SHELL_SCRIPT_AT)
        if at < 0:
            at = source.find("const Pages=")
        if at < 0:
            raise PatchError("外壳里找不到放脚本的位置")
        source = source[:at] + str(script).strip() + "\n" + source[at:]
    return source


def apply_operations(source: str, operations: list[dict]) -> tuple[str, list[str]]:
    logs = []
    original_regions = set(regions(source))
    for op in operations:
        action, value = op.get("action"), str(op.get("value", ""))
        selector, name = op.get("selector", ""), op.get("name", "")
        if action == "replace_source_text":
            old = op.get("old", "")
            if re.search(r"<html\b[\s\S]*</html\s*>", old, re.I):
                raise PatchError("不能替换整份 HTML，请定位具体元素或 region")
            source = replace_unique(source, op.get("old", ""), op.get("new", ""), op.get("region", ""))
        elif action == "replace_region":
            bounds = regions(source)
            region = op.get("region", "")
            if region not in bounds:
                raise PatchError(f"region 不存在：{region}")
            a, b = bounds[region]
            source = source[:a] + value + source[b:]
        elif action in {"append_style", "append_script"}:
            source = append_block(source, value, action.split("_")[1])
        elif action == "set_token":
            source = set_token(source, name, value)
        elif action == "shell_add":
            source = shell_add(source, op.get("nav", ""), op.get("pages", ""), op.get("bind", ""), op.get("script", ""))
        elif action == "set_rule":
            # 给一类元素写样式规则（脚本生成的元素在源码里没有标签，不用定位）
            source = set_style(source, selector, name, value)
        else:
            node, span = locate(source, selector)
            if span.tag in {"html", "head", "body"} and action in {"set_text", "set_html", "replace_outer_html", "remove"}:
                raise PatchError("不能重写页面根结构，请修改具体元素或 region")
            a, b = span.start, span.end
            if action == "set_style":
                source = set_style(source, selector, name, value)
                logs.append(f"{selector} · {name} → {value}")
                continue
            if action in {"set_text", "set_html"}:
                if span.tag in VOID:
                    raise PatchError("该元素没有文本内容")
                a, b = span.open_end, span.close_start
                value = html.escape(value, quote=False) if action == "set_text" else value
            elif action == "remove":
                value = ""
            elif action == "append_html":
                # 放进容器里、排在原有内容后面（insert_component inside 用），不清掉原来的子元素
                if span.tag in VOID:
                    raise PatchError("该元素不能放子内容")
                a = b = span.close_start
            elif action == "insert_before":
                b = a
            elif action == "insert_after":
                a = b
            elif action == "replace_outer_html":
                pass
            elif action in {"set_attr", "remove_attr", "add_class", "remove_class"}:
                if action in {"add_class", "remove_class"}:
                    classes = list(node.get("class", []))
                    classes = list(dict.fromkeys(classes + value.split())) if action == "add_class" else [c for c in classes if c not in value.split()]
                    name, value = "class", " ".join(classes)
                if not re.fullmatch(r"[\w:-]+", name):
                    raise PatchError("无效属性名称")
                a, b = span.start, span.open_end
                opening = source[a:b]
                pattern = re.compile(r"\s+" + re.escape(name) + r"(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?(?=[\s/>])", re.I)
                attr = "" if action == "remove_attr" else f' {name}="{html.escape(value, quote=True)}"'
                if pattern.search(opening):
                    value = pattern.sub(lambda _: attr, opening, count=1)
                elif action != "remove_attr":
                    pos = len(opening) - (2 if opening.endswith("/>") else 1)
                    value = opening[:pos] + attr + opening[pos:]
                else:
                    value = opening
            else:
                raise PatchError(f"不支持的操作：{action}")
            source = source[:a] + value + source[b:]
        logs.append(f"{action} · {selector or name or op.get('region', '源码片段')}")
        if not original_regions.issubset(regions(source)):
            raise PatchError("不能删除或改名已有 region 标记")
    return source, logs



@functools.lru_cache(maxsize=256)
def _script_issue(kind: str, code: str) -> str | None:
    """一段脚本的语法检查结果。同一段脚本只起一次 node：每次改动都要整页检查，20 段脚本就是 20 个进程"""
    node = shutil.which("node")
    if not node:
        return None
    try:
        result = subprocess.run([node, "--check", "--input-type=" + ("module" if kind == "module" else "commonjs")], input=code, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return "unchecked"
    return result.stderr[:900] if result.returncode else ""


def issue_kind(issue: str) -> str:
    """问题的种类：「脚本 3 语法错误：…」和「脚本 4 语法错误：…」是同一种（脚本序号会随前面的增删变化）"""
    return re.sub(r"\d+", "N", issue.split("：", 1)[0])


def new_issues(before: dict, after: dict) -> list[str]:
    """改动后新冒出来的问题。页面原来就有的问题（比如本来就有重复的 data-pid、某段脚本本来就报错）
    不该算到这次改动头上——否则这种页面上的任何修改都会被拒，任务必然失败"""
    have: dict[str, int] = {}
    for issue in before.get("issues", []):
        have[issue_kind(issue)] = have.get(issue_kind(issue), 0) + 1
    out = []
    for issue in after.get("issues", []):
        k = issue_kind(issue)
        if have.get(k, 0) > 0:
            have[k] -= 1
        else:
            out.append(issue)
    return out


def verify_source(source: str, assertions: list[dict] | None = None) -> dict:
    soup, issues = BeautifulSoup(source, "html.parser"), []
    if not soup.html or not soup.body or not soup.head:
        issues.append("需要完整的 html / head / body 结构")
    try:
        regions(source)
    except PatchError as exc:
        issues.append(str(exc))
    pids = [n["data-pid"] for n in soup.select("[data-pid]")]
    if len(set(pids)) != len(pids):
        issues.append("data-pid 不能重复")
    # 从页面外壳起步的页面：交互要绑在当前页上。document 级的 click 监听对所有页面一直生效，
    # 翻页、按钮会串到别的页面（实测：巡检计划翻到第 2 页，碳配额也跟着到第 2 页）
    if "/*PA:BIND*/" in source:
        hits = len(re.findall(r"document\.addEventListener\(\s*['\"](?:click|change|input)['\"]", source))
        if hits:
            issues.append(f"全局点击监听：有 {hits} 处 document.addEventListener('click'…)，会串到别的页面；"
                          "交互写进 bindPage(page) 按 page 分开，或用 PageEvents.on('页面key', 'click', 选择器, 处理函数)")
    if "/*PA:BIND*/" in source and re.search(r"location\.(?:reload|replace|assign)\(|location\.href\s*=|window\.location\s*=", source):
        issues.append("页面跳转：不要 location.reload() / location.href=…，在预览里会变成「网页无法连接」；重画用 Router.render()，换页用 location.hash")
    syntax_checked = bool(shutil.which("node"))
    for i, tag in enumerate(soup.find_all("script"), 1):
        kind = tag.get("type", "").lower()
        if tag.get("src") or kind not in {"", "text/javascript", "application/javascript", "module"}:
            continue
        if syntax_checked and tag.string:
            problem = _script_issue(kind, str(tag.string))
            if problem == "unchecked":
                syntax_checked = False
                issues.append(f"脚本 {i} 语法检查未完成")
            elif problem:
                issues.append(f"脚本 {i} 语法错误：{problem}")
    # 几段 <script> 共用一个全局作用域：两段里都写了 const planDevices，单看每段都没错，
    # 一运行第二段整段报错（Identifier has already been declared），页面就空了。拼起来再查一次
    classic = [str(tag.string) for tag in soup.find_all("script") if tag.string and not tag.get("src")
               and tag.get("type", "").lower() in {"", "text/javascript", "application/javascript"}]
    if syntax_checked and len(classic) > 1 and not any("语法错误" in i for i in issues):
        problem = _script_issue("", "\n;\n".join(classic))
        dup = re.search(r"Identifier '([\w$]+)' has already been declared", problem or "")
        if dup:
            issues.append(f"脚本之间重复声明：{dup[1]} 在两段 <script> 里都声明了（const / let / class 不能重名），删掉多余的那一份或改个名字")
    for item in assertions or []:
        try:
            matches = soup.select(item.get("selector", ""))
            if item.get("exists", True) is False:
                if matches:
                    issues.append(f"元素仍存在：{item['selector']}")
            elif not matches:
                issues.append(f"未找到：{item.get('selector')}")
            elif item.get("contains") and item["contains"] not in str(matches[0]):
                issues.append(f"内容不匹配：{item['selector']}")
        except Exception:
            issues.append("断言选择器无效")
    return {"ok": not issues, "issues": issues, "syntax_checked": syntax_checked}
