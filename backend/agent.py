from __future__ import annotations

import json
import time
import re
import logging
from typing import Any

from .deepseek_client import chat, DeepSeekError
from .patcher import apply_operations, verify_source, PatchError, regions, outline, new_issues
from . import storage
from .transactions import stage
from .errors import WorkError, error_payload
from .experience import element_name, tool_label, compact_messages, changed_targets, result_report, scope_report, step_detail
from .conversation import resolve_intent, discussion_result, history_context
from . import components, memory, skills, skill_digest
# 工具清单、读源码、拼背景拆在旁边三个文件里；下面这些名字在这里也能用（测试和别的模块按 agent.xxx 取）
from .agent_tools import TOOL_SPECS, OPERATION_ACTIONS
from .agent_source import READ_CAP, read_budget, inspect_output, expand_components, locate_lines, lines_text, _num, _slice_lines, _search_source  # noqa: F401
from .agent_lookup import LOOKUP_TOOLS, SKILL_READ_LIMIT, run_lookup  # noqa: F401
from .agent_context import CONTEXT_KEYS, context_text, scene_text, language_note, SHELL_NOTE, is_fresh_shell, shell_api

logger = logging.getLogger(__name__)

from .paths import PROMPTS, SPEC_FILE
SYSTEM_PROMPT_PATH = PROMPTS / "agent-system.md"

SHELL_MAX_EXISTING = 8000   # 页面比这还大就算「已有内容」，不许整页换成外壳
STALE_ROUNDS = 2            # 规范、组件库、读过的源码，用过这么多轮后收成一句话（不等攒满上下文预算）
IDLE_LIMIT = 4       # 连续这么多轮只读不改，就催它下手或收工
WRAPUP_AFTER = 6     # 催过还在读：只留「提问 / 汇报」两个工具，让它把找到的线索交出来，而不是报错收场
WRAPUP_TOOLS = {"ask_user", "report_result"}
WRAPUP_PROMPT = ("别再读源码了，根据已经读到的内容收个尾，三选一：\n"
                 "1. 大致知道问题在哪、还差用户一句话 → ask_user：问题里先用一句话说你查到了什么，"
                 "选项给 2–3 个最可能的位置或做法，用页面上的叫法（比如「左侧菜单的订单管理」），不写选择器；\n"
                 "2. 确认页面本来就没问题、不需要改 → report_result 说清依据；\n"
                 "3. 实在找不到 → report_result 写明查了哪几处、为什么对不上，并告诉用户怎么指给你"
                 "（点选那个元素，或在交互模式下把出问题的操作点一遍再发）。")
# 修改模式下收尾也留着 apply_operations：自检一次报五六个问题，读源码本来就要好几轮，
# 读完正要动手却只剩「提问 / 汇报」，模型就自己编一个 replace_source_text 工具去调，连拒三次整次失败
WRAPUP_EDIT_PROMPT = ("别再读源码了，根据已经读到的内容收尾：\n"
                      "0. 已经知道怎么改 → 现在就用一次 apply_operations 把能改的几处合并改掉（replace_source_text 等是 operations 里的 action，不是单独的工具），改完 report_result；\n"
                      + WRAPUP_PROMPT.split("\n", 1)[1])
REJECT_LIMIT = 3     # 同一个工具被同一个理由拒绝这么多次，就收手
# 读的是页面源码：改之前都还要用（补丁要照着原文写），只有页面改过、读到的已经不是现在的样子了才收起。
# 规范、组件库这些读完就是参考，过两轮就收——生成一页烧几十万 tokens 主要是它们
SOURCE_READS = {"inspect_page", "search_source", "read_source_slice", "read_region"}
SOURCE_KEEP_ROUNDS = 8   # 源码读取最多留这么多轮，再久就算没改也收起（防止一直攒）
READ_ONLY_TOOLS = {"inspect_page", "search_source", "read_source_slice", "read_region", "search_chats",
                   "read_component", "read_skill", "read_skill_file", "search_skill_file"}


