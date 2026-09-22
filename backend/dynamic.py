"""从渲染出来的 DOM 反查拼出它的那段源码。

用户点选的是浏览器里渲染出来的东西。可这份原型 86% 是脚本，
页面上看到的绝大部分在源码里根本不存在——是模板字符串拼出来的。
于是"点选"这个最该好使的能力，在这里直接失效：选择器指向的 DOM 找不到，
模型只能自己猜关键词。实测猜了八轮（badge(d.status、cx-badge、data-cx…）
仍然没同时拿到"标签怎么拼"和"这一列怎么填"这两处，最后空手而归。

这里替它猜：从 outer_html 提取特征，只在 <script> 里找，
把命中按"像不像在拼 HTML"排序后交给它。
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

# 纯布局/工具类名，几乎每个页面都有，拿它们搜等于没搜
GENERIC_CLASSES = {
    "active", "btn", "card", "cell", "col", "container", "content", "current", "disabled",
    "flex", "grid", "hidden", "icon", "item", "left", "line", "link", "list", "main",
    "panel", "right", "row", "section", "selected", "show", "small", "sm", "tag", "text",
    "title", "wrap", "wrapper", "green", "gray", "grey", "red", "blue", "yellow", "orange",
}
MAX_HITS = 12
SNIPPET = 260
# 「const badge=(t,c)=>...」「function tplStatus(t){...}」这类：一行里定义了一个生成标签的函数
DEFINES = re.compile(r"(?:function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:function|\(|\w+\s*=>))")


class _Probe(HTMLParser):
    """只看最外层那个标签的属性。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tag = ""
        self.attrs: dict[str, str] = {}
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if not self.tag:
            self.tag = tag
            self.attrs = {k: (v or "") for k, v in attrs}

    def handle_data(self, data):
        if data.strip():
            self.text.append(data.strip())


def fingerprint(outer_html: str) -> dict:
    """从一段渲染后的 DOM 里挑出能用来搜的特征。"""
    probe = _Probe()
    try:
        probe.feed(outer_html or "")
    except Exception:
        pass
    classes = [c for c in probe.attrs.get("class", "").split() if c]
    data_keys = [k for k in probe.attrs if k.startswith("data-")]
    label = " ".join(probe.text)[:40].strip()
    return {
        "tag": probe.tag,
        "classes": classes,
        "distinct_classes": [c for c in classes if c.lower() not in GENERIC_CLASSES and len(c) > 2],
        "data_keys": data_keys,
        "data_values": [probe.attrs[k] for k in data_keys if probe.attrs[k]],
        "text": label,
        # 纯数字/日期是数据不是模板，拿它搜只会搜到数据源
        "text_is_literal": bool(label) and not re.fullmatch(r"[\d\s.,:%／/+\-—–]+", label),
    }


