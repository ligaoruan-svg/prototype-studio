"""架构模式的小改：AI 只说改了哪几处（【改动】），程序照着改，没提到的节点一个字不动。

以前每次都让模型把整棵树原样抄一遍：慢、费 token，树大了会被截断，还会顺手改到别处；
编号按「名字路径」对，模块一改名，它和下面所有子项都对不上，变成「删掉一整块 + 新增一整块」。
现在改名就是改名，编号、原型里有没有的标记、只写在画布上的介绍都跟着走。

【改动】的写法（每一处一行，路径用 / 隔开，只写名字也行，名字唯一就能找到）：
  + 在「报修管理 / 报修工单」下面：     ← 后面缩进几行，写法和页面树一样
      维修工 [菜单页]：管理维修工
        维修工列表 [表格] | 列：姓名、电话
  + 在最外层：
      统计分析 [模块]
  - 删掉「报修管理 / 费用单」
  ~ 「报修工单」改名为「工单管理」
  > 把「统计」挪到「首页」下面          （挪到最外层：把「统计」挪到最外层）
  * 改「工单列表」：列：工单号、状态、维修工 | 出现：状态是待派单时     （去掉一项写「列：去掉」）

还有画完 / 改完的自动检查（problems）：按钮要打开的东西不存在、页面重名、表格叫「列表」这种通用名、
业务梳理里的对象在页面树里没页面、流转动作没有按钮。arch_chat 拿它自动修一轮。
"""
from __future__ import annotations

import copy
import re

from .arch_text import SEP, WORD_TYPE, _indent, _node_from_line, _tree
from .architecture import check, loose_name, walk

EDIT_FORMAT = """回复格式：第一行以「说明：」开头，一句话说你改了什么；空一行；然后写【改动】，每一处一行，只写要改的地方，没提到的节点程序会原样保留。
不要输出整棵页面树，不要 Markdown 代码块，不要别的解释。

【改动】的写法（路径用 / 隔开，从模块写起；名字唯一时只写名字也行）：
+ 在「报修管理 / 报修工单」下面：
    维修工 [菜单页]：管理维修工
      维修工列表 [表格] | 列：姓名、电话、在岗状态
+ 在最外层：
    统计分析 [模块]
- 删掉「报修管理 / 费用单」
~ 「报修工单」改名为「工单管理」
> 把「统计」挪到「首页」下面
> 把「统计」挪到最外层
* 改「工单列表」：列：工单号、状态、维修工 | 出现：状态是待派单时
* 改「派单」：介绍：指派维修工并约上门时间 | 类型：弹窗
「+」下面缩进的几行写法和页面树完全一样，可以带子项。「*」只写要变的属性，要去掉某个属性写「列：去掉」。
有重名的（按钮和它打开的弹窗都叫「派单」），名字后面带上类型：「派单 [弹窗]」。"""

# 表格、区块叫这些名字等于没起名
GENERIC = {"列表", "表格", "明细", "明细表", "数据表", "筛选 / 表单", "表单区"}
CLEAR = {"去掉", "（去掉）", "(去掉)", "无", "删掉", "清空"}

OP_ADD = re.compile(r"^\+\s*在(?:「(?P<path>[^」]+)」下面|(?P<root>最外层))\s*[:：]?\s*$")
OP_DEL = re.compile(r"^-\s*删掉?\s*「(?P<path>[^」]+)」")
OP_REN = re.compile(r"^~\s*「(?P<path>[^」]+)」\s*改名(?:为|成)\s*「(?P<name>[^」]+)」")
OP_MOV = re.compile(r"^>\s*把\s*「(?P<path>[^」]+)」\s*挪到(?:「(?P<to>[^」]+)」下面|(?P<root>最外层))")
OP_SET = re.compile(r"^\*\s*改\s*「(?P<path>[^」]+)」\s*[:：]\s*(?P<rest>.+)$")