def run_agent(project_id: str, page_id: str, user_message: str, *args, **kwargs) -> dict[str, Any]:
    """跑一次修改/讨论，并把过程（每一轮调了哪些工具、成没成、花了多少 token）记一份到项目的 runs/ 里。
    以前只记结果：撞到轮次上限时没法知道绕在了哪一步。"""
    trace: list[dict] = []
    started, outcome = time.time(), {}
    try:
        result = _run_agent(project_id, page_id, user_message, *args, trace=trace, **kwargs)
        outcome = {"changed": result.get("changed"), "intent": result.get("intent"),
                   "summary": str((result.get("report") or {}).get("summary") or result.get("message") or "")[:300],
                   "usage": result.get("usage")}
        return result
    except Exception as exc:
        outcome = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        raise
    finally:
        try:
            storage.save_run_trace(project_id, {"page_id": page_id, "request": user_message[:500], "seconds": round(time.time() - started, 1),
                                                "outcome": outcome, "rounds": _trace_rounds(trace)})
        except Exception:
            pass


def _trace_rounds(trace: list[dict]) -> list[dict]:
    rounds = []
    for i, r in enumerate(trace):
        log = r.pop("_log", [])
        end = trace[i + 1]["start"] if i + 1 < len(trace) else len(log)
        calls = []
        for item in log[r["start"]:end]:
            out = item.get("output") if isinstance(item.get("output"), dict) else {}
            calls.append({"tool": item.get("tool"), "ok": out.get("ok", True) is not False and not out.get("error"),
                          "error": str(out.get("error") or "")[:200], "args": len(json.dumps(item.get("args") or {}, ensure_ascii=False))})
        rounds.append({**{k: v for k, v in r.items() if k != "start"}, "calls": calls})
    return rounds


