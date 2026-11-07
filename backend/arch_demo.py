"""演示数据也由程序生成（3C）：照列表页配置里出现的字段，按梳理里的每个状态生成 2–3 条。
编号、日期、金额、人名、下拉选项、引用别的数据（维修工）都由程序填；描述、备注这类文字放进 Demo.text，
AI 只把那一小段换成贴合业务的话——以前 AI 一口气写两三万字数据，最耗时也最容易手误。
"""
from __future__ import annotations

import re

from .arch_fields import parse_field
from .arch_gen import JS, js, key_of, name_key

PEOPLE = ["张三", "李四", "王五", "赵六", "钱七", "孙八", "周九", "吴十"]
PLACES = ["阳光花园 3 栋 201", "翠湖苑 1 栋 502", "锦绣家园 7 栋 1103", "金色港湾 2 栋 806"]
PERSON = re.compile(r"(姓名|人|业主|客服|主管|员|工)$")
NAME = re.compile(r"(姓名|名称|名字)$")
MONTH = re.compile(r"(月份|账期)$")
CODE = re.compile(r"(编号|单号|工号|编码|代码)$")


def _fields(cfgs: list[dict]) -> dict[str, dict]:
    """一份数据在各页出现过的字段：{名字: {type, options}}；表单、筛选写了类型的为准"""
    out: dict[str, dict] = {}

    def add(key, kind="", options=None):
        if not key or key == "status" or not isinstance(key, str):
            return
        cur = out.setdefault(key, {"type": "", "options": []})
        if kind and not cur["type"]:
            cur["type"] = kind
        if isinstance(options, list) and options and not cur["options"]:
            cur["options"] = options
    for cfg in cfgs:
        for c in cfg.get("columns") or []:
            if "value" not in c and "render" not in c:
                add(c["key"], "money" if c.get("money") else "")
        for f in cfg.get("filters") or []:
            add(f["key"], f.get("type", ""), f.get("options"))
        for a in (cfg.get("actions") or []) + (cfg.get("toolbar") or []):
            for f in a.get("form") or []:
                if not f.get("readonly"):
                    add(f["key"], f.get("type", ""), f.get("options"))
        for f in (cfg.get("detail") or {}).get("fields") or []:
            add(f["key"], "money" if f.get("money") else "")
    return out


def _states(name: str, cfgs: list[dict], spec: dict) -> list[str]:
    obj = next((o for o in (spec or {}).get("objects") or [] if o["name"] == name), None)
    if obj and obj.get("states"):
        return obj["states"]
    for cfg in cfgs:     # 没写状态的（材料价目）：看有没有状态筛选、页签
        if cfg.get("tabs"):
            return [t for t in cfg["tabs"] if t != "全部"]
        f = next((f for f in cfg.get("filters") or [] if f["key"] == "status" and isinstance(f.get("options"), list)), None)
        if f:
            return f["options"]
    return []


def _prefix(cfgs: list[dict], keys: dict) -> str:
    route = keys.get(cfgs[0]["title"], "") if cfgs else ""
    parts = [p for p in re.split(r"[-_]", route) if p and not re.fullmatch(r"p\d+", p)]
    return ("".join(p[0] for p in parts) if len(parts) > 1 else (parts[0][:2] if parts else "NO")).upper()


