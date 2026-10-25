"""架构：原型的镜子。读、存、用文字编辑（大纲）、粘贴功能清单；从展开图读出页面树（refresh）；
同步到原型以后记下这一刻的树（synced），之后在树里改了什么，和它一比就知道还有哪些没同步"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import arch_expand, architecture, storage
from ..arch_text import from_outline, from_table, keep_ids, looks_like_table, merge_nodes, to_outline

router = APIRouter()


class ArchIn(BaseModel):
    architecture: dict


class TextIn(BaseModel):
    text: str = Field(default="", max_length=200_000)
    mode: str = Field(default="append", pattern="^(append|replace)$")


class RefreshIn(BaseModel):
    page_id: str = ""
    force: bool = False   # 丢掉还没同步的改动，照原型重读


def _project(project_id: str) -> dict:
    try:
        return storage.load_meta(project_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "项目不存在") from exc


def bundle(arch: dict | None, project_id: str = "", **extra) -> dict:
    out = architecture.bundle(arch)
    out["outline"] = to_outline(arch)
    out["synced"] = architecture.load_synced(project_id) if project_id else None
    out.update(extra)
    return out


def _page_id(meta: dict, page_id: str) -> str:
    page_id = page_id or (meta.get("pages") or [{}])[0].get("id", "")
    storage.get_page(meta, page_id)
    return page_id


@router.get("/api/projects/{project_id}/architecture")
def get_architecture(project_id: str):
    _project(project_id)
    return bundle(architecture.load(project_id), project_id)


@router.put("/api/projects/{project_id}/architecture")
def put_architecture(project_id: str, body: ArchIn):
    _project(project_id)
    return bundle(architecture.save(project_id, body.architecture), project_id)


# 手动编：大纲改完整份读回来；路径没变的节点沿用原来的编号
@router.post("/api/projects/{project_id}/architecture/outline")
def put_outline(project_id: str, body: TextIn):
    _project(project_id)
    current = architecture.load(project_id)
    fresh = keep_ids(from_outline(body.text), current)
    if not fresh.get("lanes") and current:   # 大纲里没写流程：原来的流程留着
        fresh["lanes"], fresh["steps"] = current.get("lanes"), current.get("steps")
    return bundle(architecture.save(project_id, fresh), project_id)


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
        return bundle(architecture.save(project_id, base), project_id)
    merge_nodes(current["nodes"], incoming["nodes"])
    names = {e["name"] for e in current["entities"]}
    current["entities"] += [e for e in incoming.get("entities") or [] if e["name"] not in names]
    current["relations"] += incoming.get("relations") or []
    return bundle(architecture.save(project_id, current), project_id)


# 从原型读：展开图 → 页面树，你在树里写的介绍、字段控件带过去。树里有还没同步到原型的改动就先不读（除非 force）
@router.post("/api/projects/{project_id}/architecture/refresh")
def refresh(project_id: str, body: RefreshIn):
    meta = _project(project_id)
    current = architecture.load(project_id)
    if not body.force and architecture.pending(project_id, current):
        return bundle(current, project_id, refreshed=False, reason="pending")
    nodes = arch_expand.expand_tree(project_id, _page_id(meta, body.page_id))
    if not nodes:
        return bundle(current, project_id, refreshed=False, reason="no_expand")
    arch = current or architecture.empty()
    arch["nodes"] = arch_expand.carry(arch.get("nodes") or [], nodes)
    arch["name"] = arch.get("name") or meta.get("name", "")
    saved = architecture.save(project_id, arch)
    architecture.save_synced(project_id, saved["nodes"])
    return bundle(saved, project_id, refreshed=True)


# 「同步到原型」那一轮改完了：现在的树就是原型的样子
@router.post("/api/projects/{project_id}/architecture/synced")
def mark_synced(project_id: str):
    _project(project_id)
    current = architecture.load(project_id)
    if current:
        architecture.save_synced(project_id, current["nodes"])
    return bundle(current, project_id)
