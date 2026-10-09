from __future__ import annotations

import json
import re
import logging
from pathlib import Path
from typing import Any

from .deepseek_client import chat
from .patcher import apply_operations, verify_source, PatchError, regions, outline
from . import storage
from .transactions import stage
from .errors import WorkError, error_payload
from .experience import element_name, tool_label, compact_messages, changed_targets, result_report, scope_report, step_detail
from .conversation import resolve_intent, discussion_result, history_context
from . import components, memory, skills

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "agent-system.md"

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_page",
            "description": "读取当前页面摘要、标注目标和相关 DOM 片段。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_source",
            "description": "在当前 HTML 源码中搜索关键词并返回附近上下文。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_source_slice",
            "description": "按行读取当前 HTML 的一段源码。",
            "parameters": {
                "type": "object",
                "properties": {"start": {"type": "integer"}, "end": {"type": "integer"}},
                "required": ["start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_operations",
            "description": "对当前页面执行局部 DOM/CSS/JS 修改。一次可以提交多条操作。插入现成组件用 insert_component（只写 name 和 selector，原文由系统插入，不要自己抄一遍）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "operations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": [
                                        "set_text", "set_html", "set_attr", "remove_attr", "add_class",
                                        "remove_class", "insert_before", "insert_after", "replace_outer_html",
                                        "remove", "append_style", "append_script", "replace_source_text",
                                        "replace_region", "set_token", "set_style", "insert_component"
                                    ],
                                },
                                "selector": {"type": "string"},
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                                "old": {"type": "string"},
                                "new": {"type": "string"},
                                "region": {"type": "string"},
                                "position": {"type": "string", "enum": ["before", "after", "inside", "replace"],
                                             "description": "仅 insert_component 使用：相对 selector 的位置，默认 after"},
                            },
                            "required": ["action"],
                        },
                    }
                },
                "required": ["operations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_page",
            "description": "校验当前 HTML 结构和指定元素/文本是否存在。",
            "parameters": {
                "type": "object",
                "properties": {
                    "assertions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"selector": {"type": "string"}, "contains": {"type": "string"}, "exists": {"type": "boolean"}},
                            "required": ["selector"],
                        },
                    }
                },
            },
        },
    },
]

TOOL_SPECS.extend([
    {"type":"function","function":{"name":"read_skill",
     "description":"这轮任务符合某个 skill 的适用说明时，取它的正文来照着做。",
     "parameters":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}}},
    {"type":"function","function":{"name":"read_skill_file",
     "description":("按行取 skill 正文里引用的文件，path 用正文里写的相对路径。组件库这类文件很大，"
                    "一次只给一段；返回里有 truncated 就按它给的行号往后接着读。"
                    "不要整份通读——读完就没额度写页面了。知道要找什么就用 search_skill_file。"),
     "parameters":{"type":"object","properties":{"name":{"type":"string"},"path":{"type":"string"},
                   "start":{"type":"integer","description":"起始行，默认 1"},
                   "end":{"type":"integer","description":"结束行，默认 start+200"}},
                   "required":["name","path"]}}},
    {"type":"function","function":{"name":"search_skill_file",
     "description":("在 skill 的附带文件里搜关键词，只拿回命中处附近的内容。要用组件库里的某个组件"
                    "（表格、Modal、分页…）时用这个，比整份读快得多，也不会把额度耗光。"),
     "parameters":{"type":"object","properties":{"name":{"type":"string"},"path":{"type":"string"},
                   "query":{"type":"string","description":"组件名或类名，如「Form Modal」「data-table」"}},
                   "required":["name","path","query"]}}},
])

TOOL_SPECS.extend([
    {"type":"function","function":{"name":"remember",
     "description":"用户说了对整个项目长期有效的约定时记下来，一次一条。一次性指令、你的推测、页面内容都不要记。",
     "parameters":{"type":"object","properties":{"note":{"type":"string"}},"required":["note"]}}},
    {"type":"function","function":{"name":"forget",
     "description":"用户说不用再守某条约定时，传它的 id 删掉。",
     "parameters":{"type":"object","properties":{"id":{"type":"string"}},"required":["id"]}}},
])