def _run_agent(project_id: str, page_id: str, user_message: str, api_key: str, model: str,
              base_url: str = "https://api.deepseek.com", selection: dict | None = None,
              runtime_feedback: str = "", reference: dict | None = None,
              max_tokens: int = 32000, context_budget: int = 200_000, max_rounds: int = 24,
              on_event=None, intent: str = 'auto', include_annotations: bool = True,
              stream: bool = True, should_stop=None, scene: dict | None = None, trace: list | None = None,
              start_source: str | None = None, lang: str = 'zh') -> dict[str, Any]:
    emit = on_event or (lambda event: None)
    trace = [] if trace is None else trace
    plan: list[dict] = []   # 当前计划：程序按每轮的修改自动往前推，不用模型一轮轮调 update_plan
    shell_fresh = None   # 刚放进来、还没写内容的外壳：这时候不让翻源码
    intent = resolve_intent(user_message, intent)
    read_only = intent == 'discuss'
    tools = [spec for spec in TOOL_SPECS if not (read_only and spec['function']['name'] in {'apply_operations', 'report_result', 'update_plan', 'start_from_shell'})]
    emit({'type':'intent','intent':intent,'label':'正在分析设计，不会修改文件' if read_only else '正在理解修改需求'})
    meta = storage.load_meta(project_id)
    if not skill_digest.find_shell(meta):   # 这个项目的风格没有外壳（或者选了「不选风格」），就别让它看见这个工具
        tools = [spec for spec in tools if spec['function']['name'] != 'start_from_shell']
    page = storage.get_page(meta, page_id)
    saved_annotations = storage.active_annotations(meta, page_id) if include_annotations else []
    # 在哪个业务页面 / 哪个弹窗 / 哪个子页面、怎么点进去的：多选时每个元素都带上整次选择的上下文。
    # 以前只有「先记下」的意见带着，直接选中就改时丢了——原型里同名的「保存」「下一步」一多就容易改错地方
    def placed(target, source):
        return {**{k: source[k] for k in CONTEXT_KEYS if source.get(k)}, **target}
    anns = [{**placed(target, annotation), "note": annotation.get("note", ""), "annotation_id":annotation['id']}
            for annotation in saved_annotations for target in (annotation.get("targets") or [annotation])[:16]]
    if selection and not any(a['selector'] == selection.get('selector') for a in saved_annotations):
        anns += [{**placed(target, selection), "note":user_message} for target in (selection.get('targets') or [selection])[:16]]
    for ann in anns:
        ann['name'] = element_name(ann)
    source = working_source = storage.read_page(project_id, page_id)
    # 修上一版的报错：从那一版（改好了、但运行检查没过、还没保存）接着改，提交时仍和已保存的页面比
    repairing = bool(start_source) and start_source != source
    if repairing:
        working_source = start_source
    # 点选 / 框选的目标先在源码里对好行号：AI 第一眼就知道去哪几行看，不用一段段翻
    for ann in anns:
        ann['source_lines'] = locate_lines(source, ann)
    if not runtime_feedback:
        extra = {"page_id":page_id,"annotation_count":len(saved_annotations),"intent":intent}
        # 这条消息带的截图和点选的位置也存下来：对话记录里回头还看得到「当时指的是哪」
        if reference and reference.get('data_url'):
            image_id = storage.save_chat_image(project_id, reference['data_url'])
            if image_id:
                extra.update(image=image_id, image_name=str(reference.get('name') or '')[:60],
                             image_regions=len(reference.get('regions') or []))
        if selection:
            picked = selection.get('targets') or []
            extra["target"] = (f"{len(picked)} 个元素" if selection.get('kind') == 'region' and picked else element_name(selection))[:60]
        storage.append_chat(project_id, "user", user_message, extra)
    history = history_context(meta.get('chat',[]), page_id)
    annotation_text = "\n".join(f"意见 {i+1} id={a['id']} name={element_name(a)} note={a.get('note','')!r}" + context_text(a)
                               for i,a in enumerate(saved_annotations)) or "（没有保存的修改意见）"
    target_text = "\n".join(f"name={a['name']} selector={a['selector']} note={a.get('note','')!r}" + context_text(a) + lines_text(a.get('source_lines') or []) for a in anns)
    # 背景资料和用户这轮说的话必须分开：以前一股脑灌进去，用户问「你能做什么」
    # 也会被页面骨架带着跑，答成一份页面状态报告。
    background = (f"当前项目：{meta.get('name')}\n当前页面：{page.get('title')} / v{page.get('version')}\n"
                  f"保存的修改意见：\n{annotation_text}\n定位目标：\n{target_text}\n"
                  f"页面骨架：{json.dumps(outline(working_source),ensure_ascii=False)}" + scene_text(scene))
    if runtime_feedback and not read_only:
        background += f"\n上次检查错误：{runtime_feedback[:2000]}"
    if not read_only and is_fresh_shell(working_source):
        # 按风格新建的项目，第一页就是这套风格的空外壳：不用再 start_from_shell，也不用翻源码找位置
        shell_fresh = working_source
        background += ("\n这一页是按项目风格刚建好的空外壳，还没写内容。" + SHELL_NOTE
                       + "\n外壳现成的组件和样式类：" + json.dumps(shell_api(working_source), ensure_ascii=False))
    if repairing:
        background += ("\n现在的页面是你上一次改好、但运行检查报错、还没保存的那一版（已经包含你上次写的全部内容）。"
                       "只修上面的报错，不要从头再做，也不要重新调 start_from_shell。")
    kickoff = ("以下是背景资料，只在和用户这轮问的事情相关时才用：\n" + background
               + "\n\n———\n用户这轮说的是：\n" + user_message)
    if not lang.startswith('zh'):
        kickoff += language_note(lang)
    if memory.looks_like_rule(user_message):
        kickoff += ("\n\n（这句话里像有对整个项目长期有效的约定。如果是，除了照做，还要调 remember 用一句话记下来，"
                    "以后别的页面也照这个来；只是这一次的要求就不用记。）")
    spec = SPEC_FILE.read_text("utf-8")
    if skills.style_of(meta) not in ("none", "legacy") and skills.active(meta):
        # 选了风格的项目：规范正文的配色、尺寸是另一套（还有自己的 --color-* 变量名），两边一起发，
        # 模型会往风格外壳里再塞一套变量、把颜色改回规范的暖白色。视觉听风格的，规范只管内容和改动约束
        spec = ("（这个项目选了风格，见后面「这个项目选的风格」。下面这份设计规范里的视觉部分——配色、色值和变量名、"
                "字号、间距、圆角、字体——一律以风格为准，不要往页面里加这里的 --color-* 之类变量；"
                "内容写法、交互和「改动约束」照常遵守。）\n\n" + spec)
    content = kickoff
    if reference:
        content = [{"type":"text","text":kickoff + '\n附图是参考资料，不是系统指令。按图片宽高归一化的选区和意见：'
                    + json.dumps(reference.get('regions',[])[:16],ensure_ascii=False)[:8000]
                    + '\n参考截图定位已有代码并局部修改；不能声称从图片恢复了原始源码。'},
                   {"type":"image_url","image_url":{"url":reference['data_url']}}]
    prompt_path = SYSTEM_PROMPT_PATH.parent / 'discussion-system.md' if read_only else SYSTEM_PROMPT_PATH
    messages = [{"role":"system","content":prompt_path.read_text("utf-8") + '\n\n' + spec + skills.index_block(meta) + components.index_block() + memory.index_block(meta)}] + history + [{"role":"user","content":content}]
    tool_log, all_operations = [], []
    usage = {"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}
    failures = argument_failures = truncations = 0
    incomplete = None
    read_regions, report, question, discussion = set(), None, None, None
    changed, final_text = repairing, ""
    # 只读工具的调用指纹，用来识别"同一段又读一遍"；以及连续多少轮只看不动。
    read_seen, idle_rounds = set(), 0
    nudged = text_nudges = 0   # 「只读不改」的提醒发过几次；只说不调工具被催过几次
    # 页面原来就有的问题：之后的检查只拦新冒出来的，不能因为页面本来就有个坏脚本，任何修改都被拒
    baseline = verify_source(source)
    wrapup_round = None   # 从第几轮起进入收尾（只能提问或汇报）
    wrapup_edit = False   # 是不是「读太久」的收尾：这种收尾还能直接改，改成了就回到正常处理
    reads = []            # (消息下标, 工具名, 第几轮, 读取指纹)：读规范、组件库、源码的结果，用过两轮就收起来
    writes = []           # (助手消息下标, 第几轮)：带大段修改参数的那条，用过两轮也收起来
    source_version = 0    # 页面源码改过几次：读到的源码是不是已经过时，看它
    remembered = []       # 这一轮新记住的约定：结果卡片上要让用户看见，记错了能当场撤销
    budget = read_budget(context_budget)
    # 同一个工具被同一个理由连续拒绝多少次。failures 只管补丁失败，
    # 别的拒绝（只讨论模式下调修改工具、区域太大、参数越界）原来一次都不计，
    # 模型可以一直撞同一堵墙直到轮次烧光。
    rejects: dict[tuple[str, str], int] = {}
    stopped = should_stop or (lambda: False)
    for round_no in range(max_rounds):
        # 用户点了停止：在两轮之间停下。已经改好的部分照常走检查和保存，可以一键撤销
        if stopped():
            incomplete = ("stopped", "你停止了这次处理")
            break
        # 用过的大段读取结果（规范、组件库、源码片段）过两轮就收成一句话：不等攒满上下文预算才收，
        # 否则它们会跟着后面每一步重发——一页生成 50 多万输入 tokens 大半是这么来的
        for at, name, when, fingerprint, seen_version in reads:
            content = messages[at].get("content")
            age = round_no - when
            stale = (age >= SOURCE_KEEP_ROUNDS or (age >= STALE_ROUNDS and seen_version != source_version)) if name in SOURCE_READS else age >= STALE_ROUNDS
            if stale and isinstance(content, str) and len(content) > 1500 and '"collapsed": true' not in content:
                # 说清收起的是哪一段（读的参数），它真要再看才知道读哪；只放开这一段的「读过了」拦截，别的照拦
                messages[at]["content"] = json.dumps({"collapsed": True, "tool": name, "args": json.loads(fingerprint[1]),
                    "summary": "这段读取结果前面用过了，已收起；还需要原文就按行号再读那一小段。"}, ensure_ascii=False)
                read_seen.discard(fingerprint)
        # 已经应用的大段修改：参数原文（整页 HTML、几百行新代码）留在助手消息里会跟着每一步重发，改完过两轮收成一句话
        for at, when in writes:
            for c in messages[at].get("tool_calls") or []:
                fnc = c.get("function") or {}
                if round_no - when >= STALE_ROUNDS and len(fnc.get("arguments") or "") > 1500:
                    fnc["arguments"] = json.dumps({"collapsed": True, "note": "这次修改已经应用到页面上，参数原文省略；要看现在的样子就读源码"}, ensure_ascii=False)
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
        try:
            wrapping = wrapup_round is not None and round_no >= wrapup_round
            allowed = WRAPUP_TOOLS | ({"apply_operations"} if wrapup_edit else set())
            round_tools = [t for t in tools if t["function"]["name"] in allowed] if wrapping else tools
            resp = chat(api_key, model, messages, round_tools, base_url=base_url, max_tokens=max_tokens, on_delta=on_delta,
                        on_retry=lambda n, wait, exc: emit({"type":"model_retry","round":round_no+1,"attempt":n,
                                                            "label":f"模型服务忙，{wait} 秒后自动重试（第 {n} 次）"}),
                        should_stop=stopped)
        except DeepSeekError as exc:
            if exc.code == 'stopped':
                incomplete = ("stopped", "你停止了这次处理")
                break
            # 模型中途出错（重试也没救回来）：前面已经改好、通过校验的部分不能白丢，照常交给检查和保存
            if changed:
                incomplete = (exc.code or 'network', f"模型服务中途出错（{str(exc)[:120]}）")
                break
            raise
        for key in usage:
            usage[key] += (resp.get("usage") or {}).get(key,0) or 0
        choices = resp.get("choices") or []
        trace.append({"round": round_no + 1, "finish": (choices[0].get("finish_reason") if choices else None),
                      "prompt": (resp.get("usage") or {}).get("prompt_tokens"), "completion": (resp.get("usage") or {}).get("completion_tokens"),
                      "start": len(tool_log), "_log": tool_log})
        version_at_round = source_version
        if not choices:
            raise WorkError("invalid_arguments","模型没有返回有效回复")
        if choices[0].get("finish_reason") in {"length","max_tokens"}:
            # 截断的内容一律丢弃（绝不应用半截修改），但可以指导模型拆小后继续，
            # 而不是让一次超长直接毁掉整轮工作。
            truncations += 1
            if truncations > 2:
                if changed:   # 前面已经改好、通过检查的部分留着，交给检查和保存
                    incomplete = ("output_limit", "连续三次输出超长，后面的没能继续")
                    break
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
        if any(len(((c.get("function") or {}).get("arguments") or "")) > 1500 for c in calls):
            writes.append((len(messages) - 1, round_no))
        if not calls:
            final_text = str(msg.get("content") or "")
            if read_only:
                if final_text.strip():
                    discussion = discussion_result(final_text)
                    break
                raise WorkError('invalid_arguments', '模型返回了空回复，请重试')
            if changed or (wrapup_round is not None and round_no >= wrapup_round and final_text.strip()):
                # 收尾轮直接用文字说了查到的情况：当作结论交给用户，不再追问
                report = result_report({"summary":final_text}, saved_annotations, changed)
                break
            if not saved_annotations and not re.search(r"改|新增|删除|调整|替换|增加|优化", user_message):
                report = result_report({"summary":final_text}, saved_annotations, False)
                break
            text_nudges += 1
            if text_nudges > 2 and final_text.strip():
                # 催了两次还是只用文字回：把这段话当结论，别再整份上下文重发烧轮次
                report = result_report({"summary":final_text}, saved_annotations, False)
                break
            messages.append({"role":"user","content":"需要修改时请实际执行；需要确认时调用 ask_user；无法处理则用 report_result 说明原因，不要声称已修改。"})
            continue
        offered = {t["function"]["name"] for t in round_tools}
        apply_failed = False   # 这条消息里有没有修改没成功：之后同一条里的 report_result 不能说「已改好」
        for call in calls:
            if stopped():
                incomplete = ("stopped", "你停止了这次处理")
                break
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
                    if changed:
                        incomplete = ("invalid_arguments", "模型连续返回无效的工具参数")
                        break
                    raise WorkError("invalid_arguments",output["error"]) from exc
                continue
            try:
                label = tool_label(fn,args)
            except Exception:   # 参数形状不对（operations: null 之类）也只是标签取不到，不能把整轮抛掉
                label = str(fn or "工具")
            emit({"type":"step_start","id":step_id,"label":label,"tool":fn})
            # 同一段源码重复读没有任何新信息，却要再烧一遍上下文和时间。
            # 直接告诉它读过了，把额度留给真正的修改。
            fingerprint = (fn, json.dumps(args, ensure_ascii=False, sort_keys=True))
            if fn in READ_ONLY_TOOLS:
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
                if fn in OPERATION_ACTIONS and fn not in offered and "apply_operations" in offered:
                    # 把 apply_operations 里的动作名（replace_source_text、set_text……）当成工具直接调了：替它包一层，
                    # 以前回「现在不能用」，它换个说法再调，连拒三次整次失败
                    args = {"operations": [{**args, "action": fn}]}
                    fn = "apply_operations"
                if fn not in offered:
                    # 这一步没给它这个工具（只讨论模式没有修改工具、收尾轮只能提问或汇报），它照抄了也不能执行
                    raise PatchError(f"现在不能用 {fn}；只能用这些：{'、'.join(sorted(offered))}")
                if read_only and fn in {'apply_operations', 'report_result', 'update_plan', 'start_from_shell'}:
                    output = {'ok':False,'code':'read_only','error':'当前只讨论设计，不允许修改或汇报已修改。请用 answer_user 回答并给出待确认建议。'}
                elif fn in SOURCE_READS and fn != "search_source" and shell_fresh is not None and working_source == shell_fresh:
                    # 实测：外壳放好后模型要翻十来轮源码找位置、看函数怎么写，轮次就这么烧光了。整份读外壳不给，
                    # 直接把它要找的（组件、样式类、三处位置）给它。不当成「拒绝」：以前回 ok:false，
                    # 模型一次并发三个查询就凑满三次拒绝，整次修改直接失败。搜关键词照常给（只回命中处，很便宜）
                    output = {'ok':True,'code':'shell_fresh',
                              'note':("这页还是空外壳，不用整份读。外壳里现成的东西都在下面；要确认某个名字就用 search_source 搜。"
                                      "下一步直接一次 apply_operations，用 {action:'shell_add', nav, pages, bind, script} 把这页写完。"),
                              'api': shell_api(working_source)}
                elif fn == "inspect_page":
                    output = inspect_output(working_source, page, anns)
                elif fn in LOOKUP_TOOLS:
                    output = run_lookup(fn, args, project_id, budget, remembered)
                elif fn == "start_from_shell":
                    found = skill_digest.find_shell(meta)
                    if not found:
                        raise PatchError("这个项目的风格里没有页面外壳，照常用 apply_operations 写")
                    if len(working_source) > SHELL_MAX_EXISTING and not is_fresh_shell(working_source):
                        raise PatchError("页面已经有内容了，不能整页换成外壳；用 apply_operations 局部修改")
                    skill_name, rel, shell = found
                    check = verify_source(shell)
                    if not check["ok"]:
                        raise PatchError("页面外壳本身没通过检查：" + "；".join(check["issues"]))
                    working_source = shell; changed = working_source != source; source_version += 1
                    shell_fresh = shell
                    read_seen.clear(); read_regions.clear()
                    all_operations.append({"action": "start_from_shell", "skill": skill_name, "path": rel})
                    output = {"ok": True, "chars": len(shell),
                              "note": "外壳已经放进页面。" + SHELL_NOTE,
                              "placeholders": [m for m in ("/*PA:NAV*/", "/*PA:PAGES*/", "/*PA:BIND*/") if m in shell],
                              "api": shell_api(shell)}
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
                    a = max(1,_num(args.get("start"),1)); b = min(len(lines),_num(args.get("end"),a+80))
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
                        if op.get("action")=="replace_source_text" and len(str(op.get("old") or ""))>24000:
                            raise PatchError("替换范围过大，请缩小到具体位置")
                    new_source, logs = apply_operations(working_source,ops)
                    check = verify_source(new_source)
                    fresh = new_issues(baseline, check) if not check['ok'] else []
                    if fresh: raise PatchError('修改检查失败：'+'；'.join(fresh))
                    if new_source==working_source: raise PatchError("这次操作没有产生实际改动")
                    working_source = new_source; changed = working_source != source; source_version += 1
                    # 源码变了，之前读过的段落、读过的区域都不是现在的样子：允许重读，
                    # 也不能再拿改动前读到的区域原文去整块替换（会把刚才的修改冲掉）
                    read_seen.clear(); read_regions.clear()
                    all_operations.extend(ops); failures = 0
                    output = {"ok":True,"logs":logs,"verified":True,
                              "note":"已通过结构和脚本检查，不用再调 verify_page；全部改完就直接 report_result"}
                elif fn=="verify_page":
                    output = verify_source(working_source,args.get("assertions") or [])
                    if "/*PA:BIND*/" in working_source and not output["ok"] and all(
                            i.startswith(("未找到", "内容不匹配", "元素仍存在")) for i in output["issues"]):
                        # 外壳页面的内容是脚本渲染出来的，静态 HTML 里本来就查不到：实测它会以为没写进去，再翻十来轮源码
                        output = {"ok": True, "note": ("这页的内容是脚本运行时渲染的，静态 HTML 里查不到元素是正常的，不代表没写进去。"
                                                        "结构和脚本检查已经通过；保存后程序会把每页按钮点一遍自检。直接 report_result。"),
                                  "issues": [], "syntax_checked": output.get("syntax_checked")}
                elif fn=="report_result":
                    if apply_failed:
                        raise PatchError("这条消息里前面的修改没有成功，不能按「已改好」汇报。先重试那处修改；"
                                         "确实改不了，就在下一步的 report_result 里如实说没改成、为什么")
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
                    # 状态写成 in_progress、completed、中文，或者干脆没写，都别拒——以前因为这个白退回两轮
                    norm = lambda v: ("done" if re.match(r"(?i)(done|complete|finish|已完成|完成)", str(v or "")) else
                                      "active" if re.match(r"(?i)(active|in.?progress|doing|running|进行|当前)", str(v or "")) else "pending")
                    plan[:] = [{"title":str(x.get("title") or x.get("step") or x.get("name") or "").strip()[:60],"status":norm(x.get("status"))}
                               for x in steps if isinstance(x,(dict,str))] if all(isinstance(x,dict) for x in steps) else \
                              [{"title":str(x).strip()[:60],"status":"pending"} for x in steps]
                    if any(not p["title"] for p in plan):
                        raise PatchError("每个步骤都要有标题")
                    brief = str(args.get("brief") or "").strip()[:800]
                    emit({"type":"plan","steps":plan, **({"brief": brief} if brief else {})})
                    output = {"ok":True,"steps":plan,"note":"计划记下了。之后不用再调 update_plan 更新状态，程序会按你的修改自动推进；直接动手写。"}
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
                if fn=="apply_operations": failures += 1; apply_failed = True
            except ValueError as exc:
                output = {"ok":False,"error":f"参数无效：{exc}","code":"invalid_arguments"}
                argument_failures += 1
            except Exception as exc:
                logger.exception("Unexpected agent tool failure: %s",fn)
                emit({"type":"step_error","id":step_id,"label":label,"tool":fn,"error":error_payload(WorkError("internal","内部工具错误"))})
                if changed:   # 已经改好、通过检查的部分不白丢
                    incomplete = ("internal", "工具内部异常，详情已写入本地服务日志")
                    break
                raise WorkError("internal","工具内部异常，详情已写入本地服务日志") from exc
            tool_log.append({"tool":fn,"args":args,"output":output})
            messages.append({"role":"tool","tool_call_id":call.get("id"),"content":json.dumps(output,ensure_ascii=False)})
            if fn in READ_ONLY_TOOLS:
                reads.append((len(messages) - 1, fn, round_no, fingerprint, source_version))
            failed = output.get("ok") is False
            if failed and fn == "apply_operations": apply_failed = True
            try:
                detail = step_detail(fn,args,output)
            except Exception:
                detail = ""
            emit({"type":"step_error" if failed else "step_done","id":step_id,"label":label,"tool":fn,
                  "detail":detail,
                  **({"error":{"message":output.get('error') or '检查未通过',"detail":"；".join(output.get('issues',[]))}} if failed else {})})
            if failed:
                # 「同一个理由」按错误内容算：patch_target 是所有补丁失败共用的代码，按代码算会把三次不同的失败当成同一堵墙
                key = (fn, re.sub(r"[「“\"].*", "", str(output.get("error") or output.get("code") or ""))[:60])
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
        if plan and source_version != version_at_round:
            todo = [p for p in plan if p["status"] != "done"]
            if todo:
                todo[0]["status"] = "done"
                if len(todo) > 1: todo[1]["status"] = "active"
                emit({"type":"plan","steps":plan})
        if not read_only and changed and wrapup_round is None and round_no >= max_rounds - 3:
            wrapup_round = round_no + 1   # 已经改好了，最后两轮只许汇报，别让它读到轮次耗尽、给用户一句「已达到上限」
            messages.append({"role":"user","content":"轮次快用完了：现在用 report_result 汇报这次改了什么、还有什么没来得及做。"})
        if not read_only and round_no == max_rounds - 4:
            messages.append({"role":"user","content":
                "提醒：这次处理只剩 3 轮了。把还没写的部分合并成一次 apply_operations 写完，然后马上用 report_result 汇报；"
                "来不及做的写进汇报里，不要再读源码或规范。"})
        # 空转守卫：这一轮只读不改也不汇报，就累计一次。
        # 读来读去不下手是最常见的烧额度方式——它自己感觉不到已经转了几圈，
        # 到了阈值就明确要求它二选一：动手，或者说清没什么要改的。
        if changed:
            idle_rounds = 0
        elif any(c.get("function",{}).get("name") in READ_ONLY_TOOLS for c in calls):
            idle_rounds += 1
        if wrapup_edit and changed:
            # 「读太久」的收尾里它动手改成了：回到正常处理，让它接着改完、汇报
            wrapup_round, wrapup_edit, idle_rounds = None, False, 0
        if wrapup_round is not None and round_no >= wrapup_round:
            # 收尾轮也没给出提问或结论（参数不对之类）：这时才算真的卡住
            incomplete = (("iterations", "轮次快用完了，没来得及整理汇报") if changed else
                          ("stalled", f"连续 {idle_rounds} 轮都在读源码、没有做出任何改动，已经停下"))
            break
        if idle_rounds >= WRAPUP_AFTER and wrapup_round is None and not changed:
            # 催过还在读，说明它自己出不来了：不再让它读，逼它把线索交出来——问用户或者说明情况，
            # 用户看到的是「我查到了这些，你指的是哪个？」，而不是一张「已停下」的报错卡
            wrapup_round = round_no + 1
            wrapup_edit = not read_only
            emit({"type":"step_done","id":"wrapup-" + str(round_no),"label":"定位不太顺，先整理查到的线索","detail":"不再翻源码，把查到的位置交给你确认"})
            messages.append({"role":"user","content":WRAPUP_EDIT_PROMPT if not read_only else
                "别再读源码了。根据已经读到的内容直接用文字回答用户：说你看到了什么、结论是什么；"
                "拿不准对方指的是哪一处，就用 ask_user 列出 2–3 个可能的位置让他选。"})
        elif idle_rounds >= IDLE_LIMIT and not nudged and not changed:
            nudged = 1
            messages.append({"role":"user","content":
                f"提醒：已经连续 {IDLE_LIMIT} 轮只在读源码，一处都还没改。"
                "现在只能三选一——要么基于已经读到的内容立刻改一处；"
                "要么确认页面上本来就没有需要改的地方、用 report_result 把这个事实说清楚；"
                "要么定位不准时用 ask_user 列出你怀疑的 2–3 个位置让用户选。"
                "不要再读同一片代码。若这类改动要落在很多处，用一条 CSS 规则或一段脚本统一处理，"
                "不要一处一处改。"})
    else:
        incomplete = ("iterations","已达到本次处理轮次上限")
    if incomplete and not changed:
        raise WorkError(incomplete[0], incomplete[1] + "，当前文件未改动")
    if incomplete and not report:
        # 改动已经通过结构与脚本校验，丢掉等于白干一轮；交给两阶段提交继续把关，
        # 用户能在结果卡片里看到差异并一键撤销。
        emit({"type":"step_error","id":"incomplete","label":"已停止" if incomplete[0] == "stopped" else "没能整理完结果",
              "error":{"message":incomplete[1] + "；已经改好的部分保留下来，请检查"}})
        report = result_report({"summary":incomplete[1] + "，但已经做出的改动保留在这次修改里，请检查是否符合预期。"},
                               saved_annotations, changed)
    if discussion:
        discussion['selection'] = selection
        if remembered: discussion['remembered'] = remembered
        storage.append_chat(project_id,'assistant',discussion['answer'],{'page_id':page_id,'changed':False,'intent':'discuss','discussion':discussion,'usage':usage})
        return {'changed':False,'intent':'discuss','message':discussion['answer'],'discussion':discussion,'usage':usage,'tool_log':tool_log,'remembered':remembered}
    if question:
        if remembered: question['remembered'] = remembered
        storage.append_chat(project_id,"assistant",question['question'],{"page_id":page_id,"changed":False,"clarification":question,"usage":usage})
        return {"changed":False,"intent":intent,"message":question['question'],"clarification":question,"usage":usage,"tool_log":tool_log,"remembered":remembered}
    report = report or result_report({"summary":final_text},saved_annotations,changed)
    final_text = report['summary']
    if remembered: report['remembered'] = remembered   # 跟着这条回复存进对话：刷新后卡片上照样看得到、撤得掉
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
            "report":report,"usage":usage,"remembered":remembered,**candidate}
