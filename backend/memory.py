"""记忆：参照 Claude 的做法。

- 两层：「这个项目」只在本项目生效；「所有项目」是你个人的习惯（回复语气、常用风格），每个项目都带上。
  项目里的东西不会流到别的项目。
- 按类别整理：设计风格 / 交互与布局 / 业务与术语 / 协作方式。
- 三种来源：你明确说的（AI 当场调 remember）、AI 定期从最近的对话里自己整理的、你在面板里手动加的。
- 你可以直接删、改、用一句话让 AI 改（「把描边那条改成只对次要按钮」），也可以暂停（照旧遵守，不再新记）或清空。
- 只记以后还用得上的工作背景；一次性的修改、页面里已经有的内容、推测、密钥都不记。
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any, Callable

from . import storage
from .atomicio import write_atomic

MAX_ITEMS = 30          # 每一层最多这么多条，满了挤掉最早的
MAX_CHARS = 120
CATEGORIES = ("设计风格", "交互与布局", "业务与术语", "协作方式")
SCOPES = ("project", "global")
SOURCES = ("said", "auto", "manual")
SYNTH_EVERY = 4         # 攒够这么多条新的用户发言，就在后台整理一次
_GLOBAL_LOCK = threading.RLock()


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。、；：,.;:!！?？]+", "", text).lower()


def _clean(entry: dict) -> dict:
    """旧数据只有 id / text / created_at：补上类别和来源。"""
    return {"id": entry["id"], "text": entry["text"],
            "category": entry.get("category") if entry.get("category") in CATEGORIES else "设计风格",
            "source": entry.get("source") if entry.get("source") in SOURCES else "said",
            "created_at": entry.get("created_at", ""), "updated_at": entry.get("updated_at") or entry.get("created_at", "")}


# ===== 存取：项目一层存在 project.json，所有项目一层存在 data/memory.json =====
def _global_path():
    # 放在项目目录旁边（以 _ 开头，扫项目时会跳过：只认带 project.json 的文件夹）
    return storage.DATA_ROOT / "_memory.json"


def _load_global() -> dict:
    path = _global_path()
    try:
        data = json.loads(path.read_text("utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        data = {}
    return {"memory": [_clean(e) for e in data.get("memory", []) if e.get("text")], "state": data.get("state", {})}


def _save_global(data: dict) -> None:
    write_atomic(_global_path(), json.dumps(data, ensure_ascii=False, indent=2))


def listing(meta: dict) -> list[dict]:
    return [_clean(e) for e in meta.get("memory", []) if e.get("text")][:MAX_ITEMS]


def state_of(meta: dict) -> dict:
    return {"paused": False, "synth_mark": 0, "synthesized_at": "", **(meta.get("memory_state") or {})}


def snapshot(project_id: str) -> dict:
    """面板要的全部：两层各自的条目和状态。"""
    meta = storage.load_meta(project_id)
    g = _load_global()
    return {"project": {"memory": listing(meta), "state": state_of(meta)},
            "global": {"memory": g["memory"][:MAX_ITEMS], "state": {"paused": False, **g["state"]}},
            "categories": list(CATEGORIES), "max": MAX_ITEMS,
            "pending": pending_count(meta)}


def _mutate(project_id: str, scope: str, fn: Callable[[list, dict], Any]):
    """在一层记忆上改东西，改完存回去。fn(条目列表, 状态) 原地改，返回值透传。"""
    if scope == "global":
        with _GLOBAL_LOCK:
            data = _load_global()
            out = fn(data["memory"], data["state"])
            del data["memory"][:-MAX_ITEMS]
            _save_global(data)
            return out
    with storage.META_LOCK:
        meta = storage.load_meta(project_id)
        items = [_clean(e) for e in meta.get("memory", []) if e.get("text")]
        state = state_of(meta)
        out = fn(items, state)
        del items[:-MAX_ITEMS]
        meta["memory"], meta["memory_state"] = items, state
        meta["updated_at"] = storage.now_iso()
        storage.save_meta(meta)
        return out


def add(project_id: str, note: str, category: str = "", scope: str = "project", source: str = "said") -> dict:
    text = " ".join(str(note or "").split())[:MAX_CHARS]
    if len(text) < 4:
        raise ValueError("要记的内容太短，写成一句完整的约定")
    scope = scope if scope in SCOPES else "project"
    def go(items, state):
        key = _normalize(text)
        for item in items:
            if _normalize(item["text"]) == key:
                return {**item, "scope": scope, "duplicate": True}
        now = storage.now_iso()
        entry = {"id": "m" + uuid.uuid4().hex[:6], "text": text,
                 "category": category if category in CATEGORIES else "设计风格",
                 "source": source if source in SOURCES else "said", "created_at": now, "updated_at": now}
        items.append(entry)
        return {**entry, "scope": scope}
    return _mutate(project_id, scope, go)


def _find_scope(project_id: str, note_id: str) -> str | None:
    if any(e["id"] == note_id for e in listing(storage.load_meta(project_id))):
        return "project"
    if any(e["id"] == note_id for e in _load_global()["memory"]):
        return "global"
    return None


def remove(project_id: str, note_id: str) -> bool:
    scope = _find_scope(project_id, note_id)
    if not scope:
        return False
    def go(items, state):
        items[:] = [i for i in items if i["id"] != note_id]
        return True
    return _mutate(project_id, scope, go)


def update(project_id: str, note_id: str, text: str = "", category: str = "") -> dict:
    scope = _find_scope(project_id, note_id)
    if not scope:
        raise KeyError("这条记忆不存在")
    text = " ".join(str(text or "").split())[:MAX_CHARS]
    def go(items, state):
        for item in items:
            if item["id"] == note_id:
                if text:
                    if len(text) < 4:
                        raise ValueError("内容太短")
                    item["text"] = text
                if category in CATEGORIES:
                    item["category"] = category
                item["updated_at"] = storage.now_iso()
                return {**item, "scope": scope}
    return _mutate(project_id, scope, go)


def clear(project_id: str, scope: str) -> None:
    _mutate(project_id, scope if scope in SCOPES else "project", lambda items, state: items.clear())


def set_paused(project_id: str, scope: str, paused: bool) -> None:
    _mutate(project_id, scope if scope in SCOPES else "project", lambda items, state: state.update(paused=bool(paused)))


def paused(project_id: str) -> bool:
    return bool(state_of(storage.load_meta(project_id)).get("paused"))


# ===== 给 AI 看的那一段 =====
# 「以后」「一律」「统一」「别再」这类说法：多半是长期约定。只用来提醒 AI 判断，记不记由它定
# 「这几个都改成蓝色」「统一一下间距」多半是这一次的事，不在这里：提醒多了它会把一次性的要求也记进去
RULE_HINT = re.compile(r"以后|今后|往后|一律|每次|始终|总是|一直用|默认都|别再|不要再|不许|禁止|记住|规范是|风格是|所有页面都|整个项目都")


def looks_like_rule(text: str) -> bool:
    return bool(RULE_HINT.search(str(text or "")))


HOW_TO = ("用户说了以后都算数的约定（「按钮一律用描边」「表格都带斑马纹」「别再用渐变」「回复短一点」），"
          "照做之外调 remember 记下来：一次一条，用你自己的话写成一句，选好类别；"
          "只跟这个项目有关的 scope 填 project，明显是他个人在所有项目里的习惯（回复语气、常用风格）才填 global。"
          "只记他明确说过、以后还算数的；一次性的指令、你的推测、页面里已经有的内容（某个按钮做了什么、数据怎么联动）都不要记。"
          "他说不用再守某条时，调 forget 传对应的 [id]。"
          "他提到以前聊过的事（「上次说的那个颜色」）而对话记录里找不到时，用 search_chats 查以前的对话。")


def _lines(items: list[dict]) -> str:
    out = []
    for cat in CATEGORIES:
        group = [i for i in items if i["category"] == cat]
        if group:
            out.append(f"{cat}：\n" + "\n".join(f"- [{i['id']}] {i['text']}" for i in group))
    return "\n".join(out)


def index_block(meta: dict) -> str:
    """挂进系统提示的一段。以前记忆为空时整段不出现，连「什么时候该记」都没有，于是永远记不下第一条。"""
    project, mine = listing(meta), _load_global()["memory"][:MAX_ITEMS]
    stopped = state_of(meta).get("paused")
    parts = ["\n\n# 记忆"]
    if mine:
        parts.append("\n用户在所有项目里的习惯：\n" + _lines(mine))
    if project:
        parts.append("\n这个项目记住的：\n" + _lines(project))
    if mine or project:
        parts.append("\n以上对以后的改动默认遵守，不必再问一遍；和这轮的要求冲突时以这轮为准，并在 summary 里提一句。")
    else:
        parts.append("\n还没有记住任何东西。")
    parts.append("\n" + ("用户暂停了记忆：照旧遵守上面的，但不要再调 remember 记新的。" if stopped else HOW_TO))
    return "\n".join(parts)


# ===== 自己整理：每攒几条新发言，在后台把对话里值得长期记住的东西整理进来 =====
def pending_count(meta: dict) -> int:
    mark = state_of(meta).get("synth_mark", 0)
    return sum(1 for m in meta.get("chat", []) if m.get("role") == "user" and int(m.get("seq", 0) or 0) > mark)


OPS_FORMAT = ('只输出一个 JSON 对象，不要别的字：{"add":[{"text":"一句话","category":"设计风格|交互与布局|业务与术语|协作方式","scope":"project|global","evidence":"用户原话"}],'
              '"update":[{"id":"已有的 id","text":"改后的一句话","evidence":"用户原话"}],"remove":["要删的 id"]}。没有要改的就三个空数组。')


def _current(project_id: str) -> str:
    snap = snapshot(project_id)
    src = {"said": "你说的", "auto": "自己整理的", "manual": "你加的"}
    rows = [f"[{e['id']}] ({'所有项目' if scope == 'global' else '这个项目'} · {e['category']} · {src.get(e.get('source'), '你说的')}) {e['text']}"
            for scope in ("global", "project") for e in snap[scope]["memory"]]
    return "\n".join(rows) or "（还没有）"


def _parse_ops(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _flat(text: str) -> str:
    return re.sub(r"[\s，。,.!！?？「」“”\"'：:；;、]+", "", str(text or ""))


def grounded(evidence, user_text: str) -> bool:
    """自动整理的每一条都要有用户原话撑着：摘的那段话真在用户说过的话里"""
    ev = _flat(evidence)
    return len(ev) >= 4 and ev in _flat(user_text)


def apply_ops(project_id: str, ops: dict, source: str, limit: int = 5, user_text: str | None = None) -> dict:
    """把模型给的增删改落下去；每次最多改 limit 处，乱写的 id / 类别直接忽略。
    user_text 给了（自动整理）：新增和修改都要有用户原话依据，只能删自己整理出来的那些"""
    done = {"added": [], "updated": [], "removed": []}
    count = 0
    auto_ids = None
    if user_text is not None:
        snap = snapshot(project_id)
        auto_ids = {e["id"] for scope in ("global", "project") for e in snap[scope]["memory"] if e.get("source") == "auto"}
    for item in (ops.get("remove") or [])[:limit]:
        if count >= limit:
            break
        if auto_ids is not None and item not in auto_ids:
            continue   # 用户亲口说的、自己加的，自动整理不能删
        if isinstance(item, str) and remove(project_id, item):
            done["removed"].append(item); count += 1
    for item in (ops.get("update") or [])[:limit]:
        if count >= limit or not isinstance(item, dict):
            break
        if user_text is not None and not grounded(item.get("evidence"), user_text):
            continue
        try:
            done["updated"].append(update(project_id, str(item.get("id", "")), str(item.get("text", "")), str(item.get("category", ""))))
            count += 1
        except (KeyError, ValueError):
            continue
    for item in (ops.get("add") or [])[:limit]:
        if count >= limit or not isinstance(item, dict):
            break
        if user_text is not None and not grounded(item.get("evidence"), user_text):
            continue
        try:
            saved = add(project_id, str(item.get("text", "")), str(item.get("category", "")),
                        str(item.get("scope", "project")), source)
        except ValueError:
            continue
        if not saved.get("duplicate"):
            done["added"].append(saved); count += 1
    return done


SYNTH_PROMPT = """你在帮「原型工坊」整理长期记忆。像 Claude 的记忆那样：只记用户本人说过、以后换个需求也还用得上的东西。