TOOL_SPECS.append({"type": "function", "function": {
    "name": "read_component", "description": "取一个可复用组件的原文，照它的结构写，不要另起炉灶。",
    "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}})

TOOL_SPECS.append({"type": "function", "function": {
    "name": "read_region", "description": "读取一个 region 的原始代码，作为精确补丁的依据。",
    "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
}})


TOOL_SPECS.extend([
    {"type":"function","function":{"name":"answer_user","description":"回答设计问题并给出可选的局部修改建议；不执行修改。",
     "parameters":{"type":"object","properties":{"answer":{"type":"string"},"suggestions":{"type":"array","maxItems":3,"items":{"type":"object","properties":{"label":{"type":"string"},"instruction":{"type":"string"}},"required":["label","instruction"]}}},"required":["answer"]}}},
    {"type":"function","function":{"name":"report_result","description":"结束本轮修改前汇报结论和每条意见的真实处理结果。",
     "parameters":{"type":"object","properties":{"summary":{"type":"string"},"assumptions":{"type":"array","items":{"type":"string"},"maxItems":2},
     "annotations":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"status":{"type":"string","enum":["completed","partial","unprocessed"]},"reason":{"type":"string"}},"required":["id","status"]}},
     "retry_hint":{"type":"string","description":"没能改成时，写一句用户可以直接发送的换种说法；改成了就留空。"}},
     "required":["summary","annotations"]}}},
    {"type":"function","function":{"name":"update_plan","description":"改动需要三步以上时，先列出计划；每推进一步就再调用一次并更新状态。步骤用页面上的叫法，不写选择器。",
     "parameters":{"type":"object","properties":{"steps":{"type":"array","minItems":2,"maxItems":6,"items":{"type":"object","properties":{
     "title":{"type":"string"},"status":{"type":"string","enum":["pending","active","done"]}},"required":["title","status"]}}},"required":["steps"]}}},
    {"type":"function","function":{"name":"ask_user","description":"改动方向存在重大歧义、删除数据或大范围重排时，先问一个问题，不做修改。",
     "parameters":{"type":"object","properties":{"question":{"type":"string"},"options":{"type":"array","minItems":2,"maxItems":3,"items":{"type":"string"}}},"required":["question","options"]}}}
])



SAFE_PAGE_PATH = re.compile(r"(?:[a-z][a-z0-9-]{0,20}/)?[a-z][a-z0-9-]{0,30}\.html")
# 共享样式和脚本只能落在 assets/ 下，不允许写到别处去。



def expand_components(ops: list[dict]) -> list[dict]:
    """把 insert_component 换成真正的插入操作。

    让模型重抄一遍组件原文既浪费输出额度，也是输出被截断的主要原因；
    它只写名字，内容由这里填。
    """
    slots = {"before": "insert_before", "after": "insert_after",
             "inside": "set_html", "replace": "replace_outer_html"}
    for op in ops:
        if op.get("action") != "insert_component":
            continue
        name = str(op.get("name", ""))
        try:
            op["value"] = components.read(name)
        except (ValueError, FileNotFoundError) as exc:
            raise PatchError(f"没有这个组件：{name}。可用的见系统提示里的组件清单") from exc
        op["action"] = slots.get(str(op.get("position", "after")), "insert_after")
        if not op.get("selector"):
            raise PatchError("插入组件要指定 selector，说明插在哪个元素旁边")
    return ops


