"""AI 改到一半，自己把页面真跑一下：打开有没有报错、按钮点了有没有反应、元素对没对齐。

跑页面要浏览器，而浏览器只在界面里：AI 的循环在后台（一个线程里），所以走「后台托界面跑」——
后台发一个 page_check 事件（流式通道里本来就在推进度）→ 界面取这份还没保存的页面，
在看不见的副本 iframe 里跑 → 把结果 POST 回来 → 后台把结果交给 AI。
安装包里不用另带一个浏览器；界面没开、跑超时，就如实告诉 AI「这次没法验证」。
"""
from __future__ import annotations

import threading
import time
import uuid

PENDING: dict[str, dict] = {}
LOCK = threading.Lock()
TIMEOUT = {"load": 30, "click": 75, "measure": 30}   # 秒：点一遍要把每页按钮都点过，给得长些
KEEP = 300   # 没人来取的请求留这么久就清掉（界面关了、刷新了）


def _gc(now: float) -> None:
    for rid in [k for k, v in PENDING.items() if now - v["at"] > KEEP]:
        PENDING.pop(rid, None)


def request(emit, project_id: str, page_id: str, html: str, kind: str, args: dict,
            should_stop=None, timeout: float | None = None) -> dict | None:
    """发出请求、等界面回话。没回话（超时、停止）返回 None"""
    rid = uuid.uuid4().hex[:16]
    item = {"html": html, "project_id": project_id, "page_id": page_id, "event": threading.Event(),
            "result": None, "at": time.time()}
    with LOCK:
        _gc(item["at"])
        PENDING[rid] = item
    try:
        emit({"type": "page_check", "id": rid, "kind": kind, "args": args})
        end = time.time() + (timeout or TIMEOUT.get(kind, 30))
        while time.time() < end:
            if item["event"].wait(0.5):
                return item["result"]
            if should_stop and should_stop():
                return None
        return None
    finally:
        with LOCK:
            PENDING.pop(rid, None)


def get(rid: str) -> dict | None:
    with LOCK:
        return PENDING.get(rid)


def deliver(rid: str, result: dict) -> bool:
    with LOCK:
        item = PENDING.get(rid)
    if not item:
        return False
    item["result"] = result if isinstance(result, dict) else {}
    item["event"].set()
    return True


def _clip(text, n=240) -> str:
    return str(text or "").replace("\n", " ")[:n]


def summarize(kind: str, result: dict | None, baseline: list[str] | None = None) -> dict:
    """界面回来的原始结果 → 交给 AI 的短结论：只给结论和数字，一两千字以内，别把上下文撑大"""
    if result is None:
        return {"ok": False, "code": "unavailable",
                "error": "这次没法真跑页面（界面没连上或跑超时了）。按代码自己检查一遍就汇报，汇报里说一句没跑成。"}
    if result.get("error"):
        return {"ok": False, "code": "page_check_failed", "error": "跑页面没成功：" + _clip(result["error"], 200)}
    old = set(baseline or []) | set(result.get("baseline") or [])
    if kind == "measure":
        out = {"ok": True, "route": result.get("route", ""), "viewport": result.get("viewport"),
               "page_overflow_x": result.get("page_overflow_x"), "items": result.get("items") or []}
        text = str(out)
        while len(text) > 2600 and out["items"]:
            out["items"] = out["items"][:-1]
            out["truncated"] = True
            text = str(out)
        return out
    pages = result.get("pages") or []
    errors = []
    for p in pages:
        for e in p.get("errors") or []:
            if e not in old and len(errors) < 12:
                errors.append({"page": _clip(p.get("title") or p.get("route") or "首页", 30), "error": _clip(e)})
    out = {"ok": True, "pages_opened": len(pages) or int(result.get("routes") or 0), "new_errors": errors}
    blank = [_clip(p.get("title") or p.get("route"), 30) for p in pages if p.get("blank")]
    if blank:
        out["blank_pages"] = blank[:8]
    if kind == "click":
        issues = [i for i in (result.get("issues") or []) if not any(b and b in str(i.get("text")) for b in old)]
        out["clicked"] = result.get("clicked", 0)
        out["issues"] = [{"kind": _clip(i.get("kind"), 8), "text": _clip(i.get("text"), 160)} for i in issues[:14]]
        if len(issues) > 14:
            out["more"] = len(issues) - 14
        if result.get("skipped"):
            out["note"] = "点一遍没跑完：" + _clip(result["skipped"], 80)
    clean = not errors and not blank and not out.get("issues")
    out["summary"] = ("都正常：打开没有新报错" + ("，按钮点了都有反应" if kind == "click" else "")) if clean else \
        "有问题，见 new_errors / issues。修好再跑一次确认，或者在汇报里如实说明还剩哪些"
    return out
