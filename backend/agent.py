from __future__ import annotations

import copy
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
from .experience import element_name, tool_label, compact_once, changed_targets, result_report, scope_report, step_detail
from .conversation import resolve_intent, is_continue, discussion_result, history_context
from . import components, memory, page_check, skills, skill_digest
from . import architecture as arch_mod
# 工具清单、读源码、拼背景拆在旁边三个文件里；下面这些名字在这里也能用（测试和别的模块按 agent.xxx 取）
from .agent_tools import TOOL_SPECS, OPERATION_ACTIONS
from .agent_source import READ_CAP, read_budget, inspect_output, expand_components, locate_lines, lines_text, _num, _slice_lines, _search_source  # noqa: F401
from .agent_lookup import LOOKUP_TOOLS, SKILL_READ_LIMIT, run_lookup  # noqa: F401
from .agent_context import CONTEXT_KEYS, context_text, scene_text, language_note, SHELL_NOTE, is_fresh_shell, shell_api
from .source_map import code_map, prefetch, changes_view

logger = logging.getLogger(__name__)

from .paths import PROMPTS, SPEC_FILE
SYSTEM_PROMPT_PATH = PROMPTS / "agent-system.md"

SHELL_MAX_EXISTING = 8000   # 页面比这还大就算「已有内容」，不许整页换成外壳
IDLE_LIMIT = 4       # 连续这么多轮只读不改，就催它下手或收工
WRAPUP_AFTER = 6     # 催过还在读：只留「提问 / 汇报」两个工具，让它把找到的线索交出来，而不是报错收场
# 「轮次上限」是兜底，不是硬杠：快到上限时最近几轮还在推进（改了页面、做完一步、检查的问题变少），就再多给几轮
EXTEND_ROUNDS = 6
MAX_EXTENSIONS = 2
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
SOURCE_READS = {"inspect_page", "search_source", "read_source_slice", "read_region"}
# 页面不超过这么多字，就把整份源码放进第一条消息：之后每轮都命中缓存（约一折），省掉一轮轮读源码。
# 实测：一页 23 轮里 16–18 轮在读，一轮只搜一个名字
FULL_SOURCE_MAX = 60_000
FULL_SOURCE_SHARE = 0.5   # 上下文预算的一半以内都整份给：预算按模型能力填，模型装得下多少就给多少（默认 20 万字 → 10 万字）
# 语法错误被退回时，这次的改动先暂存：下一次只改出错的那一小段，不用把几千字重写一遍（实测一次退回后又读了九轮源码）
DRAFT_NOTE = ("\n这次的改动整体已经暂存（还没写进页面），只差上面这一处语法错误。不用整段重写，也不用再读源码："
              "下一次 apply_operations 只放一条 replace_source_text，把出错处前后的一小段改对"
              "（old 照抄上面「出错处前后的原文」里的一段，去掉 ⟪这里⟫ 标记），程序会在暂存版上改，改对了整体一起写进页面。")
READ_ONLY_TOOLS = {"inspect_page", "search_source", "read_source_slice", "read_region", "search_chats",
                   "read_component", "read_skill", "read_skill_file", "search_skill_file", "check_page", "measure_page"}
