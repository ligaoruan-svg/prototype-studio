"""弹窗、表单里的字段是什么控件：下拉、日期、多行、上传……

字段在架构里还是一行字，类型写在最后的括号里，选项用斜杠分开：
  报修分类*（下拉：给排水/电气照明/门窗五金）
  预计上门时间*（日期时间）
  联系电话🔒            ← 自动带出、不用填
没写类型就按名字猜（「xx分类」是下拉、「xx时间」是日期时间、「备注」是多行），界面上会标出是猜的。
前端 frontend/src/lib/archFields.js 是同一套规则，两边要一起改。
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

FIELD_TYPES = {
    "text": "文本", "textarea": "多行", "select": "下拉", "multi": "多选", "radio": "单选", "check": "勾选",
    "date": "日期", "datetime": "日期时间", "daterange": "日期范围", "time": "时间", "number": "数字", "money": "金额",
    "phone": "手机号", "upload": "上传", "image": "图片", "switch": "开关", "person": "选人", "cascade": "级联", "note": "提示文字",
    "ref": "关联",    # 引用另一个业务对象的一条：维修工（关联：维修工）
}
TYPE_WORDS = {label: key for key, label in FIELD_TYPES.items()}
TYPE_WORDS.update({
    "输入框": "text", "文本框": "text", "单行": "text", "单行文本": "text", "多行文本": "textarea", "文本域": "textarea", "长文本": "textarea",
    "下拉框": "select", "下拉选择": "select", "选择": "select", "多选框": "multi", "复选": "multi", "单选框": "radio", "复选框": "check",
    "勾选框": "check", "日期选择": "date", "时间范围": "daterange", "日期区间": "daterange", "数值": "number", "整数": "number",
    "电话": "phone", "附件": "upload", "文件": "upload", "照片": "image", "人员": "person", "人员选择": "person", "省市区": "cascade",
    "地区": "cascade", "说明": "note", "提示": "note",
})
# 按名字猜：先命中的算
GUESS = [
    ("textarea", r"备注|说明|描述|内容|原因|意见"),
    ("image", r"照片|图片|头像"),
    ("upload", r"附件|文件|凭证|合同扫描"),
    ("daterange", r"时间段|起止|有效期|周期"),
    ("datetime", r"时间$"),
    ("date", r"日期|月份|年度|年份"),
    ("phone", r"电话|手机|联系方式"),
    ("money", r"金额|费用|价格|单价|总价"),
    ("number", r"数量|次数|个数|天数|时长|面积|年限|排序|比例|系数"),
    ("switch", r"^是否|启用|开启"),
    ("person", r"负责人|处理人|审批人|执行人|经办人|维修工|指派"),
    ("cascade", r"所在地区|省市区"),
    ("select", r"类型|分类|类别|状态|等级|级别|程度|方式|来源|性别|所属|部门|楼栋|小区|区域|模板|行业"),
]
OPTION_SPLIT = re.compile(r"\s*[/／、,，|]\s*")


def guess_type(name: str) -> str:
    for kind, pattern in GUESS:
        if re.search(pattern, name or ""):
            return kind
    return "text"


def _tail_group(text: str) -> tuple[int, int] | None:
    """最后面那对括号（里面可以再套括号）：返回 (开始, 结束)。后面只许跟 * 🔒 空格"""
    end = len(text)
    while end and text[end - 1] in "*🔒 ":
        end -= 1
    if not end or text[end - 1] not in "）)":
        return None
    depth = 0
    for i in range(end - 1, -1, -1):
        depth += text[i] in "）)"
        depth -= text[i] in "（("
        if depth == 0:
            return i, end
    return None


def parse_field(raw: str) -> dict:
    """「报修分类*（下拉：给排水/电气照明）」→ {name, must, locked, type, options, guessed}"""
    text = str(raw or "").strip()
    kind, options, locked = "", [], False
    span = _tail_group(text)
    if span:
        head, rest = (re.split(r"[：:]", text[span[0] + 1:span[1] - 1], maxsplit=1) + [""])[:2]
        head = head.strip()
        if head in TYPE_WORDS:
            kind = TYPE_WORDS[head]
            options = [o for o in OPTION_SPLIT.split(rest.strip()) if o]
            text = text[:span[0]] + text[span[1]:]
        elif head.startswith("自动"):
            locked = True
            text = text[:span[0]] + text[span[1]:]
    locked = locked or "🔒" in text or "自动带出" in text
    must = "*" in text
    name = re.sub(r"[*🔒]|自动带出", "", text).strip()
    return {"name": name, "must": must, "locked": locked, "type": kind or guess_type(name), "options": options, "guessed": not kind}


def field_text(name: str, must: bool = False, locked: bool = False, kind: str = "", options: list[str] | None = None) -> str:
    """反过来写成一行。类型和按名字猜的一样就不写（文本、猜对的都省掉），猜不对才写出来"""
    out = name + ("*" if must else "") + ("🔒" if locked else "")
    if kind and not locked and (options or kind != guess_type(name)):
        out += f"（{FIELD_TYPES[kind]}" + ("：" + "/".join(options[:8]) + ("/…" if len(options) > 8 else "") if options else "") + "）"
    return out


class _Form(HTMLParser):
    """照原型 HTML 认字段：每个 <label> 是一个字段，它后面（或里面）第一个控件定类型"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields: list[dict] = []
        self.label: dict | None = None   # 正在读的 <label>
        self.in_label = 0
        self.skip = 0                    # select / option / textarea / script 里面的字不算标签
        self.select: dict | None = None
        self.option = ""
        self.in_option = False

    def _current(self):
        return self.fields[-1] if self.fields and not self.fields[-1].get("type") else None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "label":
            self.in_label += 1
            if self.in_label == 1:
                self.label = {"name": "", "must": False, "locked": False, "type": "", "options": [], "_inputs": []}
            return
        if self.in_label and re.search(r"\breq|required|star", cls):
            self.label["must"] = True
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "select":
            self.skip += 1
            self.select = {"multi": "multiple" in a, "options": [], "locked": "disabled" in a}
        elif tag == "option" and self.select is not None:
            self.in_option, self.option = True, ""
        elif tag == "textarea":
            self.skip += 1
            self._control("textarea", locked="readonly" in a or "disabled" in a)
        elif tag == "input":
            kind = (a.get("type") or "text").lower()
            if kind in ("hidden", "submit", "button", "reset", "search"):
                return
            if self.in_label and kind in ("radio", "checkbox"):
                self.label["_inputs"].append(kind)
                return
            hint = a.get("placeholder") or ""
            if kind == "text" and re.search(r"YYYY|yyyy|年.{0,3}月", hint):
                kind = "datetime-local" if re.search(r"HH|hh|时", hint) else "date"
            mapped = {"date": "date", "datetime-local": "datetime", "time": "time", "month": "date", "number": "number",
                      "tel": "phone", "file": "upload", "checkbox": "check", "radio": "radio", "range": "number"}.get(kind, "text")
            self._control(mapped, locked="readonly" in a or "disabled" in a)
        elif re.search(r"upload|uploader", cls, re.I):
            self._control("upload")
        # 自己画的控件（div 做的下拉、日期选择）：看类名
        elif re.search(r"date-?picker|date-?range", cls, re.I):
            self._control("daterange" if re.search(r"range", cls, re.I) else "date")
        elif re.search(r"(^|[\s_-])(select|dropdown|picker|cascader)", cls, re.I):
            self._control("cascade" if "cascader" in cls.lower() else "select")
        elif re.search(r"switch|toggle", cls, re.I) and tag != "label":
            self._control("switch")

    def _control(self, kind, locked=False):
        field = self.label if self.in_label else self._current()
        if field is None or field.get("type"):
            return
        field["type"] = kind
        field["locked"] = field["locked"] or locked

    def handle_endtag(self, tag):
        if tag in ("script", "style", "textarea") and self.skip:
            self.skip -= 1
        elif tag == "option" and self.in_option:
            self.in_option = False
            if self.select is not None and self.option.strip():
                self.select["options"].append(self.option.strip())
        elif tag == "select" and self.select is not None:
            self.skip = max(0, self.skip - 1)
            sel, self.select = self.select, None
            opts = [re.sub(r"\s*[（(][^（()）]*[）)]\s*$", "", o) for o in sel["options"] if not re.match(r"^(请选择|全部|--|—|不限)", o)]
            field = self.label if self.in_label else self._current()
            if field is not None and not field.get("type"):
                field.update(type="multi" if sel["multi"] else "select", options=opts[:8])
                field["locked"] = field["locked"] or sel["locked"]
        elif tag == "label" and self.in_label:
            self.in_label -= 1
            if self.in_label:
                return
            label, self.label = self.label, None
            name = re.sub(r"\s+", " ", label["name"]).strip(" ：:")
            must = label["must"] or "*" in name
            name = name.replace("*", "").strip()
            inputs = label.pop("_inputs")
            # <label><input type=radio> 是</label>：这是上一个字段的选项，不是新字段
            if inputs and len(name) <= 8 and self.fields and self.fields[-1].get("type") in ("", "radio", "multi", "check"):
                prev = self.fields[-1]
                prev["type"] = "radio" if inputs[0] == "radio" else "multi"
                if name and name not in prev["options"]:
                    prev["options"].append(name)
                return
            if not name or len(name) > 24:
                return
            if inputs:
                label["type"] = "check"
            label.update(name=name, must=must)
            self.fields.append(label)

    def handle_data(self, data):
        if self.in_option:
            self.option += data
        elif self.in_label and not self.skip:
            self.label["name"] += data


def form_fields(html: str, limit: int = 20) -> list[str]:
    """一段弹窗 / 表单 HTML 里的字段，写成「名称*（下拉：a/b）」这种一行字"""
    parser = _Form()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 —— 原型 HTML 千奇百怪，认不出来就当没有字段
        return []
    out, seen = [], set()
    for f in parser.fields:
        if f["name"] in seen:
            continue
        seen.add(f["name"])
        # label 后面没认出控件的（可能是自己画的控件，也可能只放了一段说明）：不写类型，按名字猜
        out.append(field_text(f["name"], f["must"], f["locked"], f.get("type") or "", f.get("options") or []))
        if len(out) >= limit:
            break
    return out
