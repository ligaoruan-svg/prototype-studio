"""项目记忆：参照 Claude 的做法，两层（这个项目 / 所有项目）、按类别、能暂停能清空、能一句话改、会自己整理"""
from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config, memory, storage
from ..deepseek_client import chat

router = APIRouter()


def _memory_llm():
    """记忆整理和「一句话改记忆」用的模型调用：不带工具，只要一段 JSON。"""
    settings = config.load()
    key = settings.get("api_key")
    if not key:
        raise HTTPException(400, "请先在设置中保存 API 密钥")
    def ask(prompt: str) -> str:
        resp = chat(key, settings["model"], [{"role": "user", "content": prompt}], None,
                    base_url=settings["base_url"], max_tokens=1500)
        return ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return ask


SYNTHESIZING: set[str] = set()
SYNTH_LOCK = threading.Lock()


def synthesize_later(project_id: str) -> None:
    """一次修改 / 回复结束后在后台看一眼：攒够几条新发言就整理一次记忆。失败了不打扰用户。"""
    if project_id in SYNTHESIZING:
        return
    try:
        meta = storage.load_meta(project_id)
        if memory.state_of(meta).get("paused") or memory.pending_count(meta) < memory.SYNTH_EVERY or not config.load().get("api_key"):
            return
    except Exception:
        return
    with SYNTH_LOCK:   # 先占上：两次修改紧挨着结束时别起两个整理（查和占要一起做，不然两个线程都查到「没在整理」）
        if project_id in SYNTHESIZING:
            return
        SYNTHESIZING.add(project_id)
    def go():
        try:
            memory.synthesize(project_id, _memory_llm())
        except Exception:
            logging.getLogger(__name__).warning("记忆整理没成功", exc_info=True)
        finally:
            SYNTHESIZING.discard(project_id)
    threading.Thread(target=go, daemon=True).start()


@router.get("/api/projects/{project_id}/memory")
def list_memory(project_id: str):
    try:
        snap = memory.snapshot(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    return {**snap, "memory": snap["project"]["memory"], "synthesizing": project_id in SYNTHESIZING}


class MemoryIn(BaseModel):
    note: str
    category: str = ""
    scope: str = "project"


class MemoryPatch(BaseModel):
    text: str = ""
    category: str = ""


class MemoryEditIn(BaseModel):
    instruction: str


class MemoryScopeIn(BaseModel):
    scope: str = "project"
    paused: bool = False


@router.post("/api/projects/{project_id}/memory")
def add_memory(project_id: str, body: MemoryIn):
    try:
        return memory.add(project_id, body.note, body.category, body.scope, "manual")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.patch("/api/projects/{project_id}/memory/{note_id}")
def patch_memory(project_id: str, note_id: str, body: MemoryPatch):
    try:
        return memory.update(project_id, note_id, body.text, body.category)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/projects/{project_id}/memory/{note_id}")
def delete_memory(project_id: str, note_id: str):
    return {"ok": memory.remove(project_id, note_id)}


@router.post("/api/projects/{project_id}/memory/edit")
def edit_memory(project_id: str, body: MemoryEditIn):
    try:
        return memory.edit_by_instruction(project_id, body.instruction, _memory_llm())
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/projects/{project_id}/memory/synthesize")
def synthesize_memory(project_id: str):
    try:
        return memory.synthesize(project_id, _memory_llm(), force=True)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/projects/{project_id}/memory/pause")
def pause_memory(project_id: str, body: MemoryScopeIn):
    memory.set_paused(project_id, body.scope, body.paused)
    return {"ok": True}


@router.post("/api/projects/{project_id}/memory/clear")
def clear_memory(project_id: str, body: MemoryScopeIn):
    memory.clear(project_id, body.scope)
    return {"ok": True}