def split_reply(reply: str) -> tuple[str, str, str]:
    """回复拆成 (说明, 哪种格式 ops / tree / "", 正文)"""
    text = re.sub(r"```\w*", "", reply or "").strip()
    m = re.match(r"^\s*说明[:：]\s*(.+?)\s*(?:\n|$)", text)
    summary, body = (m.group(1).strip(), text[m.end():].strip()) if m else ("", text)
    if re.search(r"^\s*【改动】", body, re.M):
        return summary, "ops", body.split("【改动】", 1)[1]
    if re.search(r"^\s*【(?:页面|页面树)】", body, re.M):
        return summary, "tree", body
    return summary, "", body


def parse_ops(body: str) -> list[dict]:
    """【改动】下面那几行 → [{op, path, …}]。「+」后面缩进的几行一起读成要加的子树"""
    ops: list[dict] = []
    lines = (body or "").replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        m = OP_ADD.match(line)
        if m:
            base = _indent(lines[i - 1])
            block = []
            while i < len(lines) and (not lines[i].strip() or (_indent(lines[i]) > base and not re.match(r"^[+\-~>*]\s", lines[i].strip()))):
                block.append(lines[i])
                i += 1
            nodes = _tree(block)
            if nodes:
                ops.append({"op": "add", "path": m.group("path") or "", "nodes": nodes, "line": line})
            continue
        for op, rx in (("remove", OP_DEL), ("rename", OP_REN), ("move", OP_MOV), ("set", OP_SET)):
            m = rx.match(line)
            if m:
                ops.append({"op": op, **{k: v for k, v in m.groupdict().items() if v is not None}, "line": line})
                break
    return ops


def _parts(path: str) -> list[str]:
    return [p.strip() for p in re.split(r"\s*(?:/|／|›|>)\s*", path or "") if p.strip()]


def find(nodes: list[dict], path: str) -> tuple[dict | None, list[dict] | None]:
    """按路径找节点，返回 (节点, 它所在的那一层列表)。路径对不上就看最后一段名字是不是唯一"""
    names = _parts(path)
    if not names:
        return None, None
    # 重名时可以带类型：「派单 [弹窗]」
    m = re.match(r"^(.*?)\s*[\[［【]([^\]］】]+)[\]］】]$", names[-1])
    kind = WORD_TYPE.get(m.group(2).strip()) if m else None
    if m:
        names[-1] = m.group(1).strip()

    def same(n, name, last=False):
        ok = n["name"] == name or loose_name(n["name"]) == loose_name(name)
        return ok and (not last or not kind or n.get("type") == kind)
    level, holder, hit = nodes, nodes, None
    for i, name in enumerate(names):
        last = i == len(names) - 1
        hit = next((n for n in level if n["name"] == name and same(n, name, last)), None) or next((n for n in level if same(n, name, last)), None)
        if not hit:
            break
        holder, level = level, hit.get("children") or []
    if hit:
        return hit, holder
    found = [(n, parents) for n, _, parents in walk(nodes) if same(n, names[-1], True)]
    if len(found) != 1:
        return None, None
    node, parents = found[0]
    return node, (parents[-1]["children"] if parents else nodes)


def _set(node: dict, rest: str) -> bool:
    """「列：a、b | 出现：xx | 介绍：… | 类型：弹窗」改到节点上；「去掉」就是删掉这一项"""
    changed = False
    for part in SEP.split(rest):
        km = re.match(r"^(?P<k>[^:：]+)[:：]\s*(?P<v>.*)$", part.strip())
        if not km:
            continue
        word, value = km.group("k").strip(), km.group("v").strip()
        if word in ("介绍", "说明", "描述"):
            node.pop("desc", None) if value in CLEAR else node.__setitem__("desc", value)
            changed = True
            continue
        if word == "类型":
            kind = WORD_TYPE.get(value.strip("[]［］【】"))
            if kind:
                node["type"], changed = kind, True
            continue
        parsed = _node_from_line(f"x | {word}：{value if value not in CLEAR else 'x'}", 3)
        keys = [k for k in parsed if k not in ("name", "type", "children")]
        for key in keys:
            if value in CLEAR:
                node.pop(key, None)
                if key == "action":
                    node.pop("target", None)
            else:
                node[key] = parsed[key]
            changed = True
    return changed