def script_ranges(source: str) -> list[tuple[int, int]]:
    return [(m.start(1), m.end(1)) for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", source, re.S | re.I)]


def _in_scripts(source: str, ranges) -> set[int]:
    """脚本内容覆盖到的行号集合。"""
    starts = [0] + [m.end() for m in re.finditer("\n", source)]
    rows: set[int] = set()
    for a, b in ranges:
        lo = max(1, sum(1 for s in starts if s <= a))
        hi = sum(1 for s in starts if s <= b)
        rows.update(range(lo, hi + 1))
    return rows


def _looks_like_markup(line: str) -> bool:
    """这一行像不像在拼 HTML（而不是 CSS 规则或普通逻辑）。"""
    return "<" in line and ("'" in line or '"' in line or "`" in line)


def origin_hints(source: str, outer_html: str) -> dict:
    """选中的元素在源码里找不到时，去脚本里找拼出它的地方。

    排序是这里的全部难点。按行号排会把答案埋掉：像「启用」这种标签文字
    在页面里出现几百次，而 `cx-badge` 这个真线索只出现几次——
    真正有用的是**越少见的线索越可信**，不是越靠前的行越可信。
    """
    mark = fingerprint(outer_html)
    # 线索按可信度分档：data 属性最准（一般是代码专用的钩子），
    # 独特类名次之，页面文字最泛（同一个词到处都是）。
    tokens: list[tuple[str, str, int]] = []
    for key in mark["data_keys"]:
        tokens.append((key, "data 属性", 50))
    for value in mark["data_values"][:3]:
        if len(value) > 2 and not value.isdigit():
            tokens.append((value, "data 取值", 45))
    for name in mark["distinct_classes"]:
        tokens.append((name, "类名", 40))
    if mark["text_is_literal"]:
        tokens.append((mark["text"], "文字", 10))
    if not tokens and mark["tag"]:
        tokens.append((mark["tag"], "标签", 5))

    lines = source.splitlines()
    script_rows = _in_scripts(source, script_ranges(source))
    strong = {tok for tok, _, weight in tokens if weight >= 40}

    scored: dict[int, dict] = {}
    for token, kind, weight in tokens:
        rows = [i for i, line in enumerate(lines, 1) if i in script_rows and token in line]
        # 满页都是的词说明它不挑，别让它把稀有线索挤掉
        common = len(rows) > 40
        for i in rows:
            line = lines[i - 1]
            markup = _looks_like_markup(line)
            if common and not markup:
                continue
            score = weight + (25 if markup else 0) - (20 if common else 0)
            # 独特类名和页面文字同时出现在一行，基本就是它了
            if sum(1 for s in strong if s in line) and mark["text"] and mark["text"] in line:
                score += 60
            kept = scored.get(i)
            if kept is None or score > kept["score"]:
                scored[i] = {"line": i, "token": token, "kind": kind,
                             "markup": markup, "score": score,
                             "code": line.strip()[:SNIPPET]}
        if common:
            # 泛词只留分最高的几行，免得几百行噪音
            泛 = sorted((v for v in scored.values() if v["token"] == token),
                        key=lambda h: -h["score"])[3:]
            for extra in 泛:
                scored.pop(extra["line"], None)

    ranked = sorted(scored.values(), key=lambda h: (-h["score"], h["line"]))
    ranked += _call_sites(lines, script_rows, ranked[:3], mark, set(scored))
    hits = sorted(ranked, key=lambda h: (-h["score"], h["line"]))[:MAX_HITS]
    return {"fingerprint": mark, "tried": [t for t, _, _ in tokens], "hits": hits}


def _call_sites(lines, script_rows, best, mark, taken) -> list[dict]:
    """顺着生成函数往下追：谁调用了它。

    找到「badge 长什么样」只解决一半。用户要改的往往是「这一列为什么填这个值」，
    那在调用处。光靠搜文字找不到它——「启用」这种词页面上几百处，
    真正相关的那一处会被噪音淹掉。但只要知道函数叫 badge，一搜 badge( 就出来了。
    """
    found = []
    for hit in best:
        match = DEFINES.search(hit["code"])
        if not match:
            continue
        name = match.group(1) or match.group(2)
        if not name or len(name) < 3:
            continue
        for i, line in enumerate(lines, 1):
            if i in taken or i not in script_rows or i == hit["line"]:
                continue
            if not re.search(r"\b" + re.escape(name) + r"\s*\(", line):
                continue
            # 调用处里还带着用户看到的那个字，基本可以锁定
            relevant = bool(mark["text"]) and mark["text"] in line
            found.append({"line": i, "token": name + "(", "kind": f"调用了 {name}",
                          "markup": _looks_like_markup(line),
                          "score": 70 if relevant else 30,
                          "code": line.strip()[:SNIPPET]})
            taken.add(i)
    return found


def hint_text(source: str, outer_html: str) -> str:
    """整理成一段可以直接塞进提示词的话。没找到就返回空串。"""
    found = origin_hints(source, outer_html)
    if not found["hits"]:
        return ""
    mark = found["fingerprint"]
    what = mark["tag"] or "元素"
    if mark["distinct_classes"]:
        what += "." + ".".join(mark["distinct_classes"][:2])
    lines = "\n".join(
        f"- 第 {h['line']} 行（命中{h['kind']}「{h['token']}」{'，这行在拼 HTML' if h['markup'] else ''}）：{h['code']}"
        for h in found["hits"]
    )
    return (
        f"\n\n用户选中的是运行时生成的内容（{what}），源码里没有这段 DOM，改 DOM 没用。"
        f"\n已经替你在脚本里找过了，下面这些位置最可能是拼出它的地方：\n" + lines +
        "\n要改它就改这些行里的模板和逻辑；先用 read_source_slice 读具体行号确认，不要再去全页搜。"
    )
