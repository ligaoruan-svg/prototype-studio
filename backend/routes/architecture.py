"""架构模式：读、存、手动编大纲、粘贴功能清单、从展开图直接整理（不用 AI）、让 AI 起草 / 补全（边写边推进度、能停）"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import arch_draft, architecture, config, storage
from ..arch_text import from_outline, from_table, keep_ids, looks_like_table, merge_nodes, to_outline
from ..deepseek_client import DeepSeekError, chat
from ..errors import WorkError, error_payload

router = APIRouter()
DRAFT_DEADLINE = 300        # AI 起草最多等这么久（秒）：再长多半是模型在写一份超长的东西，不如停下来让人换个办法
DRAFT_MAX_TOKENS = 24_000   # 大纲写法一份几十页的架构也用不到这么多
DRAFTS: dict[str, threading.Event] = {}


class ArchIn(BaseModel):
    architecture: dict


class TextIn(BaseModel):
    text: str = Field(default="", max_length=200_000)
    mode: str = Field(default="append", pattern="^(append|replace)$")


class DraftIn(BaseModel):
    mode: str = Field(default="request", pattern="^(request|page|refine)$")
    text: str = Field(default="", max_length=4000)
    page_id: str = ""


class StopIn(BaseModel):
    id: str


def _project(project_id: str) -> dict:
    try:
        return storage.load_meta(project_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "项目不存在") from exc


def bundle(arch: dict | None) -> dict:
    out = architecture.bundle(arch)
    out["outline"] = to_outline(arch)
    return out


def _page_id(meta: dict, page_id: str) -> str:
    page_id = page_id or (meta.get("pages") or [{}])[0].get("id", "")
    storage.get_page(meta, page_id)
    return page_id


@router.get("/api/projects/{project_id}/architecture")
def get_architecture(project_id: str):
    _project(project_id)
    return bundle(architecture.load(project_id))


@router.put("/api/projects/{project_id}/architecture")
def put_architecture(project_id: str, body: ArchIn):
    _project(project_id)
    return bundle(architecture.save(project_id, body.architecture))


# 手动编：大纲改完整份读回来；路径没变的节点沿用原来的编号
@router.post("/api/projects/{project_id}/architecture/outline")
def put_outline(project_id: str, body: TextIn):
    _project(project_id)
    current = architecture.load(project_id)
    fresh = keep_ids(from_outline(body.text), current)
    if not fresh.get("lanes") and current:   # 大纲里没写流程：原来的流程留着
        fresh["lanes"], fresh["steps"] = current.get("lanes"), current.get("steps")
    return bundle(architecture.save(project_id, fresh))


# 粘贴：Excel 复制的功能清单（几列用 Tab 隔开）或一段大纲。追加时同名的并到一起
@router.post("/api/projects/{project_id}/architecture/import")
def import_text(project_id: str, body: TextIn):
    _project(project_id)
    incoming = from_table(body.text) if looks_like_table(body.text) else from_outline(body.text)
    if not incoming.get("nodes"):
        raise HTTPException(400, "没认出内容：从 Excel 复制几列（模块、菜单、功能、说明），或者按大纲写法一行一个")
    current = architecture.load(project_id)
    if body.mode == "replace" or not current:
        base = current or architecture.empty()
        base["nodes"] = incoming["nodes"]
        for key in ("entities", "relations"):
            if incoming.get(key):
                base[key] = incoming[key]
        return bundle(architecture.save(project_id, base))
    merge_nodes(current["nodes"], incoming["nodes"])
    names = {e["name"] for e in current["entities"]}
    current["entities"] += [e for e in incoming.get("entities") or [] if e["name"] not in names]
    current["relations"] += incoming.get("relations") or []
    return bundle(architecture.save(project_id, current))


# 不用 AI：照展开图里的业务页面、弹窗、子页面直接搭出页面树，几秒就好；之后可以手动改，或者让 AI 补全
@router.post("/api/projects/{project_id}/architecture/from-expand")
def from_expand(project_id: str, body: DraftIn):
    meta = _project(project_id)
    nodes = arch_draft.expand_tree(project_id, _page_id(meta, body.page_id))
    if not nodes:
        raise HTTPException(400, "这个原型还没展开过：先点顶上的「展开」→「一键展开」，或者用 AI 整理")
    arch = architecture.load(project_id) or architecture.empty()
    arch["nodes"] = nodes
    arch["name"] = arch.get("name") or meta.get("name", "")
    arch["status"] = "draft"
    return bundle(architecture.save(project_id, arch))


# AI 起草：流式，边写边告诉界面写了多少字；能停；超过 5 分钟自己停
@router.post("/api/projects/{project_id}/architecture/draft")
def draft_architecture(project_id: str, body: DraftIn):
    meta = _project(project_id)
    settings = config.load()
    key = settings.get("api_key")
    if not key:
        raise HTTPException(400, error_payload(WorkError("model_account", "请先在设置中保存 API 密钥")))
    page_id = _page_id(meta, body.page_id) if body.mode == "page" else ""
    current = architecture.load(project_id)
    events: queue.Queue = queue.Queue()
    run_id = uuid.uuid4().hex[:12]
    stop = DRAFTS[run_id] = threading.Event()
    started = time.time()
    too_long = lambda: time.time() - started > DRAFT_DEADLINE   # noqa: E731

    def work():
        try:
            msgs = arch_draft.messages(body.mode, body.text.strip(), current, project_id, page_id)
            events.put({"type": "progress", "label": "已整理好原型结构，交给 AI" if body.mode == "page" else "交给 AI", "chars": 0})
            written = [0]

            def on_delta(text, kind="note"):
                written[0] += len(text)
                events.put({"type": "progress", "label": "AI 正在写", "chars": written[0]})
            resp = chat(key, settings["model"], msgs, None, base_url=settings["base_url"],
                        max_tokens=min(DRAFT_MAX_TOKENS, max(8000, int(settings.get("max_tokens") or 16000))),
                        on_delta=on_delta if settings.get("stream", True) else None,
                        should_stop=lambda: stop.is_set() or too_long())
            choice = (resp.get("choices") or [{}])[0]
            reply = (choice.get("message") or {}).get("content") or ""
            try:
                fresh = arch_draft.finish(reply, body.mode, current)
            except ValueError:
                cut = "（输出被截断了）" if choice.get("finish_reason") in ("length", "max_tokens") else ""
                raise WorkError("draft_unreadable", "AI 给的架构读不出来" + cut + "，再试一次")
            if current:   # 起草前的那一份留个底
                storage.project_dir(project_id).joinpath("architecture.prev.json").write_text(json.dumps(current, ensure_ascii=False), "utf-8")
            events.put({"type": "complete", "result": bundle(architecture.save(project_id, fresh))})
        except Exception as exc:
            if isinstance(exc, DeepSeekError) and exc.code == "stopped":
                exc = WorkError("draft_timeout" if too_long() else "stopped",
                                "AI 写了 5 分钟还没写完，先停下了：可以换「不用 AI 整理」，或者把需求说小一点" if too_long() else "已停止")
            elif not isinstance(exc, WorkError):
                logging.getLogger(__name__).exception("architecture draft failed")
                exc = WorkError("internal", "本地服务内部错误")
            payload = error_payload(exc)
            payload["detail"] = payload["detail"].replace(key, "[密钥]")
            events.put({"type": "error", "error": payload})
        finally:
            events.put(None)
            DRAFTS.pop(run_id, None)

    def generate():
        finished = False
        try:
            yield "data: " + json.dumps({"type": "started", "id": run_id}, ensure_ascii=False) + "\n\n"
            threading.Thread(target=work, daemon=True).start()
            last = None
            while True:
                try:
                    event = events.get(timeout=2)
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    continue
                if event is None:
                    finished = True
                    break
                # 进度一个字一个字地来：合并一下，别把界面刷爆
                if event["type"] == "progress" and last and event["chars"] - last < 200 and event["chars"]:
                    continue
                if event["type"] == "progress":
                    last = event["chars"]
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        finally:
            if not finished:
                stop.set()
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/projects/{project_id}/architecture/draft/stop")
def stop_draft(project_id: str, body: StopIn):
    flag = DRAFTS.get(body.id)
    if flag:
        flag.set()
    return {"ok": bool(flag)}