def apply_ops(nodes: list[dict], ops: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """在一份拷贝上照着改。返回 (改好的树, 做了的, 没对上的)。没对上的跳过，不影响别的"""
    tree = copy.deepcopy(nodes)
    done, failed = [], []
    for op in ops:
        kind = op["op"]
        if kind == "add":
            if op["path"]:
                parent, _ = find(tree, op["path"])
                if not parent:
                    failed.append(f"没找到「{op['path']}」，没加上")
                    continue
                target = parent.setdefault("children", [])
            else:
                target = tree
            for new in op["nodes"]:
                if any(n["name"] == new["name"] and n.get("type") == new.get("type") for n in target):
                    failed.append(f"「{new['name']}」已经在那里了，没重复加")
                    continue
                target.append(new)
                done.append(f"加了「{new['name']}」")
            continue
        node, holder = find(tree, op["path"])
        if not node:
            failed.append(f"没找到「{op['path']}」")
            continue
        if kind == "remove":
            holder.remove(node)
            done.append(f"删了「{node['name']}」")
        elif kind == "rename":
            done.append(f"「{node['name']}」改名为「{op['name']}」")
            node["name"] = op["name"].strip()[:40]
        elif kind == "move":
            if op.get("root"):
                target = tree
            else:
                dest, _ = find(tree, op.get("to", ""))
                if not dest or dest is node or any(n is dest for n, _, _ in walk([node])):
                    failed.append(f"没法把「{node['name']}」挪到「{op.get('to', '')}」下面")
                    continue
                target = dest.setdefault("children", [])
            holder.remove(node)
            target.append(node)
            done.append(f"挪了「{node['name']}」")
        elif kind == "set":
            if _set(node, op["rest"]):
                done.append(f"改了「{node['name']}」")
            else:
                failed.append(f"「{node['name']}」要改的属性没看懂：{op['rest'][:30]}")
    return tree, done, failed


def _verb(action: str) -> str:
    """「派单：待派单→处理中（客服）」→「派单」"""
    return re.split(r"[:：（(]", action, 1)[0].strip()


def problems(arch: dict) -> list[str]:
    """画完 / 改完自动查一遍，返回要修的问题（给 AI 修、也给人看）。只挑确定有问题的，不报「还没写介绍」这种"""
    nodes = arch.get("nodes") or []
    out = [i["text"] for i in check(arch) if i["level"] == "error" or i["text"].startswith("有两个页面都叫")]
    flat = [(n, parents) for n, _, parents in walk(nodes)]
    for n, parents in flat:
        if n.get("type") in ("table", "block") and n["name"] in GENERIC:
            where = parents[-1]["name"] if parents else ""
            out.append(f"「{where}」里的{'表格' if n['type'] == 'table' else '区块'}叫「{n['name']}」，起个具体的名字")
    spec = arch.get("spec") or {}
    if spec and nodes:
        scope = spec.get("scope") or {}
        skip = " ".join((scope.get("out") or []) + (scope.get("external") or []))
        text = " ".join(n["name"] + " " + (n.get("desc") or "") for n, _ in flat)
        buttons = [n["name"] for n, _ in flat if n.get("type") in ("button", "feature")]
        for obj in spec.get("objects") or []:
            name = obj["name"]
            if name in skip:
                continue
            if loose_name(name) not in loose_name(text) and name not in text:
                out.append(f"业务对象「{name}」在页面树里没有对应的页面")
                continue
            for action in obj.get("actions") or []:
                verb = _verb(action)
                if verb and not any(verb in b or (len(b) >= 2 and b in verb) for b in buttons):
                    out.append(f"「{name}」的「{verb}」这个动作没有按钮")
    seen: list[str] = []
    for p in out:
        if p not in seen:
            seen.append(p)
    return seen[:12]