当前记住的（括号里是来源：你说的 = 用户亲口说的；自己整理的 = 以前自动整理的）：
{current}

最近的对话（较早的在前；只有「用户」说的话算数，「设计助手」那几行只是上下文，不是用户的要求）：
{chat}

可以记的，必须是用户亲口说过的：
- 以后都算数的设计偏好、约定（「按钮一律描边」「删除都要二次确认」）
- 业务名词的含义（「配额」指年度免费排放额度）、项目给谁用、他的角色
- 他明确说过的协作习惯（「回复短一点」「别问我直接改」）——这类是他个人的习惯，scope 用 global

不要记：
- 页面现在做了什么、有哪些功能和数据关联（「发起巡检会让今日待巡 +1」）：页面源码就是事实，记了只会过时
- 只这一次的修改要求、设计助手说过的话、你从他的操作里推测的习惯
- 密钥、个人隐私

每条新增或修改都要带 evidence：用户原话里的一小段（原样摘抄，至少 4 个字）。找不到原话依据的不要写——程序会核对，对不上的直接丢掉。

顺便复核「自己整理的」那些：写的是页面功能、或者被用户后来的话推翻了（比如记着「先讨论再改」，他后来说「不要问我」），就 remove 或 update。
已经记住的不要重复。宁缺毋滥，最多 5 处变更。