# 在循环里真跑页面（check_page / measure_page）：模型自己最多跑这么多次；改过页面却没验证就汇报时，程序替它跑，最多这么多次
PAGE_CHECK_LIMIT = 4
# 输出被截断：先自动放宽「单次输出」再试（最多翻两倍两次、不超过这个数），不行再让它拆小
OUTPUT_RAISE_CAP = 65_536
# 计划里做完一步（finish_step）：对话已经超过上下文预算的这么多，就把过程收拾掉、带着现在的页面重开下一步
STEP_RESET_SHARE = 0.4
AUTO_CHECK_LIMIT = 2
ARCH_ROUNDS_CAP = 120   # 按架构整套生成时轮次上限最多放到这么多


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
              start_source: str | None = None, lang: str = 'zh', live_checks: bool = False,
              architecture: bool = False, display: dict | None = None) -> dict[str, Any]:
    emit = on_event or (lambda event: None)
    trace = [] if trace is None else trace
    plan: list[dict] = []   # 当前计划：程序按每轮的修改自动往前推，不用模型一轮轮调 update_plan
    shell_fresh = None   # 刚放进来、还没写内容的外壳：这时候不让翻源码
    # 上一句是在改还是在聊：用户只说「继续」时照着上一句来（改到一半被停了，说「继续」就接着改）
    previous_intent = next((c.get('intent') for c in reversed(storage.load_meta(project_id).get('chat', []))
                            if c.get('role') == 'user' and c.get('page_id') == page_id and c.get('intent')), None)
    intent = resolve_intent(user_message, intent, previous_intent)
    read_only = intent == 'discuss'
    tools = [spec for spec in TOOL_SPECS if not (read_only and spec['function']['name'] in {'apply_operations', 'report_result', 'update_plan', 'start_from_shell', 'finish_step'})]
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
        # 界面上拼出来的长话（「同步到原型」那一大段）：对话里只显示成一张小卡片，点开才看清单
        if isinstance(display, dict) and display.get("title"):
            extra["display"] = {"kind": str(display.get("kind") or "")[:12], "title": str(display["title"])[:60], "items": [str(x)[:80] for x in (display.get("items") or [])[:30]],
                                "note": str(display.get("note") or "")[:500]}
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
    # 代码地图和预取片段：实测一页 23 轮里 16 轮只在读——搜一个名字、看到行号、再搜下一个，每轮重发全部上下文。
    # 程序先把「什么在第几行」和用户点名的那几处原文给它，第一轮就能直接读那一小段或者动手
    fresh_shell = is_fresh_shell(working_source)
    def source_block(src: str, prefetch_ok: bool = True) -> str:
        out = ""
        source_map = code_map(src)
        if source_map:
            out += "\n代码地图（行号: 定义，只有名字没有正文；括号里的字数说明这一行很长，多半一整行就是一个函数）：\n" + source_map
        if len(src) <= max(FULL_SOURCE_MAX, int(context_budget * FULL_SOURCE_SHARE)):
            out += ("\n当前页面的完整源码（这是此刻的样子；之后你改过的地方以你写的为准，改完返回的 where 会告诉你落在哪几行）。"
                    "已经在这里了，不用再 search_source / read_source_slice 去读：\n<<<页面源码\n" + src + "\n页面源码>>>")
        elif prefetch_ok:
            found = prefetch(src, [user_message, runtime_feedback, scene_text(scene)],
                             [h["line"] for a in anns for h in (a.get("source_lines") or [])])
            if found:
                out += "\n" + found
        return out
    background += source_block(working_source, prefetch_ok=not fresh_shell)
    if not read_only and fresh_shell:
        # 按风格新建的项目，第一页就是这套风格的空外壳：不用再 start_from_shell，也不用翻源码找位置
        shell_fresh = working_source
        background += ("\n这一页是按项目风格刚建好的空外壳，还没写内容。" + SHELL_NOTE
                       + "\n外壳现成的组件和样式类：" + json.dumps(shell_api(working_source), ensure_ascii=False))
    # 按架构做：页面树、共用数据、流程和统一规则都放进背景。放在第一条消息里，做完一步重开时也还在
    arch = arch_mod.load(project_id) if architecture and not read_only else None
    if arch:
        background += "\n\n" + arch_mod.brief(arch)
        # 一页一步做完整个架构要的轮次比改一处多得多：每页按 4 轮算，进度照常按「有没有推进」放宽
        max_rounds = min(ARCH_ROUNDS_CAP, max(max_rounds, 8 + 4 * len(arch_mod.order(arch))))
    if repairing:
        background += ("\n现在的页面是你上一次改好、但运行检查报错、还没保存的那一版（已经包含你上次写的全部内容）。"
                       "只修上面的报错，不要从头再做，也不要重新调 start_from_shell。")
    kickoff = ("以下是背景资料，只在和用户这轮问的事情相关时才用：\n" + background
               + "\n\n———\n用户这轮说的是：\n" + user_message)
    if not lang.startswith('zh'):
        kickoff += language_note(lang)
    if is_continue(user_message):
        kickoff += ("\n\n（用户说的是「继续」：接着把上一次没做完的做完。上一条需求、当时的计划和汇报在前面的对话里，"
                    "已经改好的部分都在当前页面里——别重做，从没做完的地方接着做。）")
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
    usage = {"prompt_tokens":0,"completion_tokens":0,"total_tokens":0,"cached_tokens":0}
    failures = argument_failures = truncations = 0
    round_max, raises = max_tokens, 0   # 这一轮的单次输出上限：截断时自动放宽
    step_notes: list[tuple[str, str]] = []   # finish_step 记下的「这一步做了什么」，重开下一步时带上
    stepped = reset_pending = False   # 模型用 finish_step 自己报进度后，就不再按「改了一次」自动推计划
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
    source_version = 0    # 页面源码改过几次：读到的源码是不是已经过时，看它
    remembered = []       # 这一轮新记住的约定：结果卡片上要让用户看见，记错了能当场撤销
    budget = read_budget(context_budget)
    # 真跑页面：后台托界面在看不见的副本里跑（page_check.py）。没有界面（一次性接口、测试）就如实说没法跑
    page_checks = auto_checks = 0
    verified_version = None   # 哪个版本的页面已经真跑过：改过以后要再跑
    # live_checks：只有流式接口（界面开着、会来取页面跑）才打开；一次性接口和测试里没人回话，别干等
    def live(kind: str, check_args: dict) -> dict:
        if not (live_checks and on_event):
            return page_check.summarize(kind, None)
        return page_check.summarize(kind, page_check.request(on_event, project_id, page_id, working_source, kind, check_args, should_stop=stopped))
    draft = None          # (暂存的页面, 那次的操作)：改动只因语法错误被退回时先存着，下一次只修出错处
    # 同一个工具被同一个理由连续拒绝多少次。failures 只管补丁失败，
    # 别的拒绝（只讨论模式下调修改工具、区域太大、参数越界）原来一次都不计，
    # 模型可以一直撞同一堵墙直到轮次烧光。
    rejects: dict[tuple[str, str], int] = {}
    stopped = should_stop or (lambda: False)
    limit, extensions = max_rounds, 0
    recent: list[bool] = []          # 每一轮有没有推进
    last_problems = None             # 上一次真跑页面发现了几个问题：变少了也算推进
    round_no = -1
    while True:
        round_no += 1
        if round_no >= limit:
            incomplete = ("iterations", "已达到本次处理轮次上限")
            break
        step_done_now = check_better_now = False
        # 用户点了停止：在两轮之间停下。已经改好的部分照常走检查和保存，可以一键撤销
        if stopped():
            incomplete = ("stopped", "你停止了这次处理")
            break
        # 对话只往后加，不每轮收：读过的、自己写过的一直留着（以前两轮就收，写完前一半要读回十几轮，还每轮打断缓存）。
        # 快到「上下文预算」时才一次性收掉较早的读取结果，收到六成，之后又能连着好几轮只往后加
        if compact_once(messages, context_budget):
            read_seen.clear()   # 旧的读取结果收起了，它可能要重读，不能再拦
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
            resp = chat(api_key, model, messages, round_tools, base_url=base_url, max_tokens=round_max, on_delta=on_delta,
                        on_retry=lambda n, wait, exc: emit({"type":"model_retry","round":round_no+1,"attempt":n,
                                                            "label":f"模型服务忙，{wait} 秒后自动重试（第 {n} 次）"}),
                        should_stop=stopped)
        except DeepSeekError as exc:
            if exc.code == 'stopped':
                incomplete = ("stopped", "你停止了这次处理")
                break
            if round_max > max_tokens and ("HTTP 400" in str(exc) or "max_tokens" in str(exc).lower()):
                # 放宽的上限这个模型服务不认：退回原来的上限，改成让它拆小（下一次截断走拆小）
                round_max, raises = max_tokens, 99
                messages.append({"role": "user", "content": "上一次输出太长被截断了。请把改动拆小：这一轮只写计划里的下一步，或者一次 apply_operations 只改一个位置。"})
                continue
            # 模型中途出错（重试也没救回来）：前面已经改好、通过校验的部分不能白丢，照常交给检查和保存
            if changed:
                incomplete = (exc.code or 'network', f"模型服务中途出错（{str(exc)[:120]}）")
                break
            raise
        used = resp.get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            usage[key] += used.get(key, 0) or 0
        # 命中模型服务前缀缓存的那部分输入（DeepSeek 叫 prompt_cache_hit_tokens，OpenAI 系放在 prompt_tokens_details 里）：
        # 价格通常只有十分之一，记下来才知道这 50 万里真正按原价算的是多少
        cached = used.get("prompt_cache_hit_tokens") or (used.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        usage["cached_tokens"] += cached
        choices = resp.get("choices") or []
        trace.append({"round": round_no + 1, "finish": (choices[0].get("finish_reason") if choices else None),
                      "prompt": used.get("prompt_tokens"), "completion": used.get("completion_tokens"), "cached": cached,
                      "start": len(tool_log), "_log": tool_log})
        version_at_round = source_version
        if not choices:
            raise WorkError("invalid_arguments","模型没有返回有效回复")
        if choices[0].get("finish_reason") in {"length","max_tokens"}:
            # 截断的内容一律丢弃（绝不应用半截修改），但可以指导模型拆小后继续，
            # 而不是让一次超长直接毁掉整轮工作。
            if raises < 2 and round_max < OUTPUT_RAISE_CAP:
                # 截断多半是一次要写的太多（加上思考也算在输出里）：先自动放宽上限，同样的对话再来一次，不打扰它的思路
                raises += 1
                round_max = min(OUTPUT_RAISE_CAP, round_max * 2)
                emit({"type": "step_done", "detail": "", "id": f"raise{raises}", "label": f"这一步写得长，单次输出自动放宽到 {round_max} 再来一次"})
                continue
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
                "有计划就这一轮只写计划里的下一步、做完调 finish_step；没有计划就一次 apply_operations 只改一个位置；"
                "插入现成组件用 insert_component 只写组件名，不要抄写原文。"})
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
                if read_only and fn in {'apply_operations', 'report_result', 'update_plan', 'start_from_shell', 'finish_step'}:
                    output = {'ok':False,'code':'read_only','error':'当前只讨论设计，不允许修改或汇报已修改。请用 answer_user 回答并给出待确认建议。'}
                elif fn in SOURCE_READS and fn != "search_source" and shell_fresh is not None and working_source == shell_fresh:
                    # 实测：外壳放好后模型要翻十来轮源码找位置、看函数怎么写，轮次就这么烧光了。整份读外壳不给，
                    # 直接把它要找的（组件、样式类、三处位置）给它。不当成「拒绝」：以前回 ok:false，
                    # 模型一次并发三个查询就凑满三次拒绝，整次修改直接失败。搜关键词照常给（只回命中处，很便宜）
                    output = {'ok':True,'code':'shell_fresh',
                              'note':("这页还是空外壳，不用整份读。外壳里现成的东西都在下面；要确认某个名字就用 search_source 搜。"
                                      "下一步直接一次 apply_operations，用 {action:'shell_add', nav, pages, bind, script} 把这页写完。"),
                              'api': shell_api(working_source)}
                elif fn in ("check_page", "measure_page"):
                    if page_checks >= PAGE_CHECK_LIMIT:
                        raise PatchError(f"这次已经真跑过 {PAGE_CHECK_LIMIT} 次页面了：按已有结果修完就汇报，还剩的问题在汇报里说清")
                    page_checks += 1
                    if fn == "check_page":
                        routes = [r.strip()[:60] for r in (args.get("routes") or []) if isinstance(r, str) and r.strip()][:4]
                        output = live("click" if args.get("click") else "load", {"routes": routes})
                        if output.get("ok"):
                            verified_version = source_version
                            problems = len(output.get("new_errors") or []) + len(output.get("issues") or []) + len(output.get("blank_pages") or [])
                            check_better_now = last_problems is None or problems < last_problems
                            last_problems = problems
                    else:
                        selectors = [x.strip()[:200] for x in (args.get("selectors") or []) if isinstance(x, str) and x.strip()][:8]
                        if not selectors:
                            raise PatchError("selectors 至少给一个 CSS 选择器")
                        output = live("measure", {"route": str(args.get("route") or "")[:60], "selectors": selectors})
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
                    # 先在页面上试；上次因语法错误暂存了一版，就再在暂存版上试（它多半只发来出错那一小段的修正）
                    attempts, new_source, logs, via_draft = [], None, [], False
                    for on_draft, base in [(False, working_source)] + ([(True, draft[0])] if draft else []):
                        try:
                            candidate_source, candidate_logs = apply_operations(base, copy.deepcopy(ops))
                        except PatchError as exc:
                            attempts.append((exc, None, on_draft)); continue
                        check = verify_source(candidate_source)
                        fresh = new_issues(baseline, check) if not check['ok'] else []
                        if fresh:
                            attempts.append((PatchError('修改检查失败：'+'；'.join(fresh)), (candidate_source, fresh), on_draft)); continue
                        if candidate_source == working_source:
                            attempts.append((PatchError("这次操作没有产生实际改动"), None, on_draft)); continue
                        new_source, logs, via_draft = candidate_source, candidate_logs, on_draft
                        break
                    if new_source is None:
                        applied = [a for a in attempts if a[1]]
                        exc, built, from_draft = applied[-1] if applied else attempts[0]
                        if built and all(re.match(r"脚本 \d+ 语法错误", i) for i in built[1]):
                            draft = (built[0], (draft[1] if from_draft else []) + ops)
                            raise PatchError(str(exc) + DRAFT_NOTE)
                        raise exc
                    if via_draft:
                        ops = draft[1] + ops   # 暂存那次的操作也算这次改的（改动落点、结果卡片要用）
                    draft = None
                    before_edit = working_source
                    working_source = new_source; changed = working_source != source; source_version += 1
                    # 源码变了，之前读过的段落、读过的区域都不是现在的样子：允许重读，
                    # 也不能再拿改动前读到的区域原文去整块替换（会把刚才的修改冲掉）
                    read_seen.clear(); read_regions.clear()
                    all_operations.extend(ops); failures = 0
                    view = changes_view(before_edit, working_source)
                    todo = [p for p in plan if p["status"] != "done"]
                    output = {"ok":True,"logs":logs,"verified":True,
                              "note":("已通过结构和脚本检查，不用再调 verify_page，也不用再搜一遍核对——改到哪几行见 where。"
                                      + ("这一步做完了就调 finish_step（写清做了什么、定义了哪些名字），再做下一步；下次可以把 finish_step 和修改放在同一次回复里。" if todo
                                         else "全部改完就直接 report_result。")),
                              "where": view}
                    if abs(view["shift"]) >= 20:
                        # 加了一大段（新页面、新函数），后面的行号全变了：给一份新的代码地图，接着改不用先搜位置
                        output["map"] = code_map(working_source)
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
                    if changed and live_checks and on_event and not read_only and verified_version != source_version and auto_checks < AUTO_CHECK_LIMIT:
                        # 改过页面、还没真跑过就汇报：程序先替它跑一遍（打开首页和每个菜单页），有新报错就退回去修，不交半成品
                        auto_checks += 1
                        emit({"type": "step_start", "id": f"autocheck{auto_checks}", "label": "汇报前先把页面真跑一遍", "tool": "check_page"})
                        checked = live("load", {"routes": []})
                        verified_version = source_version
                        problems = {k: checked[k] for k in ("new_errors", "blank_pages") if checked.get(k)}
                        detail = step_detail("check_page", {}, checked)
                        emit({"type": "step_done", "detail": detail, "id": f"autocheck{auto_checks}", "label": "汇报前先把页面真跑一遍", "tool": "check_page"})
                        if problems:
                            raise PatchError("汇报前程序替你把页面真跑了一遍，发现下面的问题，先修好再汇报（修完可以用 check_page 确认）："
                                             + json.dumps(problems, ensure_ascii=False)[:1500])
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
                    output = {"ok":True,"steps":plan,"note":("计划记下了，不用再调 update_plan。一步一步做：每做完一步就调 finish_step 说清这一步做了什么、定义了哪些名字；"
                                                            "可以和这一步的 apply_operations 放在同一次回复里（先改、后报），省一轮。程序会帮你把对话收拾干净再做下一步。全部做完 report_result。")}
                elif fn=="finish_step":
                    if not plan:
                        raise PatchError("还没有列计划：一两处的改动不用 finish_step，改完直接 report_result")
                    if apply_failed:
                        # 和 report_result 一样：同一条消息里前面的修改没成功，这一步不算做完
                        raise PatchError("这条消息里前面的修改没有成功，这一步还不算做完。先把那处改成，再调 finish_step")
                    n = _num(args.get("step"), 0)
                    if not 1 <= n <= len(plan):
                        raise PatchError(f"step 要写计划里的第几步（1 到 {len(plan)}）")
                    for p in plan[:n]:
                        p["status"] = "done"
                    rest = [p for p in plan if p["status"] != "done"]
                    if rest:
                        rest[0]["status"] = "active"
                    summary = str(args.get("summary") or "").strip()[:500]
                    step_notes.append((plan[n - 1]["title"], summary))
                    stepped = step_done_now = True
                    emit({"type": "plan", "steps": plan})
                    size = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
                    reset_pending = bool(rest) and draft is None and size > context_budget * STEP_RESET_SHARE
                    output = {"ok": True, "next": rest[0]["title"] if rest else None,
                              "note": (f"接着做「{rest[0]['title']}」" + ("（程序会先把前面的过程收起来，带着现在的页面重开）" if reset_pending else ""))
                                      if rest else "计划都做完了：真跑过就 report_result"}
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
        if plan and not stepped and source_version != version_at_round:
            todo = [p for p in plan if p["status"] != "done"]
            if todo:
                todo[0]["status"] = "done"
                if len(todo) > 1: todo[1]["status"] = "active"
                emit({"type":"plan","steps":plan})
        if reset_pending and draft is None:
            # 计划里的一步做完了，对话也长了：把读过的、试过的过程收掉，带着「现在的页面 + 计划 + 每一步做了什么」重开下一步。
            # 像人干活一样：做完一块，桌面收拾干净再做下一块。页面就是事实，前面写的都已经在里面了
            reset_pending = False
            nxt = next((p for p in plan if p["status"] != "done"), None)
            plan_text = "\n".join(f"{i + 1}. {'✓ ' if p['status'] == 'done' else '→ ' if p is nxt else ''}{p['title']}" for i, p in enumerate(plan))
            done_text = "\n".join(f"- 「{t}」：{s or '（没写说明）'}" for t, s in step_notes)
            resume = ("（接着做同一个任务。为了让对话干净，前面读源码、试错的过程已经收起；页面里已经包含你前面写的全部内容。）\n"
                      f"计划：\n{plan_text}\n\n已经做完的步骤：\n{done_text}\n"
                      f"保存的修改意见：\n{annotation_text}\n" + source_block(working_source, prefetch_ok=False)
                      + (("\n\n" + arch_mod.brief(arch)) if arch else "")
                      + f"\n\n———\n用户这轮说的是：\n{user_message}\n\n"
                      + f"现在做「{nxt['title'] if nxt else '收尾'}」。做完调 finish_step；全部做完、真跑过就 report_result。")
            messages[:] = [messages[0], {"role": "user", "content": resume}]
            read_seen.clear()
            emit({"type": "step_done", "detail": nxt["title"] if nxt else "", "id": f"reset{round_no}", "label": "这一步做完了，收拾一下对话再做下一步"})
        # 这一轮有没有推进：改了页面、做完计划里的一步、真跑页面发现的问题变少了
        progress = source_version != version_at_round or step_done_now or check_better_now
        recent.append(progress)
        if not read_only and round_no == limit - 4 and extensions < MAX_EXTENSIONS and any(recent[-3:]):
            # 快到上限了，可最近几轮一直在推进：不打断它，再多给几轮（兜底总共多 12 轮）
            extensions += 1
            limit += EXTEND_ROUNDS
            emit({"type": "step_done", "detail": f"轮次上限放宽到 {limit} 轮", "id": f"extend{extensions}", "label": "还在推进，多给几轮"})
        if not read_only and changed and wrapup_round is None and round_no >= limit - 3:
            wrapup_round = round_no + 1   # 已经改好了，最后两轮只许汇报，别让它读到轮次耗尽、给用户一句「已达到上限」
            messages.append({"role":"user","content":"轮次快用完了：现在用 report_result 汇报这次改了什么、还有什么没来得及做。"})
        if not read_only and round_no == limit - 4:
            messages.append({"role":"user","content":
                "提醒：这次处理只剩 3 轮了。把还没写的部分合并成一次 apply_operations 写完，然后马上用 report_result 汇报；"
                "来不及做的写进汇报里，不要再读源码或规范。"})
        # 空转守卫：看这一轮有没有推进，不看「以前改没改过」——以前改过一处以后，读多少轮都不算空转，
        # 改不动的补丁反复失败也不算。现在：只读、失败、原地打转都算一轮没推进
        if progress:
            idle_rounds, nudged = 0, 0
        else:
            idle_rounds += 1
        if wrapup_edit and progress:
            # 「读太久」的收尾里它动手改成了：回到正常处理，让它接着改完、汇报
            wrapup_round, wrapup_edit, idle_rounds = None, False, 0
        if wrapup_round is not None and round_no >= wrapup_round:
            # 收尾轮也没给出提问或结论（参数不对之类）：这时才算真的卡住
            incomplete = (("iterations", "轮次快用完了，没来得及整理汇报") if changed else
                          ("stalled", f"连续 {idle_rounds} 轮没有进展、没有做出任何改动，已经停下"))
            break
        if idle_rounds >= WRAPUP_AFTER and wrapup_round is None:
            # 催过还在原地打转，说明它自己出不来了：不再让它读，逼它收尾——改完能改的、问用户、或者说明情况。
            # 用户看到的是「我查到了这些，你指的是哪个？」，而不是一张「已停下」的报错卡
            wrapup_round = round_no + 1
            wrapup_edit = not read_only
            emit({"type":"step_done","id":"wrapup-" + str(round_no),"label":"好几轮没有进展，先收个尾","detail":"不再翻源码，把能改的改完、查到的交给你确认"})
            messages.append({"role":"user","content":(("你已经改好的部分会保留。" if changed else "") + WRAPUP_EDIT_PROMPT) if not read_only else
                "别再读源码了。根据已经读到的内容直接用文字回答用户：说你看到了什么、结论是什么；"
                "拿不准对方指的是哪一处，就用 ask_user 列出 2–3 个可能的位置让他选。"})
        elif idle_rounds >= IDLE_LIMIT and not nudged:
            nudged = 1
            messages.append({"role":"user","content":
                f"提醒：已经连续 {IDLE_LIMIT} 轮没有进展（只在读、或者修改一直没成功）。"
                "现在只能三选一——要么基于已经读到的内容立刻改一处（改不上就换个更短、更准的原文片段）；"
                "要么确认已经没有需要改的地方、用 report_result 把这个事实说清楚；"
                "要么定位不准时用 ask_user 列出你怀疑的 2–3 个位置让用户选。"
                "不要再读同一片代码。若这类改动要落在很多处，用一条 CSS 规则或一段脚本统一处理，"
                "不要一处一处改。"})
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
