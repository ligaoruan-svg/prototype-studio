"""架构模式：读、存、让 AI 起草 / 补全 / 从现有原型整理"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .. import architecture, config, storage
from ..deepseek_client import chat
from ..errors import WorkError
from ..source_map import code_map

router = APIRouter()
PAGE_SOURCE_MAX = 80_000   # 从原型整理时最多给这么多源码；再长就给代码地图 + 开头一段


class ArchIn(BaseModel):
    architecture: dict


class DraftIn(BaseModel):
    mode: str = Field(default="request", pattern="^(request|page|refine)$")
    text: str = Field(default="", max_length=4000)
    page_id: str = ""


def _project(project_id: str) -> dict:
    try:
        return storage.load_meta(project_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "项目不存在") from exc


@router.get("/api/projects/{project_id}/architecture")
def get_architecture(project_id: str):
    _project(project_id)
    return architecture.bundle(architecture.load(project_id))


@router.put("/api/projects/{project_id}/architecture")
def put_architecture(project_id: str, body: ArchIn):
    _project(project_id)
    return architecture.bundle(architecture.save(project_id, body.architecture))


def page_source(project_id: str, page_id: str) -> str:
    source = storage.read_page(project_id, page_id)
    if len(source) <= PAGE_SOURCE_MAX:
        return source
    return "（源码太长，下面是代码地图和开头一段）\n" + code_map(source) + "\n" + source[:PAGE_SOURCE_MAX // 2]


def run_draft(project_id: str, body: DraftIn) -> dict:
    meta = _project(project_id)
    settings = config.load()
    if not settings.get("api_key"):
        raise WorkError("model_account", "请先在设置中保存 API 密钥")
    current = architecture.load(project_id)
    source = ""
    if body.mode == "page":
        page_id = body.page_id or (meta.get("pages") or [{}])[0].get("id", "")
        storage.get_page(meta, page_id)
        source = page_source(project_id, page_id)
    messages = architecture.draft_messages(body.mode, body.text.strip(), current, source)
    resp = chat(settings["api_key"], settings["model"], messages, None, base_url=settings["base_url"],
                max_tokens=max(8000, int(settings.get("max_tokens") or 16000)))
    choice = (resp.get("choices") or [{}])[0]
    reply = (choice.get("message") or {}).get("content") or ""
    try:
        fresh = architecture.parse_reply(reply)
    except ValueError as exc:
        cut = "（输出被截断了，可以在设置里调大单次输出）" if choice.get("finish_reason") in ("length", "max_tokens") else ""
        raise WorkError("invalid_arguments", "AI 给的架构读不出来" + cut + "，再试一次") from exc
    if body.mode == "refine":
        fresh = architecture.merge_ids(fresh, current)
    fresh["status"] = "draft"
    if current:   # 起草前的那一份留一个底，界面上「撤销」用得到
        storage.project_dir(project_id).joinpath("architecture.prev.json").write_text(json.dumps(current, ensure_ascii=False), "utf-8")
    return architecture.bundle(architecture.save(project_id, fresh))


@router.post("/api/projects/{project_id}/architecture/draft")
async def draft_architecture(project_id: str, body: DraftIn):
    return await run_in_threadpool(run_draft, project_id, body)