""" + OPS_FORMAT

EDIT_PROMPT = """用户想这样调整「原型工坊」的记忆：{instruction}

当前记住的：
{current}

照他的意思改：可以增、删、改，没提到的不要动。新增的 scope 默认 project，他说「所有项目」「我的习惯」才用 global。

""" + OPS_FORMAT


def _chat_text(meta: dict, since: int) -> str:
    rows = []
    for m in meta.get("chat", []):
        if int(m.get("seq", 0) or 0) <= since and since:
            continue
        # 设计助手的话只留个开头当上下文：以前整段喂进去，它写的「已实现某某联动」被当成业务知识记了下来
        if m.get("role") == "user":
            rows.append(f"用户：{str(m.get('content') or '')[:400]}")
        else:
            rows.append(f"设计助手（上下文）：{str(m.get('content') or '')[:80]}")
    return "\n".join(rows[-24:])


def synthesize(project_id: str, llm: Callable[[str], str], force: bool = False) -> dict:
    """llm(提示) -> 模型回复的文字。由调用方注入，这里不碰密钥。"""
    meta = storage.load_meta(project_id)
    state = state_of(meta)
    if state.get("paused") and not force:
        return {"skipped": "paused"}
    if not force and pending_count(meta) < SYNTH_EVERY:
        return {"skipped": "not_enough"}
    latest = max([int(m.get("seq", 0) or 0) for m in meta.get("chat", [])] or [0])
    chat = _chat_text(meta, state.get("synth_mark", 0) if not force else 0)
    # 先把标记推过去：整理失败也别每轮都重试烧额度
    _mutate(project_id, "project", lambda items, st: st.update(synth_mark=latest, synthesized_at=storage.now_iso()))
    if not chat.strip():
        return {"added": [], "updated": [], "removed": []}
    ops = _parse_ops(llm(SYNTH_PROMPT.replace("{current}", _current(project_id)).replace("{chat}", chat)))
    since = state.get("synth_mark", 0) if not force else 0
    user_text = "\n".join(str(m.get("content") or "") for m in meta.get("chat", [])
                          if m.get("role") == "user" and (force or int(m.get("seq", 0) or 0) > since))
    return apply_ops(project_id, ops, "auto", user_text=user_text)


def edit_by_instruction(project_id: str, instruction: str, llm: Callable[[str], str]) -> dict:
    instruction = " ".join(str(instruction or "").split())[:300]
    if len(instruction) < 2:
        raise ValueError("说一下要怎么改")
    ops = _parse_ops(llm(EDIT_PROMPT.replace("{instruction}", instruction).replace("{current}", _current(project_id))))
    if not ops:
        raise ValueError("没听懂要怎么改，换个说法试试")
    return apply_ops(project_id, ops, "manual", limit=10)
