"""架构：画布上的页面树。读、存；从原型读（展开图 → 页面树，只合并不冲掉）。
在画布上改结构用对话里的「架构」模式（见 arch_chat，走 agent/stream），或者直接在画布上手动改"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import arch_expand, architecture, storage

router = APIRouter()


class ArchIn(BaseModel):
    architecture: dict


class RefreshIn(BaseModel):
    page_id: str = ""


def _project(project_id: str) -> dict:
    try:
        return storage.load_meta(project_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "项目不存在") from exc


def _page_id(meta: dict, page_id: str) -> str:
    page_id = page_id or (meta.get("pages") or [{}])[0].get("id", "")
    storage.get_page(meta, page_id)
    return page_id


@router.get("/api/projects/{project_id}/architecture")
def get_architecture(project_id: str):
    _project(project_id)
    return architecture.bundle(architecture.load(project_id))


@router.put("/api/projects/{project_id}/architecture")
def put_architecture(project_id: str, body: ArchIn):
    _project(project_id)
    return architecture.bundle(architecture.save(project_id, body.architecture))


# 从原型读：原型里新做出来的补进画布，画布上规划的一个都不删，只标出和原型对不对得上
@router.post("/api/projects/{project_id}/architecture/refresh")
def refresh(project_id: str, body: RefreshIn):
    meta = _project(project_id)
    nodes = arch_expand.expand_tree(project_id, _page_id(meta, body.page_id))
    current = architecture.load(project_id)
    if not nodes:
        return {**architecture.bundle(current), "refreshed": False, "reason": "no_expand"}
    arch = current or architecture.empty()
    arch["nodes"] = arch_expand.merge(arch.get("nodes") or [], nodes)
    arch["name"] = arch.get("name") or meta.get("name", "")
    return {**architecture.bundle(architecture.save(project_id, arch)), "refreshed": True}