def demo(cfgs_by_data: dict[str, list[dict]], spec: dict, keys: dict) -> tuple[str, list[str]]:
    """→ (script, 要 AI 换成真话的字段)。script 放在 Store.flow 后面、页面渲染前"""
    texts: dict[str, list[str]] = {}
    rows_by: dict[str, list[dict]] = {}
    namefield: dict[str, str] = {}
    # 梳理里的字段表：每份数据的字段以它为准补全；没有页面、但被别人关联的对象（维修工）也生成，关联才取得到
    objects = {o["name"]: o.get("fields") or [] for o in (spec or {}).get("objects") or []}
    cfgs_by_data = {**cfgs_by_data, **{o: [] for o, fs in objects.items() if fs and o not in cfgs_by_data}}
    fields_by = {d: _fields(c) for d, c in cfgs_by_data.items()}
    for data, fields in fields_by.items():
        for raw in objects.get(data, []):
            f = parse_field(raw)
            meta = fields.setdefault(key_of(f["name"]), {"type": "", "options": []})
            if f["type"] == "ref" and f["options"]:
                meta["ref"] = f["options"][0]
            elif not f["guessed"] or not meta["type"]:
                meta["type"] = f["type"]
                if f["options"] and f["type"] in ("select", "radio", "multi") and not meta["options"]:
                    meta["options"] = f["options"]
        namefield[data] = name_key(objects[data]) if objects.get(data) else \
            next((f for f in fields if NAME.search(f)), next((f for f in fields if CODE.search(f)), ""))
    # 别的数据里写了选项的同名字段（业主评价的「报修分类」）：照用那些选项
    shared = {f: m["options"] for fs in fields_by.values() for f, m in fs.items() if m["options"]}
    # 几份数据都有的编号（工单费用里的「工单编号」）：状态最多的那份是正主，别的从它那儿取，对得上
    states_of = {d: _states(d, c, spec) for d, c in cfgs_by_data.items()}
    owner = {}
    for d, fs in fields_by.items():
        for f in fs:
            if CODE.search(f):
                owner[f] = max([o for o in fields_by if f in fields_by[o]], key=lambda o: (len(states_of[o]), o == d))
    for data, cfgs in cfgs_by_data.items():
        fields, states = fields_by[data], states_of[data]
        count = min(18, max(6, 3 * len(states))) if states else 8
        prefix = _prefix(cfgs, keys)
        rows = []
        for i in range(count):
            row: dict = {}
            if states:
                row["status"] = states[i % len(states)]
            for f, meta in fields.items():
                kind, options = meta["type"], meta["options"] or shared.get(f, [])
                ref = next((d for d in cfgs_by_data if d != data and (f == d or f in d or d in f) and namefield.get(d)), "")
                if meta.get("ref"):     # 关联：从对方那份数据里取名字
                    row[f] = JS(f"Demo.pick({js(meta['ref'])},{js(namefield.get(meta['ref']) or name_key(objects.get(meta['ref'], [])))},{i})")
                elif CODE.search(f) and owner.get(f, data) != data:
                    row[f] = JS(f"Demo.pick({js(owner[f])},{js(f)},{i})")
                elif CODE.search(f):
                    row[f] = f"{prefix}{20261100 + i + 1}" if "工号" not in f else f"W{i + 1:03d}"
                elif MONTH.search(f):     # 月份一条一个（同一个月只有一张对账单）
                    row[f] = JS(f"Demo.at({-30 * i}).slice(0,7)")
                elif options:
                    row[f] = options[i % len(options)]
                elif kind == "datetime" or f.endswith("时间"):
                    row[f] = JS(f"Demo.at({-(i % 9)},{8 + i % 10},{(i * 13) % 60})")
                elif kind == "date" or f.endswith("日期"):
                    row[f] = JS(f"Demo.at({-(i % 9)}).slice(0,10)")
                elif kind == "money" or re.search(r"(费|费用|金额|价|总额|合计)$", f):
                    row[f] = round(60 + (i * 37) % 420 + (i % 3) * 0.5, 2)
                elif kind == "number" or re.search(r"(数|次数|数量)$", f):
                    row[f] = 1 + (i * 3) % 9
                elif re.search(r"(星级|评分)$", f):
                    row[f] = 3 + i % 3
                elif f.endswith("率"):
                    row[f] = f"{80 + (i * 7) % 20}%"
                elif kind == "check":
                    row[f] = i % 3 == 0
                elif kind == "file" or re.search(r"(照片|图片|附件)$", f):
                    row[f] = f"{f}{i % 3 + 1}.jpg"
                elif ref:     # 引用别的数据（维修工、材料）：从那份数据里取名字，对得上
                    row[f] = JS(f"Demo.pick({js(ref)},{js(namefield[ref])},{i})")
                elif re.search(r"(电话|手机)", f):
                    row[f] = f"138****{1001 + i * 7:04d}"
                elif re.search(r"(地址|位置)$", f):
                    row[f] = PLACES[i % len(PLACES)]
                elif PERSON.search(f) and not NAME.search(f) or f == "姓名":
                    row[f] = PEOPLE[i % len(PEOPLE)]
                else:     # 描述、备注、名称这类：放进 Demo.text，交给 AI 换成真话
                    tag = f"{data}·{f}"
                    texts.setdefault(tag, [f"{f}示例{n}" for n in range(1, 4)])
                    row[f] = JS(f"Demo.t({js(tag)},{i})")
            rows.append(row)
        rows_by[data] = rows
    head = ("// ===== 演示数据（程序照画布生成）：文字都在 Demo.text 里，换成贴合业务的话就行；别再 Store.define 同一份 =====\n"
            "const Demo={text:" + js(texts) + ",\n"
            "  at(d,h=9,m=0){const t=new Date();t.setDate(t.getDate()+d);t.setHours(h,m,0,0);const p=n=>String(n).padStart(2,'0');"
            "return `${t.getFullYear()}-${p(t.getMonth()+1)}-${p(t.getDate())} ${p(h)}:${p(m)}`},\n"
            "  t(k,i){const l=this.text[k]||[];return l.length?l[i%l.length]:''},\n"
            "  pick(n,f,i){const l=(Store.all(n)||[]).map(r=>r[f]).filter(Boolean);return l.length?l[i%l.length]:''}};")
    # 被别人引用的先定义（维修工先于工单），Demo.pick 才取得到
    order = sorted(rows_by, key=lambda d: -sum(1 for o in rows_by if o != d and any(isinstance(v, JS) and f"Demo.pick({js(d)}" in v for r in rows_by[o] for v in r.values())))
    body = "\n".join(f"Store.define({js(d)},[\n  " + ",\n  ".join(js(r) for r in rows_by[d]) + "\n]);" for d in order)
    return head + "\n" + body, sorted(texts)
