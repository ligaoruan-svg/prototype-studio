"""AI 查资料用的工具：skill 正文和附带文件、组件、以前的对话、长期记忆。

它们只读写各自的那份资料，不碰正在改的页面，所以从主循环里拿出来单独放；主循环遇到这几个工具就交给 run_lookup。
"""
from __future__ import annotations

from . import components, memory, skill_digest, skills, storage
from .agent_source import _num, _search_source, _slice_lines
from .patcher import PatchError

SKILL_READ_LIMIT = 8000     # skill 附带文件一次最多给这么多字；整份读大文件只给目录
LOOKUP_TOOLS = {"read_skill", "read_skill_file", "search_skill_file", "remember", "search_chats", "forget", "read_component"}


def run_lookup(fn: str, args: dict, project_id: str, budget: int, remembered: list) -> dict:
    """执行一个查资料工具，返回给模型的结果。remember 记下的新约定追加到 remembered（结果卡片上要给用户看）"""
    if fn == "read_skill":
        try:
            output = {"name": args.get("name"), "content": skills.read(str(args.get("name","")))}
        except (ValueError, FileNotFoundError) as exc:
            raise PatchError(f"没有这个 skill：{args.get('name')}。可用的见系统提示里的清单") from exc
    elif fn == "read_skill_file":
        try:
            whole = skills.read_file(str(args.get("name","")), str(args.get("path","")))
            lines = whole.splitlines()
            if "start" not in args and len(whole) > SKILL_READ_LIMIT:
                # 想整份读一个大文件：要点已经在系统提示里了，这里只给目录，让它按行号读需要的那一节
                output = {"name": args.get("name"), "path": args.get("path"), "whole_file_refused": True,
                          "note": (f"这个文件有 {len(whole)} 字，整份读进来以后每一步都要重发，不给整份。"
                                   "它的要点（目录、硬约束、组件签名）已经在系统提示里。确实要看原文，"
                                   "按下面的行号带上 start / end 只读那一节，或用 search_skill_file 搜组件名。"),
                          "outline": skill_digest.outline(whole)}
            else:
                a = max(1, _num(args.get("start"), 1))
                b = min(len(lines), _num(args.get("end"), a + 200))
                output = {"name": args.get("name"), "path": args.get("path"),
                          **_slice_lines(lines, a, b, min(budget, SKILL_READ_LIMIT))}
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
            if memory.paused(project_id):
                raise PatchError("用户暂停了记忆，这次不记；照常把事情做完")
            saved = memory.add(project_id, str(args.get("note", "")), str(args.get("category", "")),
                               str(args.get("scope", "project")), "said")
        except ValueError as exc:
            raise PatchError(str(exc)) from exc
        output = {"ok": True, **saved}
        if not saved.get("duplicate"):
            remembered.append({"id": saved["id"], "text": saved["text"], "scope": saved.get("scope", "project")})
    elif fn == "search_chats":
        found = storage.search_chat_log(project_id, str(args.get("query", "")))
        output = {"hits": len(found), "results": [{"who": "用户" if r.get("role") == "user" else "设计助手",
                  "when": str(r.get("created_at", ""))[:16], "page": r.get("page", ""), "text": r.get("content", "")} for r in found]}
        if not found:
            output["note"] = "以前的对话里没有这些词。别再换词反复查，直接问用户或按现有信息处理。"
    elif fn == "forget":
        output = {"ok": memory.remove(project_id, str(args.get("id", ""))),
                  "id": args.get("id")}
    elif fn == "read_component":
        try:
            output = components.preview(str(args.get("name", "")))
        except (ValueError, FileNotFoundError) as exc:
            raise PatchError(f"没有这个组件：{args.get('name')}。可用的见系统提示里的组件清单") from exc
    else:
        raise PatchError(f"不认识的工具：{fn}")
    return output