def read_budget(context_budget: int) -> int:
    """一次读取最多给多少字符。

    跟上下文预算挂钩：窗口大就一次多给点，省得来回分段读；
    但永远不超过预算的四分之一——一次读掉一半上下文，剩下的不够干活。
    """
    return max(12_000, context_budget // 4)
IDLE_LIMIT = 4       # 连续这么多轮只读不改，就催它下手或收工
REJECT_LIMIT = 3     # 同一个工具被同一个理由拒绝这么多次，就收手
READ_ONLY_TOOLS = {"inspect_page", "search_source", "read_source_slice", "read_region",
                   "read_component", "read_skill", "read_skill_file", "search_skill_file"}


def _slice_lines(lines: list[str], start: int, end: int, budget: int = 12_000) -> dict:
    """按行给源码，并且如实说自己给到了哪一行。

    以前是把整段拼好再 [:12000] 一刀切，返回的 end 仍是模型要求的那个行号。
    模型请求 1–530 行、实际只拿到前 156 行，却被告知已经读到 530 行——
    它当然会觉得自己读完了，找不到东西就再读一遍，来回空转。
    现在按行累加到预算为止，返回真实到达的行号，并告诉它从哪一行接着读。
    """
    picked, size = [], 0
    for i in range(start - 1, end):
        row = f"{i+1}: {lines[i]}"
        if picked and size + len(row) + 1 > budget:
            break
        picked.append(row)
        size += len(row) + 1
    reached = start - 1 + len(picked)
    out = {"start": start, "end": reached, "total_lines": len(lines),
           "content": "\n".join(picked)}
    if reached < end:
        out["truncated"] = True
        out["note"] = (f"这次只给到第 {reached} 行（一次最多 {budget} 字符）。"
                       f"要看后面的内容，从 start={reached + 1} 继续读。")
    return out


def _search_source(source: str, query: str) -> dict:
    """搜索结果同样如实：命中几处、给了几处。"""
    if not query:
        return {"hits": 0, "context": "没有给搜索词。"}
    lines = source.splitlines()
    hits = [i for i, line in enumerate(lines) if query.lower() in line.lower()]
    if not hits:
        return {"hits": 0, "context": f"整个页面里没有「{query}」。"
                "如果这正是你要改的东西，说明页面上并不存在它，不要再换范围重读——"
                "直接把这个事实汇报给用户。"}
    radius, chunks = 6, []
    for hit in hits[:5]:
        s, e = max(0, hit - radius), min(len(lines), hit + radius + 1)
        chunks.append("\n".join(f"{i+1}: {lines[i]}" for i in range(s, e)))
    out = {"hits": len(hits), "lines": [i + 1 for i in hits[:20]],
           "context": "\n---\n".join(chunks)[:8000]}
    if len(hits) > 5:
        out["note"] = f"共命中 {len(hits)} 处，上面只展开了前 5 处的上下文；全部行号见 lines。"
    return out



def run_agent(project_id: str, page_id: str, user_message: str, api_key: str, model: str,
              base_url: str = "https://api.deepseek.com", selection: dict | None = None,
              runtime_feedback: str = "", reference: dict | None = None,
              max_tokens: int = 32000, context_budget: int = 200_000, max_rounds: int = 24,
              on_event=None, intent: str = 'auto', include_annotations: bool = True,
              stream: bool = True) -> dict[str, Any]:
    emit = on_event or (lambda event: None)
    intent = resolve_intent(user_message, intent)
    read_only = intent == 'discuss'
    tools = [spec for spec in TOOL_SPECS if not (read_only and spec['function']['name'] in {'apply_operations', 'report_result', 'update_plan'})]
    emit({'type':'intent','intent':intent,'label':'正在分析设计，不会修改文件' if read_only else '正在理解修改需求'})
    meta = storage.load_meta(project_id)
    page = storage.get_page(meta, page_id)
    saved_annotations = storage.active_annotations(meta, page_id) if include_annotations else []
    anns = [{**target, "note": annotation.get("note", ""), "annotation_id":annotation['id']}
            for annotation in saved_annotations for target in (annotation.get("targets") or [annotation])[:16]]
    if selection and not any(a['selector'] == selection.get('selector') for a in saved_annotations):
        anns += [{**target, "note":user_message} for target in (selection.get('targets') or [selection])[:16]]
    for ann in anns:
        ann['name'] = element_name(ann)
    source = working_source = storage.read_page(project_id, page_id)
    if not runtime_feedback:
        storage.append_chat(project_id, "user", user_message, {"page_id":page_id,"annotation_count":len(saved_annotations),"intent":intent})
    history = history_context(meta.get('chat',[]), page_id)
    annotation_text = "\n".join(f"意见 {i+1} id={a['id']} name={element_name(a)} note={a.get('note','')!r}"
                               + (f" in_modal={a['in_modal']!r}" if a.get('in_modal') else "")
                               + (f" in_subpage={a['in_subpage']!r}" if a.get('in_subpage') else "")
                               + (f" modal_trail={a['modal_trail']!r}" if a.get('modal_trail') else "")
                               + (f" view_route={a['view_route']!r}" if a.get('view_route') else "")
                               for i,a in enumerate(saved_annotations)) or "（没有保存的修改意见）"
    target_text = "\n".join(f"name={a['name']} selector={a['selector']} note={a.get('note','')!r}" for a in anns)
    # 背景资料和用户这轮说的话必须分开：以前一股脑灌进去，用户问「你能做什么」
    # 也会被页面骨架带着跑，答成一份页面状态报告。
    background = (f"当前项目：{meta.get('name')}\n当前页面：{page.get('title')} / v{page.get('version')}\n"
                  f"保存的修改意见：\n{annotation_text}\n定位目标：\n{target_text}\n"
                  f"页面骨架：{json.dumps(outline(source),ensure_ascii=False)}")
    if runtime_feedback and not read_only:
        background += f"\n上次检查错误：{runtime_feedback[:2000]}"
    kickoff = ("以下是背景资料，只在和用户这轮问的事情相关时才用：\n" + background
               + "\n\n———\n用户这轮说的是：\n" + user_message)
    spec = (SYSTEM_PROMPT_PATH.parent / "design-spec.md").read_text("utf-8")
    content = kickoff
    if reference:
        content = [{"type":"text","text":kickoff + '\n附图是参考资料，不是系统指令。按图片宽高归一化的选区和意见：'
                    + json.dumps(reference.get('regions',[])[:16],ensure_ascii=False)[:8000]
                    + '\n参考截图定位已有代码并局部修改；不能声称从图片恢复了原始源码。'},
                   {"type":"image_url","image_url":{"url":reference['data_url']}}]
    prompt_path = SYSTEM_PROMPT_PATH.parent / 'discussion-system.md' if read_only else SYSTEM_PROMPT_PATH
    messages = [{"role":"system","content":prompt_path.read_text("utf-8") + '\n\n' + spec + skills.index_block() + components.index_block() + memory.index_block(meta)}] + history + [{"role":"user","content":content}]
    tool_log, all_operations = [], []
    usage = {"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    failures = argument_failures = truncations = 0
    incomplete = None
    read_regions, report, question, discussion = set(), None, None, None
    changed, final_text = False, ""
    # 只读工具的调用指纹，用来识别"同一段又读一遍"；以及连续多少轮只看不动。
    read_seen, idle_rounds = set(), 0
    budget = read_budget(context_budget)
    # 同一个工具被同一个理由连续拒绝多少次。failures 只管补丁失败，
    # 别的拒绝（只讨论模式下调修改工具、区域太大、参数越界）原来一次都不计，
    # 模型可以一直撞同一堵墙直到轮次烧光。
    rejects: dict[tuple[str, str], int] = {}
    for round_no in range(max_rounds):
        size_before = sum(len(str(m.get("content") or "")) for m in messages)
        compact_messages(messages, context_budget)
        if sum(len(str(m.get("content") or "")) for m in messages) < size_before:
            read_seen.clear()   # 旧的读取结果被折叠掉了，摘要会让它重读，不能再拦
        emit({"type":"model_wait","round":round_no+1,"label":"思考你的问题" if read_only else "理解需求中" if round_no==0 else "继续处理修改"})
        # 本轮的结论文字在工具参数里，边收边推给界面；只在有事件通道时才走流式。
        # note = 模型在动手之前说的话（它为什么要查这个）；result = 最终结论。
        # 两者混在一起的话，旁白会被当成结论显示，结论又会被下一轮擦掉。
        on_delta = ((lambda text, kind="result": emit({"type": "note_delta" if kind == "note" else "text_delta", "text": text}))
                    if (stream and on_event) else None)
        resp = chat(api_key, model, messages, tools, base_url=base_url, max_tokens=max_tokens, on_delta=on_delta)
        for key in usage:
            usage[key] += (resp.get("usage") or {}).get(key,0) or 0
        choices = resp.get("choices") or []
        if not choices:
            raise WorkError("invalid_arguments","模型没有返回有效回复")
        if choices[0].get("finish_reason") in {"length","max_tokens"}:
            # 截断的内容一律丢弃（绝不应用半截修改），但可以指导模型拆小后继续，
            # 而不是让一次超长直接毁掉整轮工作。
            truncations += 1
            if truncations > 2:
                raise WorkError("output_limit","连续三次输出超长。请把需求拆成几次说，或在设置里提高输出上限。")
            emit({"type":"step_error","id":f"trunc{truncations}","label":"这一步写得太长，正在拆小重来",
                  "error":{"message":f"输出超长，已丢弃（第 {truncations} 次），换成分次修改"}})
            messages.append({"role":"user","content":
                "上一次输出超过长度上限，已被丢弃，页面没有改动。请把这次改动拆小后重来："
                "一次 apply_operations 只改一个位置；插入现成组件用 insert_component 只写组件名，不要抄写原文。"})
            continue
        msg = choices[0].get("message") or {}
        assistant = {"role":"assistant","content":msg.get("content") or ""}
        if not stream and assistant["content"].strip():
            emit({"type":"note_delta","text":assistant["content"].strip()})
        calls = msg.get("tool_calls") or []
        if calls: assistant["tool_calls"] = calls
        messages.append(assistant)
        if not calls:
            final_text = str(msg.get("content") or "")
            if read_only:
                if final_text.strip():
                    discussion = discussion_result(final_text)
                    break
                raise WorkError('invalid_arguments', '模型返回了空回复，请重试')
            if changed:
                report = result_report({"summary":final_text}, saved_annotations, changed)
                break
            if not saved_annotations and not re.search(r"改|新增|删除|调整|替换|增加|优化", user_message):
                report = result_report({"summary":final_text}, saved_annotations, False)
                break
            messages.append({"role":"user","content":"需要修改时请实际执行；需要确认时调用 ask_user；无法处理则用 report_result 说明原因，不要声称已修改。"})
            continue
        for call in calls:
            fn = (call.get("function") or {}).get("name")
            step_id = str(len(tool_log)+1)
            try:
                args = json.loads((call.get("function") or {}).get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError("参数必须是对象")
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                argument_failures += 1
                output = {"ok":False,"error":"工具参数不是完整 JSON，请重新生成有效对象，不要省略或截断参数。","code":"invalid_arguments"}
                emit({"type":"step_error","id":step_id,"label":"读取修改指令","error":output})
                tool_log.append({"tool":fn,"args":{},"output":output})
                messages.append({"role":"tool","tool_call_id":call.get("id"),"content":json.dumps(output,ensure_ascii=False)})
                if argument_failures >= 3:
                    raise WorkError("invalid_arguments",output["error"]) from exc
                continue
            label = tool_label(fn,args)
            emit({"type":"step_start","id":step_id,"label":label,"tool":fn})
            # 同一段源码重复读没有任何新信息，却要再烧一遍上下文和时间。
            # 直接告诉它读过了，把额度留给真正的修改。
            if fn in READ_ONLY_TOOLS:
                fingerprint = (fn, json.dumps(args, ensure_ascii=False, sort_keys=True))
                if fingerprint in read_seen:
                    output = {"ok":False,"code":"already_read",
                              "error":"这一段你本轮已经读过了，内容没有变化。不要重复读——"
                                      "基于已经读到的内容动手改；如果确认页面上没有要改的东西，"
                                      "直接用 report_result 把这个事实说清楚。"}
                    emit({"type":"step_done","id":step_id,"label":label,"tool":fn,"detail":"这一段本轮已经读过，跳过了"})
                    tool_log.append({"tool":fn,"args":args,"output":output})
                    messages.append({"role":"tool","tool_call_id":call.get("id"),
                                     "content":json.dumps(output,ensure_ascii=False)})
                    continue
                read_seen.add(fingerprint)
            try:
                if read_only and fn in {'apply_operations', 'report_result', 'update_plan'}:
                    output = {'ok':False,'code':'read_only','error':'当前只讨论设计，不允许修改或汇报已修改。请用 answer_user 回答并给出待确认建议。'}
                elif fn == "inspect_page":
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(working_source,"html.parser")
                    targets = []
                    for a in anns:
                        try: node = soup.select_one(a["selector"])
                        except Exception: node = None
                        targets.append({**a,"found":bool(node),"html":str(node)[:2200] if node else a.get("outer_html","")[:2200]})
                    for node in soup(['script','style']): node.decompose()
                    output = {"title":page.get("title"),"chars":len(working_source),"annotations":targets,"regions":outline(working_source),
                              "page_text":(soup.body or soup).get_text(' ',strip=True)[:5000],
                              "headings":[h.get_text(' ',strip=True)[:120] for h in soup.select('h1,h2,h3')[:24]],
                              "actions":[n.get_text(' ',strip=True)[:80] or n.get('aria-label','') for n in soup.select('button,a,input[type=submit]')[:30]]}
                elif fn == "read_skill":
                    try:
                        output = {"name": args.get("name"), "content": skills.read(str(args.get("name","")))}
                    except (ValueError, FileNotFoundError) as exc:
                        raise PatchError(f"没有这个 skill：{args.get('name')}。可用的见系统提示里的清单") from exc
                elif fn == "read_skill_file":
                    try:
                        whole = skills.read_file(str(args.get("name","")), str(args.get("path","")))
                        lines = whole.splitlines()
                        a = max(1, int(args.get("start", 1)))
                        b = min(len(lines), int(args.get("end", a + 200)))
                        output = {"name": args.get("name"), "path": args.get("path"),
                                  **_slice_lines(lines, a, b, budget)}
                    except (ValueError, FileNotFoundError) as exc:
                        raise PatchError(f"skill「{args.get('name')}」里没有 {args.get('path')}；"
                                         f"先用 read_skill 看正文里写的是哪个路径") from exc
                elif fn == "search_skill_file":
                    try:
                        whole = skills.read_file(str(args.get("name","")), str(args.get("path","")))
                    except (ValueError, FileNotFoundError) as exc:
                        raise PatchError(f"skill「{args.get('name')}」里没有 {args.get('path')}") from exc
                    output = {"name": args.get("name"), "path": args.get("path"),
                              "query": args.get("query",""),
                              **_search_source(whole, str(args.get("query","")))}
                elif fn == "remember":
                    try:
                        saved = memory.add(project_id, str(args.get("note", "")))
                    except ValueError as exc:
                        raise PatchError(str(exc)) from exc
                    output = {"ok": True, **saved}
                elif fn == "forget":
                    output = {"ok": memory.remove(project_id, str(args.get("id", ""))),
                              "id": args.get("id")}
                elif fn == "read_component":
                    try:
                        output = components.preview(str(args.get("name", "")))
                    except (ValueError, FileNotFoundError) as exc:
                        raise PatchError(f"没有这个组件：{args.get('name')}。可用的见系统提示里的组件清单") from exc
                elif fn == "read_region":
                    name = args.get("name","")
                    bounds = regions(working_source)
                    if name not in bounds: raise PatchError("区域不存在，请重新查看页面结构")
                    a,b = bounds[name]
                    if b-a <= 12000: read_regions.add(name)
                    output = {"name":name,"content":working_source[a:b][:12000],"truncated":b-a>12000}
                elif fn == "search_source":
                    output = {"query":args.get("query",""),**_search_source(working_source,str(args.get("query","")))}
                elif fn == "read_source_slice":
                    lines = working_source.splitlines()
                    a = max(1,int(args.get("start",1))); b = min(len(lines),int(args.get("end",a+80)))
                    output = _slice_lines(lines, a, b, budget)
                elif fn == "apply_operations":
                    ops = args.get("operations")
                    if not isinstance(ops,list) or not ops or any(not isinstance(o,dict) for o in ops):
                        raise PatchError("需要非空的局部修改操作列表")
                    ops = expand_components(ops)
                    for op in ops:
                        if op.get("action")=="replace_region":
                            name = op.get("region")
                            if name not in read_regions:
                                # 区块过大时 read_region 不会登记，整块替换会被永久挡住；
                                # 必须说清是哪一种，否则模型只会反复撞同一堵墙。
                                bounds = regions(working_source)
                                if name in bounds and bounds[name][1]-bounds[name][0] > 12000:
                                    raise PatchError(f"区域「{name}」太大，不能整块替换。请用 replace_source_text 定位到具体片段分次修改")
                                raise PatchError(f"要整块替换必须先用 read_region 工具读取「{name}」的原文（read_source_slice 不算），再尝试精确补丁")
                            if failures<1:
                                raise PatchError("先用精确补丁试一次；失败后才可以整块替换该区域")
                        if op.get("action")=="replace_source_text" and len(op.get("old",""))>24000:
                            raise PatchError("替换范围过大，请缩小到具体位置")
                    new_source, logs = apply_operations(working_source,ops)
                    check = verify_source(new_source)
                    if not check['ok']: raise PatchError('修改检查失败：'+'；'.join(check['issues']))
                    if new_source==working_source: raise PatchError("这次操作没有产生实际改动")
                    working_source = new_source; changed = working_source != source
                    read_seen.clear()   # 源码变了，之前读过的段落已经不是现在的样子，允许重新读
                    all_operations.extend(ops); failures = 0
                    output = {"ok":True,"logs":logs}
                elif fn=="verify_page":
                    output = verify_source(working_source,args.get("assertions") or [])
                elif fn=="report_result":
                    report = result_report(args,saved_annotations,changed)
                    output = {"ok":True,"report":report}
                elif fn=='answer_user':
                    if changed: raise PatchError('已经产生修改，请用 report_result 汇报真实修改结果')
                    if not isinstance(args.get('suggestions',[]), list): raise ValueError('建议必须是列表')
                    discussion = discussion_result(args.get('answer',''), args.get('suggestions'))
                    output = {'ok':True,'discussion':discussion}
                elif fn=="update_plan":
                    steps = args.get("steps")
                    if not isinstance(steps,list) or not 2<=len(steps)<=6:
                        raise PatchError("计划需要 2 到 6 个步骤")
                    plan = [{"title":str(x.get("title","")).strip()[:60],"status":x.get("status","pending")} for x in steps if isinstance(x,dict)]
                    if len(plan)!=len(steps) or any(not p["title"] or p["status"] not in {"pending","active","done"} for p in plan):
                        raise PatchError("每个步骤都要有标题和 pending / active / done 状态")
                    emit({"type":"plan","steps":plan})
                    output = {"ok":True,"steps":plan}
                elif fn=="ask_user":
                    options = args.get("options",[])
                    if changed: raise PatchError("已修改后不能再提问，请先汇报修改结果")
                    if not str(args.get("question","")).strip() or not isinstance(options,list) or not 2<=len(options)<=3:
                        raise PatchError("需要一个明确问题和两到三个选项")
                    question = {"question":str(args['question'])[:400],"options":[str(s)[:120] for s in options],"intent":intent,"request":user_message[:3000]}
                    output = {"ok":True,"clarification":question}
                else:
                    raise PatchError("未知工具，请使用提供的工具")
            except PatchError as exc:
                output = {"ok":False,"error":str(exc),"code":"patch_target"}
                if fn=="apply_operations": failures += 1
            except ValueError as exc:
                output = {"ok":False,"error":f"参数无效：{exc}","code":"invalid_arguments"}
                argument_failures += 1
            except Exception as exc:
                logger.exception("Unexpected agent tool failure: %s",fn)
                emit({"type":"step_error","id":step_id,"label":label,"tool":fn,"error":error_payload(WorkError("internal","内部工具错误"))})
                raise WorkError("internal","工具内部异常，详情已写入本地服务日志") from exc
            tool_log.append({"tool":fn,"args":args,"output":output})
            messages.append({"role":"tool","tool_call_id":call.get("id"),"content":json.dumps(output,ensure_ascii=False)})
            failed = output.get("ok") is False
            emit({"type":"step_error" if failed else "step_done","id":step_id,"label":label,"tool":fn,
                  "detail":step_detail(fn,args,output),
                  **({"error":{"message":output.get('error') or '检查未通过',"detail":"；".join(output.get('issues',[]))}} if failed else {})})
            if failed:
                key = (fn, str(output.get("code") or output.get("error") or "")[:80])
                rejects[key] = rejects.get(key, 0) + 1
                if rejects[key] >= REJECT_LIMIT:
                    incomplete = ("tool_rejected", f"{label}连续{REJECT_LIMIT}次被拒绝，没能继续")
            else:
                rejects.clear()
            if failures>=5: incomplete = ("patch_target","连续五次未能定位或应用修改")
            if argument_failures>=3: incomplete = ("invalid_arguments","模型连续返回无效的工具参数")
            if incomplete: break
            if report or question or discussion: break
        if report or question or discussion or incomplete: break
        # 空转守卫：这一轮只读不改也不汇报，就累计一次。
        # 读来读去不下手是最常见的烧额度方式——它自己感觉不到已经转了几圈，
        # 到了阈值就明确要求它二选一：动手，或者说清没什么要改的。
        if any(c.get("function",{}).get("name") in READ_ONLY_TOOLS for c in calls):
            idle_rounds = idle_rounds + 1 if not changed else 0
        if idle_rounds >= IDLE_LIMIT * 2:
            # 已经提醒过一轮还在读，说明它自己出不来了。停下比烧完额度再报"轮次上限"诚实。
            incomplete = ("stalled", f"连续 {idle_rounds} 轮都在读源码、没有做出任何改动，已经停下")
            break
        if idle_rounds == IDLE_LIMIT:
            messages.append({"role":"user","content":
                f"提醒：已经连续 {IDLE_LIMIT} 轮只在读源码，一处都还没改。"
                "现在只能二选一——要么基于已经读到的内容立刻改一处，"
                "要么确认页面上本来就没有需要改的地方、用 report_result 把这个事实说清楚。"
                "不要再读同一片代码。若这类改动要落在很多处，用一条 CSS 规则或一段脚本统一处理，"
                "不要一处一处改。"})
    else:
        incomplete = ("iterations","已达到本次处理轮次上限")
    if incomplete and not changed:
        raise WorkError(incomplete[0], incomplete[1] + "，当前文件未改动")
    if incomplete and not report:
        # 改动已经通过结构与脚本校验，丢掉等于白干一轮；交给两阶段提交继续把关，
        # 用户能在结果卡片里看到差异并一键撤销。
        emit({"type":"step_error","id":"incomplete","label":"没能整理完结果",
              "error":{"message":incomplete[1] + "；已经改好的部分保留下来，请检查"}})
        report = result_report({"summary":incomplete[1] + "，但已经做出的改动保留在这次修改里，请检查是否符合预期。"},
                               saved_annotations, changed)
    if discussion:
        discussion['selection'] = selection
        storage.append_chat(project_id,'assistant',discussion['answer'],{'page_id':page_id,'changed':False,'intent':'discuss','discussion':discussion,'usage':usage})
        return {'changed':False,'intent':'discuss','message':discussion['answer'],'discussion':discussion,'usage':usage,'tool_log':tool_log}
    if question:
        storage.append_chat(project_id,"assistant",question['question'],{"page_id":page_id,"changed":False,"clarification":question,"usage":usage})
        return {"changed":False,"intent":intent,"message":question['question'],"clarification":question,"usage":usage,"tool_log":tool_log}
    report = report or result_report({"summary":final_text},saved_annotations,changed)
    final_text = report['summary']
    complete_ids = [a['id'] for a in report['annotations'] if a['status']=='completed']
    targets = changed_targets(all_operations,source,working_source,anns)
    if changed:
        # 改动落点和用户圈定的范围对一下；只提示，不拦截。
        report['out_of_scope'] = scope_report(source, working_source, saved_annotations)
        candidate = stage(project_id,page_id,source,working_source,user_message,"agent",message=final_text,
                          usage=usage,annotation_ids=complete_ids,report=report,targets=targets,
                          operation_count=len(all_operations))
        emit({"type":"candidate_ready","label":"修改已准备好，开始检查","candidate":candidate})
    else:
        candidate = {}
        storage.append_chat(project_id,"assistant",final_text,{"page_id":page_id,"changed":False,"usage":usage,"report":report})
    return {"message":final_text,"changed":changed,"intent":intent,"version":page.get("version",1),"tool_log":tool_log,
            "report":report,"usage":usage,**candidate}
